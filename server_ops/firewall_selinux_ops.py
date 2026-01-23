from pathlib import Path

from utils.ssh_utils import run_command, run_command_live
from utils.output import print_info, print_success, print_warning, print_error
from utils.choice import confirm_yes_no
from utils.menu_runner import run_menu


def manage_firewalld(client):
    print_info("检查 firewalld 状态 ...")
    output, err, _ = run_command(client, "systemctl is-active firewalld")
    status = output.strip()

    if err or status not in ["active", "inactive"]:
        print_warning("无法确定 firewalld 状态，跳过处理")
        return

    print_info(f"当前 firewalld 状态：{status}")
    if status == "inactive":
        if confirm_yes_no("\nfirewalld 处于关闭状态，是否开启？", default=False):
            print_info("正在开启 firewalld ...")
            _, status = run_command_live(client, "systemctl start firewalld")
            if status == 0:
                print_success("firewalld 已开启")
            else:
                print_error("开启 firewalld 失败")
            if confirm_yes_no("\n是否配置 firewalld 开机自启？", default=False):
                _, status = run_command_live(client, "systemctl enable firewalld")
                if status == 0:
                    print_success("firewalld 已配置开机自启")
                else:
                    print_error("配置 firewalld 开机自启失败")
        else:
            print_warning("保留 firewalld 当前状态")
    elif status == "active":
        if confirm_yes_no("\nfirewalld 处于开启状态，是否关闭？", default=False):
            print_info("正在关闭 firewalld ...")
            _, status = run_command_live(client, "systemctl stop firewalld")
            if status == 0:
                print_success("firewalld 已关闭")
            else:
                print_error("关闭 firewalld 失败")
            if confirm_yes_no("\n是否关闭firewalld 开机自启？", default=False):
                _, status = run_command_live(client, "systemctl disable firewalld")
                if status == 0:
                    print_success("firewalld 已配置关闭开机自启")
                else:
                    print_error("配置 firewalld 关闭开机自启失败")
        else:
            print_warning("保留 firewalld 当前状态")

def list_rules(client):
    services, _, status = run_command(client, "firewall-cmd --list-services")
    if status != 0:
        print_error("获取防火墙服务列表失败")
        return None
    ports, _, status = run_command(client, "firewall-cmd --list-ports")
    if status != 0:
        print_error("获取防火墙端口列表失败")
        return None
    print_info("当前防火墙已开放的服务：")
    print(services.strip() + "\n" if services.strip() else "无")
    print_info("当前防火墙已开放的端口：")
    print(ports.strip() if ports.strip() else "无")

def resolve_services_for_port(client, port):
    # Query remote firewalld service definitions to map port -> service names.
    cmd = (
        f"grep -R --include='*.xml' -n 'port=\"{port}\"' "
        "/etc/firewalld/services /usr/lib/firewalld/services 2>/dev/null"
    )
    output, err, status = run_command(client, cmd)
    if status != 0 or not output.strip():
        return []
    services = []
    for line in output.splitlines():
        path = line.split(":", 1)[0]
        name = Path(path).stem
        if name:
            services.append(name)
    # de-dup preserve order
    seen = set()
    dedup = []
    for s in services:
        if s not in seen:
            dedup.append(s)
            seen.add(s)
    return dedup

def add_rules(client):
    while True:
        services, _, status = run_command(client, "firewall-cmd --get-services")
        if status != 0:
            print_error("获取防火墙服务列表失败")
            return None
        rule = input("请输入需要开放的端口或服务： ").strip()
        if rule != "":
            break
        print_error("输入不能为空，请重新输入")

    services_list = services.split()
    if "/" not in rule and rule.isdigit():
        candidates = [s for s in resolve_services_for_port(client, rule) if s in services_list]
        if len(candidates) == 1:
            rule = candidates[0]
        elif len(candidates) > 1:
            print_info(f"端口 {rule} 对应多个服务：")
            for idx, svc in enumerate(candidates, 1):
                print(f"{idx}) {svc}")
            choice = input("请输入序号选择服务（直接回车跳过映射）： ").strip()
            if choice.isdigit():
                choice_idx = int(choice)
                if 1 <= choice_idx <= len(candidates):
                    rule = candidates[choice_idx - 1]

    if rule in services_list:
        _ , status = run_command_live(client, f"firewall-cmd --permanent --add-service={rule}")
        if status == 0:
            print_success(f"服务 {rule} 已成功添加到防火墙")
        else:
            print_error(f"添加服务 {rule} 到防火墙失败")
            return None
    else:
        is_port = False
        port_part = rule
        proto = None
        if "/" in rule:
            port_part, proto = rule.split("/", 1)
        if port_part and all(part.isdigit() for part in port_part.split("-")):
            is_port = True

        if not is_port:
            print_error("请输入正确的服务名或端口号")
            return None

        if proto is None:
            while True:
                protocol = input("请输入协议类型（tcp/udp），默认tcp： ").strip().lower()
                if protocol in ["tcp", "udp", ""]:
                    if protocol == "":
                        protocol = "tcp"
                    break
                print_error("协议类型输入错误，请重新输入")
            rule = f"{port_part}/{protocol}"
        else:
            if proto not in ["tcp", "udp"]:
                print_error("协议类型输入错误，请重新输入")
                return None
            rule = f"{port_part}/{proto}"

        _ , status = run_command_live(client, f"firewall-cmd --permanent --add-port={rule}")
        if status == 0:
            print_success(f"端口 {rule} 已成功添加到防火墙")
        else:
            print_error(f"添加端口 {rule} 到防火墙失败")
            return None
    if confirm_yes_no("是否重新加载防火墙以应用更改？", default=True):
        run_command_live(client, "firewall-cmd --reload")
        print_success("防火墙重载完成\n")
        list_rules(client)

def delete_rules(client):
    services, _, status = run_command(client, "firewall-cmd --list-services")
    if status != 0:
        print_error("获取防火墙服务列表失败")
        return None
    ports, _, status = run_command(client, "firewall-cmd --list-ports")
    if status != 0:
        print_error("获取防火墙端口列表失败")
        return None
    while True:
        rule = input("请输入需要删除的端口或服务： ").strip()
        if rule != "":
            break
        print_error("输入不能为空，请重新输入")

    services_list = services.split()
    if "/" not in rule and rule.isdigit():
        candidates = [s for s in resolve_services_for_port(client, rule) if s in services_list]
        if len(candidates) == 1:
            rule = candidates[0]
        elif len(candidates) > 1:
            print_info(f"端口 {rule} 对应多个服务：")
            for idx, svc in enumerate(candidates, 1):
                print(f"{idx}) {svc}")
            choice = input("请输入序号选择服务（直接回车跳过映射）： ").strip()
            if choice.isdigit():
                choice_idx = int(choice)
                if 1 <= choice_idx <= len(candidates):
                    rule = candidates[choice_idx - 1]

    if rule in services_list:
        _ , status = run_command_live(client, f"firewall-cmd --permanent --remove-service={rule}")
        if status == 0:
            print_success(f"服务 {rule} 已成功从防火墙删除")
        else:
            print_error(f"从防火墙删除服务 {rule} 失败")
            return None
    else:
        ports_list = ports.split()
        port_matches = []
        if "/" in rule:
            if rule in ports_list:
                port_matches = [rule]
        else:
            for p in ports_list:
                port_part = p.split("/")[0]
                if port_part == rule:
                    port_matches.append(p)

        if port_matches:
            for p in port_matches:
                _ , status = run_command_live(client, f"firewall-cmd --permanent --remove-port={p}")
                if status == 0:
                    print_success(f"端口 {rule} 已成功从防火墙删除")
                else:
                    print_error(f"从防火墙删除端口 {rule} 失败")
                    return None
        else:
            print_error(f"防火墙中不存在端口或服务 {rule}，请确认后重试")
            return None
    
    if confirm_yes_no("是否重新加载防火墙以应用更改？", default=True):
        run_command_live(client, "firewall-cmd --reload")
        print_success("防火墙重载完成\n")
        list_rules(client)

operations = {
    "1": ("防火墙 (firewalld) 开关", manage_firewalld),
    "2": ("添加防火墙开放端口或服务", add_rules),
    "3": ("删除防火墙开放端口或服务", delete_rules),
    "4": ("查看防火墙开放端口或服务", list_rules),
}

def manage_firewall_selinux(clients):
    run_menu("防火墙管理", operations, clients)
