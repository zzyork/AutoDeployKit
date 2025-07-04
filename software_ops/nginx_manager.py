import os
import re

import requests
from colorama import Fore
from packaging import version

from utils.file_utils import download_file, upload_file
from utils.output import print_info, print_error, print_success, print_warning
from utils.ssh_utils import run_command, run_command_live


def get_latest_nginx():
    url = "https://nginx.org/en/download.html"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"请求失败：{e}")
        return None

    # 匹配主版本，例如 nginx-1.24.0.tar.gz
    matches = re.findall(r'nginx-(\d+\.\d+\.\d+)\.tar\.gz', response.text)

    if not matches:
        print("未找到任何版本信息")
        return None

    # 排序获取最大版本
    from packaging import version
    latest = max(matches, key=lambda v: version.parse(v))
    return latest

def install_nginx(client):
    latest_version = get_latest_nginx()
    print_info("Nginx最新发行版为：" + latest_version)
    choice = input(Fore.MAGENTA + f"是否安装？(y/N): ").strip().lower()
    if choice == "y":
        print_info("安装Nginx " + latest_version)

        print_info("安装依赖")
        _, err, status = run_command(client, 'yum -y make zlib zlib-devel gcc-c++ libtool  openssl openssl-devel')
        if err:
            print_error("安装perl失败，报错信息：\n" + err)
            return None
        else:
            print_success("perl安装完成。")

        print_info("开始下载源码包并编译安装")
        local_path = os.path.join("packages", "openssl-" + latest_version + ".tar.gz")
        url = "https://github.com/openssl/openssl/releases/download/openssl-" + latest_version + "/openssl-" + latest_version + ".tar.gz"
        download_file(url, local_path)

        remote_path = "/usr/local/src/openssl-" + latest_version + ".tar.gz"
        upload_file(client, local_path, remote_path)
        cmds = [
            "tar zxf " + remote_path + " -C /usr/local/src/",
            "cd /usr/local/src/openssl-" + latest_version + "&& ./config --prefix=/usr/local/openssl3.0 no-zlib",
            "cd /usr/local/src/openssl-" + latest_version + "&& make && make install",
            "mv /usr/bin/openssl /usr/bin/openssl.bak",
            "mv /usr/include/openssl /usr/include/openssl.bak",
            "ln -s /usr/local/openssl3.0/bin/openssl /usr/bin/openssl",
            "ln -s /usr/local/openssl3.0/include/openssl /usr/include/openssl",
            "echo \"/usr/local/openssl3.0/lib\" >> /etc/ld.so.conf",
            "ldconfig -v"
        ]

        for cmd in cmds:
            run_command_live(client, cmd)

        current_version, _, _ = run_command(client, 'openssl version')
        print_info("\n安装完成！\n当前OpenSSL版本：" + current_version)
    else:
        print_warning(f"返回上一级")

    return None

def nginx_manager(client):
    current_version, _, _ = run_command(client, 'openssl version')
    print_info("\n当前OpenSSL版本：" + current_version)

    while True:
        print("=== 安全补丁升级操作 ===")
        print("1. 升级 OpenSSL 到 v3.0.* 最新发行版")
        print("0. 返回/跳过")
        choice = input("请选择操作编号: ").strip()
        if choice == "1":
            nginx_install(client)
        elif choice == "0":
            break
        else:
            print("无效选项，请重新输入")