import paramiko
import shlex
import time


def _as_int(value, default=22):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _connect_with_auth(client, hostname, username, password=None, key_file=None, port=22, pkey=None, web=False, **kwargs):
    """Helper to connect using either password or key file."""
    connect_kwargs = {"hostname": hostname, "username": username, "port": _as_int(port)}
    connect_kwargs.update(kwargs)

    if web:
        if bool(password) == bool(pkey) or key_file:
            raise ValueError("Choose exactly one Web SSH credential")
        connect_kwargs.update(allow_agent=False, look_for_keys=False, timeout=10, auth_timeout=10, banner_timeout=10)
    if pkey:
        connect_kwargs["pkey"] = pkey
    elif key_file:
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
    pkey=None,
    proxy_pkey=None,
    web=False,
):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # 只有同时提供代理地址和至少一种认证方式时才走代理隧道
    use_proxy = proxy and (proxy_password or proxy_keyfile or proxy_user or proxy_pkey)

    if web and (key_file or proxy_keyfile or (proxy and not use_proxy)):
        raise ValueError("Web SSH does not accept file credentials or incomplete proxies")

    try:
        if use_proxy:
            # Store the proxy immediately so failures at any later stage close it.
            proxy_client = paramiko.SSHClient()
            client._proxy_client = proxy_client  # noqa: SLF001
            proxy_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            _connect_with_auth(
                proxy_client,
                hostname=proxy,
                username=proxy_user or user,
                password=proxy_password,
                key_file=proxy_keyfile,
                pkey=proxy_pkey,
                web=web,
                port=proxy_port,
            )

            transport = proxy_client.get_transport()
            if not transport:
                raise RuntimeError("代理连接建立失败，无法获取 transport")

            tunnel = transport.open_channel(
                kind="direct-tcpip",
                dest_addr=(host, _as_int(port)),
                src_addr=("127.0.0.1", 0),
                **({"timeout": 10} if web else {}),
            )

            _connect_with_auth(
                client,
                hostname=host,
                username=user,
                password=password,
                key_file=key_file,
                pkey=pkey,
                web=web,
                port=port,
                sock=tunnel,
            )
        else:
            _connect_with_auth(
                client,
                hostname=host,
                username=user,
                password=password,
                key_file=key_file,
                pkey=pkey,
                web=web,
                port=port,
            )

        client._login_user = user  # noqa: SLF001
        client._web_mode = web  # noqa: SLF001
        return client
    except Exception:
        close_ssh_client(client)
        raise


def close_ssh_client(client):
    """关闭目标连接及其代理连接（如有）"""
    proxy_client = getattr(client, "_proxy_client", None)

    def _close_one(ssh_client):
        if not ssh_client:
            return
        try:
            transport = ssh_client.get_transport()
        except Exception:
            transport = None

        if transport:
            try:
                transport.close()
            except Exception:
                pass

        try:
            ssh_client.close()
        except Exception:
            pass

    try:
        _close_one(client)
    finally:
        if proxy_client:
            _close_one(proxy_client)


def run_command(client, command, strip_output=True):
    """执行远程命令，加载环境变量"""
    if getattr(client, "_web_mode", False) is True:
        return _run_web_command(client, command, strip_output)
    full_command = _build_remote_command(client, command)
    stdin, stdout, stderr = client.exec_command(full_command)
    out = stdout.read().decode()
    err = stderr.read().decode().strip()
    status = stdout.channel.recv_exit_status()
    return out.strip() if strip_output else out, err, status


def _run_web_command(client, command, strip_output):
    host_deadline = getattr(client, "_web_deadline", None)
    deadline = min(time.monotonic() + 20, host_deadline if isinstance(host_deadline, (int, float)) else float("inf"))
    if time.monotonic() >= deadline:
        raise TimeoutError("Host inspection timed out")
    transport = client.get_transport()
    if transport is None:
        raise RuntimeError("SSH transport is unavailable")
    channel = transport.open_session(timeout=10)
    stdout = bytearray()
    stderr = bytearray()
    try:
        channel.settimeout(10)
        channel.exec_command(_build_remote_command(client, command))
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("Remote read timed out")
            while channel.recv_ready():
                stdout.extend(channel.recv(4096))
                if len(stdout) + len(stderr) > 262144:
                    raise ValueError("Remote output is too large")
            while channel.recv_stderr_ready():
                stderr.extend(channel.recv_stderr(4096))
                if len(stdout) + len(stderr) > 262144:
                    raise ValueError("Remote output is too large")
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            time.sleep(0.01)
        status = channel.recv_exit_status()
        out = stdout.decode("utf-8", errors="replace")
        return out.strip() if strip_output else out, stderr.decode("utf-8", errors="replace").strip(), status
    finally:
        channel.close()


def run_command_live(client, command, timeout_seconds=None, *, use_pty=True):
    """执行远程命令；可限制本地等待总时长，超时不发送终止信号。"""
    if timeout_seconds is not None and timeout_seconds <= 0:
        raise ValueError("命令超时必须大于 0")
    deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
    full_command = _build_remote_command(client, command)
    print(f"\n>> 正在远程执行: {command}\n")

    transport = client.get_transport()
    if transport is None:
        raise RuntimeError("SSH transport 不可用")
    channel = transport.open_session(timeout=timeout_seconds) if deadline is not None else transport.open_session()
    try:
        if deadline is not None:
            channel.settimeout(max(0.001, deadline - time.monotonic()))
        channel.set_combine_stderr(True)
        if use_pty:
            channel.get_pty()
        if deadline is not None:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"远程命令等待超过 {timeout_seconds} 秒")
            channel.settimeout(max(0.001, deadline - time.monotonic()))
        channel.exec_command(full_command)

        output = ""
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"远程命令等待超过 {timeout_seconds} 秒")
            if channel.recv_ready():
                data = channel.recv(4096).decode("utf-8", errors="ignore")
                output += data
                print(data, end="")
            if channel.exit_status_ready() and not channel.recv_ready():
                return output, channel.recv_exit_status()
            time.sleep(0.1)
    finally:
        channel.close()


def _build_remote_command(client, command):
    """根据登录用户决定是否使用 sudo su 提权执行。"""
    if getattr(client, "_web_mode", False) is True:
        return command
    base_command = f"source /etc/profile; {command}"
    login_user = getattr(client, "_login_user", None)
    if isinstance(login_user, str) and login_user.strip().lower() != "root":
        root_command = f"bash -lc {shlex.quote(base_command)}"
        return f"sudo su - root -c {shlex.quote(root_command)}"
    return base_command
