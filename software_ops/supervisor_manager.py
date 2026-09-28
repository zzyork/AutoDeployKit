import os
import posixpath
import re
import shlex
from getpass import getpass
from pathlib import Path
from string import Template

from utils.choice import confirm_yes_no, menu_choice
from utils.file_utils import upload_file, upload_file_with_vars
from utils.output import print_error, print_info, print_success, print_warning
from utils.ssh_utils import run_command, run_command_live

current_version, status, stable_version = None, None, None

def get_ini_base_dir(client):
    include_line, _, _ = run_command(
        client,
        r"awk -F= '/^\s*files\s*=/ {print $2; exit}' /etc/supervisord.conf"
    )
    include_rhs = include_line.strip() if include_line else ""
    patterns = shlex.split(include_rhs) if include_rhs else []
    if patterns:
        dirs = {os.path.dirname(p) for p in patterns}
        normalized_dirs = {os.path.dirname(d) if "*" in d else d for d in dirs}
        return sorted(normalized_dirs)[0]
    return "/etc/supervisord.d"

def install_supervisor(client):
    print_info("supervisor最新稳定版为：" + stable_version)
    if confirm_yes_no("是否确认安装？", default=False):
        print_info("开始安装supervisor " + stable_version + "......")

        cmds = [
            "pip install supervisor",
            "mkdir -vp /var/log/supervisor",
            "mkdir -vp /var/run/supervisor",
            ]
        for cmd in cmds:
            _, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0:
                print_error(f"命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单")
                return

        if confirm_yes_no("是否自动配置 supervisord.conf 文件？", default=False):
            while True:
                ini_path = input("请输入ini配置文件保存路径（默认：/etc/supervisord.d）：").strip()
                if ini_path == "":
                    ini_path = "/etc/supervisord.d"
                if ini_path.startswith("/"):
                    break
                print_error("请输入正确的绝对路径")

            run_command_live(client, f"mkdir -p {ini_path}")
            local_path = os.path.join("config", "supervisor", "supervisord.conf")
            remote_path = "/etc/supervisord.conf"
            choice = menu_choice("是否开启web UI管理服务？(y/n): ", valid_choices=['y', 'n'], default='n')
            
            if choice == 'y':
                username = input("请输入web UI用户名（默认：admin）：").strip()
                if username == "":
                    username = "admin"
                password = getpass("请输入web UI密码（默认：admin）：").strip()
                if password == "":
                    password = "admin"
                upload_file_with_vars(client, local_path, remote_path,{'INI_PATH': ini_path, 'USERNAME': username, 'PASSWORD': password})
                run_command_live(client, "sed -i '/^[;[:space:]]*\\[inet_http_server\\]/,/^\\[/{s/^[[:space:]]*;//}' /etc/supervisord.conf")
            elif choice == 'n':
                upload_file_with_vars(client, local_path, remote_path, {'INI_PATH': ini_path})

        if confirm_yes_no("是否配置systemd守护进程？", default=False):
            local_path = os.path.join("config", "supervisor", "supervisord.service")
            remote_path = "/etc/systemd/system/supervisord.service"
            upload_file(client, local_path, remote_path)
            _, _, cmd_status = run_command(client, "systemctl daemon-reload")
            if cmd_status == 0:
                print_success("systemd守护进程配置完成\n")
            else:
                print_error("systemd守护进程配置失败")

        if confirm_yes_no("是否配置systemd守护进程自启？"):
            run_command_live(client, "systemctl enable supervisord")
            print_success("systemd守护进程自启配置完成\n")

        if confirm_yes_no("是否启动Supervisord服务？"):
            run_command_live(client, "systemctl start supervisord")
            print_success("Supervisord服务启动完成\n")
            current_version, _, status = run_command(client, r'supervisord -v 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
            current_version = current_version.strip() if current_version else ""
        print_info("安装完成！当前supervisor版本：" + current_version)

    else:
        print_warning(f"返回上一级菜单")
    return None

def configure_ini(client, replace=False):
    while True:
        ini_name = input("请输入要修改的守护进程名称：" if replace else "请输入要创建的守护进程名称：").strip()
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", ini_name):
            break
        print_error("名称只能包含字母、数字、下划线和连字符，且不能以符号开头")

    ini_path = posixpath.join(get_ini_base_dir(client), ini_name + ".ini")
    _, _, status = run_command(client, f"test -f {shlex.quote(ini_path)}")
    if replace and status != 0:
        print_error(f"ini文件 {ini_path} 不存在，请确认后重试")
        return
    if not replace and status == 0:
        print_error(f"ini文件 {ini_path} 已存在，取消创建")
        return

    while True:
        program_command = input("请输入要守护的程序启动命令：").strip()
        if program_command and "\n" not in program_command and "\r" not in program_command:
            break
        print_error("程序启动命令不能为空，请重新输入")

    while True:
        directory = input("请输入程序工作目录（绝对路径）：").strip()
        if posixpath.isabs(directory) and "\n" not in directory and "\r" not in directory and ";" not in directory:
            break
        print_error("工作目录必须是有效的绝对路径")

    while True:
        program_user = input("请输入运行用户（默认：nginx）：").strip() or "nginx"
        if re.fullmatch(r"[a-z_][a-z0-9_-]*\$?", program_user):
            break
        print_error("请输入有效的 Linux 用户名")

    while True:
        logfile = input(f"请输入日志文件路径（默认：/data/logs/{ini_name}.log）：").strip() or f"/data/logs/{ini_name}.log"
        if posixpath.isabs(logfile) and "\n" not in logfile and "\r" not in logfile and ";" not in logfile:
            break
        print_error("日志文件路径必须是有效的绝对路径")

    variables = {
        'PROGRAM_NAME': ini_name,
        'PROGRAM_COMMAND': program_command,
        'PROGRAM_DIRECTORY': directory,
        'PROGRAM_USER': program_user,
        'PROGRAM_LOGFILE': logfile,
    }
    local_path = Path("config/supervisor/program.ini")
    with local_path.open(encoding="utf-8") as template_file:
        config = Template(template_file.read()).substitute(variables)
    print_info(f"拟{'替换' if replace else '创建'} {ini_path}，完整配置如下：\n{config}")
    if replace:
        print_info("确认后将先备份原文件，再上传完整配置并执行 supervisorctl update")
    else:
        print_info("确认后将上传配置并执行 supervisorctl update")
    if not confirm_yes_no("确认执行以上操作？", default=False):
        return

    if replace:
        backup_cmd = f"cp -p {shlex.quote(ini_path)} {shlex.quote(ini_path + '.bak_')}$(date +%Y%m%d%H%M%S%N)"
        _, err, backup_status = run_command(client, backup_cmd)
        if backup_status != 0:
            print_error(f"备份失败，取消替换：{err}")
            return
    else:
        _, _, status = run_command(client, f"test -e {shlex.quote(ini_path)}")
        if status == 0:
            print_error("目标文件已存在，取消创建")
            return

    upload_file_with_vars(client, str(local_path), ini_path, variables)
    actual, err, read_status = run_command(client, f"cat {shlex.quote(ini_path)}")
    if read_status != 0 or actual != config.strip():
        print_error(f"配置写入后校验失败：{err or ini_path}；未执行 supervisorctl update")
        return
    print_success(f"ini文件 {ini_path} {'替换' if replace else '创建'}成功")
    _, update_status = run_command_live(client, "supervisorctl update")
    if update_status != 0:
        print_error("supervisorctl update 失败，请检查配置")
        return
    result, err, status = run_command(client, f"supervisorctl status {shlex.quote(ini_name)}")
    print_info(f"当前状态：{result or err}" if status == 0 else f"状态查询失败：{err or result}")

def add_ini(client):
    configure_ini(client)

def modify_ini(client):
    configure_ini(client, replace=True)

def delete_ini(client):
    ini_base_dir = get_ini_base_dir(client)
    while True:
        ini_name = input("请输入要删除的守护进程名称：").strip()
        if ini_name != "":
            break
        print_error("名称不能为空，请重新输入")
    ini_path = ini_base_dir + "/" + ini_name + ".ini"
    _, _, status = run_command(client, f"test -f {ini_path}")
    if status != 0:
        print_error(f"ini文件 {ini_path} 不存在，请确认后重试")
        return
    if confirm_yes_no(f"确认删除ini文件 {ini_path} ？", default=False):
        run_command(client, f"/usr/bin/mv -f {ini_path} {ini_path}.bak_$(date +%Y%m%d%H%M%S)")
        print_success(f"ini文件 {ini_path} 删除成功")
        if confirm_yes_no("是否重新加载supervisord配置以应用修改？", default=True):
            run_command_live(client, "supervisorctl update")
            print_success("supervisord配置加载完成\n")
    else:
        print_warning("取消删除操作，返回上一级菜单")

def manage_supervisor(client):
    global stable_version
    run_command(client, "dnf install pip -y")
    current_version, _, _ = run_command(client, r'supervisord --version 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    current_version = current_version.strip() if current_version else ""
    stable_version, _, _ = run_command(client, r'pip index versions supervisor 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    print_info("Supervisor最新稳定版为：" + stable_version)
    while True:
        if current_version == "":
            print("========== supervisor软件管理 ==========")
            print("1. 安装 supervisor 最新稳定版")
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', '0'], default="0")
            if choice == "1":
                install_supervisor(client)
                current_version, _, _ = run_command(client, r'supervisord --version 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
                current_version = current_version.strip() if current_version else ""
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
        else:
            print("Supervisor已安装，当前版本：" + current_version)
            print("========== ini守护进程配置菜单 ==========")
            print("1. 创建ini守护进程文件")
            print("2. 修改ini守护进程文件")
            print("3. 删除ini守护进程文件")
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', "2", '3', '0'], default="0")
            if choice == "1":
                add_ini(client)
            elif choice == "2":
                modify_ini(client)
            elif choice == "3":
                delete_ini(client)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
