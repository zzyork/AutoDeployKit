from utils.ssh_utils import run_command
from colorama import Fore
from utils.output import print_info, print_success, print_warning, print_error

def manage_hostname(client):
    current_hostname, err, _ = run_command(client, "hostname")
    if err:
        print_error("获取主机名时出错: " + err)
        return None

    current_hostname = current_hostname.strip()
    print_info(f"当前主机名: {current_hostname}")

    new_hostname = input(Fore.MAGENTA + "请输入要设置的新主机名（回车跳过）: ").strip()
    if new_hostname:
        output, err, _ = run_command(client, f"hostnamectl set-hostname {new_hostname}")
        if err:
            print_error("设置主机名时出错: " + err)
            return None
        else:
            print_success(f"主机名已设置为: {new_hostname}")
            return None
    else:
        print_warning("跳过设置主机名")
        return None
