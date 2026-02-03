from strategy.market_regime import detect_market_regime
from strategy.htf_bias import get_htf_bias
from strategy.breakout_detector import breakout_signal
from strategy.decision_engine import final_trade_decision

from strategy.vwap_filter import VWAPCalculator
from strategy.mtf_builder import MTFBuilder
from strategy.mtf_context import analyze_mtf


class StrategyEngine:
    """
    AUTHORITATIVE Strategy Engine (FINAL – PRECISION MODE)

    Improvements:
    - Evaluate ONLY on new bar close
    - Prevent duplicate breakout processing
    """

    def __init__(self, scanner, vwap_calculators):
        self.scanner = scanner
        self.vwap_calculators = vwap_calculators
        self.mtf_builder = MTFBuilder()

        # 🔒 memory to avoid duplicate alerts
        self._last_processed_bar = {}
        self._breakout_lock = {}

    def evaluate(self, inst_key: str, ltp: float):
        # ==================================================
        # 1️⃣ DATA SUFFICIENCY
        # ==================================================

        if not self.scanner.has_enough_data(inst_key, min_bars=30):
            return None

        last_bar = self.scanner.get_last_n_bars(inst_key, 1)
        if not last_bar:
            return None

        bar = last_bar[0]
        bar_time = bar["time"]

        # 🔒 BAR-CLOSE GUARD (CRITICAL)
        if self._last_processed_bar.get(inst_key) == bar_time:
            return None

        self._last_processed_bar[inst_key] = bar_time

        prices = self.scanner.get_prices(inst_key)
        highs = self.scanner.get_highs(inst_key)
        lows = self.scanner.get_lows(inst_key)
        closes = self.scanner.get_closes(inst_key)
        volumes = self.scanner.get_volumes(inst_key)

        if not (prices and highs and lows and closes and volumes):
            return None

        # ==================================================
        # 2️⃣ BUILD MTF CANDLES
        # ==================================================

        self.mtf_builder.update(
            inst_key,
            bar["time"],
            bar["open"],
            bar["high"],
            bar["low"],
            bar["close"],
            bar["volume"]
        )

        candle_5m = self.mtf_builder.get_latest_5m(inst_key)
        hist_5m = self.mtf_builder.get_tf_history(inst_key, minutes=5, lookback=3)
        candle_15m = self.mtf_builder.get_latest_15m(inst_key)
        hist_15m = self.mtf_builder.get_tf_history(inst_key, minutes=15, lookback=3)

        mtf_ctx = analyze_mtf(
            candle_5m,
            candle_15m,
            history_5m=hist_5m,
            history_15m=hist_15m
        )

        if mtf_ctx.direction == "NEUTRAL" or mtf_ctx.conflict:
            return None

        # ==================================================
        # 3️⃣ MARKET REGIME
        # ==================================================

        regime = detect_market_regime(highs=highs, lows=lows, closes=closes)
        if regime.state in ("WEAK", "COMPRESSION"):
            return None

        # ==================================================
        # 4️⃣ VWAP
        # ==================================================

        if inst_key not in self.vwap_calculators:
            self.vwap_calculators[inst_key] = VWAPCalculator()

        vwap_calc = self.vwap_calculators[inst_key]
        vwap_calc.update(ltp, volumes[-1])
        vwap_ctx = vwap_calc.get_context(ltp)

        # ==================================================
        # 5️⃣ HTF BIAS
        # ==================================================

        htf_bias = get_htf_bias(prices=prices, vwap_value=vwap_ctx.vwap)

        if mtf_ctx.direction == "BULLISH" and htf_bias.direction == "BEARISH":
            return None
        if mtf_ctx.direction == "BEARISH" and htf_bias.direction == "BULLISH":
            return None

        # ==================================================
        # 6️⃣ BREAKOUT (STRICT + LOCKED)
        # ==================================================

        breakout = breakout_signal(
            inst_key=inst_key,
            prices=prices,
            volume_history=volumes,
            high_prices=highs,
            low_prices=lows,
            close_prices=closes
        )

        if not breakout:
            return None

        # 🔒 prevent repeated breakout alerts
        lock_key = (inst_key, breakout["direction"], breakout["range_high"], breakout["range_low"])
        if self._breakout_lock.get(inst_key) == lock_key:
            return None
        self._breakout_lock[inst_key] = lock_key

        if breakout["direction"] == "LONG" and mtf_ctx.direction != "BULLISH":
            return None
        if breakout["direction"] == "SHORT" and mtf_ctx.direction != "BEARISH":
            return None

        # ==================================================
        # 7️⃣ FINAL DECISION
        # ==================================================

        decision = final_trade_decision(
            inst_key=inst_key,
            prices=prices,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
            market_regime=regime.state,
            htf_bias_label=htf_bias.label,
            vwap_ctx=vwap_ctx,
            breakout_signal=breakout
        )

        decision.components["mtf_direction"] = mtf_ctx.direction
        decision.components["mtf_strength"] = mtf_ctx.strength
        decision.components["regime"] = regime.state
        decision.components["htf_bias"] = htf_bias.label

        return decision
