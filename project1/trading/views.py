from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from portfolio.models import Portfolio

from .models import MomentumScore, RebalanceEvent, Stock, TradingSignal
from .services.strategy_engine import get_strategy_engine


def market_overview(request):
    stocks = Stock.objects.order_by("ticker")[:12]
    recent_signals = (
        TradingSignal.objects.select_related("stock")
        .order_by("-signal_date", "-created_at")[:10]
    )
    recent_rebalances = RebalanceEvent.objects.order_by("-date")[:5]
    latest_scores = (
        MomentumScore.objects.select_related("stock")
        .order_by("-calculation_date", "-momentum_score")[:8]
    )
    return render(
        request,
        "market_overview.html",
        {
            "stocks": stocks,
            "recent_signals": recent_signals,
            "recent_rebalances": recent_rebalances,
            "latest_scores": latest_scores,
        },
    )


def stock_list(request):
    stocks = Stock.objects.order_by("ticker")
    stock_rows = []
    for stock in stocks:
        latest_score = stock.momentum_scores.order_by("-calculation_date").first()
        stock_rows.append({"stock": stock, "latest_score": latest_score})
    return render(request, "stock_list.html", {"stock_rows": stock_rows})


def stock_detail(request, ticker):
    stock = get_object_or_404(Stock.objects.prefetch_related("price_data", "momentum_scores", "trading_signals"), ticker=ticker)
    price_history = stock.price_data.order_by("date")[:30]
    momentum_history = stock.momentum_scores.order_by("-calculation_date")[:10]
    recent_signals = stock.trading_signals.order_by("-signal_date", "-created_at")[:8]
    return render(
        request,
        "stock_detail.html",
        {
            "stock": stock,
            "price_history": price_history,
            "momentum_history": momentum_history,
            "recent_signals": recent_signals,
        },
    )


def signal_list(request):
    signals = (
        TradingSignal.objects.select_related("stock")
        .order_by("-signal_date", "-created_at")
    )
    return render(request, "signal_list.html", {"signals": signals})


def rebalance_history(request):
    rebalances = RebalanceEvent.objects.order_by("-date")
    return render(request, "rebalance_history.html", {"rebalances": rebalances})


def momentum_rankings(request):
    rankings = (
        MomentumScore.objects.select_related("stock")
        .order_by("-calculation_date", "-momentum_score")[:50]
    )
    message = None

    if request.method == "POST":
        try:
            from trading.services.momentum_calculator import MomentumCalculator

            calc = MomentumCalculator()
            universe = calc.update_stock_universe()
            calc.calculate_momentum_scores_bulk(universe, timezone.now().date())
            rankings = (
                MomentumScore.objects.select_related("stock")
                .filter(calculation_date=timezone.now().date())
                .order_by("-momentum_score")[:50]
            )
            message = "Top 50 momentum rankings refreshed with the latest price data."
        except Exception as exc:  # pragma: no cover - depends on live External API config
            message = f"Momentum refresh could not reach the Massive API: {exc}. Showing the latest local rankings instead."

    return render(
        request,
        "momentum_rankings.html",
        {
            "rankings": rankings,
            "message": message,
        },
    )


def generate_signals(request):
    portfolios = Portfolio.objects.filter(is_active=True).order_by("name")
    selected_portfolio = None

    if request.method == "POST":
        portfolio_id = request.POST.get("portfolio_id")
        if portfolio_id:
            selected_portfolio = get_object_or_404(Portfolio, pk=portfolio_id)
        else:
            selected_portfolio = portfolios.first()

        if selected_portfolio is None:
            return render(
                request,
                "signal_generation.html",
                {"portfolios": portfolios, "error": "Create a portfolio before generating signals."},
            )

        strategy = get_strategy_engine(selected_portfolio)
        buy_signals, sell_signals = strategy.generate_trading_signals(timezone.now().date())
        execute_requested = request.POST.get("execute_signals") == "1"

        if execute_requested:
            try:
                strategy.execute_trading_signals(buy_signals, sell_signals, None)
            except Exception as exc:
                return render(
                    request,
                    "signal_generation.html",
                    {
                        "portfolios": portfolios,
                        "portfolio": selected_portfolio,
                        "buy_signals": buy_signals,
                        "sell_signals": sell_signals,
                        "generated_at": timezone.now(),
                        "error": f"Signal execution failed: {exc}",
                    },
                )

        return render(
            request,
            "signal_generation.html",
            {
                "portfolios": portfolios,
                "portfolio": selected_portfolio,
                "buy_signals": buy_signals,
                "sell_signals": sell_signals,
                "generated_at": timezone.now(),
                "executed": execute_requested,
            },
        )

    return render(
        request,
        "signal_generation.html",
        {"portfolios": portfolios, "portfolio": portfolios.first() if portfolios else None},
    )


def strategy_dashboard(request):
    signal_summary = {
        "buy": TradingSignal.objects.filter(signal_type="BUY").count(),
        "sell": TradingSignal.objects.filter(signal_type="SELL").count(),
        "hold": TradingSignal.objects.filter(signal_type="HOLD").count(),
    }
    recent_rebalances = RebalanceEvent.objects.order_by("-date")[:5]
    latest_scores = (
        MomentumScore.objects.select_related("stock")
        .order_by("-calculation_date", "-momentum_score")[:10]
    )
    return render(
        request,
        "strategy_dashboard.html",
        {
            "signal_summary": signal_summary,
            "recent_rebalances": recent_rebalances,
            "latest_scores": latest_scores,
        },
    )
