from utils.ssh_utils import run_command


def docker_status(client, filename, config=None, alerts=None):
    alerts = alerts if alerts is not None else []
    _, _, status = run_command(client, "command -v docker >/dev/null 2>&1")
    if status != 0:
        with open(filename, "a", encoding="utf-8") as f:
            f.write("## 六、Docker 容器状态\n\n")
            f.write("未安装 docker，跳过容器巡检。\n\n---\n\n")
        return None

    containers, err, status = run_command(client, "docker ps -a --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' 2>&1")
    stats, stats_err, stats_status = run_command(client, "docker stats --no-stream --format 'table {{.Name}}\\t{{.CPUPerc}}\\t{{.MemUsage}}\\t{{.MemPerc}}' 2>&1")

    if status != 0:
        containers = err or containers
        alerts.append("⚠️ **Docker 容器状态：** docker ps 查询失败")
    else:
        for line in containers.splitlines()[1:]:
            lower_line = line.lower()
            if any(keyword in lower_line for keyword in ("exited", "unhealthy", "dead", "restarting")):
                alerts.append(f"⚠️ **Docker 异常容器：** {line.strip()}")

    if stats_status != 0:
        stats = stats_err or stats

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 六、Docker 容器状态\n\n")
        f.write("### 容器列表\n\n```text\n")
        f.write(containers.strip() + "\n" if containers.strip() else "未发现容器。\n")
        f.write("```\n\n")
        f.write("### 容器资源占用\n\n```text\n")
        f.write(stats.strip() + "\n" if stats.strip() else "未获取到容器资源占用。\n")
        f.write("```\n\n")
        f.write("---\n\n")
    return None
