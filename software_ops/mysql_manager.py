import os
from random import choice
import re

import requests
from colorama import Fore

from utils.file_utils import download_file, upload_file, upload_file_with_vars
from utils.output import print_info, print_error, print_success, print_warning
from utils.ssh_utils import run_command, run_command_live


def get_stable_mysql():
    url = "https://dev.mysql.com/downloads/mysql/8.0.html"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"请求失败：{e}")
        return None

    match = re.search(r"MySQL Community Server\s+(8\.0\.\d+)", response.text, re.DOTALL)

    if not match:
        print("未找到 Stable version 信息")
        return None

    return match.group(1)

def install_mysql8(client):
    stable_version = get_stable_mysql()
    print_info("Mysql最新发行版为：" + stable_version)
    choice = input(Fore.MAGENTA + f"是否安装？(y/N): ").strip().lower()
    if choice == "y":
        # 提示输入MySQL安装目录
        default_install_path = "/usr/local/mysql" + '.'.join(stable_version.split('.')[:2])
        install_path = input(Fore.MAGENTA + f"请输入MySQL安装目录 (默认: {default_install_path}): ").strip()
        if not install_path:
            install_path = default_install_path
        print_info("MySQL将安装到: " + install_path + "\n")
        
        # 提示输入数据目录
        default_data_dir = "/data/mysql"
        data_dir = input(Fore.MAGENTA + f"请输入MySQL数据目录 (默认: {default_data_dir}): ").strip()
        if not data_dir:
            data_dir = default_data_dir
        print_info("MySQL数据目录: " + data_dir)
        
        # 提示输入日志目录
        default_log_dir = "/var/log/mysql"
        log_dir = input(Fore.MAGENTA + f"请输入MySQL日志目录 (默认: {default_log_dir}): ").strip()
        if not log_dir:
            log_dir = default_log_dir
        print_info("MySQL日志目录: " + log_dir + "\n")
        
        print_info("开始安装Mysql " + stable_version + "......\n")

        print_info("创建mysql用户")
        output, status = run_command_live(client, "getent group mysql || groupadd mysql")
        output, status = run_command_live(client, "id mysql &>/dev/null || useradd -r -g mysql mysql -s /sbin/nologin")
        print_success("创建mysql用户完成。\n")

        print_info("创建数据和日志目录")
        output, status = run_command_live(client, f"mkdir -p {data_dir} && chown -R mysql:mysql {data_dir}")
        output, status = run_command_live(client, f"mkdir -p {log_dir} && chown -R mysql:mysql {log_dir}")
        print_success("创建数据和日志目录完成。\n")

        print_info("开始下载源码包并安装")
        local_path = os.path.join("packages", "mysql-" + stable_version + "-linux-glibc2.28-x86_64.tar.xz")
        url = "https://dev.mysql.com/get/Downloads/MySQL-8.0/mysql-" + stable_version + "-linux-glibc2.28-x86_64.tar.xz"
        remote_path = "/usr/local/src/mysql-" + stable_version + "-linux-glibc2.28-x86_64.tar.xz"

        try:
            download_file(url, local_path)
        except RuntimeError as e:
            print_error(f"下载失败，中止安装: {e}")
            print_warning("返回上一级菜单\n")
            return None
        upload_file(client, local_path, remote_path)
        cmds = [
            "tar xvf " + remote_path + " -C /usr/local/src/",
            "mv /usr/local/src/mysql-" + stable_version + "-linux-glibc2.28-x86_64 " + install_path,
            "chown -R mysql:mysql " + install_path,
            "printf '\nPATH=$PATH:" + install_path + "/bin\nexport PATH\n' >> /etc/profile",
            "source /etc/profile",
        ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        if cmd_status == 0:
            current_version, _, _ = run_command(client, r'mysql -V | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
            print_info("\n安装完成！\n当前mysql版本：" + current_version)
            
            choice = input(Fore.MAGENTA + f"是否自动配置my.cnf文件？(y/N): ").strip().lower()
            if choice == "y":
                local_path = os.path.join("config", "my.cnf")
                remote_path = "/etc/my.cnf"
                upload_file_with_vars(client, local_path, remote_path, {'MYSQL_INSTALL_PATH': install_path, 'MYSQL_DATA_DIR': data_dir, 'MYSQL_LOG_DIR': log_dir})
                cmd = "chown mysql:mysql /etc/my.cnf"
                run_command_live(client, cmd)
                print_info("my.cnf文件调整完成，建议首次初始化之前根据实际需求修改my.cnf文件！！！\n\n")
            else:
                print_warning("返回上一级")

            choice = input(Fore.MAGENTA + f"是否初始化MySQL服务？(y/N): ").strip().lower()
            # TODO: 优化输出选择信息之后的提示信息颜色显示
            if choice == "y":
                run_command_live(client, install_path + "/bin/mysqld --initialize --user=mysql")
                print_info("MySQL服务初始化完成\n\n")
            else:
                print_warning("返回上一级")

            choice = input(Fore.MAGENTA + f"是否配置systemd守护进程？(y/N): ").strip().lower()
            if choice == "y":
                local_path = os.path.join("config", "mysqld.service")
                remote_path = "/etc/systemd/system/mysqld.service"
                upload_file_with_vars(client, local_path, remote_path, {'MYSQL_INSTALL_PATH': install_path, 'MYSQL_LOG_DIR': log_dir})
                run_command_live(client, "systemctl daemon-reload")
                print_info("systemd守护进程配置完成\n\n")
            else:
                print_warning("返回上一级")

            choice = input(Fore.MAGENTA + f"是否为MySQL服务配置开机自启动？(y/N): ").strip().lower()
            if choice == "y":
                run_command_live(client, "systemctl enable mysqld")
                print_info("MySQL服务配置开机自启动完成\n\n")
            else:
                print_warning("返回上一级")

            choice = input(Fore.MAGENTA + f"是否启动MySQL服务？(y/N): ").strip().lower()
            if choice == "y":
                _, status = run_command_live(client, "systemctl start mysqld")
                if status != 0:
                    print_error("\nMySQL服务启动失败！\n")
                else:
                    default_password, _, _ = run_command(client, "grep -a \"A temporary password is generated\" /var/log/mysql/mysqld-error.log | tail -n1 | awk '{print $NF}'")
                    print_info("MySQL服务启动成功！请手动连接MySQL并修改初始root密码！\n")
                    print_info("默认root密码为：" + default_password + "\n")
            else:
                print_warning("返回上一级")

    else:
        print_warning(f"返回上一级")

    return None

def upgrade_mysql8(client):
    stable_version = get_stable_mysql()
    print_info("开始升级 Mysql 到最新发行版 " + stable_version + "......\n")

    # 获取当前MySQL安装路径
    current_mysql_path, _, _ = run_command(client, "which mysql")
    install_path = current_mysql_path.replace("/bin/mysql", "")
    choice = input("当前MySQL安装路径: " + install_path + "\n是否继续升级？(y/N): ").strip().lower()
    if choice != "y":
        print_warning("返回上一级菜单\n")
        return None

    print_info("开始下载源码包并编译安装")
    local_path = os.path.join("packages", "mysql-" + stable_version + ".tar.gz")
    url = "https://dev.mysql.com/get/Downloads/MySQL-8.0/mysql-" + stable_version + "-linux-glibc2.28-x86_64.tar.xz"
    remote_path = "/usr/local/src/mysql-" + stable_version + ".tar.gz"

    try:
        download_file(url, local_path)
    except RuntimeError as e:
        print_error(f"下载失败，中止升级: {e}")
        print_warning("返回上一级菜单\n")
        return None
    upload_file(client, local_path, remote_path)
    cmds = [
        "tar zxf " + remote_path + " -C /usr/local/src/",
        "cd /usr/local/src/mysql-" + stable_version + "&& ./configure --prefix=" + install_path + " --with-http_stub_status_module --with-http_gzip_static_module --with-http_realip_module --with-http_sub_module --with-http_ssl_module --with-http_v2_module --with-stream",
        "cd /usr/local/src/mysql-" + stable_version + "&& make && make install",
        "ln -fs " + install_path + "/sbin/mysql /usr/bin/mysql"
    ]

    cmd_status = 0
    for cmd in cmds:
        output, cmd_status = run_command_live(client, cmd)
        if cmd_status != 0 :
            print_error(f"\n命令执行失败: {cmd}")
            print_warning("中止当前操作，返回上一级菜单\n")
            break

    if cmd_status == 0:
        _, current_version, _ = run_command(client, r'mysql -v')
        print_info("\n升级已完成！\n请在非业务高峰期手动重启mysql")

def manage_mysql(client):
    current_version, _, _ = run_command(client, r'mysql -V | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    while True:
        print("=== Mysql软件管理 ===")
        print("1. 安装 Mysql 8.0 最新发行版")
        print("0. 返回/跳过")
        choice = input("请选择操作编号: ").strip()
        if choice == "1":
            install_mysql8(client)
        elif choice == "0":
            break
        else:
            print("无效选项，请重新输入")
        # if not current_version or "未找到" in current_version or "not found" in current_version:
        #     print("1. 安装 Mysql 8.0 最新发行版")
        #     print("0. 返回/跳过")
        #     choice = input("请选择操作编号: ").strip()
        #     if choice == "1":
        #         install_mysql8(client)
        #     elif choice == "0":
        #         break
        #     else:
        #         print("无效选项，请重新输入")
        # else:
        #     print_success("当前Mysql版本：" + current_version)
        #     stable_version = get_stable_mysql()
        #     print_info("Mysql最新发行版为：" + stable_version)
        #     print("1. 升级 Mysql 到最新发行版")
        #     print("0. 返回/跳过")
        #     choice = input("请选择操作编号: ").strip()
        #     if choice == "1":
        #         upgrade_mysql8(client)
        #     elif choice == "0":
        #         break
        #     else:
        #         print("无效选项，请重新输入")