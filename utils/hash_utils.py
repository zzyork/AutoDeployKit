import hashlib
from utils.ssh_utils import run_command

def get_local_md5(filepath):
    """计算本地文件的 MD5 哈希值"""
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def get_remote_md5(client, remote_path):
    output, _, _ = run_command(client, f"md5sum {remote_path} | awk '{{print $1}}'")
    return output.strip()
