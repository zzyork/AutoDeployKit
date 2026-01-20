# server_ops/openssl_upgrade.py
import os

from colorama import Fore

from utils.ssh_utils import run_command_live, run_command
from utils.output import print_info, print_success, print_warning, print_error
from utils.file_utils import download_file, upload_file, get_latest_version
from utils.choice import confirm_yes_no, menu_choice
import requests
import re
from packaging import version

def upgrade_openssl_1_1_1(client):
    print_info("升级 OpenSSL 到 1.1.1w")

    print_info("安装perl依赖")
    _, err, status = run_command(client, 'yum -y install perl')
    if err:
        print_error("安装perl失败，报错信息：\n" + err)
        return None
    else:
        print_success("perl安装完成。")

    print_info("上传源码包并开始编译安装")

    remote_pkg_path = "/usr/local/src/openssl-1.1.1w.tar.gz"

    local_pkg_path = os.path.join("packages", "openssl-1.1.1w.tar.gz")
    upload_file(client, local_pkg_path, remote_pkg_path)
    cmds = [
        "tar zxf /usr/local/src/openssl-1.1.1w.tar.gz -C /usr/local/src/",
        "cd /usr/local/src/openssl-1.1.1w && ./config --prefix=/usr/local/openssl1.1 no-zlib",
        "cd /usr/local/src/openssl-1.1.1w && make && make install",
        "mv /usr/bin/openssl /usr/bin/openssl.bak",
        "mv /usr/include/openssl /usr/include/openssl.bak",
        "ln -s /usr/local/openssl1.1/bin/openssl /usr/bin/openssl",
        "ln -s /usr/local/openssl1.1/include/openssl /usr/include/openssl",
        "ln -s /usr/local/openssl1.1/lib/libssl.so.1.1 /usr/local/lib64/libssl.so",
        "echo '/usr/local/openssl1.1/lib' >> /etc/ld.so.conf",
        "ldconfig -v",
    ]

    for cmd in cmds:
        run_command_live(client, cmd)

    current_version, _, _ = run_command(client, 'openssl version')
    current_version = current_version.strip() if current_version else ""
    print_info("\n安装完成！\n当前OpenSSL版本：" + current_version)

    return None

def upgrade_openssl_v3(client):
    if confirm_yes_no("是否升级？", default=False):
        print_info("升级 OpenSSL 到 " + latest_version)

        print_info("安装perl依赖")
        _, status = run_command_live(client, 'yum -y install perl')
        print_success("perl安装完成。")

        print_info("开始下载源码包并编译安装")
        local_path = os.path.join("packages", "openssl-" + latest_version + ".tar.gz")
        url = "https://github.com/openssl/openssl/releases/download/openssl-" + latest_version + "/openssl-" + latest_version + ".tar.gz"
        try:
            download_file(url, local_path)
        except RuntimeError as e:
            print_error(f"下载失败，中止升级: {e}")
            print_warning("返回上一级菜单\n")
            return None

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
        current_version = current_version.strip() if current_version else ""
        print_info("\n安装完成！\n当前OpenSSL版本：" + current_version)
    else:
        print_warning(f"返回上一级")

    return None

def fix_libssl_so3(client):
    print_info("开始修复 libssl.so.3 缺失问题")
    cmds = [
        "ln -sf /usr/local/openssl3.0/lib64/libssl.so.3 /usr/lib64/libssl.so.3",
        "ln -sf /usr/local/openssl3.0/lib64/libcrypto.so.3 /usr/lib64/libcrypto.so.3"
    ]
    for cmd in cmds:
        run_command_live(client, cmd)
    print_info("已修复完成")

def install_perl_cpan(client):
    print_info("安装 perl-CPAN 模块以解决 IPC/Cmd.pm 缺失")
    cmds = [
        "yum install -y perl-CPAN",
        "echo 'yes\nmanual\nyes\ninstall IPC::Cmd\n' | perl -MCPAN -e shell"
    ]
    for cmd in cmds:
        run_command_live(client, cmd)

def manage_ssl(client):
    global current_version, latest_version
    current_version, _, _ = run_command(client, 'openssl version')
    current_version = current_version.strip() if current_version else ""
    print_info("当前OpenSSL版本：" + current_version)
    if current_version.startswith("OpenSSL 1.1.1"):
        latest_version = get_latest_version("https://api.github.com/repos/openssl/openssl/tags?page=1&per_page=50", "1.1.1")
    elif current_version.startswith("OpenSSL 3.0"):
        latest_version = get_latest_version("https://api.github.com/repos/openssl/openssl/tags?page=1&per_page=50", "3.0")
    if not latest_version:
        print_error("获取最新版本失败，中止升级")
        return None
    print_info("OpenSSL 最新版本：" + latest_version)

    while True:
        print("=== OpenSSL升级操作 ===")
        if current_version.startswith("OpenSSL 1.1.1"):
            print("1. 升级 OpenSSL 到 1.1.1w")
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', '0'], default="0")
        elif current_version.startswith("OpenSSL 3.0"):
            print("1. 升级 OpenSSL 到 v3.0.* 最新发行版")
            print("2. 修复 libssl.so.3 缺失问题")
            print("3. 安装 perl-CPAN（解决 IPC/Cmd.pm 缺失）")
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', '2', '3', '0'], default="0")
        if choice == "1":
            if current_version.startswith("OpenSSL 1.1.1"):
                upgrade_openssl_1_1_1(client)
            elif current_version.startswith("OpenSSL 3.0"):
                upgrade_openssl_v3(client)
        elif choice == "2":
            fix_libssl_so3(client)
        elif choice == "3":
            install_perl_cpan(client)
        elif choice == "0":
            break
        else:
            print("无效选项，请重新输入")
