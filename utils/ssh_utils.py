import paramiko
import time


def _as_int(value, default=22):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _connect_with_auth(client, hostname, username, password=None, key_file=None, port=22, **kwargs):
    """Helper to connect using either password or key file."""
    connect_kwargs = {"hostname": hostname, "username": username, "port": _as_int(port)}
    connect_kwargs.update(kwargs)

    if key_file:
        connect_kwargs["pkey"] = _load_private_key(key_file)
    else:
        connect_kwargs["password"] = password

    client.connect(**connect_kwargs)


def _load_private_key(key_file):
    """Try loading different key types (ed25519/ecdsa/rsa/dss)."""
    loaders = (
        paramiko.Ed25519Key,
        paramiko.ECDSAKey,
        paramiko.RSAKey,
        paramiko.DSSKey,
    )
    last_exc = None
    for loader in loaders:
        try:
            return loader.from_private_key_file(key_file)
        except (OSError, paramiko.SSHException) as exc:
            last_exc = exc
            continue

    # If nothing worked, bubble up the last error to aid debugging.
    if last_exc:
        raise last_exc
    raise paramiko.SSHException("Unable to load private key: unknown error")


def ssh_connect(
    host,
    user,
    password=None,
    key_file=None,
    port=22,
    proxy=None,
    proxy_user=None,
    proxy_password=None,
    proxy_keyfile=None,
    proxy_port=22,
):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # 只有同时提供代理地址和至少一种认证方式时才走代理隧道
    use_proxy = proxy and (proxy_password or proxy_keyfile or proxy_user)

    if use_proxy:
        # 先连接代理机，再通过 direct-tcpip 打开到目标主机的隧道
        proxy_client = paramiko.SSHClient()
        proxy_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        _connect_with_auth(
            proxy_client,
            hostname=proxy,
            username=proxy_user or user,
            password=proxy_password,
            key_file=proxy_keyfile,
            port=proxy_port,
        )

        transport = proxy_client.get_transport()
        if not transport:
            raise RuntimeError("代理连接建立失败，无法获取 transport")

        tunnel = transport.open_channel(
            kind="direct-tcpip",
            dest_addr=(host, _as_int(port)),
            src_addr=("127.0.0.1", 0),
        )

        _connect_with_auth(
            client,
            hostname=host,
            username=user,
            password=password,
            key_file=key_file,
            port=port,
            sock=tunnel,
        )

        # 保存代理 client，关闭时一起清理
        client._proxy_client = proxy_client  # noqa: SLF001
    else:
        _connect_with_auth(
            client,
            hostname=host,
            username=user,
            password=password,
            key_file=key_file,
            port=port,
        )

    return client


def close_ssh_client(client):
    """关闭目标连接及其代理连接（如有）"""
    proxy_client = getattr(client, "_proxy_client", None)
    try:
        client.close()
    finally:
        if proxy_client:
            proxy_client.close()


def run_command(client, command):
    """执行远程命令，加载环境变量"""
    # 先加载环境变量，再执行命令
    full_command = f"source /etc/profile; {command}"
    stdin, stdout, stderr = client.exec_command(full_command)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    status = stdout.channel.recv_exit_status()
    return out, err, status


def run_command_live(client, command):
    """执行远程命令并实时显示输出，加载环境变量"""
    # 先加载环境变量，再执行命令
    full_command = f"source /etc/profile; {command}"
    print(f"\n>> 正在远程执行: {command}\n")

    transport = client.get_transport()
    channel = transport.open_session()
    channel.get_pty()  # 获取伪终端，保证输出格式正常
    channel.exec_command(full_command)

    output = ""
    while True:
        if channel.recv_ready():
            data = channel.recv(4096).decode("utf-8", errors="ignore")
            output += data
            print(data, end="")  # 实时打印
        if channel.exit_status_ready():
            if channel.recv_ready():
                data = channel.recv(4096).decode("utf-8", errors="ignore")
                output += data
                print(data, end="")
            break
        time.sleep(0.1)

    exit_status = channel.recv_exit_status()
    return output, exit_status
