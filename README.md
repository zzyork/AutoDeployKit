

# 服务器初始化优化工具

一个自动化服务器初始化与部署工具包，面向 DevOps 场景，支持自定义模块、组件安装与系统优化。

## 功能特性

- **一键执行多步服务器初始化操作**
- **支持主机配置文件，批量管理主机**
- **实时输出每个步骤的执行情况**
- **可选项执行每一步操作，避免破坏生产环境**
- **预集成常见依赖包与配置文件，提升部署效率**

## 使用方法

1. 安装依赖包：
```bash
pip install -r requirements.txt
```

2. 添加hosts 文件以配置目标服务器信息。
   ```tex
    [group]
    192.168.1.1 user=root password=123456 port=22 keyfile=/root/.ssh/id_rsa.pub
   ```
   密码和keyfile配置一个即可。

3. 运行 cli.py 脚本开始操作（group在hosts文件中配置）：
```bash
python cli.py {module} {group}
```

1. 模块列表

- server_ops：服务器管理模块
- software_ops：软件管理模块
- monitor_ops：prometheus监控管理模块


## 主要模块

```bash
autodeploykit/
├── cli.py                            # 项目入口 CLI，用于选择并执行任务
├── hosts                             # 服务器连接信息配置
├── requirements.txt                  # Python 依赖列表
├── config/                           # 各类配置文件（如 vim、nginx、sysctl）
├── packages/                         # 预下载的软件包（nginx、openssl 等）
├── scripts/                          # 辅助脚本（如 get-pip.py）
└── server_ops/                       # 各类服务器操作模块
    ├── hostname_ops.py               # 修改主机名
    ├── yum_repos_ops.py              # 配置 YUM 源
    ├── openssl_upgrade.py            # 升级 OpenSSL
    ├── disk_partition_ops.py         # 分区和挂载磁盘
    ├── firewall_selinux_ops.py       # 配置防火墙和 SELinux
    ├── kernel_optimize_ops.py        # 系统内核参数优化
    ├── pkg_ops.py                    # 安装依赖包
    ├── system_optimize_ops.py        # 其他系统优化操作
    └── main.py                       # 调度各模块执行
└── software_ops/                     # 各类服务器操作模块
    ├── nginx_manager.py              # 安装与升级nginx
    └── main.py                       # 调度各模块执行

```

## 许可证

本项目使用 Apache-2.0 许可证，请参阅 LICENSE 文件获取详细信息。