import os
import json
import datetime
import shlex
import posixpath
from colorama import Fore
from utils.file_utils import download_file, upload_file, upload_file_with_vars, get_stable_version, get_eol_date
from utils.output import print_info, print_error, print_success, print_warning
from utils.ssh_utils import run_command, run_command_live
from utils.choice import confirm_yes_no, menu_choice


NGINX_VERSION_CMD = r'nginx -v 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1'


def _shell_quote(value):
    return shlex.quote(str(value))


def _normalize_remote_path(path):
    """Normalize a Linux remote path that may contain Windows-style backslashes."""
    return str(path).strip().replace('\\', '/')


def _remote_join(*parts):
    """Join Linux remote path fragments regardless of the local OS."""
    return posixpath.join(*(_normalize_remote_path(part) for part in parts))


def _remote_dirname(path):
    return posixpath.dirname(_normalize_remote_path(path))


def _remote_basename(path):
    return posixpath.basename(_normalize_remote_path(path))


def _validate_nginx_version(version):
    if not version:
        raise ValueError("Nginx版本号不能为空")
    if not all(part.isdigit() for part in version.split('.')) or len(version.split('.')) < 2:
        raise ValueError(f"Nginx版本号格式不正确: {version}")


def _nginx_install_path(version):
    return "/usr/local/nginx" + '.'.join(version.split('.')[:2])


def _get_current_nginx_binary(client):
    output, _, status = run_command(client, 'readlink -f /usr/bin/nginx')
    return output.strip() if status == 0 and output.strip() else ""


def _get_nginx_prefix(client, nginx_binary):
    if nginx_binary:
        output, _, status = run_command(
            client,
            f'{_shell_quote(nginx_binary)} -V 2>&1 | tr " " "\\n" | grep -m1 "^--prefix=" | cut -d= -f2-'
        )
        if status == 0 and output.strip():
            return output.strip()
        return _remote_dirname(_remote_dirname(nginx_binary.rstrip('/')))
    return ""


def _get_systemd_service_conf(client):
    output, _, status = run_command(
        client,
        "systemctl cat nginx 2>/dev/null | grep -E '^[[:space:]]*ExecStart=' | head -n1 | grep -oE -- '-c[[:space:]]+[^[:space:]]+' | awk '{print $2}'"
    )
    return output.strip() if status == 0 and output.strip() else ""


def _get_nginx_conf_path(client, nginx_binary, nginx_prefix):
    conf_path = _get_systemd_service_conf(client)
    if conf_path:
        return conf_path

    if nginx_binary:
        output, _, status = run_command(
            client,
            f'{_shell_quote(nginx_binary)} -V 2>&1 | tr " " "\\n" | grep -m1 "^--conf-path=" | cut -d= -f2-'
        )
        if status == 0 and output.strip():
            return output.strip()

    return _remote_join(nginx_prefix, "conf", "nginx.conf") if nginx_prefix else ""


def _get_nginx_configure_args(client, nginx_binary, new_install_path):
    if not nginx_binary:
        return ""

    output, _, status = run_command(client, f'{_shell_quote(nginx_binary)} -V 2>&1')
    if status != 0 or "configure arguments:" not in output:
        return ""

    args = output.split("configure arguments:", 1)[1].strip()
    if not args:
        return ""

    parts = shlex.split(args)
    filtered = [part for part in parts if not part.startswith("--prefix=")]
    return " ".join([f"--prefix={_shell_quote(new_install_path)}", *(_shell_quote(part) for part in filtered)])


def _copy_nginx_conf_dir(client, old_prefix, new_install_path):
    if not old_prefix or old_prefix == new_install_path:
        return True
    old_conf_dir = _remote_join(old_prefix, "conf")
    new_conf_dir = _remote_join(new_install_path, "conf")
    output, _, status = run_command(client, f'test -d {_shell_quote(old_conf_dir)}')
    if status != 0:
        print_warning(f"未找到旧配置目录，跳过配置目录迁移: {old_conf_dir}")
        return True

    print_info(f"迁移旧配置目录到新安装目录: {old_conf_dir} -> {new_conf_dir}")
    _, status = run_command_live(client, f'cp -a {_shell_quote(old_conf_dir)}/. {_shell_quote(new_conf_dir)}/')
    if status != 0:
        print_error("迁移nginx配置目录失败")
        return False
    return True

def install_nginx(client, version=None):

    try:
        _validate_nginx_version(version)
    except ValueError as e:
        print_error(str(e))
        return None

    if confirm_yes_no("是否确定安装？", default=False):
        # 提示输入Nginx安装目录
        default_install_path = _nginx_install_path(version)
        install_path = input(Fore.MAGENTA + f"请输入Nginx安装目录 (默认: {default_install_path}): ").strip()
        if not install_path:
            install_path = default_install_path
        install_path = _normalize_remote_path(install_path)
        print_info("Nginx将安装到: " + install_path)
        
        # 提示输入日志目录
        default_log_dir = "/data/logs/nginx"
        log_dir = input(Fore.MAGENTA + f"请输入Nginx日志目录 (默认: {default_log_dir}): ").strip()
        if not log_dir:
            log_dir = default_log_dir
        log_dir = _normalize_remote_path(log_dir)
        print_info("Nginx日志目录: " + log_dir + "\n")
        
        print_info("开始安装Nginx " + version + "......\n")

        print_info("创建nginx用户")
        output, status = run_command_live(client, "getent group nginx || groupadd nginx")
        output, status = run_command_live(client, "id nginx &>/dev/null || useradd -r -g nginx nginx")
        print_success("创建nginx用户完成。\n")

        print_info("安装依赖")
        output, status = run_command_live(client, 'dnf -y install make zlib zlib-devel gcc-c++ libtool pcre2-devel')
        print_success("perl安装完成。\n")

        print_info("开始下载源码包并编译安装")
        local_path = os.path.join("packages", "nginx-" + version + ".tar.gz")
        url = "https://nginx.org/download/nginx-" + version + ".tar.gz"
        remote_path = "/usr/local/src/nginx-" + version + ".tar.gz"

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
            "cd /usr/local/src/nginx-" + version + " && ./configure --prefix=" + _shell_quote(install_path) + " --with-http_stub_status_module --with-http_gzip_static_module --with-http_realip_module --with-http_sub_module --with-http_ssl_module --with-http_v2_module --with-stream",
            "cd /usr/local/src/nginx-" + version + " && make && make install",
            "ln -fs " + _shell_quote(_remote_join(install_path, "sbin", "nginx")) + " /usr/bin/nginx",
            "mkdir -p " + _shell_quote(_remote_join(install_path, "conf", "conf.d")),
        ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        if cmd_status == 0:
            current_version,_, _ = run_command(client, NGINX_VERSION_CMD)
            current_version = current_version.strip() if current_version else ""
            print_info("安装完成！当前nginx版本：" + current_version)
            if confirm_yes_no("是否自动调整nginx.conf文件？", default=False):
                local_path = os.path.join("config", "nginx", "nginx.conf")
                remote_path = _remote_join(install_path, "conf", "nginx.conf")
                upload_file_with_vars(client, local_path, remote_path, {'NGINX_INSTALL_PATH': install_path, 'NGINX_LOG_DIR': log_dir})
                print_success("✓ nginx.conf配置完成\n")
            if confirm_yes_no("\n是否配置systemd守护进程？", default=False):
                local_path = os.path.join("config", "nginx", "nginx.service")
                remote_path = "/etc/systemd/system/nginx.service"
                upload_file_with_vars(client, local_path, remote_path, {'install_path': install_path})
                
                # 执行systemd相关命令
                systemd_cmds = [
                    "systemctl daemon-reload",
                    f"mkdir -p {_shell_quote(log_dir)}",
                    "systemctl enable --now nginx",
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

def upgrade_nginx(client, version=None):
    try:
        _validate_nginx_version(version)
    except ValueError as e:
        print_error(str(e))
        return None

    print_info("开始升级 Nginx 到最新发行版 " + version + "......\n")

    current_binary = _get_current_nginx_binary(client)
    current_prefix = _get_nginx_prefix(client, current_binary)
    current_conf = _get_nginx_conf_path(client, current_binary, current_prefix)

    # 先备份当前版本
    print_info("升级前备份当前nginx版本...")
    backup_info = backup_nginx(client)
    if backup_info is None:
        print_warning("备份失败，是否继续升级？")
        if not confirm_yes_no("继续升级？", default=False):
            print_warning("取消升级操作")
            return None
    else:
        print_success("备份完成，开始升级...")

    print_info("开始下载源码包并编译安装")
    local_path = os.path.join("packages", "nginx-" + version + ".tar.gz")
    url = "https://nginx.org/download/nginx-" + version + ".tar.gz"
    remote_path = "/usr/local/src/nginx-" + version + ".tar.gz"
    install_path = _nginx_install_path(version)

    wget_cmd = f"wget -O {_shell_quote(remote_path)} {_shell_quote(url)}"
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
            print_error(f"本地上传也失败，中止升级: {e}")
            print_warning("返回上一级菜单\n")
            return None
    
    configure_args = _get_nginx_configure_args(client, current_binary, install_path)
    if not configure_args:
        print_warning("无法读取旧版nginx编译参数，将使用默认编译参数")
        configure_args = " ".join([
            f"--prefix={_shell_quote(install_path)}",
            "--with-http_stub_status_module",
            "--with-http_gzip_static_module",
            "--with-http_realip_module",
            "--with-http_sub_module",
            "--with-http_ssl_module",
            "--with-http_v2_module",
            "--with-stream",
        ])

    source_dir = f"/usr/local/src/nginx-{version}"
    cmds = [
        f"tar zxf {_shell_quote(remote_path)} -C /usr/local/src/",
        f"cd {_shell_quote(source_dir)} && ./configure {configure_args}",
        f"cd {_shell_quote(source_dir)} && make && make install",
    ]

    cmd_status = 0
    for cmd in cmds:
        output, cmd_status = run_command_live(client, cmd)
        if cmd_status != 0 :
            print_error(f"\n命令执行失败: {cmd}")
            print_warning("升级失败，是否回滚到之前版本？")
            if confirm_yes_no("是否回滚？", default=False) and backup_info:
                rollback_nginx(client)
            else:
                print_warning("中止当前操作，返回上一级菜单\n")
            break

    if cmd_status == 0:
        if not _copy_nginx_conf_dir(client, current_prefix, install_path):
            return None

        new_binary = _remote_join(install_path, "sbin", "nginx")
        test_conf = current_conf or _remote_join(install_path, "conf", "nginx.conf")
        print_info("使用新版本nginx测试当前配置...")
        _, test_status = run_command_live(client, f'{_shell_quote(new_binary)} -t -c {_shell_quote(test_conf)}')
        if test_status != 0:
            print_error("新版本nginx配置测试失败，未切换/usr/bin/nginx")
            print_warning("请检查配置兼容性；如需恢复，可使用回滚功能")
            return None

        output, link_status = run_command_live(client, f'ln -fs {_shell_quote(new_binary)} /usr/bin/nginx')
        if link_status != 0:
            print_error("更新/usr/bin/nginx软链接失败")
            return None

        if os.path.exists(os.path.join("config", "nginx", "nginx.service")):
            print_info("更新systemd服务文件以指向新安装目录...")
            local_service_path = os.path.join("config", "nginx", "nginx.service")
            remote_service_path = "/etc/systemd/system/nginx.service"
            upload_file_with_vars(client, local_service_path, remote_service_path, {'install_path': install_path})
            _, reload_status = run_command_live(client, 'systemctl daemon-reload')
            if reload_status != 0:
                print_error("systemd daemon-reload失败，请手动检查nginx.service")
                return None

        current_version, _, status = run_command(client, NGINX_VERSION_CMD)
        current_version = current_version.strip() if current_version else ""
        print_success(f"\n升级已完成！\n当前nginx版本: {current_version}")
        print_info("建议在非业务高峰期手动重启nginx")
        
        # 询问是否立即重启
        if confirm_yes_no("是否立即重启nginx？", default=False):
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
    nginx_binary = ""
    install_dirs = []
    config_files = []
    systemd_service = None
    
    # 获取当前版本信息
    output, error, status = run_command(client, NGINX_VERSION_CMD)
    if status != 0:
        print_error("无法获取当前nginx版本信息")
        return None
    
    current_version = output.strip() if output else ""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"/data/backups/nginx_backup_{current_version}_{timestamp}"
    
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
        output, error, status = run_command(client, f'cp -a {_shell_quote(nginx_binary)} {_shell_quote(backup_dir)}/nginx')
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
        install_dirs = [item.strip() for item in output.strip().split('\n') if item.strip()]
        for install_dir in install_dirs:
            dir_name = _remote_basename(install_dir)
            output, error, status = run_command(client, f'cp -a {_shell_quote(install_dir)} {_shell_quote(backup_dir)}/{_shell_quote(dir_name)}')
            if status != 0:
                print_error(f"备份安装目录失败: {install_dir}")
                return None
    
    # 备份配置文件
    print_info("备份配置文件...")
    output, error, status = run_command(client, 'find /usr/local -name "nginx.conf" -type f 2>/dev/null')
    if status == 0 and output.strip():
        config_files = [item.strip() for item in output.strip().split('\n') if item.strip()]
        for config_file in config_files:
            rel_path = config_file.replace('/usr/local/', '')
            backup_config_path = f"{backup_dir}/conf_{_remote_basename(rel_path)}"
            output, error, status = run_command(client, f'cp -a {_shell_quote(config_file)} {_shell_quote(backup_config_path)}')
            if status != 0:
                print_error(f"备份配置文件失败: {config_file}")
                return None
    
    # 备份systemd服务文件
    print_info("备份systemd服务文件...")
    output, error, status = run_command(client, 'test -f /etc/systemd/system/nginx.service')
    if status == 0:
        systemd_service = "/etc/systemd/system/nginx.service"
        output, error, status = run_command(client, f'cp -a /etc/systemd/system/nginx.service {_shell_quote(backup_dir)}/')
        if status != 0:
            print_error("备份systemd服务文件失败")
            return None
    
    # 创建备份信息文件
    backup_info = {
        "version": current_version,
        "timestamp": timestamp,
        "backup_dir": backup_dir,
        "nginx_binary": nginx_binary,
        "install_dirs": install_dirs,
        "config_files": config_files,
        "systemd_service": systemd_service
    }
    
    backup_info_file = f"{backup_dir}/backup_info.json"
    backup_info_json = json.dumps(backup_info, indent=2, ensure_ascii=False)
    
    # 写入备份信息文件
    output, error, status = run_command(client, f'cat > {_shell_quote(backup_info_file)} << EOF\n{backup_info_json}\nEOF')
    if status != 0:
        print_error("创建备份信息文件失败")
        return None
    
    print_success(f"nginx备份完成！备份目录: {backup_dir}")
    return backup_info

def rollback_nginx(client):
    """回滚nginx到之前的版本"""
    print_info("查找可用的nginx备份...")
    
    # 查找备份目录
    output, error, status = run_command(client, "find /data/backups -maxdepth 1 -type d -name 'nginx_backup_*' 2>/dev/null | sort -r")
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
                print(f"{i}. {_remote_basename(backup_dir)} (信息文件损坏)")
        else:
            print(f"{i}. {_remote_basename(backup_dir)} (无信息文件)")
    
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
    print_warning(f"即将回滚nginx到版本 {backup_info['version']}")
    print_warning("这将覆盖当前的nginx安装")
    if not confirm_yes_no(f"即将回滚nginx到版本 {backup_info['version']}\n这将覆盖当前的nginx安装\n确认回滚？", default=False):
        print_warning("取消回滚操作")
        return
    
    print_info("开始回滚nginx...")
    print_warning("回滚过程不会执行停止或杀进程操作；如需切换运行中服务，请在回滚后按提示确认重启。")
    
    # 恢复nginx二进制文件
    if backup_info.get('nginx_binary'):
        print_info("恢复nginx二进制文件...")
        output, _, status = run_command(client, f'cp -a {_shell_quote(selected_backup)}/nginx /usr/bin/nginx')
        if status != 0:
            print_error("恢复nginx二进制文件失败")
            return
    
    # 恢复安装目录
    if backup_info.get('install_dirs'):
        print_info("恢复nginx安装目录...")
        for install_dir in backup_info['install_dirs']:
            dir_name = _remote_basename(install_dir)
            output, _, status = run_command(client, f'cp -a {_shell_quote(selected_backup)}/{_shell_quote(dir_name)}/. {_shell_quote(install_dir)}/')
            if status != 0:
                print_error(f"恢复安装目录失败: {install_dir}")
                return
    
    # 恢复配置文件
    if backup_info.get('config_files'):
        print_info("恢复配置文件...")
        for config_file in backup_info['config_files']:
            rel_path = config_file.replace('/usr/local/', '')
            backup_config_path = f"{selected_backup}/conf_{_remote_basename(rel_path)}"
            output, error, status = run_command(client, f'cp -a {_shell_quote(backup_config_path)} {_shell_quote(config_file)}')
            if status != 0:
                print_error(f"恢复配置文件失败: {config_file}")
                return
    
    # 恢复systemd服务文件
    if backup_info.get('systemd_service'):
        print_info("恢复systemd服务文件...")
        output, error, status = run_command(client, f'cp -a {_shell_quote(selected_backup)}/nginx.service /etc/systemd/system/')
        if status == 0:
            output, error, status = run_command(client, 'systemctl daemon-reload')
    
    # 验证回滚
    print_info("验证回滚结果...")
    output, error, status = run_command(client, NGINX_VERSION_CMD)
    if status == 0:
        rolled_back_version = output.strip()
        if rolled_back_version == backup_info['version']:
            print_success(f"nginx回滚成功！当前版本: {rolled_back_version}")
            print_info("建议检查配置文件并在业务低峰期重启nginx服务")
        else:
            print_warning(f"版本不匹配，期望: {backup_info['version']}, 实际: {rolled_back_version}")
    else:
        print_error("回滚后nginx无法正常启动")
    
    # 询问是否重启nginx
    if confirm_yes_no("是否立即重启nginx服务以应用回滚？", default=False):
        print_info("重启nginx服务...")
        output, status = run_command_live(client, 'systemctl restart nginx')
        if status == 0:
            print_success("nginx服务重启成功")
        else:
            print_error("nginx服务重启失败，请检查配置")

def list_nginx_backups(client):
    print_info("查找nginx备份...")
    
    output, error, status = run_command(client, "find /data/backups -maxdepth 1 -type d -name 'nginx_backup_*' 2>/dev/null | sort -r")
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
                print(f"{i}. {_remote_basename(backup_dir)} (信息文件损坏)")
        else:
            print(f"{i}. {_remote_basename(backup_dir)} (无信息文件)")

def manage_nginx(client):
    global current_version, status, stable_version
    current_version, _, status = run_command(client, NGINX_VERSION_CMD)
    current_version = current_version.strip() if current_version else ""
    status, info = get_stable_version("https://nginx.org/en/download.html")
    if status == 0:
        stable_version = info
    else:
        print_error(info)
        return
    
    print_info("Nginx最新stable版本为：" + stable_version)
    while True:
        print("=== Nginx软件管理 ===")
        if status != 0 or not current_version or current_version == "":
            print(f"1. 安装 Nginx 最新稳定版 {stable_version}")
            print("2. 安装其他版本的 Nginx（手动指定版本号）")
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', '2', '0'], default="0")
            if choice == "1":
                install_nginx(client, version=stable_version)
            elif choice == "2":
                while True:
                    input_version = input(Fore.MAGENTA + "请输入要安装的Nginx版本号 (例如 1.28.1): ").strip()
                    status, version = get_stable_version("https://nginx.org/en/download.html", input_version)
                    if status == 0:
                        stable_version = info
                        break
                    else:
                        print_error(info)
                eol = get_eol_date("nginx", version)
                if eol != "Unknown":
                    print_warning(f"注意: {eol}")
                install_nginx(client, version=input_version)
            elif choice == "0":
                break
            else:
                print("无效选项，请重新输入")
        else:
            print_success("当前Nginx版本：" + current_version)
            print_info("Nginx最新稳定版为：" + stable_version)
            print("1. 升级 Nginx 到最新稳定版")
            print("2. 备份当前 Nginx 版本")
            print("3. 回滚 Nginx 到之前版本")
            print("4. 查看所有备份")
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', '2', '3', '4', '0'], default="0")
            if choice == "1":
                upgrade_nginx(client, version=stable_version)
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
