from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

from utils.ssh_utils import run_command


SAFE = "SAFE"
CONFIRM = "CONFIRM"


def _quote(value: str) -> str:
    return shlex.quote(value)


def _safe_service_name(service: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9_.@-]+", service or ""):
        raise ValueError(f"非法服务名: {service}")
    return service


@dataclass
class Evidence:
    key: str
    title: str
    command: str
    output: str
    error: str
    exit_status: int
    summary: str = ""
    parsed: dict = field(default_factory=dict)
    level: str = SAFE


@dataclass
class RepairProposal:
    title: str
    risk: str
    command: str
    reason: str
    verify_command: str


def run_evidence(client, key: str, title: str, command: str, *, summary: str = "", parsed: dict | None = None) -> Evidence:
    output, error, exit_status = run_command(client, command)
    return Evidence(
        key=key,
        title=title,
        command=command,
        output=output.strip(),
        error=error.strip(),
        exit_status=exit_status,
        summary=summary,
        parsed=parsed or {},
    )


def collect_host_overview(client) -> list[Evidence]:
    return [
        run_evidence(client, "hostname", "主机名", "hostname"),
        run_evidence(client, "os", "操作系统", "cat /etc/*release | grep PRETTY_NAME | head -n1 | cut -d= -f2 | tr -d '\"'"),
        run_evidence(client, "uptime", "运行时长", "uptime -p"),
    ]


def collect_service_status(client, service: str) -> Evidence:
    service = _safe_service_name(service)
    command = (
        f"echo '__ACTIVE__'; systemctl is-active {service} 2>&1; "
        f"echo '__ENABLED__'; systemctl is-enabled {service} 2>&1; "
        f"echo '__STATUS__'; systemctl status {service} --no-pager -n 20 2>&1"
    )
    output, error, exit_status = run_command(client, command)
    active = "unknown"
    enabled = "unknown"
    if "__ACTIVE__" in output and "__ENABLED__" in output:
        active_part = output.split("__ACTIVE__", 1)[1].split("__ENABLED__", 1)[0].strip().splitlines()
        enabled_part = output.split("__ENABLED__", 1)[1].split("__STATUS__", 1)[0].strip().splitlines()
        if active_part:
            active = active_part[0].strip()
        if enabled_part:
            enabled = enabled_part[0].strip()
    return Evidence(
        key=f"service:{service}",
        title=f"服务状态: {service}",
        command=command,
        output=output.strip(),
        error=error.strip(),
        exit_status=exit_status,
        summary=f"active={active}, enabled={enabled}",
        parsed={"service": service, "active": active, "enabled": enabled},
    )


def collect_service_logs(client, service: str, lines: int = 80) -> Evidence:
    service = _safe_service_name(service)
    command = f"journalctl -u {service} -n {int(lines)} --no-pager 2>&1"
    return run_evidence(client, f"logs:{service}", f"服务日志: {service}", command)


def collect_file_tail(client, path: str, lines: int = 80) -> Evidence:
    command = f"tail -n {int(lines)} {_quote(path)} 2>&1"
    return run_evidence(client, f"file:{path}", f"文件尾部: {path}", command)


def collect_disk_usage(client) -> Evidence:
    command = "df -hT"
    output, error, exit_status = run_command(client, command)
    max_usage = 0
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 6 and parts[5].endswith("%"):
            try:
                max_usage = max(max_usage, int(parts[5].rstrip("%")))
            except ValueError:
                pass
    return Evidence(
        key="disk",
        title="磁盘使用率",
        command=command,
        output=output.strip(),
        error=error.strip(),
        exit_status=exit_status,
        summary=f"最高使用率 {max_usage}%",
        parsed={"max_usage": max_usage},
    )


def collect_memory_usage(client) -> Evidence:
    command = "free -m"
    output, error, exit_status = run_command(client, command)
    used_percent = None
    for line in output.splitlines():
        parts = line.split()
        if parts and parts[0] == "Mem:" and len(parts) >= 3:
            try:
                total = float(parts[1])
                used = float(parts[2])
                if total > 0:
                    used_percent = round(used / total * 100, 1)
            except ValueError:
                pass
            break
    summary = f"内存使用率 {used_percent}%" if used_percent is not None else "内存使用率未知"
    return Evidence(
        key="memory",
        title="内存使用情况",
        command=command,
        output=output.strip(),
        error=error.strip(),
        exit_status=exit_status,
        summary=summary,
        parsed={"used_percent": used_percent},
    )


def collect_load_average(client) -> Evidence:
    command = "cat /proc/loadavg && echo '---' && uptime"
    return run_evidence(client, "load", "系统负载", command)


def collect_listening_ports(client) -> Evidence:
    command = "ss -lntp 2>/dev/null || netstat -tlnp 2>/dev/null"
    return run_evidence(client, "ports", "监听端口", command)


def collect_processes(client, keyword: str) -> Evidence:
    command = f"ps -ef | grep -i {_quote(keyword)} | grep -v grep"
    return run_evidence(client, f"process:{keyword}", f"进程检查: {keyword}", command)


def collect_recent_errors(client, lines: int = 50) -> Evidence:
    command = f"journalctl -p err..alert -n {int(lines)} --no-pager 2>&1"
    return run_evidence(client, "recent_errors", "近期错误日志", command)


def execute_repair(client, proposal: RepairProposal) -> tuple[Evidence, Evidence]:
    apply_result = run_evidence(
        client,
        "repair_apply",
        f"执行修复: {proposal.title}",
        proposal.command,
        summary=proposal.reason,
        parsed={"risk": proposal.risk},
    )
    verify_result = run_evidence(
        client,
        "repair_verify",
        f"验证修复: {proposal.title}",
        proposal.verify_command,
    )
    return apply_result, verify_result
