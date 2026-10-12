from django.urls import path

from . import views

app_name = "trading"

urlpatterns = [
    path("", views.market_overview, name="market_overview"),
    path("stocks/", views.stock_list, name="stock_list"),
    path("stocks/<str:ticker>/", views.stock_detail, name="stock_detail"),
    path("signals/", views.signal_list, name="signal_list"),
    path("signals/generate/", views.generate_signals, name="generate_signals"),
    path("momentum/", views.momentum_rankings, name="momentum_rankings"),
    path("rebalances/", views.rebalance_history, name="rebalance_history"),
    path("strategy/", views.strategy_dashboard, name="strategy_dashboard"),
]
