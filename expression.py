import time
from pythonosc import udp_client

# VSeeFace default VMC/OSC port
IP = "127.0.0.1"
PORT = 39539

# Connect the client (lazy initialization to avoid blocking import)
_client = None

def get_client():
    global _client
    if _client is None:
        _client = udp_client.SimpleUDPClient(IP, PORT)
    return _client

# The 5 expressions your model supports
expressions = ["fun", "joy", "neutral", "sorrow", "angry"]

def trigger_expression(name):
    print(f"Triggering: {name}")
    client = get_client()
    
    # 1. First, reset all expressions to 0 (so they don't mix)
    for exp in expressions:
        client.send_message("/vmn/blend/val", [exp, 0.0])
    
    # 2. Set the target expression to 1.0 (100% intensity)
    client.send_message("/vmn/blend/val", [name, 1.0])

if __name__ == "__main__":
    try:
        print(f"Starting expression loop. Sending to {IP}:{PORT}...")
        while True:
            for exp in expressions:
                trigger_expression(exp)
                time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopped by user. Resetting to neutral...")
        trigger_expression("neutral")
