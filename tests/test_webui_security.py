import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from webui.security import create_key_file, hash_password, verify_password
from webui.storage import Database


class WebSecurityTests(unittest.TestCase):
    def test_password_hash_has_salt_and_verifies(self):
        first = hash_password("long-example-passphrase")
        second = hash_password("long-example-passphrase")
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("long-example-passphrase", first))
        self.assertFalse(verify_password("wrong", first))

    def test_existing_database_refuses_replaced_or_missing_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key_path = root / "master.key"
            create_key_file(key_path)
            Database(root / "data", key_path).initialize()
            key_path.write_bytes(Fernet.generate_key())
            with self.assertRaises(ValueError):
                Database(root / "data", key_path).initialize()
            key_path.unlink()
            with self.assertRaises(ValueError):
                Database(root / "data", key_path).initialize()

    def test_admin_session_and_api_key_are_not_returned_as_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key_path = root / "master.key"
            create_key_file(key_path)
            db = Database(root / "data", key_path)
            db.initialize()
            db.set_admin_password("long-example-passphrase")
            self.assertTrue(db.verify_admin("long-example-passphrase"))
            token, csrf = db.create_session()
            self.assertEqual(db.get_session(token), csrf)
            db.end_session(token)
            self.assertIsNone(db.get_session(token))
            db.set_model_settings("https://model.example/v1", "demo", "provider-secret")
            self.assertEqual(db.get_model_settings()["has_api_key"], True)
            self.assertNotIn("provider-secret", str(db.get_model_settings()))
            self.assertEqual(db.model_credentials()["api_key"], "provider-secret")
            with self.assertRaises(ValueError):
                db.set_model_settings("http://model.example/v1", "demo", "provider-secret")


if __name__ == "__main__":
    unittest.main()
