from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from trading.services.massive_client import MassiveAPIClient
from datetime import date


class Command(BaseCommand):
    help = "Fetch momentum data from the Massive API"

    def handle(self, *args, **options):
        if not settings.MASSIVE_API_KEY:
            raise CommandError(
                "MASSIVE_API_KEY is not configured. Add it to your environment or create a .env file from .env.example."
            )

        client = MassiveAPIClient()
        result = client.fetch_bulk_momentum_data(["AAPL", "NVDA"], date(2026, 5, 12))
        self.stdout.write(self.style.SUCCESS(f"Fetched data for {len(result)} tickers"))
        for ticker, data in result.items():
            self.stdout.write(f"{ticker}: {data}")
