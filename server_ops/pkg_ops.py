import re
from colorama import Fore
from utils.ssh_utils import run_command, run_command_live
from utils.output import print_info, print_success, print_warning, print_error

def upgrade_packages(client):
    print_info("正在升级系统软件包 ...")
    _, status = run_command_live(client, "yum makecache && yum update -y")
    if status == 0:
        print_success("软件包升级完成")
    else:
        print_warning("软件包升级可能有错误")

def install_base_deps(client):
    deps = "unzip zip vim git net-tools lrzsz bind-utils dos2unix sysstat irqbalance tree nmap iptraf gcc gcc-c++ rsync net-snmp openssh-clients lvm2 wget bc glibc-headers python3 telnet oks"
    print_info("正在安装基础依赖软件包 ...")
    _, status = run_command_live(client, f"yum install -y --skip-broken {deps}")

    if status == 0:
        print_success("基础依赖包安装完成")

def install_base_tools(client):
    tools = "htop iotop tar make ntpdate lsof"
    print_info("正在安装基础工具软件包 ...")
    _, status = run_command_live(client, f"yum install -y --skip-broken {tools}")
    if status == 0:
        print_success("基础工具包安装完成")

def backup_yum_repo(client, filepath):
    backup_path = filepath + ".bak"
    cmd = f"cp {filepath} {backup_path}"
    _, err, _ = run_command(client, cmd)
    if err:
        print_error(f"备份文件 {filepath} 失败: {err}")
        return False
    print_success(f"备份文件到 {backup_path}")
    return True

def list_yum_repos(client):
    repo_files_out, err, _ = run_command(client, "ls /etc/yum.repos.d/*.repo")
    if err:
        print_error("获取 yum repo 文件列表失败: " + err)
        return {}

    repo_files = repo_files_out.strip().splitlines()
    if not repo_files:
        print_warning("未找到任何 yum repo 文件。")
        return {}

    repos = {}
    for filepath in repo_files:
        content, err, _ = run_command(client, f"cat {filepath}")
        if err:
            print_error(f"读取 {filepath} 失败: {err}")
            continue

        current_repo = None
        repos_in_file = {}

        for line in content.splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current_repo = line[1:-1]
                repos_in_file[current_repo] = {"file": filepath, "baseurl": None, "mirrorlist": None}
            elif current_repo:
                if line.startswith("baseurl="):
                    repos_in_file[current_repo]["baseurl"] = line[len("baseurl="):]
                elif line.startswith("mirrorlist="):
                    repos_in_file[current_repo]["mirrorlist"] = line[len("mirrorlist="):]

        repos.update(repos_in_file)

    print_info("当前yum源列表及URL:")
    for repo_name, info in repos.items():
        url = info["baseurl"] or info["mirrorlist"] or "(无URL)"
        print(f"  - {repo_name}: {url}")

    return repos

def modify_yum_repo_url(client, repo_name, repos):
    if repo_name not in repos:
        print_warning(f"未找到名为 {repo_name} 的 yum 源。")
        return

    info = repos[repo_name]
    filepath = info["file"]

    if not backup_yum_repo(client, filepath):
        return

    new_url = input(Fore.MAGENTA + f"请输入 {repo_name} 的新 URL: ").strip()
    if not new_url:
        print_warning("URL 为空，取消修改。")
        return

    new_url_esc = new_url.replace("/", "\\/")
    sed_baseurl_cmd = f"sed -i 's|^baseurl=.*|baseurl={new_url_esc}|' {filepath}"
    _, err, _ = run_command(client, sed_baseurl_cmd)
    if err:
        print_warning(f"替换 baseurl 失败，尝试替换 mirrorlist: {err}")
        sed_mirror_cmd = f"sed -i 's|^mirrorlist=.*|mirrorlist={new_url_esc}|' {filepath}"
        _, err2 = run_command(client, sed_mirror_cmd)
        if err2:
            print_error(f"替换 mirrorlist 失败: {err2}")
            return

    print_success(f"{repo_name} 的 URL 已更新为: {new_url}")

def manage_yum_repos(client):
    repos = list_yum_repos(client)
    if not repos:
        return

    while True:
        choice = input(Fore.MAGENTA + "是否要修改某个 yum 源的 URL？输入源名，或回车退出: ").strip()
        if not choice:
            print_info("退出 yum 源修改。")
            break
        modify_yum_repo_url(client, choice, repos)

def manage_packages(client):
    while True:
        print("==========软件包管理选项==========")
        print("1. 升级所有软件包")
        print("2. 安装基础依赖包")
        print("3. 安装基础工具包")
        print("4. 管理yum源")
        print("0. 返回")

        op = input("请输入操作编号: ").strip()

        if op == "1":
            upgrade_packages(client)
        elif op == "2":
            install_base_deps(client)
        elif op == "3":
            install_base_tools(client)
        elif op == "4":
            manage_yum_repos(client)
        elif op == "0":
            break
        else:
            print_warning("无效选项，请重新输入")
