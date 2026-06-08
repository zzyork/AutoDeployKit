import os
import shlex
from getpass import getpass

from colorama import Fore

from utils.file_utils import get_stable_version, download_file, upload_file, upload_file_with_vars, remote_download_or_upload
from utils.output import print_info, print_error, print_warning, print_success
from utils.ssh_utils import run_command, run_command_live
from utils.server_utils import is_valid_ip
from utils.choice import confirm_yes_no


DEFAULT_EXPORTER_PORT = 9104
INSTALL_DIR = "/usr/local/mysqld-exporter"
SERVICE_NAME = "mysqld-exporter"


def _command_exists(client, command):
    _, _, code = run_command(client, f"command -v {command} >/dev/null 2>&1")
    return code == 0


def _path_exists(client, path):
    _, _, code = run_command(client, f"test -e {path}")
    return code == 0


def _get_installed_version(client):
    version_commands = [
        "command -v mysqld_exporter >/dev/null 2>&1 && mysqld_exporter --version 2>&1 | head -n1",
        f"test -x {INSTALL_DIR}/mysqld_exporter && {INSTALL_DIR}/mysqld_exporter --version 2>&1 | head -n1",
    ]
    for command in version_commands:
        output, _, code = run_command(client, command)
        if code == 0 and output.strip():
            return output.strip()
    return ""


def _pick_listen_port(client, default_port=DEFAULT_EXPORTER_PORT):
    port = str(default_port)
    while True:
        _, _, code = run_command(client, f"ss -tln 2>/dev/null | grep -q ':{port} ' || netstat -tln 2>/dev/null | grep -q ':{port} '")
        if code != 0:
            return port
        port = input(Fore.MAGENTA + f"⚠ {port}端口被占用，请重新输入监听端口: ").strip()
        if not port.isdigit() or not (1 <= int(port) <= 65535):
            print_warning(f"端口输入无效，使用默认端口{default_port}")
            port = str(default_port)


def _input_required(prompt, validator=None, error_message="输入不能为空！"):
    while True:
        value = input(Fore.MAGENTA + prompt).strip()
        if value and (validator is None or validator(value)):
            return value
        print_error(error_message)


def _input_port(prompt, default_port):
    while True:
        value = input(Fore.MAGENTA + prompt).strip() or str(default_port)
        if value.isdigit() and 1 <= int(value) <= 65535:
            return value
        print_error("请填写正确的端口！")


def install_mysqld_exporter(client):
    status, stable_version = get_stable_version("https://api.github.com/repos/prometheus/mysqld_exporter/tags?page=1&per_page=5")
    if status != 0:
        print_error("✗ 获取mysqld_exporter最新版本失败，无法继续安装")
        print_warning(stable_version)
        return None

    installed_output = _get_installed_version(client)
    if installed_output:
        print_success("mysqld_exporter已安装。")
        print_info(f"当前版本信息: {installed_output.strip()}\n")
        if not confirm_yes_no("是否继续重新安装/覆盖配置？", default=False):
            print_warning("→ 已跳过安装")
            return None

    print_info("mysqld_exporter最新发行版为：" + stable_version)
    if confirm_yes_no("是否安装？", default=False):
        print_info("开始安装mysqld_exporter " + stable_version + "......")

        install_dir_exists = _path_exists(client, INSTALL_DIR)
        if install_dir_exists:
            if not confirm_yes_no(f"检测到安装目录已存在：{INSTALL_DIR}，是否仅更新配置并重启服务？", default=False):
                print_warning("→ 已取消安装，避免覆盖现有目录")
                return None

        local_path = os.path.join("packages", "mysqld_exporter-" + stable_version + ".linux-amd64.tar.gz")
        url = "https://github.com/prometheus/mysqld_exporter/releases/download/v" + stable_version + "/mysqld_exporter-" + stable_version + ".linux-amd64.tar.gz"
        remote_path = "/usr/local/src/mysqld_exporter-" + stable_version + ".linux-amd64.tar.gz"

        cmds = []
        if not install_dir_exists:
            wget_cmd = f"cd /usr/local/src && wget {url}"
            if not remote_download_or_upload(client, url, local_path, remote_path, wget_cmd, "本地上传失败，中止安装"):
                return None
                    
            cmds = [
                "tar zxf " + remote_path + " -C /usr/local/src/",
                "cp -a /usr/local/src/mysqld_exporter-" + stable_version + ".linux-amd64 " + INSTALL_DIR
            ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0 :
                print_error(f"\n命令执行失败: {cmd}")
                print_warning("中止当前操作，返回上一级菜单\n")
                break

        if cmd_status == 0:
            print_info("\n请在需要监控的数据库创建mysqld_exporter用户并赋予权限\n示例：\nCREATE USER 'mysqld_exporter'@'%' IDENTIFIED BY '123@bCD' WITH MAX_USER_CONNECTIONS 3;\nGRANT PROCESS, REPLICATION CLIENT, SELECT ON *.* TO 'mysqld_exporter'@'%';\nFLUSH PRIVILEGES;\n")
            db_host = _input_required("请输入数据库地址：", is_valid_ip, "请填写正确的IP地址！")
            print_info("数据库地址为：" + db_host)
            db_port = _input_port("请输入数据库端口 (默认: 3306)：", 3306)
            db_username = _input_required("请输入刚刚创建的数据库用户：")
            db_password = getpass(Fore.MAGENTA + "请输入数据库密码：").strip()
            while not db_password:
                print_error("数据库密码不能为空！")
                db_password = getpass(Fore.MAGENTA + "请输入数据库密码：").strip()
            exporter_port = _pick_listen_port(client)

            variables = {
                "db_host": db_host,
                "db_port": db_port,
                "db_username": db_username,
                "db_password": db_password,
                "EXPORTER_PORT": exporter_port,
            }
            local_path = os.path.join("config", "prometheus", "mysqld_exporter.conf")
            remote_path = INSTALL_DIR + "/mysqld_exporter.conf"
            upload_file_with_vars(client, local_path, remote_path, variables)
            run_command(client, f"chmod 600 {remote_path}")

            local_path = os.path.join("config", "prometheus", "mysqld-exporter.service")
            remote_path = f"/etc/systemd/system/{SERVICE_NAME}.service"
            upload_file_with_vars(client, local_path, remote_path, variables)
            run_command(client, f"systemctl daemon-reload && systemctl enable --now {SERVICE_NAME}")

            # 检查服务状态
            print_info("\n正在检查mysqld-exporter服务状态...")
            out, err, code = run_command(client, f"systemctl is-active {SERVICE_NAME}")
            if out.strip() == "active":
                print_success("✓ mysqld-exporter服务已成功启动并运行")
                # 检查端口是否监听
                port_out, port_err, port_code = run_command(client, f"ss -tlnp 2>/dev/null | grep :{exporter_port} || netstat -tlnp 2>/dev/null | grep :{exporter_port}")
                if port_code == 0:
                    print_success(f"✓ mysqld-exporter端口{exporter_port}正在监听")
                else:
                    print_warning(f"⚠ mysqld-exporter端口{exporter_port}未检测到监听")
            else:
                print_error("✗ mysqld-exporter服务启动失败")
                if err:
                    print_error(f"错误信息: {err.strip()}")

            # 询问是否更新Prometheus配置
            if confirm_yes_no("\n是否自动更新Prometheus配置以添加MySQL监控？", default=False):
                exporter_host = input(Fore.MAGENTA + f"请输入Prometheus访问mysqld-exporter的地址 (默认: {db_host}): ").strip() or db_host
                update_prometheus_config(client, exporter_host, exporter_port)

            print_info("\n安装完成！")

    else:
        print_warning(f"返回上一级")

    return None


def update_prometheus_config(client, exporter_host, exporter_port=DEFAULT_EXPORTER_PORT):
    """更新Prometheus配置文件以添加MySQL监控目标"""
    prometheus_config_path = "/etc/prometheus/prometheus.yml"
    
    # 检查Prometheus配置文件是否存在
    out, err, code = run_command(client, f"test -f {prometheus_config_path}")
    if code != 0:
        print_warning("⚠ 未找到Prometheus配置文件，请手动配置")
        print_info(f"配置文件路径: {prometheus_config_path}")
        return
    
    print_info("正在检查Prometheus配置文件...")
    
    # 检查是否已经包含MySQL监控配置
    target = f"{exporter_host}:{exporter_port}"
    out, err, code = run_command(client, f"grep -Fq {shlex.quote(target)} {shlex.quote(prometheus_config_path)}")
    if code == 0:
        print_warning("⚠ Prometheus配置文件中已存在MySQL监控配置")
        return
    
    # 备份原配置文件
    backup_path = f"{prometheus_config_path}.backup.$(date +%Y%m%d_%H%M%S)"
    _, _, backup_code = run_command(client, f"cp {shlex.quote(prometheus_config_path)} {backup_path}")
    if backup_code != 0:
        print_error("✗ 备份Prometheus配置失败，中止自动更新")
        return
    print_success(f"✓ 已备份原配置文件到 {backup_path}")
    
    # 添加MySQL监控配置
    mysql_config = f"""
  - job_name: 'mysql'
    static_configs:
      - targets: ['{target}']
        labels:
          instance: '{exporter_host}'
"""
    
    # 将配置添加到scrape_configs部分
    add_config_cmd = f"""
sed -i '/scrape_configs:/a\\{mysql_config}' {prometheus_config_path}
"""
    out, err, code = run_command(client, add_config_cmd)
    
    if code == 0:
        if _command_exists(client, "promtool"):
            _, check_err, check_code = run_command(client, f"promtool check config {shlex.quote(prometheus_config_path)}")
            if check_code != 0:
                run_command(client, f"cp {backup_path} {shlex.quote(prometheus_config_path)}")
                print_error("✗ Prometheus配置校验失败，已回滚配置")
                if check_err:
                    print_error(f"错误信息: {check_err.strip()}")
                return
        print_success("✓ 已成功添加MySQL监控配置到Prometheus")
        
        # 重新加载Prometheus配置
        out, err, reload_code = run_command(client, "systemctl reload prometheus")
        if reload_code == 0:
            print_success("✓ Prometheus配置已重新加载")
        else:
            print_warning("⚠ Prometheus配置重载失败，请手动重启Prometheus服务")
            print_info("命令: systemctl restart prometheus")
    else:
        print_error("✗ 添加Prometheus配置失败")
        if err:
            print_error(f"错误信息: {err.strip()}")


def manage_mysql_exporter(client):
    install_mysqld_exporter(client)
