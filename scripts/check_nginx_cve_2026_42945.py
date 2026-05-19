import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cli import load_hosts  # noqa: E402
from utils.ssh_utils import close_ssh_client, run_command, ssh_connect  # noqa: E402


VERSION_RE = re.compile(r"nginx(?: version)?: nginx/(?P<version>\d+\.\d+\.\d+)")


def parse_version(text):
    match = VERSION_RE.search(text or "")
    return match.group("version") if match else ""


def version_tuple(version):
    return tuple(int(part) for part in version.split("."))


def affected_by_version(version):
    if not version:
        return False
    v = version_tuple(version)
    return version_tuple("0.6.27") <= v <= version_tuple("1.30.0")


def check_one(entry):
    host = entry["host"]
    target = entry.get("vip") or host
    group = entry.get("group", "")
    client = None
    try:
        client = ssh_connect(
            target,
            entry.get("user"),
            entry.get("password"),
            entry.get("key_file"),
            entry.get("port"),
            entry.get("proxy"),
            entry.get("proxy_user"),
            entry.get("proxy_password"),
            entry.get("proxy_keyfile"),
            entry.get("proxy_port"),
        )

        version_out, version_err, version_status = run_command(
            client,
            "command -v nginx >/dev/null 2>&1 && nginx -v 2>&1 || echo __NGINX_NOT_FOUND__",
        )
        combined_version = "\n".join(part for part in [version_out, version_err] if part)
        version = parse_version(combined_version)
        nginx_found = "__NGINX_NOT_FOUND__" not in combined_version and bool(version)

        config_hits = ""
        config_status = None
        if nginx_found:
            # 只读检查：输出可能触发该漏洞的 rewrite 规则行，不落盘、不修改配置。
            config_hits, config_err, config_status = run_command(
                client,
                r"nginx -T 2>/dev/null | grep -nE '^[[:space:]]*rewrite[[:space:]].*\$[0-9].*\?' | head -n 20",
            )
            if config_err and not config_hits:
                config_hits = ""

        return {
            "host": host,
            "target": target,
            "group": group,
            "connected": True,
            "nginx_found": nginx_found,
            "version": version,
            "version_raw": combined_version.strip(),
            "affected_by_version": affected_by_version(version),
            "suspicious_rewrite_hits": config_hits.strip(),
            "config_check_status": config_status,
            "error": "",
        }
    except Exception as exc:
        return {
            "host": host,
            "target": target,
            "group": group,
            "connected": False,
            "nginx_found": False,
            "version": "",
            "version_raw": "",
            "affected_by_version": False,
            "suspicious_rewrite_hits": "",
            "config_check_status": None,
            "error": str(exc),
        }
    finally:
        if client is not None:
            close_ssh_client(client)


def main():
    pattern = sys.argv[1] if len(sys.argv) > 1 else "all"
    hosts = load_hosts(pattern, str(ROOT / "hosts"))
    max_workers = min(len(hosts), 8) or 1
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(check_one, entry) for entry in hosts]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status = "连接失败"
            if result["connected"] and result["nginx_found"]:
                status = f"nginx {result['version']}"
            elif result["connected"]:
                status = "未发现 nginx"
            print(f"[{result['group']}] {result['host']} -> {status}", flush=True)

    results.sort(key=lambda item: (item["group"], item["host"]))
    print("__JSON_RESULT_START__")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
