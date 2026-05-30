import os
import platform
import shutil
import subprocess
from datetime import datetime

def run_cmd(cmd):
    try:
        return subprocess.check_output(cmd, shell=True).decode().strip()
    except:
        return "N/A"

def write_report(section, content):
    with open("unique/full_audit_report.txt", "a") as f:
        f.write(f"\n{'='*60}\n{section}\n{'='*60}\n{content}\n")

def audit_full_system():
    # Clear previous report
    with open("unique/full_audit_report.txt", "w") as f:
        f.write(f"🐸 HS-02 TOTAL SYSTEM AUDIT | Generated: {datetime.now()}\n")

    print("🐸 Scanning Sword-Tyrant... Please wait.")

    # 1. Hardware & OS Deep Dive
    os_info = f"OS: {platform.system()} {platform.release()}\nKernel: {platform.version()}\nMachine: {platform.machine()}\nProcessor: {platform.processor()}"
    write_report("HARDWARE & OS", os_info)

    # 2. Resource Pressure Analysis
    mem = run_cmd("free -h")
    cpu = run_cmd("top -bn1 | head -n 5")
    disk = run_cmd("df -h /")
    write_report("RESOURCE PRESSURE", f"MEM:\n{mem}\n\nCPU:\n{cpu}\n\nDISK:\n{disk}")

    # 3. Process Audit (The Top 10 RAM Eaters)
    # This finds exactly what is slowing down your RAG server
    top_procs = run_cmd("ps aux --sort=-%mem | head -n 11")
    write_report("TOP 10 RAM CONSUMING PROCESSES", top_procs)

    # 4. Network Socket Audit (All Open Ports)
    ports = run_cmd("ss -tulpn")
    write_report("NETWORK SOCKETS (OPEN PORTS)", ports)

    # 5. Hardware Heat/Health (If sensors are available)
    temp = run_cmd("sensors || echo 'Sensors not installed'")
    write_report("THERMAL STATUS", temp)

    print("\n✅ Audit Complete. Report saved to: unique/full_audit_report.txt")
    print("🚀 Run 'cat unique/full_audit_report.txt' to see the results.")

if __name__ == "__main__":
    audit_full_system()
