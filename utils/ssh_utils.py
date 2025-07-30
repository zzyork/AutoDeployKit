import paramiko
import time

def ssh_connect(host, user, password=None, key_file=None, port=22):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    if key_file:
        private_key = paramiko.RSAKey.from_private_key_file(key_file)
        client.connect(hostname=host, username=user, pkey=private_key, port=port)
    else:
        client.connect(hostname=host, username=user, password=password, port=port)

    return client

def run_command(client, command):
    stdin, stdout, stderr = client.exec_command(command)
    out = stdout.read().decode()
    err = stderr.read().decode()
    status = stdout.channel.recv_exit_status()
    return out, err, status

def run_command_live(client, command):
    print(f"\n>> 正在远程执行: {command}\n")

    transport = client.get_transport()
    channel = transport.open_session()
    channel.get_pty()  # 获取伪终端，保证输出格式正常
    channel.exec_command(command)

    output = ""
    while True:
        if channel.recv_ready():
            data = channel.recv(4096).decode('utf-8', errors='ignore')
            output += data
            print(data, end='')  # 实时打印
        if channel.exit_status_ready():
            if channel.recv_ready():
                data = channel.recv(4096).decode('utf-8', errors='ignore')
                output += data
                print(data, end='')
            break
        time.sleep(0.1)

    exit_status = channel.recv_exit_status()
    return output, exit_status

