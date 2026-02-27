from importlib import import_module
from utils import output
from utils.ssh_utils import run_command_live, run_command
from utils.output import print_info, print_success, print_warning, print_error
from utils.choice import confirm_yes_no, menu_choice
from colorama import Fore

VG_NAME = "vg_data"
LV_NAME = "lv_data"

def list_unmounted_disks(client):
    print_info("正在查找未分区且未挂载的裸磁盘 ...")

    # 列出所有磁盘及其子设备
    lsblk_cmd = (
        "lsblk -dn -o NAME,TYPE | awk '$2 == \"disk\" { print $1 }'"
    )
    output, _, _ = run_command(client, lsblk_cmd)
    all_disks = output.strip().splitlines()

    valid_disks = []

    for disk in all_disks:
        # 排除 loop、sr0、cdrom、ram 设备
        if disk.startswith(("loop", "sr", "ram", "fd")):
            continue

        full_path = f"/dev/{disk}"

        # 检查是否有分区存在
        check_part_cmd = f"lsblk {full_path} -no NAME | grep -v '^{disk}$'"
        part_output, _, _ = run_command(client, check_part_cmd)

        if not part_output.strip():
            valid_disks.append(full_path)

    return valid_disks


def create_lvm_and_mount(client, disk):
    print_info(f"开始在 {disk} 上创建 LVM")

    cmds = [
        f"parted -s {disk} mklabel gpt",
        f"parted -s {disk} mkpart primary 0% 100%",
        f"partprobe {disk}",
        f"pvcreate {disk}1",
        f"vgcreate {VG_NAME} {disk}1",
        f"lvcreate -n {LV_NAME} -l 100%FREE {VG_NAME}",
        f"mkfs.xfs /dev/{VG_NAME}/{LV_NAME}",
    ]

    for cmd in cmds:
        _, status = run_command_live(client, cmd)
        if status != 0:
            print_error(f"执行失败: {cmd}")
            return
    
    if not confirm_yes_no("新磁盘已分区并创建 LVM，是否挂载？", default=False):
        return
    
    mount_point = input("请输入挂载点(/data): ").strip()
    uuid, status = run_command(client, f"blkid -s UUID -o value /dev/{VG_NAME}/{LV_NAME}")
    if status != 0:
        print_error("获取 UUID 失败")
        return
    
    cmds = [
        f"mkdir -p {mount_point}",
        f"mount UUID={uuid.strip()} {mount_point}",
        f"echo \"UUID={uuid.strip()} {mount_point} xfs defaults 0 0\" >> /etc/fstab"
    ]

    for cmd in cmds:
        _, status = run_command_live(client, cmd)
        if status != 0:
            print_error(f"执行失败: {cmd}")
            return

    if not confirm_yes_no("是否开机自动挂载？", default=False):
        return
    
    output, status = run_command_live(client, f'echo "/dev/{VG_NAME}/{LV_NAME} {mount_point} xfs defaults 0 0" >> /etc/fstab')
    if status != 0:
        print_error(f"执行失败: {cmd}")
        return

    print_success(f"{disk} 已完成 LVM 创建并挂载到 {mount_point}")

def manage_disk_partition(client):
    print(Fore.BLUE + "\n=== 磁盘分区与挂载配置 ===")

    unmounted_disks = list_unmounted_disks(client)
    if not unmounted_disks:
        print_warning("未找到可用的未挂载磁盘")
        return

    print_info("检测到以下未挂载磁盘：")
    for i, d in enumerate(unmounted_disks, 1):
        print(f"{i}. {d}")

    choice = input(Fore.MAGENTA + f"\n请选择要使用的磁盘编号（1-{len(unmounted_disks)}），或按 Enter 跳过: ").strip()
    if not choice or not choice.isdigit() or not (1 <= int(choice) <= len(unmounted_disks)):
        print_warning("取消磁盘挂载配置")
        return

    disk = unmounted_disks[int(choice) - 1]
    if confirm_yes_no(f"⚠️ 确定要对 {disk} 分区并清空其数据？", default=False):
        create_lvm_and_mount(client, disk)
    else:
        print_warning("已取消该磁盘处理")
