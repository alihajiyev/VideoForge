import os
import sys
from datetime import datetime

if sys.platform == "win32":
    try:
        os.system("")
    except Exception:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    WHITE = "\033[97m"

def _ts():
    return datetime.now().strftime("%H:%M:%S")

def _line(msg, color, icon):
    print(f"{C.GRAY}[{_ts()}]{C.RESET} {color}{icon} {msg}{C.RESET}")

def info(msg):
    _line(msg, C.CYAN, "›")

def ok(msg):
    _line(msg, C.GREEN, "✓")

def warn(msg):
    _line(msg, C.YELLOW, "!")

def err(msg):
    _line(msg, C.RED, "✕")

def step(n, total, msg):
    print(f"{C.GRAY}[{_ts()}]{C.RESET} {C.BLUE}{C.BOLD}[{n}/{total}]{C.RESET} {C.WHITE}{msg}{C.RESET}")

def header(title, subtitle=""):
    bar = "=" * 55
    print(f"\n{C.BLUE}{C.BOLD}{bar}{C.RESET}")
    print(f"{C.BLUE}{C.BOLD}  {title}{C.RESET}")
    if subtitle:
        print(f"{C.GRAY}  {subtitle}{C.RESET}")
    print(f"{C.BLUE}{C.BOLD}{bar}{C.RESET}\n")

def footer_done(msg="Islem tamamlandi"):
    print(f"\n{C.GREEN}{C.BOLD}{'=' * 55}{C.RESET}")
    print(f"{C.GREEN}{C.BOLD}  ✓ {msg}{C.RESET}")
    print(f"{C.GREEN}{C.BOLD}{'=' * 55}{C.RESET}\n")

def footer_fail(msg="Islem basarisiz"):
    print(f"\n{C.RED}{C.BOLD}{'=' * 55}{C.RESET}")
    print(f"{C.RED}{C.BOLD}  ✕ {msg}{C.RESET}")
    print(f"{C.RED}{C.BOLD}{'=' * 55}{C.RESET}\n")

def bar(pct, width=20):
    pct = max(0, min(100, int(pct)))
    fill = pct * width // 100
    return "█" * fill + "░" * (width - fill) + f" {pct}%"
