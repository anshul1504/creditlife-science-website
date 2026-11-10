"""Credit points (loyalty) and referrals.

* Earn: SHOP["points_per_100"] points per Rs 100 paid, credited when the order is delivered (not when placed, so a
  cancelled or returned order never leaves points behind).
* Spend: at checkout, up to SHOP["max_points_pct"] percent of the order, worth SHOP["point_value"] rupees each.
* Referral: a new customer who signed up through someone's link, and that someone, each get SHOP["referral_reward"]
  points after the new customer's first delivered order. Self-referrals and repeat rewards are blocked.
"""
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum

from .models import LoyaltyEntry, Profile

logger = logging.getLogger(__name__)
REF_SESSION_KEY = "ref"


def balance(user):
    if not (user and user.is_authenticated):
        return 0
    return LoyaltyEntry.objects.filter(user=user).aggregate(total=Sum("points"))["total"] or 0


def max_redeemable(user, payable):
    """Most points this customer may spend on an order whose pre-points payable amount (excluding delivery) is `payable`."""
    shop = settings.SHOP
    cap_value = payable * shop["max_points_pct"] // 100
    return min(balance(user), cap_value // shop["point_value"])


def points_value(points):
    return points * settings.SHOP["point_value"]


# ---------------------------------------------------------------- ledger
def _credit(**kwargs):
    """Create a ledger row, swallowing the duplicate that the unique constraint blocks (a retry or a race)."""
    try:
        with transaction.atomic():
            return LoyaltyEntry.objects.create(**kwargs)
    except IntegrityError:
        return None


def redeem(order, user, points):
    """Spend points on a new order. Must run inside the order's transaction; locks the profile to serialise spenders."""
    if points <= 0:
        return
    Profile.objects.select_for_update().get(user=user)
    if balance(user) < points:
        raise ValueError("Not enough credit points.")
    LoyaltyEntry.objects.create(user=user, points=-points, kind=LoyaltyEntry.Kind.REDEEM, order=order, note=f"Used on order {order.number}")


def on_cancelled(order):
    """Give back points that were spent on an order, and take back points it earned."""
    if not order.user_id:
        return
    if order.points_used:
        _credit(user_id=order.user_id, points=order.points_used, kind=LoyaltyEntry.Kind.REFUND, order=order, note=f"Order {order.number} cancelled")
    earned = LoyaltyEntry.objects.filter(order=order, kind=LoyaltyEntry.Kind.EARN).first()
    if earned and not LoyaltyEntry.objects.filter(order=order, kind=LoyaltyEntry.Kind.ADJUST).exists():
        LoyaltyEntry.objects.create(user_id=order.user_id, points=-earned.points, kind=LoyaltyEntry.Kind.ADJUST, order=order, note=f"Order {order.number} cancelled after delivery")


def on_delivered(order):
    """Credit the points an order earned, then pay out a referral reward if this was the customer's first delivery."""
    if not order.user_id:
        return
    shop = settings.SHOP
    paid = max(0, order.total - order.shipping)
    earn = paid * shop["points_per_100"] // 100
    if earn:
        _credit(user_id=order.user_id, points=earn, kind=LoyaltyEntry.Kind.EARN, order=order, note=f"Order {order.number}")
    reward_referrer(order)


# -------------------------------------------------------------- referrals
def remember_referrer(request):
    """Call on every request: ?ref=CODE is kept in the session until the visitor signs up."""
    code = (request.GET.get("ref") or "").strip().upper()[:10]
    if code and not request.user.is_authenticated:
        request.session[REF_SESSION_KEY] = code


def attach_referrer(request, user):
    """Called when an account is created: link it to the referrer, unless it is the same person."""
    code = request.session.pop(REF_SESSION_KEY, None)
    if not code:
        return
    referrer = Profile.objects.filter(referral_code=code).select_related("user").first()
    if not referrer or referrer.user_id == user.pk or referrer.user.email.lower() == user.email.lower():
        return
    profile = user.profile
    if profile.referred_by_id is None:
        profile.referred_by = referrer.user
        profile.save(update_fields=["referred_by"])


def reward_referrer(order):
    profile = Profile.objects.filter(user_id=order.user_id).select_related("referred_by__profile").first()
    if not profile or not profile.referred_by_id:
        return
    if LoyaltyEntry.objects.filter(user_id=order.user_id, kind=LoyaltyEntry.Kind.REFERRAL).exists():
        return  # the reward is paid once per new customer
    referrer = profile.referred_by
    # the same phone number on both accounts means the same household: no reward
    if referrer.profile.phone and referrer.profile.phone == order.phone:
        return
    reward = settings.SHOP["referral_reward"]
    LoyaltyEntry.objects.create(user_id=order.user_id, points=reward, kind=LoyaltyEntry.Kind.REFERRAL, note="Welcome reward for joining through a friend")
    LoyaltyEntry.objects.create(user=referrer, points=reward, kind=LoyaltyEntry.Kind.REFERRAL, note=f"{order.name.split()[0]} placed a first order")
