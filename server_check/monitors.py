from utils.output import print_error
from utils.ssh_utils import run_command


def monitors(client, filename, config=None, alerts=None):
    alerts = alerts if alerts is not None else []
    with open(filename, "a", encoding="utf-8") as f:
        exporters_out, _, _ = run_command(client, "systemctl list-unit-files 2>&1 | grep -i 'exporter' | awk '{print $1}'")
        exporters = [line.strip() for line in exporters_out.splitlines() if line.strip()]
        f.write("## 九、监控状态\n\n")
        if not exporters:
            f.write("未找到任何已安装的 exporter。\n")
        for exporter in exporters:
            status_out, _, status = run_command(client, f"systemctl is-active {exporter}")
            if status == 1:
                print_error("exporter 状态查询失败！")
                return None
            if status_out.strip() == "active":
                f.write(f"- **{exporter}：** ✅ 运行中\n")
            else:
                f.write(f"- **{exporter}：** ☐ 未运行\n")
                alerts.append(f"⚠️ **监控组件 {exporter}：** 未运行")
        f.write("\n")
    return None
