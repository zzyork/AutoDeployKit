from utils.ssh_utils import run_command, run_command_live
from utils.output import print_info, print_success, print_warning, print_error
from utils.choice import confirm_yes_no, menu_choice
from colorama import Fore


def check_and_disable_firewalld(client):
    print_info("检查 firewalld 状态 ...")
    output, err, _ = run_command(client, "systemctl is-active firewalld")
    status = output.strip()

    if err or status not in ["active", "inactive"]:
        print_warning("无法确定 firewalld 状态，跳过处理")
        return

    print_info(f"当前 firewalld 状态：{status}")
    if status == "inactive":
        print_success("firewalld 已处于关闭状态")
        return

    if confirm_yes_no("是否关闭并禁用自启 firewalld？", default=False):
        print_info("正在关闭并禁用 firewalld ...")
        _, status = run_command_live(client, "systemctl stop firewalld && systemctl disable firewalld")
        if status == 0:
            print_success("firewalld 已关闭并禁用")
        else:
            print_error("关闭 firewalld 失败")
    else:
        print_warning("保留 firewalld 当前状态")


def disable_selinux(client):
    # 检查 SELinux 当前状态
    print_info("检查 SELinux 状态 ...")
    output, err, _ = run_command(client, "getenforce")
    selinux_status = output.strip().lower()

    if err or selinux_status not in ["enforcing", "permissive", "disabled"]:
        print_warning("无法确定 SELinux 状态，跳过处理")
        return

    print_info(f"当前 SELinux 状态：{selinux_status}")
    if selinux_status == "disabled":
        print_success("SELinux 已处于关闭状态")
        return

    if confirm_yes_no("是否禁用 SELinux？", default=False):
        print_warning("保留 SELinux 当前状态")
        return
    print_info("正在设置 SELinux 为 disabled ...")
    run_command(client, "setenforce 0")

    cmd = "sed -i 's/^SELINUX=.*/SELINUX=disabled/' /etc/selinux/config"
    _, status = run_command_live(client, cmd)
    if status == 0:
        print_success("SELinux 配置修改成功（需重启生效）")
    else:
        print_error("修改 SELinux 配置失败")


def manage_firewall_selinux(client):
    print(Fore.BLUE + "\n=== 防火墙与 SELinux 配置 ===")

    check_and_disable_firewalld(client)
    disable_selinux(client)
