from .hostname_ops import manage_hostname
from .yum_repos_ops import manage_yum_repos
from .pkg_ops import manage_packages
from .firewall_selinux_ops import manage_firewall_selinux
from .kernel_optimize_ops import kernel_optimize
from .disk_partition_ops import manage_disk_partition
from .system_optimize_ops import manage_system_optimize

from colorama import Fore, Style
from utils.output import print_info, print_success, print_warning

# 注册所有操作：编号 -> (描述, 函数)
operations = {
    "1": ("设置主机名", manage_hostname),
    "2": ("管理 Yum 源", manage_yum_repos),
    "3": ("管理软件包", manage_packages),
    "4": ("配置防火墙和 SELinux", manage_firewall_selinux),
    "5": ("内核参数调优", kernel_optimize),
    "6": ("磁盘分区与挂载", manage_disk_partition),
    "7": ("系统优化", manage_system_optimize),
}

def run(client):
    print(Style.BRIGHT + "-" * 40)
    print_info("开始执行服务器初始化操作")
    print(Style.BRIGHT + "-" * 40)

    while True:
        print(Style.BRIGHT + Fore.BLUE + "\n=== 服务器初始化菜单 ===")
        for key, (desc, _) in operations.items():
            print(f"{key}. {desc}")
        print("0. 退出")

        choice = input(Fore.MAGENTA + "请输入操作编号: ").strip()

        if choice == "0":
            print_info("退出服务器初始化。")
            break
        elif choice in operations:
            desc, func = operations[choice]
            print_info(f"\n>>> 执行操作：{desc}")
            func(client)
        else:
            print_warning("无效输入，请重新选择。")

    print(Style.BRIGHT + "-" * 40)
    print_success("服务器初始化操作完成")
    print(Style.BRIGHT + "-" * 40)
