import psutil
import platform
from datetime import datetime

def analyze_system():
    print(f"--- System Audit: {datetime.now()} ---")
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"CPU Usage: {psutil.cpu_percent()}%")
    print(f"RAM Usage: {psutil.virtual_memory().percent}%")
    print(f"Disk Usage: {psutil.disk_usage('/').percent}%")
    
    # Find the top 3 memory-consuming processes
    processes = sorted(psutil.process_iter(['name', 'memory_percent']), 
                       key=lambda x: x.info['memory_percent'], reverse=True)[:3]
    
    print("\nTop 3 RAM Consumers:")
    for p in processes:
        print(f"{p.info['name']}: {p.info['memory_percent']:.2f}%")

if __name__ == "__main__":
    analyze_system()
