from django.core.management.base import BaseCommand
from ecommerce.models import Category, Product


class Command(BaseCommand):
    help = "Seed the database with sample products and categories"

    def handle(self, *args, **options):
        categories = [
            {"name": "Electronics", "slug": "electronics", "icon": "laptop"},
            {"name": "Clothing", "slug": "clothing", "icon": "tshirt"},
            {"name": "Accessories", "slug": "accessories", "icon": "gem"},
            {"name": "Home & Living", "slug": "home-living", "icon": "couch"},
            {"name": "Sports", "slug": "sports", "icon": "football"},
        ]

        cat_objs = {}
        for c in categories:
            obj, _ = Category.objects.get_or_create(slug=c["slug"], defaults=c)
            cat_objs[c["slug"]] = obj

        products = [
            {"name": "Wireless Pro Headphones", "slug": "wireless-pro-headphones", "category": "electronics", "price": "89.99", "original_price": "149.99", "description": "Premium wireless headphones with active noise cancellation, 40-hour battery life, and crystal-clear sound quality. Perfect for music lovers and professionals.", "is_featured": True, "cta_text": "Shop Now"},
            {"name": "Smart Watch Ultra", "slug": "smart-watch-ultra", "category": "electronics", "price": "299.99", "original_price": "399.99", "description": "Advanced smartwatch with health monitoring, GPS, and seamless connectivity. Track your fitness goals with precision.", "is_featured": True, "cta_text": "Buy Now"},
            {"name": "Premium Cotton T-Shirt", "slug": "premium-cotton-tshirt", "category": "clothing", "price": "29.99", "original_price": "49.99", "description": "Ultra-soft premium cotton t-shirt with a modern fit. Available in multiple colors.", "is_featured": True, "cta_text": "Shop Now"},
            {"name": "Leather Crossbody Bag", "slug": "leather-crossbody-bag", "category": "accessories", "price": "79.99", "original_price": "129.99", "description": "Handcrafted genuine leather crossbody bag with adjustable strap. Perfect for everyday use.", "is_featured": True, "cta_text": "Get It Now"},
            {"name": "Minimalist Desk Lamp", "slug": "minimalist-desk-lamp", "category": "home-living", "price": "59.99", "original_price": "89.99", "description": "Sleek LED desk lamp with adjustable brightness and color temperature. USB charging port included.", "is_featured": True, "cta_text": "Shop Now"},
            {"name": "Bluetooth Speaker Max", "slug": "bluetooth-speaker-max", "category": "electronics", "price": "129.99", "original_price": "179.99", "description": "Powerful portable speaker with 360-degree sound, waterproof design, and 24-hour battery life.", "is_featured": False, "cta_text": "Shop Now"},
            {"name": "Running Shoes Elite", "slug": "running-shoes-elite", "category": "sports", "price": "119.99", "original_price": "159.99", "description": "Lightweight running shoes with responsive cushioning and breathable mesh upper.", "is_featured": True, "cta_text": "Run Now"},
            {"name": "Yoga Mat Premium", "slug": "yoga-mat-premium", "category": "sports", "price": "39.99", "original_price": "59.99", "description": "Extra thick non-slip yoga mat with alignment markers. Eco-friendly materials.", "is_featured": False, "cta_text": "Shop Now"},
            {"name": "Sunglasses Aviator", "slug": "sunglasses-aviator", "category": "accessories", "price": "69.99", "original_price": "99.99", "description": "Classic aviator sunglasses with UV400 protection and polarized lenses.", "is_featured": True, "cta_text": "Get It"},
            {"name": "Denim Jacket Classic", "slug": "denim-jacket-classic", "category": "clothing", "price": "89.99", "original_price": "139.99", "description": "Timeless denim jacket with a comfortable stretch fit. Perfect for layering.", "is_featured": False, "cta_text": "Shop Now"},
            {"name": "Mechanical Keyboard RGB", "slug": "mechanical-keyboard-rgb", "category": "electronics", "price": "149.99", "original_price": "199.99", "description": "Hot-swappable mechanical keyboard with per-key RGB lighting and premium switches.", "is_featured": True, "cta_text": "Buy Now"},
            {"name": "Scented Candle Set", "slug": "scented-candle-set", "category": "home-living", "price": "34.99", "original_price": "49.99", "description": "Set of 3 hand-poured soy candles with calming essential oil fragrances.", "is_featured": False, "cta_text": "Shop Now"},
        ]

        for p in products:
            Product.objects.get_or_create(
                slug=p["slug"],
                defaults={
                    "name": p["name"],
                    "category": cat_objs[p["category"]],
                    "description": p["description"],
                    "price": p["price"],
                    "original_price": p["original_price"],
                    "is_featured": p["is_featured"],
                    "cta_text": p["cta_text"],
                },
            )

        self.stdout.write(self.style.SUCCESS("Successfully seeded database with sample data!"))
