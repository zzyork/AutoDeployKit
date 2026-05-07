from agent.runner import collect_diagnosis, maybe_execute_repair, render_diagnosis
from utils.output import print_info, print_warning


def run(clients):
    question = input("请输入自然语言问题（例如：nginx 502，帮我定位一下）: ").strip()
    if not question:
        print_warning("未输入问题，已退出 Agent 诊断。")
        return

    print_info(f"收到问题：{question}")
    print_warning("默认只做只读诊断；如需修复，会先征求确认。")

    for host, client in clients:
        diagnosis = collect_diagnosis(client, host, question)
        render_diagnosis(diagnosis)
        maybe_execute_repair(client, diagnosis)
