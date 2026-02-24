from .mysql_exporter import manage_mysql_exporter
from .prometheus_monitor import manage_prometheus
from .node_exporter import manage_node_exporter
from utils.menu_runner import run_menu

# 注册所有操作：编号 -> (描述, 函数)
operations = {
    "1": ("安装Prometheus", manage_prometheus),
    "2": ("安装mysqld监控", manage_mysql_exporter),
    "3": ("安装node-exporter监控", manage_node_exporter),
}

def run(clients):
    run_menu("监控管理", operations, clients)