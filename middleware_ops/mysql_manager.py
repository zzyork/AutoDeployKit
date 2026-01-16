import os
import json
import datetime
from colorama import Fore
from utils.file_utils import download_file, upload_file, upload_file_with_vars, get_latest_version
from utils.output import print_info, print_error, print_success, print_warning
from utils.ssh_utils import run_command, run_command_live

def install_mysql8(client):
    choice = input(Fore.MAGENTA + f"是否安装？(y/N): ").strip().lower()
    if choice == "y":
        default_install_path = "/usr/local/mysql" + '.'.join(latest_version.split('.')[:2])
        install_path = input(Fore.MAGENTA + f"请输入MySQL安装目录 (默认: {default_install_path}): ").strip()
        if not install_path:
            install_path = default_install_path
        print_info("MySQL将安装到: " + install_path + "\n")
        
        default_data_dir = "/data/mysql"
        data_dir = input(Fore.MAGENTA + f"请输入MySQL数据目录 (默认: {default_data_dir}): ").strip()
        if not data_dir:
            data_dir = default_data_dir
        print_info("MySQL数据目录: " + data_dir)
        
        default_log_dir = "/var/log/mysql"
        log_dir = input(Fore.MAGENTA + f"请输入MySQL日志目录 (默认: {default_log_dir}): ").strip()
        if not log_dir:
            log_dir = default_log_dir
        print_info("MySQL日志目录: " + log_dir + "\n")
        
        print_info("开始安装Mysql " + latest_version + "......\n")

        print_info("创建mysql用户")
        output, status = run_command_live(client, "getent group mysql || groupadd mysql")
        output, status = run_command_live(client, "id mysql &>/dev/null || useradd -r -g mysql mysql -s /sbin/nologin")
        print_success("创建mysql用户完成。\n")

        print_info("创建数据和日志目录")
        output, status = run_command_live(client, f"mkdir -p {data_dir} && chown -R mysql:mysql {data_dir}")
        output, status = run_command_live(client, f"mkdir -p {log_dir} && chown -R mysql:mysql {log_dir}")
        print_success("创建数据和日志目录完成。\n")

        print_info("开始下载源码包并安装")
        local_path = os.path.join("packages", "mysql-" + latest_version + "-linux-glibc2.28-x86_64.tar.xz")
        url = "https://dev.mysql.com/get/Downloads/MySQL-8.0/mysql-" + latest_version + "-linux-glibc2.28-x86_64.tar.xz"
        remote_path = "/usr/local/src/mysql-" + latest_version + "-linux-glibc2.28-x86_64.tar.xz"

        try:
            download_file(url, local_path)
        except RuntimeError as e:
            print_error(f"下载失败，中止安装: {e}")
            print_warning("返回上一级菜单\n")
            return None
        upload_file(client, local_path, remote_path)
        cmds = [
            "tar xvf " + remote_path + " -C /usr/local/src/",
            "mv /usr/local/src/mysql-" + latest_version + "-linux-glibc2.28-x86_64 " + install_path,
            "chown -R mysql:mysql " + install_path,
            "printf '\nPATH=$PATH:" + install_path + "/bin\nexport PATH\n' >> /etc/profile",
            "source /etc/profile",
        ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        if cmd_status == 0:
            current_version, _, _ = run_command(client, r'mysql -V 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
            current_version = current_version.strip() if current_version else ""
            print_info("\n安装完成！\n当前mysql版本：" + current_version)
            
            choice = input(Fore.MAGENTA + f"是否自动配置my.cnf文件？(y/N): ").strip().lower()
            if choice == "y":
                print_success("正在配置my.cnf文件...")
                local_path = os.path.join("config", "mysql", "my.cnf")
                remote_path = "/etc/my.cnf"
                upload_file_with_vars(client, local_path, remote_path, {'MYSQL_INSTALL_PATH': install_path, 'MYSQL_DATA_DIR': data_dir, 'MYSQL_LOG_DIR': log_dir})
                cmd = "chown mysql:mysql /etc/my.cnf"
                run_command_live(client, cmd)
                print_success("✓ my.cnf文件配置完成")
                print_warning("⚠ 建议首次初始化之前根据实际需求修改my.cnf文件！")
            else:
                print_warning("→ 已跳过my.cnf文件配置")

            choice = input(Fore.MAGENTA + f"是否初始化MySQL服务？(y/N): ").strip().lower()
            if choice == "y":
                print_success("正在初始化MySQL服务，请稍候...")
                run_command_live(client, install_path + "/bin/mysqld --initialize --user=mysql")
                print_success("✓ MySQL服务初始化完成")
                print_info("注意: 初始化完成后会生成临时密码，请查看日志文件获取密码")
                print_info("日志位置: " + data_dir + "/error.log\n")
            else:
                print_warning("→ 已跳过MySQL服务初始化")

            choice = input(Fore.MAGENTA + f"是否配置systemd守护进程？(y/N): ").strip().lower()
            if choice == "y":
                print_success("正在配置systemd守护进程...")
                local_path = os.path.join("config", "mysql", "mysqld.service")
                remote_path = "/etc/systemd/system/mysqld.service"
                upload_file_with_vars(client, local_path, remote_path, {'MYSQL_INSTALL_PATH': install_path, 'MYSQL_DATA_DIR': data_dir, 'MYSQL_LOG_DIR': log_dir})
                run_command_live(client, "systemctl daemon-reload")
                print_success("✓ systemd守护进程配置完成")
            else:
                print_warning("→ 已跳过systemd守护进程配置")

            choice = input(Fore.MAGENTA + f"是否为MySQL服务配置开机自启动？(y/N): ").strip().lower()
            if choice == "y":
                print_success("正在配置开机自启动...")
                run_command_live(client, "systemctl enable mysqld")
                print_success("✓ MySQL服务开机自启动配置完成")
            else:
                print_warning("→ 已跳过开机自启动配置")

            choice = input(Fore.MAGENTA + f"是否启动MySQL服务？(y/N): ").strip().lower()
            if choice == "y":
                print_success("正在启动MySQL服务...")
                _, status = run_command_live(client, "systemctl start mysqld")
                if status != 0:
                    print_error("✗ MySQL服务启动失败！")
                else:
                    print_success("✓ MySQL服务启动成功")
                    default_password, _, _ = run_command(client, "grep -a \"A temporary password is generated\" /var/log/mysql/mysqld-error.log | tail -n1 | awk '{print $NF}'")
                    print_info("请手动连接MySQL并修改初始root密码！")
                    print_info(f"默认root密码为：{default_password}")
            else:
                print_warning("→ 已跳过MySQL服务启动")

    else:
        print_warning(f"返回上一级")

    return None

def upgrade_mysql8(client):
    print_info("开始升级 Mysql 到最新发行版 " + latest_version + "......\n")

    # 先备份当前版本
    print_info("升级前备份当前mysql版本...")
    backup_info = backup_mysql(client)
    if backup_info is None:
        print_warning("备份失败，是否继续升级？")
        choice = input(Fore.MAGENTA + "继续升级？(y/N): ").strip().lower()
        if choice != "y":
            print_warning("取消升级操作")
            return None
    else:
        print_success("备份完成，开始升级...")

    # 获取当前MySQL安装路径
    current_mysql_path, _, _ = run_command(client, "which mysql")
    install_path = current_mysql_path.replace("/bin/mysql", "")
    choice = input("当前MySQL安装路径: " + install_path + "\n是否继续升级？(y/N): ").strip().lower()
    if choice != "y":
        print_warning("返回上一级菜单\n")
        return None

    print_info("开始下载源码包并编译安装")
    local_path = os.path.join("packages", "mysql-" + latest_version + ".tar.gz")
    url = "https://dev.mysql.com/get/Downloads/MySQL-8.0/mysql-" + latest_version + "-linux-glibc2.28-x86_64.tar.xz"
    remote_path = "/usr/local/src/mysql-" + latest_version + ".tar.gz"

    try:
        download_file(url, local_path)
    except RuntimeError as e:
        print_error(f"下载失败，中止升级: {e}")
        print_warning("返回上一级菜单\n")
        return None
    upload_file(client, local_path, remote_path)
    cmds = [
        "tar zxf " + remote_path + " -C /usr/local/src/",
        "cd /usr/local/src/mysql-" + latest_version + "&& ./configure --prefix=" + install_path + " --with-http_stub_status_module --with-http_gzip_static_module --with-http_realip_module --with-http_sub_module --with-http_ssl_module --with-http_v2_module --with-stream",
        "cd /usr/local/src/mysql-" + latest_version + "&& make && make install",
        "ln -fs " + install_path + "/sbin/mysql /usr/bin/mysql"
    ]

    cmd_status = 0
    for cmd in cmds:
        output, cmd_status = run_command_live(client, cmd)
        if cmd_status != 0 :
            print_error(f"\n命令执行失败: {cmd}")
            print_warning("升级失败，是否回滚到之前版本？")
            choice = input(Fore.MAGENTA + "是否回滚？(y/N): ").strip().lower()
            if choice == "y" and backup_info:
                rollback_mysql(client)
            else:
                print_warning("中止当前操作，返回上一级菜单\n")
            break

    if cmd_status == 0:
        current_version, _, _ = run_command(client, r'mysql -V 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
        current_version = current_version.strip() if current_version else ""
        print_success(f"\n升级已完成！\n当前mysql版本: {current_version}")
        print_info("建议在非业务高峰期手动重启mysql")
        
        # 询问是否立即重启
        restart_choice = input(Fore.MAGENTA + "是否立即重启mysql？(y/N): ").strip().lower()
        if restart_choice == "y":
            print_info("重启mysql服务...")
            output, status = run_command_live(client, 'systemctl restart mysqld')
            if status == 0:
                print_success("mysql服务重启成功")
            else:
                print_error("mysql服务重启失败，请检查配置")
                print_warning("如果需要，可以使用回滚功能恢复到之前版本")

def backup_mysql(client):
    """备份当前mysql安装，用于回滚"""
    print_info("开始备份当前mysql安装...")
    
    # 获取当前版本信息
    output, error, status = run_command(client, r'mysql -V | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    if status != 0:
        print_error("无法获取当前mysql版本信息")
        return None
    
    current_version = output.strip() if output else ""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"/data/backups/mysql_backup_{current_version}_{timestamp}"
    
    print_info(f"创建备份目录: {backup_dir}")
    
    # 创建备份目录
    output, error, status = run_command(client, f'mkdir -p {backup_dir}')
    if status != 0:
        print_error(f"创建备份目录失败: {backup_dir}")
        return None
    
    # 备份mysql二进制文件
    print_info("备份mysql二进制文件...")
    output, status = run_command_live(client, 'which mysql')
    if status == 0:
        mysql_binary = output.strip()
        output, error, status = run_command(client, f'cp -a {mysql_binary} {backup_dir}/mysql')
        if status != 0:
            print_error("备份mysql二进制文件失败")
            return None
    else:
        print_error("无法找到mysql二进制文件路径")
        return None
    
    # 备份mysql安装目录
    print_info("备份mysql安装目录...")
    install_dirs = []
    output, error, status = run_command(client, 'find /usr/local -maxdepth 1 -name "mysql*" -type d')
    if status == 0 and output.strip():
        install_dirs = output.strip().split('\n')
        for install_dir in install_dirs:
            if install_dir.strip():
                dir_name = os.path.basename(install_dir.strip())
                output, status = run_command_live(client, f'cp -a {install_dir} {backup_dir}/{dir_name}')
                if status != 0:
                    print_error(f"备份安装目录失败: {install_dir}")
                    return None
    
    # 备份配置文件
    print_info("备份配置文件...")
    config_files = []
    
    # 备份my.cnf
    output, error, status = run_command(client, 'test -f /etc/my.cnf')
    if status == 0:
        config_files.append('/etc/my.cnf')
        output, status = run_command_live(client, f'cp -a /etc/my.cnf {backup_dir}/')
        if status != 0:
            print_error("备份my.cnf文件失败")
            return None
    
    # 备份其他可能的配置文件
    output, error, status = run_command(client, 'find /etc -name "*.cnf" -type f 2>/dev/null | grep mysql')
    if status == 0 and output.strip():
        mysql_configs = output.strip().split('\n')
        for config_file in mysql_configs:
            if config_file.strip() and config_file.strip() != '/etc/my.cnf':
                config_files.append(config_file.strip())
                config_name = os.path.basename(config_file.strip())
                output, status = run_command_live(client, f'cp -a {config_file.strip()} {backup_dir}/{config_name}')
                if status != 0:
                    print_error(f"备份配置文件失败: {config_file.strip()}")
                    return None
    
    # 备份systemd服务文件
    print_info("备份systemd服务文件...")
    output, error, status = run_command(client, 'test -f /etc/systemd/system/mysqld.service')
    if status == 0:
        output, status = run_command_live(client, f'cp -a /etc/systemd/system/mysqld.service {backup_dir}/')
        if status != 0:
            print_error("备份systemd服务文件失败")
            return None
    
    # 备份数据目录（可选，询问用户）
    data_backup_choice = input(Fore.MAGENTA + "是否备份数据目录（可能很大，建议单独备份）？(y/N): ").strip().lower()
    data_dirs = []
    if data_backup_choice == "y":
        print_info("备份数据目录...")
        # 常见的数据目录位置
        possible_data_dirs = ['/data/mysql', '/var/lib/mysql', '/usr/local/mysql/data']
        for data_dir in possible_data_dirs:
            output, error, status = run_command(client, f'test -d {data_dir}')
            if status == 0:
                data_dirs.append(data_dir)
                dir_name = os.path.basename(data_dir)
                output, status = run_command_live(client, f'cp -a {data_dir} {backup_dir}/data_{dir_name}')
                if status != 0:
                    print_error(f"备份数据目录失败: {data_dir}")
                    return None
    
    # 创建备份信息文件
    backup_info = {
        "version": current_version,
        "timestamp": timestamp,
        "backup_dir": backup_dir,
        "mysql_binary": mysql_binary if 'mysql_binary' in locals() else None,
        "install_dirs": install_dirs,
        "config_files": config_files,
        "systemd_service": "/etc/systemd/system/mysqld.service",
        "data_dirs": data_dirs
    }
    
    backup_info_file = f"{backup_dir}/backup_info.json"
    backup_info_json = json.dumps(backup_info, indent=2, ensure_ascii=False)
    
    # 写入备份信息文件
    output, error, status = run_command(client, f'cat > {backup_info_file} << EOF\n{backup_info_json}\nEOF')
    if status != 0:
        print_error("创建备份信息文件失败")
        return None
    
    print_success(f"mysql备份完成！备份目录: {backup_dir}")
    return backup_info

def rollback_mysql(client):
    """回滚mysql到之前的版本"""
    print_info("查找可用的mysql备份...")
    
    # 查找备份目录
    output, error, status = run_command(client, "find /data/backups -maxdepth 1 -type d -name 'mysql_backup_*' 2>/dev/null | sort -r")
    if status != 0 or not output.strip():
        print_warning("未找到任何mysql备份")
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
    
    choice = input(Fore.MAGENTA + "\n请选择要回滚到的备份编号 (0取消): ").strip()
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
    print_warning(f"即将回滚mysql到版本 {backup_info['version']}")
    print_warning("这将覆盖当前的mysql安装")
    confirm = input(Fore.MAGENTA + "确认回滚？(y/N): ").strip().lower()
    if confirm != "y":
        print_warning("取消回滚操作")
        return
    
    print_info("开始回滚mysql...")
    
    # 停止mysql服务
    print_info("停止mysql服务...")
    output, status = run_command_live(client, 'systemctl stop mysqld 2>/dev/null || pkill mysqld 2>/dev/null || true')
    
    # 恢复mysql二进制文件
    if backup_info.get('mysql_binary'):
        print_info("恢复mysql二进制文件...")
        output, status = run_command_live(client, f'cp -a {selected_backup}/mysql /usr/bin/mysql')
        if status != 0:
            print_error("恢复mysql二进制文件失败")
            return
    
    # 恢复安装目录
    if backup_info.get('install_dirs'):
        print_info("恢复mysql安装目录...")
        for install_dir in backup_info['install_dirs']:
            dir_name = os.path.basename(install_dir)
            output, status = run_command_live(client, f'cp -a {selected_backup}/{dir_name} {install_dir}')
            if status != 0:
                print_error(f"恢复安装目录失败: {install_dir}")
                return
    
    # 恢复配置文件
    if backup_info.get('config_files'):
        print_info("恢复配置文件...")
        for config_file in backup_info['config_files']:
            if config_file == '/etc/my.cnf':
                output, status = run_command_live(client, f'cp -a {selected_backup}/my.cnf {config_file}')
            else:
                config_name = os.path.basename(config_file)
                output, status = run_command_live(client, f'cp -a {selected_backup}/{config_name} {config_file}')
            if status != 0:
                print_error(f"恢复配置文件失败: {config_file}")
                return
    
    # 恢复systemd服务文件
    if backup_info.get('systemd_service'):
        print_info("恢复systemd服务文件...")
        output, status = run_command_live(client, f'cp -a {selected_backup}/mysqld.service /etc/systemd/system/')
        if status == 0:
            output, status = run_command_live(client, 'systemctl daemon-reload')
    
    # 验证回滚
    print_info("验证回滚结果...")
    output, error, status = run_command(client, r'mysql -V | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    if status == 0:
        rolled_back_version = output.strip()
        if rolled_back_version == backup_info['version']:
            print_success(f"mysql回滚成功！当前版本: {rolled_back_version}")
            print_info("建议检查配置文件并手动启动mysql服务")
        else:
            print_warning(f"版本不匹配，期望: {backup_info['version']}, 实际: {rolled_back_version}")
    else:
        print_error("回滚后mysql无法正常启动")
    
    # 询问是否启动mysql
    start_choice = input(Fore.MAGENTA + "是否启动mysql服务？(y/N): ").strip().lower()
    if start_choice == "y":
        print_info("启动mysql服务...")
        output, status = run_command_live(client, 'systemctl start mysqld')
        if status == 0:
            print_success("mysql服务启动成功")
        else:
            print_error("mysql服务启动失败，请检查配置")

def list_mysql_backups(client):
    print_info("查找mysql备份...")
    
    output, error, status = run_command(client, "find /data/backups -maxdepth 1 -type d -name 'mysql_backup_*' 2>/dev/null | sort -r")
    if status != 0 or not output.strip():
        print_warning("未找到任何mysql备份")
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
                if backup_info.get('data_dirs'):
                    print(f"   数据目录: {', '.join(backup_info['data_dirs'])}")
                print()
            except:
                print(f"{i}. {os.path.basename(backup_dir)} (信息文件损坏)")
        else:
            print(f"{i}. {os.path.basename(backup_dir)} (无信息文件)")

def manage_mysql(client):
    global current_version, status, latest_version
    current_version, _, status = run_command(client, r'mysql -V 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    current_version = current_version.strip() if current_version else ""
    latest_version = get_latest_version("https://dev.mysql.com/downloads/mysql/8.0.html", "8.0.")
    print_info("Mysql最新发行版为：" + latest_version)
    while True:
        print("=== Mysql软件管理 ===")
        if status != 0 or not current_version or current_version == "":
            print("1. 安装 Mysql 8.0 最新发行版")
            print("0. 返回/跳过")
            choice = input("请选择操作编号: ")
            if choice == "1":
                install_mysql8(client)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
        else:
            print_success("当前Mysql版本：" + current_version)
            latest_version = get_stable_mysql()
            print_info("Mysql最新发行版为：" + latest_version)
            print("1. 升级 Mysql 到最新发行版")
            print("2. 备份当前 Mysql 版本")
            print("3. 回滚 Mysql 到之前版本")
            print("4. 查看所有备份")
            print("0. 返回/跳过")
            choice = input("请选择操作编号: ").strip()
            if choice == "1":
                upgrade_mysql8(client)
            elif choice == "2":
                backup_mysql(client)
            elif choice == "3":
                rollback_mysql(client)
            elif choice == "4":
                list_mysql_backups(client)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
        
        # 重新获取版本状态
        current_version, _, status = run_command(client, r'mysql -V 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
        current_version = current_version.strip() if current_version else ""