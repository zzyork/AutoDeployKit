import os

from colorama import Fore

from utils.file_utils import get_stable_version, download_file, upload_file, upload_file_with_vars, remote_download_or_upload
from utils.output import print_info, print_error, print_warning, print_success
from utils.ssh_utils import run_command, run_command_live
from utils.choice import confirm_yes_no


DEFAULT_EXPORTER_PORT = 8100
INSTALL_DIR = "/usr/local/node-exporter"
SERVICE_NAME = "node-exporter"


def _path_exists(client, path):
    _, _, code = run_command(client, f"test -e {path}")
    return code == 0


def _get_installed_version(client):
    command = (
        f"if test -x {INSTALL_DIR}/node_exporter; then "
        f"{INSTALL_DIR}/node_exporter --version 2>&1 | head -n1; "
        "elif command -v node_exporter >/dev/null 2>&1; then "
        "node_exporter --version 2>&1 | head -n1; "
        "fi"
    )
    output, _, _ = run_command(client, command)
    return output.strip()


def _pick_listen_port(client, default_port=DEFAULT_EXPORTER_PORT):
    port = str(default_port)
    while True:
        _, _, code = run_command(client, f"ss -tln 2>/dev/null | grep -q ':{port} ' || netstat -tln 2>/dev/null | grep -q ':{port} '")
        if code != 0:
            return port
        port = input(Fore.MAGENTA + f"⚠ {port}端口被占用，请重新输入监听端口: ").strip()
        if not port.isdigit() or not (1 <= int(port) <= 65535):
            print_warning(f"端口输入无效，使用默认端口{default_port}")
            port = str(default_port)


def _check_metrics(client, port):
    command = f"curl -fsS --max-time 5 http://127.0.0.1:{port}/metrics 2>/dev/null | head -n1"
    output, _, code = run_command(client, command)
    return code == 0 and bool(output.strip())


def install_node_exporter(client):
    status, stable_version = get_stable_version("https://api.github.com/repos/prometheus/node_exporter/tags?page=1&per_page=5")
    if status != 0:
        print_error("✗ 获取node_exporter最新版本失败，无法继续安装")
        print_warning(stable_version)
        return None

    installed_output = _get_installed_version(client)
    if installed_output:
        print_success("node_exporter已安装。")
        print_info(f"当前版本信息: {installed_output}\n")
        if not confirm_yes_no("是否继续重新安装/覆盖配置？", default=False):
            print_warning("→ 已跳过安装")
            return None

    print_info("node_exporter最新发行版为：" + stable_version)
    if confirm_yes_no("是否安装？", default=False):
        print_info("开始安装node_exporter " + stable_version + "......")

        install_dir_exists = _path_exists(client, INSTALL_DIR)
        if install_dir_exists:
            if not confirm_yes_no(f"检测到安装目录已存在：{INSTALL_DIR}，是否仅更新systemd配置？", default=False):
                print_warning("→ 已取消安装，避免覆盖现有目录")
                return None

        local_path = os.path.join("packages", "node_exporter-" + stable_version + ".linux-amd64.tar.gz")
        url = "https://github.com/prometheus/node_exporter/releases/download/v" + stable_version + "/node_exporter-" + stable_version + ".linux-amd64.tar.gz"
        remote_path = "/usr/local/src/node_exporter-" + stable_version + ".linux-amd64.tar.gz"

        cmds = []
        if not install_dir_exists:
            if not remote_download_or_upload(client, url, local_path, remote_path, failure_message="本地上传失败，中止安装", wget_args=("--tries=3",)):
                return None
                    
            cmds = [
                "tar zxf " + remote_path + " -C /usr/local/src/",
                "mv /usr/local/src/node_exporter-" + stable_version + ".linux-amd64 " + INSTALL_DIR
            ]

        cmd_status = 0
        for cmd in cmds:
            _, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break
        
        if cmd_status == 0:
            listen_port = str(DEFAULT_EXPORTER_PORT)
            configured_systemd = False
            if confirm_yes_no("是否自动配置systemd守护？", default=True):
                listen_port = _pick_listen_port(client)
                configured_systemd = True
                         
                local_path = os.path.join("config", "prometheus", "node-exporter.service")
                remote_path = f"/etc/systemd/system/{SERVICE_NAME}.service"
                upload_file_with_vars(client, local_path, remote_path, {"PORT": listen_port})
                run_command(client, "systemctl daemon-reload")
            if confirm_yes_no("是否启动node-exporter服务？", default=True):
                run_command(client, f"systemctl start {SERVICE_NAME}")
            if confirm_yes_no("是否设置node-exporter开机自启？", default=True):
                run_command(client, f"systemctl enable {SERVICE_NAME}")
            # 检查服务状态
            print_info("\n正在检查node-exporter服务状态...")
            info, err, _ = run_command(client, f"systemctl is-active {SERVICE_NAME}")
            if info.strip() == "active":
                print_success("✓ node-exporter服务已成功启动并运行")
                if configured_systemd:
                    # 检查端口是否监听
                    port_out, _, _ = run_command(client, f"ss -tlnp 2>/dev/null | grep :{listen_port} || netstat -tlnp 2>/dev/null | grep :{listen_port}")
                    if port_out.strip():
                        print_success("✓ node-exporter端口" + str(listen_port) + "正在监听")
                    else:
                        print_warning("⚠ node-exporter端口" + str(listen_port) + "未检测到监听")
                    if _check_metrics(client, listen_port):
                        print_success("✓ node-exporter metrics接口可访问")
                    else:
                        print_warning("⚠ node-exporter metrics接口未验证通过，请检查服务日志")
                else:
                    print_warning("⚠ 未配置systemd守护，已跳过端口和metrics验证")
            else:
                print_error("✗ node-exporter服务启动失败")
                if err:
                    print_error(f"错误信息: {err.strip()}")

            print_info("安装完成！")
            print_warning("请手动将node-exporter的metrics端口添加到Prometheus的配置中以开始监控\n")

    else:
        print_warning(f"返回上一级")

    return None
    

def manage_node_exporter(client):
    install_node_exporter(client)
