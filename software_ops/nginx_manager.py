import os
import re
import json
import datetime

import requests
from colorama import Fore

from utils.file_utils import download_file, upload_file, upload_file_with_vars
from utils.output import print_info, print_error, print_success, print_warning
from utils.ssh_utils import run_command, run_command_live


def get_stable_nginx():
    url = "https://nginx.org/en/download.html"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"请求失败：{e}")
        return None

    # 正则匹配 “Stable version” 段落的版本号
    match = re.search(r'Stable version.*?nginx-(\d+\.\d+\.\d+)', response.text, re.DOTALL)

    if not match:
        print("未找到 Stable version 信息")
        return None

    return match.group(1)

def install_nginx(client):
    stable_version = get_stable_nginx()
    print_info("Nginx最新发行版为：" + stable_version)
    choice = input(Fore.MAGENTA + f"是否安装？(y/N): ").strip().lower()
    if choice == "y":
        # 提示输入Nginx安装目录
        default_install_path = "/usr/local/nginx" + '.'.join(stable_version.split('.')[:2])
        install_path = input(Fore.MAGENTA + f"请输入Nginx安装目录 (默认: {default_install_path}): ").strip()
        if not install_path:
            install_path = default_install_path
        print_info("Nginx将安装到: " + install_path)
        
        # 提示输入日志目录
        default_log_dir = "/data/logs/nginx"
        log_dir = input(Fore.MAGENTA + f"请输入Nginx日志目录 (默认: {default_log_dir}): ").strip()
        if not log_dir:
            log_dir = default_log_dir
        print_info("Nginx日志目录: " + log_dir + "\n")
        
        print_info("开始安装Nginx " + stable_version + "......\n")

        print_info("创建nginx用户")
        output, status = run_command_live(client, "getent group nginx || groupadd nginx")
        output, status = run_command_live(client, "id nginx &>/dev/null || useradd -r -g nginx nginx")
        print_success("创建nginx用户完成。\n")

        print_info("安装依赖")
        output, status = run_command_live(client, 'yum -y install make zlib zlib-devel gcc-c++ libtool openssl-devel pcre-devel')
        print_success("perl安装完成。\n")

        print_info("开始下载源码包并编译安装")
        local_path = os.path.join("packages", "nginx-" + stable_version + ".tar.gz")
        url = "https://nginx.org/download/nginx-" + stable_version + ".tar.gz"
        remote_path = "/usr/local/src/nginx-" + stable_version + ".tar.gz"

        # 优先使用服务器wget下载
        print_info(f"尝试使用服务器wget下载 {url}")
        wget_cmd = f"cd /usr/local/src && wget {url}"
        output, wget_status = run_command_live(client, wget_cmd)
        
        if wget_status == 0:
            print_success("服务器wget下载成功")
        else:
            print_warning("服务器wget下载失败，尝试本地上传")
            try:
                download_file(url, local_path)
                upload_file(client, local_path, remote_path)
                print_success("本地上传成功")
            except RuntimeError as e:
                print_error(f"本地上传也失败，中止安装: {e}")
                print_warning("返回上一级菜单\n")
                return None
        cmds = [
            "tar zxf " + remote_path + " -C /usr/local/src/",
            "cd /usr/local/src/nginx-" + stable_version + " && ./configure --prefix=" + install_path + " --with-http_stub_status_module --with-http_gzip_static_module --with-http_realip_module --with-http_sub_module --with-http_ssl_module --with-http_v2_module --with-stream",
            "cd /usr/local/src/nginx-" + stable_version + " && make && make install",
            "ln -fs " + install_path + "/sbin/nginx /usr/bin/nginx",
            "mkdir -p " + install_path + "/conf/conf.d",
        ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        if cmd_status == 0:
            current_version, _ = run_command_live(client, "nginx -v 2>&1 | awk -F'/' '{print $2}' | awk '{print $1}'")
            print_info("\n安装完成！\n当前nginx版本：" + current_version)
            choice = input(Fore.MAGENTA + f"是否自动调整nginx.conf文件？(y/N): ").strip().lower()
            if choice == "y":
                local_path = os.path.join("config", "nginx.conf")
                remote_path = install_path + "/conf/nginx.conf"
                upload_file_with_vars(client, local_path, remote_path, {'NGINX_INSTALL_PATH': install_path, 'NGINX_LOG_DIR': log_dir})
            choice = input(Fore.MAGENTA + f"是否配置systemd守护进程？(y/N): ").strip().lower()
            if choice == "y":
                local_path = os.path.join("config", "nginx.service")
                remote_path = "/etc/systemd/system/nginx.service"
                upload_file_with_vars(client, local_path, remote_path, {'install_path': install_path})
                
                # 执行systemd相关命令
                systemd_cmds = [
                    "systemctl daemon-reload",
                    f"mkdir -p {log_dir}",
                    "systemctl enable --now nginx",
                ]
                for cmd in systemd_cmds:
                    output, cmd_status = run_command_live(client, cmd)
                    if cmd_status != 0:
                        print_error(f"systemd命令执行失败: {cmd}")
                        break
                else:
                    print_info("systemd守护进程配置完成")

    else:
        print_warning(f"返回上一级")

    return None

def upgrade_nginx(client):
    stable_version = get_stable_nginx()
    print_info("开始升级 Nginx 到最新发行版 " + stable_version + "......\n")

    # 先备份当前版本
    print_info("升级前备份当前nginx版本...")
    backup_info = backup_nginx(client)
    if backup_info is None:
        print_warning("备份失败，是否继续升级？")
        choice = input(Fore.MAGENTA + "继续升级？(y/N): ").strip().lower()
        if choice != "y":
            print_warning("取消升级操作")
            return None
    else:
        print_success("备份完成，开始升级...")

    print_info("开始下载源码包并编译安装")
    local_path = os.path.join("packages", "nginx-" + stable_version + ".tar.gz")
    url = "https://nginx.org/download/nginx-" + stable_version + ".tar.gz"
    remote_path = "/usr/local/src/nginx-" + stable_version + ".tar.gz"
    install_path = "/usr/local/nginx" + '.'.join(stable_version.split('.')[:2])

    # 优先使用服务器wget下载
    print_info(f"尝试使用服务器wget下载 {url}")
    wget_cmd = f"cd /usr/local/src && wget {url}"
    output, wget_status = run_command_live(client, wget_cmd)
    
    if wget_status == 0:
        print_success("服务器wget下载成功")
    else:
        print_warning("服务器wget下载失败，尝试本地上传")
        try:
            download_file(url, local_path)
            upload_file(client, local_path, remote_path)
            print_success("本地上传成功")
        except RuntimeError as e:
            print_error(f"本地上传也失败，中止升级: {e}")
            print_warning("返回上一级菜单\n")
            return None
    
    cmds = [
        "tar zxf " + remote_path + " -C /usr/local/src/",
        "cd /usr/local/src/nginx-" + stable_version + "&& ./configure --prefix=" + install_path + " --with-http_stub_status_module --with-http_gzip_static_module --with-http_realip_module --with-http_sub_module --with-http_ssl_module --with-http_v2_module --with-stream",
        "cd /usr/local/src/nginx-" + stable_version + "&& make && make install",
        "ln -fs " + install_path + "/sbin/nginx /usr/bin/nginx"
    ]

    cmd_status = 0
    for cmd in cmds:
        output, cmd_status = run_command_live(client, cmd)
        if cmd_status != 0 :
            print_error(f"\n命令执行失败: {cmd}")
            print_warning("升级失败，是否回滚到之前版本？")
            choice = input(Fore.MAGENTA + "是否回滚？(y/N): ").strip().lower()
            if choice == "y" and backup_info:
                rollback_nginx(client)
            else:
                print_warning("中止当前操作，返回上一级菜单\n")
            break

    if cmd_status == 0:
        current_version, _, status = run_command(client, "nginx -v 2>&1 | awk -F'/' '{print $2}' | awk '{print $1}'")
        print_success(f"\n升级已完成！\n当前nginx版本: {current_version}")
        print_info("建议在非业务高峰期手动重启nginx")
        
        # 询问是否立即重启
        restart_choice = input(Fore.MAGENTA + "是否立即重启nginx？(y/N): ").strip().lower()
        if restart_choice == "y":
            print_info("重启nginx服务...")
            output, status = run_command_live(client, 'systemctl restart nginx')
            if status == 0:
                print_success("nginx服务重启成功")
            else:
                print_error("nginx服务重启失败，请检查配置")
                print_warning("如果需要，可以使用回滚功能恢复到之前版本")

def backup_nginx(client):
    """备份当前nginx安装，用于回滚"""
    print_info("开始备份当前nginx安装...")
    
    # 获取当前版本信息
    output, error, status = run_command(client, "nginx -v 2>&1 | awk -F'/' '{print $2}' | awk '{print $1}'")
    if status != 0:
        print_error("无法获取当前nginx版本信息")
        return None
    
    current_version = output.strip()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"/tmp/nginx_backup_{current_version}_{timestamp}"
    
    print_info(f"创建备份目录: {backup_dir}")
    
    # 创建备份目录
    output, error, status = run_command(client, f'mkdir -p {backup_dir}')
    if status != 0:
        print_error(f"创建备份目录失败: {backup_dir}")
        return None
    
    # 备份nginx二进制文件
    print_info("备份nginx二进制文件...")
    output, error, status = run_command(client, 'readlink -f /usr/bin/nginx')
    if status == 0:
        nginx_binary = output.strip()
        output, error, status = run_command(client, f'cp -a {nginx_binary} {backup_dir}/nginx')
        if status != 0:
            print_error("备份nginx二进制文件失败")
            return None
    else:
        print_error("无法找到nginx二进制文件路径")
        return None
    
    # 备份nginx安装目录
    print_info("备份nginx安装目录...")
    output, error, status = run_command(client, 'find /usr/local -maxdepth 1 -name "nginx*" -type d')
    if status == 0 and output.strip():
        install_dirs = output.strip().split('\n')
        for install_dir in install_dirs:
            if install_dir.strip():
                dir_name = os.path.basename(install_dir.strip())
                output, error, status = run_command(client, f'cp -a {install_dir} {backup_dir}/{dir_name}')
                if status != 0:
                    print_error(f"备份安装目录失败: {install_dir}")
                    return None
    
    # 备份配置文件
    print_info("备份配置文件...")
    output, error, status = run_command(client, 'find /usr/local -name "nginx.conf" -type f 2>/dev/null')
    if status == 0 and output.strip():
        config_files = output.strip().split('\n')
        for config_file in config_files:
            if config_file.strip():
                rel_path = config_file.strip().replace('/usr/local/', '')
                backup_config_path = f"{backup_dir}/conf_{os.path.basename(rel_path)}"
                output, error, status = run_command(client, f'cp -a {config_file} {backup_config_path}')
                if status != 0:
                    print_error(f"备份配置文件失败: {config_file}")
                    return None
    
    # 备份systemd服务文件
    print_info("备份systemd服务文件...")
    output, error, status = run_command(client, 'test -f /etc/systemd/system/nginx.service')
    if status == 0:
        output, error, status = run_command(client, f'cp -a /etc/systemd/system/nginx.service {backup_dir}/')
        if status != 0:
            print_error("备份systemd服务文件失败")
            return None
    
    # 创建备份信息文件
    backup_info = {
        "version": current_version,
        "timestamp": timestamp,
        "backup_dir": backup_dir,
        "nginx_binary": nginx_binary if status == 0 else None,
        "install_dirs": install_dirs if status == 0 and output.strip() else [],
        "config_files": config_files if status == 0 and output.strip() else [],
        "systemd_service": "/etc/systemd/system/nginx.service"
    }
    
    backup_info_file = f"{backup_dir}/backup_info.json"
    backup_info_json = json.dumps(backup_info, indent=2, ensure_ascii=False)
    
    # 写入备份信息文件
    output, error, status = run_command(client, f'cat > {backup_info_file} << EOF\n{backup_info_json}\nEOF')
    if status != 0:
        print_error("创建备份信息文件失败")
        return None
    
    print_success(f"nginx备份完成！备份目录: {backup_dir}")
    return backup_info

def rollback_nginx(client):
    """回滚nginx到之前的版本"""
    print_info("查找可用的nginx备份...")
    
    # 查找备份目录
    output, error, status = run_command(client, "find /tmp -maxdepth 1 -type d -name 'nginx_backup_*' 2>/dev/null | sort -r")
    if status != 0 or not output.strip():
        print_warning("未找到任何nginx备份")
        return
    
    backup_dirs = output.strip().split('\n')
    print_info("找到以下备份:")
    for i, backup_dir in enumerate(backup_dirs, 1):
        # 读取备份信息
        info_file = f"{backup_dir}/backup_info.json"
        output, error, status = run_command(client, f'cat {info_file} 2>/dev/null')
        if status == 0:
            try:
                backup_info = json.loads(output)
                print(f"{i}. 版本: {backup_info['version']}, 时间: {backup_info['timestamp']}")
            except:
                print(f"{i}. {os.path.basename(backup_dir)} (信息文件损坏)")
        else:
            print(f"{i}. {os.path.basename(backup_dir)} (无信息文件)")
    
    choice = input(Fore.MAGENTA + "请选择要回滚到的备份编号 (0取消): ").strip()
    if choice == "0" or not choice.isdigit() or int(choice) < 1 or int(choice) > len(backup_dirs):
        print_warning("取消回滚操作")
        return
    
    selected_backup = backup_dirs[int(choice) - 1]
    print_info(f"选择备份: {selected_backup}")
    
    # 读取备份信息
    info_file = f"{selected_backup}/backup_info.json"
    output, error, status = run_command(client, f'cat {info_file}')
    if status != 0:
        print_error("无法读取备份信息文件")
        return
    
    try:
        backup_info = json.loads(output)
    except:
        print_error("备份信息文件格式错误")
        return
    
    # 确认回滚
    print_warning(f"即将回滚nginx到版本 {backup_info['version']}")
    print_warning("这将覆盖当前的nginx安装")
    confirm = input(Fore.MAGENTA + "确认回滚？(y/N): ").strip().lower()
    if confirm != "y":
        print_warning("取消回滚操作")
        return
    
    print_info("开始回滚nginx...")
    
    # 停止nginx服务
    print_info("停止nginx服务...")
    output, status = run_command(client, 'systemctl stop nginx 2>/dev/null || pkill nginx 2>/dev/null || true')
    
    # 恢复nginx二进制文件
    if backup_info.get('nginx_binary'):
        print_info("恢复nginx二进制文件...")
        output, status = run_command(client, f'cp -a {selected_backup}/nginx /usr/bin/nginx')
        if status != 0:
            print_error("恢复nginx二进制文件失败")
            return
    
    # 恢复安装目录
    if backup_info.get('install_dirs'):
        print_info("恢复nginx安装目录...")
        for install_dir in backup_info['install_dirs']:
            dir_name = os.path.basename(install_dir)
            output, status = run_command(client, f'cp -a {selected_backup}/{dir_name} {install_dir}')
            if status != 0:
                print_error(f"恢复安装目录失败: {install_dir}")
                return
    
    # 恢复配置文件
    if backup_info.get('config_files'):
        print_info("恢复配置文件...")
        for config_file in backup_info['config_files']:
            rel_path = config_file.replace('/usr/local/', '')
            backup_config_path = f"{selected_backup}/conf_{os.path.basename(rel_path)}"
            output, error, status = run_command(client, f'cp -a {backup_config_path} {config_file}')
            if status != 0:
                print_error(f"恢复配置文件失败: {config_file}")
                return
    
    # 恢复systemd服务文件
    if backup_info.get('systemd_service'):
        print_info("恢复systemd服务文件...")
        output, error, status = run_command(client, f'cp -a {selected_backup}/nginx.service /etc/systemd/system/')
        if status == 0:
            output, error, status = run_command(client, 'systemctl daemon-reload')
    
    # 验证回滚
    print_info("验证回滚结果...")
    output, error, status = run_command(client, "nginx -v 2>&1 | awk -F'/' '{print $2}' | awk '{print $1}'")
    if status == 0:
        rolled_back_version = output.strip()
        if rolled_back_version == backup_info['version']:
            print_success(f"nginx回滚成功！当前版本: {rolled_back_version}")
            print_info("建议检查配置文件并手动启动nginx服务")
        else:
            print_warning(f"版本不匹配，期望: {backup_info['version']}, 实际: {rolled_back_version}")
    else:
        print_error("回滚后nginx无法正常启动")
    
    # 询问是否启动nginx
    start_choice = input(Fore.MAGENTA + "是否启动nginx服务？(y/N): ").strip().lower()
    if start_choice == "y":
        print_info("启动nginx服务...")
        output, status = run_command_live(client, 'systemctl start nginx')
        if status == 0:
            print_success("nginx服务启动成功")
        else:
            print_error("nginx服务启动失败，请检查配置")

def list_nginx_backups(client):
    print_info("查找nginx备份...")
    
    output, error, status = run_command(client, "find /tmp -maxdepth 1 -type d -name 'nginx_backup_*' 2>/dev/null | sort -r")
    if status != 0 or not output.strip():
        print_warning("未找到任何nginx备份")
        return
    
    backup_dirs = output.strip().split('\n')
    print_success(f"找到 {len(backup_dirs)} 个备份:")
    
    for i, backup_dir in enumerate(backup_dirs, 1):
        info_file = f"{backup_dir}/backup_info.json"
        output, error, status = run_command(client, f'cat {info_file} 2>/dev/null')
        if status == 0:
            try:
                backup_info = json.loads(output)
                print(f"{i}. 版本: {backup_info['version']}, 时间: {backup_info['timestamp']}")
                print(f"   目录: {backup_dir}")
                if backup_info.get('install_dirs'):
                    print(f"   安装目录: {', '.join(backup_info['install_dirs'])}")
                print()
            except:
                print(f"{i}. {os.path.basename(backup_dir)} (信息文件损坏)")
        else:
            print(f"{i}. {os.path.basename(backup_dir)} (无信息文件)")

def manage_nginx(client):
    current_version, error, status = run_command(client, "nginx -v 2>&1 | awk -F'/' '{print $2}' | awk '{print $1}'")
    while True:
        print("=== Nginx软件管理 ===")
        if status != 0 or not current_version or current_version.strip() == "":
            print("1. 安装 Nginx 最新发行版")
            print("0. 返回/跳过")
            choice = input("请选择操作编号: ").strip()
            if choice == "1":
                install_nginx(client)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
        else:
            print_success("当前Nginx版本：" + current_version.strip())
            stable_version = get_stable_nginx()
            print_info("Nginx最新发行版为：" + stable_version)
            print("1. 升级 Nginx 到最新发行版")
            print("2. 备份当前 Nginx 版本")
            print("3. 回滚 Nginx 到之前版本")
            print("4. 查看所有备份")
            print("0. 返回/跳过")
            choice = input("请选择操作编号: ").strip()
            if choice == "1":
                upgrade_nginx(client)
            elif choice == "2":
                backup_nginx(client)
            elif choice == "3":
                rollback_nginx(client)
            elif choice == "4":
                list_nginx_backups(client)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
        
        # 重新获取版本状态
        current_version, error, status = run_command(client, "nginx -v 2>&1 | awk -F'/' '{print $2}' | awk '{print $1}'")