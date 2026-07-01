from django.urls import path
from . import views

app_name = "ecommerce"

urlpatterns = [
    path("", views.home, name="home"),
    path("products/", views.product_list, name="product_list"),
    path("products/<slug:slug>/", views.product_detail, name="product_detail"),
    path("api/track/", views.track_event, name="track_event"),
    path("api/dwell/", views.update_dwell_time, name="update_dwell"),
    path("analytics/", views.analytics, name="analytics"),
    path("cart/", views.cart, name="cart"),
    path("api/cart/add/", views.api_cart_add, name="api_cart_add"),
    path("api/cart/update/", views.api_cart_update, name="api_cart_update"),
    path("api/cart/remove/", views.api_cart_remove, name="api_cart_remove"),
    path("api/set-name/", views.set_name, name="set_name"),
]
