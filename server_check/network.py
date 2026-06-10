from utils.output import print_error
from utils.ssh_utils import run_command


def network_info(client, filename):
    ports, err, _ = run_command(client, "netstat -tupln | grep -E \"LISTEN\" | awk '{print $4}'")
    network, err, _ = run_command(
        client,
        "ip -o -4 addr | awk '!/docker|veth|br-|cni|flannel|tun|kube/ && $2!=\"lo\" {print $2, $4}' | uniq",
    )

    if err:
        print_error("获取信息出错：" + err)
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
            for name, addr in rows:
                f.write(f"| {name} | {addr} |\n")
            f.write("\n")

        f.write("---\n\n")
    return None