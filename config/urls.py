from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from core.customer360 import customer_360
from core.dashboard import dashboard_view
from core.views_inventory import inventory as inventory_view
from core.sitemaps import ArticleSitemap, CategorySitemap, PageSitemap, ProductSitemap, StaticSitemap

if settings.ADMIN_2FA:
    # staff must hold a TOTP device (add one under Admin > TOTP devices) to open the admin
    from django_otp.admin import OTPAdminSite
    admin.site.__class__ = OTPAdminSite

admin.site.index_template = "admin/index_with_dashboard.html"
admin.site.site_header = "Credit Lifesciences"
admin.site.site_title = "Credit Lifesciences Admin"
admin.site.index_title = "Store management"

urlpatterns = [
    path(f"{settings.ADMIN_URL}/inventory/", inventory_view, name="inventory"),
    path(f"{settings.ADMIN_URL}/dashboard/", admin.site.admin_view(dashboard_view), name="sales_dashboard"),
    path(f"{settings.ADMIN_URL}/customer/<int:user_id>/", admin.site.admin_view(customer_360), name="customer_360"),
    path(f"{settings.ADMIN_URL}/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("sitemap.xml", sitemap, {"sitemaps": {"static": StaticSitemap, "products": ProductSitemap, "categories": CategorySitemap, "articles": ArticleSitemap, "pages": PageSitemap}}, name="sitemap"),
    path("", include("core.urls")),
]
if settings.DEBUG:
    # In production serve MEDIA_ROOT from the web server (nginx) or object storage.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "core.views.not_found"
