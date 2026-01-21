import os

from colorama import Fore

from utils.file_utils import get_stable_version, download_file, upload_file, upload_file_with_vars
from utils.output import print_info, print_error, print_warning, print_success
from utils.ssh_utils import run_command, run_command_live
from utils.choice import confirm_yes_no, menu_choice


def install_prometheus(client):
    currrent_version_output,_ , _ = run_command(client, r"prometheus --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1")
    if currrent_version_output != "":
        print_success("Prometheus已安装。\n")
        print_info(f"当前Prometheus版本: {currrent_version_output.strip()}\n")
        return None
    else:
        pass
    stable_version = get_stable_version("https://api.github.com/repos/prometheus/prometheus/tags?page=1&per_page=5")
    print_info("Prometheus最新发行版为：" + stable_version)
    if not confirm_yes_no("是否安装？", default=False):
        print_warning("→ 已跳过安装")
        return None
    default_install_path = "/usr/local/prometheus" + '.'.join(stable_version.split('.')[:2])
    install_path = input(Fore.MAGENTA + f"请输入Prometheus安装目录 (默认: {default_install_path}): ").strip()
    if not install_path:
        install_path = default_install_path
    print_info("Prometheus将安装到: " + install_path + "\n")
    
    default_data_dir = "/data/prometheus"
    data_dir = input(Fore.MAGENTA + f"请输入Prometheus数据目录 (默认: {default_data_dir}): ").strip()
    if not data_dir:
        data_dir = default_data_dir
    print_info("Prometheus数据目录: " + data_dir)

    print_info("开始安装Prometheus " + stable_version + "......\n")

    print_info("检查GO语言环境......")
    go_version_output,error , go_version_status = run_command(client, "go version")
    if go_version_status == 0:
        print_success("GO语言环境已存在。\n")
        print_info(f"当前Go版本: {go_version_output.strip()}\n")
    else:
        print_info("GO语言环境不存在，开始安装")
        output, status = run_command_live(client, "yum install -y go")
        if status == 0:
            print_success("GO语言环境安装完成。\n")
            go_version_output,_ , go_version_status = run_command(client, "go version")
            print_info(f"当前Go版本: {go_version_output.strip()}\n")
        else:
            print_error("GO语言环境安装失败，中止安装")
            return None

    print_info("开始下载Prometheus最新发行版")
    local_path = os.path.join("packages", "prometheus-" + stable_version + ".linux-amd64.tar.gz")
    url = "https://github.com/prometheus/prometheus/releases/download/v" + stable_version + "/prometheus-" + stable_version + ".linux-amd64.tar.gz"
    remote_path = "/usr/local/src/prometheus-" + stable_version + ".linux-amd64.tar.gz"

    wget_cmd = f"cd /usr/local/src && wget {url}"
    _, wget_status = run_command_live(client, wget_cmd)
    
    if wget_status != 0:
        print_warning("下载失败，尝试本地上传")
        try:
            download_file(url, local_path)
            upload_file(client, local_path, remote_path)
            print_success("本地上传成功")
        except RuntimeError as e:
            print_error(f"本地上传失败，中止安装: {e}")
            print_warning("返回上一级菜单\n")
            return None

    cmds = [
        "tar zxf " + remote_path + " -C /usr/local/src/",
        "mv /usr/local/src/prometheus-" + stable_version + ".linux-amd64 " + install_path,
        "ln -fs " + install_path + "/prometheus /usr/local/bin/prometheus",
        "ln -fs " + install_path + "/promtool /usr/local/bin/promtool"
    ]

    cmd_status = 0
    for cmd in cmds:
        _, _, cmd_status = run_command(client, cmd)
        if cmd_status != 0 :
            print_error(f"\n命令执行失败: {cmd}")
            print_warning("中止当前操作，返回上一级菜单\n")
            break

    if cmd_status == 0:
        if confirm_yes_no("是否配置systemd守护进程？", default=False):
            local_path = os.path.join("config", "prometheus", "prometheus.service")
            remote_path = "/etc/systemd/system/prometheus.service"
            run_command(client, "mkdir -p /data/prometheus")
            upload_file_with_vars(client, local_path, remote_path, {'PROMETHEUS_INSTALL_PATH': install_path, 'PROMETHEUS_DATA_PATH': data_dir})
            run_command(client, "systemctl daemon-reload")
            print_success("✓ systemd守护进程配置完成\n")
        else:
            print_warning("→ 已跳过systemd守护进程配置\n")

        if confirm_yes_no("是否配置开机自启动？", default=False):
            run_command(client, "systemctl enable prometheus")
            print_success("✓ 开机自启动配置完成")
        else:
            print_warning("→ 已跳过开机自启动配置")

        if confirm_yes_no("是否启动Prometheus服务？", default=False):
            run_command(client, "systemctl start prometheus")
            print_success("✓ Prometheus服务启动完成")
        else:
            print_warning("→ 已跳过Prometheus服务启动")
            
        print_info("\n安装完成！")

    else:
        print_warning(f"返回上一级")

    return None

def manage_prometheus(client):
    install_prometheus(client)