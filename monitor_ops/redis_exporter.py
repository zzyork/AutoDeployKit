import os
import shlex
from getpass import getpass

from colorama import Fore

from utils.file_utils import get_stable_version, download_file, upload_file, upload_file_with_vars, remote_download_or_upload
from utils.output import print_info, print_error, print_warning, print_success
from utils.ssh_utils import run_command, run_command_live
from utils.server_utils import is_valid_ip
from utils.choice import confirm_yes_no


DEFAULT_EXPORTER_PORT = 9121
INSTALL_DIR = "/usr/local/redis-exporter"
SERVICE_NAME = "redis-exporter"


def install_redis_exporter(client):
    status, stable_version = get_stable_version("https://api.github.com/repos/oliver006/redis_exporter/tags?page=1&per_page=5")
    if status != 0:
        print_error("✗ 获取redis_exporter最新版本失败，无法继续安装")
        print_warning(stable_version)
        return None

    installed_output, _, _ = run_command(client, f"{INSTALL_DIR}/redis_exporter --version 2>/dev/null | head -n 1 | awk '{{print $3}}'")
    if installed_output:
        print_info("redis_exporter已安装。")
        print_info(f"当前版本信息: {installed_output.strip()}\n")
        print_warning("→ 已跳过安装")
        return None

    print_info("redis_exporter最新发行版为：" + stable_version)
    if confirm_yes_no("是否安装？", default=False):
        print_info("开始安装redis_exporter " + stable_version + "......")

        install_dir_exists, _, _ = run_command(client, f"test -d {INSTALL_DIR} && echo 'exists'")
        if install_dir_exists:
            print_warning("→ 安装目录已存在，请确认并清理后重试")
            return None

        local_path = os.path.join("packages", "redis_exporter-" + stable_version + ".linux-amd64.tar.gz")
        url = "https://github.com/oliver006/redis_exporter/releases/download/v" + stable_version + "/redis_exporter-v" + stable_version + ".linux-amd64.tar.gz"
        remote_path = "/usr/local/src/redis_exporter-" + stable_version + ".linux-amd64.tar.gz"

        cmds = []
        if not install_dir_exists:
            if not remote_download_or_upload(client, url, local_path, remote_path, failure_message="本地上传失败，中止安装"):
                return None
                    
            cmds = [
                "tar zxf " + remote_path + " -C /usr/local/src/",
                "cp -a /usr/local/src/redis_exporter-v" + stable_version + ".linux-amd64 " + INSTALL_DIR
            ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        if cmd_status == 0:
            print_info("\n请在需要监控的redis创建redis_exporter用户并赋予权限\n示例：\nCREATE USER 'redis_exporter'@'%' IDENTIFIED BY '123@bCD' WITH MAX_USER_CONNECTIONS 3;\nGRANT PROCESS, REPLICATION CLIENT, SELECT ON *.* TO 'redis_exporter'@'%';\nFLUSH PRIVILEGES;\n")
            REDIS_HOST = input(Fore.MAGENTA + "请输入redis地址：").strip()
            while not is_valid_ip(REDIS_HOST):
                print_error("请填写正确的IP地址！")
                REDIS_HOST = input(Fore.MAGENTA + "请输入redis地址：").strip()
            print_info("redis地址为：" + REDIS_HOST)
            REDIS_PORT = input(Fore.MAGENTA + "请输入redis端口 (默认: 6379)：").strip() or str(6379)
            REDIS_PASSWORD = getpass(Fore.MAGENTA + "请输入redis密码：").strip()
            while not REDIS_PASSWORD:
                print_error("redis密码不能为空！")
                REDIS_PASSWORD = getpass(Fore.MAGENTA + "请输入redis密码：").strip()
            exporter_port = DEFAULT_EXPORTER_PORT
            while True:
                port_check, _, _ = run_command(client, f"ss -tlnp 2>/dev/null | grep :{exporter_port} || netstat -tlnp 2>/dev/null | grep :{exporter_port}")
                if port_check:
                    exporter_port = input(Fore.MAGENTA + f"检测到端口 {exporter_port} 已被占用，请输入新的redis_exporter监听端口：").strip()
                else:
                    print_info(f"将使用 {exporter_port} 端口进行安装")
                    break

            variables = {
                "REDIS_HOST": REDIS_HOST,
                "REDIS_PORT": REDIS_PORT,
                "REDIS_PASSWORD": REDIS_PASSWORD,
                "EXPORTER_PORT": exporter_port,
            }

            local_path = os.path.join("config", "prometheus", "redis-exporter.service")
            remote_path = f"/etc/systemd/system/{SERVICE_NAME}.service"
            upload_file_with_vars(client, local_path, remote_path, variables)
            run_command(client, f"systemctl daemon-reload && systemctl enable --now {SERVICE_NAME}")

            # 检查服务状态
            print_info("\n正在检查redis-exporter服务状态...")
            out, err, _ = run_command(client, f"systemctl is-active {SERVICE_NAME}")
            if out.strip() == "active":
                print_success("✓ redis-exporter服务已成功启动并运行")
                # 检查端口是否监听
                _, _, port_code = run_command(client, f"ss -tlnp 2>/dev/null | grep :{exporter_port} || netstat -tlnp 2>/dev/null | grep :{exporter_port}")
                if port_code == 0:
                    print_success(f"✓ redis-exporter端口{exporter_port}正在监听")
                else:
                    print_warning(f"⚠ redis-exporter端口{exporter_port}未检测到监听")
            else:
                print_error("✗ redis-exporter服务启动失败")
                if err:
                    print_error(f"错误信息: {err.strip()}")

            print_info("\n安装完成！")

    else:
        print_warning(f"返回上一级")

    return None


def manage_redis_exporter(client):
    install_redis_exporter(client)
