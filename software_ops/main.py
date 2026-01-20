from .docker_manager import manage_docker
from .minio_manager import manage_minio

from colorama import Fore, Style
from utils.output import print_info, print_warning, print_error

# 注册所有操作：编号 -> (描述, 函数)
operations = {
    "1": ("Docker管理", manage_docker),
    "2": ("Minio管理", manage_minio),
}

def run(clients):
    print(Style.BRIGHT + "-" * 40)
    print_info("开始执行软件管理操作")
    print(Style.BRIGHT + "-" * 40)
    while True:
        print(Style.BRIGHT + Fore.BLUE + "\n=========== 软件管理菜单 ===========")
        for key, (desc, _) in operations.items():
            print(f"{key}. {desc}")
        print("0. 退出")

        choice = input(Fore.MAGENTA + "请输入操作编号: ").strip()

        if choice == "0":
            print_info("退出软件管理操作。")
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