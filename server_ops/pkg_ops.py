import re
from colorama import Fore
from utils.ssh_utils import run_command, run_command_live
from utils.output import print_info, print_success, print_warning, print_error
from utils.file_utils import upload_file_with_vars
from utils.choice import confirm_yes_no, menu_choice

def upgrade_packages(client):
    print_info("正在升级系统软件包 ...")
    _, status = run_command_live(client, "dnf makecache && dnf update -y")
    if status == 0:
        print_success("软件包升级完成")
    else:
        print_warning("软件包升级可能有错误")

def install_base_deps(client):
    deps = "unzip zip vim git net-tools lrzsz bind-utils dos2unix sysstat irqbalance tree nmap iptraf gcc gcc-c++ rsync net-snmp openssh-clients lvm2 wget bc glibc-headers python3 telnet"
    print_info("正在安装基础依赖软件包 ...")
    _, status = run_command_live(client, f"dnf install -y --skip-broken {deps}")

    if status == 0:
        print_success("基础依赖包安装完成")

def install_base_tools(client):
    tools = "htop iotop tar make ntpdate lsof"
    print_info("正在安装基础工具软件包 ...")
    _, status = run_command_live(client, f"dnf install -y --skip-broken {tools}")
    if status == 0:
        print_success("基础工具包安装完成")

def backup_dnf_repo(client, filepath):
    backup_path = filepath + ".bak"
    cmd = f"cp {filepath} {backup_path}"
    _, err, _ = run_command(client, cmd)
    if err:
        print_error(f"备份文件 {filepath} 失败: {err}")
        return False
    print_success(f"备份文件到 {backup_path}")
    return True

def list_dnf_repos(client):
    repo_files_out, err, _ = run_command(client, "ls /etc/dnf.repos.d/*.repo")
    if err:
        print_error("获取 dnf repo 文件列表失败: " + err)
        return {}

    repo_files = repo_files_out.strip().splitlines()
    if not repo_files:
        print_warning("未找到任何 dnf repo 文件。")
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

    # print_info("当前dnf源列表及URL:")
    # for repo_name, info in repos.items():
    #     url = info["baseurl"] or info["mirrorlist"] or "(无URL)"
    #     print(f"  - {repo_name}: {url}")

    return repos

def modify_dnf_repo_url(client, repo_name, repos):
    if repo_name not in repos:
        print_warning(f"未找到名为 {repo_name} 的 dnf 源。")
        return

    info = repos[repo_name]
    filepath = info["file"]

    if not backup_dnf_repo(client, filepath):
        return

    new_url = input(Fore.MAGENTA + f"请输入 {repo_name} 的新 URL: " + Fore.RESET).strip()
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

def add_dnf_repo(client):
    print_info("添加新的dnf源")
    
    # 获取用户输入
    repo_name = input(Fore.MAGENTA + "请输入dnf源名称: " + Fore.RESET).strip()
    if not repo_name:
        print_warning("dnf源名称不能为空")
        return
    
    repo_url = input(Fore.MAGENTA + "请输入dnf源URL: " + Fore.RESET).strip()
    if not repo_url:
        print_warning("dnf源URL不能为空")
        return
    
    enabled = input(Fore.MAGENTA + "是否启用此dnf源? (1/0) [默认1]: " + Fore.RESET).strip()
    if not enabled:
        enabled = "1"
    
    gpgcheck = input(Fore.MAGENTA + "是否启用GPG检查? (1/0) [默认0]: " + Fore.RESET).strip()
    if not gpgcheck:
        gpgcheck = "0"
    
    gpgkey = input(Fore.MAGENTA + "请输入GPG密钥URL (可选): " + Fore.RESET).strip()
    if not gpgkey:
        gpgkey = ""
    
    # 准备变量
    variables = {
        "repo_name": repo_name,
        "repo_url": repo_url,
        "enabled": enabled,
        "gpgcheck": gpgcheck,
        "gpgkey": gpgkey
    }
    
    # 模板文件路径和目标路径
    template_path = "config/linux/temp.repo"
    remote_path = f"/etc/dnf.repos.d/{repo_name}.repo"
    
    try:
        # 使用upload_file_with_vars上传配置文件
        upload_file_with_vars(client, template_path, remote_path, variables)
        print_success(f"dnf源 '{repo_name}' 添加成功")
        print_info(f"配置文件位置: {remote_path}")
        
        # 重新加载dnf缓存
        print_info("正在重新加载dnf缓存...")
        _, status = run_command_live(client, "dnf clean all && dnf makecache")
        if status == 0:
            print_success("dnf缓存重新加载完成")
        else:
            print_warning("dnf缓存重新加载可能有问题")
            
    except Exception as e:
        print_error(f"添加dnf源失败: {e}")

def delete_dnf_repo(client):
    repos = list_dnf_repos(client)
    if not repos:
        return
    
    repo_names = list(repos.keys())
    print_info("当前dnf源列表：")
    for i, name in enumerate(repo_names, 1):
        filepath = repos[name]["file"]
        print(f"{i}. {name} (文件: {filepath})")
    
    choice = input(Fore.MAGENTA + "请选择要删除的dnf源编号: " + Fore.RESET).strip()
    try:
        index = int(choice) - 1
        if 0 <= index < len(repo_names):
            selected_repo = repo_names[index]
            filepath = repos[selected_repo]["file"]
            
            # 确认删除
            if confirm_yes_no(f"确定要删除dnf源 '{selected_repo}' 吗?", default=False):
                # 检查文件中有多少个源
                repos_in_file = []
                for repo_name, repo_info in repos.items():
                    if repo_info["file"] == filepath:
                        repos_in_file.append(repo_name)
                
                if len(repos_in_file) == 1:
                    # 文件中只有一个源，直接删除整个文件
                    if backup_dnf_repo(client, filepath):
                        _, err, _ = run_command(client, f"rm -f {filepath}")
                        if err:
                            print_error(f"删除文件 {filepath} 失败: {err}")
                            return
                        print_success(f"dnf源 '{selected_repo}' 及其配置文件已删除")
                    else:
                        print_warning("备份失败，取消删除操作")
                        return
                else:
                    # 文件中有多个源，只删除指定源
                    if backup_dnf_repo(client, filepath):
                        # 使用sed删除指定的源配置段
                        sed_cmd = f"sed -i '/\\[{selected_repo}\\]/,/\\[/{{/\\[/{{d;}};d;}}' {filepath}"
                        _, err, _ = run_command(client, sed_cmd)
                        if err:
                            print_error(f"从文件中删除源配置失败: {err}")
                            return
                        
                        # 清理空行
                        run_command(client, f"sed -i '/^$/d' {filepath}")
                        print_success(f"dnf源 '{selected_repo}' 已从文件 {filepath} 中删除")
                    else:
                        print_warning("备份失败，取消删除操作")
                        return
                
                # 重新加载dnf缓存
                print_info("正在重新加载dnf缓存...")
                _, status = run_command_live(client, "dnf clean all && dnf makecache")
                if status == 0:
                    print_success("dnf缓存重新加载完成")
                else:
                    print_warning("dnf缓存重新加载可能有问题")
            else:
                print_info("取消删除操作")
        else:
            print_warning("无效的编号")
    except ValueError:
        print_warning("请输入有效的编号")

def manage_dnf_repos(client):
    repos = list_dnf_repos(client)
    while True:
        print("\n==========Yum源管理选项==========")
        print("1. 新增dnf源")
        print("2. 修改dnf源URL")
        print("3. 删除dnf源")
        print("0. 返回")

        choice = menu_choice("请选择操作编号: ", valid_choices=['1', '2', '3', '0'], default="0")

        if choice == "1":
            add_dnf_repo(client)
        elif choice == "2":
            repo_names = list(repos.keys())
            print_info("repo列表：")
            for i, name in enumerate(repo_names, 1):
                print(f"{i}. {name}")
            
            choice = input(Fore.MAGENTA + "请选择要修改的dnf源编号: " + Fore.RESET).strip()
            try:
                index = int(choice) - 1
                if 0 <= index < len(repo_names):
                    selected_repo = repo_names[index]
                    modify_dnf_repo_url(client, selected_repo, repos)
                else:
                    print_warning("无效的编号")
            except ValueError:
                print_warning("请输入有效的编号")
        elif choice == "3":
            delete_dnf_repo(client)
        elif choice == "0":
            break
        else:
            print_warning("无效选项，请重新输入")

def manage_packages(client):
    while True:
        print("==========软件包管理选项==========")
        print("1. 升级所有软件包")
        print("2. 安装基础依赖包")
        print("3. 安装基础工具包")
        print("4. 管理dnf源")
        print("0. 返回")

        choice = menu_choice("请选择操作编号: ", valid_choices=['1', '2', '3', '4', '0'], default="0")

        if choice == "1":
            upgrade_packages(client)
        elif choice == "2":
            install_base_deps(client)
        elif choice == "3":
            install_base_tools(client)
        elif choice == "4":
            manage_dnf_repos(client)
        elif choice == "0":
            break
        else:
            print_warning("无效选项，请重新输入")
