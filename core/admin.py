from django.contrib import admin, messages
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from . import bulk, orders as order_service, shipping
from .views_ops import invoice_url
from .models import (
    ReturnEvent, StockMovement, log_stock,
    FAQ, Address, Announcement, Article, CareerApplication, Highlight, HeroSlide, JobRole, SiteSettings, TeamMessage, TimelineItem, District, DistributorEnquiry, DistributorListing, Banner, Batch, Bundle, BundleItem, LoyaltyEntry, Page, ProductQuestion, ReviewVote, Subscription, CategoryPage, EmailJob, ProductFAQ, ReturnRequest, SavedCart, Coupon, CouponRedemption, Enquiry, Order, OrderItem, Product, ProductImage, Profile, Review,
    Subscriber, TrackingEvent, Wishlist,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "alt", "fit", "order")


class FAQInline(admin.StackedInline):
    model = ProductFAQ
    extra = 1


class BatchInline(admin.TabularInline):
    model = Batch
    extra = 0
    fields = ("batch_no", "mfg_date", "expiry", "quantity", "received_at")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "system", "category", "is_rx", "pack", "mrp", "price", "sale_price", "sale_ends", "in_stock", "stock", "order", "is_active")
    list_filter = ("system", "category", "is_rx", "in_stock", "is_active", "track_inventory")
    list_editable = ("mrp", "price", "sale_price", "in_stock", "order", "is_active")
    search_fields = ("name", "subtitle", "composition")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline, BatchInline, FAQInline]
    change_list_template = "admin/product_changelist.html"

    def get_urls(self):
        return [path("import/", self.admin_site.admin_view(self.import_view), name="core_product_import")] + super().get_urls()

    def import_view(self, request):
        if not self.has_change_permission(request):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        ctx = {**self.admin_site.each_context(request), "title": "Import prices and stock", "done": False}
        if request.method == "POST" and request.FILES.get("file"):
            dry = bool(request.POST.get("dry_run"))
            changes, errors = bulk.import_products(request.FILES["file"], dry_run=dry)
            ctx.update(done=True, changes=changes, errors=errors, dry_run=dry)
        return render(request, "admin/import_products.html", ctx)

    @admin.display(description="Stock")
    def stock(self, obj):
        qty = obj.available_qty
        return "not tracked" if qty is None else qty


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("product", "batch_no", "expiry", "days_left", "quantity", "received_at")
    list_filter = ("product",)
    search_fields = ("batch_no", "product__name")
    date_hierarchy = "expiry"

    def save_model(self, request, obj, form, change):
        old = Batch.objects.filter(pk=obj.pk).values_list("quantity", flat=True).first() if change else 0
        super().save_model(request, obj, form, change)
        delta = obj.quantity - (old or 0)
        if delta:
            log_stock(obj.product, delta, StockMovement.Reason.ADJUSTMENT if change else StockMovement.Reason.RECEIVED, batch=obj, user=request.user,
                      note="Edited in the batch form")
        obj.product.refresh_stock_flag()


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "product", "batch", "change", "reason", "reference", "user")
    list_filter = ("reason", "product")
    search_fields = ("product__name", "reference", "batch__batch_no", "note")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "title", "is_visible", "created_at")
    list_filter = ("rating", "is_visible", "product")
    list_editable = ("is_visible",)
    search_fields = ("title", "body", "user__email")
    readonly_fields = ("created_at",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "business_name", "account_type", "phone", "kyc_status", "email_verified", "created_at")
    list_filter = ("kyc_status", "account_type", "email_verified")
    search_fields = ("user__email", "user__first_name", "phone", "business_name", "gstin", "drug_licence_no")
    readonly_fields = ("kyc_submitted_at", "kyc_reviewed_at", "created_at")
    fieldsets = (
        ("Customer", {"fields": ("user", "phone", "email_verified", "phone_verified", "created_at")}),
        ("Business", {"fields": ("account_type", "business_name", "gstin", "drug_licence_no", "gst_document", "licence_document")}),
        ("Verification", {"fields": ("kyc_status", "kyc_note", "kyc_submitted_at", "kyc_reviewed_at")}),
    )
    actions = ["approve_kyc", "reject_kyc"]

    def _decide(self, request, queryset, status):
        from . import emails
        n = 0
        for prof in queryset.exclude(kyc_status=status):
            prof.kyc_status, prof.kyc_reviewed_at = status, timezone.now()
            prof.save()
            emails.send_kyc_decision(prof.user)
            n += 1
        self.message_user(request, f"{n} account(s) updated and customers emailed.")

    @admin.action(description="Approve business verification (emails customer)")
    def approve_kyc(self, request, queryset):
        self._decide(request, queryset, Profile.Kyc.APPROVED)

    @admin.action(description="Ask for changes (write the reason in 'Note shown to the customer' first)")
    def reject_kyc(self, request, queryset):
        self._decide(request, queryset, Profile.Kyc.REJECTED)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "label", "name", "city", "pincode", "is_default")
    search_fields = ("user__email", "name", "pincode")


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "organisation", "phone", "city", "product", "created_at", "handled")
    list_filter = ("kind", "handled", "product")
    list_editable = ("handled",)
    search_fields = ("name", "organisation", "phone", "email", "city", "message")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("product", "product_name", "pack", "unit_price", "quantity", "hsn_code", "gst_rate")


class TrackingEventInline(admin.TabularInline):
    model = TrackingEvent
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "phone", "city", "total", "payment_method", "payment_status", "status", "awb", "invoice_link", "created_at")
    list_filter = ("status", "payment_method", "payment_status", "state")
    list_editable = ("status",)
    search_fields = ("number", "name", "phone", "email", "pincode")
    date_hierarchy = "created_at"
    inlines = [OrderItemInline, TrackingEventInline]
    readonly_fields = (
        "invoice_no", "shipped_at", "delivered_at", "number", "user", "subtotal", "discount", "coupon_code", "shipping", "total", "payment_status", "razorpay_order_id",
        "razorpay_payment_id", "payment_error", "paid_at", "refund_id", "refunded_at", "created_at", "updated_at",
    )
    actions = ["mark_confirmed", "mark_shipped", "mark_delivered", "mark_cancelled", "refund_paid_orders", "create_shipments"]

    @admin.display(description="Invoice")
    def invoice_link(self, obj):
        if obj.status == Order.Status.CANCELLED:
            return "-"
        return format_html('<a href="{}" target="_blank">PDF</a>', invoice_url(obj))

    @admin.action(description="Create courier shipment (AWB) for selected orders")
    def create_shipments(self, request, queryset):
        done, errors = 0, []
        for order in queryset.exclude(status=Order.Status.CANCELLED).filter(awb=""):
            try:
                shipping.create_shipment(order)
                done += 1
            except (shipping.CourierError, Exception) as exc:  # noqa: BLE001 - show every failure to staff
                errors.append(f"{order.number}: {exc}")
        self.message_user(request, f"{done} shipment(s) created." + (" Problems: " + "; ".join(errors) if errors else ""))

    def _set_status(self, request, queryset, status):
        # Save one by one (not queryset.update) so the status-change email is sent to each customer.
        count = 0
        for order in queryset:
            if order.status != status:
                order.status = status
                order.save()
                count += 1
        self.message_user(request, f"{count} order(s) updated and customers emailed.")

    @admin.action(description="Mark as Confirmed (emails customers)")
    def mark_confirmed(self, request, queryset):
        self._set_status(request, queryset, Order.Status.CONFIRMED)

    @admin.action(description="Mark as Shipped (emails customers)")
    def mark_shipped(self, request, queryset):
        self._set_status(request, queryset, Order.Status.SHIPPED)

    @admin.action(description="Mark as Delivered (emails customers)")
    def mark_delivered(self, request, queryset):
        self._set_status(request, queryset, Order.Status.DELIVERED)

    @admin.action(description="Mark as Cancelled (emails customers)")
    def mark_cancelled(self, request, queryset):
        self._set_status(request, queryset, Order.Status.CANCELLED)


    @admin.action(description="Cancel and refund (paid online orders are refunded through Razorpay)")
    def refund_paid_orders(self, request, queryset):
        done = failed = 0
        for order in queryset.exclude(status=Order.Status.CANCELLED):
            outcome = order_service.cancel_order(order)
            if outcome == "refund_failed":
                failed += 1
            else:
                done += 1
        self.message_user(request, f"{done} order(s) cancelled" + (f", {failed} need a manual refund in the Razorpay dashboard." if failed else "."))


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "is_active", "source", "created_at")
    list_filter = ("is_active", "source")
    search_fields = ("email",)
    readonly_fields = ("created_at",)



@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "headline", "active", "public", "first_order_only", "usage", "per_user_limit", "ends_at")
    list_filter = ("active", "public", "kind", "first_order_only")
    list_editable = ("active", "public")
    search_fields = ("code", "description")
    actions = ["activate", "deactivate"]

    @admin.display(description="Used")
    def usage(self, obj):
        return f"{obj.times_used()} / {obj.usage_limit or 'unlimited'}"

    @admin.action(description="Activate selected coupons")
    def activate(self, request, queryset):
        queryset.update(active=True)

    @admin.action(description="Deactivate selected coupons")
    def deactivate(self, request, queryset):
        queryset.update(active=False)


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon", "order", "discount", "email", "created_at")
    list_filter = ("coupon",)
    search_fields = ("order__number", "email", "phone")
    readonly_fields = ("coupon", "order", "user", "email", "phone", "discount", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("text", "link", "is_active", "order")
    list_editable = ("is_active", "order")


@admin.register(CategoryPage)
class CategoryPageAdmin(admin.ModelAdmin):
    list_display = ("category", "heading")


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "is_published", "published_at", "author")
    list_filter = ("is_published",)
    list_editable = ("is_published",)
    search_fields = ("title", "summary", "body")
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_at"


class ReturnEventInline(admin.TabularInline):
    model = ReturnEvent
    extra = 0
    can_delete = False
    readonly_fields = ("status", "note", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "order", "item", "quantity", "status", "resolution", "refund_state", "created_at")
    list_filter = ("status", "resolution", "reason")
    search_fields = ("reference", "order__number", "order__phone", "item__product_name", "pickup_awb", "replacement_awb")
    readonly_fields = ("reference", "order", "item", "quantity", "reason", "details", "photo", "video", "created_at", "resolved_at", "refund_id", "refunded_at", "replacement_stock_taken")
    fieldsets = (
        ("Request", {"fields": ("reference", "order", "item", "quantity", "reason", "details", "photo", "video", "created_at")}),
        ("Decision", {"fields": ("status", "resolution", "staff_note")}),
        ("Pickup of the returned item", {"fields": ("pickup_courier", "pickup_awb", "pickup_date")}),
        ("Refund", {"fields": ("refund_amount", "refund_id", "refunded_at")}),
        ("Replacement", {"fields": ("replacement_courier", "replacement_awb", "replacement_stock_taken")}),
        ("Closed", {"fields": ("resolved_at",)}),
    )
    inlines = [ReturnEventInline]
    actions = ["approve", "reject", "mark_received", "issue_refund", "dispatch_replacement", "mark_resolved"]

    @admin.display(description="Refund")
    def refund_state(self, obj):
        if obj.refunded_at:
            return f"Rs. {obj.refund_value} paid"
        return "-"

    def _set(self, request, queryset, status, **extra):
        n = 0
        for req in queryset.exclude(status=status):
            req.status = status
            for k, v in extra.items():
                if not getattr(req, k):
                    setattr(req, k, v)
            req.save()  # the signal logs the timeline and emails the customer
            n += 1
        self.message_user(request, f"{n} request(s) updated and customers emailed.")

    @admin.action(description="Approve (emails customer)")
    def approve(self, request, queryset):
        self._set(request, queryset, ReturnRequest.Status.APPROVED)

    @admin.action(description="Reject (emails customer)")
    def reject(self, request, queryset):
        self._set(request, queryset, ReturnRequest.Status.REJECTED)

    @admin.action(description="Mark the returned item as received and checked")
    def mark_received(self, request, queryset):
        self._set(request, queryset, ReturnRequest.Status.RECEIVED)

    @admin.action(description="Issue refund (Razorpay for online orders; manual for others)")
    def issue_refund(self, request, queryset):
        from . import emails, payments
        done = 0
        for req in queryset.filter(refunded_at__isnull=True).exclude(status__in=[ReturnRequest.Status.REJECTED, ReturnRequest.Status.WITHDRAWN]):
            try:
                refund_id = payments.refund_amount(req.order, req.refund_value, f"Return {req.reference}")
            except payments.PaymentError as exc:
                self.message_user(request, f"{req.reference}: {exc} Refund it from the Razorpay dashboard.", level=messages.ERROR)
                continue
            req.refund_id, req.refunded_at, req.refund_amount = refund_id, timezone.now(), req.refund_value
            req.resolution = ReturnRequest.Resolution.REFUND
            req.status = ReturnRequest.Status.RESOLVED
            req._skip_update_email = True  # the refund email below says it
            req.save()
            emails.send_return_refund(req)
            done += 1
            if not refund_id:
                self.message_user(request, f"{req.reference}: not paid online, so please pay Rs. {req.refund_value} back to the customer manually.", level=messages.WARNING)
        self.message_user(request, f"{done} refund(s) recorded and customers emailed.")

    @admin.action(description="Dispatch replacement (takes stock, emails customer)")
    def dispatch_replacement(self, request, queryset):
        from . import emails, orders
        done = 0
        for req in queryset.filter(replacement_stock_taken=False).exclude(status__in=[ReturnRequest.Status.REJECTED, ReturnRequest.Status.WITHDRAWN]):
            taken = orders.take_stock(req.item.product, req.quantity, reference=req.reference, user=request.user)
            if taken < req.quantity:
                self.message_user(request, f"{req.reference}: only {taken} unit(s) in stock, so it was not dispatched.", level=messages.ERROR)
                continue
            req.replacement_stock_taken = True
            req.resolution = ReturnRequest.Resolution.REPLACEMENT
            req.status = ReturnRequest.Status.RESOLVED
            req._skip_update_email = True
            req.save()
            emails.send_replacement_shipped(req)
            done += 1
        self.message_user(request, f"{done} replacement(s) dispatched and customers emailed.")

    @admin.action(description="Mark resolved (emails customer)")
    def mark_resolved(self, request, queryset):
        self._set(request, queryset, ReturnRequest.Status.RESOLVED)


@admin.register(EmailJob)
class EmailJobAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "status", "attempts", "run_after", "sent_at")
    list_filter = ("status",)
    readonly_fields = ("to", "subject", "text", "html", "reply_to", "attempts", "last_error", "created_at", "sent_at")
    actions = ["retry"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Retry failed emails")
    def retry(self, request, queryset):
        n = queryset.filter(status=EmailJob.Status.FAILED).update(status=EmailJob.Status.PENDING, attempts=0)
        self.message_user(request, f"{n} email(s) queued again.")


@admin.register(SavedCart)
class SavedCartAdmin(admin.ModelAdmin):
    list_display = ("user", "updated_at", "reminded_at")
    readonly_fields = ("user", "data", "updated_at", "reminded_at")

    def has_add_permission(self, request):
        return False


class BundleItemInline(admin.TabularInline):
    model = BundleItem
    extra = 2


@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "regular", "saving_amount", "is_active", "order")
    list_editable = ("is_active", "order")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [BundleItemInline]

    @admin.display(description="Normal price")
    def regular(self, obj):
        return obj.regular_price

    @admin.display(description="Customer saves")
    def saving_amount(self, obj):
        return obj.saving


@admin.register(LoyaltyEntry)
class LoyaltyEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "points", "kind", "order", "note", "created_at")
    list_filter = ("kind",)
    search_fields = ("user__email", "note", "order__number")
    readonly_fields = ("created_at",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "quantity", "interval_days", "next_date", "status")
    list_filter = ("status", "interval_days", "product")
    search_fields = ("user__email",)


@admin.register(ProductQuestion)
class ProductQuestionAdmin(admin.ModelAdmin):
    list_display = ("question", "product", "user", "answered", "is_visible", "created_at")
    list_filter = ("is_visible", "product")
    list_editable = ("is_visible",)
    readonly_fields = ("product", "user", "question", "created_at", "answered_at")
    fields = ("product", "user", "question", "answer", "is_visible", "created_at", "answered_at")

    @admin.display(boolean=True, description="Answered")
    def answered(self, obj):
        return bool(obj.answer.strip())


@admin.register(ReviewVote)
class ReviewVoteAdmin(admin.ModelAdmin):
    list_display = ("review", "user")


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ("title", "link", "is_active", "starts_at", "ends_at", "order")
    list_editable = ("is_active", "order")


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_published", "updated_at")
    list_editable = ("is_published",)
    prepopulated_fields = {"slug": ("title",)}


User = get_user_model()
admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = BaseUserAdmin.list_display + ("customer_360",)

    @admin.display(description="Customer 360")
    def customer_360(self, obj):
        return format_html('<a href="{}">Open</a>', reverse("customer_360", args=[obj.pk]))


@admin.register(DistributorEnquiry)
class DistributorEnquiryAdmin(admin.ModelAdmin):
    list_display = ("firm_name", "full_name", "district", "state", "mobile", "gst_number", "experience_years", "status", "created_at")
    list_filter = ("status", "state")
    list_editable = ("status",)
    search_fields = ("firm_name", "full_name", "mobile", "email", "gst_number", "district")
    date_hierarchy = "created_at"


@admin.register(CareerApplication)
class CareerApplicationAdmin(admin.ModelAdmin):
    list_display = ("full_name", "position", "location", "experience_years", "mobile", "handled", "created_at")
    list_filter = ("position", "handled")
    list_editable = ("handled",)
    search_fields = ("full_name", "mobile", "email", "location")
    date_hierarchy = "created_at"


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "status", "order")
    list_filter = ("status", "state")
    list_editable = ("status", "order")
    search_fields = ("name",)


@admin.register(DistributorListing)
class DistributorListingAdmin(admin.ModelAdmin):
    list_display = ("firm_name", "contact_person", "district", "state", "consent_given", "is_published")
    list_filter = ("consent_given", "is_published", "state")
    list_editable = ("consent_given", "is_published")
    search_fields = ("firm_name", "contact_person", "district")


@admin.register(HeroSlide)
class HeroSlideAdmin(admin.ModelAdmin):
    list_display = ("headline", "eyebrow", "primary_label", "is_active", "order")
    list_editable = ("is_active", "order")
    fieldsets = (
        ("Words", {"fields": ("eyebrow", "headline", "text")}),
        ("Buttons", {"fields": (("primary_label", "primary_url"), ("secondary_label", "secondary_url"))}),
        ("Background", {"fields": ("image", "default_background")}),
        ("Show", {"fields": ("is_active", "order")}),
    )


# ====================================================== editable website content

@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """One row only: opening the list jumps straight to the form."""
    fieldsets = (
        ("Company", {"fields": ("company_name", "tagline", "established", "founder_name", "website")}),
        ("Contact details", {"fields": ("phone", "whatsapp", "email", "sales_email", "careers_email", "enquiry_recipients", "address")}),
        ("Social media (empty links are not shown)", {"fields": ("facebook", "instagram", "youtube", "twitter", "threads", "linkedin")}),
        ("About page", {"fields": ("overview", "vision", "mission")}),
        ("Distributor offer", {"fields": ("min_purchase",)}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        row = SiteSettings.objects.first()
        if row is None:
            row = SiteSettings.objects.create()
        return redirect(reverse("admin:core_sitesettings_change", args=[row.pk]))


@admin.register(TeamMessage)
class TeamMessageAdmin(admin.ModelAdmin):
    list_display = ("heading", "name", "designation", "show_on_home", "is_published", "order")
    list_editable = ("show_on_home", "is_published", "order")


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ("question", "is_active", "order")
    list_editable = ("is_active", "order")
    search_fields = ("question", "answer")


@admin.register(JobRole)
class JobRoleAdmin(admin.ModelAdmin):
    list_display = ("title", "is_open", "order")
    list_editable = ("is_open", "order")


@admin.register(Highlight)
class HighlightAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "icon", "is_active", "order")
    list_filter = ("kind",)
    list_editable = ("is_active", "order")


@admin.register(TimelineItem)
class TimelineItemAdmin(admin.ModelAdmin):
    list_display = ("period", "text", "is_active", "order")
    list_editable = ("is_active", "order")


# ---------------------------------------------------------------- sectioned admin sidebar
# Few clear groups instead of one long list. (key, title, icon, [(model object name, icon)])
SECTIONS = [
    ("website", "Website content", "fas fa-desktop", [
        ("SiteSettings", "fas fa-sliders-h"), ("HeroSlide", "fas fa-images"), ("TeamMessage", "fas fa-comment-dots"), ("Highlight", "fas fa-star"),
        ("TimelineItem", "fas fa-stream"), ("FAQ", "fas fa-question-circle"), ("Banner", "fas fa-bullhorn"), ("Announcement", "fas fa-bell"),
        ("Page", "fas fa-file-alt"), ("Article", "fas fa-newspaper"), ("CategoryPage", "fas fa-th-large")]),
    ("network", "Distributors & enquiries", "fas fa-handshake", [
        ("DistributorEnquiry", "fas fa-handshake"), ("Enquiry", "fas fa-envelope-open-text"), ("District", "fas fa-map-marked-alt"),
        ("DistributorListing", "fas fa-store"), ("CareerApplication", "fas fa-id-badge"), ("JobRole", "fas fa-briefcase")]),
    ("catalogue", "Products", "fas fa-capsules", [
        ("Product", "fas fa-capsules"), ("ProductQuestion", "fas fa-comments"), ("Review", "fas fa-star-half-alt")]),
    ("inventory", "Inventory", "fas fa-boxes", [
        ("InventoryScreen", "fas fa-warehouse"), ("Batch", "fas fa-box-open"), ("StockMovement", "fas fa-exchange-alt")]),
    ("orders", "Orders & returns", "fas fa-shopping-bag", [
        ("SalesDashboard", "fas fa-chart-line"), ("Order", "fas fa-shopping-bag"), ("ReturnRequest", "fas fa-undo"), ("Subscription", "fas fa-sync-alt")]),
    ("customers", "Customers", "fas fa-users", [
        ("User", "fas fa-user"), ("Profile", "fas fa-id-card"), ("Address", "fas fa-map-marker-alt"), ("Wishlist", "fas fa-heart"),
        ("SavedCart", "fas fa-shopping-cart"), ("Subscriber", "fas fa-envelope")]),
    ("offers", "Offers & rewards", "fas fa-ticket-alt", [
        ("Coupon", "fas fa-ticket-alt"), ("CouponRedemption", "fas fa-receipt"), ("Bundle", "fas fa-gift"), ("LoyaltyEntry", "fas fa-coins")]),
    ("system", "System & access", "fas fa-shield-alt", [
        ("Group", "fas fa-users-cog"), ("TOTPDevice", "fas fa-key"), ("EmailJob", "fas fa-paper-plane"), ("ReviewVote", "fas fa-thumbs-up")]),
]
# shortcuts that are screens, not database tables: (object name, label, url name)
SCREENS = {"InventoryScreen": ("Inventory screen", "inventory"), "SalesDashboard": ("Sales dashboard", "sales_dashboard")}


def _sectioned(original):
    def get_app_list(request, app_label=None):
        apps = original(request, app_label)
        if app_label:
            return apps
        by_name = {}
        for app in apps:
            for model in app["models"]:
                by_name[model["object_name"]] = model
        used, out = set(), []
        for key, title, icon, entries in SECTIONS:
            models = []
            for name, _ in entries:
                if name in SCREENS:
                    label, url_name = SCREENS[name]
                    if request.user.is_staff:
                        models.append({"name": label, "object_name": name, "admin_url": reverse(url_name), "add_url": None,
                                       "perms": {"view": True, "change": False, "add": False, "delete": False}, "view_only": True})
                elif name in by_name:
                    models.append(by_name[name])
                    used.add(name)
            if models:
                out.append({"name": title, "app_label": "sec_" + key, "app_url": "#", "has_module_perms": True, "models": models})
        rest = [m for n, m in by_name.items() if n not in used]
        if rest:
            out.append({"name": "Other", "app_label": "sec_other", "app_url": "#", "has_module_perms": True, "models": rest})
        return out
    return get_app_list


def _register_sidebar_icons():
    from django.conf import settings as dj_settings
    icons = dj_settings.JAZZMIN_SETTINGS.setdefault("icons", {})
    for key, _title, icon, entries in SECTIONS:
        icons["sec_" + key] = icon
        for name, model_icon in entries:
            icons[f"sec_{key}.{name}".lower()] = model_icon
    icons["sec_other"] = "fas fa-ellipsis-h"
    dj_settings.JAZZMIN_SETTINGS["order_with_respect_to"] = ["sec_" + k for k, *_ in SECTIONS] + ["sec_other"]


_register_sidebar_icons()
admin.site.get_app_list = _sectioned(admin.site.get_app_list)

