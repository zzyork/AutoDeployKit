import os
import stat
from colorama import Fore
from utils.file_utils import download_file, upload_file, upload_file_with_vars
from utils.output import print_info, print_error, print_warning, print_success
from utils.ssh_utils import run_command, run_command_live

def install_minio(client):
    print_info("Minio最新稳定版为：" + latest_version)
    choice = input(Fore.MAGENTA + f"是否安装？(y/N): ").strip().lower()
    if choice == "y":
        print_info("开始安装minio " + latest_version + "......\n")
        
        default_install_path = "/usr/local/minio2504"
        install_path = input(Fore.MAGENTA + f"请输入Minio安装目录 (默认: {default_install_path}): ").strip()
        if not install_path:
            install_path = default_install_path
        run_command(client, "mkdir -p " + install_path + "/bin")
        print_success("Minio将安装到: " + install_path + "\n")
        
        default_data_dir = "/data/minio"
        data_dir = input(Fore.MAGENTA + f"请输入Minio数据目录 (默认: {default_data_dir}): ").strip()
        if not data_dir:
            data_dir = default_data_dir
        run_command(client, "mkdir -p " + data_dir)
        print_success("Minio数据目录: " + data_dir + "\n")

        print_info("创建minio用户......")
        run_command(client, "getent group minio || groupadd minio")
        run_command(client, "id minio &>/dev/null || useradd -r -g minio minio -s /sbin/nologin")
        run_command(client, "chown minio:minio " + install_path)
        run_command(client, "chown minio:minio " + data_dir)
        print_success("创建minio用户完成。\n")
        

        print_info("开始下载二进制包并安装")
        url = "https://dl.minio.org.cn/server/minio/release/linux-amd64/archive/minio.RELEASE.2025-04-22T22-12-26Z"
        local_path = os.path.join("packages", "minio.RELEASE.2025-04-22T22-12-26Z")
        remote_path = "/usr/local/src/minio.RELEASE.2025-04-22T22-12-26Z"

        wget_cmd = f"cd /usr/local/src && wget {url}"
        _, wget_status = run_command_live(client, wget_cmd)
        
        if wget_status == 0:
            pass
        else:
            print_warning("下载失败，尝试本地上传")
            try:
                download_file(url, local_path)
                upload_file(client, local_path, remote_path)
                print_success("本地上传成功")
            except RuntimeError as e:
                print_error(f"本地上传也失败，中止安装: {e}")
                print_warning("返回上一级菜单\n")
                return None

        cmds = [
            "cp -r " + remote_path + " " + install_path + "/bin/minio",
            "chmod +x " + install_path + "/bin/minio",
        ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        
        choice = input(Fore.MAGENTA + f"是否自动配置minio.conf配置？(y/N): ").strip().lower()
        if choice == "y":
            print_info("正在配置minio.conf文件...")
            local_path = os.path.join("config", "minio", "minio.conf")
            remote_path = install_path + "/minio.conf"
            minio_username = input(Fore.MAGENTA + f"请输入Minio用户名: ").strip()
            minio_password = input(Fore.MAGENTA + f"请输入Minio密码: ").strip()
            upload_file_with_vars(client, local_path, remote_path, {'MINIO_DATA_DIR': data_dir, 'MINIO_USERNAME': minio_username, 'MINIO_PASSWORD': minio_password})
            run_command(client, "chown minio:minio " + install_path + "/minio.conf")
            print_success("minio.conf文件配置完成\n")

        choice = input(Fore.MAGENTA + f"是否配置systemd守护进程？(y/N): ").strip().lower()
        if choice == "y":
            local_path = os.path.join("config", "minio", "minio.service")
            remote_path = "/etc/systemd/system/minio.service"
            upload_file_with_vars(client, local_path, remote_path, {'MINIO_INSTALL_PATH': install_path})
            output, cmd_status = run_command_live(client, "systemctl daemon-reload")
            if cmd_status == 0:
                print_success("systemd守护进程配置完成\n")
            else:
                print_error("systemd守护进程配置失败")

        choice = input(Fore.MAGENTA + f"是否配置systemd守护进程自启？(y/N): ").strip().lower()
        if choice == "y":
            run_command_live(client, "systemctl enable minio")
            print_success("systemd守护进程自启配置完成\n")

        choice = input(Fore.MAGENTA + f"是否启动Minio服务？(y/N): ").strip().lower()
        if choice == "y":
            run_command_live(client, "systemctl start minio")
            print_success("Minio服务启动完成\n")

        # 检查firewalld状态并开放端口
        firewalld_status, _, _ = run_command(client, "systemctl is-active firewalld 2>&1")
        if firewalld_status.strip() == "active":
            choice = input(Fore.MAGENTA + f"检测到firewalld防火墙已开启，是否添加放行规则？(y/N): ").strip().lower()
            if choice == "y":
                print_info("检测到firewalld已开启，正在开放Minio端口...")
                run_command(client, "firewall-cmd --permanent --add-port=9000/tcp")
                run_command(client, "firewall-cmd --permanent --add-port=9001/tcp")
                run_command(client, "firewall-cmd --reload")
                print_success("已开放9000和9001端口")
        else:
            print_info("firewalld未开启或状态异常，跳过端口配置")
        
        current_version, _, _ = run_command(client, r"/usr/local/minio2504/bin/minio -v 2>&1| grep RELEASE | awk '{print $3}'")
        current_version = current_version.strip() if current_version else ""
        print_info(f"安装完成！当前Minio版本: {current_version}")

    else:
        print_warning(f"返回上一级")

    return None

def manage_minio(client):
    global current_version, status, latest_version
    latest_version = "RELEASE.2025-04-22T22-12-26Z"
    current_version, _, status = run_command(client, r"/usr/local/minio2504/bin/minio -v 2>&1| grep RELEASE | awk '{print $3}'")
    current_version = current_version.strip() if current_version else ""
    print_info("Minio最新稳定版：" + latest_version)
    while True:
        print("=== minio软件管理 ===")
        if current_version == "":
            print("1. 安装 minio 最新稳定版")
            print("0. 返回/跳过")
            choice = input("请选择操作编号: ").strip()
            if choice == "1":
                install_minio(client)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
        else:
            print("已安装minio，版本：" + current_version)
            break