import os
import time

from utils.ssh_utils import run_command, run_command_live
from utils.file_utils import upload_file
from utils.output import print_info, print_success, print_warning, print_error
from utils.hash_utils import get_local_md5, get_remote_md5
from colorama import Fore

LIMITS_FILE = "/etc/security/limits.conf"
SYSCTL_FILE = "/etc/sysctl.conf"
DEFAULT_SYSCTL_LOCAL = "config/linux/sysctl.conf"
LIMIT_RULES = {
    "nofile": [
        "* soft nofile 65535",
        "* hard nofile 65535"
    ],
    "nproc": [
        "* soft nproc 65535\n* hard nproc 65535"
    ]
}


def check_and_optimize_limits(client):
    print_info(f"检查 {LIMITS_FILE} 配置 ...")

    cmd = f"grep -E '^\\*' {LIMITS_FILE} || true"
    output, _, _ = run_command(client, cmd)
    print(output)

    for limit_type, rules in LIMIT_RULES.items():
        missing = [r for r in rules if r not in output]

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
    local_md5 = get_local_md5(DEFAULT_SYSCTL_LOCAL)
    remote_md5 = get_remote_md5(client, "/etc/sysctl.conf")
    print_info("\n检查 /etc/sysctl.conf 系统参数配置 ...")

    # 读取本地模板
    local_path = os.path.join("config", "linux", "sysctl.conf")
    if not os.path.exists(local_path):
        print_error("默认配置文件不存在：config/linux/sysctl.conf")
        return

    # 判断差异
    if local_md5 == remote_md5:
        print_success("当前 /etc/sysctl.conf 与默认模板完全一致")
        return

    print_warning("sysctl.conf 配置与模板不一致")
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