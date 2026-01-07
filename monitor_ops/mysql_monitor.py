import os

from colorama import Fore

from utils.file_utils import get_stable_version_from_github, download_file, upload_file, upload_file_with_vars
from utils.output import print_info, print_error, print_warning
from utils.ssh_utils import run_command, run_command_live
from utils.server_utils import is_valid_ip


def install_mysqld_exporter(client):
    url = "https://api.github.com/repos/prometheus/mysqld_exporter/tags?page=1&per_page=5"
    stable_version = get_stable_version_from_github(url)
    print_info("mysqld_exporter最新发行版为：" + stable_version)
    choice = input(Fore.MAGENTA + f"是否安装？(y/N): ").strip().lower()
    if choice == "y":
        print_info("开始安装mysqld_exporter " + stable_version + "......\n")

        print_info("开始下载")
        local_path = os.path.join("packages", "mysqld_exporter-" + stable_version + ".linux-amd64.tar.gz")
        url = "https://github.com/prometheus/mysqld_exporter/releases/download/v" + stable_version + "/mysqld_exporter-" + stable_version + ".linux-amd64.tar.gz"
        remote_path = "/usr/local/src/mysqld_exporter-" + stable_version + ".linux-amd64.tar.gz"
        print(url)
        print(remote_path)

        try:
            download_file(url, local_path)
        except RuntimeError as e:
            print_error(f"下载失败，中止安装: {e}")
            print_warning("返回上一级菜单\n")
            return None
        upload_file(client, local_path, remote_path)
        cmds = [
            "tar zxf " + remote_path + " -C /usr/local/src/",
            "mv /usr/local/src/mysqld_exporter-" + stable_version + ".linux-amd64 /usr/local/mysqld-exporter"
        ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        if cmd_status == 0:
            print_info("\n请在需要监控的数据库创建mysqld_exporter用户并赋予权限\n示例：\nCREATE USER 'mysqld_exporter'@'%' IDENTIFIED BY '123@bCD' WITH MAX_USER_CONNECTIONS 3;\nGRANT PROCESS, REPLICATION CLIENT, SELECT ON *.* TO 'mysqld_exporter'@'%';\nFLUSH PRIVILEGES;\n")
            db_host = ""
            while db_host == "":
                db_host = input(Fore.MAGENTA + f"请输入数据库地址：").strip().lower()
                if is_valid_ip(db_host):
                    print_info(f"数据库地址为：" + db_host)
                else:
                    print_error("请填写正确的IP地址！")
            db_port = input(Fore.MAGENTA + f"请输入数据库端口：").strip().lower()
            db_username = input(Fore.MAGENTA + f"请输入刚刚创建的数据库用户：").strip().lower()
            db_password = input(Fore.MAGENTA + f"请输入数据库密码：").strip().lower()

            variables = {
                "db_host": db_host,
                "db_port": db_port,
                "db_username": db_username,
                "db_password": db_password
            }
            local_path = os.path.join("config", "mysqld_exporter.conf")
            remote_path = "/usr/local/mysqld-exporter/mysqld_exporter.conf"
            upload_file_with_vars(client, local_path, remote_path, variables)

            local_path = os.path.join("config", "mysqld-exporter.service")
            remote_path = "/etc/systemd/system/mysqld-exporter.service"
            upload_file(client, local_path, remote_path)
            run_command(client, "systemctl daemon-reload && systemctl enable --now mysqld-exporter")

            ## TODO： 待添加安装完成之后的服务状态展示以及prometheus配置更新功能

            print_info("\n安装完成！")

    else:
        print_warning(f"返回上一级")

    return None

def manage_mysql_monitor(client):
    install_mysqld_exporter(client)