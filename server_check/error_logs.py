import shlex

from server_check.common import DEFAULT_CONFIG
from utils.ssh_utils import run_command


def _collect_journal_errors(client, days, lines):
    cmd = (
        "bash -lc '"
        "if command -v journalctl >/dev/null 2>&1; then "
        "set -o pipefail; "
        f"journalctl --since \"{days} days ago\" -p err..alert --no-pager "
        "| grep -viE \"systemd-coredump|ldapdb_canonuser_plug_init\" | tail -n "
        f"{lines}; "
        "else echo __JOURNALCTL_NOT_FOUND__; fi'"
    )
    return run_command(client, cmd)


def _collect_file_errors(client, path, lines):
    quoted_path = shlex.quote(path)
    cmd = (
        "bash -lc "
        + shlex.quote(
            f"if [ -f {quoted_path} ]; then "
            "set -o pipefail; "
            f"grep -aiE 'error|failed|fatal|panic|crit|critical|异常' {quoted_path} | tail -n {lines}; "
            "fi"
        )
    )
    return run_command(client, cmd)


def log_error(client, filename, config=None, alerts=None):
    config = config or DEFAULT_CONFIG
    log_config = config.get("logs", {})
    days = max(1, int(log_config.get("days", 30)))
    lines = max(1, int(log_config.get("lines", 200)))
    log_paths = log_config.get("paths", DEFAULT_CONFIG["logs"]["paths"])
    journal_out, journal_err, journal_status = _collect_journal_errors(client, days, lines)

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 八、日志与系统错误\n\n")

    if "__JOURNALCTL_NOT_FOUND__" in journal_out:
        journal_title = "systemd journal 错误日志"
        journal_content = "当前系统未安装 journalctl。"
    elif journal_status == 0 and journal_out.strip():
        journal_title = f"systemd journal 错误日志（最近 {days} 天内，最近 {lines} 行）"
        journal_content = journal_out.strip()
    elif journal_status != 0 and journal_err.strip():
        journal_title = "systemd journal 错误日志"
        journal_content = journal_err.strip()
    else:
        journal_title = f"systemd journal 错误日志（最近 {days} 天内，最近 {lines} 行）"
        journal_content = "未匹配到 err..alert 级别日志。"

    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"### {journal_title}\n\n```text\n")
        f.write(journal_content + "\n")
        f.write("```\n\n")

    for log_path in log_paths:
        file_out, file_err, file_status = _collect_file_errors(client, log_path, lines)
        title = f"文件日志扫描：{log_path}（关键字匹配最近 {lines} 行）"
        content = None
        if file_status == 0 and file_out.strip():
            content = file_out.strip()
        elif file_err.strip():
            content = file_err.strip()
        elif file_status == 0:
            content = "文件存在，但未匹配到关键字日志。"
        if content is not None:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(f"### {title}\n\n```text\n")
                f.write(content + "\n")
                f.write("```\n\n")

    with open(filename, "a", encoding="utf-8") as f:
        f.write("---\n\n")
    return None
