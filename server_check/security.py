from utils.output import print_error
from utils.ssh_utils import run_command


def security_info(client, filename):
    permit_root_login, err, _ = run_command(
        client,
        "grep -E \"^PermitRootLogin\" /etc/ssh/sshd_config 2>/dev/null || echo \"未配置\"",
    )
    password_expired_policy, err, _ = run_command(
        client,
        "chage -l root 2>/dev/null | grep -E \"Maximum|最大|minimum|最小|Last|最近\"",
    )
    last_login, err, _ = run_command(client, "last -n 5 | grep -v begins")
    failed_login, err, _ = run_command(client, "lastb -n 5 | grep -v begins 2>/dev/null")
    firewalld_status, err, _ = run_command(
        client,
        "systemctl is-active firewalld >/dev/null 2>&1 && echo \"✅ 运行中\" || echo \"❌ 未运行\"",
    )
    selinux_status, err, _ = run_command(client, "getenforce")

    if err:
        print_error("获取信息出错：" + err)
        return None

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 三、安全配置\n\n")
        f.write(f"- **Root 远程登录检查：** `{permit_root_login.strip()}`\n")
        f.write(f"- **防火墙状态：** {firewalld_status.strip()}\n")
        f.write(f"- **SeLinux 状态：** `{selinux_status.strip()}`\n\n")
        f.write("### 密码策略\n\n```text\n")
        f.write(f"{password_expired_policy.strip()}\n" if password_expired_policy.strip() else "无\n")
        f.write("```\n\n")
        f.write("### 最近登录记录\n\n```text\n")
        f.write(f"{last_login.strip()}\n" if last_login.strip() else "无\n")
        f.write("```\n\n")

        if failed_login.strip():
            f.write("### 失败登录记录\n\n```text\n")
            f.write(f"{failed_login.strip()}\n")
            f.write("```\n\n")

        f.write("---\n\n")
    return None