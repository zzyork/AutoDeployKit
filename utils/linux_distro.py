"""Identify a remote Linux distribution without conflating it with RPM compatibility."""

import shlex

from utils.ssh_utils import run_command


def _parse_os_release(content):
    values = {}
    for line in content.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in ("ID", "VERSION_ID", "PRETTY_NAME", "ID_LIKE"):
            continue
        try:
            parts = shlex.split(value, comments=False)
        except ValueError as exc:
            raise ValueError(f"无效的 /etc/os-release 字段：{key}") from exc
        if len(parts) != 1:
            raise ValueError(f"无效的 /etc/os-release 字段：{key}")
        values[key] = parts[0]

    distro_id = values.get("ID", "").lower()
    if not distro_id:
        raise ValueError("/etc/os-release 缺少 ID")
    version_id = values.get("VERSION_ID", "")
    major = version_id.split(".", 1)[0]
    el_series = None
    # ponytail: 这里只列已知的 RPM 包系列；其他衍生版/版本需单独验证后再扩展。
    if distro_id in ("centos", "rhel", "rocky", "almalinux", "ol") and major in ("7", "8", "9"):
        el_series = major
    elif (distro_id, version_id) in (("openeuler", "22.03"), ("hce", "2.0")):
        el_series = "8"

    return {
        "id": distro_id,
        "version_id": version_id,
        "pretty_name": values.get("PRETTY_NAME", distro_id),
        "id_like": tuple(values.get("ID_LIKE", "").lower().split()),
        "el_series": el_series,
    }


def get_linux_distribution(client):
    """Read /etc/os-release via an existing SSH client; reject unsupported RPM series.

    el_series is an RPM packaging hint, not a claim that a derivative is CentOS.
    Raises RuntimeError on read failure and ValueError on invalid or unsupported systems.
    """
    content, error, status = run_command(client, "cat /etc/os-release")
    if status != 0:
        raise RuntimeError(f"无法识别目标系统：无法读取 /etc/os-release：{error or content or f'退出码 {status}'}")
    try:
        distribution = _parse_os_release(content)
    except ValueError as exc:
        raise ValueError(f"无法识别目标系统：{exc}") from exc
    if distribution["el_series"] is None:
        raise ValueError("不支持的系统：" + distribution["pretty_name"])
    return distribution
