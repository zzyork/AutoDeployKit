from utils.output import print_error
from utils.ssh_utils import run_command


def network_info(client, filename, config=None, alerts=None):
    errors = []
    ports, err, status = run_command(
        client,
        "if command -v netstat >/dev/null 2>&1; then netstat -tupln | grep -E 'LISTEN' | awk '{print $4}' || true; elif command -v ss >/dev/null 2>&1; then ss -tupln | grep -E 'LISTEN' | awk '{print $5}' || true; else echo '未安装 netstat/ss'; fi",
    )
    if status != 0:
        errors.append("开放端口列表：" + (err.strip() or ports.strip() or f"退出码 {status}"))

    network, err, status = run_command(
        client,
        "ip -o -4 addr | awk '!/docker|veth|br-|cni|flannel|tun|kube/ && $2!=\"lo\" {print $2, $4}' | uniq",
    )
    if status != 0:
        errors.append("网卡地址信息：" + (err.strip() or network.strip() or f"退出码 {status}"))

    if errors:
        print_error("获取网络信息出错：" + "; ".join(errors))
        return None

    rows = [line.split() for line in network.strip().splitlines() if line.strip()]

    with open(filename, "a", encoding="utf-8") as f:
        f.write("## 五、网络与端口\n\n")
        f.write("### 开放端口列表\n\n```text\n")
        f.write(f"{ports.strip()}\n" if ports.strip() else "无\n")
        f.write("```\n\n")

        if rows:
            f.write("### 网卡地址信息\n\n")
            f.write("| 接口 | 地址 |\n")
            f.write("| --- | --- |\n")
            for row in rows:
                if len(row) >= 2:
                    f.write(f"| {row[0]} | {row[1]} |\n")
            f.write("\n")

        f.write("---\n\n")
    return None
