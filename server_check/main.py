import datetime
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from colorama import Fore

from utils.output import buffer_output, print_error, print_info, print_warning
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


def system_resources(client, filename):
    system_load, err, _ = run_command(client, "cat /proc/loadavg | awk '{print $1,$2,$3}'")
    cpu_usage, err, _ = run_command(client, "vmstat 1 2 | tail -1 | awk '{print 100-$15\"%\"}'")
    mem_usage, err, _ = run_command(client, "free -m | awk '/Mem:/ {printf \"%.1f%%\\n\", $3/$2*100}'")
    disks_usage, err, _ = run_command(
        client,
        "df -hT | grep -E \"ext4|xfs|挂载点|Mounted\" | awk '{print $7,$3,$4,$5,$6}'",
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
            for row in body:
                f.write("| " + " | ".join(row) + " |\n")
            f.write("\n")

        f.write("---\n\n")
    return None


def security_info(client, filename):
    permit_root_login, err, _ = run_command(
        client,
        "grep -E \"^PermitRootLogin\" /etc/ssh/sshd_config 2>/dev/null || echo \"未配置\"",
    )
    password_expired_policy, err, _ = run_command(
        client,
        "chage -l root 2>/dev/null | grep -E \"Maximum|最大|minimum|最小|Last|最近\"",
    )
    last_login, err, _ = run_command(client, "last -n 5 | grep -v begins")
    failed_login, err, _ = run_command(client, "lastb -n 5 | grep -v begins 2>/dev/null")
    firewalld_status, err, _ = run_command(
        client,
        "systemctl is-active firewalld >/dev/null 2>&1 && echo \"✅ 运行中\" || echo \"❌ 未运行\"",
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


def network_info(client, filename):
    ports, err, _ = run_command(client, "netstat -tupln | grep -E \"LISTEN\" | awk '{print $4}'")
    network, err, _ = run_command(
        client,
        "ip -o -4 addr | awk '!/docker|veth|br-|cni|flannel|tun|kube/ && $2!=\"lo\" {print $2, $4}' | uniq",
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


def _append_log_section(filename, title, content, fallback_message):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"### {title}\n\n```text\n")
        f.write(content.strip() + "\n" if content.strip() else fallback_message + "\n")
        f.write("```\n\n")


def _collect_journal_errors(client, days, lines):
    cmd = (
        "bash -lc '"
        "if command -v journalctl >/dev/null 2>&1; then "
        "set -o pipefail; "
        f"journalctl --since \"{days} days ago\" -p err..alert --no-pager "
        "| grep -viE \"systemd-coredump|ldapdb_canonuser_plug_init\" | tail -n "
        f"{lines}; "
        "else echo __JOURNALCTL_NOT_FOUND__; fi'"
    )
    return run_command(client, cmd)


def _collect_file_errors(client, path, lines):
    cmd = (
        "bash -lc '"
        f"if [ -f {path} ]; then "
        "set -o pipefail; "
        f"grep -aiE \"error|failed|fatal|panic|crit|critical|异常\" {path} | tail -n {lines}; "
        "fi'"
    )
    return run_command(client, cmd)


def log_error(client, filename, days=30, lines=200):
    days = max(1, int(days))
    lines = max(1, int(lines))
    journal_out, journal_err, journal_status = _collect_journal_errors(client, days, lines)

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 六、日志与系统错误\n\n")

    if "__JOURNALCTL_NOT_FOUND__" in journal_out:
        _append_log_section(filename, "systemd journal 错误日志", "", "当前系统未安装 journalctl。")
    elif journal_status == 0 and journal_out.strip():
        _append_log_section(
            filename,
            f"systemd journal 错误日志（最近 {days} 天内，最近 {lines} 行）",
            journal_out,
            "未匹配到 err..alert 级别日志。",
        )
    elif journal_status != 0 and journal_err.strip():
        _append_log_section(
            filename,
            "systemd journal 错误日志",
            journal_err,
            "journalctl 查询失败。",
        )
    else:
        _append_log_section(
            filename,
            f"systemd journal 错误日志（最近 {days} 天内，最近 {lines} 行）",
            "",
            "未匹配到 err..alert 级别日志。",
        )

    fallback_logs = [
        "/var/log/messages",
        "/var/log/secure",
        "/var/log/nginx/error.log",
        "/var/log/mysql/error.log",
        "/var/log/mysqld.log",
        "/var/log/rabbitmq/rabbitmqd-error.log",
    ]

    for log_path in fallback_logs:
        safe_path = log_path.replace("'", "'\"'\"'")
        file_out, file_err, file_status = _collect_file_errors(client, f"'{safe_path}'", lines)
        title = f"文件日志扫描：{log_path}（关键字匹配最近 {lines} 行）"
        if file_status == 0 and file_out.strip():
            _append_log_section(filename, title, file_out, "未匹配到关键字日志。")
        elif file_err.strip():
            _append_log_section(filename, title, file_err, "日志文件扫描失败。")
        elif file_status == 0:
            _append_log_section(filename, title, "", "文件存在，但未匹配到关键字日志。")

    with open(filename, "a", encoding="utf-8") as f:
        f.write("---\n\n")

    return None


def monitors(client, filename):
    with open(filename, "a", encoding="utf-8") as f:
        exporters_out, _, _ = run_command(client, "systemctl list-unit-files 2>&1 | grep -i 'exporter' | awk '{print $1}'")
        exporters = [line.strip() for line in exporters_out.splitlines() if line.strip()]
        f.write("## 七、监控状态\n\n")
        if not exporters:
            f.write("未找到任何已安装的 exporter。\n")
        for exporter in exporters:
            status_out, _, status = run_command(client, f"systemctl is-active {exporter}")
            if status == 1:
                print_error("exporter 状态查询失败！")
                return None
            if status_out.strip() == "active":
                f.write(f"- **{exporter}：** ✅ 运行中\n")
            else:
                f.write(f"- **{exporter}：** ☐ 未运行\n")
        f.write("\n")
    return None


def inspect_server(ip, client, path):
    with buffer_output():
        print_info(f"当前操作的服务器：[{ip}]")
        hostname, err, _ = run_command(client, "hostname")
        if err:
            print_error(f"[{ip}] 获取主机名失败：{err}")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m")
        group = sys.argv[2] if len(sys.argv) > 2 else "ungrouped"
        file_path = os.path.join(path, group, timestamp)

        try:
            os.makedirs(file_path, exist_ok=True)
        except Exception as exc:
            print_error(f"创建目录 {file_path} 失败：{exc}")
            return

        filename = os.path.join(file_path, f"{ip}_{hostname.strip()}.md")

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
            monitors(client, filename)
            print_info(f"[{ip}] 巡检完成，报告已生成：{filename}")
        except Exception as exc:
            print_error(f"[{ip}] 执行失败：{exc}")


def choose_report_path(default_path):
    env_path = os.getenv("SERVER_CHECK_REPORT_DIR")
    if env_path:
        return env_path

    if sys.platform.startswith("win") and sys.stdin.isatty():
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askdirectory(
                title="选择报告保存目录",
                initialdir=default_path,
                mustexist=False,
            )
            root.destroy()
            if path:
                return path
        except Exception as exc:
            print_warning(f"打开目录选择器失败，将使用默认目录：{exc}")

    if sys.stdin.isatty():
        path = input(Fore.MAGENTA + f"请输入报告保存目录 (默认: {default_path}): ").strip()
        if path:
            return path

    print_info("未提供报告目录，将使用默认地址: " + default_path)
    return default_path


def run(clients):
    default_path = "server_check/reports"
    path = choose_report_path(default_path)
    print_info("报告将保存到: " + path + "\n")

    max_workers = int(os.getenv("MAX_WORKERS", str(min(len(clients), 5) or 1)))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ip = {executor.submit(inspect_server, ip, client, path): ip for ip, client in clients}
        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                future.result()
            except Exception as exc:
                print_error(f"[{ip}] 执行失败：{exc}")
