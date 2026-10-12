from django.core.management import call_command
from django.test import TestCase

from trading.models import MomentumScore, PriceData, Stock


class BackfillDataTests(TestCase):
    def test_backfill_command_creates_stock_history(self):
        call_command("backfill_data", "--tickers", "AAPL", "--days-back", "30", "--skip-api")

        self.assertTrue(Stock.objects.filter(ticker="AAPL").exists())
        self.assertTrue(PriceData.objects.filter(stock__ticker="AAPL").exists())
        self.assertTrue(MomentumScore.objects.filter(stock__ticker="AAPL").exists())


class MomentumRankingTests(TestCase):
    def test_momentum_ranking_page_renders(self):
        response = self.client.get("/market/momentum/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Momentum")
