import os
from utils.file_utils import download_file, upload_file, get_stable_version
from utils.output import print_info, print_error, print_warning, print_success
from utils.ssh_utils import run_command, run_command_live
from utils.choice import confirm_yes_no, menu_choice

def install_docker(client):
    print_info("docker最新稳定版为：" + stable_version)
    if confirm_yes_no("是否安装？", default=False):
        print_info("开始安装docker " + stable_version + "......\n")

        print_info("开始下载源码包并编译安装")
        url = "https://download.docker.com/linux/static/stable/x86_64/docker-" + stable_version + ".tgz"
        local_path = os.path.join("packages", "docker-" + stable_version + ".tgz")
        remote_path = "/usr/local/src/docker-" + stable_version + ".tgz"

        wget_cmd = f"cd /usr/local/src && wget {url}"
        _, wget_status = run_command_live(client, wget_cmd)
        
        if wget_status == 0:
            pass
        else:
            print_warning("下载失败，尝试本地上传")
            try:
                download_file(url, local_path)
                upload_file(client, local_path, remote_path)
                print_info("本地上传成功")
            except RuntimeError as e:
                print_error(f"本地上传也失败，中止安装: {e}")
                print_warning("返回上一级菜单\n")
                return None
                
        cmds = [
            "tar zxf " + remote_path + " -C /usr/local/src/",
            "cp /usr/local/src/docker/* /usr/bin/",
        ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        if confirm_yes_no("是否自动配置 daemon.json 配置文件？", default=False):
            run_command(client, "mkdir -p /etc/docker")
            local_path = os.path.join("config", "docker", "daemon.json")
            remote_path = "/etc/docker/daemon.json"
            upload_file(client, local_path, remote_path)
            run_command(client, "mkdir -p /data/docker-data")

        if confirm_yes_no("是否配置systemd守护进程？", default=False):
            local_path = os.path.join("config", "docker", "docker.service")
            remote_path = "/etc/systemd/system/docker.service"
            upload_file(client, local_path, remote_path)
            local_path = os.path.join("config", "docker", "docker.socket")
            remote_path = "/etc/systemd/system/docker.socket"
            upload_file(client, local_path, remote_path)
            _, _, cmd_status = run_command(client, "systemctl daemon-reload")
            if cmd_status == 0:
                print_success("systemd守护进程配置完成\n")
            else:
                print_error("systemd守护进程配置失败")

        if confirm_yes_no("是否配置systemd守护进程自启？"):
            run_command_live(client, "systemctl enable docker")
            print_success("systemd守护进程自启配置完成\n")

        if confirm_yes_no("是否启动Docker服务？"):
            run_command_live(client, "systemctl start docker")
            print_success("Docker服务启动完成\n")
            current_version, _, status = run_command(client, r'docker -v 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
            current_version = current_version.strip() if current_version else ""
        print_info("安装完成！当前docker版本：" + current_version)

    else:
        print_warning(f"返回上一级")

    return None

def install_docker_compose(client):
    current_version, _, status = run_command(client, r'docker-compose -v 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    current_version = current_version.strip() if current_version else ""
    if current_version != "":
        print_info("docker-compose 已安装，版本：" + current_version)
        return None
    stable_version = get_stable_version("https://api.github.com/repos/docker/compose/tags?page=1&per_page=5")
    print_info("docker-compose 最新稳定版为：" + stable_version)
    if confirm_yes_no("是否安装？", default=False):
        print_info("开始安装docker-compose " + stable_version + "......\n")

        print_info("开始下载源码包并编译安装")
        url = "https://github.com/docker/compose/releases/download/v" + stable_version + "/docker-compose-linux-x86_64"
        local_path = os.path.join("packages", "docker-compose-linux-x86_64")
        remote_path = "/usr/local/src/docker-compose-linux-x86_64"

        wget_cmd = f"cd /usr/local/src && wget {url}"
        _, wget_status = run_command_live(client, wget_cmd)
        
        if wget_status == 0:
            pass
        else:
            print_warning("下载失败，尝试本地上传")
            try:
                download_file(url, local_path)
                upload_file(client, local_path, remote_path)
                print_info("本地上传成功")
            except RuntimeError as e:
                print_error(f"本地上传也失败，中止安装: {e}")
                print_warning("返回上一级菜单\n")
                return None
                
        cmds = [
            "cp /usr/local/src/docker-compose-linux-x86_64 /usr/local/bin/docker-compose",
            "chmod +x /usr/local/bin/docker-compose",
        ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break
            else:
                current_version, _, status = run_command(client, r'docker-compose -v 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
                current_version = current_version.strip() if current_version else ""
                print_success("docker-compose安装完成！当前docker-compose版本：" + current_version)

    else:
        print_warning(f"返回上一级")

    return None

def manage_docker(client):
    global current_version, status, stable_version
    current_version, _, status = run_command(client, r'docker -v 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    current_version = current_version.strip() if current_version else ""
    stable_version = get_stable_version("https://download.docker.com/linux/static/stable/x86_64/")
    print_info("Docker最新稳定版为：" + stable_version)
    while True:
        if current_version == "":
            print("========== docker软件管理 ==========")
            print("1. 安装 docker 最新稳定版")
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', '0'], default="0")
            if choice == "1":
                install_docker(client)
            elif choice == "0":
                break
            else:
                    print("无效选项，请重新输入")
        else:
            print("已安装docker，版本：" + current_version)
            current_version, _, status = run_command(client, r'docker-compose -v 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
            current_version = current_version.strip() if current_version else ""
            if current_version == "":
                print("========== docker-compose软件管理 ==========")
                print("1. 安装 docker-compose 最新稳定版")
                print("0. 返回/跳过")
                choice = menu_choice("请选择操作编号: ", valid_choices=['1', '0'], default="0")
                if choice == "1":
                    install_docker_compose(client)
                elif choice == "0":
                    break
                else:
                    print("无效选项，请重新输入")
            else:
                print("已安装docker-compose，版本：" + current_version)
                break