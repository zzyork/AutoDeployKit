import os
import re
import sys
import tempfile
import time
from string import Template
import hashlib
import difflib
from datetime import datetime, timezone

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

def get_stable_version(url: str, prefix: str = "") -> tuple[int, str]:
    """从网页或 GitHub API 中提取最新稳定版本号。

    返回值保持历史兼容：成功返回 ``(0, version)``，失败返回 ``(1, error_message)``。
    ``prefix`` 可用于限定版本前缀，例如 ``"1.28."`` 或 ``"8.0."``。
    """
    normalized_prefix = (prefix or "").strip().lstrip("v")

    def _version_matches_prefix(version: str) -> bool:
        if not normalized_prefix:
            return True
        return version.startswith(normalized_prefix)

    def _is_prerelease(version: str) -> bool:
        return bool(re.search(r"(?:^|[._-])(alpha|beta|rc|preview|dev|nightly|snapshot)(?:[._-]?\d*)?$", version, re.I))

    def _version_key(version: str):
        version = version.strip().lstrip("v").replace("_", ".")
        version = re.sub(r"[+-].*$", "", version)

        # OpenSSH/OpenSSL 风格：9.9p2、1.1.1w
        parts = []
        for token in re.findall(r"\d+|[a-z]+", version, re.I):
            if token.isdigit():
                parts.append(int(token))
            else:
                # 字母后缀按自然顺序排序：a < b < ... < w
                parts.extend(ord(ch.lower()) - ord("a") + 1 for ch in token)
        return tuple(parts) if parts else (-1,)

    def _extract_versions(text: str) -> list[str]:
        candidates = set()
        patterns = [
            r"(?<![\w.])v?(\d+\.\d+\.\d+(?:p\d+)?[a-z]?)(?![\w.])",
            r"(?<![\w.])v?(\d+\.\d+(?:p\d+)?[a-z]?)(?![\w.])",
            r"(?<![\w])v?(\d+_\d+_\d+[a-z]?)(?![\w])",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, text or "", re.I):
                version = match.strip().lstrip("v").replace("_", ".")
                if _version_matches_prefix(version) and not _is_prerelease(version):
                    candidates.add(version)
        return sorted(candidates, key=_version_key, reverse=True)

    def _request(url_: str) -> requests.Response:
        headers = {"User-Agent": "AutoDeployKit/version-checker"}
        if "api.github.com" in url_:
            headers["Accept"] = "application/vnd.github+json"
            token = os.getenv("GITHUB_TOKEN")
            if token:
                headers["Authorization"] = f"Bearer {token}"

        last_error = None
        for timeout in ((3, 8), (5, 15)):
            try:
                response = requests.get(url_, headers=headers, timeout=timeout)
                if response.status_code == 403 and "api.github.com" in url_:
                    remaining = response.headers.get("X-RateLimit-Remaining")
                    reset = response.headers.get("X-RateLimit-Reset")
                    if remaining == "0" and reset:
                        wait_s = max(0, int(reset) - int(time.time()))
                        raise RuntimeError(f"GitHub API 触发限流：请在 {wait_s}s 后再试，或配置 GITHUB_TOKEN 提升额度")
                response.raise_for_status()
                return response
            except Exception as e:
                last_error = e
        raise RuntimeError(last_error)

    try:
        response = _request(url)

        if "api.github.com" in url:
            data = response.json()
            if isinstance(data, dict):
                items = data.get("items") or data.get("releases") or data.get("tags") or []
            else:
                items = data
            content = " ".join(
                str(item.get("name") or item.get("tag_name") or "")
                for item in items
                if isinstance(item, dict)
            )
        else:
            content = response.text
    except Exception as e:
        return 1, f"获取版本信息失败: {e}"

    # Nginx 官网下载页有明确的 Stable version 区块，优先使用，避免 Mainline/Legacy version 干扰。
    if "nginx.org/en/download.html" in url:
        stable_block_match = re.search(
            r"Stable\s+version(?P<block>.*?)(?:Legacy\s+versions|Source\s+Code|Pre-Built\s+Packages|$)",
            content,
            re.I | re.S,
        )
        stable_block = stable_block_match.group("block") if stable_block_match else content
        stable_versions = [
            version
            for version in _extract_versions(stable_block)
            if _version_matches_prefix(version)
        ]
        if stable_versions:
            return 0, stable_versions[0]

    versions = _extract_versions(content)
    if not versions:
        prefix_tip = f"前缀为 {normalized_prefix} 的" if normalized_prefix else "可用"
        return 1, f"未找到{prefix_tip}稳定版本"

    return 0, versions[0]


def get_eol_date(software: str, version: str) -> str:
    if not version or not software:
        return "Unknown"

    url = f"https://endoflife.date/api/{software.strip().lower()}.json"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch EOL data from endoflife.date: {e}")

    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Invalid JSON from endoflife.date: {e}")

    if not isinstance(data, list):
        raise RuntimeError("Unexpected EOL API response format")

    normalized = version.strip().lower().lstrip("v")
    candidates = []
    m = re.match(r"^(\d+\.\d+)", normalized)
    if m:
        candidates.append(m.group(1))
    m = re.match(r"^(\d+)", normalized)
    if m:
        candidates.append(m.group(1))
    candidates.append(normalized)

    best = None
    best_score = -1
    best_len = -1
    for entry in data:
        cycle = str(entry.get("cycle", "")).strip().lower()
        if not cycle:
            continue
        score = 0
        if cycle == normalized:
            score = 3
        elif normalized.startswith(cycle):
            score = 2
        elif cycle in candidates:
            score = 1

        if score > best_score or (score == best_score and len(cycle) > best_len):
            best_score = score
            best_len = len(cycle)
            best = entry

    if not best or best_score <= 0:
        return "Unknown"

    eol = best.get("eol")
    if not eol or eol is False:
        return "Unknown"

    if isinstance(eol, str):
        try:
            dt = datetime.strptime(eol, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return "Unknown"

        now = datetime.now(timezone.utc)
        if dt <= now:
            return f"{software} {version} 的官方支持已于 {eol} 结束"
        return f"{software} {version} 的官方支持将于 {eol} 结束"

    return "Unknown"
