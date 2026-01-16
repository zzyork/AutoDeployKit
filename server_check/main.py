from utils.output import print_info, print_error
from utils.ssh_utils import run_command
import datetime
import sys
import os


def server_info(client, filename):
    hostname, err, _ = run_command(client, "hostname")
    ipaddress, err, _ = run_command(
        client,
        "ip -o -4 addr | awk '!/docker|veth|br-|cni|flannel|kube/ && $2!=\"lo\" {print $4}' | uniq"
    )
    os, err, _ = run_command(
        client,
        "cat /etc/*release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'"
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

        f.write(f"- **操作系统：** `{os.strip()}`\n")
        f.write(f"- **内核版本：** `{kernel_version.strip()}`\n")
        f.write(f"- **运行时长：** `{uptime.strip()}`\n\n")
        f.write("---\n\n")
    return None

def system_resources(client, filename):
    system_load, err, _ = run_command(client, "cat /proc/loadavg | awk '{print $1,$2,$3}'")
    cpu_usage, err, _ = run_command(
        client,
        "vmstat 1 2 | tail -1 | awk '{print 100-$15\"%\"}'"
    )
    mem_usage, err, _ = run_command(
        client,
        "free -m | awk '/Mem:/ {printf \"%.1f%%\\n\", $3/$2*100}'"
    )
    disks_usage, err, _ = run_command(
        client,
        "df -hT | grep -E \"ext4|xfs|挂载点|Mounted\" | awk '{print $7,$3,$4,$5,$6}'"
    )

    if err:
        print_error("获取信息出错：" + err)
        return None

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 二、系统资源与性能\n\n")
        f.write(f"- **系统负载：** `{system_load.strip()}`\n")
        f.write(f"- **CPU 使用率：** `{cpu_usage.strip()}`\n")
        f.write(f"- **内存使用率：** `{mem_usage.strip()}`\n\n")

        rows = [line.split() for line in disks_usage.strip().splitlines() if line.strip()]
        if rows:
            header, *body = rows
            f.write("### 磁盘使用率\n\n")
            f.write("| " + " | ".join(header) + " |\n")
            f.write("| " + " | ".join(["---"] * len(header)) + " |\n")
            for r in body:
                f.write("| " + " | ".join(r) + " |\n")
            f.write("\n")

        f.write("---\n\n")
    return None

def security_info(client, filename):
    permit_root_login, err, _ = run_command(
        client,
        "grep -E \"^PermitRootLogin\" /etc/ssh/sshd_config 2>/dev/null || echo \"未配置\""
    )
    password_expired_policy, err, _ = run_command(
        client,
        "chage -l root 2>/dev/null | grep -E \"Maximum|最大|minimum|最小|Last|最近\""
    )
    last_login, err, _ = run_command(client, "last -n 5 | grep -v begins")
    failed_login, err, _ = run_command(
        client,
        "lastb -n 5 | grep -v begins 2>/dev/null"
    )
    firewalld_status, err, _ = run_command(
        client,
        "systemctl is-active firewalld &>/dev/null && echo \"✅ 运行中\" || echo \"❌ 未运行\""
    )
    selinux_status, err, _ = run_command(client, "getenforce")

    if err:
        print_error("获取信息出错：" + err)
        return None

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 三、安全配置\n\n")
        f.write(f"- **Root 远程登录检查：** `{permit_root_login.strip()}`\n")
        f.write(f"- **防火墙状态：** {firewalld_status.strip()}\n")
        f.write(f"- **SeLinux 状态：** `{selinux_status.strip()}`\n\n")

        f.write("### 密码策略\n\n```text\n")
        f.write(f"{password_expired_policy.strip()}\n" if password_expired_policy.strip() else "无\n")
        f.write("```\n\n")

        f.write("### 最近登录记录\n\n```text\n")
        f.write(f"{last_login.strip()}\n" if last_login.strip() else "无\n")
        f.write("```\n\n")

        if failed_login.strip():
            f.write("### 失败登录记录\n\n```text\n")
            f.write(f"{failed_login.strip()}\n")
            f.write("```\n\n")

        f.write("---\n\n")
    return None

def service_status(client, filename):
    services = "sshd nginx mysqld redis dockerd rabbitmq DmServiceDMSERVER".split()

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 四、服务与进程状态\n\n")

        for service in services:
            out, err, code = run_command(client, f"systemctl status {service}")
            if "could not be found" in (err or "") or "could not be found" in (out or ""):
                print_info(f"{service}: 未安装或未找到服务")
                continue

            status, err, code = run_command(client, f"systemctl is-active {service}")
            if err and "could not be found" not in err:
                print_error("获取信息出错：" + err)
                continue

            if status.strip() == "active":
                f.write(f"- **{service}：** ✅ 运行中\n")
            else:
                f.write(f"- **{service}：** ☐ 未运行\n")
        print(f"\n")

        f.write("\n---\n\n")
    return None

def network_info(client, filename):
    ports, err, _ = run_command(
        client,
        "netstat -tupln | grep -E \"LISTEN\" | awk '{print $4}'"
    )
    network, err, _ = run_command(
        client,
        "ip -o -4 addr | awk '!/docker|veth|br-|cni|flannel|tun|kube/ && $2!=\"lo\" {print $2, $4}' | uniq"
    )

    if err:
        print_error("获取信息出错：" + err)
        return None

    rows = [line.split() for line in network.strip().splitlines() if line.strip()]

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 五、网络与端口\n\n")

        f.write("### 开放端口列表\n\n```text\n")
        f.write(f"{ports.strip()}\n" if ports.strip() else "无\n")
        f.write("```\n\n")

        if rows:
            f.write("### 网卡地址信息\n\n")
            f.write("| 接口 | 地址 |\n")
            f.write("| --- | --- |\n")
            for name, addr in rows:
                f.write(f"| {name} | {addr} |\n")
            f.write("\n")

        f.write("---\n\n")
    return None

def log_error(client, filename):
    logs_error, err, _ = run_command(
        client,
        "grep -v \"ldapdb_canonuser_plug_init\" /var/log/messages | grep -E \"error|fail|critical\" | tail -n 20"
    )

    if err:
        print_error("获取信息出错：" + err)
        return None

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 六、日志与系统错误\n\n")
        f.write("### 系统错误日志（最近 20 行）\n\n```text\n")
        f.write(f"{logs_error.strip()}\n" if logs_error.strip() else "无\n")
        f.write("```\n\n")
        f.write("---\n\n")
    return None

def run(clients):
    for ip, client in clients:
        print_info(f"当前操作的服务器：[{ip}]")
        hostname, err, _ = run_command(client, "hostname")
        timestamp = datetime.datetime.now().strftime("%Y%m")
        group = sys.argv[2] if len(sys.argv) > 2 else None

        dir_name = f"server_check/reports/{group}/{timestamp}"
        try:
            os.makedirs(dir_name, exist_ok=True)
        except Exception as e:
            print_error(f"创建目录 {dir_name} 失败：{e}")

        filename = f"{dir_name}/{ip}_{hostname.strip()}.md"

        try:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# 服务器巡检报告 - {hostname.strip()} ({ip})\n\n")
                f.write(f"- 生成时间：`{now_str}`\n\n")
                f.write("---\n\n")

            server_info(client, filename)
            system_resources(client, filename)
            security_info(client, filename)
            service_status(client, filename)
            network_info(client, filename)
            log_error(client, filename)
        except Exception as e:
            print_error(f"[{ip}] 执行失败：{e}")
