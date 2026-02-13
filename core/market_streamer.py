import json
import datetime
import upstox_client
from config.settings import ACCESS_TOKEN

from strategy.scanner import MarketScanner
from strategy.vwap_filter import VWAPCalculator
from strategy.strategy_engine import StrategyEngine

from execution.execution_engine import ExecutionEngine
from execution.order_executor import OrderExecutor
from execution.trade_monitor import TradeMonitor
from execution.risk_manager import RiskManager
from execution.trade_logger import TradeLogger


FEED_MODE = "full"

# =========================
# RISK LIMITS (CRITICAL)
# =========================
MAX_TRADES_PER_DAY = 5
MAX_CONCURRENT_TRADES = 3
MIN_EXECUTION_SCORE = 7.5

# ---------------- LOAD UNIVERSE ----------------
with open("data/nifty500_keys.json", "r") as f:
    INSTRUMENT_LIST = json.load(f)

# ---------------- CORE OBJECTS ----------------
scanner = MarketScanner(max_len=600)
vwap_calculators = {inst: VWAPCalculator() for inst in INSTRUMENT_LIST}

strategy_engine = StrategyEngine(scanner, vwap_calculators)

order_executor = OrderExecutor()
trade_monitor = TradeMonitor()
risk_manager = RiskManager()
trade_logger = TradeLogger()

execution_engine = ExecutionEngine(
    order_executor,
    trade_monitor,
    risk_manager,
    trade_logger
)

signals_today = {}
open_positions = set()


# =========================
# STREAMER
# =========================
def start_market_streamer():

    config = upstox_client.Configuration()
    config.access_token = ACCESS_TOKEN
    api_client = upstox_client.ApiClient(config)

    streamer = upstox_client.MarketDataStreamerV3(
        api_client,
        INSTRUMENT_LIST,
        FEED_MODE
    )

    def on_message(message):

        feeds = message.get("feeds", {})
        now = datetime.datetime.now()
        today = now.date().isoformat()

        # ---- SESSION FILTERS ----
        if now.hour == 9 and now.minute < 30:
            return

        if 12 <= now.hour <= 13:
            return

        if now.hour >= 15:
            return

        if today not in signals_today:
            signals_today[today] = set()

        # ---- DAILY LIMIT ----
        if len(signals_today[today]) >= MAX_TRADES_PER_DAY:
            return

        current_prices = {}
        candidate_signals = []

        for inst_key, feed_info in feeds.items():

            if len(open_positions) >= MAX_CONCURRENT_TRADES:
                break

            data = feed_info.get("fullFeed", {}).get("marketFF", {})

            try:
                ltp = float(data["ltpc"]["ltp"])
            except Exception:
                continue

            current_prices[inst_key] = ltp

            ohlc = data.get("marketOHLC", {}).get("ohlc", [])
            if not ohlc:
                continue

            bar = ohlc[-1]

            try:
                high = float(bar["high"])
                low = float(bar["low"])
                close = float(bar["close"])
                volume = float(bar["vol"])
            except Exception:
                continue

            scanner.update(inst_key, ltp, high, low, close, volume)

            decision = strategy_engine.evaluate(inst_key, ltp)

            if not decision:
                continue

            if decision.state.startswith("EXECUTE"):

                if inst_key in signals_today[today]:
                    continue

                if decision.score < MIN_EXECUTION_SCORE:
                    continue

                candidate_signals.append((inst_key, decision, ltp))

        # ---- PRIORITIZE BEST SIGNAL ----
        candidate_signals.sort(key=lambda x: x[1].score, reverse=True)

        for inst_key, decision, ltp in candidate_signals:

            if len(signals_today[today]) >= MAX_TRADES_PER_DAY:
                break

            if len(open_positions) >= MAX_CONCURRENT_TRADES:
                break

            execution_engine.handle_entry(inst_key, decision, ltp)

            signals_today[today].add(inst_key)
            open_positions.add(inst_key)

        # ---- EXIT MANAGEMENT ----
        execution_engine.handle_exits(current_prices, now)

    streamer.on("message", on_message)
    streamer.connect()

    print("🚀 Institutional Pullback System Started (Capital Protected)")
