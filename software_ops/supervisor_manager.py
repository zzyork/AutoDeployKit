import os
import tempfile
from utils.file_utils import upload_file_with_vars, upload_file
from utils.output import print_info, print_error, print_warning, print_success
from utils.ssh_utils import run_command, run_command_live
from utils.choice import confirm_yes_no, menu_choice

current_version, status, stable_version = None, None, None

def install_supervisor(client):
    print_info("supervisor最新稳定版为：" + stable_version)
    if confirm_yes_no("是否确认安装？", default=False):
        print_info("开始安装supervisor " + stable_version + "......")

        cmds = [
            "pip install supervisor",
            "mkdir -vp /var/log/supervisor",
            "mkdir -vp /var/run/supervisor",
            ]
        for cmd in cmds:
            _, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0:
                print_error(f"命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单")
                return

        if confirm_yes_no("是否自动配置 supervisord.conf 文件？", default=False):
            while True:
                ini_path = input("请输入ini配置文件保存路径（默认：/etc/supervisord.d）：").strip()
                if ini_path == "":
                    ini_path = "/etc/supervisord.d"
                if ini_path.startswith("/"):
                    break
                print_error("请输入正确的绝对路径")

            run_command_live(client, f"mkdir -p {ini_path}")
            local_path = os.path.join("config", "supervisor", "supervisord.conf")
            remote_path = "/etc/supervisord.conf"
            choice = menu_choice("是否开启web UI管理服务？(y/n): ", valid_choices=['y', 'n'], default='n')
            
            if choice == 'y':
                username = input("请输入web UI用户名（默认：admin）：").strip()
                if username == "":
                    username = "admin"
                password = input("请输入web UI密码（默认：admin）：").strip()
                if password == "":
                    password = "admin"
                upload_file_with_vars(client, local_path, remote_path,{'USERNAME': username, 'PASSWORD': password})
                run_command_live(client, "sed -i '/^[;[:space:]]*\\[inet_http_server\\]/,/^\\[/{s/^[[:space:]]*;//}' /etc/supervisord.conf")
            elif choice == 'n':
                upload_file(client, local_path, remote_path)

        if confirm_yes_no("是否配置systemd守护进程？", default=False):
            local_path = os.path.join("config", "supervisor", "supervisord.service")
            remote_path = "/etc/systemd/system/supervisord.service"
            upload_file(client, local_path, remote_path)
            _, _, cmd_status = run_command(client, "systemctl daemon-reload")
            if cmd_status == 0:
                print_success("systemd守护进程配置完成\n")
            else:
                print_error("systemd守护进程配置失败")

        if confirm_yes_no("是否配置systemd守护进程自启？"):
            run_command_live(client, "systemctl enable supervisord")
            print_success("systemd守护进程自启配置完成\n")

        if confirm_yes_no("是否启动Supervisord服务？"):
            run_command_live(client, "systemctl start supervisord")
            print_success("Supervisord服务启动完成\n")
            current_version, _, status = run_command(client, r'supervisord -v 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
            current_version = current_version.strip() if current_version else ""
        print_info("安装完成！当前supervisor版本：" + current_version)

    else:
        print_warning(f"返回上一级菜单")
    return None

def manage_supervisor(client):
    global stable_version
    run_command(client, "dnf install pip -y")
    current_version, _, _ = run_command(client, r'supervisord --version 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    current_version = current_version.strip() if current_version else ""
    stable_version, _, _ = run_command(client, r'pip index versions supervisor 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    print_info("Supervisor最新稳定版为：" + stable_version)
    while True:
        if current_version == "":
            print("========== supervisor软件管理 ==========")
            print("1. 安装 supervisor 最新稳定版")
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', '0'], default="0")
            if choice == "1":
                install_supervisor(client)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
        else:
            print("Supervisor已安装，当前版本：" + current_version)
            break
