import os
import shlex
from getpass import getpass

from colorama import Fore

from utils.file_utils import get_stable_version, download_file, upload_file, upload_file_with_vars, remote_download_or_upload
from utils.output import print_info, print_error, print_warning, print_success
from utils.ssh_utils import run_command, run_command_live
from utils.server_utils import is_valid_ip
from utils.choice import confirm_yes_no


DEFAULT_EXPORTER_PORT = 9104
INSTALL_DIR = "/usr/local/mysqld-exporter"
SERVICE_NAME = "mysqld-exporter"


def install_mysqld_exporter(client):
    status, stable_version = get_stable_version("https://api.github.com/repos/prometheus/mysqld_exporter/tags?page=1&per_page=5")
    if status != 0:
        print_error("✗ 获取mysqld_exporter最新版本失败，无法继续安装")
        print_warning(stable_version)
        return None

    installed_output, _, _ = run_command(client, f"{INSTALL_DIR}/mysqld_exporter --version 2>/dev/null | head -n 1 | awk '{{print $3}}'")
    if installed_output:
        print_success("mysqld_exporter已安装。")
        print_info(f"当前版本信息: {installed_output.strip()}\n")
        print_warning("→ 已跳过安装")
        return None

    print_info("mysqld_exporter最新发行版为：" + stable_version)
    if confirm_yes_no("是否安装？", default=False):
        print_info("开始安装mysqld_exporter " + stable_version + "......")

        install_dir_exists, _, _ = run_command(client, f"test -d {INSTALL_DIR} && echo 'exists'")
        if install_dir_exists:
            print_warning("→ 安装目录已存在，请确认并清理后重试")
            return None

        local_path = os.path.join("packages", "mysqld_exporter-" + stable_version + ".linux-amd64.tar.gz")
        url = "https://github.com/prometheus/mysqld_exporter/releases/download/v" + stable_version + "/mysqld_exporter-" + stable_version + ".linux-amd64.tar.gz"
        remote_path = "/usr/local/src/mysqld_exporter-" + stable_version + ".linux-amd64.tar.gz"

        cmds = []
        if not install_dir_exists:
            wget_cmd = f"cd /usr/local/src && wget {url}"
            if not remote_download_or_upload(client, url, local_path, remote_path, wget_cmd, "远程下载或本地下载均失败，请检查网络连接后重试"):
                return None
                    
            cmds = [
                "tar zxf " + remote_path + " -C /usr/local/src/",
                "cp -a /usr/local/src/mysqld_exporter-" + stable_version + ".linux-amd64 " + INSTALL_DIR
            ]

        cmd_status = 0
        for cmd in cmds:
            _, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        if cmd_status == 0:
            print_info("\n请在需要监控的数据库创建mysqld_exporter用户并赋予权限\n示例：\nCREATE USER 'mysqld_exporter'@'%' IDENTIFIED BY '123@bCD' WITH MAX_USER_CONNECTIONS 3;\nGRANT PROCESS, REPLICATION CLIENT, SELECT ON *.* TO 'mysqld_exporter'@'%';\nFLUSH PRIVILEGES;\n")
            db_host = input(Fore.MAGENTA + "请输入数据库地址：").strip()
            while not is_valid_ip(db_host):
                print_error("请填写正确的IP地址！")
                db_host = input(Fore.MAGENTA + "请输入数据库地址：").strip()
            print_info("数据库地址为：" + db_host)
            db_port = input(Fore.MAGENTA + "请输入数据库端口 (默认: 3306)：").strip() or str(3306)
            db_username = input(Fore.MAGENTA + "请输入刚刚创建的数据库用户：").strip()
            db_password = getpass(Fore.MAGENTA + "请输入数据库密码：").strip()
            while not db_password:
                print_error("数据库密码不能为空！")
                db_password = getpass(Fore.MAGENTA + "请输入数据库密码：").strip()
            exporter_port = DEFAULT_EXPORTER_PORT
            while True:
                port_check, _, _ = run_command(client, f"ss -tlnp 2>/dev/null | grep :{exporter_port} || netstat -tlnp 2>/dev/null | grep :{exporter_port}")
                if port_check:
                    exporter_port = input(Fore.MAGENTA + f"检测到端口 {exporter_port} 已被占用，请输入新的mysqld_exporter监听端口：").strip()
                else:
                    print_info(f"将使用 {exporter_port} 端口进行安装")
                    break

            variables = {
                "db_host": db_host,
                "db_port": db_port,
                "db_username": db_username,
                "db_password": db_password,
                "EXPORTER_PORT": exporter_port,
            }
            local_path = os.path.join("config", "prometheus", "mysqld_exporter.conf")
            remote_path = INSTALL_DIR + "/mysqld_exporter.conf"
            upload_file_with_vars(client, local_path, remote_path, variables)
            run_command(client, f"chmod 600 {remote_path}")

            local_path = os.path.join("config", "prometheus", "mysqld-exporter.service")
            remote_path = f"/etc/systemd/system/{SERVICE_NAME}.service"
            upload_file_with_vars(client, local_path, remote_path, variables)
            run_command(client, f"systemctl daemon-reload && systemctl enable --now {SERVICE_NAME}")

            # 检查服务状态
            print_info("\n正在检查mysqld-exporter服务状态...")
            out, err, _ = run_command(client, f"systemctl is-active {SERVICE_NAME}")
            if out.strip() == "active":
                print_success("✓ mysqld-exporter服务已成功启动并运行")
                # 检查端口是否监听
                _, _, port_code = run_command(client, f"ss -tlnp 2>/dev/null | grep :{exporter_port} || netstat -tlnp 2>/dev/null | grep :{exporter_port}")
                if port_code == 0:
                    print_success(f"✓ mysqld-exporter端口{exporter_port}正在监听")
                else:
                    print_warning(f"⚠ mysqld-exporter端口{exporter_port}未检测到监听")
            else:
                print_error("✗ mysqld-exporter服务启动失败")
                if err:
                    print_error(f"错误信息: {err.strip()}")

            print_info("\n安装完成！")

    else:
        print_warning(f"返回上一级")

    return None


def manage_mysql_exporter(client):
    install_mysqld_exporter(client)
