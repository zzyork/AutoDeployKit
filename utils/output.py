from colorama import init, Fore, Style
import datetime

init(autoreset=True)
LOG_FILE = "server_init.log"

def log(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {msg}\n")

def print_info(msg):
    print(Fore.CYAN + msg)
    log("INFO: " + msg)

def print_success(msg):
    print(Fore.GREEN + msg)
    log("SUCCESS: " + msg)

def print_warning(msg):
    print(Fore.YELLOW + msg)
    log("WARNING: " + msg)

def print_error(msg):
    print(Fore.RED + msg)
    log("ERROR: " + msg)
