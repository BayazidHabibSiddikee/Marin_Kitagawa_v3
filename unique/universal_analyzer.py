import os
import platform
import shutil
import subprocess
from datetime import datetime

def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, shell=True).decode().strip()
    except:
        return "Error retrieving data"

def analyze():
    print("="*60)
    print(f"🐸 HS-02 UNIVERSAL SYSTEM ANALYSIS | {datetime.now()}")
    print("="*60)

    # 1. OS & Hardware
    print(f"[+] OS: {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"[+] Processor: {platform.processor()}")

    # 2. Memory Analysis (Using Linux 'free' command for accuracy)
    print("\n[+] Memory Status:")
    print(run_cmd("free -h | grep Mem"))

    # 3. Disk Space (Using shutil)
    total, used, free = shutil.disk_usage("/")
    print(f"\n[+] Disk Usage:")
    print(f"    Total: {total // (2**30)} GB | Used: {used // (2**30)} GB | Free: {free // (2**30)} GB")

    # 4. CPU Load (Using 'uptime')
    print(f"\n[+] CPU Load Average (1, 5, 15 min):")
    print(run_cmd("uptime | awk -F'load average: ' '{print \$2}'"))

    # 5. Network Interface
    print("\n[+] Network Interfaces:")
    print(run_cmd("ip -brief addr | grep 'UP'")[:200] + "...") # Truncated for brevity

    # 6. RAG Server Health Check
    print("\n[+] Backend Check (Port 5080):")
    status = run_cmd("netstat -tuln | grep 5080")
    if status:
        print("    ✅ RAG Server is LISTENING on port 5080")
    else:
        print("    ❌ RAG Server is DOWN")

    print("="*60)

if __name__ == "__main__":
    analyze()
