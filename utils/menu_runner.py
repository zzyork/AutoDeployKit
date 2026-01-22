# utils/menu_runner.py
import inspect
from colorama import Fore, Style
from utils.output import print_info, print_warning, print_error

def run_menu(title: str, operations: dict, clients: list):

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
        try:
            params = inspect.signature(func).parameters
        except (TypeError, ValueError):
            params = {}

        # If the operation explicitly asks for the full clients list, call once.
        if len(params) == 1 and "clients" in params:
            try:
                func(clients)
            except Exception as e:
                print_error(f"执行失败：{e}")
            continue

        for hostname, client in clients:
            print_info(f"当前操作的服务器：[{hostname}]")
            try:
                func(client)
            except Exception as e:
                print_error(f"[{hostname}] 执行失败：{e}")
