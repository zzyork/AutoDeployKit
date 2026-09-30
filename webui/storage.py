import hashlib
import io
import json
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import paramiko
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from webui.assets import validate_host
from webui.security import hash_password, verify_password

SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_auth (id INTEGER PRIMARY KEY CHECK(id=1), password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, csrf_token TEXT NOT NULL, expires_at REAL NOT NULL, user_id TEXT NOT NULL, session_version TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ssh_keys (id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, public_key TEXT NOT NULL, private_cipher TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS hosts (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, address TEXT NOT NULL, port INTEGER NOT NULL,
    group_name TEXT NOT NULL, tags_json TEXT NOT NULL, username TEXT NOT NULL,
    password_cipher TEXT, ssh_key_id TEXT REFERENCES ssh_keys(id),
    proxy_host_id TEXT REFERENCES hosts(id), enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL, updated_at REAL NOT NULL, UNIQUE(address, port)
);
CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id), role TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, conversation_id TEXT REFERENCES conversations(id), tool_name TEXT, status TEXT NOT NULL,
    arguments_json TEXT NOT NULL, result_json TEXT, error TEXT, created_at REAL NOT NULL, started_at REAL, finished_at REAL);
"""


class Database:
    def __init__(self, data_dir, key_path):
        self.data_dir = Path(data_dir)
        self.key_path = Path(key_path)
        if not self.data_dir.is_absolute() or not self.key_path.is_absolute():
            raise ValueError("Database and encryption key paths must be absolute")
        if self.key_path == self.data_dir or self.data_dir in self.key_path.parents:
            raise ValueError("Encryption key must be outside the data directory")
        self.path = self.data_dir / "webui.sqlite3"
        self.report_root = self.data_dir / "reports"
        self.cipher = None

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        if not self.key_path.is_file():
            raise ValueError("Encryption key is missing")
        if self.data_dir.is_symlink() or self.report_root.is_symlink():
            raise ValueError("Data directory cannot be a symlink")
        self.cipher = Fernet(self.key_path.read_bytes())
        previous_database = self.path.exists()
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.report_root.mkdir(exist_ok=True, mode=0o700)
        with self._connection() as connection:
            connection.executescript(SCHEMA)
            if "user_id" not in {row["name"] for row in connection.execute("PRAGMA table_info(sessions)")}:
                connection.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT")
            if "session_version" not in {row["name"] for row in connection.execute("PRAGMA table_info(sessions)")}:
                connection.execute("ALTER TABLE sessions ADD COLUMN session_version TEXT")
            row = connection.execute("SELECT value FROM settings WHERE key='key_check'").fetchone()
            if row is None:
                if previous_database:
                    raise ValueError("Database encryption key check is missing")
                marker = self.cipher.encrypt(b"autodeploykit-webui-v1").decode("ascii")
                connection.execute(
                    "INSERT INTO settings (key,value) VALUES ('key_check',?)", (marker,)
                )
            else:
                try:
                    if (
                        self.cipher.decrypt(row["value"].encode("ascii"))
                        != b"autodeploykit-webui-v1"
                    ):
                        raise ValueError("Invalid encryption key")
                except InvalidToken as exc:
                    raise ValueError("Invalid encryption key") from exc
            connection.execute(
                "UPDATE jobs SET status='interrupted', finished_at=? WHERE status IN ('queued','running')",
                (time.time(),),
            )

    def _encrypt(self, text):
        return self.cipher.encrypt(text.encode("utf-8")).decode("ascii")

    def _decrypt(self, text):
        return self.cipher.decrypt(text.encode("ascii")).decode("utf-8")

    def set_admin_password(self, password):
        hashed = hash_password(password)
        with self._connection() as connection:
            if connection.execute("SELECT 1 FROM admin_auth WHERE id=1").fetchone():
                raise ValueError("Administrator is already initialized")
            connection.execute("INSERT INTO admin_auth (id,password_hash) VALUES (1,?)", (hashed,))

    def verify_admin(self, password):
        with self._connection() as connection:
            row = connection.execute("SELECT password_hash FROM admin_auth WHERE id=1").fetchone()
        return bool(row) and verify_password(password, row["password_hash"])

    def admin_is_initialized(self):
        with self._connection() as connection:
            return connection.execute("SELECT 1 FROM admin_auth WHERE id=1").fetchone() is not None

    def clear_legacy_admin(self):
        with self._connection() as connection:
            connection.execute("DELETE FROM admin_auth WHERE id=1")

    def create_session(self, user_id, session_version):
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO sessions (token_hash,csrf_token,expires_at,user_id,session_version) VALUES (?,?,?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), csrf, time.time() + 43200, str(user_id), session_version),
            )
        return token, csrf

    def get_session(self, token):
        if not token:
            return None
        with self._connection() as connection:
            row = connection.execute(
                "SELECT s.csrf_token, u.id, u.username, u.is_superuser "
                "FROM sessions s JOIN user u ON u.id=s.user_id AND u.is_active=1 AND u.session_version=s.session_version "
                "WHERE s.token_hash=? AND s.expires_at>?",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            ).fetchone()
        return {
            "csrf_token": row["csrf_token"], "id": row["id"],
            "username": row["username"], "is_admin": bool(row["is_superuser"]),
        } if row else None

    def revoke_user_sessions(self, user_id):
        with self._connection() as connection:
            connection.execute("DELETE FROM sessions WHERE user_id=?", (str(user_id),))

    def end_session(self, token):
        if token:
            with self._connection() as connection:
                connection.execute(
                    "DELETE FROM sessions WHERE token_hash=?",
                    (hashlib.sha256(token.encode()).hexdigest(),),
                )

    def create_key(self, name):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError("Invalid key name")
        private = Ed25519PrivateKey.generate()
        secret = private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption(),
        ).decode("ascii")
        public = (
            private.public_key()
            .public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
            .decode("ascii")
        )
        key = {"id": uuid.uuid4().hex, "name": name.strip(), "public_key": public}
        with self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO ssh_keys VALUES (?,?,?,?,?)",
                    (key["id"], key["name"], public, self._encrypt(secret), time.time()),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("SSH key name is already registered") from exc
        return key

    def list_keys(self):
        with self._connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT id,name,public_key,created_at FROM ssh_keys ORDER BY name"
                )
            ]

    def _pkey(self, connection, key_id):
        row = connection.execute(
            "SELECT private_cipher FROM ssh_keys WHERE id=?", (key_id,)
        ).fetchone()
        if row is None:
            raise ValueError("SSH key is unavailable")
        return paramiko.Ed25519Key.from_private_key(
            io.StringIO(self._decrypt(row["private_cipher"]))
        )

    @staticmethod
    def _public_host(row):
        return {
            key: row[key]
            for key in (
                "id",
                "name",
                "address",
                "port",
                "group_name",
                "username",
                "ssh_key_id",
                "proxy_host_id",
                "enabled",
                "created_at",
                "updated_at",
            )
        } | {"tags": json.loads(row["tags_json"]), "has_password": bool(row["password_cipher"])}

    def list_hosts(self):
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM hosts ORDER BY name").fetchall()
        return [self._public_host(row) for row in rows]

    def add_host(
        self,
        *,
        name,
        address,
        username,
        port=22,
        group_name="default",
        tags=None,
        password=None,
        ssh_key_id=None,
        proxy_host_id=None,
    ):
        validate_host(name, address, port, username, group_name)
        if bool(password) == bool(ssh_key_id):
            raise ValueError("Choose exactly one SSH credential")
        if tags is None:
            tags = []
        if (
            not isinstance(tags, list)
            or len(tags) > 20
            or any(not isinstance(tag, str) or len(tag) > 40 for tag in tags)
        ):
            raise ValueError("Invalid asset tags")
        now = time.time()
        host_id = uuid.uuid4().hex
        with self._connection() as connection:
            if (
                ssh_key_id
                and not connection.execute(
                    "SELECT 1 FROM ssh_keys WHERE id=?", (ssh_key_id,)
                ).fetchone()
            ):
                raise ValueError("Unknown SSH key")
            if proxy_host_id:
                proxy = connection.execute(
                    "SELECT enabled,proxy_host_id FROM hosts WHERE id=?", (proxy_host_id,)
                ).fetchone()
                if proxy is None or not proxy["enabled"] or proxy["proxy_host_id"]:
                    raise ValueError("Invalid jump host")
            try:
                connection.execute(
                    "INSERT INTO hosts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        host_id,
                        name.strip(),
                        address.strip(),
                        port,
                        group_name.strip(),
                        json.dumps(tags),
                        username,
                        self._encrypt(password) if password else None,
                        ssh_key_id,
                        proxy_host_id,
                        1,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Asset name or address is already registered") from exc
            row = connection.execute("SELECT * FROM hosts WHERE id=?", (host_id,)).fetchone()
        return self._public_host(row)

    def update_host(self, host_id, **changes):
        permitted = {
            "name",
            "address",
            "port",
            "group_name",
            "username",
            "tags",
            "password",
            "ssh_key_id",
            "proxy_host_id",
            "enabled",
        }
        if not changes or set(changes) - permitted:
            raise ValueError("Invalid host update")
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM hosts WHERE id=?", (host_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown asset")
            new = dict(row)
            for key in (
                "name",
                "address",
                "port",
                "group_name",
                "username",
                "proxy_host_id",
                "ssh_key_id",
                "enabled",
            ):
                if key in changes:
                    new[key] = changes[key]
            if "password" in changes:
                new["password_cipher"] = (
                    self._encrypt(changes["password"]) if changes["password"] else None
                )
                new["ssh_key_id"] = None
            elif "ssh_key_id" in changes and changes["ssh_key_id"]:
                new["password_cipher"] = None
            if "tags" in changes:
                if (
                    not isinstance(changes["tags"], list)
                    or len(changes["tags"]) > 20
                    or any(not isinstance(tag, str) or len(tag) > 40 for tag in changes["tags"])
                ):
                    raise ValueError("Invalid asset tags")
                new["tags_json"] = json.dumps(changes["tags"])
            validate_host(
                new["name"], new["address"], new["port"], new["username"], new["group_name"]
            )
            if bool(new["password_cipher"]) == bool(new["ssh_key_id"]):
                raise ValueError("Choose exactly one SSH credential")
            if new["proxy_host_id"] == host_id:
                raise ValueError("Asset cannot proxy itself")
            if new["proxy_host_id"]:
                proxy = connection.execute(
                    "SELECT enabled,proxy_host_id FROM hosts WHERE id=?", (new["proxy_host_id"],)
                ).fetchone()
                if proxy is None or not proxy["enabled"] or proxy["proxy_host_id"]:
                    raise ValueError("Invalid jump host")
            if (
                new["ssh_key_id"]
                and not connection.execute(
                    "SELECT 1 FROM ssh_keys WHERE id=?", (new["ssh_key_id"],)
                ).fetchone()
            ):
                raise ValueError("Unknown SSH key")
            try:
                connection.execute(
                    """UPDATE hosts SET name=?,address=?,port=?,group_name=?,tags_json=?,username=?,password_cipher=?,ssh_key_id=?,proxy_host_id=?,enabled=?,updated_at=? WHERE id=?""",
                    (
                        new["name"],
                        new["address"],
                        new["port"],
                        new["group_name"],
                        new["tags_json"],
                        new["username"],
                        new["password_cipher"],
                        new["ssh_key_id"],
                        new["proxy_host_id"],
                        int(bool(new["enabled"])),
                        time.time(),
                        host_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("Asset name or address is already registered") from exc
            updated = connection.execute("SELECT * FROM hosts WHERE id=?", (host_id,)).fetchone()
        return self._public_host(updated)

    def resolve_hosts(self, pattern):
        if not isinstance(pattern, str) or not pattern or len(pattern) > 253:
            raise ValueError("Invalid asset target")
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM hosts WHERE enabled=1 ORDER BY name"
            ).fetchall()
        if pattern == "all":
            matched = rows
        else:
            matched = [
                row
                for row in rows
                if pattern in (row["id"], row["name"], row["address"], row["group_name"])
            ]
            if any(pattern == row["group_name"] for row in matched) and any(
                pattern in (row["name"], row["address"], row["id"]) for row in matched
            ):
                raise ValueError("Ambiguous asset target")
            if not any(pattern == row["group_name"] for row in matched) and len(matched) > 1:
                raise ValueError("Ambiguous asset target")
        if not matched:
            raise ValueError("No enabled assets match")
        return [self._public_host(row) for row in matched]

    def connection_settings(self, host_id):
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM hosts WHERE id=? AND enabled=1", (host_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Asset is unavailable")
            result = {
                "host": row["address"],
                "user": row["username"],
                "port": row["port"],
                "web": True,
            }
            if row["ssh_key_id"]:
                result["pkey"] = self._pkey(connection, row["ssh_key_id"])
            elif row["password_cipher"]:
                result["password"] = self._decrypt(row["password_cipher"])
            else:
                raise ValueError("Asset has no credentials")
            if row["proxy_host_id"]:
                proxy = connection.execute(
                    "SELECT * FROM hosts WHERE id=? AND enabled=1", (row["proxy_host_id"],)
                ).fetchone()
                if proxy is None or proxy["proxy_host_id"]:
                    raise ValueError("Jump host is unavailable")
                result.update(
                    proxy=proxy["address"], proxy_port=proxy["port"], proxy_user=proxy["username"]
                )
                if proxy["ssh_key_id"]:
                    result["proxy_pkey"] = self._pkey(connection, proxy["ssh_key_id"])
                elif proxy["password_cipher"]:
                    result["proxy_password"] = self._decrypt(proxy["password_cipher"])
                else:
                    raise ValueError("Jump host has no credentials")
        return result

    def set_model_settings(self, base_url, model, api_key=None):
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Invalid model API URL")
        if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("Non-local model API must use HTTPS")
        if not isinstance(model, str) or not 1 <= len(model.strip()) <= 100:
            raise ValueError("Invalid model name")
        with self._connection() as connection:
            for key, value in (
                ("model_base_url", base_url.rstrip("/")),
                ("model_name", model.strip()),
            ):
                connection.execute(
                    "INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)", (key, value)
                )
            if api_key is not None:
                connection.execute(
                    "INSERT OR REPLACE INTO settings (key,value) VALUES ('model_api_key',?)",
                    (self._encrypt(api_key) if api_key else "",),
                )

    def model_credentials(self):
        with self._connection() as connection:
            values = dict(
                connection.execute(
                    "SELECT key,value FROM settings WHERE key LIKE 'model_%'"
                ).fetchall()
            )
        return {
            "base_url": values.get("model_base_url", ""),
            "model": values.get("model_name", ""),
            "api_key": self._decrypt(values["model_api_key"])
            if values.get("model_api_key")
            else "",
        }

    def get_model_settings(self):
        credentials = self.model_credentials()
        return {
            "base_url": credentials["base_url"],
            "model": credentials["model"],
            "has_api_key": bool(credentials["api_key"]),
        }

    def create_conversation(self, title):
        conversation_id = uuid.uuid4().hex
        now = time.time()
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO conversations VALUES (?,?,?,?)",
                (conversation_id, title[:80], now, now),
            )
        return conversation_id

    def add_message(self, conversation_id, role, content):
        if role not in ("user", "assistant"):
            raise ValueError("Invalid message role")
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO messages VALUES (?,?,?,?,?)",
                (uuid.uuid4().hex, conversation_id, role, content[:8000], time.time()),
            )
            connection.execute(
                "UPDATE conversations SET updated_at=? WHERE id=?", (time.time(), conversation_id)
            )

    def list_conversations(self):
        with self._connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT 100"
                )
            ]

    def has_conversation(self, conversation_id):
        with self._connection() as connection:
            return (
                connection.execute(
                    "SELECT 1 FROM conversations WHERE id=?", (conversation_id,)
                ).fetchone()
                is not None
            )

    def get_messages(self, conversation_id):
        with self._connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT id,role,content,created_at FROM messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT 30",
                    (conversation_id,),
                )
            ][::-1]

    def create_job(self, conversation_id, arguments):
        job_id = uuid.uuid4().hex
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO jobs (id,conversation_id,status,arguments_json,created_at) VALUES (?,?,'queued',?,?)",
                (job_id, conversation_id, json.dumps(arguments), time.time()),
            )
        return job_id

    def update_job(self, job_id, status, *, tool_name=None, result=None, error=None):
        if status not in ("queued", "running", "succeeded", "partial", "failed", "interrupted"):
            raise ValueError("Invalid job status")
        now = time.time()
        with self._connection() as connection:
            connection.execute(
                """UPDATE jobs SET status=?,tool_name=COALESCE(?,tool_name),
                result_json=COALESCE(?,result_json),error=?,started_at=CASE WHEN ?='running' THEN COALESCE(started_at,?) ELSE started_at END,
                finished_at=CASE WHEN ? IN ('succeeded','partial','failed','interrupted') THEN ? ELSE finished_at END WHERE id=?""",
                (
                    status,
                    tool_name,
                    json.dumps(result) if result is not None else None,
                    error,
                    status,
                    now,
                    status,
                    now,
                    job_id,
                ),
            )

    @staticmethod
    def _public_job(row):
        job = dict(row)
        job["arguments"] = json.loads(job.pop("arguments_json"))
        result_json = job.pop("result_json")
        job["result"] = json.loads(result_json) if result_json else None
        return job

    def get_job(self, job_id):
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._public_job(row) if row else None

    def list_jobs(self):
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        return [self._public_job(row) for row in rows]

    def list_reports(self):
        reports = []
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE result_json IS NOT NULL AND status IN ('succeeded','partial','failed','interrupted') ORDER BY created_at DESC"
            ).fetchall()
        for job in (self._public_job(row) for row in rows):
            reports.extend(
                {
                    "id": host["report_id"],
                    "host": host["host"],
                    "job_id": job["id"],
                    "risk_count": host["risk_count"],
                    "created_at": job["finished_at"],
                }
                for host in (job["result"] or {}).get("hosts", [])
                if host.get("report_id")
            )
        return reports

    def report_path(self, report_id):
        if not isinstance(report_id, str) or not re.fullmatch(r"[0-9a-f]{32}", report_id):
            raise ValueError("Invalid report ID")
        if not any(report["id"] == report_id for report in self.list_reports()):
            raise ValueError("Unknown report")
        if self.report_root.is_symlink():
            raise ValueError("Report directory is unavailable")
        root = self.report_root.resolve()
        path = root / f"{report_id}.md"
        if path.is_symlink() or not path.is_file() or path.resolve().parent != root:
            raise ValueError("Report is unavailable")
        return path
