# utils/menu_runner.py
from colorama import Fore, Style
from utils.output import print_info, print_warning, print_error

def run_menu(title: str, operations: dict, clients: list):
    print(Style.BRIGHT + "-" * 40)
    print_info(f"开始执行{title}")
    print(Style.BRIGHT + "-" * 40)

    while True:
        print(Style.BRIGHT + Fore.BLUE + f"\n========== {title}菜单 ==========")
        for key, (desc, _) in operations.items():
            print(f"{key}. {desc}")
        print("0. 退出")

        choice = input(Fore.MAGENTA + "请输入操作编号: ").strip()

        if choice == "0":
            print_info(f"退出{title}。")
            break
        if choice not in operations:
            print_warning("无效输入，请重新选择。")
            continue

        _, func = operations[choice]
        for hostname, client in clients:
            print_info(f"当前操作的服务器：[{hostname}]")
            try:
                func(client)
            except Exception as e:
                print_error(f"[{hostname}] 执行失败：{e}")
