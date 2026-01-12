import os
import re

import requests
from colorama import Fore

from utils.file_utils import download_file, upload_file, upload_file_with_vars
from utils.output import print_info, print_error, print_success, print_warning
from utils.ssh_utils import run_command, run_command_live


def get_stable_docker():
    """
    从 https://download.docker.com/linux/static/stable/x86_64/ 页面抓取所有 SkyWalking APM 的 tar.gz 包链接，
    提取所有版本号，返回最大版本号。
    """
    import requests
    import re
    from packaging import version

    url = "https://download.docker.com/linux/static/stable/x86_64/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"请求失败：{e}")
        return None

    # 匹配所有 Docker 包链接
    pattern = r"docker-(\d+.\d+.\d+).tgz"
    versions = re.findall(pattern, response.text)
    if not versions:
        print("未找到 Docker 包")
        return None

    # 取最大版本
    max_version = max(versions, key=version.parse)
    return max_version

def install_docker(client):
    stable_version = get_stable_docker()
    print_info("docker最新发行版为：" + stable_version)
    choice = input(Fore.MAGENTA + f"是否安装？(y/N): ").strip().lower()
    if choice == "y":
        print_info("开始安装docker " + stable_version + "......\n")

        print_info("开始下载源码包并编译安装")
        url = "https://download.docker.com/linux/static/stable/x86_64/docker-" + stable_version + ".tgz"
        local_path = os.path.join("packages", "docker-" + stable_version + ".tgz")
        remote_path = "/usr/local/src/docker-" + stable_version + ".tgz"

        try:
            download_file(url, local_path)
        except RuntimeError as e:
            print_error(f"下载失败，中止安装: {e}")
            print_warning("返回上一级菜单\n")
            return None
        upload_file(client, local_path, remote_path)
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

        if cmd_status == 0:
            _, current_version, _ = run_command(client, 'docker version')
            print_info("\n安装完成！\n当前docker版本：" + current_version)
            choice = input(Fore.MAGENTA + f"是否配置systemd守护进程？(y/N): ").strip().lower()
            if choice == "y":
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

    else:
        print_warning(f"返回上一级")

    return None

def manage_docker(client):
    _, current_version, status = run_command(client, 'docker -v')
    while True:
        print("=== docker软件管理 ===")
        if status != 0:
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
            print("已安装docker，版本：current_version")
            break