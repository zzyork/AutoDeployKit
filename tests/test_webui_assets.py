import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from webui.security import create_key_file
from webui.storage import Database


class WebAssetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.key_path = root / "master.key"
        create_key_file(self.key_path)
        self.db = Database(root / "data", self.key_path)
        self.db.initialize()

    def test_host_password_is_encrypted_and_not_listed(self):
        host = self.db.add_host(
            name="demo",
            address="example.invalid",
            port=2222,
            username="operator",
            password="ssh-secret",
            group_name="sample",
        )
        self.assertNotIn("ssh-secret", str(self.db.list_hosts()))
        with closing(sqlite3.connect(self.db.path)) as connection:
            raw = connection.execute(
                "SELECT password_cipher FROM hosts WHERE id=?", (host["id"],)
            ).fetchone()[0]
        self.assertNotIn("ssh-secret", raw)
        self.assertEqual(self.db.connection_settings(host["id"])["password"], "ssh-secret")
        self.assertEqual([item["id"] for item in self.db.resolve_hosts("sample")], [host["id"]])
        self.db.update_host(host["id"], enabled=False)
        with self.assertRaises(ValueError):
            self.db.resolve_hosts("demo")

    def test_generated_key_can_be_used_for_target_and_proxy(self):
        key = self.db.create_key("shared")
        proxy = self.db.add_host(
            name="jump", address="jump.invalid", username="jump", ssh_key_id=key["id"]
        )
        target = self.db.add_host(
            name="app",
            address="app.invalid",
            username="app",
            ssh_key_id=key["id"],
            proxy_host_id=proxy["id"],
        )
        connection = self.db.connection_settings(target["id"])
        self.assertEqual(connection["pkey"].get_name(), "ssh-ed25519")
        self.assertEqual(connection["proxy_pkey"].get_name(), "ssh-ed25519")
        self.assertEqual(connection["proxy"], "jump.invalid")
        self.assertNotIn("private", str(self.db.list_keys()))

    def test_address_match_must_be_unique(self):
        self.db.add_host(
            name="first", address="shared.invalid", port=22, username="operator", password="demo"
        )
        self.db.add_host(
            name="second", address="shared.invalid", port=2222, username="operator", password="demo"
        )
        with self.assertRaises(ValueError):
            self.db.resolve_hosts("shared.invalid")
        with self.assertRaises(ValueError):
            self.db.add_host(
                name="first", address="another.invalid", username="operator", password="demo"
            )


if __name__ == "__main__":
    unittest.main()
