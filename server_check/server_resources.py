from utils.output import print_error
from utils.ssh_utils import run_command


def system_resources(client, filename):
    errors = []
    system_load, err, _ = run_command(client, "cat /proc/loadavg | awk '{print $1,$2,$3}'")
    if err:
        errors.append("系统负载：" + err)
    
    cpu_usage, err, _ = run_command(client, "vmstat 1 2 | tail -1 | awk '{print 100-$15\"%\"}'")
    if err:
        errors.append("CPU 使用率：" + err)
    
    mem_usage, err, _ = run_command(client, "free -m | awk '/Mem:/ {printf \"%.1f%%\\n\", $3/$2*100}'")
    if err:
        errors.append("内存使用率：" + err)
    
    disks_usage, err, _ = run_command(
        client,
        "df -hT | grep -E \"ext4|xfs|挂载点|Mounted\" | awk '{print $7,$3,$4,$5,$6}'",
    )
    if err:
        errors.append("磁盘使用率：" + err)
    
    # CPU 使用率 TOP10 进程
    top_cpu_procs, err, _ = run_command(
        client,
        "ps aux --sort=-%cpu | head -11 | awk '{cmd=\"\"; for(i=11;i<=NF;i++) cmd=cmd\" \"$i; printf \"%-10s %-6s %-6s %s\\n\", $1, $3, $4, cmd}'"
    )
    if err:
        errors.append("CPU 使用率TOP10：" + err)

    # 内存使用率 TOP10 进程
    top_mem_procs, err, _ = run_command(
        client,
        "ps aux --sort=-%mem | head -11 | awk '{cmd=\"\"; for(i=11;i<=NF;i++) cmd=cmd\" \"$i; printf \"%-10s %-6s %-6s %s\\n\", $1, $3, $4, cmd}'"
    )
    if err:
        errors.append("内存使用率TOP10：" + err)

    if errors:
        print_error("获取信息出错：" + "; ".join(errors))
        return None

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 二、系统资源与性能\n\n")
        f.write(f"- **系统负载：** `{system_load.strip()}`\n")
        f.write(f"- **CPU 使用率：** `{cpu_usage.strip()}`\n")
        f.write(f"- **内存使用率：** `{mem_usage.strip()}`\n\n")
        f.write("### CPU 使用率 TOP10 进程\n\n```text\n")
        f.write(f"{top_cpu_procs.strip()}\n" if top_cpu_procs.strip() else "无\n")
        f.write("```\n\n")

        f.write("### 内存使用率 TOP10 进程\n\n```text\n")
        f.write(f"{top_mem_procs.strip()}\n" if top_mem_procs.strip() else "无\n")
        f.write("```\n\n")

        rows = [line.split() for line in disks_usage.strip().splitlines() if line.strip()]
        if rows:
            header, *body = rows
            f.write("### 磁盘使用率\n\n")
            f.write("| " + " | ".join(header) + " |\n")
            f.write("| " + " | ".join(["---"] * len(header)) + " |\n")
            for row in body:
                f.write("| " + " | ".join(row) + " |\n")
            f.write("\n")

        f.write("---\n\n")
    return None