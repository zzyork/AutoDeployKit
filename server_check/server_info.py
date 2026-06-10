from utils.output import print_error
from utils.ssh_utils import run_command


def server_info(client, filename, config=None, alerts=None):
    errors = []
    hostname, err, status = run_command(client, "hostname")
    if status != 0:
        errors.append("主机名：" + (err.strip() or hostname.strip() or f"退出码 {status}"))

    ipaddress, err, status = run_command(
        client,
        "ip -o -4 addr | awk '!/docker|veth|br-|cni|flannel|kube/ && $2!=\"lo\" {print $4}' | uniq",
    )
    if status != 0:
        errors.append("IP 地址：" + (err.strip() or ipaddress.strip() or f"退出码 {status}"))

    os_name, err, status = run_command(
        client,
        "cat /etc/*release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'",
    )
    if status != 0:
        errors.append("操作系统：" + (err.strip() or os_name.strip() or f"退出码 {status}"))

    kernel_version, err, status = run_command(client, "uname -r")
    if status != 0:
        errors.append("内核版本：" + (err.strip() or kernel_version.strip() or f"退出码 {status}"))

    uptime, err, status = run_command(client, "uptime -p")
    if status != 0:
        errors.append("运行时长：" + (err.strip() or uptime.strip() or f"退出码 {status}"))

    if errors:
        print_error("获取系统基础信息出错：" + "; ".join(errors))
        return None

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 一、系统基础信息\n\n")
        f.write(f"- **主机名：** `{hostname.strip()}`\n\n")
        f.write("- **IP 地址：**\n\n")
        f.write("```text\n")
        f.write(f"{ipaddress.strip()}\n" if ipaddress.strip() else "无\n")
        f.write("```\n\n")
        f.write(f"- **操作系统：** `{os_name.strip()}`\n")
        f.write(f"- **内核版本：** `{kernel_version.strip()}`\n")
        f.write(f"- **运行时长：** `{uptime.strip()}`\n\n")
        f.write("---\n\n")
    return None
