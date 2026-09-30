import argparse
import asyncio
import os
import secrets
import sys
from importlib.resources import files
from pathlib import Path

from webui.security import create_key_file
from webui.storage import Database
from webui.users import UserStore


async def initialize_users(db):
    users = UserStore(db)
    try:
        await users.initialize()
        if await users.any_users() or db.admin_is_initialized():
            print("管理员账号已存在，不重新生成口令。")
            return
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise ValueError("首次初始化需要交互终端显示初始口令")
        password = secrets.token_urlsafe(24)
        await users.create("admin", password, admin=True)
        print(f"初始账号：admin\n初始口令：{password}\n请立即将口令保存到安全位置。")
    finally:
        await users.close()


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
    try:
        asyncio.run(initialize_users(db))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
