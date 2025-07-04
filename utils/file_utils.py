import os
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