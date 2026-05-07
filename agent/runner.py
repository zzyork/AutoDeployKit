from __future__ import annotations

from dataclasses import dataclass, field

from utils.output import print_error, print_header, print_info, print_step, print_success, print_warning

from .planner import DiagnosisIntent, build_intent
from .tools import (
    CONFIRM,
    Evidence,
    RepairProposal,
    collect_disk_usage,
    collect_file_tail,
    collect_host_overview,
    collect_listening_ports,
    collect_load_average,
    collect_memory_usage,
    collect_processes,
    collect_recent_errors,
    collect_service_logs,
    collect_service_status,
    execute_repair,
)


@dataclass
class HostDiagnosis:
    host: str
    intent: DiagnosisIntent
    evidences: list[Evidence] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    repair: RepairProposal | None = None


def _append_if_present(items: list[Evidence], evidence: Evidence | None):
    if evidence is not None:
        items.append(evidence)


def collect_diagnosis(client, host: str, question: str) -> HostDiagnosis:
    intent = build_intent(question)
    diagnosis = HostDiagnosis(host=host, intent=intent)

    for evidence in collect_host_overview(client):
        diagnosis.evidences.append(evidence)

    if intent.issue_type in {"service_issue", "nginx_502", "ssh_issue"} and intent.service:
        _append_if_present(diagnosis.evidences, collect_service_status(client, intent.service))
        _append_if_present(diagnosis.evidences, collect_service_logs(client, intent.service))

    if intent.issue_type == "nginx_502":
        _append_if_present(diagnosis.evidences, collect_file_tail(client, "/var/log/nginx/error.log"))
        _append_if_present(diagnosis.evidences, collect_listening_ports(client))
        _append_if_present(diagnosis.evidences, collect_disk_usage(client))
        _append_if_present(diagnosis.evidences, collect_memory_usage(client))
    elif intent.issue_type == "disk_full":
        _append_if_present(diagnosis.evidences, collect_disk_usage(client))
        _append_if_present(diagnosis.evidences, collect_recent_errors(client))
    elif intent.issue_type == "high_load":
        _append_if_present(diagnosis.evidences, collect_load_average(client))
        _append_if_present(diagnosis.evidences, collect_memory_usage(client))
        _append_if_present(diagnosis.evidences, collect_processes(client, "java"))
        _append_if_present(diagnosis.evidences, collect_processes(client, "python"))
    else:
        _append_if_present(diagnosis.evidences, collect_disk_usage(client))
        _append_if_present(diagnosis.evidences, collect_memory_usage(client))
        _append_if_present(diagnosis.evidences, collect_recent_errors(client))

    analyze_diagnosis(diagnosis)
    return diagnosis


def analyze_diagnosis(diagnosis: HostDiagnosis) -> None:
    service_evidence = next(
        (item for item in diagnosis.evidences if item.key.startswith("service:")),
        None,
    )
    disk_evidence = next((item for item in diagnosis.evidences if item.key == "disk"), None)
    memory_evidence = next((item for item in diagnosis.evidences if item.key == "memory"), None)
    recent_errors = next((item for item in diagnosis.evidences if item.key == "recent_errors"), None)

    if service_evidence:
        active = service_evidence.parsed.get("active")
        service = service_evidence.parsed.get("service")
        if active and active not in {"active", "unknown"}:
            diagnosis.findings.append(f"服务 {service} 当前状态异常：{active}。")
            diagnosis.suggestions.append(f"优先检查 {service} 配置、依赖端口和最近日志。")
            diagnosis.repair = RepairProposal(
                title=f"重启服务 {service}",
                risk=CONFIRM,
                command=f"systemctl restart {service}",
                reason=f"检测到 {service} 未处于 active 状态，可尝试受控重启恢复。",
                verify_command=f"systemctl is-active {service} && systemctl status {service} --no-pager -n 10",
            )
        elif active == "active":
            diagnosis.findings.append(f"服务 {service} 当前处于 active 状态。")

    if disk_evidence:
        max_usage = disk_evidence.parsed.get("max_usage")
        if isinstance(max_usage, int) and max_usage >= 95:
            diagnosis.findings.append(f"磁盘最高使用率达到 {max_usage}%，可能已影响服务写日志或写数据。")
            diagnosis.suggestions.append("建议优先清理大文件、日志和临时目录，再观察服务恢复情况。")
            diagnosis.repair = None

    if memory_evidence:
        used_percent = memory_evidence.parsed.get("used_percent")
        if isinstance(used_percent, (int, float)) and used_percent >= 90:
            diagnosis.findings.append(f"内存使用率约 {used_percent}%，存在内存压力。")
            diagnosis.suggestions.append("建议结合占用高的进程与 OOM 日志进一步分析。")

    if recent_errors and recent_errors.output:
        diagnosis.suggestions.append("已抓取近期系统错误日志，可结合业务报错时间进一步定位。")

    if diagnosis.intent.issue_type == "nginx_502":
        diagnosis.suggestions.append("重点关注 upstream 服务是否监听、是否超时，以及 Nginx error.log 中的 connect()/upstream 关键字。")

    if not diagnosis.findings:
        diagnosis.findings.append("未发现单一确定性根因，已收集基础状态与日志，建议继续结合具体报错时间点分析。")


def render_diagnosis(diagnosis: HostDiagnosis) -> None:
    print_header(f"Agent 诊断结果 - {diagnosis.host}")
    print_info(f"诊断意图：{diagnosis.intent.summary}")
    print_info(f"问题描述：{diagnosis.intent.issue_type}")

    print_step("关键结论")
    for item in diagnosis.findings:
        print_info(item)

    print_step("关键证据")
    for evidence in diagnosis.evidences:
        preview = evidence.summary or evidence.output.splitlines()[0] if evidence.output else evidence.error or "无输出"
        print_info(f"[{evidence.title}] {preview}")

    print_step("建议动作")
    for item in diagnosis.suggestions:
        print_warning(item)

    if diagnosis.repair:
        print_step("可执行修复")
        print_warning(f"方案：{diagnosis.repair.title}")
        print_warning(f"风险级别：{diagnosis.repair.risk}")
        print_warning(f"执行命令：{diagnosis.repair.command}")
        print_warning(f"原因说明：{diagnosis.repair.reason}")


def maybe_execute_repair(client, diagnosis: HostDiagnosis) -> None:
    if not diagnosis.repair:
        return

    answer = input(f"\n是否对 [{diagnosis.host}] 执行修复“{diagnosis.repair.title}”？(y/N): ").strip().lower()
    if answer not in {"y", "yes"}:
        print_info("已跳过修复。")
        return

    print_step("执行修复")
    apply_result, verify_result = execute_repair(client, diagnosis.repair)
    if apply_result.exit_status == 0:
        print_success("修复命令执行完成。")
    else:
        print_error(f"修复命令执行失败：{apply_result.error or apply_result.output}")

    if verify_result.exit_status == 0 and "active" in verify_result.output:
        print_success("修复验证通过，服务已恢复 active。")
    else:
        print_warning(f"修复后验证结果：{verify_result.output or verify_result.error or '无输出'}")
