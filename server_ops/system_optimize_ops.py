import os
import time
from utils.ssh_utils import run_command
from utils.output import print_info, print_success, print_warning, print_error
from utils.file_utils import upload_file, get_local_md5, get_remote_md5
from colorama import Fore

def configure_ntpdate(client):
    print_info("配置 ntpdate 时间同步服务...")

    # 检查 ntpdate 是否安装
    out, _, _ = run_command(client, "which ntpdate")
    if not out.strip():
        print_info("ntpdate 未安装，尝试安装...")
        _, _, status = run_command(client, "yum install -y ntpdate")
        if status != 0:
            print_error("安装 ntpdate 失败，请手动检查")
            return

    ntp_server = "ntp.aliyun.com"
    out, err, status = run_command(client, f"ntpdate {ntp_server}")
    if "adjust time" in out or "step time" in out or status == 0:
        print_success(f"时间同步成功，使用服务器 {ntp_server}")
    else:
        print_warning(f"ntpdate 同步失败，输出：{out.strip()}")

    cron_line = f"0 3 * * * /usr/sbin/ntpdate {ntp_server} >/dev/null 2>&1"
    tmp_cron = "/tmp/crontab.tmp"

    # 导出当前 crontab 到临时文件，忽略无 crontab 报错
    run_command(client, f"crontab -l > {tmp_cron} || true")

    # 判断是否已有相同任务（用grep匹配行）
    out, _, _ = run_command(client, f"grep -F 'ntpdate' {tmp_cron} || true")
    if not out.strip():
        # 追加任务到临时文件
        run_command(client, f"echo '{cron_line}' >> {tmp_cron}")
        # 重新加载 crontab
        out, err, status = run_command(client, f"crontab {tmp_cron}")
        if status == 0 or "some known success indicator" in out+err:
            print_success("已添加每日凌晨3点ntpdate同步任务")
        else:
            print_warning(f"添加ntpdate定时任务失败，命令输出: {out.strip()} {err.strip()}")
    else:
        print_info("ntpdate定时同步任务已存在")


def optimize_vimrc(client):
    print_info("\n优化 Vim 配置文件 ~/.vimrc ...")

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
