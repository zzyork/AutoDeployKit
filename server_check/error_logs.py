from utils.ssh_utils import run_command


def _append_log_section(filename, title, content, fallback_message):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"### {title}\n\n```text\n")
        f.write(content.strip() + "\n" if content.strip() else fallback_message + "\n")
        f.write("```\n\n")


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
    cmd = (
        "bash -lc '"
        f"if [ -f {path} ]; then "
        "set -o pipefail; "
        f"grep -aiE \"error|failed|fatal|panic|crit|critical|异常\" {path} | tail -n {lines}; "
        "fi'"
    )
    return run_command(client, cmd)


def log_error(client, filename, days=30, lines=200):
    days = max(1, int(days))
    lines = max(1, int(lines))
    journal_out, journal_err, journal_status = _collect_journal_errors(client, days, lines)

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 六、日志与系统错误\n\n")

    if "__JOURNALCTL_NOT_FOUND__" in journal_out:
        _append_log_section(filename, "systemd journal 错误日志", "", "当前系统未安装 journalctl。")
    elif journal_status == 0 and journal_out.strip():
        _append_log_section(
            filename,
            f"systemd journal 错误日志（最近 {days} 天内，最近 {lines} 行）",
            journal_out,
            "未匹配到 err..alert 级别日志。",
        )
    elif journal_status != 0 and journal_err.strip():
        _append_log_section(
            filename,
            "systemd journal 错误日志",
            journal_err,
            "journalctl 查询失败。",
        )
    else:
        _append_log_section(
            filename,
            f"systemd journal 错误日志（最近 {days} 天内，最近 {lines} 行）",
            "",
            "未匹配到 err..alert 级别日志。",
        )

    fallback_logs = [
        "/var/log/messages",
        "/var/log/secure",
        "/var/log/nginx/error.log",
        "/var/log/mysql/error.log",
        "/var/log/mysqld.log",
        "/var/log/rabbitmq/rabbitmqd-error.log",
    ]

    for log_path in fallback_logs:
        safe_path = log_path.replace("'", "'\"'\"'")
        file_out, file_err, file_status = _collect_file_errors(client, f"'{safe_path}'", lines)
        title = f"文件日志扫描：{log_path}（关键字匹配最近 {lines} 行）"
        if file_status == 0 and file_out.strip():
            _append_log_section(filename, title, file_out, "未匹配到关键字日志。")
        elif file_err.strip():
            _append_log_section(filename, title, file_err, "日志文件扫描失败。")
        elif file_status == 0:
            _append_log_section(filename, title, "", "文件存在，但未匹配到关键字日志。")

    with open(filename, "a", encoding="utf-8") as f:
        f.write("---\n\n")

    return None