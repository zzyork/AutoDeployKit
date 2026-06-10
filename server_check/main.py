import datetime
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from colorama import Fore

from server_check.common import DEFAULT_CONFIG, load_config
from server_check.docker import docker_status
from server_check.error_logs import log_error
from server_check.monitors import monitors
from server_check.network import network_info
from server_check.security import security_info
from server_check.server_info import server_info
from server_check.server_resources import system_resources
from server_check.services import service_status
from server_check.supervisor import supervisor_status
from utils.output import buffer_output, print_error, print_info, print_warning
from utils.ssh_utils import run_command


CHECK_HANDLERS = {
    "server_info": server_info,
    "system_resources": system_resources,
    "security_info": security_info,
    "service_status": service_status,
    "network_info": network_info,
    "docker_status": docker_status,
    "supervisor_status": supervisor_status,
    "log_error": log_error,
    "monitors": monitors,
}


def inspect_server(ip, client, path, config):
    with buffer_output():
        print_info(f"当前操作的服务器：[{ip}]")
        hostname, err, status = run_command(client, "hostname")
        if status != 0:
            print_error(f"[{ip}] 获取主机名失败：{err or hostname}")
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
        body_filename = filename + ".body"
        alerts = []

        try:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(body_filename, "w", encoding="utf-8"):
                pass

            for check_name in config.get("checks", DEFAULT_CONFIG["checks"]):
                handler = CHECK_HANDLERS.get(check_name)
                if not handler:
                    print_warning(f"[{ip}] 未知巡检项，已跳过：{check_name}")
                    continue
                handler(client, body_filename, config, alerts)

            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# 服务器巡检报告 - {hostname.strip()} ({ip})\n\n")
                f.write(f"- 生成时间：`{now_str}`\n\n")
                f.write("---\n\n")

            with open(filename, "a", encoding="utf-8") as f:
                f.write("## 风险摘要\n\n")
                if alerts:
                    for alert in alerts:
                        f.write(f"- {alert}\n")
                else:
                    f.write("- ✅ 未发现达到告警阈值的风险项。\n")
                f.write("\n---\n\n")
            with open(body_filename, "r", encoding="utf-8") as body, open(filename, "a", encoding="utf-8") as report:
                report.write(body.read())
            os.remove(body_filename)
            print_info(f"[{ip}] 巡检完成，报告已生成：{filename}")
        except Exception as exc:
            print_error(f"[{ip}] 执行失败：{exc}")
            try:
                if os.path.exists(body_filename):
                    os.remove(body_filename)
            except Exception:
                pass


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
    default_path = "server_check/reporters"
    path = choose_report_path(default_path)
    config = load_config()
    print_info("报告将保存到: " + path + "\n")

    max_workers = int(os.getenv("MAX_WORKERS", str(min(len(clients), 5) or 1)))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ip = {executor.submit(inspect_server, ip, client, path, config): ip for ip, client in clients}
        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                future.result()
            except Exception as exc:
                print_error(f"[{ip}] 执行失败：{exc}")
