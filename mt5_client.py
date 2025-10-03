# mt5_client.py
# ---------------------------------------------------------------------------

import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta
import threading
import os
from dotenv import load_dotenv
import numpy as np

# ── MT5 credentials & client ───────────────────────────────────────────────
load_dotenv()

MT5_LOGIN = int(os.getenv("MT5_LOGIN"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD")
MT5_SERVER = os.getenv("MT5_SERVER")
MT5_PATH = os.getenv("MT5_PATH", None)

if not mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
    raise RuntimeError(f"MT5 initialize() failed, error code: {mt5.last_error()}")

# ── symbol maps ────────────────────────────────────────────────────────────
symbol_map = {}        # {name: name}
symbol_name_to_id = {} # {name.upper(): name}
symbol_digits_map = {} # {name: digits}

def load_symbols():
    global symbol_map, symbol_name_to_id, symbol_digits_map
    symbol_map.clear(); symbol_name_to_id.clear(); symbol_digits_map.clear()
    symbols = mt5.symbols_get()
    for s in symbols:
        symbol_map[s.name] = s.name
        symbol_name_to_id[s.name.upper()] = s.name
        symbol_digits_map[s.name] = s.digits

load_symbols()

def pips_to_relative(pips: int, digits: int) -> float:
    """Convert pips → price units (works for 2- to 5-digit symbols)."""
    return pips * 10 ** -digits

def on_error(failure):
    print("[ERROR]", failure)

# ── OHLC fetch (used by /fetch-data) ───────────────────────────────────────
def get_ohlc_data(symbol: str, tf: str = "D1", n: int = 10):
    timeframe_map = {
        "D1": mt5.TIMEFRAME_D1,
        "H4": mt5.TIMEFRAME_H4,
        "H1": mt5.TIMEFRAME_H1,
        "M30": mt5.TIMEFRAME_M30,
        "M15": mt5.TIMEFRAME_M15,
        "M5": mt5.TIMEFRAME_M5,
        "M1": mt5.TIMEFRAME_M1,
    }
    timeframe = timeframe_map.get(tf.upper(), mt5.TIMEFRAME_D1)
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, max(n + 10, 50))
    if rates is None or len(rates) == 0:
        raise ValueError(f"No OHLC data for {symbol} {tf}")

    candles = []
    for r in rates[-50:]:
        ts = datetime.utcfromtimestamp(r['time']).replace(tzinfo=timezone.utc)
        candles.append({
            "time": ts.isoformat(),
            "open": float(r['open']),
            "high": float(r['high']),
            "low": float(r['low']),
            "close": float(r['close']),
            "volume": int(r['tick_volume']),
        })

    candles = candles[-n:]
    highs = [bar["high"] for bar in candles]
    lows = [bar["low"] for bar in candles]
    closes = [bar["close"] for bar in candles]

    context_levels = {}
    if len(candles) >= 2:
        context_levels = {
            "today_high": candles[-1]["high"],
            "today_low": candles[-1]["low"],
            "prev_day_high": candles[-2]["high"],
            "prev_day_low": candles[-2]["low"],
            "range_high_5": max(highs[-5:]),
            "range_low_5": min(lows[-5:])
        }

    trend_strength = {}
    if tf in ("D1", "H4") and len(closes) >= 5:
        x = np.arange(len(closes))
        slope, intercept = np.polyfit(x, closes, 1)
        r = np.corrcoef(x, closes)[0, 1]
        trend_strength = {
            "slope": float(slope),
            "correlation": float(r),
            "confidence": (
                "Ultra Strong Bullish" if slope > 0.5 and r > 0.9 else
                "Strong Bearish" if slope < -0.5 and r > 0.9 else
                "Sideways/Neutral"
            )
        }

    return {
        "candles": candles,
        "context": context_levels,
        "trend": trend_strength
    }

# ── reconcile helpers ──────────────────────────────────────────────────────
def get_open_positions():
    positions = mt5.positions_get()
    open_positions = []
    if positions is not None:
        for p in positions:
            open_positions.append(
                dict(
                    symbol_name=p.symbol,
                    position_id=p.ticket,
                    direction="buy" if p.type == mt5.ORDER_TYPE_BUY else "sell",
                    entry_price=p.price_open,
                    volume_lots=p.volume,
                )
            )
    return open_positions

def is_forex_symbol(symbol: str) -> bool:
    return symbol.upper() in {
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCHF", "USDCAD",
        "EURJPY", "EURGBP", "GBPJPY"
    }

# ── core: place_order ──────────────────────────────────────────────────────
def place_order(
    *, symbol, order_type, side, volume,
    price=None, stop_loss=None, take_profit=None,
    client_msg_id=None,
):
    symbol_id = symbol_name_to_id.get(symbol.upper())
    if symbol_id is None:
        raise ValueError(f"Unknown symbol '{symbol}'")
    digits = symbol_digits_map.get(symbol_id, 5)
    lot_size = float(volume)

    order_type_map = {
        "MARKET": mt5.ORDER_TYPE_BUY if side.upper() == "BUY" else mt5.ORDER_TYPE_SELL,
        "LIMIT": mt5.ORDER_TYPE_BUY_LIMIT if side.upper() == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT,
        "STOP": mt5.ORDER_TYPE_BUY_STOP if side.upper() == "BUY" else mt5.ORDER_TYPE_SELL_STOP,
    }
    mt5_order_type = order_type_map[order_type.upper()]

    request = {
        "action": mt5.TRADE_ACTION_DEAL if order_type.upper() == "MARKET" else mt5.TRADE_ACTION_PENDING,
        "symbol": symbol_id,
        "volume": lot_size,
        "type": mt5_order_type,
        "deviation": 10,
        "magic": 0,
        "comment": client_msg_id or "",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    if order_type.upper() == "LIMIT":
        if price is None:
            raise ValueError("Limit order requires price.")
        request["price"] = float(price)
    elif order_type.upper() == "STOP":
        if price is None:
            raise ValueError("Stop order requires price.")
        request["price"] = float(price)

    if stop_loss is not None:
        request["sl"] = float(stop_loss)
    if take_profit is not None:
        request["tp"] = float(take_profit)

    print(
        f"[DEBUG] Sending order: {order_type=} {side=} "
        f"price={price} SL={stop_loss} TP={take_profit}"
    )
    result = mt5.order_send(request)
    # print("[MT5 ORDER RESULT]", result)
    return result

# ── amend helpers ──────────────────────────────────────────────────────────
def modify_position_sltp(position_id, stop_loss=None, take_profit=None):
    pos = mt5.positions_get(ticket=position_id)
    if not pos:
        return {"status": "position_not_found"}
    pos = pos[0]
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": position_id,
        "symbol": pos.symbol,
        "sl": stop_loss if stop_loss is not None else pos.sl,
        "tp": take_profit if take_profit is not None else pos.tp,
        "magic": 0,
        "comment": "modify sltp",
    }
    result = mt5.order_send(request)
    return result

def modify_pending_order_sltp(order_id, stop_loss=None, take_profit=None):
    order = mt5.orders_get(ticket=order_id)
    if not order:
        return {"status": "order_not_found"}
    order = order[0]
    request = {
        "action": mt5.TRADE_ACTION_MODIFY,
        "order": order_id,
        "symbol": order.symbol,
        "price": order.price_open,
        "sl": stop_loss if stop_loss is not None else order.sl,
        "tp": take_profit if take_profit is not None else order.tp,
        "magic": 0,
        "comment": "modify pending sltp",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    return result

# ── blocking helper used by FastAPI layer ─────────────────────────────────
def wait_for_deferred(result, timeout=10):
    # For MT5, actions are synchronous, so just return the result
    return result

def get_pending_orders():
    orders = mt5.orders_get()
    pending_orders = []
    if orders is not None:
        for o in orders:
            order_type = (
                "LIMIT" if o.type in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT)
                else "STOP"
            )
            direction = "buy" if o.type in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP) else "sell"
            entry_price = o.price_open
            symbol_id = o.symbol
            timestamp = datetime.utcfromtimestamp(o.time_setup).isoformat()
            pending_orders.append({
                "order_id": o.ticket,
                "symbol_id": symbol_id,
                "symbol_name": symbol_id,
                "direction": direction,
                "order_type": order_type,
                "entry_price": entry_price,
                "stop_loss": o.sl,
                "take_profit": o.tp,
                "volume": o.volume_initial,
                "creation_time": timestamp
            })
    return {"orders": pending_orders}