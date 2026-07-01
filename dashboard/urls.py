from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard_home, name="home"),
    path("bulk-message/", views.bulk_message, name="bulk_message"),
    path("analytics/", views.analytics, name="analytics"),
    path("send-bulk/", views.send_bulk_message, name="send_bulk"),
    path("test-message/", views.test_telegram_message, name="test_message"),
    path("send-product-image/", views.send_product_image, name="send_product_image"),
    path("bulk-progress/<int:campaign_id>/", views.bulk_progress, name="bulk_progress"),
]
