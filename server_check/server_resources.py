import re

from server_check.common import DEFAULT_CONFIG
from utils.output import print_error
from utils.ssh_utils import run_command


def system_resources(client, filename, config=None, alerts=None):
    config = config or DEFAULT_CONFIG
    alerts = alerts if alerts is not None else []
    thresholds = config.get("thresholds", {})
    errors = []

    system_load, err, status = run_command(client, "cat /proc/loadavg | awk '{print $1,$2,$3}'")
    if status != 0:
        errors.append("系统负载：" + (err.strip() or system_load.strip() or f"退出码 {status}"))

    cpu_usage, err, status = run_command(client, "vmstat 1 2 | tail -1 | awk '{print 100-$15\"%\"}'")
    if status != 0:
        errors.append("CPU 使用率：" + (err.strip() or cpu_usage.strip() or f"退出码 {status}"))

    mem_usage, err, status = run_command(client, "free -m | awk '/Mem:/ {printf \"%.1f%%\\n\", $3/$2*100}'")
    if status != 0:
        errors.append("内存使用率：" + (err.strip() or mem_usage.strip() or f"退出码 {status}"))

    swap_usage, err, status = run_command(client, "free -m | awk '/Swap:/ {if ($2==0) print \"0.0%\"; else printf \"%.1f%%\\n\", $3/$2*100}'")
    if status != 0:
        errors.append("Swap 使用率：" + (err.strip() or swap_usage.strip() or f"退出码 {status}"))

    disks_usage, err, status = run_command(
        client,
        "df -hT | grep -E \"ext4|xfs|挂载点|Mounted\" | awk '{print $7,$3,$4,$5,$6}'",
    )
    if status != 0:
        errors.append("磁盘使用率：" + (err.strip() or disks_usage.strip() or f"退出码 {status}"))

    top_cpu_procs, err, status = run_command(
        client,
        "ps aux --sort=-%cpu | head -11 | awk '{cmd=\"\"; for(i=11;i<=NF;i++) cmd=cmd\" \"$i; printf \"%-10s %-6s %-6s %s\\n\", $1, $3, $4, cmd}'",
    )
    if status != 0:
        errors.append("CPU 使用率TOP10：" + (err.strip() or top_cpu_procs.strip() or f"退出码 {status}"))

    top_mem_procs, err, status = run_command(
        client,
        "ps aux --sort=-%mem | head -11 | awk '{cmd=\"\"; for(i=11;i<=NF;i++) cmd=cmd\" \"$i; printf \"%-10s %-6s %-6s %s\\n\", $1, $3, $4, cmd}'",
    )
    if status != 0:
        errors.append("内存使用率TOP10：" + (err.strip() or top_mem_procs.strip() or f"退出码 {status}"))

    if errors:
        print_error("获取系统资源信息出错：" + "; ".join(errors))
        return None

    cpu_percent = float(re.search(r"(\d+(?:\.\d+)?)%", cpu_usage).group(1)) if re.search(r"(\d+(?:\.\d+)?)%", cpu_usage) else None
    mem_percent = float(re.search(r"(\d+(?:\.\d+)?)%", mem_usage).group(1)) if re.search(r"(\d+(?:\.\d+)?)%", mem_usage) else None
    swap_percent = float(re.search(r"(\d+(?:\.\d+)?)%", swap_usage).group(1)) if re.search(r"(\d+(?:\.\d+)?)%", swap_usage) else None

    cpu_mark = ""
    if cpu_percent is not None:
        if cpu_percent >= thresholds.get("cpu_critical", 95):
            cpu_mark = " 🔴 CRITICAL"
            alerts.append(f"🔴 **CPU 使用率：** {cpu_usage.strip()}")
        elif cpu_percent >= thresholds.get("cpu_warning", 80):
            cpu_mark = " ⚠️ WARNING"
            alerts.append(f"⚠️ **CPU 使用率：** {cpu_usage.strip()}")
        else:
            cpu_mark = " ✅ OK"

    mem_mark = ""
    if mem_percent is not None:
        if mem_percent >= thresholds.get("mem_critical", 95):
            mem_mark = " 🔴 CRITICAL"
            alerts.append(f"🔴 **内存使用率：** {mem_usage.strip()}")
        elif mem_percent >= thresholds.get("mem_warning", 80):
            mem_mark = " ⚠️ WARNING"
            alerts.append(f"⚠️ **内存使用率：** {mem_usage.strip()}")
        else:
            mem_mark = " ✅ OK"

    swap_mark = ""
    if swap_percent is not None:
        if swap_percent >= thresholds.get("swap_critical", 80):
            swap_mark = " 🔴 CRITICAL"
            alerts.append(f"🔴 **Swap 使用率：** {swap_usage.strip()}")
        elif swap_percent >= thresholds.get("swap_warning", 50):
            swap_mark = " ⚠️ WARNING"
            alerts.append(f"⚠️ **Swap 使用率：** {swap_usage.strip()}")
        else:
            swap_mark = " ✅ OK"

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 二、系统资源与性能\n\n")
        f.write(f"- **系统负载：** `{system_load.strip()}`\n")
        f.write(f"- **CPU 使用率：** `{cpu_usage.strip()}`{cpu_mark}\n")
        f.write(f"- **内存使用率：** `{mem_usage.strip()}`{mem_mark}\n")
        f.write(f"- **Swap 使用率：** `{swap_usage.strip()}`{swap_mark}\n\n")
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
                if len(row) >= 5:
                    disk_match = re.search(r"(\d+(?:\.\d+)?)%", row[4])
                    disk_percent = float(disk_match.group(1)) if disk_match else None
                    disk_mark = ""
                    if disk_percent is not None:
                        if disk_percent >= thresholds.get("disk_critical", 90):
                            disk_mark = " 🔴 CRITICAL"
                            alerts.append(f"🔴 **磁盘 {row[0]} 使用率：** {row[4]}")
                        elif disk_percent >= thresholds.get("disk_warning", 80):
                            disk_mark = " ⚠️ WARNING"
                            alerts.append(f"⚠️ **磁盘 {row[0]} 使用率：** {row[4]}")
                        else:
                            disk_mark = " ✅ OK"
                    row[-1] = row[-1] + disk_mark
                f.write("| " + " | ".join(row) + " |\n")
            f.write("\n")

        f.write("---\n\n")
    return None
