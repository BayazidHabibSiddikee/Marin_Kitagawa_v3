import psutil
import platform
import socket
import os
from datetime import datetime

def get_size(bytes, suffix=None):
    if suffix == None:
        suffix = 'B'
    factor = 1024
    while bytes > factor:
        bytes /= factor
    return f"{bytes:.2f}{suffix}"

def audit():
    print("="*50)
    print(f"🐸 HS-02 SYSTEM AUDIT | {datetime.now()}")
    print("="*50)

    # OS and Hardware
    print(f"[+] OS: {platform.system()} {platform.release()}")
    print(f"[+] CPU: {psutil.cpu_percent()}% | RAM: {psutil.virtual_memory().percent}%")
    print(f"[+] Disk Usage: {get_size(psutil.disk_usage('/').used)} / {get_size(psutil.disk_usage('/').total)}")

    # Network Connectivity Check (Looking for your IoT devices)
    print("\n[+] Checking IoT Heartbeats...")
    # Add your robot/car IPs here to track them
    devices = {"ESP32_Car": "192.168.1.10", "Surveillance_Robot": "192.168.1.11"}

    for name, ip in devices.items():
        try:
            socket.setdefaulttimeout(1)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((ip, 80))
            print(f"  ✅ {name} ({ip}): ONLINE")
        except:
            print(f"  ❌ {name} ({ip}): OFFLINE")

    print("="*50)

if __name__ == "__main__":
    audit()
