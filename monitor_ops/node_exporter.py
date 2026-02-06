import os
from colorama import Fore
from utils.file_utils import get_stable_version, download_file, upload_file, upload_file_with_vars
from utils.output import print_info, print_error, print_warning, print_success
from utils.ssh_utils import run_command, run_command_live
from utils.server_utils import is_valid_ip
from utils.choice import confirm_yes_no


def install_node_exporter(client):
    status, stable_version = get_stable_version("https://api.github.com/repos/prometheus/node_exporter/tags?page=1&per_page=5")
    if status != 0:
        print_error("✗ 获取node_exporter最新版本失败，无法继续安装")
        return None
    print_info("node_exporter最新发行版为：" + stable_version)
    if confirm_yes_no("是否安装？", default=False):
        print_info("开始安装node_exporter " + stable_version + "......")

        local_path = os.path.join("packages", "node_exporter-" + stable_version + ".linux-amd64.tar.gz")
        url = "https://github.com/prometheus/node_exporter/releases/download/v" + stable_version + "/node_exporter-" + stable_version + ".linux-amd64.tar.gz"
        remote_path = "/usr/local/src/node_exporter-" + stable_version + ".linux-amd64.tar.gz"

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
            "mv /usr/local/src/node_exporter-" + stable_version + ".linux-amd64 /usr/local/node-exporter"
        ]

        cmd_status = 0
        for cmd in cmds:
            _, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break
        
        if cmd_status == 0:
            if confirm_yes_no("是否自动配置systemd守护？", default=True):
                global port
                port = 8100
                while True:
                    port_check, _, _ = run_command(client, f"netstat -tlnp | grep :{port}")
                    if port_check.strip():
                        port = input(f"⚠ {port}端口被占用请重新输入监听端口: ").strip()
                        if not port.isdigit():
                            print_warning("端口输入无效，使用默认端口8100")
                    else:
                        break
                        
                local_path = os.path.join("config", "prometheus", "node-exporter.service")
                remote_path = "/etc/systemd/system/node-exporter.service"
                upload_file_with_vars(client, local_path, remote_path, {"PORT": port})
                run_command(client, "systemctl daemon-reload")
            if confirm_yes_no("是否启动node-exporter服务？", default=True):
                run_command(client, "systemctl start node-exporter")
            if confirm_yes_no("是否设置node-exporter开机自启？", default=True):
                run_command(client, "systemctl enable node-exporter")
            # 检查服务状态
            print_info("\n正在检查node-exporter服务状态...")
            info, _, _ = run_command(client, "systemctl is-active node-exporter")
            if info.strip() == "active":
                print_success("✓ node-exporter服务已成功启动并运行")
                # 检查端口是否监听
                port_out, _, _ = run_command(client, f"netstat -tlnp | grep :{port}")
                if port_out.strip():
                    print_success("✓ node-exporter端口" + str(port) + "正在监听")
                else:
                    print_warning("⚠ node-exporter端口" + str(port) + "未检测到监听")
            else:
                print_error("✗ node-exporter服务启动失败")

            print_info("安装完成！")
            print_warning("请手动将node-exporter的metrics端口添加到Prometheus的配置中以开始监控\n")

    else:
        print_warning(f"返回上一级")

    return None
    

def manage_node_exporter(client):
    install_node_exporter(client)