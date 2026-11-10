from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from django.utils import timezone

from . import cart, emails, loyalty, orders, sitecfg
from .models import Batch, Order, Profile, ProductQuestion, ReturnRequest, SiteSettings


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    # on every save, not only the first: it also repairs an account that somehow has no profile
    if created or not Profile.objects.filter(user=instance).exists():
        Profile.objects.get_or_create(user=instance)


@receiver(pre_save, sender=Order)
def remember_old_status(sender, instance, **kwargs):
    instance._old_status = (
        Order.objects.filter(pk=instance.pk).values_list("status", flat=True).first() if instance.pk else None
    )
    if instance._old_status != instance.status:
        if instance.status == Order.Status.SHIPPED and not instance.shipped_at:
            instance.shipped_at = timezone.now()
        elif instance.status == Order.Status.DELIVERED and not instance.delivered_at:
            instance.delivered_at = timezone.now()


@receiver(post_save, sender=Order)
def release_stock_on_cancel(sender, instance, **kwargs):
    """A cancelled order (from the admin, the customer or the expiry job) gives its units back to their batches."""
    if instance.status == Order.Status.CANCELLED and not instance.stock_released:
        orders.release_stock(instance)
        loyalty.on_cancelled(instance)


@receiver(post_save, sender=Order)
def credit_points_on_delivery(sender, instance, created, **kwargs):
    if instance.status == Order.Status.DELIVERED and getattr(instance, "_old_status", None) != Order.Status.DELIVERED:
        loyalty.on_delivered(instance)


@receiver(post_save, sender=Batch)
def sync_stock_flag(sender, instance, **kwargs):
    instance.product.refresh_stock_flag()


@receiver(post_save, sender=Order)
def email_on_status_change(sender, instance, created, **kwargs):
    """Whenever staff change an order's status (admin edit or bulk action), email the customer."""
    old = getattr(instance, "_old_status", None)
    if created or old is None or old == instance.status:
        return
    emails.send_order_status(instance)


@receiver(pre_save, sender=ReturnRequest)
def remember_old_return_status(sender, instance, **kwargs):
    instance._old_status = ReturnRequest.objects.filter(pk=instance.pk).values_list("status", flat=True).first() if instance.pk else None
    if instance.status in (ReturnRequest.Status.RESOLVED, ReturnRequest.Status.REJECTED) and not instance.resolved_at:
        instance.resolved_at = timezone.now()


@receiver(post_save, sender=ReturnRequest)
def email_on_return_change(sender, instance, created, **kwargs):
    from .models import ReturnEvent
    old = getattr(instance, "_old_status", None)
    if created:
        ReturnEvent.objects.create(request=instance, status=instance.status, note="Request received")
    elif old is not None and old != instance.status:
        ReturnEvent.objects.create(request=instance, status=instance.status, note=instance.staff_note[:300])
        if not getattr(instance, "_skip_update_email", False):
            emails.send_return_update(instance)


@receiver(pre_save, sender=ProductQuestion)
def stamp_answer(sender, instance, **kwargs):
    old = ProductQuestion.objects.filter(pk=instance.pk).values_list("answer", flat=True).first() if instance.pk else ""
    instance._newly_answered = bool(instance.answer.strip()) and not (old or "").strip()
    if instance._newly_answered:
        instance.answered_at = timezone.now()


@receiver(post_save, sender=ProductQuestion)
def email_when_answered(sender, instance, created, **kwargs):
    if getattr(instance, "_newly_answered", False):
        emails.send_question_answered(instance)


@receiver(post_save, sender=SiteSettings)
@receiver(post_delete, sender=SiteSettings)
def forget_cached_site_settings(sender, **kwargs):
    sitecfg.clear()


user_logged_in.connect(cart.merge_on_login, dispatch_uid="merge_saved_cart")
