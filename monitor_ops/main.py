from .mysql_monitor import manage_mysql_monitor
from .prometheus_monitor import manage_prometheus

from colorama import Fore, Style
from utils.output import print_info, print_warning, print_error
from utils.menu_runner import run_menu

# 注册所有操作：编号 -> (描述, 函数)
operations = {
    "1": ("安装Prometheus", manage_prometheus),
    "2": ("安装mysqld监控", manage_mysql_monitor),
}

def run(clients):
    run_menu("监控管理", operations, clients)