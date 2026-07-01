from ecommerce.models import Category


def global_context(request):
    cart = request.session.get("cart", {})
    cart_count = sum(int(item.get("quantity", 1)) for item in cart.values())
    categories = Category.objects.all()
    return {
        "cart_count": cart_count,
        "categories": categories,
    }
