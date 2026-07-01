from django.contrib import admin
from .models import Category, Product, Visitor, PageView, TrackingEvent, ProductScore


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "is_featured", "created_at")
    list_filter = ("category", "is_featured")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ("session_id", "ip_address", "first_seen", "last_seen")


@admin.register(PageView)
class PageViewAdmin(admin.ModelAdmin):
    list_display = ("visitor", "product", "url", "dwell_time", "entered_at")


@admin.register(TrackingEvent)
class TrackingEventAdmin(admin.ModelAdmin):
    list_display = ("visitor", "event_type", "product", "value", "created_at")
    list_filter = ("event_type",)


@admin.register(ProductScore)
class ProductScoreAdmin(admin.ModelAdmin):
    list_display = ("product", "visitor", "base_score", "multiplier", "final_score", "visit_count")
