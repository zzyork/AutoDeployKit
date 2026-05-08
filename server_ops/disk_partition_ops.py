import re
import shlex

from utils.ssh_utils import run_command_live, run_command
from utils.output import print_info, print_success, print_warning, print_error
from utils.choice import confirm_yes_no
from colorama import Fore

VG_NAME = "vg_data"
LV_NAME = "lv_data"


def get_partition_path(disk, partition_number=1):
    """返回 Linux 分区路径，兼容 /dev/sdb1 与 /dev/nvme0n1p1 这两类命名。"""
    disk_name = disk.rsplit("/", 1)[-1]
    separator = "p" if disk_name[-1:].isdigit() else ""
    return f"{disk}{separator}{partition_number}"


def validate_mount_point(mount_point):
    return mount_point.startswith("/") and ".." not in mount_point and not re.search(r"\s", mount_point)


def lvm_name_exists(client):
    vg_out, _, _ = run_command(client, f"vgs --noheadings -o vg_name {shlex.quote(VG_NAME)} 2>/dev/null || true")
    lv_out, _, _ = run_command(client, f"lvs --noheadings -o lv_name {shlex.quote(VG_NAME)}/{shlex.quote(LV_NAME)} 2>/dev/null || true")
    return bool(vg_out.strip() or lv_out.strip())


def is_disk_in_use(client, disk_path):
    """保守判断整盘是否已被使用，避免清空已有文件系统、LVM、RAID 或 swap。"""
    quoted_disk = shlex.quote(disk_path)
    checks = [
        f"lsblk -nr -o MOUNTPOINT {quoted_disk} | awk 'NF {{print}}'",
        f"blkid {quoted_disk} 2>/dev/null",
        f"pvs --noheadings -o pv_name 2>/dev/null | grep -Fx {quoted_disk}",
        f"swapon --noheadings --raw --show=NAME 2>/dev/null | grep -Fx {quoted_disk}",
        f"mdadm --examine {quoted_disk} >/dev/null 2>&1 && echo RAID",
        f"wipefs -n {quoted_disk} 2>/dev/null | awk 'NR > 1 {{print}}'",
    ]

    for cmd in checks:
        output, _, status = run_command(client, cmd)
        if status == 0 and output.strip():
            return True
    return False

def list_unmounted_disks(client):
    print_info("正在查找未分区、未挂载且无已知占用签名的裸磁盘 ...")

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

        if is_disk_in_use(client, full_path):
            continue

        # 检查是否有分区存在
        check_part_cmd = f"lsblk -nr {shlex.quote(full_path)} -o NAME | grep -Fxv {shlex.quote(disk)}"
        part_output, _, _ = run_command(client, check_part_cmd)

        if not part_output.strip():
            valid_disks.append(full_path)

    return valid_disks


def create_lvm_and_mount(client, disk):
    print_info(f"开始在 {disk} 上创建 LVM")
    partition = get_partition_path(disk)

    if is_disk_in_use(client, disk):
        print_error(f"磁盘 {disk} 已检测到占用签名，取消操作")
        return
    if lvm_name_exists(client):
        print_error(f"LVM 名称 /dev/{VG_NAME}/{LV_NAME} 已存在，取消操作以避免覆盖")
        return

    cmds = [
        f"parted -s {shlex.quote(disk)} mklabel gpt",
        f"parted -s {shlex.quote(disk)} mkpart primary 0% 100%",
        f"partprobe {shlex.quote(disk)}",
        f"pvcreate {shlex.quote(partition)}",
        f"vgcreate {VG_NAME} {shlex.quote(partition)}",
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
    
    mount_point = input("请输入挂载点(/data): ").strip() or "/data"
    if not validate_mount_point(mount_point):
        print_error("挂载点必须是绝对路径，且不能包含空白字符")
        return

    uuid, _, status = run_command(client, f"blkid -s UUID -o value /dev/{VG_NAME}/{LV_NAME}")
    if status != 0:
        print_error("获取 UUID 失败")
        return
    
    cmds = [
        f"mkdir -p {shlex.quote(mount_point)}",
        f"mount UUID={uuid.strip()} {shlex.quote(mount_point)}",
    ]

    for cmd in cmds:
        _, status = run_command_live(client, cmd)
        if status != 0:
            print_error(f"执行失败: {cmd}")
            return

    if confirm_yes_no("是否开机自动挂载？", default=False):
        fstab_line = f"UUID={uuid.strip()} {mount_point} xfs defaults 0 0"
        exists, _, _ = run_command(client, f"grep -F {shlex.quote('UUID=' + uuid.strip())} /etc/fstab >/dev/null 2>&1 && echo YES || echo NO")
        if exists.strip() == "YES":
            print_warning("/etc/fstab 中已存在该 UUID，跳过重复写入")
            print_success(f"{disk} 已完成 LVM 创建并挂载到 {mount_point}")
            return
        _, status = run_command_live(client, f"echo {shlex.quote(fstab_line)} >> /etc/fstab")
        if status != 0:
            print_error("写入 /etc/fstab 失败")
            return
        print_success("已写入 /etc/fstab，配置为开机自动挂载")

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
