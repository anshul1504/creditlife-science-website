from django.conf import settings

from . import loyalty
from .models import Bundle, Coupon, Product, SavedCart
from . import sitecfg

SESSION_KEY = "cart"
COUPON_KEY = "coupon"
POINTS_KEY = "points"


def persist(user, data):
    """Mirror the session cart onto the server so it follows the customer to other devices."""
    if data:
        # a changed cart is a fresh chance to remind, so reminded_at is cleared
        SavedCart.objects.update_or_create(user=user, defaults={"data": dict(data), "reminded_at": None})
    else:
        SavedCart.objects.filter(user=user).delete()


def merge_on_login(sender, request, user, **kwargs):
    """user_logged_in handler: combine the cart they built before signing in with the one they left last time.

    Quantities are capped at the limit per order and at what is in stock, and products that are no longer sold are
    dropped, with a short note so the customer knows why the basket changed."""
    from django.contrib import messages
    max_qty = settings.SHOP["max_qty"]
    saved = dict(SavedCart.objects.filter(user=user).values_list("data", flat=True).first() or {})
    guest = dict(request.session.get(SESSION_KEY) or {})
    merged = dict(saved)
    for slug, qty in guest.items():
        merged[slug] = min(max(merged.get(slug, 0), qty), max_qty)  # max, not sum: the same cart seen twice must not double
    products = {p.slug: p for p in Product.objects.filter(slug__in=merged, is_active=True)}
    final, trimmed = {}, []
    for slug, qty in merged.items():
        p = products.get(slug)
        if p is None:
            trimmed.append(slug)
            continue
        limit = max_qty if p.available_qty is None else min(max_qty, p.available_qty)
        if limit <= 0:
            trimmed.append(p.name)
            continue
        if qty > limit:
            trimmed.append(p.name)
        final[slug] = min(qty, limit)
    request.session[SESSION_KEY] = final
    persist(user, final)
    try:
        if guest and saved and final:
            messages.info(request, "We combined the items you added before signing in with your saved cart.")
        if trimmed:
            messages.warning(request, "Some items were adjusted or removed because of stock or availability: " + ", ".join(trimmed) + ".")
    except Exception:  # no messages middleware (e.g. management commands)
        pass


class Cart:
    """Session-backed shopping cart: {product slug: quantity}, plus an optional coupon code."""

    def __init__(self, request):
        self.session = request.session
        self.user = getattr(request, "user", None)
        self.data = dict(self.session.get(SESSION_KEY, {}))
        self.max_qty = settings.SHOP["max_qty"]
        self.coupon_notice = ""
        self._rows = None
        self._coupon_state = None
        self._bundles = None

    # ------------------------------------------------------------ storage
    def _save(self):
        self.session[SESSION_KEY] = self.data
        self.session.modified = True
        self._rows = None
        self._coupon_state = None
        self._bundles = None
        if self.user is not None and self.user.is_authenticated:
            persist(self.user, self.data)

    def add(self, product, qty=1):
        current = self.data.get(product.slug, 0)
        limit = self.max_qty if product.available_qty is None else min(self.max_qty, product.available_qty)
        self.data[product.slug] = max(1, min(current + qty, limit))
        self._save()

    def set(self, product, qty):
        if qty <= 0:
            self.remove(product.slug)
            return
        limit = self.max_qty if product.available_qty is None else min(self.max_qty, product.available_qty)
        self.data[product.slug] = max(1, min(qty, limit))
        self._save()

    def remove(self, slug):
        self.data.pop(slug, None)
        self._save()

    def clear(self):
        self.data = {}
        self.session.pop(COUPON_KEY, None)
        self.session.pop(POINTS_KEY, None)
        self._save()

    # -------------------------------------------------------------- lines
    @property
    def items(self):
        if self._rows is None:
            products = {p.slug: p for p in Product.objects.filter(slug__in=self.data.keys())}
            rows = []
            for slug, qty in self.data.items():
                product = products.get(slug)
                if product and product.sellable and product.in_stock:
                    left = product.available_qty
                    if left is not None and qty > left:
                        qty = left  # never offer more than the batches hold
                        self.coupon_notice = f"Only {left} of {product.name} left, so we adjusted your quantity."
                    unit = product.effective_price
                    rows.append({"product": product, "qty": qty, "unit": unit, "line": unit * qty})
            self._rows = rows
        return self._rows

    @property
    def count(self):
        return sum(row["qty"] for row in self.items)

    @property
    def subtotal(self):
        return sum(row["line"] for row in self.items)

    # ------------------------------------------------------------ bundles
    @property
    def bundles_applied(self):
        """[(bundle, sets, saving)] for every bundle whose items are all in the cart. Each unit counts for one bundle only."""
        if self._bundles is None:
            left = {row["product"].slug: row["qty"] for row in self.items}
            applied = []
            for bundle in Bundle.objects.filter(is_active=True):
                lines = bundle.lines
                if not lines or bundle.saving <= 0:
                    continue
                sets = min((left.get(i.product.slug, 0) // i.quantity for i in lines), default=0)
                if sets:
                    for i in lines:
                        left[i.product.slug] -= sets * i.quantity
                    applied.append((bundle, sets, sets * bundle.saving))
            self._bundles = applied
        return self._bundles

    @property
    def bundle_discount(self):
        return sum(saving for _, _, saving in self.bundles_applied)

    # -------------------------------------------------------- credit points
    @property
    def points_used(self):
        want = self.session.get(POINTS_KEY)
        if not want or not (self.user and self.user.is_authenticated):
            return 0
        payable = self.subtotal - self.bundle_discount - self.discount
        return max(0, min(int(want), loyalty.max_redeemable(self.user, payable)))

    @property
    def points_discount(self):
        return loyalty.points_value(self.points_used)

    @property
    def points_balance(self):
        return loyalty.balance(self.user)

    def apply_points(self, requested):
        if not (self.user and self.user.is_authenticated):
            return False, "Please sign in to use your credit points."
        payable = self.subtotal - self.bundle_discount - self.discount
        most = loyalty.max_redeemable(self.user, payable)
        if most <= 0:
            return False, "You have no credit points to use on this order."
        points = most if str(requested).lower() in ("max", "all", "") else min(max(int(requested), 0), most)
        self.session[POINTS_KEY] = points
        self.session.modified = True
        return True, f"{points} credit points applied. You save Rs {loyalty.points_value(points)}."

    def remove_points(self):
        self.session.pop(POINTS_KEY, None)
        self.session.modified = True

    # ------------------------------------------------------------- coupon
    def _evaluate_coupon(self):
        if self._coupon_state is None:
            state = (None, 0, False)
            code = self.session.get(COUPON_KEY)
            if code and self.items:
                coupon = Coupon.objects.filter(code=code.upper()).first()
                if coupon is None:
                    self.coupon_notice = "That coupon is no longer available."
                    self.session.pop(COUPON_KEY, None)
                else:
                    discount, error = coupon.evaluate(self.subtotal, self.user)
                    if error:
                        self.coupon_notice = f"Coupon {coupon.code} was removed: {error}"
                        self.session.pop(COUPON_KEY, None)
                    else:
                        state = (coupon, discount, coupon.free_shipping)
            self._coupon_state = state
        return self._coupon_state

    @property
    def coupon(self):
        return self._evaluate_coupon()[0]

    @property
    def discount(self):
        return self._evaluate_coupon()[1]

    def apply_coupon(self, code):
        """Try a code. Returns (ok, message). The code is kept only if it is valid for this cart."""
        code = (code or "").strip().upper()
        if not code:
            return False, "Please enter a coupon code."
        if not self.items:
            return False, "Add a product to your cart before applying a coupon."
        coupon = Coupon.objects.filter(code=code).first()
        if coupon is None:
            return False, "That coupon code is not valid."
        discount, error = coupon.evaluate(self.subtotal, self.user)
        if error:
            return False, error
        self.session[COUPON_KEY] = coupon.code
        self.session.modified = True
        self._coupon_state = None
        if discount:
            return True, f"Coupon {coupon.code} applied. You save Rs {discount}."
        return True, f"Coupon {coupon.code} applied. Delivery is free on this order."

    def remove_coupon(self):
        self.session.pop(COUPON_KEY, None)
        self.session.modified = True
        self._coupon_state = None

    def available_offers(self):
        """Public coupons the customer could use, with whether this cart qualifies."""
        offers = []
        for coupon in Coupon.objects.filter(active=True, public=True):
            discount, error = coupon.evaluate(self.subtotal, self.user)
            offers.append({"coupon": coupon, "eligible": error is None, "reason": error or "", "saving": discount})
        return offers

    @property
    def whatsapp_url(self):
        """A WhatsApp chat pre-filled with this cart, for ordering through the sales team."""
        from urllib.parse import quote
        lines = [f"- {row['qty']} x {row['product'].name} ({row['product'].pack})" for row in self.items]
        text = "Hello Credit Lifesciences, I would like to place an order:\n" + "\n".join(lines)
        return f"https://wa.me/{sitecfg.site()['whatsapp']}?text={quote(text)}"

    # ----------------------------------------------------------- totals
    @property
    def shipping(self):
        subtotal = self.subtotal
        threshold = settings.SHOP["free_shipping_above"]  # 0 means delivery is never free (the buyer bears shipping)
        if subtotal == 0 or (threshold and subtotal >= threshold) or self._evaluate_coupon()[2]:
            return 0
        return settings.SHOP["shipping_fee"]

    @property
    def total(self):
        return self.subtotal - self.bundle_discount - self.discount - self.points_discount + self.shipping

    @property
    def free_shipping_gap(self):
        subtotal = self.subtotal
        threshold = settings.SHOP["free_shipping_above"]
        return max(threshold - subtotal, 0) if subtotal else threshold

    @property
    def free_shipping_progress(self):
        threshold = settings.SHOP["free_shipping_above"]
        return min(100, round(self.subtotal * 100 / threshold)) if threshold else 100
