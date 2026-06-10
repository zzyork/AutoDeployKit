from utils.ssh_utils import run_command


def service_status(client, filename):
    services = [
        ("sshd", ["sshd"]),
        ("crond", ["crond"]),
        ("chronyd", ["chronyd"]),
        ("firewalld", ["firewalld"]),
        ("NetworkManager", ["NetworkManager"]),
        ("nginx", ["nginx"]),
        ("mysqld", ["mysqld"]),
        ("redis", ["redis"]),
        ("rabbitmq", ["rabbitmqd", "rabbitmq-server", "rabbitmq"]),
        ("docker", ["docker", "dockerd"]),
        ("minio", ["minio"]),
        ("supervisord", ["supervisord"]),
        ("prometheus", ["prometheus"]),
        ("node-exporter", ["node-exporter"]),
        ("mysqld-exporter", ["mysqld-exporter"]),
        ("keepalived", ["keepalived"]),
        ("DmServiceDMSERVER", ["DmServiceDMSERVER"]),
    ]

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 四、服务与进程状态\n\n")

        for service_name, candidates in services:
            loaded_service = None
            for candidate in candidates:
                info, _, _ = run_command(client, f"systemctl show -p LoadState --value {candidate}")
                if info.strip() == "loaded":
                    loaded_service = candidate
                    break

            if loaded_service:
                info, _, _ = run_command(client, f"systemctl is-active {loaded_service}")
                status = info.strip()
                if status == "active":
                    f.write(f"- **{service_name}：** ✅ 运行中\n")
                elif status == "inactive":
                    f.write(f"- **{service_name}：** ❌ 未运行\n")
                else:
                    f.write(f"- **{service_name}：** ⚠️ {status}\n")

        f.write("\n---\n\n")
    return None