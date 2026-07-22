import io
import os
import uuid
from pathlib import Path

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from ecommerce.models import Category, Product


PLACEHOLDER_BASE = "https://placehold.co"


def _placeholder_url(label, width=600, height=600, text=None):
    """Generate a placeholder image URL for a given product label."""
    safe = label.replace(" ", "+").replace("&", "and")
    t = text or safe
    return f"{PLACEHOLDER_BASE}/{width}x{height}/EEE/999?text={t}"


def _gallery_for(slug, count=4):
    """Build a list of gallery image URLs for a product."""
    label = slug.replace("-", " ").title()
    return [
        _placeholder_url(label, width=800, height=800, text=f"View+{i+1}")
        for i in range(count)
    ]


CATEGORIES = [
    {"name": "Electronics", "slug": "electronics", "icon": "laptop"},
    {"name": "Clothing", "slug": "clothing", "icon": "tshirt"},
    {"name": "Accessories", "slug": "accessories", "icon": "gem"},
    {"name": "Home & Living", "slug": "home-living", "icon": "couch"},
    {"name": "Sports", "slug": "sports", "icon": "football"},
    {"name": "Beauty", "slug": "beauty", "icon": "spa"},
    {"name": "Books", "slug": "books", "icon": "book"},
]

PRODUCTS = [
    {
        "name": "Wireless Pro Headphones",
        "slug": "wireless-pro-headphones",
        "category": "electronics",
        "price": "89.99",
        "original_price": "149.99",
        "description": "Premium wireless headphones with active noise cancellation, 40-hour battery life, and crystal-clear sound quality. Perfect for music lovers and professionals.",
        "is_featured": True,
        "cta_text": "Shop Now",
    },
    {
        "name": "Smart Watch Ultra",
        "slug": "smart-watch-ultra",
        "category": "electronics",
        "price": "299.99",
        "original_price": "399.99",
        "description": "Advanced smartwatch with health monitoring, GPS, and seamless connectivity. Track your fitness goals with precision. Features include heart rate monitoring, sleep tracking, and 5 ATM water resistance.",
        "is_featured": True,
        "cta_text": "Buy Now",
    },
    {
        "name": "Premium Cotton T-Shirt",
        "slug": "premium-cotton-tshirt",
        "category": "clothing",
        "price": "29.99",
        "original_price": "49.99",
        "description": "Ultra-soft premium cotton t-shirt with a modern fit. Available in multiple colors including black, white, navy, and grey. Pre-shrunk fabric for lasting comfort.",
        "is_featured": True,
        "cta_text": "Shop Now",
    },
    {
        "name": "Leather Crossbody Bag",
        "slug": "leather-crossbody-bag",
        "category": "accessories",
        "price": "79.99",
        "original_price": "129.99",
        "description": "Handcrafted genuine leather crossbody bag with adjustable strap. Features multiple compartments, RFID blocking pocket, and premium brass hardware. Perfect for everyday use.",
        "is_featured": True,
        "cta_text": "Get It Now",
    },
    {
        "name": "Minimalist Desk Lamp",
        "slug": "minimalist-desk-lamp",
        "category": "home-living",
        "price": "59.99",
        "original_price": "89.99",
        "description": "Sleek LED desk lamp with adjustable brightness and color temperature. USB charging port included. Touch-sensitive controls and memory function for your preferred settings.",
        "is_featured": True,
        "cta_text": "Shop Now",
    },
    {
        "name": "Bluetooth Speaker Max",
        "slug": "bluetooth-speaker-max",
        "category": "electronics",
        "price": "129.99",
        "original_price": "179.99",
        "description": "Powerful portable speaker with 360-degree sound, waterproof design (IPX7), and 24-hour battery life. Built-in microphone for hands-free calls and party mode for multi-speaker pairing.",
        "is_featured": False,
        "cta_text": "Shop Now",
    },
    {
        "name": "Running Shoes Elite",
        "slug": "running-shoes-elite",
        "category": "sports",
        "price": "119.99",
        "original_price": "159.99",
        "description": "Lightweight running shoes with responsive cushioning and breathable mesh upper. Engineered for stability and speed with carbon fiber plate technology.",
        "is_featured": True,
        "cta_text": "Run Now",
    },
    {
        "name": "Yoga Mat Premium",
        "slug": "yoga-mat-premium",
        "category": "sports",
        "price": "39.99",
        "original_price": "59.99",
        "description": "Extra thick 6mm non-slip yoga mat with alignment markers. Made from eco-friendly TPE material. Includes carrying strap for easy transport.",
        "is_featured": False,
        "cta_text": "Shop Now",
    },
    {
        "name": "Sunglasses Aviator",
        "slug": "sunglasses-aviator",
        "category": "accessories",
        "price": "69.99",
        "original_price": "99.99",
        "description": "Classic aviator sunglasses with UV400 protection and polarized lenses. Lightweight titanium frame with adjustable nose pads for all-day comfort.",
        "is_featured": True,
        "cta_text": "Get It",
    },
    {
        "name": "Denim Jacket Classic",
        "slug": "denim-jacket-classic",
        "category": "clothing",
        "price": "89.99",
        "original_price": "139.99",
        "description": "Timeless denim jacket with a comfortable stretch fit. Features button closure, chest pockets, and adjustable waist tabs. Perfect for layering in any season.",
        "is_featured": False,
        "cta_text": "Shop Now",
    },
    {
        "name": "Mechanical Keyboard RGB",
        "slug": "mechanical-keyboard-rgb",
        "category": "electronics",
        "price": "149.99",
        "original_price": "199.99",
        "description": "Hot-swappable mechanical keyboard with per-key RGB lighting and premium Cherry MX switches. CNC aluminum frame, USB-C connectivity, and programmable macro keys.",
        "is_featured": True,
        "cta_text": "Buy Now",
    },
    {
        "name": "Scented Candle Set",
        "slug": "scented-candle-set",
        "category": "home-living",
        "price": "34.99",
        "original_price": "49.99",
        "description": "Set of 3 hand-poured soy candles with calming essential oil fragrances: Lavender, Vanilla Bean, and Eucalyptus. 40+ hours burn time each. Natural cotton wicks.",
        "is_featured": False,
        "cta_text": "Shop Now",
    },
    {
        "name": "Stainless Steel Water Bottle",
        "slug": "stainless-water-bottle",
        "category": "sports",
        "price": "24.99",
        "original_price": "39.99",
        "description": "Double-wall vacuum insulated water bottle that keeps drinks cold for 24 hours or hot for 12 hours. 750ml capacity, BPA-free, leak-proof lid.",
        "is_featured": True,
        "cta_text": "Shop Now",
    },
    {
        "name": "Organic Face Serum",
        "slug": "organic-face-serum",
        "category": "beauty",
        "price": "45.99",
        "original_price": "69.99",
        "description": "Vitamin C brightening face serum with hyaluronic acid. Organic, cruelty-free, and suitable for all skin types. Reduces fine lines and evens skin tone.",
        "is_featured": True,
        "cta_text": "Shop Now",
    },
    {
        "name": "Wireless Charging Pad",
        "slug": "wireless-charging-pad",
        "category": "electronics",
        "price": "19.99",
        "original_price": "29.99",
        "description": "Fast wireless charger compatible with all Qi-enabled devices. Slim design with LED indicator and foreign object detection. 15W fast charging.",
        "is_featured": False,
        "cta_text": "Shop Now",
    },
    {
        "name": "Kindle Paperwhite Case",
        "slug": "kindle-paperwhite-case",
        "category": "books",
        "price": "14.99",
        "original_price": "24.99",
        "description": "Premium slim-fit protective case for Kindle Paperwhite. Auto wake/sleep cover with magnetic closure. Lightweight design in multiple colors.",
        "is_featured": False,
        "cta_text": "Shop Now",
    },
    {
        "name": "French Press Coffee Maker",
        "slug": "french-press-coffee",
        "category": "home-living",
        "price": "32.99",
        "original_price": "49.99",
        "description": "Classic 34oz French press coffee maker with borosilicate glass carafe and stainless steel plunger. Makes 8 cups of rich, full-bodied coffee in minutes.",
        "is_featured": False,
        "cta_text": "Shop Now",
    },
    {
        "name": "Fitness Tracker Band",
        "slug": "fitness-tracker-band",
        "category": "electronics",
        "price": "49.99",
        "original_price": "79.99",
        "description": "Sleek fitness tracker with heart rate monitor, step counter, sleep analysis, and smartphone notifications. 7-day battery life and water resistant to 50m.",
        "is_featured": False,
        "cta_text": "Shop Now",
    },
]


class Command(BaseCommand):
    help = "Seed the database with sample categories, products, and placeholder images"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing products and categories before seeding",
        )
        parser.add_argument(
            "--download-images",
            action="store_true",
            help="Download placeholder images from placehold.co (requires internet)",
        )

    def _download_image(self, url, slug):
        """Download an image from a URL and return a ContentFile."""
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return ContentFile(resp.content, name=f"{slug}.png")
        except requests.RequestException as exc:
            self.stdout.write(self.style.WARNING(f"  Could not download image for '{slug}': {exc}"))
            return None

    @transaction.atomic
    def handle(self, *args, **options):
        should_clear = options["clear"]
        download_images = options["download_images"]

        # ── Clear existing data (optional) ──
        if should_clear:
            self.stdout.write("Clearing existing products and categories...")
            Product.objects.all().delete()
            Category.objects.all().delete()

        # ── Ensure media directory exists ──
        media_root = settings.MEDIA_ROOT
        products_dir = Path(media_root) / "products"
        products_dir.mkdir(parents=True, exist_ok=True)

        # ── Seed categories ──
        cat_objs = {}
        for c in CATEGORIES:
            obj, created = Category.objects.get_or_create(slug=c["slug"], defaults=c)
            if created:
                self.stdout.write(f"  Created category: {obj.name}")
            cat_objs[c["slug"]] = obj

        # ── Seed products ──
        created_count = 0
        updated_count = 0
        for p in PRODUCTS:
            slug = p["slug"]
            label = p["name"]
            gallery = _gallery_for(slug)

            defaults = {
                "name": p["name"],
                "category": cat_objs[p["category"]],
                "description": p["description"],
                "price": p["price"],
                "original_price": p["original_price"],
                "is_featured": p["is_featured"],
                "cta_text": p["cta_text"],
                "gallery": gallery,
            }

            obj, created = Product.objects.get_or_create(slug=slug, defaults=defaults)

            if created:
                created_count += 1
            else:
                # Update fields on existing products so gallery / new fields appear
                for field, value in defaults.items():
                    setattr(obj, field, value)
                obj.save()
                updated_count += 1

            # ── Download placeholder image (optional) ──
            if download_images and not obj.image:
                img_url = _placeholder_url(label)
                content = self._download_image(img_url, slug)
                if content:
                    obj.image.save(f"{slug}.png", content, save=True)
                    self.stdout.write(f"  Downloaded image for: {obj.name}")

            if created:
                self.stdout.write(f"  Created product: {obj.name}")

        # ── Summary ──
        self.stdout.write("=" * 50)
        self.stdout.write(self.style.SUCCESS(f"Seed complete!"))
        self.stdout.write(f"  Categories: {Category.objects.count()}")
        self.stdout.write(f"  Products:   {Product.objects.count()}")
        self.stdout.write(f"    Created:  {created_count}")
        self.stdout.write(f"    Updated:  {updated_count}")
        self.stdout.write(f"  Download images: {'Yes' if download_images else 'No (use --download-images to fetch placeholders)'}")
