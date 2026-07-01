import json
import uuid
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Category, Product, PageView, Visitor, ProductScore
from .scoring import (
    get_or_create_visitor,
    record_event,
    get_recommendations,
    get_lead_temperature,
    get_top_products,
)


# ─── Cart Helper Functions ───
def _get_cart(request):
    return request.session.get("cart", {})


def _save_cart(request, cart):
    request.session["cart"] = cart
    request.session.modified = True


def _get_cart_count(request):
    cart = _get_cart(request)
    return sum(int(item.get("quantity", 1)) for item in cart.values())


def _get_cart_items(request):
    cart = _get_cart(request)
    items = []
    total = 0
    for product_id, item in cart.items():
        try:
            product = Product.objects.get(id=int(product_id))
            qty = int(item.get("quantity", 1))
            items.append({
                "product": product,
                "quantity": qty,
                "subtotal": float(product.price) * qty,
            })
            total += float(product.price) * qty
        except Product.DoesNotExist:
            pass
    return items, total


def _capture_ref(request):
    ref = request.GET.get("ref") or request.session.get("chat_id")
    if ref:
        request.session["chat_id"] = ref
        from dashboard.models import IdentifiedUser
        user, created = IdentifiedUser.objects.get_or_create(
            chat_id=ref,
            defaults={"username": f"user_{ref[:8]}"},
        )
        return ref, user
    return None, None


def _get_visitor(request):
    _capture_ref(request)

    session_id = request.session.get("visitor_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session["visitor_id"] = session_id

    visitor = get_or_create_visitor(session_id)

    chat_id = request.session.get("chat_id")
    if chat_id:
        if not visitor.chat_id:
            visitor.chat_id = chat_id
        from dashboard.models import IdentifiedUser
        try:
            ident = IdentifiedUser.objects.get(chat_id=chat_id)
            if visitor.username != ident.username:
                visitor.username = ident.username
                visitor.save(update_fields=["username"])
        except IdentifiedUser.DoesNotExist:
            if not visitor.username:
                visitor.username = f"user_{chat_id[:8]}"
                visitor.save()

    return visitor


def home(request):
    visitor = _get_visitor(request)
    featured = Product.objects.filter(is_featured=True)[:8]
    categories = Category.objects.all()
    recommendations = get_recommendations(visitor, limit=4)
    
    PageView.objects.create(
        visitor=visitor,
        url=request.get_full_path(),
    )
    
    context = {
        "featured": featured,
        "categories": categories,
        "recommendations": recommendations,
        "cart_count": _get_cart_count(request),
        "active_category": "",
    }
    return render(request, "ecommerce/home.html", context)


def product_list(request):
    visitor = _get_visitor(request)
    category_slug = request.GET.get("category")
    search_query = request.GET.get("q", "")
    sort_by = request.GET.get("sort", "")

    products = Product.objects.all()
    if category_slug:
        products = products.filter(category__slug=category_slug)
    if search_query:
        products = products.filter(name__icontains=search_query)
    
    if sort_by == "price_low":
        products = products.order_by("price")
    elif sort_by == "price_high":
        products = products.order_by("-price")
    elif sort_by == "name":
        products = products.order_by("name")
    else:
        products = products.order_by("-created_at")

    categories = Category.objects.all()

    PageView.objects.create(visitor=visitor, url=request.get_full_path())

    context = {
        "products": products,
        "categories": categories,
        "active_category": category_slug,
        "search_query": search_query,
        "sort_by": sort_by,
        "cart_count": _get_cart_count(request),
    }
    return render(request, "ecommerce/product_list.html", context)


def product_detail(request, slug):
    visitor = _get_visitor(request)
    product = get_object_or_404(Product, slug=slug)

    record_event(visitor, "product_click", product=product)

    PageView.objects.create(visitor=visitor, product=product, url=request.get_full_path())

    lead_temp, lead_color = get_lead_temperature(
        _get_product_score_value(visitor, product)
    )
    
    # Related products from same category
    related = Product.objects.filter(category=product.category).exclude(id=product.id)[:4]
    
    # Check if in cart
    cart = _get_cart(request)
    in_cart = str(product.id) in cart
    cart_qty = cart.get(str(product.id), {}).get("quantity", 0) if in_cart else 0

    context = {
        "product": product,
        "lead_temp": lead_temp,
        "lead_color": lead_color,
        "related": related,
        "in_cart": in_cart,
        "cart_qty": cart_qty,
        "cart_count": _get_cart_count(request),
        "categories": Category.objects.all(),
    }
    return render(request, "ecommerce/product_detail.html", context)


def _get_product_score_value(visitor, product):
    try:
        return ProductScore.objects.get(visitor=visitor, product=product).final_score
    except ProductScore.DoesNotExist:
        return 0


@require_POST
def track_event(request):
    data = json.loads(request.body)
    visitor = _get_visitor(request)

    event_type = data.get("event_type")
    product_id = data.get("product_id")
    value = data.get("value", 0)
    metadata = data.get("metadata", {})

    product = None
    if product_id:
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            pass

    event = record_event(visitor, event_type, product=product, value=value, metadata=metadata)

    score = None
    if product:
        try:
            ps = ProductScore.objects.get(visitor=visitor, product=product)
            score = {
                "base": ps.base_score,
                "multiplier": ps.multiplier,
                "final": round(ps.final_score, 2),
                "visits": ps.visit_count,
                "temperature": get_lead_temperature(ps.final_score)[0],
            }
        except ProductScore.DoesNotExist:
            pass

    return JsonResponse({"ok": True, "event_id": event.id, "score": score})


@require_POST
def update_dwell_time(request):
    data = json.loads(request.body)
    visitor = _get_visitor(request)
    product_id = data.get("product_id")
    dwell_seconds = data.get("seconds", 0)

    if product_id and dwell_seconds > 0:
        try:
            product = Product.objects.get(id=product_id)
            if dwell_seconds >= 20:
                record_event(visitor, "dwell_time", product=product, value=dwell_seconds)
            pv = PageView.objects.filter(visitor=visitor, product=product).last()
            if pv:
                pv.dwell_time = dwell_seconds
                pv.save()
        except Product.DoesNotExist:
            pass

    return JsonResponse({"ok": True})


def analytics(request):
    visitor = _get_visitor(request)
    top = get_top_products(limit=20)
    recommendations = get_recommendations(visitor, limit=10)

    lead_temp, lead_color = "Cold", "#94a3b8"
    best_score = ProductScore.objects.filter(visitor=visitor).order_by("-final_score").first()
    if best_score:
        lead_temp, lead_color = get_lead_temperature(best_score.final_score)

    top_product = None
    if best_score:
        top_product = best_score.product

    chat_id = visitor.chat_id or request.session.get("chat_id", "")

    context = {
        "top_products": top,
        "recommendations": recommendations,
        "lead_temp": lead_temp,
        "lead_color": lead_color,
        "top_product": top_product,
        "chat_id": chat_id,
        "cart_count": _get_cart_count(request),
        "categories": Category.objects.all(),
    }
    return render(request, "ecommerce/analytics.html", context)


# ─── Cart Views ───
def cart(request):
    items, total = _get_cart_items(request)
    context = {
        "items": items,
        "total": total,
        "cart_count": _get_cart_count(request),
        "categories": Category.objects.all(),
    }
    return render(request, "ecommerce/cart.html", context)


@require_POST
def api_cart_add(request):
    data = json.loads(request.body)
    product_id = str(data.get("product_id"))
    quantity = int(data.get("quantity", 1))
    
    cart = _get_cart(request)
    if product_id in cart:
        cart[product_id]["quantity"] += quantity
    else:
        cart[product_id] = {"quantity": quantity}
    
    _save_cart(request, cart)
    return JsonResponse({"ok": True, "count": _get_cart_count(request)})


@require_POST
def api_cart_update(request):
    data = json.loads(request.body)
    product_id = str(data.get("product_id"))
    quantity = int(data.get("quantity", 0))
    
    cart = _get_cart(request)
    if quantity <= 0:
        cart.pop(product_id, None)
    else:
        cart[product_id] = {"quantity": quantity}
    
    _save_cart(request, cart)
    return JsonResponse({"ok": True, "count": _get_cart_count(request)})


@require_POST
def api_cart_remove(request):
    data = json.loads(request.body)
    product_id = str(data.get("product_id"))
    
    cart = _get_cart(request)
    cart.pop(product_id, None)
    _save_cart(request, cart)
    return JsonResponse({"ok": True, "count": _get_cart_count(request)})
