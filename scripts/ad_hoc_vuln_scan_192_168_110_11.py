import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cli import load_hosts
from utils.ssh_utils import close_ssh_client, run_command, ssh_connect


COMMANDS = [
    (
        "基础信息",
        "hostname; echo ---os-release---; cat /etc/os-release 2>/dev/null; echo ---kernel---; uname -a",
    ),
    (
        "监听端口与进程",
        "(ss -tulpen || netstat -tulpen) 2>/dev/null",
    ),
    (
        "常见服务版本",
        "for x in nginx httpd apache2 mysql mysqld mariadbd redis-server redis-cli docker containerd runc openssl sshd php java python3 node npm tomcat; do if command -v $x >/dev/null 2>&1; then echo ===$x===; ($x -v || $x --version || $x -V) 2>&1 | head -n 8; fi; done",
    ),
    (
        "运行服务",
        "systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null | awk '{print $1}' | head -n 160",
    ),
    (
        "SSH 与基础安全配置",
        "echo ---sshd_config---; grep -Ei '^(PermitRootLogin|PasswordAuthentication|PubkeyAuthentication|PermitEmptyPasswords|Protocol|X11Forwarding|AllowUsers|DenyUsers)' /etc/ssh/sshd_config 2>/dev/null || true; echo ---firewalld---; systemctl is-active firewalld 2>/dev/null; firewall-cmd --list-all 2>/dev/null || true; echo ---selinux---; getenforce 2>/dev/null || true; echo ---sudoers-wheel---; grep -E '^%wheel|NOPASSWD' /etc/sudoers /etc/sudoers.d/* 2>/dev/null || true",
    ),
    (
        "关键软件包版本",
        "if command -v rpm >/dev/null 2>&1; then rpm -qa | egrep -i '^(openssl|openssh|nginx|httpd|apache|mysql|mariadb|redis|docker|containerd|runc|curl|wget|sudo|polkit|glibc|kernel|php|java|tomcat|postgresql|nodejs|python3)' | sort | head -n 400; elif command -v dpkg-query >/dev/null 2>&1; then dpkg-query -W -f='${Package} ${Version}\\n' | egrep -i '^(openssl|openssh|nginx|apache|mysql|mariadb|redis|docker|containerd|runc|curl|wget|sudo|polkit|glibc|linux-image|php|java|tomcat|postgresql|nodejs|python3)' | sort | head -n 400; fi",
    ),
    (
        "Web 配置摘要",
        "echo ---nginx---; (nginx -T 2>/dev/null | grep -Ei 'server_name|listen|ssl_protocols|ssl_ciphers|autoindex|proxy_pass|root |alias |rewrite' | head -n 220) || true; echo ---apache---; (apachectl -S 2>/dev/null || httpd -S 2>/dev/null) || true",
    ),
    (
        "数据库与缓存暴露检查",
        "echo ---mysql-bind---; grep -RniE '^(bind-address|skip-networking)' /etc/my.cnf /etc/mysql /etc/my.cnf.d 2>/dev/null || true; echo ---redis-conf---; grep -RniE '^(bind|protected-mode|requirepass|aclfile)' /etc/redis* /etc/redis /etc/redis.conf 2>/dev/null || true",
    ),
    (
        "Docker 与容器",
        "echo ---docker-version---; docker version 2>/dev/null || true; echo ---docker-ps---; docker ps --format 'table {{.Names}}\\t{{.Image}}\\t{{.Ports}}' 2>/dev/null || true; echo ---docker-sock---; ls -l /var/run/docker.sock 2>/dev/null || true",
    ),
    (
        "近期安全相关日志摘要",
        "echo ---failed-login---; lastb -n 10 2>/dev/null || true; echo ---sshd-errors---; journalctl -u sshd --since '14 days ago' --no-pager 2>/dev/null | egrep -i 'failed|invalid|error|disconnect|accepted' | tail -n 80 || true",
    ),
    (
        "安全更新公告",
        "dnf -q updateinfo list security 2>/dev/null | head -n 120 || yum --security check-update 2>/dev/null | head -n 120 || true",
    ),
    (
        "Nginx 安全头与暴露配置",
        "nginx -T 2>/dev/null | grep -Ei 'Strict-Transport-Security|X-Frame-Options|X-Content-Type-Options|Content-Security-Policy|Referrer-Policy|server_tokens|autoindex|ssl_protocols|listen|server_name' | head -n 260 || true",
    ),
    (
        "敏感路径权限",
        "ls -ld /etc /etc/ssh /etc/ssh/sshd_config /var/www /usr/share/nginx/html 2>/dev/null || true",
    ),
    (
        "计划任务摘要",
        "for f in /etc/crontab /etc/cron.d/*; do [ -f \"$f\" ] && echo ---$f--- && sed -n '1,120p' \"$f\"; done 2>/dev/null || true",
    ),
]


def main():
    entry = load_hosts("192.168.110.11", "hosts")[0]
    client = ssh_connect(
        entry.get("vip") or entry["host"],
        entry.get("user"),
        entry.get("password"),
        entry.get("key_file"),
        entry.get("port"),
        entry.get("proxy"),
        entry.get("proxy_user"),
        entry.get("proxy_password"),
        entry.get("proxy_keyfile"),
        entry.get("proxy_port"),
    )
    try:
        for title, command in COMMANDS:
            print(f"\n===== {title} =====")
            out, err, status = run_command(client, command)
            print(out)
            if err:
                print(f"[stderr/status={status}] {err}")
    finally:
        close_ssh_client(client)


if __name__ == "__main__":
    main()
