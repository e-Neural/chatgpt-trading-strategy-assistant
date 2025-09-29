# test_mt5.py
from mt5_client import get_open_positions, get_ohlc_data, place_order, get_pending_orders

print("✅ Testando conexão e símbolos...")
print("Símbolos carregados:", len(get_open_positions()))

print("✅ Testando OHLC...")
ohlc = get_ohlc_data("EURUSD", "M5", 5)
print("OHLC:", ohlc)

print("✅ Testando ordens pendentes...")
print(get_pending_orders())