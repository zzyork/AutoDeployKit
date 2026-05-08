# server_ops/openssl_upgrade.py
import os
import re
import shlex
from utils.ssh_utils import run_command_live, run_command
from utils.output import print_info, print_success, print_warning, print_error
from utils.file_utils import download_file, upload_file, get_stable_version
from utils.choice import confirm_yes_no, menu_choice

current_version = None
stable_version = None


def run_steps(client, cmds):
    for cmd in cmds:
        _, status = run_command_live(client, cmd)
        if status != 0:
            print_error(f"执行失败，已中止: {cmd}")
            return False
    return True


def is_safe_version(version):
    return bool(re.fullmatch(r"\d+\.\d+\.\d+[A-Za-z0-9.-]*", version or ""))


def ld_library_path_command(install_dir):
    quoted_install_dir = shlex.quote(install_dir)
    return (
        "lib_dir=$(for d in "
        f"{quoted_install_dir}/lib64 {quoted_install_dir}/lib; "
        "do [ -d \"$d\" ] && echo \"$d\" && break; done); "
        "test -n \"$lib_dir\" && "
        "grep -Fx \"$lib_dir\" /etc/ld.so.conf >/dev/null || "
        "echo \"$lib_dir\" >> /etc/ld.so.conf"
    )

def upgrade_openssl_1_1_1(client):
    print_info("升级 OpenSSL 到 1.1.1w")

    print_info("安装perl依赖......")
    _, status = run_command_live(client, 'dnf -y install perl')
    if status != 0:
        print_error("安装perl失败")
        return None
    print_success("perl安装完成。\n")

    print_info("开始下载源码包并编译安装")
    local_path = os.path.join("packages", "openssl-1.1.1w.tar.gz")
    remote_path = "/usr/local/src/openssl-1.1.1w.tar.gz"
    url = "https://github.com/openssl/openssl/releases/download/OpenSSL_1_1_1w/openssl-1.1.1w.tar.gz"

    wget_cmd = f"cd /usr/local/src && wget {url}"
    output, wget_status = run_command_live(client, wget_cmd)
    
    if wget_status == 0:
        pass
    else:
        print_warning("！！！下载失败，尝试本地上传")
        try:
            download_file(url, local_path)
            upload_file(client, local_path, remote_path)
            print_success("本地上传成功")
        except RuntimeError as e:
            print_error(f"！！！本地上传也失败，中止升级: {e}")
            print_warning("返回上一级菜单\n")
            return None
    cmds = [
        "tar zxf /usr/local/src/openssl-1.1.1w.tar.gz -C /usr/local/src/",
        "cd /usr/local/src/openssl-1.1.1w && ./config --prefix=/usr/local/openssl1.1 no-zlib",
        "cd /usr/local/src/openssl-1.1.1w && make && make install",
        "test ! -e /usr/bin/openssl.bak && mv /usr/bin/openssl /usr/bin/openssl.bak || true",
        "test ! -e /usr/include/openssl.bak && mv /usr/include/openssl /usr/include/openssl.bak || true",
        "ln -sfn /usr/local/openssl1.1/bin/openssl /usr/bin/openssl",
        "ln -sfn /usr/local/openssl1.1/include/openssl /usr/include/openssl",
        "ln -sfn /usr/local/openssl1.1/lib/libssl.so.1.1 /usr/local/lib64/libssl.so",
        "grep -Fx '/usr/local/openssl1.1/lib' /etc/ld.so.conf >/dev/null || echo '/usr/local/openssl1.1/lib' >> /etc/ld.so.conf",
        "ldconfig -v",
    ]

    if not run_steps(client, cmds):
        return None

    current_version, _, _ = run_command(client, r'openssl version 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    current_version = current_version.strip() if current_version else ""
    print_info("升级完成！\n当前OpenSSL版本：" + current_version)

    return None

def upgrade_openssl_v3(client):
    if confirm_yes_no("是否升级？", default=False):
        if not is_safe_version(stable_version):
            print_error(f"版本号非法，取消升级: {stable_version}")
            return None
        print_info("升级 OpenSSL 到 " + stable_version)

        print_info("安装perl依赖")
        _, status = run_command_live(client, 'dnf -y install perl')
        if status != 0:
            print_error("安装perl失败")
            return None
        print_success("perl安装完成。")

        print_info("开始下载源码包并编译安装")
        local_path = os.path.join("packages", "openssl-" + stable_version + ".tar.gz")
        url = "https://github.com/openssl/openssl/releases/download/openssl-" + stable_version + "/openssl-" + stable_version + ".tar.gz"
        try:
            download_file(url, local_path)
        except RuntimeError as e:
            print_error(f"下载失败，中止升级: {e}")
            print_warning("返回上一级菜单\n")
            return None

        remote_path = "/usr/local/src/openssl-" + stable_version + ".tar.gz"
        source_dir = "/usr/local/src/openssl-" + stable_version
        install_dir = "/usr/local/openssl-" + stable_version
        upload_file(client, local_path, remote_path)
        cmds = [
            "tar zxf " + shlex.quote(remote_path) + " -C /usr/local/src/",
            "cd " + shlex.quote(source_dir) + " && ./config --prefix=" + shlex.quote(install_dir) + " no-zlib",
            "cd " + shlex.quote(source_dir) + " && make && make install",
            "test ! -e /usr/bin/openssl.bak && mv /usr/bin/openssl /usr/bin/openssl.bak || true",
            "test ! -e /usr/include/openssl.bak && mv /usr/include/openssl /usr/include/openssl.bak || true",
            "ln -sfn " + shlex.quote(install_dir + "/bin/openssl") + " /usr/bin/openssl",
            "ln -sfn " + shlex.quote(install_dir + "/include/openssl") + " /usr/include/openssl",
            ld_library_path_command(install_dir),
            "ldconfig -v"
        ]

        if not run_steps(client, cmds):
            return None

        current_version, _, _ = run_command(client, r'openssl version 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
        current_version = current_version.strip() if current_version else ""
        print_info("\n安装完成！\n当前OpenSSL版本：" + current_version)
    else:
        print_warning(f"返回上一级")

    return None

def fix_libssl_so3(client):
    print_info("开始修复 libssl.so.3 缺失问题")
    cmds = [
        "openssl_dir=$(ls -d /usr/local/openssl-3.* 2>/dev/null | sort -V | tail -n1); lib_dir=$(for d in \"$openssl_dir/lib64\" \"$openssl_dir/lib\"; do [ -d \"$d\" ] && echo \"$d\" && break; done); test -n \"$lib_dir\" && ln -sf \"$lib_dir/libssl.so.3\" /usr/lib64/libssl.so.3",
        "openssl_dir=$(ls -d /usr/local/openssl-3.* 2>/dev/null | sort -V | tail -n1); lib_dir=$(for d in \"$openssl_dir/lib64\" \"$openssl_dir/lib\"; do [ -d \"$d\" ] && echo \"$d\" && break; done); test -n \"$lib_dir\" && ln -sf \"$lib_dir/libcrypto.so.3\" /usr/lib64/libcrypto.so.3"
    ]
    if run_steps(client, cmds):
        print_info("已修复完成")

def install_perl_cpan(client):
    print_info("安装 perl-CPAN 模块以解决 IPC/Cmd.pm 缺失")
    cmds = [
        "dnf install -y perl-CPAN",
        "echo 'yes\nmanual\nyes\ninstall IPC::Cmd\n' | perl -MCPAN -e shell"
    ]
    run_steps(client, cmds)

def manage_ssl(client):
    global current_version, stable_version
    current_version, _, _ = run_command(client, r'openssl version 2>&1 | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -n1')
    current_version = current_version.strip() if current_version else ""
    print_info("当前OpenSSL版本：" + current_version)
    if "1.1.1" in current_version:
        stable_version = "1.1.1w"
        print_info("OpenSSL 最新版本：" + stable_version)
    elif "3." in current_version:
        major_minor = ".".join(current_version.split(".")[:2]) if current_version else ""
        status, version_or_error = get_stable_version("https://api.github.com/repos/openssl/openssl/tags?page=1&per_page=50", major_minor)
        if status != 0:
            print_error(version_or_error)
            return None
        stable_version = version_or_error
        print_info("OpenSSL 最新版本：" + stable_version)
    else:
        print_error("当前 OpenSSL 版本不在支持的升级范围内，仅支持 1.1.1 和 3.x")
        return None
    if not stable_version:
        print_error("获取最新版本失败，中止升级")
        return None

    while True:
        print("=== OpenSSL升级操作 ===")
        if "1.1.1" in current_version:
            print("1. 升级 OpenSSL 到 1.1.1w")
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', '0'], default="0")
        elif "3." in current_version:
            print("1. 将 OpenSSL v3 升级到最新稳定版")
            print("2. 修复 libssl.so.3 缺失问题")
            print("3. 安装 perl-CPAN（解决 IPC/Cmd.pm 缺失）")
            print("0. 返回/跳过")
            choice = menu_choice("请选择操作编号: ", valid_choices=['1', '2', '3', '0'], default="0")

        if choice == "1":
            if "1.1.1" in current_version:
                upgrade_openssl_1_1_1(client)
            elif "3." in current_version:
                upgrade_openssl_v3(client)
        elif choice == "2":
            fix_libssl_so3(client)
        elif choice == "3":
            install_perl_cpan(client)
        elif choice == "0":
            break
        else:
            print("无效选项，请重新输入")
