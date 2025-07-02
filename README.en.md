# Server Initialization Optimization Tool

This is a Python toolkit designed to automate server initialization and optimization tasks, suitable for Linux system administration.

## Features

- **Hostname Management**
- **Package Installation and Upgrade**
- **Disk Partitioning and LVM Management**
- **Firewall and SELinux Configuration**
- **YUM Repository Management**
- **System Optimization**
- **SSH Remote Connection and File Upload**

## Usage

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Modify the hosts file to configure target server information.

3. Run the cli.py script to start the operations:
```bash
python cli.py
```

## Main Modules

- `cli.py`: Main command-line interface  
- `server_ops/`: Operation modules, including the following functions:
  - `disk_partition_ops.py`: Disk management  
  - `firewall_selinux_ops.py`: Firewall and SELinux management  
  - `hostname_ops.py`: Hostname management  
  - `kernel_optimize_ops.py`: Kernel parameter optimization  
  - `pkg_ops.py`: Package management  
  - `server_init.py`: Initialization entry point  
  - `system_optimize_ops.py`: System optimization  
  - `yum_repos_ops.py`: YUM repository management  

- `utils/`: Utility modules, including the following functions:
  - `hash_utils.py`: File hash calculation  
  - `output.py`: Information output and logging  
  - `ssh_utils.py`: SSH connection and command execution  

## License

This project uses the Apache-2.0 License. Please refer to the LICENSE file for details.