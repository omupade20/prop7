# main.py

from core.market_streamer import start_market_streamer

def start_system():
    print("Starting Trading System ...")
    start_market_streamer()

    # Keep the script running so WebSocket stays alive
    import time
    while True:
        time.sleep(1)

if __name__ == "__main__":
    start_system()
