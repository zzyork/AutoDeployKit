from .docker_manager import manage_docker
from .minio_manager import manage_minio

from colorama import Fore, Style
from utils.output import print_info, print_warning, print_error
from utils.menu_runner import run_menu

# 注册所有操作：编号 -> (描述, 函数)
operations = {
    "1": ("Docker管理", manage_docker),
    "2": ("Minio管理", manage_minio),
}

def run(clients):
    run_menu("软件管理", operations, clients)