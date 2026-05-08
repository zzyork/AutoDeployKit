import re
import shlex
from colorama import Fore
from utils.ssh_utils import run_command, run_command_live
from utils.output import print_info, print_success, print_warning, print_error
from utils.file_utils import upload_file_with_vars
from utils.choice import confirm_yes_no, menu_choice

REPO_DIR_CANDIDATES = ["/etc/dnf.repos.d", "/etc/yum.repos.d"]
REPO_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
REPO_URL_RE = re.compile(r"^(https?|ftp|file)://[^\s]+$|^[A-Za-z0-9_./:-]+$")


def is_valid_repo_name(repo_name):
    return bool(REPO_NAME_RE.fullmatch(repo_name)) and ".." not in repo_name


def is_valid_repo_value(value):
    return "\n" not in value and "\r" not in value and bool(REPO_URL_RE.fullmatch(value))


def upload_text(client, remote_path, content):
    with client.open_sftp() as sftp:
        with sftp.file(remote_path, "w") as remote_file:
            remote_file.write(content)


def remove_remote_file(client, remote_path):
    with client.open_sftp() as sftp:
        sftp.remove(remote_path)


def replace_repo_url(content, new_url):
    lines = content.splitlines()
    replaced = False
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith("baseurl="):
            lines[idx] = f"{indent}baseurl={new_url}"
            replaced = True
        elif stripped.startswith("mirrorlist="):
            lines[idx] = f"{indent}mirrorlist={new_url}"
            replaced = True
    return "\n".join(lines) + ("\n" if content.endswith("\n") else ""), replaced


def remove_repo_section(content, repo_name):
    output_lines = []
    in_target = False
    removed = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section_name = stripped[1:-1]
            in_target = section_name == repo_name
            if in_target:
                removed = True
                continue

        if not in_target:
            output_lines.append(line)

    return "\n".join(line for line in output_lines if line.strip()) + "\n", removed


def get_repo_dir(client):
    """返回目标机可用的 repo 目录，兼容 dnf/yum 不同发行版路径。"""
    for repo_dir in REPO_DIR_CANDIDATES:
        out, _, status = run_command(client, f"test -d {shlex.quote(repo_dir)} && echo OK || true")
        if status == 0 and out.strip() == "OK":
            return repo_dir

    default_dir = REPO_DIR_CANDIDATES[0]
    _, err, status = run_command(client, f"mkdir -p {shlex.quote(default_dir)}")
    if status != 0:
        print_warning(f"创建默认 repo 目录 {default_dir} 失败: {err}")
    return default_dir


def list_repo_files(client):
    """列出 dnf/yum repo 文件，兼容 /etc/dnf.repos.d 与 /etc/yum.repos.d。"""
    repo_files = []
    existing_dirs = []

    for repo_dir in REPO_DIR_CANDIDATES:
        quoted_dir = shlex.quote(repo_dir)
        exists, _, _ = run_command(client, f"test -d {quoted_dir} && echo OK || true")
        if exists.strip() != "OK":
            continue

        existing_dirs.append(repo_dir)
        out, err, status = run_command(
            client,
            f"find {quoted_dir} -maxdepth 1 -type f -name '*.repo' -print 2>/dev/null | sort"
        )
        if status != 0:
            print_warning(f"扫描 repo 目录 {repo_dir} 失败: {err}")
            continue
        repo_files.extend([line.strip() for line in out.splitlines() if line.strip()])

    if repo_files:
        return repo_files

    if existing_dirs:
        print_warning("已找到 repo 目录，但未找到任何 .repo 文件。")
    else:
        print_warning("未找到 /etc/dnf.repos.d 或 /etc/yum.repos.d 目录。")
    return []

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
    cmd = f"cp {shlex.quote(filepath)} {shlex.quote(backup_path)}"
    _, err, _ = run_command(client, cmd)
    if err:
        print_error(f"备份文件 {filepath} 失败: {err}")
        return False
    print_success(f"备份文件到 {backup_path}")
    return True

def list_dnf_repos(client):
    repo_files = list_repo_files(client)
    if not repo_files:
        return {}

    repos = {}
    for filepath in repo_files:
        content, err, _ = run_command(client, f"cat {shlex.quote(filepath)}")
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
    if not is_valid_repo_value(new_url):
        print_error("URL 格式非法：不允许空白、换行或不受支持的协议")
        return

    content, err, status = run_command(client, f"cat {shlex.quote(filepath)}")
    if status != 0:
        print_error(f"读取 {filepath} 失败: {err}")
        return

    new_content, replaced = replace_repo_url(content, new_url)
    if not replaced:
        print_error("未找到 baseurl 或 mirrorlist 配置，取消修改")
        return

    try:
        upload_text(client, filepath, new_content)
    except Exception as exc:
        print_error(f"写入 {filepath} 失败: {exc}")
        return

    print_success(f"{repo_name} 的 URL 已更新为: {new_url}")

def add_dnf_repo(client):
    print_info("添加新的dnf源")
    
    # 获取用户输入
    repo_name = input(Fore.MAGENTA + "请输入dnf源名称: " + Fore.RESET).strip()
    if not repo_name:
        print_warning("dnf源名称不能为空")
        return
    if not is_valid_repo_name(repo_name):
        print_error("dnf源名称非法：仅允许字母、数字、下划线、点和短横线，且不能包含 '..'")
        return
    
    repo_url = input(Fore.MAGENTA + "请输入dnf源URL: " + Fore.RESET).strip()
    if not repo_url:
        print_warning("dnf源URL不能为空")
        return
    if not is_valid_repo_value(repo_url):
        print_error("dnf源URL非法：不允许空白、换行或不受支持的协议")
        return
    
    enabled = input(Fore.MAGENTA + "是否启用此dnf源? (1/0) [默认1]: " + Fore.RESET).strip()
    if not enabled:
        enabled = "1"
    if enabled not in {"0", "1"}:
        print_error("enabled 只能为 0 或 1")
        return
    
    gpgcheck = input(Fore.MAGENTA + "是否启用GPG检查? (1/0) [默认0]: " + Fore.RESET).strip()
    if not gpgcheck:
        gpgcheck = "0"
    if gpgcheck not in {"0", "1"}:
        print_error("gpgcheck 只能为 0 或 1")
        return
    
    gpgkey = input(Fore.MAGENTA + "请输入GPG密钥URL (可选): " + Fore.RESET).strip()
    if not gpgkey:
        gpgkey = ""
    elif not is_valid_repo_value(gpgkey):
        print_error("GPG密钥URL非法：不允许空白、换行或不受支持的协议")
        return
    
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
    repo_dir = get_repo_dir(client)
    remote_path = f"{repo_dir.rstrip('/')}/{repo_name}.repo"
    
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
                        try:
                            remove_remote_file(client, filepath)
                        except Exception as exc:
                            print_error(f"删除文件 {filepath} 失败: {exc}")
                            return
                        print_success(f"dnf源 '{selected_repo}' 及其配置文件已删除")
                    else:
                        print_warning("备份失败，取消删除操作")
                        return
                else:
                    # 文件中有多个源，只删除指定源
                    if backup_dnf_repo(client, filepath):
                        content, err, status = run_command(client, f"cat {shlex.quote(filepath)}")
                        if status != 0:
                            print_error(f"读取 {filepath} 失败: {err}")
                            return

                        new_content, removed = remove_repo_section(content, selected_repo)
                        if not removed:
                            print_error(f"未找到源配置段 {selected_repo}，取消删除")
                            return

                        try:
                            upload_text(client, filepath, new_content)
                        except Exception as exc:
                            print_error(f"写入 {filepath} 失败: {exc}")
                            return
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


def prompt_menu_input(prompt_message):
    try:
        return input(prompt_message).strip()
    except (KeyboardInterrupt, EOFError):
        print_warning("输入中断，返回上一级")
        return "0"

def manage_dnf_repos(client):
    while True:
        repos = list_dnf_repos(client)
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
            
            choice = prompt_menu_input(Fore.MAGENTA + "请选择要修改的dnf源编号: " + Fore.RESET)
            if choice == "0":
                continue
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
