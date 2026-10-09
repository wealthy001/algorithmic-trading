from django.contrib import admin
from portfolio.models import Portfolio, Position, Trade, PerformanceMetric

@admin.register(Portfolio)
class PortfolioAdmin(admin.ModelAdmin):
    list_display = ("name", "initial_cash", "current_cash", "total_value", "is_active", "created_at")
    list_filter = ("is_active","created_at")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "Updated_at")

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("portfolio", "stock", "quantity", "average_cost", "current_price", "current_value", "unrealised_pnl", "unrealised_pnl_percent", "last_updated")
    list_filter = ("portfolio", "last_updated")
    search_fields = ("portfolio__name", "stock__ticker")
    readonly_fields = ("last_updated", "created_at")

@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = ("portfolio", "trade_type", "status", "quantity", "price", "created_at")
    list_filter = ("trade_type", "status", "created_at", "portfolio")
    search_fields = ("portfolio__name", "stock__ticker")
    readonly_fields = ("created_at", "submitted_at", "filled_at")
    date_hierarchy = "created_at"

@admin.register(PerformanceMetric)
class PerformanceMetricAdmin(admin.ModelAdmin):
    list_display = ("portfolio", "date", "total_value", "cumulative_return", "daily_return")
    list_filter = ("portfolio", "date")
    search_fields = ("portfolio__name",)
    readonly_fields = ("created_at",)
    date_hierachy = "created_at"
