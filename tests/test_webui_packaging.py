import os
import unittest
from pathlib import Path
from zipfile import ZipFile


class WheelContentsTests(unittest.TestCase):
    def test_installer_requires_binary_dependencies(self):
        installer = (Path(__file__).resolve().parents[1] / "scripts/install_webui.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('pip install --no-input --only-binary=:all: "${WHEEL}[web]"', installer)

    @unittest.skipUnless(
        os.environ.get("WEBUI_TEST_WHEEL"), "Set WEBUI_TEST_WHEEL to verify a built wheel"
    )
    def test_wheel_contains_entrypoints_static_files_and_installed_rules(self):
        with ZipFile(os.environ["WEBUI_TEST_WHEEL"]) as wheel:
            names = set(wheel.namelist())
        for name in (
            "cli.py",
            "webui/app.py",
            "webui/bootstrap.py",
            "webui/static/index.html",
            "webui/static/app.css",
            "webui/static/app.js",
            "webui/install/AGENTS.md",
            "webui/install/CLAUDE.md",
            "utils/ssh_utils.py",
            "server_check/main.py",
        ):
            with self.subTest(name=name):
                self.assertIn(name, names)


if __name__ == "__main__":
    unittest.main()
