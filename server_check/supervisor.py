import re

from utils.ssh_utils import run_command


def supervisor_status(client, filename, config=None, alerts=None):
    alerts = alerts if alerts is not None else []
    _, _, status = run_command(client, "command -v supervisorctl >/dev/null 2>&1")

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 七、Supervisor 子应用状态\n\n")

    if status != 0:
        with open(filename, "a", encoding="utf-8") as f:
            f.write("未安装 supervisorctl，跳过 Supervisor 子应用巡检。\n\n---\n\n")
        return None

    status_out, status_err, status_code = run_command(client, "supervisorctl status 2>&1")
    content = status_out if status_code == 0 else status_err or status_out
    for line in content.splitlines():
        if re.search(r"\b(FATAL|BACKOFF|STOPPED|EXITED|UNKNOWN)\b", line):
            alerts.append(f"⚠️ **Supervisor 子应用异常：** {line.strip()}")

    with open(filename, "a", encoding="utf-8") as f:
        f.write("### supervisorctl status\n\n```text\n")
        f.write(content.strip() + "\n" if content.strip() else "未发现 Supervisor 子应用。\n")
        f.write("```\n\n")
        f.write("---\n\n")
    return None
