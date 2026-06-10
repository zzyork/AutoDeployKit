from utils.output import print_error
from utils.ssh_utils import run_command


def security_info(client, filename, config=None, alerts=None):
    alerts = alerts if alerts is not None else []
    errors = []
    permit_root_login, err, status = run_command(
        client,
        "grep -E '^PermitRootLogin' /etc/ssh/sshd_config 2>/dev/null || echo '未配置'",
    )
    if status != 0:
        errors.append("Root 远程登录检查：" + (err.strip() or permit_root_login.strip() or f"退出码 {status}"))

    password_expired_policy, err, status = run_command(
        client,
        "chage -l root 2>/dev/null | grep -E 'Maximum|最大|minimum|最小|Last|最近' || true",
    )
    if status != 0:
        errors.append("密码策略：" + (err.strip() or password_expired_policy.strip() or f"退出码 {status}"))

    last_login, err, status = run_command(client, "last -n 5 | grep -v begins || true")
    if status != 0:
        errors.append("最近登录记录：" + (err.strip() or last_login.strip() or f"退出码 {status}"))

    failed_login, err, status = run_command(client, "lastb -n 5 2>/dev/null | grep -v begins || true")
    if status != 0:
        errors.append("失败登录记录：" + (err.strip() or failed_login.strip() or f"退出码 {status}"))

    firewalld_status, err, status = run_command(
        client,
        "systemctl is-active firewalld >/dev/null 2>&1 && echo '✅ 运行中' || echo '❌ 未运行'",
    )
    if status != 0:
        errors.append("防火墙状态：" + (err.strip() or firewalld_status.strip() or f"退出码 {status}"))

    selinux_status, err, status = run_command(client, "getenforce 2>/dev/null || echo '未安装/未启用'")
    if status != 0:
        errors.append("SeLinux 状态：" + (err.strip() or selinux_status.strip() or f"退出码 {status}"))

    if errors:
        print_error("获取安全配置信息出错：" + "; ".join(errors))
        return None

    if "PermitRootLogin yes" in permit_root_login:
        alerts.append(f"⚠️ **Root 远程登录：** {permit_root_login.strip()}")
    if "未运行" in firewalld_status:
        alerts.append(f"⚠️ **防火墙状态：** {firewalld_status.strip()}")

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
