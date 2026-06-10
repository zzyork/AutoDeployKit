from utils.output import print_error
from utils.ssh_utils import run_command


def server_info(client, filename):
    hostname, err, _ = run_command(client, "hostname")
    ipaddress, err, _ = run_command(
        client,
        "ip -o -4 addr | awk '!/docker|veth|br-|cni|flannel|kube/ && $2!=\"lo\" {print $4}' | uniq",
    )
    os_name, err, _ = run_command(
        client,
        "cat /etc/*release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'",
    )
    kernel_version, err, _ = run_command(client, "uname -r")
    uptime, err, _ = run_command(client, "uptime -p")

    if err:
        print_error("获取信息出错：" + err)
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