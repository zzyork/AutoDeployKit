from .nginx_manager import manage_nginx
from .mysql_manager import manage_mysql
from .redis_manager import manage_redis
from .rabbitmq_manager import install_rabbitmq

from colorama import Fore, Style
from utils.output import print_info, print_warning, print_error
from utils.menu_runner import run_menu

# 注册所有操作：编号 -> (描述, 函数)
operations = {
    "1": ("Nginx管理", manage_nginx),
    "2": ("Mysql管理", manage_mysql),
    "3": ("Redis管理", manage_redis),
    "4": ("RabbitMQ管理", install_rabbitmq),
}

def run(clients):
    run_menu("中间件管理", operations, clients)
