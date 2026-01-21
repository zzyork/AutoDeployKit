# server_ops/openssh_upgrade.py
import os
import datetime
import json

from colorama import Fore

from utils.ssh_utils import run_command_live, run_command
from utils.output import print_info, print_success, print_warning, print_error
from utils.file_utils import download_file, upload_file, get_stable_version
from utils.choice import confirm_yes_no, menu_choice
import re

def upgrade_openssh(client):
    if confirm_yes_no("是否升级？", default=False):
        # 先备份当前版本
        print_info("升级前备份当前OpenSSH版本...")
        backup_info = backup_openssh(client)
        if backup_info is None:
            print_warning("！！！备份失败，是否继续升级？")
            if not confirm_yes_no("继续升级？", default=False):
                print_warning("取消升级操作")
                return None
        else:
            print_success("备份完成，开始升级...")

        print_info("升级 OpenSSH 到 " + latest_version)

        print_info("安装telnet及xinetd依赖")
        run_command_live(client, 'yum -y install xinetd telnet-server')
        run_command_live(client, "systemctl enable xinetd --now && systemctl enable telnet.socket --now")
        print_info("\n检查telnet 23端口是否正常启动......")
        output, error, status = run_command(client, 'ss -nltp | grep :23')
        if status == 0 and ":23" in output.strip():
            print_success("\ntelnet 23端口已正常启动!")
        else:
            print_warning("telnet 23端口未检测到，请检查配置")
        
        # 检查和配置防火墙规则
        print_info("\n检查防火墙状态...")
        output, error, status = run_command(client, 'systemctl is-active firewalld 2>/dev/null')
        if status == 0:
            print_info("检测到firewalld运行中，添加telnet服务规则...")
            output, status = run_command_live(client, 'firewall-cmd --permanent --add-service=telnet')
            if status == 0:
                output, status = run_command_live(client, 'firewall-cmd --reload')
                if status == 0:
                    print_success("firewalld规则添加成功，telnet服务已允许")
                else:
                    print_warning("！！！firewalld重载失败，请手动检查")
            else:
                print_warning("！！！firewalld规则添加失败，请手动配置")
        
        # 检查和配置SELinux
        print_info("\n检查SELinux状态...")
        output, error, status = run_command(client, 'getenforce 2>/dev/null')
        if status == 0:
            selinux_status = output.strip()
            if selinux_status in ['Enforcing', 'Permissive']:
                print_info(f"SELinux状态: {selinux_status}，配置telnet SELinux规则...")
                output, status = run_command_live(client, 'setsebool -P telnetd_disable_trans 1')
                if status == 0:
                    print_success("SELinux telnet规则配置成功")
                else:
                    print_warning("！！！SELinux telnet规则配置失败，尝试其他方式...")
                    output, status = run_command_live(client, 'semanage permissive -a telnetd_t 2>/dev/null || true')
                    if status == 0:
                        print_success("SELinux telnet域设置为permissive模式")
                    else:
                        print_warning("！！！SELinux配置失败，可能需要手动配置")
            else:
                print_info(f"SELinux状态: {selinux_status}，无需配置")
        else:
            print_info("未检测到SELinux或SELinux命令不可用")
        
        print_success("\ntelnet及xinetd依赖安装完成。")
        print_success("\n!!!请手动telnet连接远程服务器23端口，以避免无法远程服务器!!!")

        print_info("\n安装依赖......")
        run_command_live(client, 'yum -y install gcc gcc-c++ glibc make autoconf pcre-devel pam-devel zlib zlib-devel')
        print_success("\n依赖安装完成!")

        current_openssl_version, error, status = run_command(client, 'openssl version')
        print_info("\n当前OpenSSL版本为：" + current_openssl_version)
        if confirm_yes_no("\n是否已升级OpenSSL？", default=False):
            openssl_upgraded = 1
            openssl_path, error, status = run_command(client, 'ls -d /usr/local/*ssl*')
            openssl_path = openssl_path.strip()
        else:
            if confirm_yes_no("是否升级OpenSSL？", default=False):
                print_info("调用OpenSSL升级工具...")
                from server_ops.openssl_upgrade import upgrade_openssl_v3, upgrade_openssl_1_1_1
                if current_openssl_version.startswith("OpenSSL 1.1.1"):
                    upgrade_result = upgrade_openssl_1_1_1(client)
                elif current_openssl_version.startswith("OpenSSL 3.0"):
                    upgrade_result = upgrade_openssl_v3(client)
                if upgrade_result is not None:
                    openssl_upgraded = 1
                    print_success("OpenSSL升级完成")
                else:
                    print_warning("OpenSSL升级失败，继续使用当前版本")
                    openssl_upgraded = 0
            else:
                print_info("跳过OpenSSL升级")
                openssl_upgraded = 0

        print_info("\n开始下载源码包并编译安装")
        local_path = os.path.join("packages", "openssh-" + latest_version + ".tar.gz")
        remote_path = "/usr/local/src/openssh-" + latest_version + ".tar.gz"
        url = "http://ftp.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-" + latest_version + ".tar.gz"

        wget_cmd = f"cd /usr/local/src && wget {url}"
        output, wget_status = run_command_live(client, wget_cmd)
        
        if wget_status == 0:
            pass
        else:
            print_warning("！！！下载失败，尝试本地上传")
            try:
                download_file(url, local_path)
                upload_file(client, local_path, remote_path)
                print_success("本地上传成功")
            except RuntimeError as e:
                print_error(f"！！！本地上传也失败，中止升级: {e}")
                print_warning("返回上一级菜单\n")
                return None
        
        # 解压并编译安装
        # 从latest_version中提取版本号（如9.6, 9.9等）
        version_number = latest_version.split('-')[-1] if '-' in latest_version else latest_version
        install_path = f"/usr/local/openssh{version_number}"
        run_command_live(client, f"cd /usr/local/src && tar xzf openssh-{latest_version}.tar.gz")

        if openssl_upgraded == 0:
            cmds = [
                "cd /usr/local/src/openssh-" + latest_version + "&& ./configure --prefix=" + install_path + " --sysconfdir=/etc/ssh --with-pam --with-zlib --with-md5-passwords --with-pam",
                "cd /usr/local/src/openssh-" + latest_version + " && make",
                "cd /usr/local/src/openssh-" + latest_version + " && make install"
            ]
        elif openssl_upgraded == 1:
            cmds = [
                "cd /usr/local/src/openssh-" + latest_version + " && ./configure --prefix=" + install_path + " --sysconfdir=/etc/ssh --with-openssl-includes=/usr/local/include --with-ssl-dir=" + openssl_path + " --with-zlib --with-md5-passwords --with-pam",
                "cd /usr/local/src/openssh-" + latest_version + " && make",
                "cd /usr/local/src/openssh-" + latest_version + " && make install"
            ]

        cmd_status = 0
        for cmd in cmds:
            output, cmd_status = run_command_live(client, cmd)
            if cmd_status != 0:
                print_error(f"\n！！！命令执行失败: {cmd}")
                break

        # 追加SSH配置到/etc/ssh/sshd_config
        ssh_config_lines = [
            "UseDNS no",
            "PermitRootLogin yes", 
            "PubkeyAuthentication yes",
            "PasswordAuthentication yes",
            "X11Forwarding yes",
            "X11UseLocalhost no",
            "XAuthLocation /usr/bin/xauth"
        ]
        
        print_info("正在配置SSH服务...")
        for line in ssh_config_lines:
            run_command_live(client, f'echo "{line}" >> /etc/ssh/sshd_config')
        
        print_success("SSH配置已更新")

        # 备份并替换二进制文件
        ssh_links = {
            "/usr/bin/ssh": f"{install_path}/bin/ssh",
            "/usr/sbin/ssh": f"{install_path}/bin/ssh",
            "/usr/bin/sshd": f"{install_path}/sbin/sshd",
            "/usr/sbin/sshd": f"{install_path}/sbin/sshd",
            "/usr/bin/ssh-keygen": f"{install_path}/bin/ssh-keygen",
            "/usr/sbin/ssh-keygen": f"{install_path}/bin/ssh-keygen"
        }
        for dst, src in ssh_links.items():
            run_command_live(client, f'if [ -f {dst} ]; then mv {dst} {dst}.bak_$(date "+%Y%m%d") && ln -s {src} {dst}; fi')

        # 备份并别名当前SSH启动文件
        print_info("正在备份当前SSH 启动文件")
        sshd_service_path = ["/etc/rc.d/init.d/sshd", "/etc/init.d/sshd", "/etc/systemd/system/sshd.service", "/usr/lib/systemd/system/sshd.service", "/usr/lib/systemd/system/sshd.socket"]
        total_status = 0
        for path in sshd_service_path:
            output, error, status = run_command(client, f'ls -d {path}')
            if status == 0:
                print_info(f"找到sshd服务文件: {path}")
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output, status = run_command_live(client, f'mv {path} {path}.backup_{timestamp}')
                if status == 0:
                    print_success(f"已移动到: {path}.backup_{timestamp}")
                else:
                    print_error(f"移动失败: {path}")
                    total_status = 1
        if total_status == 0:
            print_success("sshd服务文件已备份")
        else:
            print_error("sshd服务文件备份失败")

        # 配置新版本OpenSSH的启动脚本
        cmds = [
            "cp -a /usr/local/src/openssh-" + latest_version + "/contrib/redhat/sshd.init /etc/init.d/sshd",
            "chmod +x /etc/init.d/sshd",
            "cp -a /usr/local/src/openssh-" + latest_version + "/contrib/redhat/sshd.pam /etc/pam.d/sshd",
            "systemctl daemon-reload",
            "chkconfig --add sshd",
            "chkconfig sshd on"
        ]
        
        for cmd in cmds:
            output, status = run_command_live(client, cmd)
            if status != 0:
                print_error(f"！！！命令执行失败: {cmd}")
                break

        current_version, _, _ = run_command(client, 'ssh -V 2>&1')
        current_version = current_version.strip() if current_version else ""
        print_success(f"\n升级已完成！\n当前OpenSSH版本: {current_version}")
        print_info("建议在非业务高峰期手动重启sshd服务")
        
        # 询问是否立即重启
        if confirm_yes_no("是否立即重启sshd服务？", default=False):
            print_info("重启sshd服务...")
            output, status = run_command_live(client, '/etc/init.d/sshd restart')
            if status == 0:
                print_success("sshd服务重启成功")
            else:
                print_error("！！！sshd服务重启失败，请检查配置")
                print_warning("如果需要，可以使用回滚功能恢复到之前版本")
    else:
        print_warning(f"返回上一级")

    return None

def backup_openssh(client):
    print_info("开始备份当前OpenSSH...")
    
    # 获取当前版本信息
    output, error, status = run_command(client, 'ssh -V 2>&1')
    if status != 0:
        print_error("无法获取当前OpenSSH版本信息")
        return None
    
    # 从版本信息中提取版本号
    version_match = re.search(r'OpenSSH_([\d.]+)', output)
    if not version_match:
        print_error("无法解析OpenSSH版本号")
        return None
    
    current_version = version_match.group(1).strip() if version_match.group(1) else ""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"/data/backups/openssh_backup_{current_version}_{timestamp}"
    
    print_info(f"创建备份目录: {backup_dir}")
    
    # 创建备份目录
    output, error, status = run_command(client, f'mkdir -p {backup_dir}')
    if status != 0:
        print_error(f"！！！创建备份目录失败: {backup_dir}")
        return None
    
    # 备份SSH二进制文件
    print_info("备份SSH二进制文件...")
    ssh_binaries = ['/usr/bin/ssh', '/usr/sbin/ssh', '/usr/bin/sshd', '/usr/sbin/sshd', '/usr/bin/ssh-keygen', '/usr/sbin/ssh-keygen']
    backed_up_binaries = []
    
    for binary in ssh_binaries:
        output, error, status = run_command(client, f'test -f {binary}')
        if status == 0:
            binary_name = os.path.basename(binary)
            # 避免与目录名冲突，二进制文件添加_bin后缀
            backup_name = f"{binary_name}_bin"
            output, status = run_command_live(client, f'cp -a {binary} {backup_dir}/{backup_name}')
            if status != 0:
                print_error(f"！！！备份SSH二进制文件失败: {binary}")
                return None
            backed_up_binaries.append(binary)
    
    if not backed_up_binaries:
        print_error("！！！无法找到SSH二进制文件")
        return None
    
    # 备份SSH配置目录
    print_info("备份SSH配置目录...")
    config_files = []
    
    # 备份PAM配置文件
    print_info("\n备份PAM配置文件...")
    output, error, status = run_command(client, 'test -f /etc/pam.d/sshd')
    if status == 0:
        config_files.append('/etc/pam.d/sshd')
        output, status = run_command_live(client, f'cp -a /etc/pam.d/sshd {backup_dir}/pam_sshd')
        if status != 0:
            print_error("！！！备份PAM配置文件失败")
            return None
    
    # 备份整个/etc/ssh目录
    print_info("\n备份/etc/ssh目录...")
    output, error, status = run_command(client, 'test -d /etc/ssh')
    if status == 0:
        config_files.append('/etc/ssh')
        output, status = run_command_live(client, f'cp -a /etc/ssh {backup_dir}/etc_ssh')
        if status != 0:
            print_error("！！！备份/etc/ssh目录失败")
            return None
    
    # 备份 SSH 启动文件
    print_info("备份 SSH 服务启动脚本...")
    service_file = []
    
    # 检查systemd服务启动脚本位置
    print_info("\n检查sshd服务启动脚本位置...")
    output, error, status = run_command(client, 'systemctl show sshd --property=SourcePath,FragmentPath')
    if status == 0:
        source_path = ""
        fragment_path = ""
        
        # 解析SourcePath
        source_match = re.search(r'SourcePath=([^\s]+)', output)
        if source_match:
            source_path = source_match.group(1)
        
        # 解析FragmentPath
        fragment_match = re.search(r'FragmentPath=([^\s]+)', output)
        if fragment_match:
            fragment_path = fragment_match.group(1)
        
        # 根据优先级备份服务文件
        if source_path and source_path != "/dev/null":
            print_info(f"\n备份SourcePath文件: {source_path}")
            service_filename = os.path.basename(source_path)
            output, status = run_command_live(client, f'cp -a {source_path} {backup_dir}/sshd_init')
            if status != 0:
                print_error(f"\n！！！备份SourcePath文件失败: {source_path}")
                return None
            service_file.append(source_path)
        elif fragment_path and fragment_path != "/dev/null":
            print_info(f"\n备份FragmentPath文件: {fragment_path}")
            service_filename = os.path.basename(fragment_path)
            output, status = run_command_live(client, f'cp -a {fragment_path} {backup_dir}/sshd_service')
            if status != 0:
                print_error(f"\n！！！备份FragmentPath文件失败: {fragment_path}")
                return None
            service_file.append(fragment_path)
        else:
            print_info("未找到有效的sshd服务文件路径")
    else:
        print_error("无法获取sshd服务文件信息")
    
    # 创建文件映射信息
    file_mappings = {
        "binaries": {},
        "config_files": {},
        "service_file": {}
    }
    
    # 生成二进制文件映射
    for binary in backed_up_binaries:
        binary_name = os.path.basename(binary)
        backup_name = f"{binary_name}_bin"
        file_mappings["binaries"][binary] = f"{backup_dir}/{backup_name}"
    
    # 生成配置文件映射
    for config_file in config_files:
        if config_file == '/etc/pam.d/sshd':
            file_mappings["config_files"][config_file] = f"{backup_dir}/pam_sshd"
        elif config_file == '/etc/ssh':
            file_mappings["config_files"][config_file] = f"{backup_dir}/etc_ssh"
        else:
            file_mappings["config_files"][config_file] = f"{backup_dir}/{os.path.basename(config_file)}"
    
    # 生成服务文件映射
    service_file_path = (source_path if source_path and source_path != "/dev/null" else fragment_path) if ('source_path' in locals() and source_path and source_path != "/dev/null") or ('fragment_path' in locals() and fragment_path and fragment_path != "/dev/null") else ""
    if service_file_path:
        # 根据备份时的逻辑确定备份文件名
        if 'SourcePath' in service_file_path or service_file_path.endswith('/init.d/sshd') or service_file_path.endswith('/rc.d/init.d/sshd'):
            backup_service_name = "sshd_init"
        else:
            backup_service_name = "sshd_service"
        file_mappings["service_file"][service_file_path] = f"{backup_dir}/{backup_service_name}"
    
    # 创建备份信息文件
    backup_info = {
        "version": current_version,
        "timestamp": timestamp,
        "backup_dir": backup_dir,
        "file_mappings": file_mappings
    }
    
    backup_info_file = f"{backup_dir}/backup_info.json"
    backup_info_json = json.dumps(backup_info, indent=2, ensure_ascii=False)
    
    # 写入备份信息文件
    output, error, status = run_command(client, f'cat > {backup_info_file} << EOF\n{backup_info_json}\nEOF')
    if status != 0:
        print_error("！！！创建备份信息文件失败")
        return None
    
    print_success(f"OpenSSH备份完成！备份目录: {backup_dir}")
    return backup_info

def rollback_openssh(client):
    """回滚OpenSSH到之前的版本"""
    print_info("查找可用的OpenSSH备份...")
    
    # 查找备份目录
    output, error, status = run_command(client, "find /data/backups -maxdepth 1 -type d -name 'openssh_backup_*' 2>/dev/null | sort -r")
    if status != 0 or not output.strip():
        print_warning("未找到任何OpenSSH备份")
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
    
    # 显示文件映射信息
    print_info("文件映射关系:")
    if backup_info.get('file_mappings'):
        mappings = backup_info['file_mappings']
        
        # 显示二进制文件映射
        if mappings.get('binaries'):
            print("  二进制文件:")
            for original, backup_path in mappings['binaries'].items():
                print(f"    {backup_path} -> {original}")
        
        # 显示配置文件映射
        if mappings.get('config_files'):
            print("  配置文件:")
            for original, backup_path in mappings['config_files'].items():
                print(f"    {backup_path} -> {original}")
        
        # 显示服务文件映射
        if mappings.get('service_file'):
            print("  服务文件:")
            for original, backup_path in mappings['service_file'].items():
                print(f"    {backup_path} -> {original}")
        print()
    else:
        print_warning("  无文件映射信息")
        print()
    
    # 确认回滚
    print_warning(f"即将回滚OpenSSH到版本 {backup_info['version']}")
    print_warning("这将覆盖当前的OpenSSH安装")
    if not confirm_yes_no(f"即将回滚OpenSSH到版本 {backup_info['version']}\n这将覆盖当前的OpenSSH安装\n确认回滚？", default=False):
        print_warning("取消回滚操作")
        return
    
    print_info("开始回滚OpenSSH...")
    
    # 停止SSH服务
    print_info("停止SSH服务...")
    run_command_live(client, "systemctl stop sshd")
    
    # 恢复SSH二进制文件
    if backup_info.get('file_mappings') and backup_info['file_mappings'].get('binaries'):
        print_info("恢复SSH二进制文件...")
        for original_path, backup_path in backup_info['file_mappings']['binaries'].items():
            output, status = run_command_live(client, f'cp -a {backup_path} {original_path}')
            if status != 0:
                print_error(f"！！！恢复SSH二进制文件失败: {original_path}")
                return
    
    # 恢复配置文件
    if backup_info.get('file_mappings') and backup_info['file_mappings'].get('config_files'):
        print_info("恢复SSH配置文件...")
        for original_path, backup_path in backup_info['file_mappings']['config_files'].items():
            output, status = run_command_live(client, f'cp -a {backup_path} {original_path}')
            if status != 0:
                print_error(f"！！！恢复SSH配置文件失败: {original_path}")
                return
    
    # 恢复服务文件
    if backup_info.get('file_mappings') and backup_info['file_mappings'].get('service_file'):
        print_info("恢复SSH服务文件...")
        for original_path, backup_path in backup_info['file_mappings']['service_file'].items():
            # 确保目标目录存在
            target_dir = os.path.dirname(original_path)
            output, status = run_command_live(client, f'mkdir -p {target_dir}')
            if status != 0:
                print_error(f"！！！创建服务文件目录失败: {target_dir}")
                return
            
            # 恢复服务文件
            output, status = run_command_live(client, f'cp -a {backup_path} {original_path}')
            if status != 0:
                print_error(f"！！！恢复SSH服务文件失败: {original_path}")
                return
            print_info(f"已恢复服务文件: {original_path}")
            
            # 重新加载systemd配置
            print_info("重新加载systemd配置...")
            output, status = run_command_live(client, 'systemctl daemon-reload')
            if status != 0:
                print_warning("！！！systemctl daemon-reload 执行失败，请手动执行")
    
    # 验证回滚
    print_info("验证回滚结果...")
    output, error, status = run_command(client, 'ssh -V 2>&1')
    if status == 0:
        version_match = re.search(r'OpenSSH_([\d.]+)', output)
        if version_match:
            rolled_back_version = version_match.group(1)
            if rolled_back_version == backup_info['version']:
                print_success(f"OpenSSH回滚成功！当前版本: {rolled_back_version}")
                print_info("建议检查配置文件并手动启动SSH服务")
            else:
                print_warning(f"版本不匹配，期望: {backup_info['version']}, 实际: {rolled_back_version}")
        else:
            print_error("无法解析回滚后的版本信息")
    else:
        print_error("回滚后OpenSSH无法正常启动")
    
    # 询问是否启动SSH
    if confirm_yes_no("是否启动SSH服务？", default=False):
        print_info("启动SSH服务...")
        output, status = run_command_live(client, 'systemctl start sshd')
        if status == 0:
            print_success("SSH服务启动成功")
        else:
            print_error("！！！SSH服务启动失败，请检查配置")

def list_openssh_backups(client):
    print_info("\n查找OpenSSH备份...")
    
    output, error, status = run_command(client, "find /data/backups -maxdepth 1 -type d -name 'openssh_backup_*' 2>/dev/null | sort -r")
    if status != 0 or not output.strip():
        print_warning("未找到任何OpenSSH备份")
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
                print(f"   备份目录: {backup_dir}")
                print()
                print("-" * 60)
            except Exception as e:
                print(f"{i}. {os.path.basename(backup_dir)} (信息文件损坏: {str(e)})")
        else:
            print(f"{i}. {os.path.basename(backup_dir)} (无信息文件)")

def manage_openssh(client):
    global current_version, latest_version
    current_version, _, _ = run_command(client, 'ssh -V 2>&1')
    current_version = current_version.strip() if current_version else ""
    print_success("当前OpenSSH版本：" + current_version)
    try:
        latest_version = get_stable_version("http://ftp.openbsd.org/pub/OpenBSD/OpenSSH/portable/", "9.")
        print_info("OpenSSH最新发行版为：" + latest_version)
    except:
        print_warning("无法获取最新版本信息")
        latest_version = "未知"
    while True:
        print("\n=== OpenSSH升级操作 ===")
        
        print("1. 升级 OpenSSH 到最新发行版")
        print("2. 备份当前 OpenSSH 版本")
        print("3. 回滚 OpenSSH 到之前版本")
        print("4. 查看所有备份")
        print("0. 返回/跳过")
        choice = menu_choice("请选择操作编号: ", valid_choices=['1', '2', '3', '4', '0'], default="0")
        if choice == "1":
            upgrade_openssh(client)
        elif choice == "2":
            backup_openssh(client)
        elif choice == "3":
            rollback_openssh(client)
        elif choice == "4":
            list_openssh_backups(client)
        elif choice == "0":
            break
        else:
            print("无效选项，请重新输入")
        
        # 重新获取版本状态
        current_version, _, status = run_command(client, 'ssh -V 2>&1')
        current_version = current_version.strip() if current_version else ""
