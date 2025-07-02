import sys
import configparser
from utils.ssh_utils import ssh_connect

def load_hosts(group, filename="hosts"):
    config = configparser.ConfigParser(allow_no_value=True, delimiters=(" ",))
    config.optionxform = str
    read_files = config.read(filename)
    if not read_files:
        print(f"错误：未找到hosts文件：{filename}")
        sys.exit(1)

    if group not in config.sections():
        print(f"错误：组名 '{group}' 不存在于 hosts 文件中")
        sys.exit(1)

    hosts = []
    for line in config.items(group):
        host = line[0]
        params = {}
        if line[1]:
            try:
                for item in line[1].split():
                    k, v = item.split("=", 1)
                    params[k] = v
            except Exception:
                print(f"解析参数错误，跳过该条目: {line}")
                continue

        hosts.append({
            "host": host,
            "user": params.get("user"),
            "password": params.get("password"),
            "key_file": params.get("key_file")
        })
    return hosts

def main():
    if len(sys.argv) < 3:
        print("用法: python cli.py <module_name> <group>")
        print("示例: python cli.py server_init webservers")
        sys.exit(1)

    module_name = sys.argv[1]
    group = sys.argv[2]

    # 动态导入模块
    try:
        module = __import__(f"server_ops.{module_name}", fromlist=[''])
    except ImportError:
        print(f"错误：找不到模块 server_ops.{module_name}")
        sys.exit(1)

    hosts = load_hosts(group)

    clients = []
    for entry in hosts:
        # print(f"连接 {entry['host']} ...")
        try:
            client = ssh_connect(entry['host'], entry['user'], entry.get("password"), entry.get("key_file"))
            clients.append((entry['host'], client))
        except Exception as e:
            print(f"连接失败 {entry['host']}: {e}")

    if not clients:
        print("无可用连接，程序退出。")
        sys.exit(1)

    # 将多个连接交给模块统一处理
    try:
        module.run(clients)
    finally:
        for _, client in clients:
            client.close()

if __name__ == "__main__":
    main()
