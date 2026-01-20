import os
from colorama import Fore

from utils.file_utils import download_file, upload_file, get_latest_version
from utils.output import print_info, print_error, print_warning
from utils.ssh_utils import run_command, run_command_live
from utils.choice import confirm_yes_no

def install_docker(client):
    print_info("docker最新发行版为：" + latest_version)
    if confirm_yes_no("是否安装？", default=False):
        print_info("开始安装docker " + latest_version + "......\n")

        print_info("开始下载源码包并编译安装")
        url = "https://download.docker.com/linux/static/stable/x86_64/docker-" + latest_version + ".tgz"
        local_path = os.path.join("packages", "docker-" + latest_version + ".tgz")
        remote_path = "/usr/local/src/docker-" + latest_version + ".tgz"

        wget_cmd = f"cd /usr/local/src && wget {url}"
        _, wget_status = run_command_live(client, wget_cmd)
        
        if wget_status == 0:
            pass
        else:
            print_warning("下载失败，尝试本地上传")
            try:
                download_file(url, local_path)
                upload_file(client, local_path, remote_path)
                print_info("本地上传成功")
            except RuntimeError as e:
                print_error(f"本地上传也失败，中止安装: {e}")
                print_warning("返回上一级菜单\n")
                return None
                
        cmds = [
            "tar zxf " + remote_path + " -C /usr/local/src/",
            "cp /usr/local/src/docker/* /usr/bin/",
        ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        # TODO 调整修复docker部署
        if confirm_yes_no("是否配置systemd守护进程？", default=False):
            local_path = os.path.join("config", "docker", "docker.service")
            remote_path = "/etc/systemd/system/docker.service"
            upload_file(client, local_path, remote_path)
            local_path = os.path.join("config", "docker", "docker.socket")
            remote_path = "/etc/systemd/system/docker.socket"
            upload_file(client, local_path, remote_path)
            cmds = [
                "systemctl daemon-reload",
                "systemctl enable --now docker",
            ]
            print_info("systemd守护进程配置完成")
        print_info("安装完成！当前docker版本：" + current_version)

    else:
        print_warning(f"返回上一级")

    return None

def manage_docker(client):
    global current_version, status, latest_version
    current_version, _, status = run_command(client, r'docker -v 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    current_version = current_version.strip() if current_version else ""
    latest_version = get_latest_version("https://download.docker.com/linux/static/stable/x86_64/")
    print_info("Docker最新发行版为：" + latest_version)
    while True:
        print("=== docker软件管理 ===")
        if current_version == "":
            print("1. 安装 docker 最新发行版")
            print("0. 返回/跳过")
            choice = input("请选择操作编号: ").strip()
            if choice == "1":
                install_docker(client)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
        else:
            print("已安装docker，版本：" + current_version)
            break