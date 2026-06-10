import json
import os

from utils.output import print_warning


DEFAULT_CONFIG = {
    "checks": [
        "server_info",
        "system_resources",
        "security_info",
        "service_status",
        "network_info",
        "docker_status",
        "supervisor_status",
        "log_error",
        "monitors",
    ],
    "thresholds": {
        "cpu_warning": 80,
        "cpu_critical": 95,
        "mem_warning": 80,
        "mem_critical": 95,
        "disk_warning": 80,
        "disk_critical": 90,
        "swap_warning": 50,
        "swap_critical": 80,
    },
    "logs": {
        "days": 30,
        "lines": 200,
        "paths": [
            "/var/log/messages",
            "/var/log/secure",
            "/var/log/nginx/error.log",
            "/var/log/mysql/error.log",
            "/var/log/mysqld.log",
            "/var/log/rabbitmq/rabbitmqd-error.log",
        ],
    },
    "services": [
        {"name": "sshd", "candidates": ["sshd"]},
        {"name": "crond", "candidates": ["crond"]},
        {"name": "chronyd", "candidates": ["chronyd"]},
        {"name": "firewalld", "candidates": ["firewalld"]},
        {"name": "NetworkManager", "candidates": ["NetworkManager"]},
        {"name": "nginx", "candidates": ["nginx"]},
        {"name": "mysqld", "candidates": ["mysqld"]},
        {"name": "redis", "candidates": ["redis"]},
        {"name": "rabbitmq", "candidates": ["rabbitmqd", "rabbitmq-server", "rabbitmq"]},
        {"name": "docker", "candidates": ["docker", "dockerd"]},
        {"name": "minio", "candidates": ["minio"]},
        {"name": "supervisord", "candidates": ["supervisord"]},
        {"name": "prometheus", "candidates": ["prometheus"]},
        {"name": "node-exporter", "candidates": ["node-exporter"]},
        {"name": "mysqld-exporter", "candidates": ["mysqld-exporter"]},
        {"name": "keepalived", "candidates": ["keepalived"]},
        {"name": "DmServiceDMSERVER", "candidates": ["DmServiceDMSERVER"]},
    ],
}


def _merge_config(default, override):
    merged = default.copy()
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config():
    config_path = os.getenv("SERVER_CHECK_CONFIG", os.path.join("server_check", "config.json"))
    if not os.path.exists(config_path):
        print_warning(f"未找到巡检配置文件，将使用内置默认配置：{config_path}")
        return DEFAULT_CONFIG

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return _merge_config(DEFAULT_CONFIG, json.load(f))
    except Exception as exc:
        print_warning(f"读取巡检配置失败，将使用内置默认配置：{exc}")
        return DEFAULT_CONFIG

