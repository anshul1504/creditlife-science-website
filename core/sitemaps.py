from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from django.utils import timezone

from .models import Article, CategoryPage, Page, Product


class StaticSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return ["home", "products", "about", "contact", "policies", "privacy", "disclaimer", "terms", "grievance", "cookies", "blog", "distributor", "network", "careers", "faqs", "legal_info"]

    def location(self, item):
        return reverse(item)


class ProductSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.9

    def items(self):
        return Product.objects.filter(is_active=True)


class CategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return CategoryPage.objects.all()


class ArticleSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return Article.objects.filter(is_published=True, published_at__lte=timezone.now())

    def lastmod(self, obj):
        return obj.published_at


class PageSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.4

    def items(self):
        return Page.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.updated_at
