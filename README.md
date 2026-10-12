# Momentum Trader

A small Django app for ranking stocks by momentum, generating buy/sell signals, and connecting to a paper brokerage through SnapTrade.

This project is meant to be run locally and is built around a simple workflow:

- pull market data from Massive
- score a stock universe by momentum
- generate signals from the top and bottom performers
- connect a portfolio to Alpaca Paper through SnapTrade
- submit paper-trading orders from the app

## Stack

- Django
- SQLite for local development
- Massive for market data
- SnapTrade for brokerage connectivity
- Alpaca Paper for simulated orders

## Local setup

From the repo root:

```bash
python manage.py migrate
python manage.py runserver
```

If the app is not starting from the workspace root, use the repo-level launcher:

```bash
python manage.py runserver
```

The project is nested under the `project1/` folder, so the root `manage.py` wrapper handles the Django entrypoint for you.

## Environment variables

Create a local `.env` file in `project1/.env` with:

```env
MASSIVE_API_KEY=your_massive_key
SNAPTRADE_CLIENT_ID=your_snaptrade_client_id
SNAPTRADE_CLIENT_SECRET=your_snaptrade_client_secret
```

Do not commit secrets to git. The app reads them through Django settings.

## Typical workflow

1. Start the app.
2. Create a portfolio.
3. Connect it to Alpaca Paper via SnapTrade.
4. Generate momentum rankings.
5. Generate signals for the portfolio.
6. Use the “Generate + buy signals” action to send paper orders for the selected buy signals.

## Notes

- This is a paper-trading workflow only.
- The app is intentionally simple and educational rather than production-grade.
- Live flow depends on valid SnapTrade and Alpaca credentials.

## Useful commands

```bash
python manage.py check
python manage.py test
python manage.py createsuperuser
```

## Project layout

- `project1/trading/` — market data, momentum logic, strategy engine
- `project1/portfolio/` — portfolios, positions, trades, SnapTrade integration
- `project1/templates/` — Django HTML pages
- `project1/static/` — frontend assets
