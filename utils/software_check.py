import math
import re
import shlex
import time

from paramiko import SSHException

from utils.ssh_utils import run_command


def _probe(client, command):
    try:
        stdout, stderr, exit_code = run_command(client, command)
    except (OSError, SSHException) as exc:
        stdout, stderr, exit_code = "", str(exc), -1
    return {
        "command": command,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "success": False,
    }


def _has_live_process(check):
    if check["exit_code"] != 0:
        return False
    for line in check["stdout"].splitlines():
        fields = line.split(None, 2)
        if len(fields) >= 2 and fields[0].isdigit() and fields[1][0] not in "ZTtXx":
            return True
    return False


def check_software_started(
    client,
    *,
    service_name=None,
    process_name=None,
    log_path=None,
    success_pattern=None,
    error_pattern=r"\b(error|failed|fatal|panic|exception|critical)\b|address already in use",
    retries=3,
    interval=2,
    log_lines=100,
):
    """Check a Linux daemon through an existing SSH client using read-only commands.

    At least one of service_name/process_name is required. All requested runtime
    checks must pass; systemd also requires a live MainPID. process_name is the
    exact executable name accepted by ps -C, not a command-line substring.
    Logs are diagnostic unless success_pattern (case-insensitive regex) is set.
    Journal queries use the current invocation when available, otherwise the
    last five minutes. File logs use only their last log_lines lines, which may
    include older runs. Error matches are warnings, not proof of startup failure.
    retries is the total attempt count; interval is the delay between attempts,
    not an SSH command timeout. The returned dict includes success, attempts,
    checks (command/stdout/stderr/exit_code/success), and warnings.
    This checks liveness, not application-specific readiness or installation.
    """
    if not service_name and not process_name:
        raise ValueError("至少指定 service_name 或 process_name")
    if service_name is not None and (
        not isinstance(service_name, str)
        or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@:\-]*", service_name)
    ):
        raise ValueError("service_name 必须是有效的 systemd 服务名称")
    if service_name and not service_name.endswith(".service"):
        service_name += ".service"
    if process_name is not None and (
        not isinstance(process_name, str)
        or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+\-]*", process_name)
    ):
        raise ValueError("process_name 必须是单个可执行文件名称")
    if log_path is not None and (
        not isinstance(log_path, str)
        or not log_path.startswith("/")
        or any(char in log_path for char in "\0\r\n")
    ):
        raise ValueError("log_path 必须是 Linux 绝对文件路径")
    for name, value in (("retries", retries), ("log_lines", log_lines)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} 必须是正整数")
    if (
        isinstance(interval, bool)
        or not isinstance(interval, (int, float))
        or not math.isfinite(interval)
        or interval < 0
    ):
        raise ValueError("interval 必须是有限的非负数")
    if success_pattern is not None and (
        not isinstance(success_pattern, str)
        or not success_pattern
        or not (service_name or log_path)
    ):
        raise ValueError("success_pattern 需要非空正则及 service_name 或 log_path 日志来源")
    if error_pattern is not None and (not isinstance(error_pattern, str) or not error_pattern):
        raise ValueError("error_pattern 必须是非空正则或 None")
    ready_regex = re.compile(success_pattern, re.IGNORECASE) if success_pattern else None
    error_regex = re.compile(error_pattern, re.IGNORECASE) if error_pattern else None

    for attempt in range(1, retries + 1):
        checks = {}
        warnings = []
        properties = {}
        if service_name:
            command = (
                "systemctl show --no-pager "
                "--property=LoadState,ActiveState,SubState,MainPID,Result,InvocationID "
                f"-- {shlex.quote(service_name)}"
            )
            service = checks["systemd"] = _probe(client, command)
            properties = dict(
                line.split("=", 1) for line in service["stdout"].splitlines() if "=" in line
            )
            service["success"] = (
                service["exit_code"] == 0
                and properties.get("LoadState") == "loaded"
                and properties.get("ActiveState") == "active"
                and properties.get("SubState") == "running"
            )
            main_pid = properties.get("MainPID", "")
            if main_pid.isascii() and main_pid.isdigit() and int(main_pid) > 0:
                process = _probe(client, f"ps -p {int(main_pid)} -o pid=,stat=,args=")
                process["success"] = _has_live_process(process)
            else:
                process = {
                    "command": None,
                    "stdout": "",
                    "stderr": "systemd 未提供有效的 MainPID",
                    "exit_code": None,
                    "success": False,
                }
            checks["service_process"] = process
        if process_name:
            process = _probe(client, f"ps -C {shlex.quote(process_name)} -o pid=,stat=,args=")
            process["success"] = _has_live_process(process)
            checks["process"] = process

        runtime_ok = all(check["success"] for check in checks.values())
        if log_path or service_name:
            if log_path:
                path = shlex.quote(log_path)
                command = f"test -f {path} && tail -n {log_lines} -- {path}"
            else:
                invocation = properties.get("InvocationID", "")
                if re.fullmatch(r"[0-9a-fA-F]{32}", invocation):
                    source = f"_SYSTEMD_INVOCATION_ID={invocation}"
                else:
                    source = f"--unit={shlex.quote(service_name)} --since='5 minutes ago'"
                command = f"journalctl --no-pager --output=cat --lines={log_lines} {source}"
            logs = checks["logs"] = _probe(client, command)
            logs["success"] = (
                logs["exit_code"] == 0 and bool(ready_regex.search(logs["stdout"]))
                if ready_regex
                else None
            )
            logs["error_matches"] = (
                [line for line in logs["stdout"].splitlines() if error_regex.search(line)]
                if error_regex and logs["exit_code"] == 0
                else []
            )
            if logs["exit_code"] != 0:
                warnings.append("日志读取失败，请检查 logs.stderr 和 logs.exit_code")
            if logs["error_matches"]:
                warnings.append("日志中发现错误关键字，请检查 logs.error_matches")

        success = runtime_ok and (ready_regex is None or checks["logs"]["success"])
        result = {
            "success": bool(success),
            "attempts": attempt,
            "checks": checks,
            "warnings": warnings,
        }
        if success:
            break
        if attempt < retries:
            time.sleep(interval)
    return result
