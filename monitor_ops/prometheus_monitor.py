import os

from colorama import Fore

from utils.file_utils import get_stable_version_from_github, download_file, upload_file, upload_file_with_vars
from utils.output import print_info, print_error, print_warning
from utils.ssh_utils import run_command, run_command_live
from utils.server_utils import is_valid_ip


def install_prometheus(client):
    url = "https://api.github.com/repos/prometheus/prometheus/tags?page=1&per_page=5"
    stable_version = get_stable_version_from_github(url)
    print_info("prometheus最新发行版为：" + stable_version)
    choice = input(Fore.MAGENTA + f"是否安装？(y/N): ").strip().lower()
    if choice == "y":
        print_info("开始安装prometheus " + stable_version + "......\n")

        print_info("开始下载")
        local_path = os.path.join("packages", "prometheus-" + stable_version + ".linux-amd64.tar.gz")
        url = "https://github.com/prometheus/prometheus/releases/download/v" + stable_version + "/prometheus-" + stable_version + ".linux-amd64.tar.gz"
        remote_path = "/usr/local/src/prometheus-" + stable_version + ".linux-amd64.tar.gz"

        try:
            download_file(url, local_path)
        except RuntimeError as e:
            print_error(f"下载失败，中止安装: {e}")
            print_warning("返回上一级菜单\n")
            return None
        upload_file(client, local_path, remote_path)
        cmds = [
            "tar zxf " + remote_path + " -C /usr/local/src/",
            "mv /usr/local/src/prometheus-" + stable_version + ".linux-amd64 /usr/local/prometheus"
        ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        if cmd_status == 0:
            local_path = os.path.join("config", "prometheus.service")
            remote_path = "/etc/systemd/system/prometheus.service"
            run_command(client, "mkdir -p /data/prometheus")
            upload_file(client, local_path, remote_path)
            run_command(client, "systemctl daemon-reload && systemctl enable --now prometheus")

            ## TODO： 待添加安装完成之后的服务状态展示以及prometheus配置更新功能

            print_info("\n安装完成！")

    else:
        print_warning(f"返回上一级")

    return None

def manage_prometheus(client):
    install_prometheus(client)