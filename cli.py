import importlib
import sys
import configparser
import shlex

from utils.ssh_utils import close_ssh_client, ssh_connect

def parse_host_pattern(pattern, filename="hosts"):
    """
    Parse host pattern supporting:
    - IP addresses: 192.168.1.10, 192.168.1.10,192.168.1.11
    - Group names: webservers
    - All hosts: all
    """
    # Disable interpolation to allow raw '%' in host parameters
    config = configparser.ConfigParser(allow_no_value=True, delimiters=(" ",), interpolation=None)
    config.optionxform = str
    try:
        read_files = config.read(filename, encoding="utf-8")
    except configparser.Error:
        sys.exit("错误：hosts 格式错误，请检查分组、地址及重复条目")
    if not read_files:
        print(f"错误：未找到hosts文件：{filename}")
        sys.exit(1)

    # Handle 'all' pattern
    if pattern == "all":
        hosts = []
        for section in config.sections():
            for line in config.items(section):
                hosts.append((section, line))
        return hosts

    # Check if it's a group name
    if pattern in config.sections():
        return [(pattern, line) for line in config.items(pattern)]

    # Handle IP addresses (comma-separated)
    ip_list = [ip.strip() for ip in pattern.split(",") if ip.strip()]
    hosts = []
    
    for ip in ip_list:
        found = False
        for section in config.sections():
            for line in config.items(section):
                if line[0] == ip:
                    hosts.append((section, line))
                    found = True
                    break
            if found:
                break
        if not found:
            print(f"警告：IP地址 '{ip}' 在hosts文件中未找到")
    
    return hosts

def load_hosts(pattern, filename="hosts"):
    """
    Load hosts based on pattern (IP, group name, or 'all')
    """
    host_entries = parse_host_pattern(pattern, filename)
    
    if not host_entries:
        print(f"错误：未找到匹配的主机模式：{pattern}")
        sys.exit(1)

    hosts = []
    for section, line in host_entries:
        host = line[0]
        if not host.strip() or "=" in host:
            sys.exit(f"错误：[{section}] 主机条目缺少有效的行首地址")
        params = {}
        if line[1]:
            try:
                param_string = line[1]
                # Use shlex.split() to properly handle quotes and spaces
                param_items = shlex.split(param_string)
                
                for item in param_items:
                    if '=' not in item:
                        raise ValueError("参数必须使用 key=value 格式")
                    k, v = item.split("=", 1)
                    if k == "keyfile":
                        params["key_file"] = v
                    else:
                        params[k] = v
            except ValueError:
                sys.exit(f"错误：[{section}] 主机 {host} 参数格式错误，请检查引号及 key=value 格式")

        missing = []
        if not params.get("user", "").strip():
            missing.append("用户名（user）")
        if not params.get("port", "").strip():
            missing.append("端口（port）")
        if not (params.get("password") or params.get("key_file", "").strip()):
            missing.append("密码或 SSH 密钥（password/keyfile）")
        if missing:
            sys.exit(f"错误：[{section}] 主机 {host} 缺少必填项：{'、'.join(missing)}")
        try:
            port = int(params["port"])
            if not 1 <= port <= 65535:
                raise ValueError("端口超出范围")
        except ValueError:
            sys.exit(f"错误：[{section}] 主机 {host} 的端口必须为 1–65535 的整数")

        hosts.append({
            "host": host,
            "user": params.get("user"),
            "port": params.get("port"),
            "password": params.get("password"),
            "key_file": params.get("key_file"),
            "vip": params.get("vip"),
            "proxy": params.get("proxy"),
            "proxy_user": params.get("proxy_user"),
            "proxy_password": params.get("proxy_password"),
            "proxy_keyfile": params.get("proxy_keyfile"),
            "proxy_port": params.get("proxy_port"),
            "hostname": params.get("hostname"),
            "lan_ip": params.get("lan_ip"),
            "remark": params.get("remark"),
            "group": section  # Add group information
        })
    return hosts

def main():
    args = sys.argv[1:]

    if len(args) != 2:
        print("用法: python cli.py <module_name> <host_pattern>")
        print("示例:")
        print("  python cli.py server_ops webservers")
        print("  python cli.py server_ops 192.168.1.10")
        print("  python cli.py server_ops 192.168.1.10,192.168.1.11")
        print("  python cli.py server_ops all")
        print("\n<host_pattern> 支持:")
        print("  - 组名: webservers, dbservers")
        print("  - IP地址: 192.168.1.10")
        print("  - 多个IP: 192.168.1.10,192.168.1.11")
        print("  - 所有主机: all")
        sys.exit(1)

    module_name, host_pattern = args[0], args[1]

    try:
        module = importlib.import_module(f"{module_name}.main")
    except ModuleNotFoundError:
        print(f"错误：找不到模块 {module_name}")
        sys.exit(1)
    except Exception as e:
        print(f"导入模块 {module_name}.main 出错: {e}")
        sys.exit(1)

    hosts = load_hosts(host_pattern)

    clients = []
    for entry in hosts:
        try:
            target_host = entry.get("vip") or entry['host']
            client = ssh_connect(target_host, entry['user'], entry.get("password"), entry.get("key_file"), entry.get("port"), entry.get("proxy"), entry.get("proxy_user"), entry.get("proxy_password"), entry.get("proxy_keyfile"), entry.get("proxy_port"))
            clients.append((entry['host'], client))
        except Exception as e:
            print(f"连接失败 {entry['host']}: {e}")

    if not clients:
        print("无可用连接，程序退出。")
        sys.exit(1)

    try:
        module.run(clients)
    except TypeError:
        print(f"错误：模块 {module_name}.run() 函数参数不匹配")
        sys.exit(1)
    finally:
        for _, client in clients:
            close_ssh_client(client)

if __name__ == "__main__":
    main()
