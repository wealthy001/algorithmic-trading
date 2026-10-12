from django.urls import path

from . import views

app_name = "portfolio"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("portfolios/", views.portfolio_list, name="portfolio_list"),
    path("portfolios/new/", views.portfolio_create, name="portfolio_create"),
    path("portfolios/<int:pk>/connect-alpaca/", views.connect_alpaca, name="portfolio_connect_alpaca"),
    path("portfolios/<int:pk>/generate-signals/", views.generate_portfolio_signals, name="portfolio_generate_signals"),
    path("portfolios/<int:pk>/", views.portfolio_detail, name="portfolio_detail"),
]
