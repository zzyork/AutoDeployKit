# 服务器初始化优化工具

该工具旨在帮助用户自动化完成服务器初始化配置和优化任务，提高服务器的安全性、稳定性和性能。

## 功能特性

- **主机名管理**：自动设置或修改服务器主机名。
- **磁盘分区与LVM管理**：自动识别未挂载磁盘并创建LVM逻辑卷进行挂载。
- **防火墙与SELinux管理**：检查并禁用firewalld和SELinux以减少安全策略限制。
- **内核优化**：优化系统资源限制和内核参数（sysctl）。
- **系统优化**：配置NTP时间同步、优化Vim配置。
- **YUM源管理**：备份、列出和修改YUM软件仓库配置。
- **软件包管理**：升级系统软件包、安装基础依赖和工具。
- **OpenSSL升级**：支持升级OpenSSL 1.1.1和OpenSSL 3.0.x版本，并修复相关依赖问题。
- **SSH远程操作**：通过SSH连接远程服务器并执行命令或文件传输。

## 使用方法

1. **配置主机列表**：在`hosts`文件中配置需要操作的服务器信息，格式如下：
   ```
   [group_name]
   host1 ansible_user=username ansible_ssh_pass=password
   host2 ansible_user=username ansible_ssh_private_key_file=/path/to/private_key
   ```

2. **运行工具**：使用`cli.py`脚本运行工具，支持指定主机组和操作类型。例如：
   ```bash
   python cli.py -g group_name
   ```

3. **查看帮助**：运行以下命令获取更多使用选项：
   ```bash
   python cli.py --help
   ```

## 主要模块

- `cli.py`：命令行接口，用于解析用户输入并启动相应操作。
- `server_ops/`：核心操作模块，包含各类服务器优化任务。
- `utils/`：工具类模块，提供SSH连接、文件传输、日志输出等功能。
- `config/`：配置文件目录，包含Vim和sysctl配置模板。
- `scripts/`：辅助脚本目录，如`get-pip.py`用于安装pip工具。
- `packages/`：软件包目录，存放OpenSSL等需要安装的软件包。

## 许可证

本项目遵循MIT许可证。有关详细信息，请参阅[LICENSE](LICENSE)文件。