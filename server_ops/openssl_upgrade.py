# server_ops/security_patch_ops.py
import os

from colorama import Fore

from utils.ssh_utils import run_command_live, run_command
from utils.output import print_info, print_success, print_warning, print_error
from utils.file_utils import download_file, upload_file
import requests
import re
from packaging import version

def get_latest_openssl(prefix: str):
    tags = []
    url = f"https://api.github.com/repos/openssl/openssl/tags?page=1&per_page=50"
    response = requests.get(url)
    if response.status_code != 200:
        raise RuntimeError(f"GitHub API 请求失败: {response.status_code}")
    data = response.json()
    for tag in data:
        name = tag["name"].split("-")[-1]
        if name.startswith(prefix):
            ver_math = re.match(r"^(\d+\.\d+\.\d+)$", name)
            if ver_math:
                tags.append(name)

    if not tags:
        raise ValueError(f"未找到前缀为 {prefix} 的版本")

    # 使用 packaging.version 排序，返回最大值
    latest = max(tags, key=version.parse)
    return latest

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
    print_info("\n安装完成！\n当前OpenSSL版本：" + current_version)

    return None

def upgrade_openssl_v3(client):
    latest_version = get_latest_openssl(prefix="3.0.")
    print_info("OpenSSL 3.0.* 最新发行版为：" + latest_version)
    choice = input(Fore.MAGENTA + f"是否升级？(y/N): ").strip().lower()
    if choice == "y":
        print_info("升级 OpenSSL 到 " + latest_version)

        print_info("安装perl依赖")
        _, status = run_command_live(client, 'yum -y install perl')
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

def manage_security_patch(client):
    current_version, _, _ = run_command(client, 'openssl version')
    print_info("\n当前OpenSSL版本：" + current_version)

    while True:
        print("=== 安全补丁升级操作 ===")
        # print("1. 升级 OpenSSL 到 1.1.1w")
        print("1. 升级 OpenSSL 到 v3.0.* 最新发行版")
        # print("2. 修复 libssl.so.3 缺失问题")
        # print("3. 安装 perl-CPAN（解决 IPC/Cmd.pm 缺失）")
        print("0. 返回/跳过")
        choice = input("请选择操作编号: ").strip()
        if choice == "1":
        #     upgrade_openssl_1_1_1(client)
        # elif choice == "1":
            upgrade_openssl_v3(client)
        # elif choice == "2":
        #     fix_libssl_so3(client)
        # elif choice == "3":
        #     install_perl_cpan(client)
        elif choice == "0":
            break
        else:
            print("无效选项，请重新输入")
