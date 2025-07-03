

# 服务器初始化优化工具

这是一个用于自动化执行服务器任务的 Python 工具集，适用于 Linux 系统管理。
目前只写了一个服务器初始化功能，正在添加其他功能

## 功能特性

- **主机名管理**
- **软件包安装与升级**
- **磁盘分区与 LVM 管理**
- **防火墙与 SELinux 配置**
- **YUM 源管理**
- **系统优化**
- **SSH 远程连接与文件上传**

## 使用方法

1. 安装依赖包：
```bash
pip install -r requirements.txt
```

2. 修改 hosts 文件以配置目标服务器信息。

3. 运行 cli.py 脚本开始操作（group在hosts文件中配置）：
```bash
python cli.py {module} {group}
```

4. 模块列表
server_ops：服务器模块

## 主要模块

- `cli.py`：主命令行接口
- `server_ops/`：操作模块，包含以下功能：
  - `disk_partition_ops.py`：磁盘管理
  - `firewall_selinux_ops.py`：防火墙与 SELinux 管理
  - `hostname_ops.py`：主机名管理
  - `kernel_optimize_ops.py`：内核参数优化
  - `pkg_ops.py`：软件包管理
  - `server_init.py`：初始化入口
  - `system_optimize_ops.py`：系统优化
  - `yum_repos_ops.py`：YUM 源管理

- `utils/`：工具模块，包含以下功能：
  - `hash_utils.py`：文件哈希计算
  - `output.py`：信息输出与日志记录
  - `ssh_utils.py`：SSH 连接与命令执行

## 许可证

本项目使用 Apache-2.0 许可证，请参阅 LICENSE 文件获取详细信息。