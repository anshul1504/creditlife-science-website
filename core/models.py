import random
from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Avg, Count, F, Q
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property


class ProductQuerySet(models.QuerySet):
    def on_sale(self):
        """Products whose sale price is lower than the normal price and whose sale window is open right now."""
        now = timezone.now()
        return self.filter(sale_price__gt=0, sale_price__lt=F("price")).filter(
            Q(sale_starts__isnull=True) | Q(sale_starts__lte=now),
            Q(sale_ends__isnull=True) | Q(sale_ends__gte=now),
        )


class Product(models.Model):
    class Category(models.TextChoices):
        DIGESTIVE = "digestive", "Digestive Care"
        NUTRITION = "nutrition", "Nutritional Support"
        PAIN = "pain", "Joint & Muscle Care"

    class System(models.TextChoices):
        AYURVEDIC = "ayurvedic", "Ayurvedic"
        ALLOPATHIC = "allopathic", "Allopathic"

    class Stage(models.TextChoices):
        LIGHT = "light", "Light (white-background image)"
        DARK = "dark", "Dark"
        GREEN = "green", "Green"

    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    system = models.CharField("Ayurvedic / Allopathic", max_length=12, choices=System.choices, default=System.ALLOPATHIC)
    is_rx = models.BooleanField(
        "Prescription (Rx) medicine",
        default=False,
        help_text="Rx products are never sold online and are shown without benefit claims.",
    )
    subtitle = models.CharField(max_length=160, help_text="Generic / descriptive name shown under the brand name.")
    tagline = models.CharField(max_length=120, blank=True)
    summary = models.TextField(blank=True, help_text="Short description used on cards and the product header.")
    dosage_form = models.CharField(max_length=40)
    pack = models.CharField(max_length=80)
    price = models.PositiveIntegerField(
        "Selling price (Rs)", default=0, help_text="Inclusive of all taxes. 0 means not available for online sale."
    )
    mrp = models.PositiveIntegerField("MRP (Rs)", default=0, help_text="Printed MRP. Shown struck through when higher than the selling price.")
    in_stock = models.BooleanField(default=True, help_text="Switched automatically when stock tracking is on.")
    track_inventory = models.BooleanField(default=False, help_text="Sell only what the batches below hold; stops sales at zero and expiry.")
    hsn_code = models.CharField("HSN code", max_length=10, blank=True, help_text="Printed on the tax invoice.")
    gst_rate = models.DecimalField("GST %", max_digits=4, decimal_places=1, default=12, help_text="Tax already included in the selling price.")
    sale_price = models.PositiveIntegerField("Sale price (Rs)", default=0, help_text="Optional. Must be lower than the selling price. 0 means no sale.")
    sale_starts = models.DateTimeField(null=True, blank=True, help_text="Leave empty to start the sale immediately.")
    sale_ends = models.DateTimeField(null=True, blank=True, help_text="Leave empty to run the sale until you clear the sale price.")
    hero_image = models.CharField(max_length=120, blank=True, help_text="Optional artwork for the home slider, e.g. img/hero/npr-hb-syrup.webp")
    composition_title = models.CharField(max_length=80, default="Composition")
    composition = models.TextField(blank=True, help_text="One per line: Ingredient | Strength")
    uses = models.TextField(blank=True, help_text="One per line.")
    how_it_works = models.TextField(blank=True, help_text="One per line: Ingredient | Role")
    dosage = models.TextField(blank=True, help_text="One per line.")
    side_effects = models.TextField(blank=True, help_text="One per line.")
    warnings = models.TextField(blank=True, help_text="One per line.")
    storage = models.TextField(blank=True, help_text="One per line.")
    manufacturer = models.TextField(blank=True, help_text="One per line: Label | Value (e.g. Marketed by | Credit Lifesciences)")
    highlights = models.CharField(max_length=200, blank=True, help_text="Comma-separated short badges.")
    image = models.CharField(max_length=120, help_text="Cover image path under static/, e.g. img/npr-hb.jpg. Extra images are added below.")
    stage = models.CharField(max_length=10, choices=Stage.choices, default=Stage.LIGHT)
    accent = models.CharField(max_length=7, default="#0E7A55", help_text="Hex colour used for this product's accents.")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("product_detail", args=[self.slug])

    @property
    def on_sale(self):
        if not (0 < self.sale_price < self.price):
            return False
        now = timezone.now()
        return (self.sale_starts is None or self.sale_starts <= now) and (self.sale_ends is None or self.sale_ends >= now)

    @property
    def effective_price(self):
        """What the customer actually pays: the sale price while a sale is running, otherwise the normal price."""
        return self.sale_price if self.on_sale else self.price

    @property
    def available_qty(self):
        """Units that can still be sold, or None when stock is not tracked."""
        if not self.track_inventory:
            return None
        return sum(b.quantity for b in self.batches.sellable())

    def refresh_stock_flag(self):
        """Keep in_stock in step with the batches (only for tracked products)."""
        if self.track_inventory:
            flag = self.available_qty > 0
            if flag != self.in_stock:
                Product.objects.filter(pk=self.pk).update(in_stock=flag)
                self.in_stock = flag

    @property
    def sellable(self):
        return (not self.is_rx) and self.price > 0 and self.is_active

    @property
    def discount_pct(self):
        price = self.effective_price
        if self.mrp and self.mrp > price > 0:
            return round((self.mrp - price) * 100 / self.mrp)
        return 0

    @property
    def gallery(self):
        """Cover image first, then any extra images uploaded in the admin."""
        items = [{"url": static(self.image), "alt": f"{self.name} {self.pack}", "fit": "contain" if self.stage == "light" else "cover"}]
        for img in self.images.all():
            items.append({"url": img.image.url, "alt": img.alt or self.name, "fit": img.fit})
        return items

    @cached_property
    def rating_stats(self):
        agg = self.reviews.filter(is_visible=True).aggregate(avg=Avg("rating"), n=Count("id"))
        avg = round(agg["avg"] or 0, 1)
        return {"avg": avg, "count": agg["n"], "pct": round(avg * 20)}


class BatchQuerySet(models.QuerySet):
    def sellable(self):
        """Batches with stock that still have at least MIN_SHELF_LIFE_DAYS of life left."""
        cutoff = timezone.localdate() + timedelta(days=settings.SHOP["min_shelf_life_days"])
        return self.filter(quantity__gt=0, expiry__gte=cutoff)


class Batch(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="batches")
    batch_no = models.CharField(max_length=40)
    mfg_date = models.DateField("Manufactured", null=True, blank=True)
    expiry = models.DateField()
    quantity = models.PositiveIntegerField(default=0, help_text="Units on hand")
    received_at = models.DateField(default=timezone.localdate)

    objects = BatchQuerySet.as_manager()

    class Meta:
        ordering = ["expiry", "id"]  # first expiry, first out
        unique_together = [("product", "batch_no")]
        verbose_name_plural = "batches"

    def __str__(self):
        return f"{self.product.name} / {self.batch_no} (exp {self.expiry:%b %Y})"

    @property
    def days_left(self):
        return (self.expiry - timezone.localdate()).days


class ProductImage(models.Model):
    class Fit(models.TextChoices):
        CONTAIN = "contain", "Contain (shows the whole image)"
        COVER = "cover", "Cover (fills the frame)"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/")
    alt = models.CharField(max_length=140, blank=True)
    fit = models.CharField(max_length=10, choices=Fit.choices, default=Fit.CONTAIN)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.product.name} image {self.order}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from .images import upload_variants  # WebP copies next to the upload, for faster pages
        upload_variants(self.image)


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=100, blank=True)
    body = models.TextField(max_length=1500, blank=True)
    photo = models.ImageField(upload_to="reviews/", blank=True)
    is_visible = models.BooleanField(default=True, help_text="Untick to hide a review from the site.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["product", "user"], name="one_review_per_user_product")]

    @property
    def helpful_count(self):
        return self.votes.count()

    def __str__(self):
        return f"{self.product} - {self.rating}/5 by {self.user}"


def make_referral_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I, which are easy to misread
    while True:
        code = "".join(random.choice(alphabet) for _ in range(7))
        if not Profile.objects.filter(referral_code=code).exists():
            return code


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=10, blank=True)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False, help_text="Set only after a code sent by SMS was entered.")
    referral_code = models.CharField(max_length=10, unique=True, null=True, blank=True, editable=False)
    referred_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class AccountType(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        DISTRIBUTOR = "distributor", "Distributor or stockist"
        CHEMIST = "chemist", "Retail chemist"
        CLINIC = "clinic", "Hospital, clinic or doctor"
        OTHER = "other", "Other business"

    class Kyc(models.TextChoices):
        NONE = "none", "Not submitted"
        PENDING = "pending", "Under review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Needs changes"

    account_type = models.CharField(max_length=12, choices=AccountType.choices, default=AccountType.INDIVIDUAL)
    business_name = models.CharField(max_length=120, blank=True)
    gstin = models.CharField("GSTIN", max_length=15, blank=True)
    drug_licence_no = models.CharField("Drug licence number", max_length=60, blank=True)
    gst_document = models.FileField("GST certificate", upload_to="kyc/", blank=True)
    licence_document = models.FileField("Drug licence copy", upload_to="kyc/", blank=True)
    kyc_status = models.CharField(max_length=10, choices=Kyc.choices, default=Kyc.NONE, db_index=True)
    kyc_note = models.CharField("Note shown to the customer", max_length=300, blank=True)
    kyc_submitted_at = models.DateTimeField(null=True, blank=True)
    kyc_reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Profile of {self.user}"

    @property
    def kyc_approved(self):
        return self.kyc_status == self.Kyc.APPROVED

    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = make_referral_code()
        super().save(*args, **kwargs)


class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=30, default="Home", help_text="e.g. Home, Work")
    name = models.CharField("Full name", max_length=100)
    phone = models.CharField(max_length=10)
    address = models.TextField("Full address")
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=60)
    pincode = models.CharField(max_length=6)
    is_default = models.BooleanField("Make this my default address", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]
        verbose_name_plural = "addresses"

    def __str__(self):
        return f"{self.label}: {self.name}, {self.city} {self.pincode}"

    def save(self, *args, **kwargs):
        if not self.is_default and not Address.objects.filter(user=self.user).exclude(pk=self.pk).exists():
            self.is_default = True  # the first address is always the default
        super().save(*args, **kwargs)
        if self.is_default:
            Address.objects.filter(user=self.user).exclude(pk=self.pk).update(is_default=False)


class Wishlist(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="unique_wishlist_item")]

    def __str__(self):
        return f"{self.user} - {self.product}"


class Enquiry(models.Model):
    class Kind(models.TextChoices):
        CUSTOMER = "customer", "Customer / General"
        DISTRIBUTOR = "distributor", "Distributor / Stockist"
        FRANCHISE = "franchise", "PCD / Franchise partner"
        DOCTOR = "doctor", "Doctor / Hospital / Clinic"
        PHARMACY = "pharmacy", "Pharmacy / Chemist"
        OTHER = "other", "Other"

    class Topic(models.TextChoices):
        PRODUCT = "product", "Product Enquiry"
        ORDER = "order", "Order Enquiry"
        PARTNERSHIP = "partnership", "Business Partnership"
        GENERAL = "general", "General Query"
        COMPLAINT = "complaint", "Complaint"

    name = models.CharField(max_length=100)
    organisation = models.CharField(max_length=140, blank=True)
    topic = models.CharField("Enquiry type", max_length=12, choices=Topic.choices, default=Topic.GENERAL)
    kind = models.CharField("I am a", max_length=20, choices=Kind.choices, default=Kind.CUSTOMER)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    city = models.CharField("City / State", max_length=100)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="enquiries")
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    handled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "enquiries"

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()}) - {self.created_at:%d %b %Y}"


class Subscriber(models.Model):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=40, blank=True, default="footer")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email


def make_order_number():
    while True:
        number = "CL" + timezone.localdate().strftime("%y%m%d") + f"{random.randint(0, 9999):04d}"
        if not Order.objects.filter(number=number).exists():
            return number


class Order(models.Model):
    class Status(models.TextChoices):
        PLACED = "placed", "Order placed"
        CONFIRMED = "confirmed", "Confirmed"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class Payment(models.TextChoices):
        COD = "cod", "Cash on delivery"
        ONLINE = "online", "Online payment"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Payment pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Payment failed"
        REFUNDED = "refunded", "Refunded"
        COD = "cod", "Pay on delivery"

    number = models.CharField(max_length=16, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=10)
    email = models.EmailField(blank=True)
    address = models.TextField("Full address")
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=60)
    pincode = models.CharField(max_length=6)
    notes = models.TextField("Order notes", blank=True)
    payment_method = models.CharField(max_length=10, choices=Payment.choices, default=Payment.COD)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLACED)
    subtotal = models.PositiveIntegerField(default=0)
    shipping = models.PositiveIntegerField(default=0)
    discount = models.PositiveIntegerField(default=0)
    coupon_code = models.CharField(max_length=30, blank=True)
    total = models.PositiveIntegerField(default=0)
    payment_status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.COD)
    razorpay_order_id = models.CharField(max_length=40, blank=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=40, blank=True)
    payment_error = models.CharField(max_length=300, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    refund_id = models.CharField(max_length=40, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    courier = models.CharField(max_length=40, blank=True)
    awb = models.CharField("AWB / tracking number", max_length=40, blank=True, db_index=True)
    tracking_url = models.URLField(blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    expected_delivery = models.DateField(null=True, blank=True)
    points_used = models.PositiveIntegerField(default=0, editable=False)
    bundle_discount = models.PositiveIntegerField(default=0, editable=False)
    invoice_no = models.CharField(max_length=20, blank=True, editable=False)
    stock_released = models.BooleanField(default=False, editable=False)
    tracking_note = models.CharField("Courier / tracking note", max_length=200, blank=True, help_text="Shown to the customer on the tracking page and in status emails.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = make_order_number()
        super().save(*args, **kwargs)

    @property
    def points_discount(self):
        return self.points_used * settings.SHOP["point_value"]

    @property
    def total_discount(self):
        """Coupon + bundle + credit points: everything taken off the items' price."""
        return self.discount + self.bundle_discount + self.points_discount

    @property
    def can_cancel(self):
        return self.status in (self.Status.PLACED, self.Status.CONFIRMED)

    @property
    def awaiting_payment(self):
        return (
            self.payment_method == self.Payment.ONLINE
            and self.payment_status in (self.PaymentStatus.PENDING, self.PaymentStatus.FAILED)
            and self.status != self.Status.CANCELLED
        )

    @property
    def paid_online(self):
        return self.payment_method == self.Payment.ONLINE and self.payment_status == self.PaymentStatus.PAID


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL)
    product_name = models.CharField(max_length=80)
    pack = models.CharField(max_length=80, blank=True)
    unit_price = models.PositiveIntegerField()
    quantity = models.PositiveSmallIntegerField()
    hsn_code = models.CharField(max_length=10, blank=True)
    gst_rate = models.DecimalField(max_digits=4, decimal_places=1, default=12)

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class StockMovement(models.Model):
    """Every change to on-hand stock, so the numbers can always be explained."""
    class Reason(models.TextChoices):
        RECEIVED = "received", "Stock received"
        SALE = "sale", "Sold on an order"
        CANCEL = "cancel", "Order cancelled, stock returned"
        REPLACEMENT = "replacement", "Replacement sent"
        ADJUSTMENT = "adjustment", "Manual correction"
        DAMAGED = "damaged", "Damaged or expired, written off"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="movements")
    batch = models.ForeignKey("Batch", null=True, blank=True, on_delete=models.SET_NULL, related_name="movements")
    change = models.IntegerField(help_text="Plus adds stock, minus removes it")
    reason = models.CharField(max_length=12, choices=Reason.choices)
    reference = models.CharField(max_length=40, blank=True)
    note = models.CharField(max_length=200, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.product} {self.change:+d} ({self.get_reason_display()})"


def log_stock(product, change, reason, batch=None, reference="", note="", user=None):
    return StockMovement.objects.create(product=product, batch=batch, change=change, reason=reason, reference=reference, note=note[:200], user=user)


class OrderAllocation(models.Model):
    """Which batch each unit of an order line came from, so cancelling puts stock back where it belongs."""
    item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="allocations")
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="allocations")
    quantity = models.PositiveIntegerField()


class TrackingEvent(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=80)
    location = models.CharField(max_length=80, blank=True)
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return f"{self.order.number}: {self.status}"


# --------------------------------------------------------------------- offers

class Coupon(models.Model):
    class Kind(models.TextChoices):
        PERCENT = "percent", "Percentage off"
        FLAT = "flat", "Flat amount off (Rs)"

    code = models.CharField(max_length=30, unique=True, help_text="Customers type this at checkout. Saved in capitals.")
    description = models.CharField(max_length=140, blank=True, help_text="Shown with the code, e.g. 'Flat 10% off on your first order'.")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PERCENT)
    value = models.PositiveIntegerField(help_text="Percent (1-100) or rupees, depending on the type.")
    min_order = models.PositiveIntegerField("Minimum order (Rs)", default=0)
    max_discount = models.PositiveIntegerField("Maximum discount (Rs)", default=0, help_text="Cap for percentage coupons. 0 means no cap.")
    free_shipping = models.BooleanField(default=False, help_text="Also waives the delivery charge.")
    first_order_only = models.BooleanField(default=False)
    usage_limit = models.PositiveIntegerField(default=0, help_text="Total times the code can be used. 0 means unlimited.")
    per_user_limit = models.PositiveIntegerField(default=1, help_text="Times one customer can use it. 0 means unlimited.")
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    public = models.BooleanField(default=False, help_text="Show this offer to customers in the cart and checkout.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)

    @property
    def headline(self):
        if self.kind == self.Kind.PERCENT:
            text = f"{self.value}% off"
            if self.max_discount:
                text += f" up to Rs {self.max_discount}"
        else:
            text = f"Rs {self.value} off"
        if self.min_order:
            text += f" on orders above Rs {self.min_order}"
        return text

    def times_used(self):
        return self.redemptions.count()

    def evaluate(self, subtotal, user=None, email="", phone="", now=None):
        """Return (discount_in_rupees, error_message_or_None). Never raises."""
        now = now or timezone.now()
        if not self.active:
            return 0, "This coupon is not active."
        if self.starts_at and now < self.starts_at:
            return 0, "This coupon is not valid yet."
        if self.ends_at and now > self.ends_at:
            return 0, "This coupon has expired."
        if subtotal < self.min_order:
            return 0, f"Add items worth Rs {self.min_order - subtotal} more to use this coupon (minimum order Rs {self.min_order})."
        if self.usage_limit and self.redemptions.count() >= self.usage_limit:
            return 0, "This coupon has reached its usage limit."

        authed = user is not None and getattr(user, "is_authenticated", False)
        who = Q(pk__in=[])  # matches nothing until we know something about the customer
        if authed:
            who |= Q(user=user)
            email = email or user.email
        if email:
            who |= Q(email__iexact=email)
        if phone:
            who |= Q(phone=phone)
        known = authed or bool(email) or bool(phone)
        if known and self.per_user_limit and self.redemptions.filter(who).count() >= self.per_user_limit:
            return 0, "You have already used this coupon."
        if known and self.first_order_only:
            order_who = Q(pk__in=[])
            if authed:
                order_who |= Q(user=user)
            if email:
                order_who |= Q(email__iexact=email)
            if phone:
                order_who |= Q(phone=phone)
            if Order.objects.exclude(status=Order.Status.CANCELLED).filter(order_who).exists():
                return 0, "This coupon is only valid on your first order."

        if self.kind == self.Kind.PERCENT:
            discount = subtotal * min(self.value, 100) // 100
            if self.max_discount:
                discount = min(discount, self.max_discount)
        else:
            discount = self.value
        discount = max(0, min(discount, subtotal))
        if discount == 0 and not self.free_shipping:
            return 0, "This coupon does not apply to your cart."
        return discount, None


class CouponRedemption(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name="redemptions")
    order = models.OneToOneField("Order", on_delete=models.CASCADE, related_name="redemption")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=10, blank=True)
    discount = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.coupon.code} on {self.order.number}"


class Announcement(models.Model):
    """Messages that rotate in the bar at the very top of the site."""
    text = models.CharField(max_length=140)
    link = models.CharField(max_length=200, blank=True, help_text="Optional page, e.g. /shop/?sale=1")
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text


# ------------------------------------------------------------------------ OTP

class OTP(models.Model):
    class Purpose(models.TextChoices):
        LOGIN = "login", "Sign in"
        SIGNUP = "signup", "Create account"
        RESET = "reset", "Reset password"
        VERIFY = "verify", "Verify email"
        PHONE_LOGIN = "plogin", "Sign in with mobile"
        PHONE_VERIFY = "pverify", "Verify mobile"

    email = models.EmailField(db_index=True)
    purpose = models.CharField(max_length=10, choices=Purpose.choices)
    code_hash = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["email", "purpose", "-created_at"])]

    def __str__(self):
        return f"{self.get_purpose_display()} code for {self.email}"


# =============================================================== Sprint B models

class SavedCart(models.Model):
    """A signed-in customer's cart, kept on the server so it follows them across devices and can be reminded about."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_cart")
    data = models.JSONField(default=dict)  # {product slug: qty}
    updated_at = models.DateTimeField(auto_now=True)
    reminded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Cart of {self.user}"


class ProductFAQ(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="faqs")
    question = models.CharField(max_length=200)
    answer = models.TextField()
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "product FAQ"

    def __str__(self):
        return self.question


class CategoryPage(models.Model):
    """SEO landing copy for one product category (key matches Product.Category)."""
    category = models.CharField(max_length=20, choices=Product.Category.choices, unique=True)
    heading = models.CharField(max_length=120)
    intro = models.CharField(max_length=300, blank=True)
    body = models.TextField(blank=True, help_text="Paragraphs separated by a blank line. Start a line with ## for a sub-heading.")
    meta_description = models.CharField(max_length=160, blank=True)

    def __str__(self):
        return self.heading

    def get_absolute_url(self):
        return reverse("category", args=[self.category])


class Article(models.Model):
    title = models.CharField(max_length=140)
    slug = models.SlugField(unique=True)
    summary = models.CharField(max_length=300)
    body = models.TextField(help_text="Paragraphs separated by a blank line. Start a line with ## for a sub-heading.")
    meta_description = models.CharField(max_length=160, blank=True)
    cover = models.ImageField(upload_to="blog/", blank=True)
    is_published = models.BooleanField(default=False, help_text="Drafts are visible to staff only.")
    published_at = models.DateTimeField(default=timezone.now)
    author = models.CharField(max_length=80, default="Credit Lifesciences team")

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("article", args=[self.slug])


class ReturnRequest(models.Model):
    class Reason(models.TextChoices):
        DAMAGED = "damaged", "Arrived damaged or leaking"
        WRONG = "wrong", "Wrong item received"
        EXPIRY = "expiry", "Near or past expiry on arrival"
        MISSING = "missing", "Item missing from the parcel"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        APPROVED = "approved", "Approved"
        PICKUP = "pickup", "Pickup arranged"
        RECEIVED = "received", "Received and checked"
        REJECTED = "rejected", "Not approved"
        WITHDRAWN = "withdrawn", "Withdrawn"
        RESOLVED = "resolved", "Resolved"

    class Resolution(models.TextChoices):
        REPLACEMENT = "replacement", "Replacement"
        REFUND = "refund", "Refund"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="returns")
    item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="returns")
    quantity = models.PositiveSmallIntegerField(default=1)
    reason = models.CharField(max_length=10, choices=Reason.choices)
    details = models.TextField(blank=True)
    photo = models.ImageField(upload_to="returns/", blank=True)
    video = models.FileField("Unboxing video", upload_to="returns/video/", blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED)
    resolution = models.CharField(max_length=12, choices=Resolution.choices, blank=True)
    staff_note = models.CharField(max_length=300, blank=True, help_text="Shown to the customer.")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    reference = models.CharField(max_length=14, blank=True, db_index=True, editable=False)
    pickup_courier = models.CharField(max_length=60, blank=True)
    pickup_awb = models.CharField("Pickup tracking number", max_length=60, blank=True)
    pickup_date = models.DateField(null=True, blank=True)
    refund_amount = models.PositiveIntegerField(default=0, help_text="Rupees. Leave 0 to use the value of the returned units.")
    refund_id = models.CharField(max_length=60, blank=True, editable=False)
    refunded_at = models.DateTimeField(null=True, blank=True, editable=False)
    replacement_courier = models.CharField(max_length=60, blank=True)
    replacement_awb = models.CharField("Replacement tracking number", max_length=60, blank=True)
    replacement_stock_taken = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Return {self.reference or self.pk} for {self.order.number}: {self.item.product_name}"

    def save(self, *args, **kwargs):
        if not self.reference:
            import secrets
            self.reference = "RR-" + "".join(secrets.choice("0123456789") for _ in range(7))
        super().save(*args, **kwargs)

    @property
    def refund_value(self):
        return self.refund_amount or self.item.unit_price * self.quantity

    @property
    def can_withdraw(self):
        return self.status in (self.Status.REQUESTED, self.Status.APPROVED)

    @property
    def is_open(self):
        return self.status not in (self.Status.REJECTED, self.Status.WITHDRAWN, self.Status.RESOLVED)


class ReturnEvent(models.Model):
    """One line of a return's timeline, shown to the customer."""
    request = models.ForeignKey(ReturnRequest, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=10)
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    @property
    def label(self):
        return dict(ReturnRequest.Status.choices).get(self.status, self.status.title())


class EmailJob(models.Model):
    """Outgoing email waiting for the background worker (used when EMAIL_QUEUE=1)."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    to = models.JSONField()
    subject = models.CharField(max_length=255)
    text = models.TextField()
    html = models.TextField(blank=True)
    reply_to = models.JSONField(default=list)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    run_after = models.DateTimeField(default=timezone.now, db_index=True)
    last_error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]


# =============================================================== Sprint C models

class Bundle(models.Model):
    """Buy these together and pay `price` for each complete set. Applied automatically in the cart."""
    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    description = models.CharField(max_length=240, blank=True)
    price = models.PositiveIntegerField("Bundle price (Rs) for one set", help_text="Must be lower than the normal prices of its items added up.")
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name

    @cached_property
    def lines(self):
        return list(self.items.select_related("product"))

    @property
    def regular_price(self):
        return sum(i.product.effective_price * i.quantity for i in self.lines)

    @property
    def saving(self):
        return max(0, self.regular_price - self.price)

    @property
    def valid(self):
        return bool(self.lines) and self.is_active and all(i.product.sellable and i.product.in_stock for i in self.lines) and self.saving > 0


class BundleItem(models.Model):
    bundle = models.ForeignKey(Bundle, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveSmallIntegerField(default=1)

    class Meta:
        unique_together = [("bundle", "product")]


class LoyaltyEntry(models.Model):
    """Credit points ledger. The balance is the sum of `points` (spending is negative)."""
    class Kind(models.TextChoices):
        EARN = "earn", "Earned on an order"
        REDEEM = "redeem", "Used at checkout"
        REFUND = "refund", "Returned (order cancelled)"
        REFERRAL = "referral", "Referral reward"
        ADJUST = "adjust", "Manual adjustment"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="loyalty")
    points = models.IntegerField()
    kind = models.CharField(max_length=10, choices=Kind.choices)
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="loyalty")
    note = models.CharField(max_length=140, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # an order earns, spends and returns points at most once each, even if two requests race
            models.UniqueConstraint(
                fields=["order", "kind"], condition=Q(order__isnull=False) & Q(kind__in=["earn", "redeem", "refund"]),
                name="one_loyalty_entry_per_order_kind"),
        ]

    def __str__(self):
        return f"{self.user}: {self.points:+d} ({self.kind})"


class Subscription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        CANCELLED = "cancelled", "Cancelled"

    INTERVALS = [(30, "Every month"), (45, "Every 6 weeks"), (60, "Every 2 months"), (90, "Every 3 months")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="subscriptions")
    quantity = models.PositiveSmallIntegerField(default=1)
    interval_days = models.PositiveSmallIntegerField(choices=INTERVALS, default=30)
    address = models.ForeignKey(Address, null=True, blank=True, on_delete=models.SET_NULL)
    next_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    last_order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reminded_for = models.DateField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["next_date"]

    def __str__(self):
        return f"{self.user}: {self.quantity} x {self.product} {self.get_interval_days_display().lower()}"

    @property
    def unit_price(self):
        pct = settings.SHOP["subscribe_discount_pct"]
        return round(self.product.effective_price * (100 - pct) / 100)


class ReviewVote(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        unique_together = [("review", "user")]


class ProductQuestion(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="questions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    question = models.CharField(max_length=300)
    answer = models.TextField(blank=True, help_text="Your answer. Questions without an answer are hidden from the public.")
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-answered_at", "-created_at"]

    def __str__(self):
        return self.question[:60]


class Banner(models.Model):
    """Promotional banner shown on the home page (below the hero)."""
    title = models.CharField(max_length=80)
    subtitle = models.CharField(max_length=140, blank=True)
    image = models.ImageField(upload_to="banners/", blank=True, help_text="Optional. 1200 x 400 works well.")
    link = models.CharField(max_length=200, blank=True, help_text="Page to open, e.g. /shop/?sale=1")
    button_text = models.CharField(max_length=30, default="Shop now")
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class Page(models.Model):
    """Simple content page managed in the admin (served at /p/<slug>/)."""
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=120)
    body = models.TextField(help_text="Paragraphs separated by a blank line. Start a line with ## for a sub-heading.")
    meta_description = models.CharField(max_length=160, blank=True)
    is_published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("cms_page", args=[self.slug])


# ========================================================== B2B site models (content brief, Nov 2026)

class DistributorEnquiry(models.Model):
    """Application to become an authorised distributor. Submitting it grants nothing by itself."""
    class Status(models.TextChoices):
        NEW = "new", "New"
        CONTACTED = "contacted", "Contacted"
        QUALIFIED = "qualified", "Qualified"
        CLOSED = "closed", "Closed"

    full_name = models.CharField(max_length=100)
    firm_name = models.CharField("Company / firm name", max_length=140)
    mobile = models.CharField(max_length=20)
    email = models.EmailField()
    state = models.CharField(max_length=60)
    district = models.CharField(max_length=60)
    gst_number = models.CharField("GST number", max_length=15)
    licence_number = models.CharField("Wholesale drug licence number (Form 20B / 21B)", max_length=60, blank=True)
    experience_years = models.PositiveSmallIntegerField("Years of experience in pharmaceutical distribution", default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    notes = models.TextField("Internal notes", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "distributor enquiries"

    def __str__(self):
        return f"{self.firm_name} ({self.district}, {self.state})"


class CareerApplication(models.Model):
    ROLES = [
        ("Medical Representative", "Medical Representatives"), ("Sales Executive", "Sales Executives"),
        ("Area Sales Manager", "Area Sales Managers"), ("Distribution and Operations", "Distribution and Operations"),
        ("Office Administration", "Office Administration"), ("Content Creation", "Content Creation"), ("Marketing", "Marketing"),
    ]
    full_name = models.CharField(max_length=100)
    mobile = models.CharField(max_length=20)
    email = models.EmailField()
    location = models.CharField("Current location (city / district / state)", max_length=120)
    position = models.CharField("Position applied for", max_length=80)
    experience_years = models.PositiveSmallIntegerField("Years of experience", default=0)
    qualification = models.CharField("Educational qualification", max_length=140)
    resume = models.FileField("Resume / CV", upload_to="careers/")
    message = models.TextField("Short introduction", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    handled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} - {self.position}"


class District(models.Model):
    """One place on the distribution map. The company sets and updates each status."""
    class Status(models.TextChoices):
        ACTIVE = "active", "Active location"
        OPEN = "open", "Open for appointment"
        UPCOMING = "upcoming", "Upcoming location"

    name = models.CharField(max_length=60)
    state = models.CharField(max_length=60, default="Uttar Pradesh")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        unique_together = [("name", "state")]

    def __str__(self):
        return f"{self.name}, {self.state} ({self.get_status_display()})"


class DistributorListing(models.Model):
    """Public distributor directory entry. Shown only after the distributor has given consent."""
    firm_name = models.CharField(max_length=140)
    address = models.CharField("Address / market area", max_length=200, blank=True)
    contact_person = models.CharField(max_length=100, blank=True)
    mobile = models.CharField("Mobile number(s)", max_length=40, blank=True)
    district = models.CharField(max_length=60)
    state = models.CharField(max_length=60, default="Uttar Pradesh")
    consent_given = models.BooleanField(default=False, help_text="Tick only after the distributor has agreed (in writing) to publish these details.")
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering = ["state", "district", "firm_name"]

    def __str__(self):
        return self.firm_name

    @property
    def visible(self):
        return self.consent_given and self.is_published

    @property
    def mobile_list(self):
        return [n.strip() for n in self.mobile.replace(",", "/").split("/") if n.strip()]


class HeroSlide(models.Model):
    """One rotating full-screen slide at the top of the home page (managed in the admin)."""
    eyebrow = models.CharField(max_length=80, blank=True, help_text="Small line above the headline.")
    headline = models.CharField(max_length=160)
    text = models.TextField(blank=True, help_text="Supporting copy under the headline.")
    primary_label = models.CharField("Main button text", max_length=40, blank=True)
    primary_url = models.CharField("Main button link", max_length=200, blank=True, help_text="e.g. /become-a-distributor/")
    secondary_label = models.CharField("Second button text", max_length=40, blank=True)
    secondary_url = models.CharField("Second button link", max_length=200, blank=True)
    image = models.ImageField("Background image", upload_to="hero/", blank=True,
                              help_text="Optional. 1920 x 1080 or larger, landscape. Leave empty to use the built-in artwork below.")
    default_background = models.CharField(max_length=80, blank=True, default="img/hero/bg-1.jpg",
                                          help_text="Built-in artwork used when no image is uploaded, e.g. img/hero/bg-3.jpg (bg-1 to bg-6).")
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.headline

    @property
    def background_url(self):
        if self.image:
            return self.image.url
        return static(self.default_background or "img/hero/bg-1.jpg")


# ================================================== fully editable website content (Admin > Website content)

class SiteSettings(models.Model):
    """Company details shown across the site. There is only one row; leave a field blank to use the built-in default."""
    company_name = models.CharField(max_length=80, blank=True)
    tagline = models.CharField(max_length=80, blank=True, help_text="Stays in English in the Hindi version too.")
    established = models.PositiveSmallIntegerField(default=2009, help_text="The 'years' figure is worked out from this every year.")
    founder_name = models.CharField(max_length=80, blank=True)
    phone = models.CharField("Phone / customer support", max_length=30, blank=True)
    whatsapp = models.CharField("WhatsApp number", max_length=20, blank=True, help_text="Digits with country code, e.g. 919936360600")
    email = models.EmailField("Official email", blank=True)
    sales_email = models.EmailField("Sales / business enquiry email", blank=True)
    careers_email = models.EmailField("HR / careers email", blank=True, help_text="Job applications go here; blank = the enquiry addresses.")
    enquiry_recipients = models.TextField("Who receives enquiry and order alerts", blank=True, help_text="One email per line.")
    address = models.TextField("Registered office", blank=True)
    website = models.CharField(max_length=80, blank=True)
    facebook = models.URLField(blank=True)
    instagram = models.URLField(blank=True)
    youtube = models.URLField(blank=True)
    twitter = models.URLField("X (Twitter)", blank=True)
    threads = models.URLField(blank=True)
    linkedin = models.URLField(blank=True)
    overview = models.TextField("Company overview (About page)", blank=True)
    vision = models.CharField(max_length=300, blank=True)
    mission = models.TextField(blank=True, help_text="One point per line.")
    min_purchase = models.CharField("Minimum initial purchase (Rs)", max_length=20, blank=True, help_text="Shown on the Become a Distributor page and in the FAQs, e.g. 5,00,000")

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self):
        return "Site settings"


class TeamMessage(models.Model):
    """A signed message from the founder, director or anyone else, shown on the About page (and teased on the home page)."""
    name = models.CharField(max_length=80)
    designation = models.CharField(max_length=140)
    heading = models.CharField(max_length=140, help_text="e.g. Founder & CEO's Message")
    subheading = models.CharField(max_length=200, blank=True)
    body = models.TextField(help_text="Paragraphs separated by a blank line. Put **double stars** around words to make them bold.")
    photo = models.ImageField(upload_to="team/", blank=True, help_text="Optional portrait, square works best. Initials are shown without one.")
    show_on_home = models.BooleanField("Show a short extract on the home page", default=False)
    is_published = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.heading} ({self.name})"

    @property
    def initials(self):
        return "".join(w[0] for w in self.name.split()[:2]).upper()

    @property
    def extract(self):
        first = (self.body or "").strip().split("\n\n")[0].replace("**", "")
        return first if len(first) < 340 else first[:337].rsplit(" ", 1)[0] + "..."


class FAQ(models.Model):
    question = models.CharField(max_length=240)
    answer = models.TextField(help_text="You can use {phone}, {email} and {sales_email}; they are filled in from Site settings.")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "FAQ"

    def __str__(self):
        return self.question


class JobRole(models.Model):
    title = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=240, blank=True)
    is_open = models.BooleanField("Accepting applications", default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.title


class Highlight(models.Model):
    """Small icon cards: 'why choose us' on the home page, core values and guiding principles on the About page."""
    class Kind(models.TextChoices):
        WHY = "why", "Why choose us (home page)"
        VALUE = "value", "Core value (About page)"
        PRINCIPLE = "principle", "Guiding principle (About page)"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=100)
    text = models.CharField(max_length=300, blank=True)
    icon = models.CharField(max_length=40, default="bi-patch-check", help_text="A Bootstrap Icons name, e.g. bi-shield-check (see icons.getbootstrap.com)")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "order", "id"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"


class TimelineItem(models.Model):
    period = models.CharField(max_length=60, help_text="e.g. 2009, Over the years, Present")
    text = models.CharField(max_length=300)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.period}: {self.text[:40]}"
