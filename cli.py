import importlib
import sys
import configparser

from utils.ssh_utils import close_ssh_client, ssh_connect

def load_hosts(group, filename="hosts"):
    config = configparser.ConfigParser(allow_no_value=True, delimiters=(" ",))
    config.optionxform = str
    read_files = config.read(filename, encoding="utf-8")
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
                    v = v.strip('"').strip("'")
                    if k == "keyfile":
                        params["key_file"] = v
                    else:
                        params[k] = v
            except Exception:
                print(f"解析参数错误，跳过该条目: {line}")
                continue

        hosts.append({
            "host": host,
            "user": params.get("user"),
            "port": params.get("port"),
            "password": params.get("password"),
            "key_file": params.get("key_file"),
            "proxy": params.get("proxy"),
            "proxy_user": params.get("proxy_user"),
            "proxy_password": params.get("proxy_password"),
            "proxy_keyfile": params.get("proxy_keyfile"),
            "proxy_port": params.get("proxy_port"),
        })
    return hosts

def main():
    if len(sys.argv) != 3:
        print("用法: python cli.py <module_name> <group>")
        print("示例: python cli.py server_ops webservers")
        sys.exit(1)

    module_name = sys.argv[1]
    group = sys.argv[2]

    # 动态导入模块
    try:
        module = importlib.import_module(f"{module_name}.main")
    except ModuleNotFoundError:
        print(f"错误：找不到模块 {module_name}")
        sys.exit(1)
    except Exception as e:
        print(f"导入模块 {module_name}.main 出错: {e}")
        sys.exit(1)

    hosts = load_hosts(group)

    clients = []
    for entry in hosts:
        try:
            client = ssh_connect(entry['host'], entry['user'], entry.get("password"), entry.get("key_file"), entry.get("port"), entry.get("proxy"), entry.get("proxy_user"), entry.get("proxy_password"), entry.get("proxy_keyfile"), entry.get("proxy_port"))
            clients.append((entry['host'], client))
        except Exception as e:
            print(f"连接失败 {entry['host']}: {e}")

    if not clients:
        print("无可用连接，程序退出。")
        sys.exit(1)

    try:
        module.run(clients)
    finally:
        for _, client in clients:
            close_ssh_client(client)

if __name__ == "__main__":
    main()
