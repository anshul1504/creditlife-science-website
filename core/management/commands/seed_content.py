from django.core.management.base import BaseCommand

from core.models import Article, CategoryPage, Product, ProductFAQ

CATEGORIES = {
    "digestive": {
        "heading": "Digestive care",
        "intro": "Everyday digestive support from Dr. GAS and related products.",
        "meta": "Digestive care products from Credit Lifesciences: Dr. GAS range with composition, usage and delivery details.",
        "body": (
            "## About this range\n\n"
            "Our digestive care products are made for everyday use. Each product page lists the full composition, how to use it, "
            "cautions and storage so you can read everything before you buy.\n\n"
            "## Using digestive products sensibly\n\n"
            "- Read the label and follow the directions on the pack or from your doctor.\n"
            "- Do not use for more than the recommended time without medical advice.\n"
            "- See a doctor if symptoms are severe, keep coming back, or come with weight loss, fever or blood in stool.\n\n"
            "These products are not a substitute for medical advice."
        ),
    },
    "nutrition": {
        "heading": "Nutritional support",
        "intro": "Nutritional supplements with clear composition and usage information.",
        "meta": "Nutritional support products from Credit Lifesciences with full composition and usage details.",
        "body": (
            "## About this range\n\n"
            "Our nutritional support products are supplements, not medicines for treating a disease. "
            "Composition and recommended use are shown on every product page.\n\n"
            "## Before you start\n\n"
            "- Supplements work best alongside a balanced diet.\n"
            "- If you are pregnant, nursing, or take regular medicines, speak to your doctor first.\n"
            "- Store as directed and keep out of reach of children."
        ),
    },
    "pain": {
        "heading": "Joint and muscle care",
        "intro": "Topical and oral care for everyday aches in joints and muscles.",
        "meta": "Joint and muscle care products from Credit Lifesciences, including MahaJoint oil, with usage and cautions.",
        "body": (
            "## About this range\n\n"
            "Products for everyday joint and muscle discomfort. Each page explains how to use the product and what to avoid.\n\n"
            "## Good to know\n\n"
            "- For external use products: do not apply on broken skin and wash hands after use.\n"
            "- Persistent or worsening pain, swelling or numbness needs a doctor's advice.\n"
            "- Gentle movement and rest matter as much as any product."
        ),
    },
}

ARTICLES = [
    {
        "slug": "how-to-read-a-medicine-label",
        "title": "How to read a medicine or supplement label",
        "summary": "A short guide to the information on every pack and why it matters before you buy or use it.",
        "body": (
            "A label tells you what is inside, how much to use, and what to watch out for. A minute spent reading it is the easiest safety check there is.\n\n"
            "## What to look for\n\n"
            "- **Name and composition:** the active ingredients and their strength.\n"
            "- **Directions:** how much, how often and for how long.\n"
            "- **Warnings:** who should not use it, and what to avoid while using it.\n"
            "- **Batch number, manufacturing and expiry dates:** never use a product past its expiry.\n"
            "- **Licence and manufacturer details:** these show who is responsible for the product.\n\n"
            "## When to ask\n\n"
            "If anything is unclear, ask your doctor or pharmacist before using the product."
        ),
    },
    {
        "slug": "storing-medicines-safely-at-home",
        "title": "Storing medicines and supplements safely at home",
        "summary": "Simple habits that keep products effective and keep children safe.",
        "body": (
            "Heat, damp and sunlight can spoil products long before their printed expiry date.\n\n"
            "## Simple rules\n\n"
            "- Keep products in a cool, dry place away from direct sunlight. The bathroom is usually a poor choice.\n"
            "- Keep the cap tight and use the original pack.\n"
            "- Store out of reach of children, ideally in a closed cupboard.\n"
            "- Check expiry dates every few months and dispose of anything expired.\n\n"
            "## Always follow the pack\n\n"
            "Some products have their own storage instructions. The pack is always the final word."
        ),
    },
    {
        "slug": "questions-to-ask-your-doctor-or-pharmacist",
        "title": "Five questions to ask your doctor or pharmacist",
        "summary": "Make the most of a short consultation with a few simple questions.",
        "body": (
            "Good advice starts with good questions. These five work for almost any product.\n\n"
            "## The five questions\n\n"
            "- What is this for, and how will I know it is working?\n"
            "- How and when should I use it, and for how long?\n"
            "- Is it safe with the other medicines or supplements I take?\n"
            "- What side effects should I look out for?\n"
            "- What should I do if I miss a dose?\n\n"
            "Write the answers down, or ask the pharmacist to mark them on the pack."
        ),
    },
]


class Command(BaseCommand):
    help = "Create starter category pages, product FAQs and DRAFT articles (articles stay unpublished until the client approves them)."

    def handle(self, *args, **options):
        for key, data in CATEGORIES.items():
            _, created = CategoryPage.objects.get_or_create(category=key, defaults={
                "heading": data["heading"], "intro": data["intro"], "body": data["body"], "meta_description": data["meta"]})
            self.stdout.write(f"{'Created' if created else 'Exists '}: category page {key}")

        for product in Product.objects.filter(is_active=True, is_rx=False):
            if product.faqs.exists():
                continue
            dosage = " ".join(ln.strip() for ln in product.dosage.splitlines() if ln.strip())
            storage = " ".join(ln.strip() for ln in product.storage.splitlines() if ln.strip())
            faqs = []
            if dosage:
                faqs.append((f"How should I use {product.name}?", f"{dosage} Always follow the directions on the pack or your doctor's advice."))
            if storage:
                faqs.append((f"How do I store {product.name}?", storage))
            faqs += [
                ("Can you deliver to my PIN code?", "Enter your PIN code in the delivery box on this page to check delivery and the expected time."),
                ("Is cash on delivery available?", "Yes. You can pay on delivery or pay online at checkout."),
                ("What if the product arrives damaged or near expiry?", "Report it from My orders within 7 days of delivery with a photo, and we will arrange a replacement or refund."),
            ]
            for order, (q, a) in enumerate(faqs):
                ProductFAQ.objects.create(product=product, question=q, answer=a, order=order)
            self.stdout.write(f"Created {len(faqs)} FAQs for {product.slug}")

        for data in ARTICLES:
            _, created = Article.objects.get_or_create(slug=data["slug"], defaults={**data, "is_published": False, "meta_description": data["summary"][:160]})
            self.stdout.write(f"{'Created draft' if created else 'Exists      '}: {data['slug']}")
        self.stdout.write(self.style.WARNING("Articles are drafts. Have them reviewed, then tick Published in the admin."))
