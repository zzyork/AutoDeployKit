from utils.ssh import run_command, run_command_live
from utils.output import print_info, print_success, print_warning, print_error
from colorama import Fore

DEPENDENCIES = [
    "gcc", "gcc-c++", "glibc-headers", "make", "python3", "bc", "lvm2"
]

TOOLS = [
    "unzip", "zip", "vim", "git", "net-tools", "lrzsz", "bind-utils",
    "dos2unix", "sysstat", "irqbalance", "tree", "nmap", "iptraf",
    "rsync", "net-snmp", "openssh-clients", "wget",
    "telnet", "iotop", "htop", "tar", "ntpdate"
]

def print_tail(output, n=20):
    lines = output.strip().splitlines()
    tail = lines[-n:] if len(lines) > n else lines
    print("\n".join(tail))

def install_packages(client, name, package_list):
    print_info(f"\n{name}：")
    print(Fore.CYAN + " ".join(package_list))

    choice = input(Fore.MAGENTA + f"\n是否安装 {name}？(y/N): ").strip().lower()
    if choice != 'y':
        print_warning(f"跳过安装 {name}")
        return

    pkg_str = " ".join(package_list)
    print_info(f"正在安装 {name} ...")

    cmd = f"yum install -y {pkg_str}"
    output, err = run_command_live(client, cmd)

    if err:
        print_error(f"{name} 安装失败: {err}")
    else:
        print_success(f"{name} 安装完成")
        print_info("安装输出（末尾部分）:")
        print_tail(output)

def upgrade_all_packages(client):
    choice = input(Fore.MAGENTA + "\n是否升级所有系统软件包？(y/N): ").strip().lower()
    if choice != 'y':
        print_warning("跳过升级。")
        return

    print_info("正在执行 yum update -y ...")
    output, err = run_command_live(client, "yum update -y")
    if err:
        print_error("系统升级失败: " + err)
    else:
        print_success("系统软件包升级完成")
        print_info("升级输出（末尾部分）:")
        print_tail(output)

def manage_packages(client):
    while True:
        print(Fore.BLUE + "\n=== 软件包管理 ===")
        print("1. 升级所有软件包")
        print("2. 安装基础依赖包")
        print("3. 安装基础工具包")
        print("0. 返回上级菜单")

        choice = input(Fore.MAGENTA + "请选择操作编号: ").strip()
        if choice == "1":
            upgrade_all_packages(client)
        elif choice == "2":
            install_packages(client, "基础依赖包", DEPENDENCIES)
        elif choice == "3":
            install_packages(client, "基础工具包", TOOLS)
        elif choice == "0":
            print_info("返回上级菜单。")
            break
        else:
            print_warning("无效输入，请重新选择。")
