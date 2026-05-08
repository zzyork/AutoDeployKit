from __future__ import annotations

import sys

from agent.runner import collect_diagnosis, maybe_execute_repair, render_diagnosis
from cli import load_hosts
from utils.output import print_error, print_header, print_info, print_warning
from utils.ssh_utils import close_ssh_client, ssh_connect


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        print("用法: python agent_cli.py <host_pattern> <自然语言问题>")
        print("示例:")
        print('  python agent_cli.py webservers "nginx 502，帮我定位一下"')
        print('  python agent_cli.py 192.168.1.10 "mysql 服务起不来，帮我看下"')
        sys.exit(1)

    host_pattern = args[0]
    question = " ".join(args[1:]).strip()

    hosts = load_hosts(host_pattern)
    clients = []
    for entry in hosts:
        try:
            target_host = entry.get("vip") or entry["host"]
            client = ssh_connect(
                target_host,
                entry["user"],
                entry.get("password"),
                entry.get("key_file"),
                entry.get("port"),
                entry.get("proxy"),
                entry.get("proxy_user"),
                entry.get("proxy_password"),
                entry.get("proxy_keyfile"),
                entry.get("proxy_port"),
            )
            clients.append((entry["host"], client))
        except Exception as exc:
            print_error(f"连接失败 {entry['host']}: {exc}")

    if not clients:
        print_error("无可用连接，程序退出。")
        sys.exit(1)

    print_header("AutoDeployKit Agent 诊断模式")
    print_info(f"诊断目标：{host_pattern}")
    print_info(f"问题描述：{question}")
    print_warning("默认只执行只读诊断；涉及修复操作时，会先征求你的确认。")

    try:
        for host, client in clients:
            diagnosis = collect_diagnosis(client, host, question)
            render_diagnosis(diagnosis)
            maybe_execute_repair(client, diagnosis)
    finally:
        for _, client in clients:
            close_ssh_client(client)


if __name__ == "__main__":
    main()
