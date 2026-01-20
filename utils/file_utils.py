import os
import re
import sys
import tempfile
import time
from string import Template
import hashlib
import difflib

import requests
from utils.output import print_error, print_info
from utils.ssh_utils import run_command

def get_local_md5(filepath):
    """计算本地文件的 MD5 哈希值"""
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def get_remote_md5(client, remote_path):
    output, _, _ = run_command(client, f"md5sum {remote_path} | awk '{{print $1}}'")
    return output.strip()

def download_file(url, dest):
    if os.path.exists(dest):
        print_info(f"文件已存在: {dest}")
        return True

    # 确保目标目录存在
    dest_dir = os.path.dirname(dest)
    if dest_dir and not os.path.exists(dest_dir):
        try:
            os.makedirs(dest_dir, exist_ok=True)
            print_info(f"创建目录: {dest_dir}")
        except Exception as e:
            print_error(f"无法创建目录 {dest_dir}: {e}")
            return False

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    r = None
    try:
        print_info(f"开始下载: {url}")
        r = requests.get(url, headers=headers, stream=True, timeout=30)
        r.raise_for_status()

        total_size = r.headers.get("Content-Length")
        try:
            total_size = int(total_size) if total_size is not None else None
        except ValueError:
            total_size = None

        downloaded = 0
        last_print_ts = 0.0
        start_ts = time.time()
        filename = os.path.basename(dest) or dest

        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)

                now_ts = time.time()
                if now_ts - last_print_ts >= 0.2:
                    elapsed = max(now_ts - start_ts, 1e-6)
                    speed = downloaded / elapsed
                    if total_size and total_size > 0:
                        percent = min(downloaded * 100.0 / total_size, 100.0)
                        sys.stdout.write(
                            f"\rDownloading {filename}: {percent:6.2f}% "
                            f"({downloaded / 1024 / 1024:.2f}/{total_size / 1024 / 1024:.2f} MB) "
                            f"{speed / 1024 / 1024:.2f} MB/s"
                        )
                    else:
                        sys.stdout.write(
                            f"\rDownloading {filename}: {downloaded / 1024 / 1024:.2f} MB "
                            f"{speed / 1024 / 1024:.2f} MB/s"
                        )
                    sys.stdout.flush()
                    last_print_ts = now_ts

        end_ts = time.time()
        elapsed = max(end_ts - start_ts, 1e-6)
        speed = downloaded / elapsed
        if total_size and total_size > 0:
            sys.stdout.write(
                f"\rDownloading {filename}: {100.00:6.2f}% "
                f"({downloaded / 1024 / 1024:.2f}/{total_size / 1024 / 1024:.2f} MB) "
                f"{speed / 1024 / 1024:.2f} MB/s\n"
            )
        else:
            sys.stdout.write(
                f"\rDownloading {filename}: {downloaded / 1024 / 1024:.2f} MB "
                f"{speed / 1024 / 1024:.2f} MB/s\n"
            )
        sys.stdout.flush()
        
        print_info(f"下载完成: {dest} ({downloaded / 1024 / 1024:.2f} MB)")
        return True
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"网络错误: {e}")
    except IOError as e:
        raise RuntimeError(f"文件写入错误: {e}")
    except Exception as e:
        raise RuntimeError(f"未知错误: {e}")
    finally:
        try:
            if r is not None:
                r.close()
        except Exception:
            pass

def upload_file(client, local_path, remote_path):
    """上传文件到远程服务器，显示传输进度"""
    if not os.path.exists(local_path):
        print_error(f"本地文件不存在: {local_path}")
        raise RuntimeError(f"本地文件不存在: {local_path}")
    
    file_size = os.path.getsize(local_path)
    filename = os.path.basename(local_path)
    
    # 检查远程文件是否已存在
    try:
        sftp = client.open_sftp()
        try:
            remote_stat = sftp.stat(remote_path)
            remote_size = remote_stat.st_size
            
            if remote_size == file_size:
                sftp.close()
                print_info(f"远程文件已存在且大小相同，跳过上传: {remote_path}")
                return
                
        except FileNotFoundError:
            # 远程文件不存在，需要上传
            pass
        finally:
            sftp.close()
    except Exception as e:
        print_error(f"检查远程文件失败: {e}")
        # 继续上传流程
    
    print_info(f"开始上传: {filename} ({file_size / 1024 / 1024:.2f} MB) -> {remote_path}")
    
    uploaded = 0
    last_print_ts = 0.0
    start_ts = time.time()
    
    def progress_callback(transferred, total):
        nonlocal uploaded, last_print_ts
        uploaded = transferred
        now_ts = time.time()
        
        if now_ts - last_print_ts >= 0.2:
            elapsed = max(now_ts - start_ts, 1e-6)
            speed = transferred / elapsed
            percent = (transferred * 100.0 / total) if total > 0 else 0
            
            sys.stdout.write(
                f"\rUploading {filename}: {percent:6.2f}% "
                f"({transferred / 1024 / 1024:.2f}/{total / 1024 / 1024:.2f} MB) "
                f"{speed / 1024 / 1024:.2f} MB/s"
            )
            sys.stdout.flush()
            last_print_ts = now_ts
    
    try:
        sftp = client.open_sftp()
        sftp.put(local_path, remote_path, callback=progress_callback)
        sftp.close()
        
        # 显示最终进度
        end_ts = time.time()
        elapsed = max(end_ts - start_ts, 1e-6)
        speed = uploaded / elapsed
        
        sys.stdout.write(
            f"\rUploading {filename}: {100.00:6.2f}% "
            f"({uploaded / 1024 / 1024:.2f}/{file_size / 1024 / 1024:.2f} MB) "
            f"{speed / 1024 / 1024:.2f} MB/s\n"
        )
        sys.stdout.flush()
        
        print_info(f"上传完成: {remote_path}")
        
    except Exception as e:
        print_error(f"上传失败: {e}")
        raise RuntimeError(f"上传失败: {e}")

def upload_file_with_vars(client, local_path, remote_path, variables: dict):
    """读取模板文件，替换变量后上传到远程服务器，显示传输进度"""
    # 1. 读取模板文件内容
    with open(local_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 2. 替换变量：${VAR}
    template = Template(content)
    rendered = template.safe_substitute(variables)

    # 3. 写入到临时文件
    with tempfile.NamedTemporaryFile('w+', delete=False, encoding='utf-8') as tmpfile:
        tmpfile.write(rendered)
        tmpfile_path = tmpfile.name

    try:
        # 4. 上传临时文件（使用带进度显示的upload_file）
        # 直接调用SFTP上传以避免递归调用
        if not os.path.exists(tmpfile_path):
            print_error(f"临时文件不存在: {tmpfile_path}")
            raise RuntimeError(f"临时文件不存在: {tmpfile_path}")
        
        file_size = os.path.getsize(tmpfile_path)
        filename = os.path.basename(remote_path)
        
        # 检查远程文件是否已存在
        try:
            sftp = client.open_sftp()
            try:
                remote_stat = sftp.stat(remote_path)
                remote_size = remote_stat.st_size
                
                if remote_size == file_size:
                    sftp.close()
                    print_info(f"远程配置文件已存在且大小相同，跳过上传: {remote_path}")
                    return
                    
            except FileNotFoundError:
                # 远程文件不存在，需要上传
                pass
            finally:
                sftp.close()
        except Exception as e:
            print_error(f"检查远程配置文件失败: {e}")
            # 继续上传流程
        
        print_info(f"开始上传配置文件: {filename} ({file_size / 1024:.2f} KB) -> {remote_path}")
        
        uploaded = 0
        last_print_ts = 0.0
        start_ts = time.time()
        
        def progress_callback(transferred, total):
            nonlocal uploaded, last_print_ts
            uploaded = transferred
            now_ts = time.time()
            
            if now_ts - last_print_ts >= 0.2:
                elapsed = max(now_ts - start_ts, 1e-6)
                speed = transferred / elapsed
                percent = (transferred * 100.0 / total) if total > 0 else 0
                
                sys.stdout.write(
                    f"\rUploading {filename}: {percent:6.2f}% "
                    f"({transferred / 1024:.2f}/{total / 1024:.2f} KB) "
                    f"{speed / 1024:.2f} KB/s"
                )
                sys.stdout.flush()
                last_print_ts = now_ts
        
        sftp = client.open_sftp()
        sftp.put(tmpfile_path, remote_path, callback=progress_callback)
        sftp.close()
        
        # 显示最终进度
        end_ts = time.time()
        elapsed = max(end_ts - start_ts, 1e-6)
        speed = uploaded / elapsed
        
        sys.stdout.write(
            f"\rUploading {filename}: {100.00:6.2f}% "
            f"({uploaded / 1024:.2f}/{file_size / 1024:.2f} KB) "
            f"{speed / 1024:.2f} KB/s\n"
        )
        sys.stdout.flush()
        
        print_info(f"配置文件上传完成: {remote_path}")
        
    except Exception as e:
        print_error(f"配置文件上传失败: {e}")
        raise RuntimeError(f"配置文件上传失败: {e}")
    finally:
        # 5. 清理临时文件
        try:
            os.remove(tmpfile_path)
        except Exception:
            pass

def compare_file_content(client, filepath, remote_path):
    """比较本地文件和远程文件的内容差异，返回远程文件相对于本地文件多出来或缺少的内容"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            local_content = f.read()
        
        output, _, _ = run_command(client, f"cat {remote_path}")
        remote_content = output
        
        local_lines = [line for line in local_content.splitlines() if line.strip()]
        remote_lines = [line for line in remote_content.splitlines() if line.strip()]
        
        diff = list(difflib.unified_diff(
            local_lines, 
            remote_lines, 
            fromfile=f"local:{filepath}",
            tofile=f"remote:{remote_path}",
            lineterm=''
        ))
        
        if not diff:
            return "文件内容完全相同"
        
        result_lines = []
        for line in diff:
            if line.startswith('+++') or line.startswith('---') or line.startswith('@@'):
                continue
            elif line.startswith('+'):
                result_lines.append(f"远程文件多出: {line[1:]}")
            elif line.startswith('-'):
                result_lines.append(f"远程文件缺少: {line[1:]}")
            elif line.startswith(' '):
                continue
        
        if not result_lines:
            return "文件内容完全相同"
        
        return '\n'.join(result_lines)
        
    except FileNotFoundError:
        return f"本地文件不存在: {filepath}"
    except Exception as e:
        return f"比较文件内容时出错: {str(e)}"

def get_latest_version(url: str, prefix: str = "") -> str:
    content = ""
    
    if "api.github.com" in url:
        headers = {"User-Agent": "version-checker"}
        headers["Accept"] = "application/vnd.github+json"
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        resp = requests.get(url, headers=headers, timeout=15)
        
        if resp.status_code == 403:
            remaining = resp.headers.get("X-RateLimit-Remaining")
            reset = resp.headers.get("X-RateLimit-Reset")
            if remaining == "0" and reset:
                reset_ts = int(reset)
                wait_s = max(0, reset_ts - int(time.time()))
                raise RuntimeError(
                    f"GitHub API 触发限流：请在 {wait_s}s 后再试，或配置 GITHUB_TOKEN 提升额度"
                )
            raise RuntimeError(f"GitHub API 403: {resp.text}")
        
        if resp.status_code != 200:
            raise RuntimeError(f"GitHub API 请求失败: {resp.status_code}, {resp.text}")
        
        data = resp.json()
        content = " ".join([tag.get("name", "") for tag in data])
    
    else:
        sess = requests.Session()
        
        try:
            r = sess.get(url, timeout=(2, 5))
            r.raise_for_status()
            content = r.text
        except Exception:
            r = sess.get(url, timeout=(2, 10))
            r.raise_for_status()
            content = r.text
    
    versions = []
    
    version_patterns = [
        r"(\d+\.\d+\.\d+)",  # x.y.z
        r"(\d+\.\d+)",       # x.y
        r"((?:\d+\.)+\d+p\d+)",  # x.y.zpN (OpenSSH 格式)
        r"v(\d+\.\d+\.\d+)", # vx.y.z
    ]
    
    for pattern in version_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0] if match[0] else match[1]
            
            version_str = match.strip().lstrip('v')
            
            if version_str.startswith(prefix):
                versions.append(version_str)
    
    versions = list(set(versions))
    
    if not versions:
        raise ValueError(f"未找到前缀为 {prefix} 的版本")
    
    def version_key(v: str):
        m = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?p(\d+)$", v)
        if m:
            return tuple(int(x or 0) for x in m.groups())
        try:
            return tuple(map(int, v.split('.')))
        except ValueError:
            return (-1, -1, -1, -1)
    
    latest_version = max(versions, key=version_key)
    return latest_version
