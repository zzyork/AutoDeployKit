import re
import shlex

from server_check.common import DEFAULT_CONFIG
from utils.ssh_utils import run_command


def _normalize_services(config):
    services = []
    for item in config.get("services", DEFAULT_CONFIG["services"]):
        if isinstance(item, str):
            services.append((item, [item]))
        elif isinstance(item, dict):
            name = item.get("name")
            candidates = item.get("candidates") or [name]
            if name:
                services.append((name, candidates))
    return services


def service_status(client, filename, config=None, alerts=None):
    config = config or DEFAULT_CONFIG
    alerts = alerts if alerts is not None else []

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 四、服务与进程状态\n\n")

        for service_name, candidates in _normalize_services(config):
            loaded_service = None
            for candidate in candidates:
                if not isinstance(candidate, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@-]*", candidate):
                    continue
                info, _, status = run_command(client, f"systemctl show -p LoadState --value {shlex.quote(candidate)} 2>/dev/null")
                if status == 0 and info.strip() == "loaded":
                    loaded_service = candidate
                    break

            if loaded_service:
                info, _, _ = run_command(client, f"systemctl is-active {shlex.quote(loaded_service)} 2>/dev/null")
                status_text = info.strip()
                if status_text == "active":
                    f.write(f"- **{service_name}：** ✅ 运行中\n")
                elif status_text == "inactive":
                    f.write(f"- **{service_name}：** ❌ 未运行\n")
                    alerts.append(f"⚠️ **服务 {service_name}：** 已安装但未运行")
                else:
                    f.write(f"- **{service_name}：** ⚠️ {status_text}\n")
                    alerts.append(f"⚠️ **服务 {service_name}：** {status_text or '状态异常'}")

        f.write("\n---\n\n")
    return None
