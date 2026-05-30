#!/usr/bin/env python3
import subprocess, os, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))

def run(cmd, delay=5):
    print(f"\n🌸 {cmd}")
    p = subprocess.Popen(cmd, shell=True, cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(delay)
    p.terminate()
    try: p.wait(2)
    except: p.kill()

if __name__ == "__main__":
    print("🌸 Limoni Suite: GO!")
    run(f"{sys.executable} maths/mathplot.py heart", 5)
    run(f"{sys.executable} maths/mathplot.py butterfly", 5)
    print("\n✨ Limoni execution complete ✨")
