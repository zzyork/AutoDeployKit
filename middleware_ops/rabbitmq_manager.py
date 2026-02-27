import os
import json
import datetime
from colorama import Fore
from utils.file_utils import download_file, upload_file, upload_file_with_vars, get_stable_version, get_eol_date
from utils.output import print_info, print_error, print_success, print_warning
from utils.ssh_utils import run_command, run_command_live
from utils.choice import confirm_yes_no, menu_choice

def install_rabbitmq(client, version=None):

    if confirm_yes_no("是否确定安装？", default=False):
        default_install_path = "/usr/local/rabbitmq" + '.'.join(version.split('.')[:2])
        install_path = input(Fore.MAGENTA + f"请输入RabbitMQ安装目录 (默认: {default_install_path}): ").strip()
        if not install_path:
            install_path = default_install_path
        print_info("RabbitMQ将安装到: " + install_path + "\n")
        
        default_data_dir = "/data/rabbitmq"
        data_dir = input(Fore.MAGENTA + f"请输入RabbitMQ数据目录 (默认: {default_data_dir}): ").strip()
        if not data_dir:
            data_dir = default_data_dir
        print_info("RabbitMQ数据目录: " + data_dir)
        
        default_log_dir = "/var/log/rabbitmq"
        log_dir = input(Fore.MAGENTA + f"请输入RabbitMQ日志目录 (默认: {default_log_dir}): ").strip()
        if not log_dir:
            log_dir = default_log_dir
        print_info("RabbitMQ日志目录: " + log_dir + "\n")
        
        print_info("开始安装RabbitMQ " + version + "......\n")

        print_info("创建rabbitmq用户")
        output, status = run_command_live(client, "getent group rabbitmq || groupadd rabbitmq")
        output, status = run_command_live(client, "id rabbitmq &>/dev/null || useradd -r -g rabbitmq rabbitmq -s /sbin/nologin")
        print_success("创建rabbitmq用户完成。\n")

        print_info("创建数据和日志目录")
        output, status = run_command_live(client, f"mkdir -p {data_dir} && chown -R rabbitmq:rabbitmq {data_dir}")
        output, status = run_command_live(client, f"mkdir -p {log_dir} && chown -R rabbitmq:rabbitmq {log_dir}")
        print_success("创建数据和日志目录完成。\n")

        print_info("开始下载源码包并安装")
        local_path = os.path.join("packages", "rabbitmq-" + version + "-linux-glibc2.28-x86_64.tar.xz")
        url = "https://dev.rabbitmq.com/get/Downloads/RabbitMQ-8.0/rabbitmq-" + version + "-linux-glibc2.28-x86_64.tar.xz"
        remote_path = "/usr/local/src/rabbitmq-" + version + "-linux-glibc2.28-x86_64.tar.xz"

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
            "tar xvf " + remote_path + " -C /usr/local/src/",
            "mv /usr/local/src/rabbitmq-" + version + "-linux-glibc2.28-x86_64 " + install_path,
            "chown -R rabbitmq:rabbitmq " + install_path,
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
            current_version, _, _ = run_command(client, r'rabbitmq -V 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
            current_version = current_version.strip() if current_version else ""
            print_info("\n安装完成！\n当前rabbitmq版本：" + current_version)
            
            if confirm_yes_no("是否自动配置my.cnf文件？", default=False):
                print_success("正在配置my.cnf文件...")
                local_path = os.path.join("config", "rabbitmq", "my.cnf")
                remote_path = "/etc/my.cnf"
                upload_file_with_vars(client, local_path, remote_path, {'MYSQL_INSTALL_PATH': install_path, 'MYSQL_DATA_DIR': data_dir, 'MYSQL_LOG_DIR': log_dir})
                cmd = "chown rabbitmq:rabbitmq /etc/my.cnf"
                run_command_live(client, cmd)
                print_success("✓ my.cnf文件配置完成")
                print_warning("⚠ 建议首次初始化之前根据实际需求修改my.cnf文件！")
            else:
                print_warning("→ 已跳过my.cnf文件配置")

            if confirm_yes_no("是否初始化RabbitMQ服务？", default=False):
                print_success("正在初始化RabbitMQ服务，请稍候...")
                run_command_live(client, install_path + "/bin/rabbitmqd --initialize --user=rabbitmq")
                print_success("✓ RabbitMQ服务初始化完成")
                print_info("注意: 初始化完成后会生成临时密码，请查看日志文件获取密码")
                print_info("日志位置: " + data_dir + "/error.log\n")
            else:
                print_warning("→ 已跳过RabbitMQ服务初始化")

            if confirm_yes_no("是否配置systemd守护进程？", default=False):
                print_success("正在配置systemd守护进程...")
                local_path = os.path.join("config", "rabbitmq", "rabbitmqd.service")
                remote_path = "/etc/systemd/system/rabbitmqd.service"
                upload_file_with_vars(client, local_path, remote_path, {'MYSQL_INSTALL_PATH': install_path, 'MYSQL_DATA_DIR': data_dir, 'MYSQL_LOG_DIR': log_dir})
                run_command_live(client, "systemctl daemon-reload")
                print_success("✓ systemd守护进程配置完成")
            else:
                print_warning("→ 已跳过systemd守护进程配置")

            if confirm_yes_no("是否为RabbitMQ服务配置开机自启动？", default=False):
                print_success("正在配置开机自启动...")
                run_command_live(client, "systemctl enable rabbitmqd")
                print_success("✓ RabbitMQ服务开机自启动配置完成")
            else:
                print_warning("→ 已跳过开机自启动配置")

            if confirm_yes_no("是否启动RabbitMQ服务？", default=False):
                print_success("正在启动RabbitMQ服务...")
                _, status = run_command_live(client, "systemctl start rabbitmqd")
                if status != 0:
                    print_error("✗ RabbitMQ服务启动失败！")
                else:
                    print_success("✓ RabbitMQ服务启动成功")
                    default_password, _, _ = run_command(client, "grep -a \"A temporary password is generated\" /var/log/rabbitmq/rabbitmqd-error.log | tail -n1 | awk '{print $NF}'")
                    print_info("请手动连接RabbitMQ并修改初始root密码！")
                    print_info(f"默认root密码为：{default_password}")
            else:
                print_warning("→ 已跳过RabbitMQ服务启动")

    else:
        print_warning(f"返回上一级")

    return None

def upgrade_rabbitmq(client, version=None):
    # TODO：实现升级逻辑
    pass
    # print_info("开始升级 RabbitMQ 到最新发行版 " + version + "......\n")

    # # 先备份当前版本
    # print_info("升级前备份当前rabbitmq版本...")
    # backup_info = backup_rabbitmq(client)
    # if backup_info is None:
    #     print_warning("备份失败，是否继续升级？")
    #     if not confirm_yes_no("继续升级？", default=False):
    #         print_warning("取消升级操作")
    #         return None
    # else:
    #     print_success("备份完成，开始升级...")

    # # 获取当前RabbitMQ安装路径
    # current_rabbitmq_path, _, _ = run_command(client, "which rabbitmq")
    # install_path = current_rabbitmq_path.replace("/bin/rabbitmq", "")
    # if not confirm_yes_no(f"当前RabbitMQ安装路径: {install_path}\n是否继续升级？", default=False):
    #     print_warning("返回上一级菜单\n")
    #     return None

    # print_info("开始下载源码包并编译安装")
    # local_path = os.path.join("packages", "rabbitmq-" + version + ".tar.gz")
    # url = "https://dev.rabbitmq.com/get/Downloads/RabbitMQ-8.0/rabbitmq-" + version + "-linux-glibc2.28-x86_64.tar.xz"
    # remote_path = "/usr/local/src/rabbitmq-" + version + ".tar.gz"

    # try:
    #     download_file(url, local_path)
    # except RuntimeError as e:
    #     print_error(f"下载失败，中止升级: {e}")
    #     print_warning("返回上一级菜单\n")
    #     return None
    # upload_file(client, local_path, remote_path)
    # cmds = [
    #     "tar zxf " + remote_path + " -C /usr/local/src/",
    #     "cd /usr/local/src/rabbitmq-" + version + "&& ./configure --prefix=" + install_path + " --with-http_stub_status_module --with-http_gzip_static_module --with-http_realip_module --with-http_sub_module --with-http_ssl_module --with-http_v2_module --with-stream",
    #     "cd /usr/local/src/rabbitmq-" + version + "&& make && make install",
    #     "ln -fs " + install_path + "/sbin/rabbitmq /usr/bin/rabbitmq"
    # ]

    # cmd_status = 0
    # for cmd in cmds:
    #     output, cmd_status = run_command_live(client, cmd)
    #     if cmd_status != 0 :
    #         print_error(f"\n命令执行失败: {cmd}")
    #         print_warning("升级失败，是否回滚到之前版本？")
    #         if confirm_yes_no("是否回滚？", default=False) and backup_info:
    #             rollback_rabbitmq(client)
    #         else:
    #             print_warning("中止当前操作，返回上一级菜单\n")
    #         break

    # if cmd_status == 0:
    #     current_version, _, _ = run_command(client, r'rabbitmq -V 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    #     current_version = current_version.strip() if current_version else ""
    #     print_success(f"\n升级已完成！\n当前rabbitmq版本: {current_version}")
    #     print_info("建议在非业务高峰期手动重启rabbitmq")
        
    #     # 询问是否立即重启
    #     if confirm_yes_no("是否立即重启rabbitmq？", default=False):
    #         print_info("重启rabbitmq服务...")
    #         output, status = run_command_live(client, 'systemctl restart rabbitmqd')
    #         if status == 0:
    #             print_success("rabbitmq服务重启成功")
    #         else:
    #             print_error("rabbitmq服务重启失败，请检查配置")
    #             print_warning("如果需要，可以使用回滚功能恢复到之前版本")

def backup_rabbitmq(client):
    """备份当前rabbitmq安装，用于回滚"""
    print_info("开始备份当前rabbitmq安装...")
    
    # 获取当前版本信息
    output, error, status = run_command(client, r'rabbitmq -V | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    if status != 0:
        print_error("无法获取当前rabbitmq版本信息")
        return None
    
    current_version = output.strip() if output else ""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"/data/backups/rabbitmq_backup_{current_version}_{timestamp}"
    
    print_info(f"创建备份目录: {backup_dir}")
    
    # 创建备份目录
    output, error, status = run_command(client, f'mkdir -p {backup_dir}')
    if status != 0:
        print_error(f"创建备份目录失败: {backup_dir}")
        return None
    
    # 备份rabbitmq二进制文件
    print_info("备份rabbitmq二进制文件...")
    output, status = run_command_live(client, 'which rabbitmq')
    if status == 0:
        rabbitmq_binary = output.strip()
        output, error, status = run_command(client, f'cp -a {rabbitmq_binary} {backup_dir}/rabbitmq')
        if status != 0:
            print_error("备份rabbitmq二进制文件失败")
            return None
    else:
        print_error("无法找到rabbitmq二进制文件路径")
        return None
    
    # 备份rabbitmq安装目录
    print_info("备份rabbitmq安装目录...")
    install_dirs = []
    output, error, status = run_command(client, 'find /usr/local -maxdepth 1 -name "rabbitmq*" -type d')
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
    output, error, status = run_command(client, 'find /etc -name "*.cnf" -type f 2>/dev/null | grep rabbitmq')
    if status == 0 and output.strip():
        rabbitmq_configs = output.strip().split('\n')
        for config_file in rabbitmq_configs:
            if config_file.strip() and config_file.strip() != '/etc/my.cnf':
                config_files.append(config_file.strip())
                config_name = os.path.basename(config_file.strip())
                output, status = run_command_live(client, f'cp -a {config_file.strip()} {backup_dir}/{config_name}')
                if status != 0:
                    print_error(f"备份配置文件失败: {config_file.strip()}")
                    return None
    
    # 备份systemd服务文件
    print_info("备份systemd服务文件...")
    output, error, status = run_command(client, 'test -f /etc/systemd/system/rabbitmqd.service')
    if status == 0:
        output, status = run_command_live(client, f'cp -a /etc/systemd/system/rabbitmqd.service {backup_dir}/')
        if status != 0:
            print_error("备份systemd服务文件失败")
            return None
    
    # 备份数据目录（可选，询问用户）
    data_dirs = []
    if confirm_yes_no("是否备份数据目录（可能很大，建议单独备份）？", default=False):
        print_info("备份数据目录...")
        # 常见的数据目录位置
        possible_data_dirs = ['/data/rabbitmq', '/var/lib/rabbitmq', '/usr/local/rabbitmq/data']
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
        "rabbitmq_binary": rabbitmq_binary if 'rabbitmq_binary' in locals() else None,
        "install_dirs": install_dirs,
        "config_files": config_files,
        "systemd_service": "/etc/systemd/system/rabbitmqd.service",
        "data_dirs": data_dirs
    }
    
    backup_info_file = f"{backup_dir}/backup_info.json"
    backup_info_json = json.dumps(backup_info, indent=2, ensure_ascii=False)
    
    # 写入备份信息文件
    output, error, status = run_command(client, f'cat > {backup_info_file} << EOF\n{backup_info_json}\nEOF')
    if status != 0:
        print_error("创建备份信息文件失败")
        return None
    
    print_success(f"rabbitmq备份完成！备份目录: {backup_dir}")
    return backup_info

def rollback_rabbitmq(client):
    """回滚rabbitmq到之前的版本"""
    print_info("查找可用的rabbitmq备份...")
    
    # 查找备份目录
    output, error, status = run_command(client, "find /data/backups -maxdepth 1 -type d -name 'rabbitmq_backup_*' 2>/dev/null | sort -r")
    if status != 0 or not output.strip():
        print_warning("未找到任何rabbitmq备份")
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
    
    choice = menu_choice("\n请选择要回滚到的备份编号 (0取消): ", valid_choices=[str(i) for i in range(len(backup_dirs) + 1)], default="0")
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
    print_warning(f"即将回滚rabbitmq到版本 {backup_info['version']}")
    print_warning("这将覆盖当前的rabbitmq安装")
    if not confirm_yes_no(f"即将回滚rabbitmq到版本 {backup_info['version']}\n这将覆盖当前的rabbitmq安装\n确认回滚？", default=False):
        print_warning("取消回滚操作")
        return
    
    print_info("开始回滚rabbitmq...")
    
    # 停止rabbitmq服务
    print_info("停止rabbitmq服务...")
    output, status = run_command_live(client, 'systemctl stop rabbitmqd 2>/dev/null || pkill rabbitmqd 2>/dev/null || true')
    
    # 恢复rabbitmq二进制文件
    if backup_info.get('rabbitmq_binary'):
        print_info("恢复rabbitmq二进制文件...")
        output, status = run_command_live(client, f'cp -a {selected_backup}/rabbitmq /usr/bin/rabbitmq')
        if status != 0:
            print_error("恢复rabbitmq二进制文件失败")
            return
    
    # 恢复安装目录
    if backup_info.get('install_dirs'):
        print_info("恢复rabbitmq安装目录...")
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
        output, status = run_command_live(client, f'cp -a {selected_backup}/rabbitmqd.service /etc/systemd/system/')
        if status == 0:
            output, status = run_command_live(client, 'systemctl daemon-reload')
    
    # 验证回滚
    print_info("验证回滚结果...")
    output, error, status = run_command(client, r'rabbitmq -V | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    if status == 0:
        rolled_back_version = output.strip()
        if rolled_back_version == backup_info['version']:
            print_success(f"rabbitmq回滚成功！当前版本: {rolled_back_version}")
            print_info("建议检查配置文件并手动启动rabbitmq服务")
        else:
            print_warning(f"版本不匹配，期望: {backup_info['version']}, 实际: {rolled_back_version}")
    else:
        print_error("回滚后rabbitmq无法正常启动")
    
    # 询问是否启动rabbitmq
    if confirm_yes_no("是否启动rabbitmq服务？", default=False):
        print_info("启动rabbitmq服务...")
        output, status = run_command_live(client, 'systemctl start rabbitmqd')
        if status == 0:
            print_success("rabbitmq服务启动成功")
        else:
            print_error("rabbitmq服务启动失败，请检查配置")

def list_rabbitmq_backups(client):
    print_info("查找rabbitmq备份...")
    
    output, error, status = run_command(client, "find /data/backups -maxdepth 1 -type d -name 'rabbitmq_backup_*' 2>/dev/null | sort -r")
    if status != 0 or not output.strip():
        print_warning("未找到任何rabbitmq备份")
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

def manage_rabbitmq(client):
    global current_version, status, lts_version
    current_version, _, status = run_command(client, r'rabbitmq -V 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    current_version = current_version.strip() if current_version else ""
    try:
        status, info = get_stable_version("https://dev.rabbitmq.com/downloads/rabbitmq/8.0.html", "8.0.")
    except Exception:
        status, info = get_stable_version("https://dev.rabbitmq.com/downloads/rabbitmq/", "8.0.")
    if status == 0:
        lts_version = info
        print_info("RabbitMQ最新LTS版本为：" + lts_version)
    else:
        print_error(info)
        return
    while True:
        print("========== RabbitMQ软件管理 ==========")
        if status != 0 or not current_version or current_version == "":
            print("1. 安装 RabbitMQ 8.0 最新LTS版本")
            print("2. 安装其他版本的 RabbitMQ （手动指定版本号）")
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', '2', '0'], default="0")
            if choice == "1":
                install_rabbitmq(client, version=lts_version)
            elif choice == "2":
                while True:
                    input_version = input(Fore.MAGENTA + "请输入要安装的RabbitMQ版本号 (例如 8.0.33): ").strip()
                    try:
                        status, info = get_stable_version("https://downloads.rabbitmq.com/archives/community/", input_version)
                    except Exception:
                        status, info = get_stable_version("https://dev.rabbitmq.com/downloads/rabbitmq/", input_version)
                    if status == 0:
                        version = info
                        break
                    else:
                        print_error(info)
                eol = get_eol_date("rabbitmq", version)
                if eol != "Unknown":
                    print_warning(f"注意: {eol}")
                install_rabbitmq(client, version=input_version)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
        else:
            print_success("当前RabbitMQ版本：" + current_version)
            print_info("RabbitMQ最新LTS版本为：" + lts_version)
            print("1. 升级 RabbitMQ 到最新LTS版本")
            print("2. 备份当前 RabbitMQ 版本")
            print("3. 回滚 RabbitMQ 到之前版本")
            print("4. 查看所有备份")
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', '2', '3', '4', '0'], default="0")
            if choice == "1":
                upgrade_rabbitmq(client)
            elif choice == "2":
                backup_rabbitmq(client)
            elif choice == "3":
                rollback_rabbitmq(client)
            elif choice == "4":
                list_rabbitmq_backups(client)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
