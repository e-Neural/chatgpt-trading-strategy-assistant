# analysis.py

from typing import Optional, List, Dict, Tuple

def tag_sessions_local(candles):
    from datetime import datetime

    def label_session(utc_iso_time: str) -> str:
        dt = datetime.fromisoformat(utc_iso_time.replace("Z", "+00:00"))
        hour = dt.hour
        if 0 <= hour < 7:
            return "Asia"
        elif 7 <= hour < 12:
            return "London"
        elif 12 <= hour < 17:
            return "NewYork"
        elif 17 <= hour < 24:
            return "PostNY"
        return "Unknown"

    return [
        {**c, "session": label_session(c["time"])}
        for c in candles
    ]

def compute_session_levels(candles):
    from collections import defaultdict

    session_groups = defaultdict(list)
    for c in candles:
        session_groups[c["session"]].append(c)

    session_levels = {}
    for session, group in session_groups.items():
        highs = [c["high"] for c in group]
        lows = [c["low"] for c in group]
        session_levels[session] = {
            "high": max(highs) if highs else None,
            "low": min(lows) if lows else None
        }
    return session_levels


def detect_order_block(candles: list, lookback: int = 50):
    """
    Detect the most recent bullish or bearish order block based on engulfing structure.

    Args:
        candles: List of OHLC dictionaries
        lookback: How many candles back to analyze

    Returns:
        Dict with order block type and level or None
    """
    for i in reversed(range(1, min(lookback, len(candles) - 1))):
        prev = candles[i - 1]
        curr = candles[i]

        # Bullish order block: last down candle before strong up close
        if prev["close"] < prev["open"] and curr["close"] > curr["open"] and curr["close"] > prev["high"]:
            return {
                "type": "bullish",
                "low": prev["low"],
                "high": prev["high"],
                "time": prev["time"]
            }

        # Bearish order block: last up candle before strong down close
        if prev["close"] > prev["open"] and curr["close"] < curr["open"] and curr["close"] < prev["low"]:
            return {
                "type": "bearish",
                "low": prev["low"],
                "high": prev["high"],
                "time": prev["time"]
            }

    return None

def detect_fvg(candles: list, lookback: int = 50):
    """
    Detect the most recent Fair Value Gap (FVG) between candle wicks.

    Args:
        candles: List of OHLC dictionaries
        lookback: How many candles back to analyze

    Returns:
        Dict with FVG type and levels or None
    """
    for i in reversed(range(2, min(lookback, len(candles)))):
        c0 = candles[i - 2]
        c1 = candles[i - 1]
        c2 = candles[i]

        # Bullish FVG: Gap between c0 high and c2 low
        if c2["low"] > c0["high"]:
            return {
                "type": "up_fvg",
                "low": c0["high"],
                "high": c2["low"],
                "base_time": c1["time"]
            }

        # Bearish FVG: Gap between c0 low and c2 high
        if c2["high"] < c0["low"]:
            return {
                "type": "down_fvg",
                "low": c2["high"],
                "high": c0["low"],
                "base_time": c1["time"]
            }

    return None


def detect_sweep(candles: list, pdh: float, pdl: float, session_levels: dict = None):
    """
    Detect if recent candles swept above PDH or below PDL or session highs/lows.

    Args:
        candles: List of OHLC dictionaries (preferably session-tagged M15)
        pdh: Previous day high
        pdl: Previous day low
        session_levels: Dict of session highs/lows (e.g., NewYork, London)

    Returns:
        Dict with key 'sweeps' containing list of sweep descriptions
    """
    sweeps = []
    recent = candles[-5:] if len(candles) >= 5 else candles

    for c in recent:
        if c["high"] > pdh:
            sweeps.append("PDH sweep")
        if c["low"] < pdl:
            sweeps.append("PDL sweep")

        if session_levels:
            for session, levels in session_levels.items():
                if levels["high"] and c["high"] > levels["high"]:
                    sweeps.append(f"{session} High sweep")
                if levels["low"] and c["low"] < levels["low"]:
                    sweeps.append(f"{session} Low sweep")

    return {"sweeps": list(set(sweeps))}  # ✅ Now returns a dict


def detect_bullish_or_bearish_engulfing(candles: list) -> Optional[str]:
    """
    Detect bullish or bearish engulfing pattern on the last two candles.

    Args:
        candles: List of OHLC dictionaries.

    Returns:
        "Bullish Engulfing", "Bearish Engulfing", or None
    """
    if len(candles) < 2:
        return None

    prev = candles[-2]
    curr = candles[-1]

    # Bullish engulfing: prev red, curr green and engulfs body
    if prev["close"] < prev["open"] and curr["close"] > curr["open"]:
        if curr["open"] < prev["close"] and curr["close"] > prev["open"]:
            return "Bullish Engulfing"

    # Bearish engulfing: prev green, curr red and engulfs body
    if prev["close"] > prev["open"] and curr["close"] < curr["open"]:
        if curr["open"] > prev["close"] and curr["close"] < prev["open"]:
            return "Bearish Engulfing"

    return None


def detect_trend_bias(candles: list) -> str:
    # Example dummy logic
    if candles[-1]['close'] > candles[0]['close']:
        return "bullish"
    return "bearish"


def detect_ltf_entry(m15: list, m5: list, pdh: float, pdl: float, session_levels: dict) -> dict:
    if m5[-1]['close'] > m5[-1]['open']:
        return {
            "entry_type": "bullish",
            "entry_price": m5[-1]["close"],
            "stop_loss": m5[-1]["low"],
            "take_profit": m5[-1]["close"] + (m5[-1]["close"] - m5[-1]["low"]) * 2,
            "notes": "Bullish close detected on M5"
        }
    return {
        "entry_type": "none",
        "entry_price": None,
        "stop_loss": None,
        "take_profit": None,
        "notes": "No valid LTF entry"
    }



def detect_choch(candles: list):
    if len(candles) < 2:
        return None
    prev = candles[-2]
    curr = candles[-1]
    if curr["high"] > prev["high"] and curr["low"] < prev["low"]:
        return "choch_detected"
    return None


