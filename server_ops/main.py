from .hostname_ops import manage_hostname
from .pkg_ops import manage_packages
from .firewall_ops import manage_firewall_selinux
from .kernel_optimize_ops import kernel_optimize
from .disk_partition_ops import manage_disk_partition
from .system_optimize_ops import manage_system_optimize
from .openssl_upgrade import manage_ssl
from utils.menu_runner import run_menu

# 注册所有操作：编号 -> (描述, 函数)
operations = {
    "1": ("设置主机名", manage_hostname),
    "2": ("管理软件包", manage_packages),
    "3": ("防火墙(firewalld)配置", manage_firewall_selinux),
    "4": ("内核参数调优", kernel_optimize),
    "5": ("磁盘分区与挂载", manage_disk_partition),
    "6": ("系统优化", manage_system_optimize),
    "7": ("OpenSSL管理", manage_ssl),
}

def run(clients):
    run_menu("服务器初始化", operations, clients)