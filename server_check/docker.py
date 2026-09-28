from utils.ssh_utils import run_command


def docker_status(client, filename, config=None, alerts=None):
    alerts = alerts if alerts is not None else []
    _, _, status = run_command(client, "command -v docker >/dev/null 2>&1")
    if status != 0:
        with open(filename, "a", encoding="utf-8") as f:
            f.write("## 六、Docker 容器状态\n\n")
            f.write("未安装 docker，跳过容器巡检。\n\n---\n\n")
        return None

    web_mode = getattr(client, "_web_mode", False) is True
    if not web_mode:
        context, context_err, context_status = run_command(client, "docker context show 2>&1")
        context = context.strip()
        if context_status != 0:
            alerts.append("⚠️ **Docker Context：** 查询失败，跳过容器巡检")
            with open(filename, "a", encoding="utf-8") as f:
                f.write("## 六、Docker 容器状态\n\n")
                f.write("Docker context 查询失败，跳过容器巡检。\n\n")
                f.write("```text\n")
                f.write((context_err or context).strip() + "\n")
                f.write("```\n\n---\n\n")
            return None
        if context != "default":
            switch_result, switch_err, switch_status = run_command(client, "docker context use default 2>&1")
            if switch_status != 0:
                alerts.append(f"⚠️ **Docker Context：** 当前为 {context}，切换 default 失败，本机容器巡检已跳过")
                with open(filename, "a", encoding="utf-8") as f:
                    f.write("## 六、Docker 容器状态\n\n")
                    f.write(f"当前 Docker context 为 `{context}`，切换到 `default`（本机）失败，跳过容器巡检。\n\n")
                    f.write("```text\n")
                    f.write((switch_err or switch_result).strip() + "\n")
                    f.write("```\n\n---\n\n")
                return None
            alerts.append(f"ℹ️ **Docker Context：** 已从 {context} 切换到 default 后继续巡检")

    docker_cmd = "docker --context default" if web_mode else "docker"
    containers, err, status = run_command(client, f"{docker_cmd} ps -a --format 'table {{{{.Names}}}}\\t{{{{.Status}}}}\\t{{{{.Ports}}}}' 2>&1")
    stats, stats_err, stats_status = run_command(client, f"{docker_cmd} stats --no-stream --format 'table {{{{.Name}}}}\\t{{{{.CPUPerc}}}}\\t{{{{.MemUsage}}}}\\t{{{{.MemPerc}}}}' 2>&1")

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
