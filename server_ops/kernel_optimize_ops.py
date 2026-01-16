import os
import time
import re

from utils.ssh_utils import run_command, run_command_live
from utils.file_utils import upload_file, get_local_md5, get_remote_md5, compare_file_content
from utils.output import print_info, print_success, print_warning, print_error
from colorama import Fore

LIMITS_FILE = "/etc/security/limits.conf"
SYSCTL_FILE = "/etc/sysctl.conf"
DEFAULT_SYSCTL_LOCAL = "config/linux/sysctl.conf"
LIMIT_RULES = {
    "nofile": [
        "* soft nofile 65535",
        "* hard nofile 65535",
    ],
    "nproc": [
        "* soft nproc 65535",
        "* hard nproc 65535",
    ],
}


def _normalize_line(s: str) -> str:
    # 去掉首尾空白 + 把多个空格/Tab 压成一个空格
    return re.sub(r"\s+", " ", s.strip())

def check_and_optimize_limits(client):
    print_info(f"检查 {LIMITS_FILE} 配置 ...")

    cmd = f"grep -E '^\\*' {LIMITS_FILE} || true"
    output, _, _ = run_command(client, cmd)
    print(output)

    # 把输出按行归一化，做成一个集合便于判断
    normalized_lines = {_normalize_line(line) for line in output.splitlines() if line.strip()}

    for limit_type, rules in LIMIT_RULES.items():
        missing = [r for r in rules if _normalize_line(r) not in normalized_lines]

        if not missing:
            print_success(f"{limit_type} 已设置为 65535")
            continue

        print_warning(f"{limit_type} 未完全设置为 65535")
        choice = input(Fore.MAGENTA + f"是否设置 {limit_type} 为 65535？(y/N): ").strip().lower()
        if choice == "y":
            for rule in missing:
                run_command(client, f"echo '{rule}' >> {LIMITS_FILE}")
            print_success(f"{limit_type} 设置完成")
        else:
            print_warning(f"跳过设置 {limit_type}")

def check_and_optimize_sysctl(client):
    print_info("\n检查 /etc/sysctl.conf 系统参数配置 ...")

    # 读取本地模板
    local_path = os.path.join("config", "linux", "sysctl.conf")
    if not os.path.exists(local_path):
        print_error("默认配置文件不存在：config/linux/sysctl.conf")
        return

    # 使用文件内容对比
    diff_result = compare_file_content(client, local_path, "/etc/sysctl.conf")
    
    # 判断差异
    if diff_result == "文件内容完全相同":
        print_success("当前 /etc/sysctl.conf 与默认模板完全一致")
        return

    print_warning("sysctl.conf 配置与模板不一致")
    print_info("差异详情:")
    print(diff_result)
    
    choice = input(Fore.MAGENTA + "是否上传默认模板并替换？(y/N): ").strip().lower()
    if choice != "y":
        print_warning("跳过 sysctl 配置修改")
        return

    # 备份原文件
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_cmd = f"cp /etc/sysctl.conf /etc/sysctl.conf.bak_{timestamp}"
    print_info(f"备份原始 sysctl.conf 为 sysctl.conf.bak_{timestamp} ...")
    _, _, status = run_command(client, backup_cmd)
    if status != 0:
        print_warning("备份失败，可能文件不存在或权限不足")

    # 上传并生效
    upload_file(client, local_path, "/etc/sysctl.conf")
    print_info("已上传配置文件，执行 sysctl -p ...")
    _, status = run_command_live(client, "sysctl -p")
    if status == 0:
        print_success("sysctl 参数应用成功")
    else:
        print_error("sysctl -p 执行失败")

def kernel_optimize(client):
    print(Fore.BLUE + "\n=== 系统内核参数调优 ===")
    check_and_optimize_limits(client)
    check_and_optimize_sysctl(client)