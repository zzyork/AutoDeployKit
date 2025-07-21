import os
import re
import tempfile
from string import Template

import requests


def download_file(url, dest):
    if os.path.exists(dest):
        return True

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        r = requests.get(url, headers=headers, stream=True)
        r.raise_for_status()

        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        return False

def upload_file(client, local_path, remote_path):
    sftp = client.open_sftp()
    sftp.put(local_path, remote_path)
    sftp.close()

def upload_file_with_vars(client, local_path, remote_path, variables: dict):
    # 1. 读取模板文件内容
    with open(local_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 2. 替换变量：${VAR}
    template = Template(content)
    rendered = template.safe_substitute(variables)

    # 3. 写入到临时文件
    with tempfile.NamedTemporaryFile('w+', delete=False) as tmpfile:
        tmpfile.write(rendered)
        tmpfile_path = tmpfile.name

    try:
        # 4. 上传临时文件
        sftp = client.open_sftp()
        sftp.put(tmpfile_path, remote_path)
        sftp.close()
    finally:
        # 5. 清理临时文件
        os.remove(tmpfile_path)

def get_stable_version_from_github(url, prefix=None):
    tags = []
    response = requests.get(url)
    if response.status_code != 200:
        raise RuntimeError(f"GitHub API 请求失败: {response.status_code}")
    data = response.json()
    for tag in data:
        name = tag["name"].split("-")[-1]
        if prefix:
            if name.startswith(prefix):
                ver_math = re.match(r"^(\d+\.\d+\.\d+)$", name)
                if ver_math:
                    tags.append(name)
        else:
            tags.append(name)

    if not tags:
        raise ValueError(f"未找到前缀为 {prefix} 的版本")

    # 使用 packaging.version 排序，返回最大值
    latest = max(tags)
    return latest.lstrip('v')
