import time
import traceback
import datetime

from core.market_streamer import start_market_streamer


def start_system():
    print("====================================")
    print("🚀 Starting Institutional Trading System")
    print("Time:", datetime.datetime.now())
    print("====================================")

    while True:
        try:
            start_market_streamer()

        except KeyboardInterrupt:
            print("\n🛑 Manual stop detected. Shutting down safely...")
            break

        except Exception as e:
            print("\n❌ Critical system error:")
            print(str(e))
            traceback.print_exc()

            print("🔁 Restarting system in 10 seconds...")
            time.sleep(10)

        # Safety pause before restart
        time.sleep(2)


if __name__ == "__main__":
    start_system()
