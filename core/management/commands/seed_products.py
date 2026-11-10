from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management import call_command
from django.core.management.base import BaseCommand

from core.models import Product, ProductImage

RX_NOTICE = "Prescription medicine. To be taken only on the advice and prescription of a registered medical practitioner."

PRODUCTS = [
    {
        "slug": "npr-hb-syrup",
        "name": "NPR-HB Syrup",
        "category": "nutrition",
        "subtitle": "Hematinic & Multivitamin Syrup",
        "tagline": "Boost Hemoglobin, Restore Vitality",
        "summary": (
            "A comprehensive hematinic and multivitamin syrup with iron, folic acid, vitamin B12, "
            "vitamin B6 and zinc, formulated to support healthy red blood cell formation and "
            "overall vitality."
        ),
        "dosage_form": "Syrup",
        "pack": "300 ml",
        "composition_title": "Each 5 ml contains",
        "composition": "\n".join([
            "Ferric Ammonium Citrate IP | 200 mg",
            "Cyanocobalamin IP (Vitamin B12) | 7.5 mcg",
            "Folic Acid IP | 1 mg",
            "Zinc Sulphate IP | 7 mg",
            "Pyridoxine Hydrochloride IP (Vitamin B6) | 1.5 mg",
            "Sorbitol Solution (70%) IP (Non-Crystallising) | 750 mg",
            "Flavoured syrup base | q.s.",
            "Colour | Caramel",
        ]),
        "uses": "\n".join([
            "Iron deficiency anaemia caused by poor dietary intake, chronic blood loss or impaired absorption",
            "Nutritional deficiencies, general weakness and fatigue, and recovery after illness or surgery",
            "Higher iron, folic acid and vitamin needs during pregnancy and lactation (under medical supervision)",
            "Support for appetite and nutritional uptake in growing children and adults",
            "General vitality, nerve health and immunity support",
        ]),
        "how_it_works": "\n".join([
            "Ferric Ammonium Citrate | A bioavailable source of iron needed to make haemoglobin, which carries oxygen to body tissues.",
            "Folic Acid (B9) | Essential for DNA synthesis and the maturation of healthy red blood cells.",
            "Vitamin B12 | Works with folic acid in red blood cell formation, cellular metabolism and nerve health.",
            "Vitamin B6 | A coenzyme in amino acid metabolism, haem biosynthesis and neurotransmitter balance.",
            "Zinc Sulphate | Supports immune cells, enzyme activity, tissue repair and appetite.",
            "Sorbitol Solution | Helps reduce iron-related constipation and supports digestive tolerance.",
        ]),
        "dosage": "\n".join([
            "For oral use only. Shake the bottle well before each use.",
            "Adults: 5 ml to 10 ml (1 to 2 teaspoonfuls) twice daily, or as directed by the physician.",
            "Children above 3 years: 2.5 ml to 5 ml daily, or strictly as directed by the physician.",
            "Best taken immediately after meals. Use an accurate measuring cup or spoon rather than a household spoon.",
        ]),
        "side_effects": "\n".join([
            "Dark or blackish stool (a harmless effect of oral iron)",
            "Mild stomach discomfort, heartburn or cramping",
            "Transient nausea or a metallic taste",
            "Mild loose stools or laxative action (due to sorbitol)",
            "Temporary tooth staining. Mixing with a little water or using a straw helps avoid it",
        ]),
        "warnings": "\n".join([
            "Use as directed by a healthcare professional. Do not exceed the recommended dose.",
            "Do not use if you are hypersensitive to iron salts, zinc compounds or any ingredient.",
            "Consult a doctor first if you have haemochromatosis, haemosiderosis, haemolytic anaemia or an active peptic ulcer.",
            "Avoid antacids, dairy products, tea, coffee or calcium supplements within 2 hours of a dose, as they reduce iron absorption.",
            "Use during pregnancy and lactation only under medical advice.",
            "Keep out of reach and sight of children.",
        ]),
        "storage": "\n".join([
            "Store in a cool, dry and dark place.",
            "Protect from direct sunlight, heat and moisture. Do not freeze.",
            "Keep the container tightly closed when not in use.",
        ]),
        "highlights": "Iron + B12 + Folic Acid, Zinc enriched, Gentle on the stomach",
        "image": "img/npr-hb.jpg",
        "stage": "light",
        "accent": "#C2670A",
        "order": 1,
    },
    {
        "slug": "dr-gas-liquid",
        "name": "Dr. GAS Liquid",
        "category": "digestive",
        "subtitle": "Antacid Liquid with Bismuth, Belladonna, Thymol & Menthol",
        "tagline": "To Keep Stomach Fit",
        "summary": (
            "A sugar-free antacid liquid with a protective coating action, for relief from gas, "
            "hyperacidity, heartburn and indigestion."
        ),
        "dosage_form": "Liquid",
        "pack": "450 ml",
        "composition_title": "Active ingredients",
        "composition": "\n".join([
            "Ammonium Bismuth Citrate | As per label",
            "Belladonna Dry Extract | As per label",
            "Thymol | As per label",
            "Menthol | As per label",
        ]),
        "uses": "\n".join([
            "Gas, hyperacidity, heartburn and indigestion",
            "Belching and nausea",
            "Gastritis and stomach-related discomfort, as advised by a physician",
            "Constipation or loose stools associated with digestive upset",
            "Sugar free, so it may also be used by people with diabetes",
        ]),
        "how_it_works": "\n".join([
            "Ammonium Bismuth Citrate | Supports the protective mucous layer of the digestive tract and eases indigestion and heartburn.",
            "Belladonna Dry Extract | Helps reduce stomach and intestinal spasm and bloating.",
            "Thymol | Has carminative properties that help relieve gas and support digestion.",
            "Menthol | Provides a cooling effect and helps ease nausea and digestive discomfort.",
        ]),
        "dosage": "\n".join([
            "For oral use only. Shake well before use and read the directions on the label.",
            "10 to 15 ml three times a day with a cup of water after meals, or as directed by your physician.",
        ]),
        "side_effects": "\n".join([
            "Temporary and harmless darkening of the tongue or stool",
            "Blurred vision, dry mouth or fast heartbeat in some people",
            "Most effects are temporary and settle on stopping. See your doctor if you notice anything serious.",
        ]),
        "warnings": "\n".join([
            "For oral use only. Keep out of reach of children.",
            "In case of excessive intake, consult a physician immediately.",
            "If pregnant or breastfeeding, consult your doctor before use.",
            "Avoid alcohol while taking this product, as it can increase drowsiness and dizziness.",
        ]),
        "storage": "\n".join([
            "Store in a cool, dark and dry place.",
            "Keep away from direct sunlight and moisture. Do not freeze.",
        ]),
        "highlights": "Sugar free, Protective coating action, Bismuth + Belladonna",
        "image": "img/drgas-liquid.jpg",
        "stage": "green",
        "accent": "#0E7A55",
        "order": 2,
    },
    {
        "slug": "dr-gas-plus",
        "name": "Dr. GAS Plus",
        "category": "digestive",
        "is_rx": True,
        "subtitle": "Enteric Coated Rabeprazole Sodium & Sustained Release Domperidone Capsules",
        "tagline": "Protective · Coating · Action",
        "summary": "Prescription antacid capsules. Product information is provided for healthcare professionals.",
        "dosage_form": "Capsules",
        "pack": "10 x 20 Capsules (Alu-Alu)",
        "composition_title": "Composition",
        "composition": "\n".join([
            "Rabeprazole Sodium (enteric coated) | As per label",
            "Domperidone (sustained release) | As per label",
        ]),
        "dosage": "\n".join([
            "As directed by the registered medical practitioner.",
            RX_NOTICE,
        ]),
        "warnings": "\n".join([
            RX_NOTICE,
            "Read the package insert and label before use. Keep out of reach of children.",
        ]),
        "storage": "Store as directed on the pack, away from heat, light and moisture.",
        "highlights": "Rx only, Alu-Alu pack",
        "image": "img/drgas-plus.jpg",
        "stage": "green",
        "accent": "#0E7A55",
        "order": 3,
    },
    {
        "slug": "dr-gas-2x",
        "name": "Dr. GAS 2X",
        "category": "digestive",
        "is_rx": True,
        "subtitle": "Pantoprazole Gastro-resistant & Domperidone Prolonged-release Capsules IP",
        "tagline": "Protective · Coating · Action",
        "summary": "Prescription antacid capsules. Product information is provided for healthcare professionals.",
        "dosage_form": "Capsules",
        "pack": "20 x 10 Capsules (Alu-Alu)",
        "composition_title": "Composition",
        "composition": "\n".join([
            "Pantoprazole (gastro-resistant) | As per label",
            "Domperidone (prolonged-release) | As per label",
        ]),
        "dosage": "\n".join([
            "As directed by the registered medical practitioner.",
            RX_NOTICE,
        ]),
        "warnings": "\n".join([
            RX_NOTICE,
            "Read the package insert and label before use. Keep out of reach of children.",
        ]),
        "storage": "Store as directed on the pack, away from heat, light and moisture.",
        "highlights": "Rx only, Alu-Alu pack",
        "image": "img/drgas-2x.jpg",
        "stage": "dark",
        "accent": "#1766A6",
        "order": 4,
    },
    {
        "slug": "tumlanta-mps",
        "name": "Tumlanta MPS",
        "category": "digestive",
        "subtitle": "Antacid & Antigas Suspension",
        "tagline": "From the makers of Dr. GAS",
        "summary": "A sugar-free, mint-flavoured antacid and antigas suspension from the makers of Dr. GAS.",
        "dosage_form": "Suspension",
        "pack": "As per pack",
        "composition_title": "Composition",
        "composition": "Aluminium and Magnesium based antacid suspension | Full composition as per label",
        "uses": "\n".join([
            "Acidity, heartburn and indigestion",
            "Gas and bloating",
            "Sugar free",
        ]),
        "dosage": "\n".join([
            "For oral use only. Shake well before use.",
            "As directed by the physician.",
        ]),
        "warnings": "\n".join([
            "Use as directed by a healthcare professional.",
            "If pregnant or breastfeeding, consult your doctor before use.",
            "Keep out of reach of children.",
        ]),
        "storage": "Store in a cool, dry place away from direct sunlight.",
        "highlights": "Sugar free, Mint flavour, Antacid + Antigas",
        "image": "img/tumlanta.jpg",
        "stage": "dark",
        "accent": "#B5457A",
        "order": 5,
    },
    {
        "slug": "mahajoint-oil",
        "name": "MahaJoint Oil",
        "category": "pain",
        "subtitle": "Joint Pain Relief Oil",
        "tagline": "Enriched with 29 Precious Herbs & Oils",
        "summary": (
            "An ayurvedic massage oil enriched with 29 herbs and oils, for external application "
            "on muscle pain, joint pain and stiffness."
        ),
        "dosage_form": "Oil (external use)",
        "pack": "50 ml",
        "composition_title": "Formulation",
        "composition": "Proprietary ayurvedic blend of 29 herbs & oils | Full ingredient list on pack",
        "uses": "\n".join([
            "Muscle pain",
            "Joint pain",
            "Stiffness",
            "Natural support for sciatica discomfort",
        ]),
        "dosage": "\n".join([
            "Only for external application and gentle massage.",
            "Apply a suitable quantity on the affected area and massage gently, or as directed by the physician.",
        ]),
        "warnings": "\n".join([
            "For external use only. Do not take by mouth.",
            "Avoid contact with eyes, mouth and mucous membranes.",
            "Do not use over open wounds or burns.",
            "Keep out of reach of children.",
        ]),
        "storage": "Store in a cool, dry place away from direct sunlight.",
        "highlights": "Ayurvedic, 29 herbs & oils, For external use",
        "image": "img/mahajoint.jpg",
        "stage": "light",
        "accent": "#9A6B12",
        "order": 6,
    },
]


# PLACEHOLDER prices (MRP, selling price) in rupees. The client has not supplied prices yet:
# replace these in /admin/ (Products) before going live. Rx products are never sold online.
PLACEHOLDER_PRICES = {
    "npr-hb-syrup": (250, 225),
    "dr-gas-liquid": (220, 199),
    "tumlanta-mps": (160, 145),
    "mahajoint-oil": (300, 270),
}


MARKETER = "Marketed by | Credit Lifesciences, Division of Volkscure Pvt. Ltd."
ORIGIN = "Country of origin | India"
LICENCE = "Mfg. Lic. No. | 40/UA/2006"
MANUFACTURER = {
    "npr-hb-syrup": "\n".join([
        MARKETER,
        "Manufactured by | Yacca Pharmaceuticals Pvt. Ltd., 11th Km Stone, Dehradun Road, Roorkee - 247667 (Uttarakhand)",
        ORIGIN,
    ]),
    "dr-gas-liquid": "\n".join([MARKETER, LICENCE, ORIGIN]),
    "dr-gas-plus": "\n".join([MARKETER, LICENCE, ORIGIN]),
    "dr-gas-2x": "\n".join([MARKETER, LICENCE, ORIGIN]),
    "tumlanta-mps": "\n".join([MARKETER, ORIGIN]),
    "mahajoint-oil": "\n".join([MARKETER, ORIGIN]),
}

# Extra gallery images (files live in static/img/gallery). (file, alt text, fit)
GALLERY = {
    "npr-hb-syrup": [
        ("npr-hb-pack.jpg", "NPR-HB Syrup carton and 300 ml bottle", "cover"),
        ("npr-hb-bottle.jpg", "NPR-HB Syrup 300 ml bottle", "cover"),
    ],
    "dr-gas-liquid": [
        ("drgas-liquid-box.jpg", "Dr. GAS Liquid carton", "cover"),
        ("drgas-liquid-bottle.jpg", "Dr. GAS Liquid bottle", "cover"),
        ("drgas-liquid-leaflet.jpg", "Dr. GAS Liquid product information", "contain"),
    ],
    "dr-gas-plus": [("drgas-plus-front.jpg", "Dr. GAS Plus carton front", "cover")],
    "dr-gas-2x": [
        ("drgas-2x-pack.jpg", "Dr. GAS 2X carton", "cover"),
        ("drgas-2x-front.jpg", "Dr. GAS 2X carton front", "cover"),
    ],
    "tumlanta-mps": [
        ("tumlanta-label.jpg", "Tumlanta MPS bottle label", "cover"),
        ("tumlanta-base.jpg", "Tumlanta MPS bottle base", "cover"),
    ],
    "mahajoint-oil": [
        ("mahajoint-bottle.jpg", "MahaJoint Oil 50 ml bottle", "cover"),
        ("mahajoint-box.jpg", "MahaJoint Oil carton", "cover"),
    ],
}


class Command(BaseCommand):
    help = "Create or update the product catalogue (placeholder prices are only filled in where no price is set)."

    def handle(self, *args, **options):
        gallery_dir = Path(settings.BASE_DIR) / "static" / "img" / "gallery"
        for data in PRODUCTS:
            slug = data["slug"]
            data = {**data, "manufacturer": MANUFACTURER.get(slug, "")}
            product, created = Product.objects.update_or_create(slug=slug, defaults=data)
            if slug in PLACEHOLDER_PRICES and not product.price:
                product.mrp, product.price = PLACEHOLDER_PRICES[slug]
                product.save(update_fields=["mrp", "price"])
            hero = f"img/hero/{slug}.webp"
            if (Path(settings.BASE_DIR) / "static" / hero).exists() and product.hero_image != hero:
                product.hero_image = hero
                product.save(update_fields=["hero_image"])
            for order, (filename, alt, fit) in enumerate(GALLERY.get(slug, []), start=1):
                if product.images.filter(alt=alt).exists():
                    continue
                img = ProductImage(product=product, alt=alt, fit=fit, order=order)
                with open(gallery_dir / filename, "rb") as fh:
                    img.image.save(f"{slug}-{filename}", File(fh), save=True)
            self.stdout.write(f"{'Created' if created else 'Updated'}: {slug} ({product.images.count()} extra images)")
        # apply the client's content brief on top: Ayurvedic/Allopathic tags, PDF product details, the 20 districts
        call_command("seed_brief", stdout=self.stdout)
