# ATLAS — Trading Lab v0.1

Paper-only autonomous trading research service.

## Safety defaults
- Alpaca `paper=True` is hard-coded.
- Shadow equity: USD 100.
- Universe: SPY, QQQ, AAPL, MSFT, NVDA.
- 1-hour bars, IEX feed.
- v0.1 scans and journals signals but does **not** submit orders yet.
- Live trading is intentionally unavailable.

## Render
Build command:
`pip install -r requirements.txt`

Start command:
`gunicorn --workers 1 --threads 4 --timeout 120 app:app`

Environment variables:
- `APCA_API_KEY_ID`
- `APCA_API_SECRET_KEY`
- `ATLAS_PAPER_ONLY=true`
- `ATLAS_SHADOW_EQUITY=100`
- `ATLAS_RISK_PCT=0.01`
- `ATLAS_MAX_DRAWDOWN=0.05`
- `ATLAS_SCAN_SECONDS=300`

Health endpoint: `/health`
