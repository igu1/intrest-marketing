import json
import threading
from io import BytesIO
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
import openpyxl

from .models import BulkCampaign, MessageRecipient, IdentifiedUser
from .services import TelegramService


def dashboard_home(request):
    campaigns = BulkCampaign.objects.all()[:10]
    total_campaigns = BulkCampaign.objects.count()
    total_sent = sum(c.total_sent for c in BulkCampaign.objects.all())
    total_failed = sum(c.total_failed for c in BulkCampaign.objects.all())
    context = {
        "campaigns": campaigns,
        "total_campaigns": total_campaigns,
        "total_sent": total_sent,
        "total_failed": total_failed,
        "active_page": "dashboard",
    }
    return render(request, "dashboard/index.html", context)


def bulk_message(request):
    campaigns = BulkCampaign.objects.all().order_by("-created_at")[:20]
    context = {
        "campaigns": campaigns,
        "active_page": "bulk_message",
    }
    return render(request, "dashboard/bulk_message.html", context)


def analytics(request):
    from ecommerce.scoring import get_dashboard_analytics
    from ecommerce.models import Product, ProductScore, Visitor
    from dashboard.models import IdentifiedUser
    data = get_dashboard_analytics()

    existing_chat_ids = set()

    enhanced_users = []
    for user in data.get("per_user_summary", []):
        chat_id = user.get("chat_id", "")
        existing_chat_ids.add(chat_id)
        try:
            visitors = Visitor.objects.filter(chat_id=chat_id)
            best_score = ProductScore.objects.filter(visitor__in=visitors).order_by("-final_score").first()
            if best_score:
                user["top_product_id"] = best_score.product.id
                user["top_product_slug"] = best_score.product.slug
                user["top_product_name"] = best_score.product.name
                user["top_product_price"] = best_score.product.price
                user["top_product_image"] = best_score.product.image.url if best_score.product.image else ""
                user["top_product_category"] = best_score.product.category.name
            else:
                user["top_product_id"] = None
        except Exception:
            user["top_product_id"] = None
        enhanced_users.append(user)

    for ident in IdentifiedUser.objects.all():
        if ident.chat_id not in existing_chat_ids:
            enhanced_users.append({
                "username": ident.username or ident.chat_id,
                "chat_id": ident.chat_id,
                "total_events": 0,
                "cta_clicks": 0,
                "product_clicks": 0,
                "total_dwell": 0,
                "top_score": 0,
                "temperature": "Cold",
                "temp_color": "#94a3b8",
                "top_product_id": None,
            })

    data["per_user_summary"] = enhanced_users

    featured_products = Product.objects.filter(is_featured=True)[:10]
    data["featured_products"] = [
        {
            "id": p.id,
            "slug": p.slug,
            "name": p.name,
            "price": p.price,
            "image": p.image.url if p.image else "",
            "category": p.category.name,
        }
        for p in featured_products
    ]

    context = {
        "active_page": "analytics",
        **data,
    }
    return render(request, "dashboard/analytics.html", context)


def _process_bulk_send(campaign_id, recipients_data, image_file, site_url):
    campaign = BulkCampaign.objects.get(id=campaign_id)
    telegram = TelegramService()
    sent = 0
    failed = 0

    for r in recipients_data:
        text = r.get("message", "")
        text = text.replace("{name}", r["name"])

        recipient_obj = MessageRecipient.objects.filter(
            campaign=campaign, chat_id=r["chat_id"]
        ).first()

        ok = True

        if text:
            if image_file:
                image_file.seek(0)
                result = telegram.send_message_with_image(r["chat_id"], text, image_file=image_file)
            else:
                result = telegram.send_message(r["chat_id"], text)
            if not result["ok"]:
                ok = False
                failed += 1
                if recipient_obj:
                    recipient_obj.status = "failed"
                    recipient_obj.error_message = result.get("error", "")[:500]
                    recipient_obj.save()
                campaign.total_sent = sent
                campaign.total_failed = failed
                campaign.save()
                continue

        link_result = telegram.send_message(r["chat_id"], site_url)
        if ok and link_result["ok"]:
            sent += 1
            if recipient_obj:
                recipient_obj.status = "sent"
                recipient_obj.save()
        elif ok:
            failed += 1
            if recipient_obj:
                recipient_obj.status = "failed"
                recipient_obj.error_message = link_result.get("error", "")[:500]
                recipient_obj.save()
            campaign.total_sent = sent
            campaign.total_failed = failed
            campaign.save()

        campaign.total_sent = sent
        campaign.total_failed = failed
        campaign.save()

    campaign.status = "completed"
    campaign.sent_at = timezone.now()
    campaign.save()


@csrf_exempt
@require_POST
def send_bulk_message(request):
    image = request.FILES.get("image")
    sheet = request.FILES.get("sheet")

    if not sheet:
        return JsonResponse({"ok": False, "error": "Sheet file is required."})

    try:
        wb = openpyxl.load_workbook(sheet)
        ws = wb.active
        recipients = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if len(row) >= 2 and row[0] and row[1]:
                recipients.append({
                    "name": str(row[0]).strip(),
                    "chat_id": str(row[1]).strip(),
                    "message": str(row[2]).strip() if len(row) >= 3 and row[2] else "",
                })
    except Exception as e:
        return JsonResponse({"ok": False, "error": f"Failed to parse sheet: {e}"})

    if not recipients:
        return JsonResponse({"ok": False, "error": "No valid recipients found in sheet."})

    from django.conf import settings
    site_url = settings.SITE_URL

    campaign = BulkCampaign.objects.create(
        name=f"Campaign {timezone.now().strftime('%Y-%m-%d %H:%M')}",
        message_text="",
        image=image if image else None,
        status="sending",
    )

    for r in recipients:
        MessageRecipient.objects.create(
            campaign=campaign,
            name=r["name"],
            chat_id=r["chat_id"],
        )
        user, _ = IdentifiedUser.objects.get_or_create(
            chat_id=r["chat_id"],
            defaults={"username": r["name"]},
        )
        if user.username != r["name"]:
            user.username = r["name"]
            user.save()
        from ecommerce.models import Visitor
        Visitor.objects.filter(chat_id=r["chat_id"]).update(username=r["name"])

    image_data = None
    if campaign.image:
        campaign.image.open("rb")
        image_data = BytesIO(campaign.image.read())
        image_data.name = campaign.image.name

    thread = threading.Thread(
        target=_process_bulk_send,
        args=(campaign.id, recipients, image_data, site_url),
        daemon=True,
    )
    thread.start()

    return JsonResponse({
        "ok": True,
        "campaign_id": campaign.id,
        "total": len(recipients),
    })


def bulk_progress(request, campaign_id):
    try:
        campaign = BulkCampaign.objects.get(id=campaign_id)
    except BulkCampaign.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Campaign not found"})

    total = campaign.total_sent + campaign.total_failed
    return JsonResponse({
        "ok": True,
        "status": campaign.status,
        "sent": campaign.total_sent,
        "failed": campaign.total_failed,
        "total": total,
    })


@require_POST
def test_telegram_message(request):
    chat_id = request.POST.get("chat_id", "")
    message = request.POST.get("message", "Test message from SamShar Dashboard")
    image = request.FILES.get("image")

    if not chat_id:
        return JsonResponse({"ok": False, "error": "chat_id is required."})

    telegram = TelegramService()

    if image:
        result = telegram.send_message_with_image(chat_id, message, image_file=image)
    else:
        result = telegram.send_message(chat_id, message)

    return JsonResponse(result)


@csrf_exempt
@require_POST
def send_product_image(request):
    """Send a product image with caption to a specific Telegram chat."""
    import json
    data = json.loads(request.body)
    chat_id = data.get("chat_id", "")
    product_id = data.get("product_id")
    message = data.get("message", "")

    if not chat_id:
        return JsonResponse({"ok": False, "error": "chat_id is required."})

    if not product_id:
        return JsonResponse({"ok": False, "error": "product_id is required."})

    try:
        from ecommerce.models import Product
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return JsonResponse({"ok": False, "error": "Product not found."})

    telegram = TelegramService()

    username = ""
    try:
        ident = IdentifiedUser.objects.get(chat_id=chat_id)
        username = ident.username
    except IdentifiedUser.DoesNotExist:
        pass

    product_url = f"http://127.0.0.1:8000/products/{product.slug}/?ref={chat_id}"

    price_line = f"Price: Rs{product.price}"
    if product.original_price and product.original_price > product.price:
        discount = product.discount_percent
        price_line += f" <s>Rs{product.original_price}</s> (Save {discount}%)"

    desc = product.description[:300] if product.description else ""
    if len(product.description) > 300:
        desc += "..."

    greeting = f"Hi {username}! " if username else ""

    caption = message or f"""{greeting}<b>{product.name}</b>

Category: {product.category.name}
{price_line}

Description:
{desc}

<a href="{product_url}">View Product</a>
"""

    if product.image:
        product.image.open("rb")
        raw = BytesIO(product.image.read())
        raw.name = product.image.name

        if username:
            try:
                from PIL import Image, ImageDraw, ImageFont
                raw.seek(0)
                pil_img = Image.open(raw)
                pil_img = pil_img.convert("RGBA")
                overlay = Image.new("RGBA", pil_img.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)
                text = f"Hi {username}!"
                try:
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size=28)
                except Exception:
                    font = ImageFont.load_default()
                bbox = draw.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                x, y = 12, 12
                margin = 8
                draw.rounded_rectangle(
                    [(x - margin, y - margin), (x + tw + margin * 2, y + th + margin)],
                    radius=8, fill=(255, 255, 255, 200)
                )
                draw.text((x + margin, y), text, font=font, fill=(0, 0, 0, 255))
                pil_img = Image.alpha_composite(pil_img, overlay)
                pil_img = pil_img.convert("RGB")
                named = BytesIO()
                pil_img.save(named, format="JPEG", quality=90)
                named.seek(0)
                named.name = product.image.name
                raw = named
            except Exception:
                raw.seek(0)

        result = telegram.send_photo(chat_id, raw, caption=caption)
    else:
        result = telegram.send_message(chat_id, caption)

    return JsonResponse(result)
