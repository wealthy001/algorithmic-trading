from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from portfolio.models import Portfolio
from trading.models import MomentumScore, RebalanceEvent, Stock, TradingSignal


class PortfolioCreationTests(TestCase):
    def test_portfolio_creation_endpoint(self):
        response = self.client.post(
            "/portfolios/new/",
            {
                "name": "Growth Fund",
                "description": "Momentum-based portfolio",
                "initial_cash": "15000.00",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Portfolio.objects.filter(name="Growth Fund").exists())

    def test_portfolio_creation_stores_snaptrade_connection_details(self):
        response = self.client.post(
            "/portfolios/new/",
            {
                "name": "Alpaca Linked Fund",
                "description": "Connected to Alpaca",
                "initial_cash": "20000.00",
                "snaptrade_user_id": "user_123",
                "snaptrade_account_id": "acct_456",
                "snaptrade_user_secret": "secret_789",
                "brokerage": "alpaca",
            },
        )

        self.assertEqual(response.status_code, 302)
        portfolio = Portfolio.objects.get(name="Alpaca Linked Fund")
        self.assertEqual(portfolio.snaptrade_user_id, "user_123")
        self.assertEqual(portfolio.snaptrade_account_id, "acct_456")
        self.assertEqual(portfolio.snaptrade_user_secret, "secret_789")

    def test_portfolio_creation_allows_blank_starting_cash_for_paper_trading(self):
        response = self.client.post(
            "/portfolios/new/",
            {
                "name": "Paper Trading Fund",
                "description": "Real Alpaca paper account",
                "initial_cash": "",
                "brokerage": "alpaca",
            },
        )

        self.assertEqual(response.status_code, 302)
        portfolio = Portfolio.objects.get(name="Paper Trading Fund")
        self.assertEqual(portfolio.initial_cash, Decimal("0.00"))

    @patch("portfolio.views.get_partner_snaptrade_client")
    def test_alpaca_connection_registers_snaptrade_user(self, mock_client_factory):
        portfolio = Portfolio.objects.create(
            name="Connect Fund",
            initial_cash=Decimal("10000.00"),
            current_cash=Decimal("10000.00"),
            total_value=Decimal("10000.00"),
        )
        mock_client = mock_client_factory.return_value
        mock_client.authentication.register_snap_trade_user.return_value = type(
            "Resp",
            (),
            {"body": {"userId": "snaptrade-user-123", "userSecret": "secret-abc"}},
        )()
        mock_client.authentication.login_snap_trade_user.return_value = type(
            "Resp",
            (),
            {"body": {"redirectURI": "https://portal.example.com/connect"}},
        )()

        response = self.client.post(f"/portfolios/{portfolio.pk}/connect-alpaca/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://portal.example.com/connect")
        portfolio.refresh_from_db()
        self.assertEqual(portfolio.snaptrade_user_id, "snaptrade-user-123")
        self.assertEqual(portfolio.snaptrade_user_secret, "secret-abc")

    @patch("portfolio.views.get_partner_snaptrade_client")
    def test_alpaca_connection_recovers_from_invalid_existing_snaptrade_credentials(
        self, mock_client_factory
    ):
        portfolio = Portfolio.objects.create(
            name="Recovery Fund",
            initial_cash=Decimal("10000.00"),
            current_cash=Decimal("10000.00"),
            total_value=Decimal("10000.00"),
            snaptrade_user_id="stale-user",
            snaptrade_user_secret="stale-secret",
        )
        mock_client = mock_client_factory.return_value
        mock_client.authentication.login_snap_trade_user.side_effect = [
            Exception(
                "401 Unauthorized: Invalid userID or userSecret provided"
            ),
            type("Resp", (), {"body": {"redirectURI": "https://portal.example.com/connect"}})(),
        ]
        mock_client.authentication.register_snap_trade_user.return_value = type(
            "Resp",
            (),
            {"body": {"userId": "fresh-user-456", "userSecret": "fresh-secret-789"}},
        )()

        response = self.client.post(f"/portfolios/{portfolio.pk}/connect-alpaca/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://portal.example.com/connect")
        portfolio.refresh_from_db()
        self.assertEqual(portfolio.snaptrade_user_id, "fresh-user-456")
        self.assertEqual(portfolio.snaptrade_user_secret, "fresh-secret-789")


class SignalGenerationTests(TestCase):
    def test_signal_generation_endpoint(self):
        portfolio = Portfolio.objects.create(
            name="Signal Fund",
            initial_cash=Decimal("25000.00"),
            current_cash=Decimal("25000.00"),
            total_value=Decimal("25000.00"),
        )
        stock = Stock.objects.create(ticker="NVDA", name="NVIDIA", is_active=True)
        MomentumScore.objects.create(
            stock=stock,
            calculation_date=timezone.now().date(),
            momentum_score=Decimal("0.28"),
            rank=1,
            quintile=1,
            is_top_quintile=True,
            period_start=timezone.now().date(),
            period_end=timezone.now().date(),
        )

        response = self.client.post("/market/signals/generate/", {"portfolio_id": portfolio.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BUY")

    def test_buy_signals_execute_with_portfolio_user_secret(self):
        portfolio = Portfolio.objects.create(
            name="Execution Fund",
            initial_cash=Decimal("10000.00"),
            current_cash=Decimal("10000.00"),
            total_value=Decimal("10000.00"),
            snaptrade_user_id="user_123",
            snaptrade_account_id="acct_456",
            snaptrade_user_secret="secret_789",
        )
        stock = Stock.objects.create(ticker="AMD", name="Advanced Micro Devices", is_active=True)
        momentum = MomentumScore.objects.create(
            stock=stock,
            calculation_date=timezone.now().date(),
            momentum_score=Decimal("0.25"),
            rank=1,
            quintile=1,
            is_top_quintile=True,
            period_start=timezone.now().date(),
            period_end=timezone.now().date(),
        )
        signal = TradingSignal.objects.create(
            stock=stock,
            signal_date=timezone.now().date(),
            signal_type="BUY",
            momentum_score=momentum,
            target_value=Decimal("5000.00"),
            reason="Top momentum stock",
        )

        strategy = __import__("trading.services.strategy_engine", fromlist=["get_strategy_engine"]).get_strategy_engine(portfolio)
        strategy.trading_executor = MagicMock()
        strategy.trading_executor.get_available_cash_for_trading.return_value = Decimal("10000.00")
        strategy.trading_executor.execute_buy_orders.return_value = []

        rebalance_event = RebalanceEvent.objects.create(
            date=timezone.now().date(),
            total_stocks_analyzed=1,
            buy_signals_generated=1,
            sell_signals_generated=0,
            execution_status="IN_PROGRESS",
        )

        strategy.execute_trading_signals([signal], [], rebalance_event)

        strategy.trading_executor.execute_buy_orders.assert_called_once_with(
            portfolio,
            [stock],
            Decimal("10000.00"),
            user_secret="secret_789",
        )
