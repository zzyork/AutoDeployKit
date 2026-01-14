from utils.ssh_utils import run_command, run_command_live
from utils.output import print_info, print_success, print_warning

def upgrade_packages(client):
    print_info("正在升级系统软件包 ...")
    _, _, status = run_command(client, "yum update -y")
    if status == 0:
        print_success("软件包升级完成")
    else:
        print_warning("软件包升级可能有错误")

def install_base_deps(client):
    # TODO：如果某个包不存在则移除后重试
    deps = "unzip zip vim git net-tools lrzsz bind-utils dos2unix sysstat irqbalance tree nmap iptraf gcc gcc-c++ rsync net-snmp openssh-clients lvm2 wget bc glibc-headers python3 telnet"
    print_info("正在安装基础依赖软件包 ...")
    _, _, status = run_command(client, f"yum install -y {deps}")
    if status == 0:
        print_success("基础依赖包安装完成")
    else:
        print_warning("部分依赖包可能安装失败")

def install_base_tools(client):
    # TODO：如果某个包不存在则移除后重试
    tools = "htop iotop tar make ntpdate lsof"
    print_info("正在安装基础工具软件包 ...")
    _, _, status = run_command(client, f"yum install -y {tools}")
    if status == 0:
        print_success("基础工具包安装完成")
    else:
        print_warning("部分工具包可能安装失败")

def manage_packages(client):
    while True:
        print("\n软件包管理选项：")
        print("1. 升级所有软件包")
        print("2. 安装基础依赖包")
        print("3. 安装基础工具包")
        print("0. 返回")

        op = input("请输入操作编号: ").strip()

        if op == "1":
            run_command_live(client, "yum update -y")
        elif op == "2":
            deps = "unzip zip vim git net-tools lrzsz bind-utils dos2unix sysstat irqbalance tree nmap iptraf gcc gcc-c++ rsync net-snmp openssh-clients lvm2 wget bc glibc-headers python3 telnet"
            run_command_live(client, f"yum install -y {deps}")
        elif op == "3":
            tools = "htop iotop tar make ntpdate"
            run_command_live(client, f"yum install -y {tools}")
        elif op == "0":
            break
        else:
            print_warning("无效选项，请重新输入")
