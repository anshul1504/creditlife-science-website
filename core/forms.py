import re

from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.core.cache import cache

from .models import (
    Address, CareerApplication, DistributorEnquiry, Enquiry, Order, Product, ProductQuestion, ReturnRequest, Review, Subscription,
)

STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
    "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
]
STATE_CHOICES = [("", "Select state")] + [(s, s) for s in STATES]

PHONE_WIDGET = {"placeholder": "10-digit mobile number", "inputmode": "tel", "autocomplete": "tel"}


def normalize_phone(value):
    """Return a bare 10-digit Indian mobile number or raise ValidationError."""
    phone = re.sub(r"[\s\-()]", "", value or "")
    match = re.fullmatch(r"(?:\+?91)?0?([6-9]\d{9})", phone)
    if not match:
        raise forms.ValidationError("Please enter a valid 10-digit Indian mobile number.")
    return match.group(1)


def valid_pincode(value):
    pin = (value or "").strip()
    if not re.fullmatch(r"[1-9]\d{5}", pin):
        raise forms.ValidationError("Please enter a valid 6-digit PIN code.")
    return pin


def _style(form, skip=()):
    for name, field in form.fields.items():
        if name in skip or isinstance(field.widget, (forms.RadioSelect, forms.CheckboxInput)):
            continue
        css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
        field.widget.attrs["class"] = css
        if not isinstance(field.widget, forms.Select):
            field.widget.attrs.setdefault("placeholder", " ")  # Bootstrap floating labels need a placeholder


class EnquiryForm(forms.ModelForm):
    # Honeypot: real visitors never see or fill this field.
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    class Meta:
        model = Enquiry
        fields = ["name", "organisation", "topic", "kind", "phone", "email", "city", "product", "message"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Your full name", "autocomplete": "name"}),
            "organisation": forms.TextInput(attrs={"placeholder": "Firm / clinic / hospital (optional)", "autocomplete": "organization"}),
            "email": forms.EmailInput(attrs={"placeholder": "you@example.com", "autocomplete": "email"}),
            "city": forms.TextInput(attrs={"placeholder": "City / district / state, e.g. Basti, Uttar Pradesh"}),
            "message": forms.Textarea(attrs={"rows": 4, "placeholder": "How can we help? Tell us about your requirement or question"}),
        }

    phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs=PHONE_WIDGET))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.filter(is_active=True)
        self.fields["product"].required = False
        self.fields["product"].empty_label = "Not about a specific product"
        self.fields["email"].required = True  # the brief lists email as required
        _style(self, skip=("website",))

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")
        return ""


class CheckoutForm(forms.ModelForm):
    state = forms.ChoiceField(choices=STATE_CHOICES)
    # Declared here (max_length 20) so "+91 98765 43210" is accepted and normalised to 10 digits in clean_phone.
    phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs=PHONE_WIDGET))
    payment_method = forms.ChoiceField(widget=forms.RadioSelect, initial=Order.Payment.COD)
    save_address = forms.BooleanField(required=False, label="Save this address for next time")

    class Meta:
        model = Order
        fields = ["name", "phone", "email", "address", "city", "state", "pincode", "notes", "payment_method"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Full name", "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"placeholder": "Email for order updates", "autocomplete": "email"}),
            "address": forms.Textarea(attrs={"rows": 3, "placeholder": "House no., street, area, landmark", "autocomplete": "street-address"}),
            "city": forms.TextInput(attrs={"placeholder": "City / town", "autocomplete": "address-level2"}),
            "pincode": forms.TextInput(attrs={"placeholder": "6-digit PIN code", "inputmode": "numeric", "maxlength": "6", "autocomplete": "postal-code"}),
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": "Anything we should know? (optional)"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = []
        if settings.SHOP["online_payment_enabled"]:
            choices.append((Order.Payment.ONLINE, "Online payment (UPI / debit card / credit card / net banking)"))
        if settings.SHOP["cod_enabled"]:
            choices.append((Order.Payment.COD, "Cash on delivery"))
        self.fields["payment_method"].choices = choices
        if choices:
            self.fields["payment_method"].initial = choices[0][0]
        _style(self)

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def clean_pincode(self):
        return valid_pincode(self.cleaned_data["pincode"])


class TrackForm(forms.Form):
    number = forms.CharField(label="Order number", max_length=16, widget=forms.TextInput(attrs={"placeholder": "e.g. CL2610290123"}))
    phone = forms.CharField(label="Mobile number used for the order", max_length=20, widget=forms.TextInput(attrs={"placeholder": "10-digit mobile number", "inputmode": "tel"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)

    def clean_number(self):
        return self.cleaned_data["number"].strip().upper()

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])


# ------------------------------------------------------------------ accounts

class SignupDetailsForm(forms.Form):
    """What we ask a new customer for. The email itself is proven by the one-time code, so no password is needed."""
    name = forms.CharField(label="Full name", max_length=100)
    phone = forms.CharField(label="Mobile number", max_length=20)

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if len(name) < 2:
            raise forms.ValidationError("Please enter your full name.")
        return name

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"placeholder": "you@example.com", "autofocus": True, "autocomplete": "email"}))
    password = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"placeholder": "Your password", "autocomplete": "current-password"}))
    remember = forms.BooleanField(required=False, initial=True, label="Keep me signed in on this device")
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "That email and password do not match. Please try again.",
    }
    MAX_FAILS = 5
    LOCK_SECONDS = 600

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)

    def clean(self):
        email = (self.data.get("username") or "").strip().lower()
        key = f"login-fail:{email}"
        if email and cache.get(key, 0) >= self.MAX_FAILS:
            raise forms.ValidationError("Too many failed attempts. Please try again in 10 minutes, or reset your password.")
        try:
            cleaned = super().clean()
        except forms.ValidationError:
            if email:
                cache.set(key, cache.get(key, 0) + 1, self.LOCK_SECONDS)
            raise
        cache.delete(key)
        return cleaned


class ProfileForm(forms.Form):
    name = forms.CharField(label="Full name", max_length=100)
    phone = forms.CharField(label="Mobile number", max_length=20, widget=forms.TextInput(attrs=PHONE_WIDGET))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])


class BusinessForm(forms.ModelForm):
    class Meta:
        from .models import Profile as _P
        model = _P
        fields = ["account_type", "business_name", "gstin", "drug_licence_no", "gst_document", "licence_document"]
        widgets = {"gstin": forms.TextInput(attrs={"maxlength": 15, "placeholder": "15-character GSTIN", "style": "text-transform:uppercase"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["business_name"].required = True
        self.fields["gstin"].required = True
        self.fields["drug_licence_no"].required = True
        _style(self)

    def clean_gstin(self):
        value = self.cleaned_data["gstin"].strip().upper()
        if not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", value):
            raise forms.ValidationError("Enter a valid 15-character GSTIN.")
        return value

    def _doc(self, name, existing):
        f = self.cleaned_data.get(name)
        if f and hasattr(f, "size"):
            if f.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Please upload a file under 5 MB.")
            if not f.name.lower().endswith((".pdf", ".jpg", ".jpeg", ".png")):
                raise forms.ValidationError("Upload a PDF, JPG or PNG file.")
        if not f and not existing:
            raise forms.ValidationError("This document is required.")
        return f

    def clean_gst_document(self):
        return self._doc("gst_document", self.instance.gst_document)

    def clean_licence_document(self):
        return self._doc("licence_document", self.instance.licence_document)


class AddressForm(forms.ModelForm):
    state = forms.ChoiceField(choices=STATE_CHOICES)
    phone = forms.CharField(max_length=20, widget=forms.TextInput(attrs=PHONE_WIDGET))

    class Meta:
        model = Address
        fields = ["label", "name", "phone", "address", "city", "state", "pincode", "is_default"]
        widgets = {
            "label": forms.TextInput(attrs={"placeholder": "Home, Work..."}),
            "address": forms.Textarea(attrs={"rows": 3, "placeholder": "House no., street, area, landmark"}),
            "pincode": forms.TextInput(attrs={"inputmode": "numeric", "maxlength": "6"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)

    def clean_phone(self):
        return normalize_phone(self.cleaned_data["phone"])

    def clean_pincode(self):
        return valid_pincode(self.cleaned_data["pincode"])


class ReviewForm(forms.ModelForm):
    rating = forms.IntegerField(min_value=1, max_value=5, widget=forms.HiddenInput, error_messages={"required": "Please choose a star rating."})

    class Meta:
        model = Review
        fields = ["rating", "title", "body", "photo"]
        labels = {"photo": "Add a photo (optional)"}
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Summarise your experience (optional)"}),
            "body": forms.Textarea(attrs={"rows": 4, "placeholder": "What did you like or dislike? How did you use it?"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self)


class StyledPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].label = "Email address"
        self.fields["email"].widget.attrs.update({"placeholder": "you@example.com", "autocomplete": "email", "autofocus": True})
        _style(self)


class StyledSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].widget.attrs.update({"placeholder": "New password", "autocomplete": "new-password", "autofocus": True})
        self.fields["new_password2"].widget.attrs.update({"placeholder": "Confirm new password", "autocomplete": "new-password"})
        _style(self)


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].widget.attrs.update({"placeholder": "Current password", "autocomplete": "current-password", "autofocus": True})
        self.fields["new_password1"].widget.attrs.update({"placeholder": "New password", "autocomplete": "new-password"})
        self.fields["new_password2"].widget.attrs.update({"placeholder": "Confirm new password", "autocomplete": "new-password"})
        _style(self)


class ReturnForm(forms.ModelForm):
    quantity = forms.IntegerField(min_value=1, label="How many units?")

    class Meta:
        model = ReturnRequest
        fields = ["quantity", "details", "video", "photo"]
        widgets = {"details": forms.Textarea(attrs={"rows": 4, "placeholder": "Tell us what was damaged"})}
        labels = {"photo": "Photo of the damage (optional)", "video": "Unboxing video (required)"}

    def __init__(self, *args, max_qty=1, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_qty = max_qty
        self.fields["quantity"].widget.attrs["max"] = max_qty
        self.fields["quantity"].initial = 1
        self.fields["video"].required = True  # the brief: replacement only after reviewing an unboxing video
        self.fields["video"].widget.attrs["accept"] = "video/*"
        _style(self)

    def clean_quantity(self):
        qty = self.cleaned_data["quantity"]
        if qty > self.max_qty:
            raise forms.ValidationError(f"You can return at most {self.max_qty} unit(s) of this item.")
        return qty

    def clean_video(self):
        video = self.cleaned_data.get("video")
        name = (getattr(video, "name", "") or "").lower()
        if video and not name.endswith((".mp4", ".mov", ".webm", ".3gp", ".m4v", ".avi")):
            raise forms.ValidationError("Please upload a video file (MP4, MOV or WebM).")
        if video and video.size > 100 * 1024 * 1024:
            raise forms.ValidationError("Please upload a video under 100 MB.")
        return video

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Please upload a photo under 5 MB.")
        return photo


class ReviewPhotoMixin:
    pass


class QuestionForm(forms.ModelForm):
    class Meta:
        model = ProductQuestion
        fields = ["question"]
        widgets = {"question": forms.TextInput(attrs={"placeholder": "Ask about usage, ingredients, delivery...", "maxlength": 300})}

    def clean_question(self):
        q = self.cleaned_data["question"].strip()
        if len(q) < 10:
            raise forms.ValidationError("Please write a little more.")
        return q


class SubscribeForm(forms.Form):
    interval_days = forms.TypedChoiceField(choices=Subscription.INTERVALS, coerce=int)
    quantity = forms.IntegerField(min_value=1, max_value=settings.SHOP["max_qty"], initial=1)


def _check_review_photo(self):
    photo = self.cleaned_data.get("photo")
    if photo and getattr(photo, "size", 0) > 5 * 1024 * 1024:
        raise forms.ValidationError("Please upload a photo under 5 MB.")
    return photo


ReviewForm.clean_photo = _check_review_photo


GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


class _Honeypot(forms.Form):
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")
        return ""


class DistributorEnquiryForm(_Honeypot, forms.ModelForm):
    mobile = forms.CharField(max_length=20, label="Mobile number", widget=forms.TextInput(attrs=PHONE_WIDGET))
    state = forms.ChoiceField(choices=STATE_CHOICES)

    class Meta:
        model = DistributorEnquiry
        fields = ["full_name", "firm_name", "mobile", "email", "state", "district", "gst_number", "licence_number", "experience_years"]
        labels = {"experience_years": "Years of experience in pharmaceutical distribution"}
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "firm_name": forms.TextInput(attrs={"autocomplete": "organization"}),
            "gst_number": forms.TextInput(attrs={"placeholder": "15-character GSTIN", "maxlength": 15, "style": "text-transform:uppercase"}),
            "licence_number": forms.TextInput(attrs={"placeholder": "Form 20B / 21B licence number(s)"}),
            "experience_years": forms.NumberInput(attrs={"min": 0, "max": 80}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["licence_number"].label = "Wholesale drug licence number (Form 20B / 21B)"
        _style(self, skip=("website",))

    def clean_mobile(self):
        return normalize_phone(self.cleaned_data["mobile"])

    def clean_gst_number(self):
        gst = (self.cleaned_data["gst_number"] or "").strip().upper()
        if not GSTIN_RE.match(gst):
            raise forms.ValidationError("Please enter a valid 15-character GST number (for example 09ABCDE1234F1Z5).")
        return gst


class CareerForm(_Honeypot, forms.ModelForm):
    mobile = forms.CharField(max_length=20, label="Mobile number", widget=forms.TextInput(attrs=PHONE_WIDGET))
    position = forms.ChoiceField(label="Position applied for")
    ALLOWED = (".pdf", ".doc", ".docx")

    class Meta:
        model = CareerApplication
        fields = ["full_name", "mobile", "email", "location", "position", "experience_years", "qualification", "resume", "message"]
        widgets = {
            "full_name": forms.TextInput(attrs={"autocomplete": "name"}),
            "message": forms.Textarea(attrs={"rows": 4, "placeholder": "A few lines about yourself"}),
            "experience_years": forms.NumberInput(attrs={"min": 0, "max": 60}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import JobRole
        self.fields["position"].choices = [("", "Select a role")] + [(r.title, r.title) for r in JobRole.objects.filter(is_open=True)]
        self.fields["resume"].widget.attrs["accept"] = ",".join(self.ALLOWED)
        _style(self, skip=("website",))

    def clean_mobile(self):
        return normalize_phone(self.cleaned_data["mobile"])

    def clean_resume(self):
        f = self.cleaned_data["resume"]
        name = (getattr(f, "name", "") or "").lower()
        if not name.endswith(self.ALLOWED):
            raise forms.ValidationError("Please upload your CV as a PDF or Word file.")
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Please upload a file under 5 MB.")
        return f
