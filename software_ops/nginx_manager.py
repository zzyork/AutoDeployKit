import os
import re

import requests
from colorama import Fore

from utils.file_utils import download_file, upload_file, upload_file_with_vars
from utils.output import print_info, print_error, print_success, print_warning
from utils.ssh_utils import run_command, run_command_live


def get_stable_nginx():
    url = "https://nginx.org/en/download.html"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"请求失败：{e}")
        return None

    # 正则匹配 “Stable version” 段落的版本号
    match = re.search(r'Stable version.*?nginx-(\d+\.\d+\.\d+)', response.text, re.DOTALL)

    if not match:
        print("未找到 Stable version 信息")
        return None

    return match.group(1)

def install_nginx(client):
    stable_version = get_stable_nginx()
    print_info("Nginx最新发行版为：" + stable_version)
    choice = input(Fore.MAGENTA + f"是否安装？(y/N): ").strip().lower()
    if choice == "y":
        print_info("开始安装Nginx " + stable_version + "......\n")

        print_info("创建nginx用户")
        _, err, status = run_command_live(client, "getent group nginx || groupadd nginx")
        _, err, status = run_command_live(client, "id nginx &>/dev/null || useradd -r -g nginx nginx")
        if err:
            print_error("创建nginx用户失败，报错信息：\n" + err)
            return None
        else:
            print_success("创建nginx用户完成。\n")

        print_info("安装依赖")
        _, err, status = run_command_live(client, 'yum -y install make zlib zlib-devel gcc-c++ libtool openssl-devel pcre-devel')
        if err:
            print_error("安装perl失败，报错信息：\n" + err)
            return None
        else:
            print_success("perl安装完成。\n")

        print_info("开始下载源码包并编译安装")
        local_path = os.path.join("packages", "nginx-" + stable_version + ".tar.gz")
        url = "https://nginx.org/download/nginx-" + stable_version + ".tar.gz"
        remote_path = "/usr/local/src/nginx-" + stable_version + ".tar.gz"
        install_path = "/usr/local/nginx" + '.'.join(stable_version.split('.')[:2])

        download_file(url, local_path)
        upload_file(client, local_path, remote_path)
        cmds = [
            "tar zxf " + remote_path + " -C /usr/local/src/",
            "cd /usr/local/src/nginx-" + stable_version + "&& ./configure --prefix=" + install_path + " --with-http_stub_status_module --with-http_gzip_static_module --with-http_realip_module --with-http_sub_module --with-http_ssl_module --with-http_v2_module --with-stream",
            "cd /usr/local/src/nginx-" + stable_version + "&& make && make install",
            "ln -fs " + install_path + "/sbin/nginx /usr/bin/nginx",
            "mkdir -p " + install_path + "/conf/conf.d",
        ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        if cmd_status == 0:
            _, current_version, _ = run_command_live(client, 'nginx -v')
            print_info("\n安装完成！\n当前nginx版本：" + current_version)
            choice = input(Fore.MAGENTA + f"是否自动调整nginx.conf文件？(y/N): ").strip().lower()
            if choice == "y":
                local_path = os.path.join("config", "nginx.conf")
                remote_path = install_path + "/conf/nginx.conf"
                upload_file(client, local_path, remote_path)
                cmds = [
                    "sed -i 's/${install_path}/" + install_path + "/g' " + remote_path,
                ]
                print_info("nginx.conf文件调整完成")
            choice = input(Fore.MAGENTA + f"是否配置systemd守护进程？(y/N): ").strip().lower()
            if choice == "y":
                local_path = os.path.join("config", "nginx.service")
                remote_path = "/etc/systemd/system/nginx.service"
                upload_file(client, local_path, remote_path)
                cmds = [
                    "sed -i 's/${install_path}/" + install_path + "/g' " + remote_path,
                    "systemctl daemon-reload",
                    "systemctl enable --now nginx",
                ]
                print_info("systemd守护进程配置完成")

    else:
        print_warning(f"返回上一级")

    return None

def upgrade_nginx(client):
    stable_version = get_stable_nginx()
    print_info("开始升级 Nginx 到最新发行版 " + stable_version + "......\n")

    print_info("开始下载源码包并编译安装")
    local_path = os.path.join("packages", "nginx-" + stable_version + ".tar.gz")
    url = "https://nginx.org/download/nginx-" + stable_version + ".tar.gz"
    remote_path = "/usr/local/src/nginx-" + stable_version + ".tar.gz"
    install_path = "/usr/local/nginx" + '.'.join(stable_version.split('.')[:2])

    download_file(url, local_path)
    upload_file(client, local_path, remote_path)
    cmds = [
        "tar zxf " + remote_path + " -C /usr/local/src/",
        "cd /usr/local/src/nginx-" + stable_version + "&& ./configure --prefix=" + install_path + " --with-http_stub_status_module --with-http_gzip_static_module --with-http_realip_module --with-http_sub_module --with-http_ssl_module --with-http_v2_module --with-stream",
        "cd /usr/local/src/nginx-" + stable_version + "&& make && make install",
        "ln -fs " + install_path + "/sbin/nginx /usr/bin/nginx"
    ]

    cmd_status = 0
    for cmd in cmds:
        output, cmd_status = run_command_live(client, cmd)
        if cmd_status != 0 :
            print_error(f"\n命令执行失败: {cmd}")
            print_warning("中止当前操作，返回上一级菜单\n")
            break

    if cmd_status == 0:
        _, current_version, _ = run_command(client, 'nginx -v')
        print_info("\n升级已完成！\n请在非业务高峰期手动重启nginx")

def manage_nginx(client):
    _, current_version, status = run_command(client, 'nginx -v')
    while True:
        print("=== Nginx软件管理 ===")
        if status != 0:
            print("1. 安装 Nginx 最新发行版")
            print("0. 返回/跳过")
            choice = input("请选择操作编号: ").strip()
            if choice == "1":
                install_nginx(client)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
        else:
            print_success("当前Nginx版本：" + current_version)
            stable_version = get_stable_nginx()
            print_info("Nginx最新发行版为：" + stable_version)
            print("1. 升级 Nginx 到最新发行版")
            print("0. 返回/跳过")
            choice = input("请选择操作编号: ").strip()
            if choice == "1":
                upgrade_nginx(client)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")