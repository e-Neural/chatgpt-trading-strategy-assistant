# charts.py
import plotly.graph_objects as go
from datetime import datetime

def generate_smc_chart(candles: list, title="SMC Chart", highlights=None) -> str:
    """
    Generate a Plotly candlestick chart with optional SMC highlights.
    
    Args:
        candles (list): List of OHLC dicts with 'time', 'open', 'high', 'low', 'close'
        title (str): Chart title
        highlights (dict): Optional dict with CHOCH, OB, FVG, SL, TP

    Returns:
        str: Base64-encoded image of the chart
    """
    df = {
        "time": [datetime.fromisoformat(c["time"].replace("Z", "+00:00")) for c in candles],
        "open": [c["open"] for c in candles],
        "high": [c["high"] for c in candles],
        "low": [c["low"] for c in candles],
        "close": [c["close"] for c in candles],
    }

    fig = go.Figure(data=[go.Candlestick(
        x=df["time"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="Price"
    )])

    if highlights:
        if "order_block" in highlights:
            ob = highlights["order_block"]
            fig.add_shape(type="rect", x0=df["time"][0], x1=df["time"][-1],
                          y0=ob["low"], y1=ob["high"],
                          fillcolor="rgba(0,255,0,0.2)", line_width=0,
                          name="Order Block")

        if "fvg" in highlights:
            fvg = highlights["fvg"]
            fig.add_shape(type="rect", x0=df["time"][0], x1=df["time"][-1],
                          y0=fvg["low"], y1=fvg["high"],
                          fillcolor="rgba(255,165,0,0.3)", line_width=0,
                          name="FVG")

        if "choch" in highlights:
            choch_price = highlights["choch"]["price"]
            fig.add_hline(y=choch_price, line_dash="dot", line_color="red", name="CHOCH")

        if "entry" in highlights:
            fig.add_hline(y=highlights["entry"], line_color="blue", name="Entry")

        if "stop_loss" in highlights:
            fig.add_hline(y=highlights["stop_loss"], line_color="black", name="SL")

        if "take_profit" in highlights:
            fig.add_hline(y=highlights["take_profit"], line_color="green", name="TP")

    fig.update_layout(title=title, xaxis_rangeslider_visible=False)
    
    # Export as base64 image
    return fig.to_image(format="png")

