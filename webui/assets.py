import ipaddress
import re


def validate_host(name, address, port, username, group_name):
    if not isinstance(name, str) or not re.fullmatch(r"[\w. -]{1,80}", name):
        raise ValueError("Invalid asset name")
    if not isinstance(address, str) or len(address) > 253:
        raise ValueError("Invalid host address")
    try:
        ipaddress.ip_address(address)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", address):
            raise ValueError("Invalid host address") from None
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("Invalid SSH port")
    if not isinstance(username, str) or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", username
    ):
        raise ValueError("Invalid SSH username")
    if not isinstance(group_name, str) or not re.fullmatch(r"[\w. -]{1,80}", group_name):
        raise ValueError("Invalid asset group")
