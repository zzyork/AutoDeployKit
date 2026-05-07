from __future__ import annotations

from dataclasses import dataclass


KNOWN_SERVICES = [
    "nginx",
    "mysql",
    "mysqld",
    "redis",
    "docker",
    "dockerd",
    "minio",
    "prometheus",
    "node-exporter",
    "node_exporter",
    "mysqld-exporter",
    "mysqld_exporter",
    "supervisor",
    "supervisord",
    "sshd",
    "ssh",
    "rabbitmq",
]


@dataclass
class DiagnosisIntent:
    issue_type: str
    summary: str
    service: str | None = None


def _normalize_service(service: str | None) -> str | None:
    if not service:
        return None
    mapping = {
        "mysql": "mysqld",
        "docker": "dockerd",
        "supervisor": "supervisord",
        "ssh": "sshd",
        "node_exporter": "node-exporter",
        "mysqld_exporter": "mysqld-exporter",
    }
    return mapping.get(service.lower(), service.lower())


def detect_service(question: str) -> str | None:
    text = question.lower()
    for service in KNOWN_SERVICES:
        if service in text:
            return _normalize_service(service)
    return None


def build_intent(question: str) -> DiagnosisIntent:
    text = question.lower()
    service = detect_service(question)

    if "502" in text or "bad gateway" in text:
        return DiagnosisIntent("nginx_502", "排查 Nginx 502 / upstream 异常", service or "nginx")

    if any(keyword in text for keyword in ["磁盘", "空间", "disk", "no space", "满了"]):
        return DiagnosisIntent("disk_full", "排查磁盘空间不足或目录占满", service)

    if any(keyword in text for keyword in ["cpu", "负载", "load average", "卡", "很慢"]):
        return DiagnosisIntent("high_load", "排查 CPU / 负载异常", service)

    if any(keyword in text for keyword in ["登录失败", "连不上", "ssh", "拒绝连接", "connection refused"]):
        return DiagnosisIntent("ssh_issue", "排查 SSH 登录或连接异常", service or "sshd")

    if service:
        return DiagnosisIntent("service_issue", f"排查服务 {service} 的状态、日志与依赖", service)

    return DiagnosisIntent("generic", "执行通用健康检查并收集近期错误日志", None)
