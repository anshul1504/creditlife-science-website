"""Business pages from the content brief: distributor enquiry, distribution network, careers, FAQs, legal information."""
from django.shortcuts import render

from . import emails, sitecfg
from .forms import CareerForm, DistributorEnquiryForm
from .models import FAQ, District, DistributorListing, JobRole


def distributor(request):
    form = DistributorEnquiryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        enquiry = form.save()
        emails.send_distributor_enquiry(enquiry)
        return render(request, "core/form_thanks.html", {
            "heading": "Thank you for your interest",
            "message": "We have received your distributor enquiry. Our team will contact you to discuss it. "
                       "Submitting this form does not automatically grant an authorised distributorship.",
        })
    return render(request, "core/distributor.html", {"form": form, "min_purchase": sitecfg.site()["min_purchase"]})


def network(request):
    districts = list(District.objects.all())
    listings = list(DistributorListing.objects.filter(consent_given=True, is_published=True))
    for d in districts:
        d.entries = [row for row in listings if row.district.lower() == d.name.lower()]
    counts = {key: sum(1 for d in districts if d.status == key) for key, _ in District.Status.choices}
    documented = [d for d in districts if d.entries]
    return render(request, "core/network.html", {
        "districts": districts, "documented": documented, "pending": [d for d in districts if not d.entries],
        "branch_cols": min(max(len(documented), 1), 5), "statuses": District.Status.choices, "counts": counts, "listings": listings,
    })


def careers(request):
    form = CareerForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        application = form.save()
        emails.send_career_application(application)
        return render(request, "core/form_thanks.html", {
            "heading": "Application received",
            "message": "Thank you for applying to Credit Lifesciences. Our team will review your application and get in touch if your profile matches an opening.",
        })
    return render(request, "core/careers.html", {"form": form, "roles": JobRole.objects.filter(is_open=True)})


class _Safe(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def faqs(request):
    site = sitecfg.site()
    values = _Safe(phone=site["phones"][0][0], email=site["email"], sales_email=site["sales_email"], min_purchase=site["min_purchase"])
    items = [(f.question, f.answer.format_map(values)) for f in FAQ.objects.filter(is_active=True)]
    return render(request, "core/faqs.html", {"items": items})


def legal_info(request):
    return render(request, "core/legal_info.html")
