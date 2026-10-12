from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from snaptrade_client.auth import SnapTradeAuth
from snaptrade_client.client import SnapTrade

from trading.models import TradingSignal
from trading.services.strategy_engine import get_strategy_engine

from .models import Portfolio, Position


def _extract_response_value(payload, *keys):
    if payload is None:
        return ""

    getter = getattr(payload, "get", None)
    if callable(getter):
        for key in keys:
            value = getter(key)
            if value not in (None, ""):
                return value

    for key in keys:
        value = getattr(payload, key, None)
        if value not in (None, ""):
            return value

    return ""


def _looks_like_invalid_snaptrade_credentials(exc):
    if exc is None:
        return False

    details = " ".join(
        str(part)
        for part in (
            exc,
            getattr(exc, "body", None),
            getattr(exc, "status", None),
            getattr(exc, "reason", None),
            getattr(exc, "detail", None),
        )
        if part not in (None, "")
    ).lower()

    invalid_user = "invalid user" in details or "invalid userid" in details or "invalid user id" in details
    invalid_secret = "invalid usersecret" in details or "invalid user secret" in details
    unauthorized = "401" in details and "unauthorized" in details
    return (invalid_user or invalid_secret or unauthorized) and (
        "user" in details or "secret" in details
    )


def _register_snaptrade_user(snaptrade, portfolio):
    generated_user_id = (
        f"portfolio-{portfolio.pk}-{timezone.now().strftime('%Y%m%d%H%M%S')}"
    )
    registration = snaptrade.authentication.register_snap_trade_user(user_id=generated_user_id)
    registration_body = getattr(registration, "body", registration)
    user_id = _extract_response_value(registration_body, "userId", "user_id") or generated_user_id
    user_secret = _extract_response_value(registration_body, "userSecret", "user_secret")

    if not user_secret:
        raise ValueError(
            "SnapTrade registration did not return a valid user secret for this portfolio."
        )

    return user_id, user_secret


def get_partner_snaptrade_client():
    client_id = (getattr(settings, "SNAPTRADE_CLIENT_ID", "") or "").strip()
    consumer_key = (getattr(settings, "SNAPTRADE_CLIENT_SECRET", "") or "").strip()

    if not client_id or not consumer_key:
        raise ValueError(
            "SnapTrade partner credentials are not configured. Set SNAPTRADE_CLIENT_ID and SNAPTRADE_CLIENT_SECRET."
        )

    return SnapTrade(
        auth=SnapTradeAuth.commercial_api_key(
            consumer_key=consumer_key,
            client_id=client_id,
        )
    )


def dashboard(request):
    portfolios = Portfolio.objects.filter(is_active=True).order_by("name")
    total_value = sum(float(portfolio.total_value or 0) for portfolio in portfolios)
    total_cash = sum(float(portfolio.current_cash or 0) for portfolio in portfolios)
    active_positions = (
        Position.objects.select_related("portfolio", "stock")
        .order_by("-current_value")[:6]
    )
    recent_signals = (
        TradingSignal.objects.select_related("stock")
        .order_by("-signal_date", "-created_at")[:5]
    )

    context = {
        "portfolios": portfolios,
        "total_value": total_value,
        "total_cash": total_cash,
        "active_positions": active_positions,
        "recent_signals": recent_signals,
    }
    return render(request, "dashboard.html", context)


def portfolio_list(request):
    portfolios = Portfolio.objects.filter(is_active=True).order_by("name")
    return render(request, "portfolio_list.html", {"portfolios": portfolios})


def portfolio_create(request):
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        description = (request.POST.get("description") or "").strip()
        initial_cash_value = (request.POST.get("initial_cash") or "").strip()
        snaptrade_user_id = (request.POST.get("snaptrade_user_id") or "").strip()
        snaptrade_account_id = (request.POST.get("snaptrade_account_id") or "").strip()
        snaptrade_user_secret = (request.POST.get("snaptrade_user_secret") or "").strip()
        brokerage = (request.POST.get("brokerage") or "alpaca").strip().lower()

        if not name:
            return render(
                request,
                "portfolio_form.html",
                {
                    "error": "Portfolio name is required.",
                    "name": name,
                    "description": description,
                    "brokerage": brokerage,
                    "snaptrade_user_id": snaptrade_user_id,
                    "snaptrade_account_id": snaptrade_account_id,
                    "snaptrade_user_secret": snaptrade_user_secret,
                },
            )

        initial_cash = Decimal("0.00")
        if initial_cash_value:
            try:
                initial_cash = Decimal(initial_cash_value)
            except InvalidOperation:
                return render(
                    request,
                    "portfolio_form.html",
                    {
                        "error": "Starting cash must be a valid number when provided.",
                        "name": name,
                        "description": description,
                        "brokerage": brokerage,
                        "snaptrade_user_id": snaptrade_user_id,
                        "snaptrade_account_id": snaptrade_account_id,
                        "snaptrade_user_secret": snaptrade_user_secret,
                    },
                )

        if brokerage in {"alpaca", "snaptrade"} and not snaptrade_user_id and not snaptrade_account_id and not snaptrade_user_secret:
            brokerage = "manual"

        portfolio = Portfolio.objects.create(
            name=name,
            description=description,
            initial_cash=initial_cash,
            current_cash=initial_cash,
            total_value=initial_cash,
            snaptrade_user_id=snaptrade_user_id,
            snaptrade_account_id=snaptrade_account_id,
            snaptrade_user_secret=snaptrade_user_secret,
        )
        return HttpResponseRedirect(
            reverse("portfolio:portfolio_detail", kwargs={"pk": portfolio.pk})
        )

    return render(request, "portfolio_form.html", {"portfolio": None, "brokerage": "alpaca"})


def generate_portfolio_signals(request, pk):
    portfolio = get_object_or_404(Portfolio, pk=pk)
    if request.method == "POST":
        strategy = get_strategy_engine(portfolio)
        buy_signals, sell_signals = strategy.generate_trading_signals(timezone.now())
        execute_requested = request.POST.get("execute_signals") == "1"

        if execute_requested:
            try:
                strategy.execute_trading_signals(buy_signals, sell_signals, None)
            except Exception as exc:
                return render(
                    request,
                    "signal_generation.html",
                    {
                        "portfolio": portfolio,
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
                "portfolio": portfolio,
                "buy_signals": buy_signals,
                "sell_signals": sell_signals,
                "generated_at": timezone.now(),
                "executed": execute_requested,
            },
        )

    return render(
        request,
        "signal_generation.html",
        {"portfolio": portfolio, "buy_signals": [], "sell_signals": []},
    )


def connect_alpaca(request, pk):
    portfolio = get_object_or_404(Portfolio, pk=pk)

    if request.method != "POST":
        return HttpResponseRedirect(
            reverse("portfolio:portfolio_detail", kwargs={"pk": portfolio.pk})
        )

    try:
        snaptrade = get_partner_snaptrade_client()

        user_id = (portfolio.snaptrade_user_id or "").strip()
        user_secret = (portfolio.snaptrade_user_secret or "").strip()

        for attempt in range(2):
            if not user_id or not user_secret:
                user_id, user_secret = _register_snaptrade_user(snaptrade, portfolio)

            try:
                portfolio.snaptrade_user_id = user_id
                portfolio.snaptrade_user_secret = user_secret
                portfolio.save(
                    update_fields=["snaptrade_user_id", "snaptrade_user_secret", "updated_at"]
                )

                login_response = snaptrade.authentication.login_snap_trade_user(
                    user_id=user_id,
                    user_secret=user_secret,
                    broker="ALPACA",
                    immediate_redirect=True,
                    connection_type="trade",
                )
                login_body = getattr(login_response, "body", login_response)
                redirect_url = _extract_response_value(
                    login_body,
                    "redirectURI",
                    "redirectUri",
                    "redirect_url",
                )

                if redirect_url:
                    return HttpResponseRedirect(redirect_url)

                return HttpResponseRedirect(
                    reverse("portfolio:portfolio_detail", kwargs={"pk": portfolio.pk})
                )
            except Exception as exc:
                if not _looks_like_invalid_snaptrade_credentials(exc) or attempt >= 1:
                    raise
                user_id, user_secret = _register_snaptrade_user(snaptrade, portfolio)

        raise ValueError("SnapTrade connection failed after retrying invalid credentials.")
    except Exception as exc:
        return render(
            request,
            "portfolio_detail.html",
            {
                "portfolio": portfolio,
                "positions": portfolio.positions.select_related("stock").order_by("-current_value"),
                "recent_trades": portfolio.trades.select_related("stock").order_by("-created_at")[:8],
                "performance": portfolio.performance_metrics.order_by("-date")[:7],
                "error": f"SnapTrade connection failed: {exc}",
            },
        )


def portfolio_detail(request, pk):
    portfolio = get_object_or_404(
        Portfolio.objects.prefetch_related(
            "positions__stock",
            "trades__stock",
            "performance_metrics",
        ),
        pk=pk,
    )

    positions = portfolio.positions.select_related("stock").order_by("-current_value")
    recent_trades = portfolio.trades.select_related("stock").order_by("-created_at")[:8]
    performance = portfolio.performance_metrics.order_by("-date")[:7]

    context = {
        "portfolio": portfolio,
        "positions": positions,
        "recent_trades": recent_trades,
        "performance": performance,
    }
    return render(request, "portfolio_detail.html", context)
