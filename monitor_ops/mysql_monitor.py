import os

from colorama import Fore

from utils.file_utils import get_latest_version, download_file, upload_file, upload_file_with_vars
from utils.output import print_info, print_error, print_warning, print_success
from utils.ssh_utils import run_command, run_command_live
from utils.server_utils import is_valid_ip
from utils.choice import confirm_yes_no, menu_choice


def install_mysqld_exporter(client):
    latest_version = get_latest_version("https://api.github.com/repos/prometheus/mysqld_exporter/tags?page=1&per_page=5")
    print_info("mysqld_exporter最新发行版为：" + latest_version)
    if confirm_yes_no("是否安装？", default=False):
        print_info("开始安装mysqld_exporter " + latest_version + "......")

        local_path = os.path.join("packages", "mysqld_exporter-" + latest_version + ".linux-amd64.tar.gz")
        url = "https://github.com/prometheus/mysqld_exporter/releases/download/v" + latest_version + "/mysqld_exporter-" + latest_version + ".linux-amd64.tar.gz"
        remote_path = "/usr/local/src/mysqld_exporter-" + latest_version + ".linux-amd64.tar.gz"

        wget_cmd = f"cd /usr/local/src && wget {url}"
        _, wget_status = run_command_live(client, wget_cmd)
        
        if wget_status != 0:
            print_warning("下载失败，尝试本地上传")
            try:
                download_file(url, local_path)
                upload_file(client, local_path, remote_path)
                print_success("本地上传成功")
            except RuntimeError as e:
                print_error(f"本地上传失败，中止安装: {e}")
                print_warning("返回上一级菜单\n")
                return None
                
        cmds = [
            "tar zxf " + remote_path + " -C /usr/local/src/",
            "mv /usr/local/src/mysqld_exporter-" + latest_version + ".linux-amd64 /usr/local/mysqld-exporter"
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
            db_host = ""
            while db_host == "":
                db_host = input(Fore.MAGENTA + f"请输入数据库地址：").strip().lower()
                if is_valid_ip(db_host):
                    print_info(f"数据库地址为：" + db_host)
                else:
                    print_error("请填写正确的IP地址！")
            db_port = input(Fore.MAGENTA + f"请输入数据库端口：").strip().lower()
            db_username = input(Fore.MAGENTA + f"请输入刚刚创建的数据库用户：").strip().lower()
            db_password = input(Fore.MAGENTA + f"请输入数据库密码：").strip().lower()

            variables = {
                "db_host": db_host,
                "db_port": db_port,
                "db_username": db_username,
                "db_password": db_password
            }
            local_path = os.path.join("config", "prometheus", "mysqld_exporter.conf")
            remote_path = "/usr/local/mysqld-exporter/mysqld_exporter.conf"
            upload_file_with_vars(client, local_path, remote_path, variables)

            local_path = os.path.join("config", "prometheus", "mysqld-exporter.service")
            remote_path = "/etc/systemd/system/mysqld-exporter.service"
            upload_file(client, local_path, remote_path)
            run_command(client, "systemctl daemon-reload && systemctl enable --now mysqld-exporter")

            # 检查服务状态
            print_info("\n正在检查mysqld-exporter服务状态...")
            out, err, code = run_command(client, "systemctl status mysqld-exporter")
            if code == 0:
                print_success("✓ mysqld-exporter服务已成功启动并运行")
                # 检查端口是否监听
                port_out, port_err, port_code = run_command(client, "netstat -tlnp | grep :9104")
                if port_code == 0:
                    print_success("✓ mysqld-exporter端口9104正在监听")
                else:
                    print_warning("⚠ mysqld-exporter端口9104未检测到监听")
            else:
                print_error("✗ mysqld-exporter服务启动失败")
                if err:
                    print_error(f"错误信息: {err.strip()}")

            # 询问是否更新Prometheus配置
            if confirm_yes_no("\n是否自动更新Prometheus配置以添加MySQL监控？", default=False):
                update_prometheus_config(client, db_host)

            print_info("\n安装完成！")

    else:
        print_warning(f"返回上一级")

    return None


def update_prometheus_config(client, mysql_host):
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
    out, err, code = run_command(client, f"grep -q 'mysqld_exporter' {prometheus_config_path}")
    if code == 0:
        print_warning("⚠ Prometheus配置文件中已存在MySQL监控配置")
        return
    
    # 备份原配置文件
    backup_path = f"{prometheus_config_path}.backup.$(date +%Y%m%d_%H%M%S)"
    run_command(client, f"cp {prometheus_config_path} {backup_path}")
    print_success(f"✓ 已备份原配置文件到 {backup_path}")
    
    # 添加MySQL监控配置
    mysql_config = f"""
  - job_name: 'mysql'
    static_configs:
      - targets: ['{mysql_host}:9104']
        labels:
          instance: '{mysql_host}'
"""
    
    # 将配置添加到scrape_configs部分
    add_config_cmd = f"""
sed -i '/scrape_configs:/a\\{mysql_config}' {prometheus_config_path}
"""
    out, err, code = run_command(client, add_config_cmd)
    
    if code == 0:
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


def manage_mysql_monitor(client):
    install_mysqld_exporter(client)