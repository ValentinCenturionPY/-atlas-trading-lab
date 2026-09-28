import os, json, threading, time
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, render_template_string

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

app = Flask(__name__)

SYMBOLS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]
SHADOW_EQUITY = float(os.getenv("ATLAS_SHADOW_EQUITY", "100"))
RISK_PCT = float(os.getenv("ATLAS_RISK_PCT", "0.01"))
MAX_DRAWDOWN = float(os.getenv("ATLAS_MAX_DRAWDOWN", "0.05"))
PAPER_ONLY = os.getenv("ATLAS_PAPER_ONLY", "true").lower() == "true"
SCAN_SECONDS = int(os.getenv("ATLAS_SCAN_SECONDS", "300"))

state = {
    "mode": "PAPER",
    "status": "BOOTING",
    "shadow_equity": SHADOW_EQUITY,
    "symbols": SYMBOLS,
    "last_scan": None,
    "signals": [],
    "error": None,
}

def clients():
    key = os.environ["APCA_API_KEY_ID"]
    secret = os.environ["APCA_API_SECRET_KEY"]
    # Hard fail closed: v0.1 can never instantiate a live TradingClient.
    trading = TradingClient(key, secret, paper=True)
    data = StockHistoricalDataClient(key, secret)
    return trading, data

def bullish_setup(df):
    """Simple ATLAS-001 proxy: rising swing structure + breakout + pullback hold."""
    if len(df) < 30:
        return False, "insufficient_bars"
    close = df["close"]
    high = df["high"]
    low = df["low"]
    # Trend filter: price above 20-bar mean and mean rising.
    ma20 = close.rolling(20).mean()
    trend = close.iloc[-1] > ma20.iloc[-1] > ma20.iloc[-5]
    # BOS: a recent close exceeded the prior 10-bar high.
    prior_high = high.iloc[-16:-6].max()
    bos = close.iloc[-6:-1].max() > prior_high
    # Pullback: latest low remains above recent structural floor and close recovers.
    structural_floor = low.iloc[-16:-6].min()
    pullback_hold = low.iloc[-5:].min() > structural_floor and close.iloc[-1] > close.iloc[-2]
    ok = bool(trend and bos and pullback_hold)
    return ok, f"trend={trend},bos={bos},pullback_hold={pullback_hold}"

def scan_once():
    trading, data = clients()
    clock = trading.get_clock()
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=10)
    req = StockBarsRequest(
        symbol_or_symbols=SYMBOLS,
        timeframe=TimeFrame.Hour,
        start=start,
        end=now - timedelta(minutes=16),
        feed=DataFeed.IEX,
    )
    bars = data.get_stock_bars(req).df
    signals = []
    for symbol in SYMBOLS:
        try:
            df = bars.xs(symbol)
            ok, reason = bullish_setup(df)
            signals.append({"symbol": symbol, "setup": ok, "reason": reason,
                            "last": float(df["close"].iloc[-1])})
        except Exception as e:
            signals.append({"symbol": symbol, "setup": False, "reason": str(e)})
    state.update(status="SCANNING" if clock.is_open else "MARKET_CLOSED",
                 last_scan=now.isoformat(), signals=signals, error=None)
    # v0.1 intentionally observes first. Executor activation comes after validation.
    return signals

def loop():
    while True:
        try:
            scan_once()
        except Exception as e:
            state.update(status="ERROR", error=str(e), last_scan=datetime.now(timezone.utc).isoformat())
        time.sleep(SCAN_SECONDS)

@app.get("/health")
def health():
    return jsonify({"ok": True, **state})

@app.get("/")
def dashboard():
    html = """
    <!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>ATLAS Trading Lab</title>
    <style>
    body{font-family:system-ui;background:#0b0f14;color:#e8eef5;margin:0;padding:24px}
    .card{background:#151b23;border:1px solid #263140;border-radius:16px;padding:18px;margin:12px 0}
    .pill{display:inline-block;padding:6px 10px;border-radius:999px;background:#233044}
    h1{margin-bottom:4px} small{color:#9fb0c3} table{width:100%;border-collapse:collapse}
    td,th{text-align:left;padding:9px;border-bottom:1px solid #263140}
    </style>
    <h1>ATLAS — Trading Lab</h1><small>v0.1 · autonomous research runner</small>
    <div class=card><span class=pill>{{s.mode}} MODE</span>
    <h2>{{s.status}}</h2><p>Shadow capital: ${{"%.2f"|format(s.shadow_equity)}}</p>
    <p>Last scan: {{s.last_scan or "waiting"}}</p></div>
    <div class=card><h3>Scout</h3><table><tr><th>Symbol</th><th>Setup</th><th>Last</th><th>Reason</th></tr>
    {% for x in s.signals %}<tr><td>{{x.symbol}}</td><td>{{"YES" if x.setup else "—"}}</td>
    <td>{{x.last or ""}}</td><td>{{x.reason}}</td></tr>{% endfor %}</table></div>
    {% if s.error %}<div class=card><b>Error:</b> {{s.error}}</div>{% endif %}
    """
    return render_template_string(html, s=state)

if __name__ == "__main__":
    if PAPER_ONLY:
        threading.Thread(target=loop, daemon=True).start()
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
