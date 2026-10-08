import argparse
import asyncio
import ipaddress
import os
import secrets
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from pathlib import Path

from cryptography import x509
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

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


def ensure_tls_certificate(key_directory, addresses):
    ips = tuple(
        dict.fromkeys(ipaddress.IPv4Address(value.strip()) for value in addresses.split(","))
    )
    directory = Path(key_directory)
    cert_file = directory / "tls.crt"
    key_file = directory / "tls.key"
    if cert_file.is_symlink() or key_file.is_symlink():
        raise ValueError("TLS certificate and key cannot be symlinks")
    if cert_file.exists() != key_file.exists():
        raise ValueError("TLS certificate and key must both exist or both be absent")
    existing = cert_file.exists()
    if existing:
        certificate = x509.load_pem_x509_certificate(cert_file.read_bytes())
        private_key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
        if certificate.public_key().public_numbers() != private_key.public_key().public_numbers():
            raise ValueError("TLS certificate and key do not match")
        existing_ips = set(
            certificate.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            ).value.get_values_for_type(x509.IPAddress)
        )
        if set(ips) == existing_ips and certificate.not_valid_after_utc > datetime.now(
            timezone.utc
        ) + timedelta(days=30):
            return

    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, str(ips[0]))]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, str(ips[0]))]))
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=397))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ip) for ip in ips]), critical=False
        )
        .sign(private_key, hashes.SHA256())
    )
    new_key = key_file.with_suffix(".key.new")
    new_cert = cert_file.with_suffix(".crt.new")
    try:
        if not existing:
            with os.fdopen(
                os.open(new_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
            ) as stream:
                stream.write(
                    private_key.private_bytes(
                        serialization.Encoding.PEM,
                        serialization.PrivateFormat.TraditionalOpenSSL,
                        serialization.NoEncryption(),
                    )
                )
        with os.fdopen(
            os.open(new_cert, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644), "wb"
        ) as stream:
            stream.write(certificate.public_bytes(serialization.Encoding.PEM))
        if not existing:
            new_key.replace(key_file)
        new_cert.replace(cert_file)
    finally:
        new_key.unlink(missing_ok=True)
        new_cert.unlink(missing_ok=True)


def backup_installation(db, destination):
    target = Path(destination)
    if (
        not target.is_absolute()
        or target.is_symlink()
        or not target.is_dir()
        or any(target.iterdir())
    ):
        raise ValueError("Backup directory must be an existing empty absolute directory")
    if not db.path.is_file() or not db.key_path.is_file():
        raise ValueError("Database or encryption key is missing")
    if (
        db.data_dir.is_symlink()
        or db.report_root.is_symlink()
        or db.path.is_symlink()
        or db.key_path.is_symlink()
        or db.key_path.parent.is_symlink()
    ):
        raise ValueError("Backup source cannot contain symlinks")
    for root in (db.report_root, db.key_path.parent):
        for base, dirs, filenames in os.walk(root):
            if any((Path(base) / name).is_symlink() for name in dirs + filenames):
                raise ValueError("Backup source cannot contain symlinks")

    copy_path = target / "webui.sqlite3"
    with (
        sqlite3.connect(db.path.as_uri() + "?mode=ro", uri=True) as source,
        sqlite3.connect(copy_path) as copy,
    ):
        source.backup(copy)
        if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity check failed")
        marker = copy.execute("SELECT value FROM settings WHERE key='key_check'").fetchone()
    try:
        valid_key = (
            marker is not None
            and Fernet(db.key_path.read_bytes()).decrypt(marker[0].encode())
            == b"autodeploykit-webui-v1"
        )
    except (InvalidToken, ValueError) as exc:
        raise ValueError("Encryption key does not match database") from exc
    if not valid_key:
        raise ValueError("Encryption key does not match database")
    copy_path.chmod(0o600)
    if db.report_root.exists():
        shutil.copytree(db.report_root, target / "reports")
    key_target = target / "keys"
    shutil.copytree(db.key_path.parent, key_target)
    key_target.chmod(0o700)
    for entry in key_target.iterdir():
        if entry.is_file():
            entry.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description="Initialize the installed WebUI locally")
    parser.add_argument("--data-dir", default=os.getenv("WEBUI_DATA_DIR"))
    parser.add_argument("--key-file", default=os.getenv("WEBUI_KEY_FILE"))
    parser.add_argument("--create-key-only", action="store_true")
    parser.add_argument("--write-instructions", metavar="INSTALL_DIR")
    parser.add_argument(
        "--tls-ips",
        "--tls-ip",
        dest="tls_ips",
        default=os.getenv("WEBUI_TLS_IPS") or os.getenv("WEBUI_TLS_IP"),
    )
    parser.add_argument("--tls-only", action="store_true")
    parser.add_argument("--tls-fingerprint", action="store_true")
    parser.add_argument("--backup-dir")
    args = parser.parse_args()
    if args.tls_fingerprint:
        if not args.key_file:
            parser.error("Provide --key-file")
        cert_file = Path(args.key_file).parent / "tls.crt"
        print(
            x509.load_pem_x509_certificate(cert_file.read_bytes())
            .fingerprint(hashes.SHA256())
            .hex()
        )
        return
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
    if args.backup_dir:
        backup_installation(db, args.backup_dir)
        return
    if not args.tls_ips and not args.create_key_only:
        parser.error("Provide --tls-ips or WEBUI_TLS_IPS")
    if args.tls_only:
        if not db.path.is_file() or not db.key_path.is_file():
            parser.error("Existing database and encryption key are required")
        ensure_tls_certificate(db.key_path.parent, args.tls_ips)
        return
    if not db.key_path.exists():
        if db.path.exists():
            parser.error("Database exists but encryption key is missing")
        create_key_file(db.key_path)
    if args.create_key_only:
        return
    db.initialize()
    ensure_tls_certificate(db.key_path.parent, args.tls_ips)
    try:
        asyncio.run(initialize_users(db))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
