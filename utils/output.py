from colorama import init, Fore, Style
import datetime

init(autoreset=True)
LOG_FILE = "output.log"

def log(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")

def print_info(msg):
    formatted_msg = f"ℹ️  {Fore.CYAN}{Style.BRIGHT}{msg}{Style.RESET_ALL}"
    print(formatted_msg)
    log(f"INFO: {msg}")

def print_success(msg):
    formatted_msg = f"✅ {Fore.GREEN}{Style.BRIGHT}{msg}{Style.RESET_ALL}"
    print(formatted_msg)
    log(f"SUCCESS: {msg}")

def print_warning(msg):
    formatted_msg = f"⚠️  {Fore.YELLOW}{Style.BRIGHT}{msg}{Style.RESET_ALL}"
    print(formatted_msg)
    log(f"WARNING: {msg}")

def print_error(msg):
    formatted_msg = f"❌ {Fore.RED}{Style.BRIGHT}{msg}{Style.RESET_ALL}"
    print(formatted_msg)
    log(f"ERROR: {msg}")

def print_header(msg):
    formatted_msg = f"\n{Fore.BLUE}{Style.BRIGHT}{'='*50}{Style.RESET_ALL}"
    formatted_msg += f"\n{Fore.BLUE}{Style.BRIGHT}  {msg}{Style.RESET_ALL}"
    formatted_msg += f"\n{Fore.BLUE}{Style.BRIGHT}{'='*50}{Style.RESET_ALL}\n"
    print(formatted_msg)
    log(f"HEADER: {msg}")

def print_step(msg, step_num=None, total_steps=None):
    if step_num and total_steps:
        prefix = f"📍 步骤 {step_num}/{total_steps}"
    else:
        prefix = "📍"
    formatted_msg = f"{prefix} {Fore.MAGENTA}{Style.BRIGHT}{msg}{Style.RESET_ALL}"
    print(formatted_msg)
    log(f"STEP: {msg}")
