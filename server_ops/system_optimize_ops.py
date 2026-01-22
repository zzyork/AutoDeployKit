import os
import time
from utils import output
from utils.ssh_utils import run_command, run_command_live
from utils.output import print_info, print_success, print_warning, print_error
from utils.file_utils import upload_file, get_local_md5, get_remote_md5
from colorama import Fore

def configure_ntpdate(client):
    print_info("配置时间同步服务...")

    ntp_server = "ntp.aliyun.com"

    # 1) 优先使用 ntpdate
    out, _, _ = run_command(client, "which ntpdate")
    if out.strip():
        out, status = run_command_live(client, f"ntpdate {ntp_server}")
        if status == 0 or ("adjust time" in out) or ("step time" in out):
            print_success(f"时间同步成功，使用 ntpdate 服务器 {ntp_server}")
        else:
            print_warning(f"ntpdate 同步失败，输出：{(out).strip()}")

        cron_line = f"0 3 * * * /usr/sbin/ntpdate {ntp_server} >/dev/null 2>&1"
        tmp_cron = "/tmp/crontab.tmp"

        run_command(client, f"crontab -l > {tmp_cron} || true")
        out, _, _ = run_command(client, f"grep -F 'ntpdate' {tmp_cron} || true")
        if not out.strip():
            run_command(client, f"echo '{cron_line}' >> {tmp_cron}")
            out, err, status = run_command(client, f"crontab {tmp_cron}")
            if status == 0:
                print_success("已添加每日凌晨3点 ntpdate 同步任务")
            else:
                print_warning(f"添加 ntpdate 定时任务失败，命令输出: {(out + ' ' + err).strip()}")
        else:
            print_info("ntpdate 定时同步任务已存在")
        return

    # 2) ntpdate 不存在：尝试 dnf 是否能找到并安装
    print_info("ntpdate 未安装，检查 dnf 源是否提供 ntpdate ...")
    out, err, status = run_command(client, "dnf -q list ntpdate 2>/dev/null || true")
    not_found = ("No matching Packages" in (out + err)) or ("Error: No matching Packages" in (out + err)) or (not out.strip())

    if not not_found:
        print_info("dnf 源存在 ntpdate，尝试安装...")
        out, err, status = run_command(client, "dnf install -y ntpdate")
        if status == 0:
            print_success("安装 ntpdate 成功，开始同步...")
            out, err, status = run_command(client, f"ntpdate {ntp_server}")
            if status == 0 or ("adjust time" in out) or ("step time" in out):
                print_success(f"时间同步成功，使用 ntpdate 服务器 {ntp_server}")
            else:
                print_warning(f"ntpdate 同步失败，输出：{(out + err).strip()}")

            cron_line = f"0 3 * * * /usr/sbin/ntpdate {ntp_server} >/dev/null 2>&1"
            tmp_cron = "/tmp/crontab.tmp"

            run_command(client, f"crontab -l > {tmp_cron} || true")
            out, _, _ = run_command(client, f"grep -F 'ntpdate' {tmp_cron} || true")
            if not out.strip():
                run_command(client, f"echo '{cron_line}' >> {tmp_cron}")
                out, err, status = run_command(client, f"crontab {tmp_cron}")
                if status == 0:
                    print_success("已添加每日凌晨3点 ntpdate 同步任务")
                else:
                    print_warning(f"添加 ntpdate 定时任务失败，命令输出: {(out + ' ' + err).strip()}")
            else:
                print_info("ntpdate 定时同步任务已存在")
            return
        else:
            print_warning(f"安装 ntpdate 失败，改用 chrony。输出：{(out + err).strip()}")
    else:
        print_info("dnf 源未找到 ntpdate，改用 chrony。")

    # 3) fallback: chrony
    print_info("安装并配置 chrony 时间同步服务...")
    out, err, status = run_command(client, "dnf install -y chrony")
    if status != 0:
        print_error(f"安装 chrony 失败，请手动检查。输出：{(out + err).strip()}")
        return

    # 配置 /etc/chrony.conf：确保有指定 server
    conf = "/etc/chrony.conf"
    out, _, _ = run_command(client, f"test -f {conf} && echo OK || echo NO")
    if out.strip() != "OK":
        print_warning(f"未找到 {conf}，尝试继续启用 chronyd（可能路径不同）")
    else:
        out, _, _ = run_command(client, f"grep -F 'server {ntp_server}' {conf} >/dev/null 2>&1 && echo YES || echo NO")
        if out.strip() != "YES":
            run_command(client, f"cp -a {conf} {conf}.bak.$(date +%Y%m%d%H%M%S) >/dev/null 2>&1 || true")
            run_command(client, f"echo 'server {ntp_server} iburst' >> {conf}")
            print_success(f"已写入 chrony NTP 服务器：{ntp_server}")
        else:
            print_info(f"chrony NTP 服务器已存在：{ntp_server}")

    # 启用并启动 chronyd
    out, err, status = run_command(client, "systemctl enable --now chronyd")
    if status != 0:
        # 兼容部分无 systemd 环境
        run_command(client, "service chronyd start || service chrony start || true")
        run_command(client, "chkconfig chronyd on || chkconfig chrony on || true")

    # 立刻校时（允许失败，不影响常驻同步）
    out, err, status = run_command(client, "chronyc -a makestep || true")
    if (out + err).strip():
        print_info(f"chrony 校时输出：{(out + err).strip()}")
    print_success("chrony 时间同步已配置完成（常驻服务同步，无需 crontab）")


def optimize_vimrc(client):
    print_info("优化 Vim 配置文件 ~/.vimrc ...")

    # 明确远程绝对路径，假设用 root 用户
    remote_vimrc_path = "/root/.vimrc"

    local_vimrc_path = os.path.join("config", "linux", ".vimrc")
    if not os.path.exists(local_vimrc_path):
        print_error(f"本地 .vimrc 文件不存在，请检查 {local_vimrc_path}")
        return

    # 先用 md5 判断是否需要覆盖
    local_md5 = get_local_md5(local_vimrc_path)
    remote_md5 = get_remote_md5(client, remote_vimrc_path)

    if local_md5 == remote_md5:
        print_info("远程 .vimrc 已与本地配置一致，无需更新")
        return

    # 上传覆盖
    upload_file(client, local_vimrc_path, remote_vimrc_path)
    print_success("上传并覆盖了远程 ~/.vimrc 配置文件")

def manage_system_optimize(client):
    print(Fore.BLUE + "\n=== 系统优化配置 ===")
    configure_ntpdate(client)
    optimize_vimrc(client)
