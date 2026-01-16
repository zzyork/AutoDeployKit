from server_ops.hostname_ops import manage_hostname
from server_ops.pkg_ops import manage_packages
from server_ops.firewall_selinux_ops import manage_firewall_selinux
from server_ops.kernel_optimize_ops import kernel_optimize
from server_ops.disk_partition_ops import manage_disk_partition
from server_ops.system_optimize_ops import manage_system_optimize
from server_ops.openssl_upgrade import manage_ssl
from server_ops.openssh_upgrade import manage_openssh

from colorama import Fore, Style
from utils.output import print_info, print_warning, print_error

# 注册所有操作：编号 -> (描述, 函数)
operations = {
    "1": ("设置主机名", manage_hostname),
    "2": ("管理软件包", manage_packages),
    "3": ("配置防火墙和 SELinux", manage_firewall_selinux),
    "4": ("内核参数调优", kernel_optimize),
    "5": ("磁盘分区与挂载", manage_disk_partition),
    "6": ("系统优化", manage_system_optimize),
    "7": ("OpenSSL管理", manage_ssl),
    "8": ("OpenSSH管理", manage_openssh),
}

def run(clients):
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

        if choice not in operations:
            print_warning("无效输入，请重新选择。")

        _, func = operations[choice]

        for hostname, client in clients:
            print_info(f"当前操作的服务器：[{hostname}]")
            try:
                func(client)
            except Exception as e:
                print_error(f"[{hostname}] 执行失败：{e}")