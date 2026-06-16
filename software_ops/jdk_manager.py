import os
import shlex
from urllib.parse import urlencode

import requests
from colorama import Fore

from utils.choice import confirm_yes_no, menu_choice
from utils.file_utils import download_file, upload_file
from utils.output import print_error, print_info, print_success, print_warning
from utils.ssh_utils import run_command, run_command_live


def get_current_jdk_version(client):
    current_version, _, _ = run_command(
        client,
        r"java -version 2>&1 | awk -F'\"' '/version/ {print $2; exit}'",
    )
    return current_version.strip() if current_version else ""


def get_foojay_jdk_package(major_version, distribution="temurin"):
    params = {
        "version": major_version,
        "package_type": "jdk",
        "operating_system": "linux",
        "architecture": "x64",
        "archive_type": "tar.gz",
        "latest": "available",
        "directly_downloadable": "true",
        "release_status": "ga",
        "libc_type": "glibc",
    }
    if distribution:
        params["distribution"] = distribution
    url = "https://api.foojay.io/disco/v3.0/packages?" + urlencode(params)
    headers = {"User-Agent": "AutoDeployKit/jdk-manager"}

    try:
        response = requests.get(url, headers=headers, timeout=(5, 20))
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print_error(f"获取 Foojay JDK{major_version} 版本信息失败: {e}")
        return None

    packages = data.get("result") if isinstance(data, dict) else None
    if not isinstance(packages, list):
        print_error("Foojay API 返回格式异常")
        return None

    for item in packages:
        if not isinstance(item, dict):
            continue
        download_url = item.get("links", {}).get("pkg_download_redirect") or item.get("direct_download_uri")
        if not download_url:
            continue
        filename = item.get("filename") or os.path.basename(download_url.split("?", 1)[0])
        version = item.get("java_version") or item.get("jdk_version") or str(major_version)
        distribution = item.get("distribution") or "OpenJDK"
        return {
            "version": str(version),
            "url": download_url,
            "filename": filename,
            "distribution": distribution,
        }

    if distribution:
        return get_foojay_jdk_package(major_version, distribution=None)

    print_error(f"未找到可直接下载的 Linux x64 JDK{major_version} tar.gz 包")
    return None


def install_jdk(client, major_version):
    package = get_foojay_jdk_package(major_version)
    if not package:
        print_error(f"未找到JDK{major_version}的稳定版本信息")
        return None
    stable_version = package["version"]
    print_info(f"JDK{major_version}最新稳定版为：{stable_version} ({package['distribution']})")
    if not confirm_yes_no(f"是否安装JDK{major_version}？", default=False):
        print_warning("返回上一级")
        return None

    default_install_path = f"/usr/local/jdk{major_version}"
    install_path = input(Fore.MAGENTA + f"请输入JDK{major_version}安装目录 (默认: {default_install_path}): ").strip()
    if not install_path:
        install_path = default_install_path
    install_path = install_path.strip().replace("\\", "/")
    if not install_path.startswith("/"):
        print_error("安装目录必须是绝对路径")
        return None

    print_info(f"开始安装JDK{major_version} " + stable_version + "......\n")
    print_success(f"JDK{major_version}将安装到: " + install_path + "\n")

    output, _, status = run_command(client, f"test -e {shlex.quote(install_path)} && echo exists")
    if status == 0 and output.strip() == "exists":
        print_error("安装目录已存在，请更换目录或手动处理后重试：" + install_path)
        return None

    print_info("开始下载二进制包")
    url = package["url"]
    filename = package["filename"]
    local_path = os.path.join("packages", filename)
    remote_path = "/usr/local/src/" + filename
    quoted_remote_path = shlex.quote(remote_path)
    quoted_install_path = shlex.quote(install_path)

    try:
        download_file(url, local_path)
        upload_file(client, local_path, remote_path)
    except RuntimeError as e:
        print_error(f"本地下载或上传失败，中止安装: {e}")
        print_warning("返回上一级菜单\n")
        return None
    

    cmds = [
        f"mkdir -p {quoted_install_path}",
        f"tar zxf {quoted_remote_path} -C {quoted_install_path} --strip-components=1",
    ]

    for cmd in cmds:
        _, cmd_status = run_command_live(client, cmd)
        if cmd_status != 0:
            print_error(f"\n命令执行失败: {cmd}")
            print_warning("中止当前操作，返回上一级菜单\n")
            return None

    if confirm_yes_no("是否配置JAVA_HOME环境变量？", default=True):
        profile_content = (
            f"cat >> {shlex.quote('/etc/profile')} <<'EOF'\n"
            "{\n"
            f"export JAVA_HOME={install_path}\n"
            f"export PATH=$PATH:{install_path}/bin\n"
            "}\n"
            "EOF"
        )
        _, cmd_status = run_command_live(client, profile_content)
        if cmd_status == 0:
            _, source_status = run_command_live(client, "source /etc/profile")
            if source_status == 0:
                print_success("JAVA_HOME环境变量配置完成\n")
            else:
                print_error("/etc/profile 加载失败")
        else:
            print_error("JAVA_HOME环境变量配置失败")

    run_command_live(client, "java -version")
    current_version = get_current_jdk_version(client)
    print_info("安装完成！当前Java版本：" + current_version)
    return None


def manage_jdk(client):
    while True:
        current_version = get_current_jdk_version(client)
        print("========== JDK软件管理 ==========")
        if current_version:
            print_info("当前Java版本：" + current_version)
        else:
            print_warning("当前未检测到Java")
        print("1. 安装JDK")
        print("0. 返回/跳过")
        choice = menu_choice("请选择操作编号: ", valid_choices=["1", "0"], default="0")
        if choice == "1":
            major_version = input(Fore.MAGENTA + "请输入要安装的JDK主版本号 (例如 8, 11, 17, 21): ").strip()
            if not major_version:
                print_error("主版本号不能为空")
                continue
            install_jdk(client, major_version)
        elif choice == "0":
            break
        else:
            print("无效选项，请重新输入")
