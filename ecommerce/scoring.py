from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Count, F, Q, Avg, Max
from .models import TrackingEvent, ProductScore, Visitor, Product, PageView

EVENT_SCORES = {
    "cta_click": 7,
    "product_click": 5,
    "dwell_time": 4,
    "section_view": 2,
    "gallery_interaction": 1,
    "negative_signal": -1,
}

MULTIPLIER_CAP = 1.5
DECAY_RATE = 0.9
DECAY_HOURS = 24
SCROLL_THRESHOLDS = [25, 50, 75, 100]
SCROLL_SCORE_PER_THRESHOLD = 1


def get_or_create_visitor(session_id):
    visitor, _ = Visitor.objects.get_or_create(
        session_id=session_id,
        defaults={"session_id": session_id},
    )
    return visitor


def record_event(visitor, event_type, product=None, value=0, metadata=None):
    event = TrackingEvent.objects.create(
        visitor=visitor,
        product=product,
        event_type=event_type,
        value=value,
        metadata=metadata or {},
    )
    if product:
        _update_score(visitor, product, event_type, value)
    return event


def _scroll_points_already_awarded(visitor, product):
    events = TrackingEvent.objects.filter(
        visitor=visitor,
        product=product,
        event_type="scroll_depth",
    )
    awarded = set()
    for e in events:
        awarded.add(int(e.value))
    return awarded


def _update_score(visitor, product, event_type, value=0):
    score_obj, created = ProductScore.objects.get_or_create(
        product=product,
        visitor=visitor,
    )

    points = EVENT_SCORES.get(event_type, 0)

    if event_type == "scroll_depth":
        already = _scroll_points_already_awarded(visitor, product)
        threshold = int(value)
        if threshold in already:
            return score_obj
        points = SCROLL_SCORE_PER_THRESHOLD

    score_obj.base_score += points
    score_obj.visit_count += 1
    score_obj.multiplier = min(1.0 + (score_obj.visit_count - 1) * 0.1, MULTIPLIER_CAP)
    score_obj.final_score = score_obj.base_score * score_obj.multiplier
    _apply_decay(score_obj)
    score_obj.save()
    return score_obj


def _apply_decay(score_obj):
    now = timezone.now()
    hours_since = (now - score_obj.last_interaction).total_seconds() / 3600
    days_old = hours_since / 24
    if days_old > 0:
        score_obj.final_score = score_obj.final_score * (DECAY_RATE ** days_old)


def get_product_scores(visitor=None):
    qs = ProductScore.objects.all()
    if visitor:
        qs = qs.filter(visitor=visitor)
    return qs.order_by("-final_score")


def get_lead_temperature(score):
    if score >= 40:
        return "Ready to Buy", "#10b981"
    if score >= 26:
        return "Hot", "#f59e0b"
    if score >= 11:
        return "Warm", "#3b82f6"
    return "Cold", "#94a3b8"


def get_recommendations(visitor, limit=10):
    scored = ProductScore.objects.filter(visitor=visitor).order_by("-final_score")[:limit]
    return [s.product for s in scored]


def get_top_products(limit=10):
    return (
        ProductScore.objects.values("product__name", "product__id")
        .annotate(
            total_score=Sum("final_score"),
            total_visitors=Count("visitor", distinct=True),
        )
        .order_by("-total_score")[:limit]
    )


def get_dashboard_analytics():
    identified_visitors = Visitor.objects.exclude(chat_id="").values_list("id", flat=True)
    all_visitors = Visitor.objects.all()

    total_visitors = all_visitors.count()
    identified_count = Visitor.objects.exclude(chat_id="").count()
    total_events = TrackingEvent.objects.count()
    total_page_views = PageView.objects.count()

    cta_clicks = TrackingEvent.objects.filter(event_type="cta_click").count()
    product_clicks = TrackingEvent.objects.filter(event_type="product_click").count()
    dwell_events = TrackingEvent.objects.filter(event_type="dwell_time")

    total_dwell = dwell_events.aggregate(total=Sum("value"))["total"] or 0
    avg_dwell = dwell_events.aggregate(avg=Avg("value"))["avg"] or 0

    scroll_events = TrackingEvent.objects.filter(event_type="scroll_depth").count()
    gallery_events = TrackingEvent.objects.filter(event_type="gallery_interaction").count()

    top_clicked = (
        TrackingEvent.objects.filter(event_type="product_click")
        .values("product__name", "product__id")
        .annotate(clicks=Count("id"))
        .order_by("-clicks")[:10]
    )

    top_cta = (
        TrackingEvent.objects.filter(event_type="cta_click")
        .values("product__name", "product__id")
        .annotate(clicks=Count("id"))
        .order_by("-clicks")[:10]
    )

    top_dwell = (
        TrackingEvent.objects.filter(event_type="dwell_time")
        .values("product__name", "product__id")
        .annotate(
            total_seconds=Sum("value"),
            avg_seconds=Avg("value"),
            sessions=Count("id"),
        )
        .order_by("-total_seconds")[:10]
    )

    top_scrolled = (
        TrackingEvent.objects.filter(event_type="scroll_depth")
        .values("product__name", "product__id")
        .annotate(
            max_depth=Max("value"),
            events=Count("id"),
        )
        .order_by("-max_depth")[:10]
    )

    top_scored = list(
        ProductScore.objects.values("product__name", "product__id")
        .annotate(
            total_score=Sum("final_score"),
            unique_visitors=Count("visitor", distinct=True),
        )
        .order_by("-total_score")[:10]
    )

    user_engagement = []
    if identified_count > 0:
        user_engagement = (
            ProductScore.objects.filter(visitor__in=identified_visitors)
            .values(
                "visitor__username",
                "visitor__chat_id",
                "product__name",
            )
            .annotate(
                score=Sum("final_score"),
                visits=Sum("visit_count"),
            )
            .order_by("-score")[:50]
        )

    per_user_summary = []
    if identified_count > 0:
        per_user_summary = []
        for v in Visitor.objects.exclude(chat_id="").iterator():
            events = TrackingEvent.objects.filter(visitor=v)
            ev_count = events.count()
            if ev_count == 0:
                continue
            cta = events.filter(event_type="cta_click").count()
            clicks = events.filter(event_type="product_click").count()
            dwell = events.filter(event_type="dwell_time")
            total_d = dwell.aggregate(t=Sum("value"))["t"] or 0
            best_score = ProductScore.objects.filter(visitor=v).order_by("-final_score").first()
            final = best_score.final_score if best_score else 0
            temp, color = get_lead_temperature(final)
            per_user_summary.append({
                "username": v.username or v.chat_id,
                "chat_id": v.chat_id,
                "total_events": ev_count,
                "cta_clicks": cta,
                "product_clicks": clicks,
                "total_dwell": total_d,
                "top_score": round(final, 1),
                "temperature": temp,
                "temp_color": color,
            })
        per_user_summary.sort(key=lambda x: x["top_score"], reverse=True)

    event_breakdown = []
    for etype, label in TrackingEvent.EVENT_TYPES:
        cnt = TrackingEvent.objects.filter(event_type=etype).count()
        event_breakdown.append({"type": etype, "label": label, "count": cnt})

    return {
        "total_visitors": total_visitors,
        "identified_visitors": identified_count,
        "total_events": total_events,
        "total_page_views": total_page_views,
        "cta_clicks": cta_clicks,
        "product_clicks": product_clicks,
        "total_dwell_seconds": total_dwell,
        "avg_dwell_seconds": round(avg_dwell, 1),
        "scroll_events": scroll_events,
        "gallery_events": gallery_events,
        "top_clicked": list(top_clicked),
        "top_cta": list(top_cta),
        "top_dwell": list(top_dwell),
        "top_scrolled": list(top_scrolled),
        "top_scored": top_scored,
        "user_engagement": list(user_engagement),
        "per_user_summary": per_user_summary,
        "event_breakdown": event_breakdown,
    }
