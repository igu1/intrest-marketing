import uuid
from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products")
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    image = models.ImageField(upload_to="products/", blank=True)
    gallery = models.JSONField(default=list, blank=True)
    is_featured = models.BooleanField(default=False)
    cta_text = models.CharField(max_length=50, default="Shop Now")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def discount_percent(self):
        if self.original_price and self.original_price > self.price:
            return int((1 - self.price / self.original_price) * 100)
        return 0


class Visitor(models.Model):
    session_id = models.CharField(max_length=100, unique=True)
    chat_id = models.CharField(max_length=255, blank=True, default="")
    username = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.username:
            return self.username
        return self.session_id[:8]


class PageView(models.Model):
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="page_views")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="page_views", blank=True, null=True)
    url = models.CharField(max_length=500)
    entered_at = models.DateTimeField(auto_now_add=True)
    dwell_time = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-entered_at"]


class TrackingEvent(models.Model):
    EVENT_TYPES = [
        ("product_click", "Product Click"),
        ("cta_click", "CTA Click"),
        ("section_view", "Section View"),
        ("scroll_depth", "Scroll Depth"),
        ("gallery_interaction", "Gallery Interaction"),
        ("negative_signal", "Negative Signal"),
        ("dwell_time", "Dwell Time"),
    ]

    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="events")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="events", blank=True, null=True)
    event_type = models.CharField(max_length=30, choices=EVENT_TYPES)
    value = models.FloatField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} - {self.visitor.session_id[:8]}"


class ProductScore(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="scores")
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="product_scores")
    base_score = models.FloatField(default=0)
    multiplier = models.FloatField(default=1.0)
    final_score = models.FloatField(default=0)
    visit_count = models.PositiveIntegerField(default=0)
    last_interaction = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["product", "visitor"]
        ordering = ["-final_score"]

    def __str__(self):
        return f"{self.product.name}: {self.final_score:.1f}"
