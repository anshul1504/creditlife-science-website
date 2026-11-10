"""Apply the data from the client's content brief and product documents (November 2026). Safe to run again."""
from django.core.management import call_command
from django.core.management.base import BaseCommand

from core.models import Announcement, District, HeroSlide, Product

DISTRICTS = [
    "Lucknow", "Ayodhya", "Gonda", "Bahraich", "Gorakhpur", "Azamgarh", "Ambedkar Nagar", "Jaunpur", "Varanasi", "Basti",
    "Sant Kabir Nagar", "Balrampur", "Sultanpur", "Shravasti", "Sitapur", "Lakhimpur Kheri", "Hardoi", "Shahjahanpur",
    "Pilibhit", "Bareilly",
]

SYSTEMS = {
    "mahajoint-oil": Product.System.AYURVEDIC,
    "npr-hb-syrup": Product.System.ALLOPATHIC, "dr-gas-liquid": Product.System.ALLOPATHIC, "dr-gas-plus": Product.System.ALLOPATHIC,
    "dr-gas-2x": Product.System.ALLOPATHIC, "tumlanta-mps": Product.System.ALLOPATHIC,
}

UPDATES = {
    "dr-gas-plus": {
        "composition_title": "Composition (per capsule)",
        "composition": "Rabeprazole Sodium (enteric-coated) | 20 mg\nDomperidone (sustained-release) | 30 mg",
        "dosage_form": "Capsules",
    },
    "dr-gas-2x": {
        "composition_title": "Composition (per capsule)",
        "composition": "Pantoprazole (gastro-resistant) | 40 mg\nDomperidone (prolonged-release) | 30 mg",
        "dosage_form": "Capsules",
    },
    "tumlanta-mps": {
        "pack": "200 ml",
        "composition_title": "Composition (each 5 ml contains)",
        "composition": "Activated Dimethicone | 50 mg\nMagnesium Hydroxide | 250 mg\nDried Aluminium Hydroxide | 250 mg\nSorbitol Solution (70%) | 1.25 gm\nColour | Erythrosine",
        "dosage": "\n".join([
            "For oral use only. Shake the bottle well before each use and measure the dose with a cup or spoon.",
            "1 to 2 teaspoonfuls (about 5 to 10 ml), 30 to 60 minutes after meals or whenever symptoms occur, or as directed by the physician.",
            "Do not exceed 10 teaspoonfuls in 24 hours.",
            "If you miss a dose, take it when you remember; skip it if it is close to the next dose. Do not double the dose.",
        ]),
        "storage": "\n".join(["Keep away from direct sunlight.", "Keep out of reach of children.", "Do not freeze."]),
    },
    "mahajoint-oil": {
        "pack": "As per pack",
        "composition_title": "Composition",
        "composition": "\n".join([
            "Jatamansi | 0.8 gm", "Rasnaspatak | 0.8 gm", "Dashmool | 0.8 gm", "Haldi | 0.8 gm", "Ashwagandha | 0.8 gm", "Methi | 0.8 gm",
            "Kuth | 0.8 gm", "Ajwayan | 0.8 gm", "Soye | 0.8 gm", "Punarnava Mool | 0.8 gm", "Mustak | 0.8 gm", "Devdaru | 0.8 gm",
            "Vacha | 0.8 gm", "Gajpipali | 0.8 gm", "Black Salt | 0.8 gm", "Bala | 0.8 gm", "Ati Bala | 0.8 gm", "Vasa | 0.8 gm",
            "Arand Mool | 5.0 gm", "Ark | 5.0 gm", "Garlic | 3.0 gm", "Lemon | 3.0 gm", "Ginger | 3.0 gm", "Camphor | 1.0 gm",
            "Winter Green Oil | 2.0 ml", "Menthol Oil | 2.0 ml", "Castor Oil | 10 ml", "Nilgiri Oil | 10 ml", "Til (Sesame) Oil | q.s.",
        ]),
        "storage": "\n".join(["Store at a temperature not exceeding 25 C.", "Do not freeze.", "Replace the cap tightly after use."]),
    },
}


SLIDES = [
    ("Credit Lifesciences · since 2009", "Building Trusted Partnerships. Serving Health.",
     "At Credit Lifesciences, we believe that strong business partnerships drive better healthcare accessibility. With a commitment to quality, affordability and long-term relationships, we invite distributors and business partners to grow with us.",
     "Become a Distributor", "/become-a-distributor/", "Explore Our Products", "/shop/", "img/hero/bg-1.jpg"),
    ("Quality & Affordability", "Quality healthcare at affordable prices.",
     "We believe healthcare should be accessible, not a luxury. Our range is built around consistent quality and fair pricing.",
     "Explore Our Products", "/shop/", "", "", "img/hero/bg-2.jpg"),
    ("Trust & Experience", "Pharmaceutical market presence since 2009.",
     "17 years of building relationships with distributors, stockists and retail chemists.",
     "About Credit Lifesciences", "/about/", "", "", "img/hero/bg-3.jpg"),
    ("Healthcare Accessibility", "Medicines for rural and underserved communities too.",
     "Our focus has always included making medicines accessible in rural and underserved markets, alongside mainstream markets.",
     "Our Mission", "/about/", "", "", "img/hero/bg-4.jpg"),
    ("Distribution Network", "A growing network of distributors across Uttar Pradesh.",
     "Present today in 20 districts of Uttar Pradesh, with plans to expand across India.",
     "View Distribution Network", "/distribution-network/", "", "", "img/hero/bg-5.jpg"),
    ("Business Partnerships · Product Portfolio", "Ayurvedic and Allopathic products. Opportunities to become an authorised distributor.",
     "Explore our portfolio and talk to us about a territory-based distribution partnership.",
     "Become a Distributor", "/become-a-distributor/", "Explore Our Products", "/shop/", "img/hero/bg-6.jpg"),
]


class Command(BaseCommand):
    help = "Load the 20 Uttar Pradesh districts, Ayurvedic/Allopathic tags, product details from the supplied PDFs and the new announcement."

    def handle(self, *args, **options):
        for i, name in enumerate(DISTRICTS, 1):
            _, created = District.objects.get_or_create(name=name, state="Uttar Pradesh", defaults={"status": District.Status.ACTIVE, "order": i})
            self.stdout.write(f"{'Added' if created else 'Exists'}: {name}")
        for slug, system in SYSTEMS.items():
            Product.objects.filter(slug=slug).update(system=system)
        for slug, data in UPDATES.items():
            Product.objects.filter(slug=slug).update(**data)
            self.stdout.write(f"Updated product details: {slug}")
        if not HeroSlide.objects.exists():
            for i, (eyebrow, headline, text, pl, pu, sl, su, bg) in enumerate(SLIDES, 1):
                HeroSlide.objects.create(eyebrow=eyebrow, headline=headline, text=text, primary_label=pl, primary_url=pu,
                                         secondary_label=sl, secondary_url=su, default_background=bg, order=i)
            self.stdout.write("Created the six hero slides.")
        text = "Building Trusted Partnerships. Serving Health."
        Announcement.objects.filter(text__icontains="Free delivery").update(text=text, link="/become-a-distributor/")
        if not Announcement.objects.exists():
            Announcement.objects.create(text=text, link="/become-a-distributor/", order=1)
        call_command("seed_site", stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Brief content applied. Statuses of the 20 districts default to Active: confirm each one in the admin."))
