from utils.ssh_utils import run_command, run_command_live
from utils.output import print_info, print_success, print_warning, print_error
from utils.choice import confirm_yes_no
from utils.menu_runner import run_menu


def manage_firewalld(client):
    print_info("检查 firewalld 状态 ...")
    output, err, _ = run_command(client, "systemctl is-active firewalld")
    status = output.strip()

    if err or status not in ["active", "inactive"]:
        print_warning("无法确定 firewalld 状态，跳过处理")
        return

    print_info(f"当前 firewalld 状态：{status}")
    if status == "inactive":
        if confirm_yes_no("\nfirewalld 处于关闭状态，是否开启？", default=False):
            print_info("正在开启 firewalld ...")
            _, status = run_command_live(client, "systemctl start firewalld")
            if status == 0:
                print_success("firewalld 已开启")
            else:
                print_error("开启 firewalld 失败")
            if confirm_yes_no("\n是否配置 firewalld 开机自启？", default=False):
                _, status = run_command_live(client, "systemctl enable firewalld")
                if status == 0:
                    print_success("firewalld 已配置开机自启")
                else:
                    print_error("配置 firewalld 开机自启失败")
        else:
            print_warning("保留 firewalld 当前状态")
    elif status == "active":
        if confirm_yes_no("\nfirewalld 处于开启状态，是否关闭？", default=False):
            print_info("正在关闭 firewalld ...")
            _, status = run_command_live(client, "systemctl stop firewalld")
            if status == 0:
                print_success("firewalld 已关闭")
            else:
                print_error("关闭 firewalld 失败")
            if confirm_yes_no("\n是否关闭firewalld 开机自启？", default=False):
                _, status = run_command_live(client, "systemctl disable firewalld")
                if status == 0:
                    print_success("firewalld 已配置关闭开机自启")
                else:
                    print_error("配置 firewalld 关闭开机自启失败")
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

    if not confirm_yes_no("是否禁用 SELinux？", default=False):
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

operations = {
    "1": ("防火墙 (firewalld) 配置", manage_firewalld),
    "2": ("禁用 SELinux", disable_selinux),
}

def manage_firewall_selinux(clients):
    run_menu("防火墙与 SELinux 配置", operations, clients)
