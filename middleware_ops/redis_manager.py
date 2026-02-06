import os
import json
import datetime
from colorama import Fore
from utils.file_utils import download_file, upload_file, upload_file_with_vars, get_stable_version
from utils.output import print_info, print_error, print_success, print_warning
from utils.ssh_utils import run_command, run_command_live
from utils.choice import confirm_yes_no, menu_choice

def install_redis(client, version=None):
    print_info("Redis最新发行版为：" + version)
    if confirm_yes_no("是否确定安装？", default=False):
        # 提示输入Redis安装目录
        default_install_path = "/usr/local/redis" + '.'.join(version.split('.')[:2])
        install_path = input(Fore.MAGENTA + f"请输入Redis安装目录 (默认: {default_install_path}): ").strip()
        if not install_path:
            install_path = default_install_path
        print_info("Redis将安装到: " + install_path)
        
        # 提示输入日志目录
        default_log_dir = "/data/logs/redis"
        log_dir = input(Fore.MAGENTA + f"请输入Redis日志目录 (默认: {default_log_dir}): ").strip()
        if not log_dir:
            log_dir = default_log_dir
        print_info("Redis日志目录: " + log_dir + "\n")
        
        print_info("开始安装Redis " + version + "......\n")

        print_info("创建redis用户")
        output, status = run_command_live(client, "getent group redis || groupadd redis")
        output, status = run_command_live(client, "id redis &>/dev/null || useradd -r -g redis redis")
        print_success("创建redis用户完成。\n")

        print_info("安装依赖")
        output, status = run_command_live(client, 'dnf -y install make zlib zlib-devel gcc-c++ libtool pcre2-devel')
        print_success("perl安装完成。\n")

        print_info("开始下载源码包并编译安装")
        local_path = os.path.join("packages", "redis-" + version + ".tar.gz")
        url = "https://redis.org/download/redis-" + version + ".tar.gz"
        remote_path = "/usr/local/src/redis-" + version + ".tar.gz"

        wget_cmd = f"cd /usr/local/src && wget {url}"
        output, wget_status = run_command_live(client, wget_cmd)
        
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
            "tar zxf " + remote_path + " -C /usr/local/src/",
            "cd /usr/local/src/redis-" + version + " && ./configure --prefix=" + install_path + " --with-http_stub_status_module --with-http_gzip_static_module --with-http_realip_module --with-http_sub_module --with-http_ssl_module --with-http_v2_module --with-stream",
            "cd /usr/local/src/redis-" + version + " && make && make install",
            "ln -fs " + install_path + "/sbin/redis /usr/bin/redis",
            "mkdir -p " + install_path + "/conf/conf.d",
        ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        if cmd_status == 0:
            current_version,_, _ = run_command(client, 'redis-cli -v 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
            current_version = current_version.strip() if current_version else ""
            print_info("安装完成！当前redis版本：" + current_version)
            if confirm_yes_no("是否自动调整redis.conf文件？", default=False):
                local_path = os.path.join("config", "redis", "redis.conf")
                remote_path = install_path + "/conf/redis.conf"
                upload_file_with_vars(client, local_path, remote_path, {'NGINX_INSTALL_PATH': install_path, 'NGINX_LOG_DIR': log_dir})
                print_success("✓ redis.conf配置完成\n")
            if confirm_yes_no("\n是否配置systemd守护进程？", default=False):
                local_path = os.path.join("config", "redis", "redis.service")
                remote_path = "/etc/systemd/system/redis.service"
                upload_file_with_vars(client, local_path, remote_path, {'install_path': install_path})
                
                # 执行systemd相关命令
                systemd_cmds = [
                    "systemctl daemon-reload",
                    f"mkdir -p {log_dir}",
                    "systemctl enable --now redis",
                ]
                for cmd in systemd_cmds:
                    _, cmd_status = run_command_live(client, cmd)
                    if cmd_status != 0:
                        print_error(f"命令执行失败: {cmd}")
                        break
                else:
                    print_success("✓ systemd守护进程配置完成\n")

    else:
        print_warning(f"返回上一级")

    return None

def backup_redis(client):
    """备份当前redis安装，用于回滚"""
    print_info("开始备份当前redis安装...")
    
    # 获取当前版本信息
    output, error, status = run_command(client, "redis-cli -v 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1")
    if status != 0:
        print_error("无法获取当前redis版本信息")
        return None
    
    current_version = output.strip() if output else ""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"/data/backups/redis_backup_{current_version}_{timestamp}"
    
    print_info(f"创建备份目录: {backup_dir}")
    
    # 创建备份目录
    output, error, status = run_command(client, f'mkdir -p {backup_dir}')
    if status != 0:
        print_error(f"创建备份目录失败: {backup_dir}")
        return None
    
    # 备份redis二进制文件
    print_info("备份redis二进制文件...")
    output, error, status = run_command(client, 'readlink -f /usr/bin/redis')
    if status == 0:
        redis_binary = output.strip()
        output, error, status = run_command(client, f'cp -a {redis_binary} {backup_dir}/redis')
        if status != 0:
            print_error("备份redis二进制文件失败")
            return None
    else:
        print_error("无法找到redis二进制文件路径")
        return None
    
    # 备份redis安装目录
    print_info("备份redis安装目录...")
    output, error, status = run_command(client, 'find /usr/local -maxdepth 1 -name "redis*" -type d')
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
    output, error, status = run_command(client, 'find /usr/local -name "redis.conf" -type f 2>/dev/null')
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
    output, error, status = run_command(client, 'test -f /etc/systemd/system/redis.service')
    if status == 0:
        output, error, status = run_command(client, f'cp -a /etc/systemd/system/redis.service {backup_dir}/')
        if status != 0:
            print_error("备份systemd服务文件失败")
            return None
    
    # 创建备份信息文件
    backup_info = {
        "version": current_version,
        "timestamp": timestamp,
        "backup_dir": backup_dir,
        "redis_binary": redis_binary if status == 0 else None,
        "install_dirs": install_dirs if status == 0 and output.strip() else [],
        "config_files": config_files if status == 0 and output.strip() else [],
        "systemd_service": "/etc/systemd/system/redis.service"
    }
    
    backup_info_file = f"{backup_dir}/backup_info.json"
    backup_info_json = json.dumps(backup_info, indent=2, ensure_ascii=False)
    
    # 写入备份信息文件
    output, error, status = run_command(client, f'cat > {backup_info_file} << EOF\n{backup_info_json}\nEOF')
    if status != 0:
        print_error("创建备份信息文件失败")
        return None
    
    print_success(f"redis备份完成！备份目录: {backup_dir}")
    return backup_info

def rollback_redis(client):
    """回滚redis到之前的版本"""
    print_info("查找可用的redis备份...")
    
    # 查找备份目录
    output, error, status = run_command(client, "find /data/backups -maxdepth 1 -type d -name 'redis_backup_*' 2>/dev/null | sort -r")
    if status != 0 or not output.strip():
        print_warning("未找到任何redis备份")
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
    
    choice = menu_choice("请选择要回滚到的备份编号 (0取消): ", valid_choices=[str(i) for i in range(len(backup_dirs) + 1)], default="0")
    if choice == "0":
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
    print_warning(f"即将回滚redis到版本 {backup_info['version']}")
    print_warning("这将覆盖当前的redis安装")
    if not confirm_yes_no(f"即将回滚redis到版本 {backup_info['version']}\n这将覆盖当前的redis安装\n确认回滚？", default=False):
        print_warning("取消回滚操作")
        return
    
    print_info("开始回滚redis...")
    
    # 停止redis服务
    print_info("停止redis服务...")
    output, status = run_command(client, 'systemctl stop redis 2>/dev/null || pkill redis 2>/dev/null || true')
    
    # 恢复redis二进制文件
    if backup_info.get('redis_binary'):
        print_info("恢复redis二进制文件...")
        output, status = run_command(client, f'cp -a {selected_backup}/redis /usr/bin/redis')
        if status != 0:
            print_error("恢复redis二进制文件失败")
            return
    
    # 恢复安装目录
    if backup_info.get('install_dirs'):
        print_info("恢复redis安装目录...")
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
        output, error, status = run_command(client, f'cp -a {selected_backup}/redis.service /etc/systemd/system/')
        if status == 0:
            output, error, status = run_command(client, 'systemctl daemon-reload')
    
    # 验证回滚
    print_info("验证回滚结果...")
    output, error, status = run_command(client, "redis-cli -v 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1")
    if status == 0:
        rolled_back_version = output.strip()
        if rolled_back_version == backup_info['version']:
            print_success(f"redis回滚成功！当前版本: {rolled_back_version}")
            print_info("建议检查配置文件并手动启动redis服务")
        else:
            print_warning(f"版本不匹配，期望: {backup_info['version']}, 实际: {rolled_back_version}")
    else:
        print_error("回滚后redis无法正常启动")
    
    # 询问是否启动redis
    if confirm_yes_no("是否启动redis服务？", default=False):
        print_info("启动redis服务...")
        output, status = run_command_live(client, 'systemctl start redis')
        if status == 0:
            print_success("redis服务启动成功")
        else:
            print_error("redis服务启动失败，请检查配置")

def list_redis_backups(client):
    print_info("查找redis备份...")
    
    output, error, status = run_command(client, "find /data/backups -maxdepth 1 -type d -name 'redis_backup_*' 2>/dev/null | sort -r")
    if status != 0 or not output.strip():
        print_warning("未找到任何redis备份")
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

def manage_redis(client):
    global current_version, status, stable_version
    current_version, _, status = run_command(client, 'redis-cli -v 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    current_version = current_version.strip() if current_version else ""
    status, info = get_stable_version("http://download.redis.io/releases/", "7.")
    if status == 0:
        stable_version = info
    else:
        print_error(info)
        return
    print_info("Redis最新稳定版为：" + stable_version)
    while True:
        print("=== Redis软件管理 ===")
        if status != 0 or not current_version or current_version == "":
            print("1. 安装 Redis 最新稳定版")
            # TODO: 未来可添加选择版本安装功能
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', '0'], default="0")
            if choice == "1":
                install_redis(client)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
        else:
            print_success("当前Redis版本：" + current_version)
            print("1. 备份当前 Redis 版本")
            print("2. 回滚 Redis 到之前版本")
            print("3. 查看所有备份")
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', '2', '3', '0'], default="0")
            if choice == "1":
                backup_redis(client)
            elif choice == "2":
                rollback_redis(client)
            elif choice == "3":
                list_redis_backups(client)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")