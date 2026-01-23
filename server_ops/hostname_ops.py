from utils import choice
from utils.ssh_utils import run_command
from colorama import Fore
from utils.output import print_info, print_success, print_warning, print_error
from utils.choice import confirm_yes_no

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
            hostname, _, _ = run_command(client, "hostname")
            hostname = hostname.strip()
            print_success(f"主机名已设置为: {hostname}")
        
        choice = confirm_yes_no("是否向/etc/hosts 文件添加新主机名？")
        if choice:
            run_command(client, f"echo '127.0.0.1 {new_hostname}' >> /etc/hosts")
            print_success(f"主机名已添加到/etc/hosts文件")
            hosts, _, _ = run_command(client, "cat /etc/hosts")
            print_info("当前/etc/hosts文件内容:\n" + hosts.strip())
        else:
            print_warning("跳过添加主机名到/etc/hosts文件")
            
    else:
        print_warning("跳过设置主机名")
        return None
