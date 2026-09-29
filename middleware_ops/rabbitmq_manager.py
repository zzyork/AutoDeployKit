import base64
import datetime
import hashlib
import json
import os
import re
import secrets
import shlex
import string
from getpass import getpass

from colorama import Fore

from utils.choice import confirm_yes_no, menu_choice
from utils.file_utils import get_eol_date, get_stable_version, remote_download_or_upload, upload_file
from utils.linux_distro import get_linux_distribution
from utils.output import print_error, print_info, print_success, print_warning
from utils.ssh_utils import run_command, run_command_live

RABBITMQ_VERSION = "4.2.0"
ERLANG_VERSION = "27.3.4.11"
# GitHub release asset digests; cached/team-library packages must match as well.
RABBITMQ_SHA256 = "5eaebefc8d2e3e24fe123a38769577f98d2085e56429bc5024fd437e65514c85"
ERLANG_SHA256 = {
    "7": "598514aba44f023b4e0d8bcf6803cd05b07da40901f6680354f21b63be91c76a",
    "8": "06adab0e4ba188d151b99e285aa8c291bc3b74918787e08d765189ffe46c9a8e",
    "9": "9f299130d6bcb2218dfc9a6f6d0a5bff5ba4a5ab8bad4a70e7913bc41f941c6a",
}
ERLANG_VERSION_COMMAND = (
    "erl -noshell -eval "
    + shlex.quote(
        '{ok, V} = file:read_file(filename:join([code:root_dir(), "releases", '
        'erlang:system_info(otp_release), "OTP_VERSION"])), '
        '{ok, _} = application:ensure_all_started(crypto), io:put_chars(V), halt().'
    )
)


def install_rabbitmq(client, version=None):
    # ponytail: 固定已核验的版本和校验和；需要其他版本时先核对兼容矩阵及发布资产。
    if version is not None and version != RABBITMQ_VERSION:
        print_error("当前通用二进制安装仅支持 RabbitMQ " + RABBITMQ_VERSION)
        return
    install_path = "/usr/local/rabbitmq_server4.2"
    profile_path = "/etc/profile.d/rabbitmq.sh"
    service_path = "/etc/systemd/system/rabbitmq-server.service"
    installed, error, status = run_command(client, "rpm -q rabbitmq-server")
    if status == 0:
        print_info("RabbitMQ 已安装：" + installed)
        return
    if status != 1:
        print_error("无法检查 RabbitMQ RPM：" + (error or installed))
        return
    installed, error, status = run_command(client, "command -v rabbitmqctl")
    if status == 0:
        print_info("已存在 RabbitMQ CLI，不重复安装：" + installed)
        return
    if status != 1:
        print_error("无法检查 RabbitMQ CLI：" + error)
        return
    installed, error, status = run_command(client, "find /usr/local -maxdepth 3 -name rabbitmqctl -print")
    if status != 0 or installed:
        print_error("发现已有 RabbitMQ 或无法检查安装目录：" + (error or installed))
        return
    for path in (install_path, profile_path, service_path, "/usr/lib/systemd/system/rabbitmq-server.service"):
        _, error, status = run_command(client, "test -e " + path + " || test -L " + path)
        if status != 1:
            print_error("安装目标已存在或无法检查，不会覆盖：" + path + " " + error)
            return
    try:
        distribution = get_linux_distribution(client)
    except (RuntimeError, ValueError) as exc:
        print_error("无法识别目标系统：" + str(exc))
        return
    el_version = distribution["el_series"]
    if el_version not in ERLANG_SHA256:
        print_error("不支持的系统：" + distribution["pretty_name"])
        return
    arch, error, status = run_command(client, "uname -m")
    if status != 0 or arch != "x86_64":
        print_error("当前已核验的 Erlang RPM 仅支持 x86_64：" + (error or arch))
        return
    _, _, status = run_command(client, "command -v dnf")
    package_manager = "dnf"
    if status != 0:
        _, _, status = run_command(client, "command -v yum")
        if status != 0:
            print_error("目标主机没有 dnf 或 yum，无法安装依赖")
            return
        package_manager = "yum"
    erl_path, error, status = run_command(client, "command -v erl")
    if status not in (0, 1):
        print_error("无法检查 Erlang：" + error)
        return
    install_erlang = status == 1
    if not install_erlang:
        current_erlang, error, status = run_command(client, ERLANG_VERSION_COMMAND)
        if status != 0 or not re.fullmatch(r"27(?:\.[0-9]+)+", current_erlang):
            print_error("现有 Erlang 无法运行或不是兼容的 27.x，不会自动替换：" + (error or current_erlang))
            return
        if not re.fullmatch(r"/[A-Za-z0-9_./+-]+", erl_path):
            print_error("无法安全地将 Erlang 路径用于 systemd：" + erl_path)
            return
        print_info("复用 Erlang " + current_erlang)
    else:
        erl_path = "/usr/bin/erl"

    erlang_package = f"erlang-{ERLANG_VERSION}-1.el{el_version}.x86_64.rpm"
    rabbitmq_package = f"rabbitmq-server-generic-unix-{RABBITMQ_VERSION}.tar.xz"
    print_warning("RabbitMQ 4.2 社区支持已于 2026-07-31 结束。")
    if el_version == "7":
        print_warning("CentOS/RHEL 7 已结束支持，使用官方一次性 el7 Erlang RPM")
    erlang_action = f"安装 Erlang {ERLANG_VERSION}（el{el_version} RPM）" if install_erlang else f"复用 Erlang {current_erlang}"
    print_info(
        f"将通过 {package_manager} 安装 socat、ncurses-compat-libs、wget、xz；{erlang_action}；"
        f"下载包到 /usr/local/src；将 RabbitMQ {RABBITMQ_VERSION} 解压到 {install_path}；"
        f"写入 {profile_path}。不会添加 RabbitMQ 软件源、升级 OpenSSL 或修改防火墙。"
    )
    if not confirm_yes_no("是否确认以上安装操作？", default=False):
        print_warning("已取消 RabbitMQ 安装")
        return
    for command in (f"{package_manager} -y install socat ncurses-compat-libs wget xz", "mkdir -p /usr/local/src"):
        output, status = run_command_live(client, command)
        if status != 0:
            print_error("安装准备失败：" + (output or command))
            return
    packages = [("rabbitmq-server", RABBITMQ_VERSION, rabbitmq_package, RABBITMQ_SHA256)]
    if install_erlang:
        packages.insert(0, ("erlang-rpm", ERLANG_VERSION, erlang_package, ERLANG_SHA256[el_version]))
    for repository, release, filename, checksum in packages:
        url = f"https://github.com/rabbitmq/{repository}/releases/download/v{release}/{filename}"
        remote_path = "/usr/local/src/" + filename
        local_path = os.path.join("packages", filename)
        if os.path.isfile(local_path):
            try:
                upload_file(client, local_path, remote_path)
            except RuntimeError as exc:
                print_error(str(exc))
                return
        elif not remote_download_or_upload(client, url, local_path, remote_path):
            return
        digest, error, status = run_command(client, "sha256sum " + remote_path)
        if status != 0 or not digest.split() or digest.split()[0] != checksum:
            print_error("安装包 SHA256 校验失败，不会安装或解压：" + filename + " " + error)
            return
    if install_erlang:
        for command in (
            "rpm -ivh --test /usr/local/src/" + erlang_package,
            "rpm -ivh /usr/local/src/" + erlang_package,
        ):
            output, status = run_command_live(client, command)
            if status != 0:
                print_error("Erlang RPM 安装失败；不会强制忽略依赖或升级 OpenSSL：" + output)
                return
        current_erlang, error, status = run_command(client, ERLANG_VERSION_COMMAND)
        if status != 0 or current_erlang != ERLANG_VERSION:
            print_error("Erlang 版本或 crypto 运行验证失败：" + (error or current_erlang))
            return
    # Extract directly into a new directory instead of moving an existing tree.
    output, status = run_command_live(
        client,
        "mkdir " + install_path + " && tar -xJf /usr/local/src/" + rabbitmq_package
        + " --strip-components=1 -C " + install_path,
    )
    if status != 0:
        print_error("RabbitMQ 解压失败；保留现场，不会自动删除目录：" + output)
        return
    ctl = install_path + "/sbin/rabbitmqctl"
    installed, error, status = run_command(client, ctl + " version")
    if status != 0 or installed != RABBITMQ_VERSION:
        print_error("RabbitMQ CLI 版本验证失败：" + (error or installed))
        return
    profile = 'export PATH="$PATH:' + install_path + '/sbin"\n'
    output, status = run_command_live(
        client, "(set -C; printf %s " + shlex.quote(profile) + " > " + profile_path + ")"
    )
    if status != 0:
        print_error("环境变量配置失败，不会覆盖已有文件：" + output)
        return
    print_success(f"RabbitMQ {installed} 安装完成：{install_path}；Erlang {current_erlang}")
    _configure_rabbitmq(client, install_path, erl_path)


def _configure_rabbitmq(client, install_path, erl_path):
    if confirm_yes_no("是否启用 rabbitmq_management 管理插件（写入离线插件配置）？", default=False):
        output, status = run_command_live(
            client, install_path + "/sbin/rabbitmq-plugins --offline enable rabbitmq_management"
        )
        if status != 0:
            print_error("启用管理插件失败：" + output)
            return
        print_info("管理界面端口为 15672；不会关闭防火墙或放开 guest 的远程访问")
    _, _, status = run_command(client, "test -d /run/systemd/system")
    if status != 0:
        print_warning("未检测到运行中的 systemd，跳过服务配置及管理员创建")
        return
    service_path = "/etc/systemd/system/rabbitmq-server.service"
    service = (
        "[Unit]\nDescription=RabbitMQ broker\nAfter=syslog.target network.target\n\n"
        "[Service]\nType=simple\nUser=root\nGroup=root\n"
        f'Environment="PATH={os.path.dirname(erl_path)}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"\n'
        f"WorkingDirectory={install_path}\nExecStart={install_path}/sbin/rabbitmq-server\n"
        f"ExecStop={install_path}/sbin/rabbitmqctl stop\nLimitNOFILE=65536\n\n"
        "[Install]\nWantedBy=multi-user.target\n"
    )
    print_info("拟写入 " + service_path + "，随后执行 systemctl daemon-reload：\n" + service)
    print_warning("按文档使用 root 运行服务；生产环境建议另行评估专用账号")
    if not confirm_yes_no("是否创建以上 systemd 服务并重新加载配置？", default=False):
        print_info("服务未启动，已跳过 systemd 配置及管理员创建")
        return
    for command in (
        "(set -C; printf %s " + shlex.quote(service) + " > " + service_path + ")",
        "systemctl daemon-reload",
    ):
        output, status = run_command_live(client, command)
        if status != 0:
            print_error("systemd 配置失败，不会覆盖已有服务：" + output)
            return
    if not confirm_yes_no("是否执行 systemctl start rabbitmq-server 并设置开机自启？", default=False):
        print_info("服务未启动，已跳过管理员创建")
        return
    for command in ("systemctl start rabbitmq-server", "systemctl enable rabbitmq-server"):
        output, status = run_command_live(client, command)
        if status != 0:
            print_error("服务启动或自启配置失败：" + output)
            return
    ctl = install_path + "/sbin/rabbitmqctl"
    for command in (
        ctl + " --timeout 60 await_startup",
        "systemctl is-active rabbitmq-server",
        ctl + " status",
    ):
        output, error, status = run_command(client, command)
        if status != 0:
            print_error("RabbitMQ 启动验证失败，请检查主机名解析及服务日志：" + (error or output))
            return
    print_success("RabbitMQ 服务已启动并设置开机自启")
    _create_rabbitmq_admin(client, ctl)


def _create_rabbitmq_admin(client, ctl):
    users, error, status = run_command(client, ctl + " list_users --formatter=json")
    try:
        users = json.loads(users)
        if status != 0 or not isinstance(users, list) or any(
            not isinstance(user, dict) or "user" not in user for user in users
        ):
            raise ValueError("无法读取用户列表")
    except ValueError:
        print_error("无法确认现有用户，跳过管理员创建：" + error)
        return
    if any(user["user"] == "admin" for user in users):
        print_warning("admin 已存在，不修改其密码、角色或权限")
        return
    if not confirm_yes_no("是否创建 admin 管理员并授予 / vhost 的配置、写入、读取权限？", default=False):
        return
    try:
        password = getpass("请输入随机管理员密码（至少 12 位，含大小写、数字及特殊符号）：")
        if (
            len(password) < 12
            or not all(
                any(char in group for char in password)
                for group in (string.ascii_lowercase, string.ascii_uppercase, string.digits, string.punctuation)
            )
            or any(char not in string.ascii_letters + string.digits + string.punctuation for char in password)
        ):
            print_error("密码不符合要求，未创建管理员")
            return
        if getpass("请再次输入管理员密码：") != password:
            print_error("两次密码不一致，未创建管理员")
            return
    except (EOFError, KeyboardInterrupt):
        print_warning("已取消管理员创建")
        return
    # Fresh generic installations use rabbit_password_hashing_sha256 by default.
    salt = secrets.token_bytes(4)
    hashed = base64.b64encode(salt + hashlib.sha256(salt + password.encode()).digest()).decode()
    _, _, status = run_command(
        client, ctl + " add_user admin " + shlex.quote(hashed) + " --pre-hashed-password"
    )
    if status != 0:
        print_error("管理员创建失败，请检查服务日志；不会输出密码或密码哈希")
        return
    for command in (
        ctl + " set_user_tags admin administrator",
        ctl + ' set_permissions -p / admin ".*" ".*" ".*"',
    ):
        output, status = run_command_live(client, command)
        if status != 0:
            print_error("admin 已创建，但角色或权限设置失败，请人工核查：" + output)
            return
    users, error, status = run_command(client, ctl + " list_users")
    if status != 0:
        print_error("管理员设置完成，但无法读取用户列表：" + error)
        return
    print_success("admin 管理员配置完成：\n" + users)


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
