from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, List

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from trading.models import MomentumScore, PriceData, Stock
from trading.services.momentum_calculator import MomentumCalculator

DEFAULT_TICKERS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "TSLA",
    "AMD",
    "INTC",
    "SPY",
]


class Command(BaseCommand):
    help = "Backfill stock price history and momentum scores into the local database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tickers",
            nargs="+",
            default=None,
            help="Ticker symbols to populate. Defaults to a sample market basket.",
        )
        parser.add_argument(
            "--days-back",
            type=int,
            default=365,
            help="How many days of price history to backfill for each stock.",
        )
        parser.add_argument(
            "--skip-api",
            action="store_true",
            help="Use locally generated demo data instead of the Massive API.",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="Delete existing price and momentum records before backfilling.",
        )

    def handle(self, *args, **options):
        tickers = [ticker.upper() for ticker in (options["tickers"] or DEFAULT_TICKERS)]
        days_back = max(30, int(options["days_back"]))
        skip_api = bool(options["skip_api"]) or not getattr(settings, "MASSIVE_API_KEY", None)

        if options["clear_existing"]:
            for ticker in tickers:
                stock = Stock.objects.filter(ticker=ticker).first()
                if stock:
                    stock.price_data.all().delete()
                    stock.momentum_scores.all().delete()

        calculator = MomentumCalculator()
        populated = []

        for ticker in tickers:
            stock, created = Stock.objects.get_or_create(
                ticker=ticker,
                defaults={
                    "name": ticker,
                    "sector": "Technology",
                    "is_active": True,
                },
            )
            if skip_api:
                records_created = self._seed_demo_price_data(stock, days_back)
            else:
                try:
                    records_created = calculator.backfill_price_data(stock, days_back=days_back)
                except Exception as exc:  # pragma: no cover - defensive fallback for API issues
                    self.stdout.write(
                        self.style.WARNING(
                            f"API backfill failed for {ticker}: {exc}. Falling back to demo data."
                        )
                    )
                    records_created = self._seed_demo_price_data(stock, days_back)

            self._save_momentum_score(stock, calculator)
            populated.append((ticker, records_created, created))

        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete for {len(populated)} tickers."
            )
        )

        for ticker, records_created, created in populated:
            self.stdout.write(
                f"- {ticker}: {records_created} price records, "
                f"{'created' if created else 'updated'} stock"
            )

    def _seed_demo_price_data(self, stock: Stock, days_back: int) -> int:
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days_back)
        created = 0

        ticker_seed = sum(ord(ch) for ch in stock.ticker)
        previous_close = Decimal("100") + Decimal(ticker_seed % 80)

        for offset in range(days_back + 1):
            day = start_date + timedelta(days=offset)
            if day.weekday() >= 5:
                continue

            wave = math.sin((offset + (ticker_seed % 13)) / 6.0)
            drift = (offset / max(days_back, 1)) * 0.35
            price = float(previous_close) * (1 + (wave / 135.0) + drift + (offset / 5000.0)) + 1.75
            price = max(float(previous_close) * 0.5, price)

            open_price = previous_close
            close_value = Decimal(str(price))
            high_value = Decimal(str(price * (1 + abs(wave) / 18 + 0.02)))
            low_value = Decimal(str(price * (1 - abs(wave) / 20 - 0.01)))
            volume = 750000 + ((ticker_seed + offset) % 500000)

            PriceData.objects.update_or_create(
                stock=stock,
                date=day,
                defaults={
                    "open_price": Decimal(str(open_price)),
                    "high": high_value,
                    "low": low_value,
                    "close": close_value,
                    "volume": volume,
                    "adjusted_close": close_value,
                },
            )
            previous_close = close_value
            created += 1

        return created

    def _save_momentum_score(self, stock: Stock, calculator: MomentumCalculator):
        calculation_date = timezone.now().date()
        price_data = stock.price_data.filter(date__lte=calculation_date).order_by("date")
        if not price_data.exists():
            return

        twelve_months_ago = calculation_date - timedelta(days=365)
        one_month_ago = calculation_date - timedelta(days=30)

        price_12m = self._find_closest_close(price_data, twelve_months_ago)
        price_1m = self._find_closest_close(price_data, one_month_ago)

        if price_12m and price_1m and price_12m > 0:
            momentum = (price_1m - price_12m) / price_12m
            score, _ = MomentumScore.objects.update_or_create(
                stock=stock,
                calculation_date=calculation_date,
                defaults={
                    "momentum_score": Decimal(str(momentum)),
                    "rank": None,
                    "quintile": None,
                    "is_top_quintile": False,
                    "period_start": twelve_months_ago,
                    "period_end": one_month_ago,
                },
            )
            score.rank = None
            score.quintile = None
            score.is_top_quintile = False
            score.save(update_fields=["momentum_score", "period_start", "period_end", "is_top_quintile"])

        MomentumScore.calculate_quintiles_for_date(calculation_date)

    def _find_closest_close(self, price_data, target_date):
        records = list(price_data)
        if not records:
            return None

        closest = min(
            records,
            key=lambda row: abs((row.date - target_date).days),
        )
        return Decimal(str(closest.close))
