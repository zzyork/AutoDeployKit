import argparse
import getpass
import hmac
import os
import sys
from importlib.resources import files
from pathlib import Path

from webui.security import create_key_file
from webui.storage import Database


def main():
    parser = argparse.ArgumentParser(description="Initialize the installed WebUI locally")
    parser.add_argument("--data-dir", default=os.getenv("WEBUI_DATA_DIR"))
    parser.add_argument("--key-file", default=os.getenv("WEBUI_KEY_FILE"))
    parser.add_argument("--create-key-only", action="store_true")
    parser.add_argument("--write-instructions", metavar="INSTALL_DIR")
    args = parser.parse_args()
    if args.write_instructions:
        install_dir = Path(args.write_instructions)
        if not install_dir.is_absolute() or not install_dir.is_dir():
            parser.error("Installation directory must already exist")
        for name in ("AGENTS.md", "CLAUDE.md"):
            template = files("webui").joinpath("install", name).read_text(encoding="utf-8")
            (install_dir / name).write_text(template, encoding="utf-8")
        return
    if not args.data_dir or not args.key_file:
        parser.error("Provide --data-dir and --key-file")
    db = Database(args.data_dir, args.key_file)
    if not db.key_path.exists():
        if db.path.exists():
            parser.error("Database exists but encryption key is missing")
        create_key_file(db.key_path)
    if args.create_key_only:
        return
    db.initialize()
    if db.admin_is_initialized():
        print("管理员口令已设置。")
        return
    if not sys.stdin.isatty():
        parser.error("First initialization requires a local terminal")
    password = getpass.getpass("设置管理员口令（至少 12 字符）：")
    confirm = getpass.getpass("再次输入管理员口令：")
    if not hmac.compare_digest(password, confirm):
        parser.error("口令不一致")
    db.set_admin_password(password)
    print("管理员口令已设置。")


if __name__ == "__main__":
    main()
