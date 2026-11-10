"""Load the starting website content into the admin-managed tables (site settings, messages, FAQs, roles, cards, timeline,
distributor directory). It only fills tables that are empty, so it never overwrites what staff have edited."""
from django.conf import settings
from django.core.management.base import BaseCommand

from core.models import FAQ, DistributorListing, Highlight, JobRole, SiteSettings, TeamMessage, TimelineItem

FOUNDER_BODY = """The journey that began in 2009 with the inception of **Credit Pharmaceuticals** has today evolved into **Credit Lifesciences and Volkscure** — a resilient, trusted and purpose-driven healthcare organization.

Coming from an engineering background (B.Tech Mechanical Engineering) and having prepared for the Civil Services (UPSC), my focus was naturally aligned with problem-solving and systemic impact. However, witnessing the stark health disparities, lack of awareness and limited access to genuine healthcare in rural areas, especially across Eastern Uttar Pradesh, redefined my life's purpose. When faced with the choice between personal career pursuits and sustaining the legacy of this enterprise, I chose the latter — to build and protect a vision that directly touches human lives.

Driven by our core philosophy, **"Chalo Gaon Ki Or" (Towards the Villages),** we set out to bridge the gap in rural healthcare by making high-quality, effective and affordable medicines available to those who needed them most.

Our faith in our formulation standards gave rise to our landmark principle: **"Try Then Buy."** This commitment to transparency and excellence remains our cornerstone to this day. Even through unprecedented global disruptions like the COVID-19 pandemic and economic shifts, we stood firm on one unshakeable rule — **Zero Compromise on Quality.**

Today, Credit Lifesciences stands as a testament to ethical manufacturing, deep-rooted empathy, and continuous innovation. As we move forward, we remain dedicated to advancing healthcare accessibility, reaching every corner with trust and care."""

DIRECTOR_BODY = """My academic background in Bachelor and Master of Social Work (MSW) from Lucknow University and my engagement with public administration studies have provided me with a deep understanding of societal needs, particularly in healthcare accessibility and community welfare.

**Credit Lifesciences** was founded on a noble vision by my brother, **Prakash Harendra Singh,** to bridge the healthcare gap in rural and semi-urban regions by delivering affordable, top-tier pharmaceutical formulations. As a Director, my role is aligned with nurturing this founding legacy, offering strategic direction and reinforcing our core initiative — **"Chalo Gaon Ki Or."**

For us, healthcare is fundamentally a social responsibility. Guided by my background in social welfare, I strongly endorse our company's unshakeable policy of zero compromise on quality and our ethical commitment to the community. Together, we remain dedicated to expanding this legacy of trust, care and service."""

WHY = [
    ("Established since 2009", "An established pharmaceutical presence built over the years.", "bi-calendar-check"),
    ("Quality at affordable prices", "Quality products at prices that keep healthcare within reach.", "bi-tag"),
    ("Strong relationships", "Strong distributor and retailer relationships.", "bi-people"),
    ("Growing network", "A growing district-wise distribution network.", "bi-geo-alt"),
    ("Sales & marketing support", "Dedicated sales and marketing support for our partners.", "bi-headset"),
    ("Long-term approach", "A long-term business partnership approach.", "bi-people-fill"),
]
VALUES = [
    ("Quality", "Commitment to product quality.", "bi-patch-check"), ("Affordability", "Healthcare should be accessible, not a luxury.", "bi-tag"),
    ("Integrity", "Honest business practices.", "bi-shield-check"), ("Trust", "Lasting relationships with customers and partners.", "bi-people"),
    ("Accessibility", "Reaching underserved communities.", "bi-signpost-split"), ("Responsibility", "Contributing to better healthcare.", "bi-heart"),
    ("Consistency", "Maintaining consistency across the product range.", "bi-arrow-repeat"),
]
PRINCIPLES = [
    ("Chalo Gaon Ki Or", "Towards the villages: high-quality, effective and affordable medicines for those who need them most.", "bi-signpost-split"),
    ("Try Then Buy", "Faith in our formulation standards, with transparency and excellence as our cornerstone.", "bi-patch-check"),
    ("Zero Compromise on Quality", "The one unshakeable rule we held through the COVID-19 pandemic and economic shifts.", "bi-shield-check"),
]
TIMELINE = [
    ("2009", "The journey begins with the inception of Credit Pharmaceuticals, which has since evolved into Credit Lifesciences and Volkscure."),
    ("Over the years", "Evolution from a rural-market focus to a wider pharmaceutical market."),
    ("Over the years", "Expansion of distribution presence across multiple districts and growth in distributor relationships."),
    ("Over the years", "Expansion of the product range and product categories."),
    ("COVID-19 period", "The company continued its operations and service during the pandemic."),
    ("Present", "Distribution presence across 20 districts in Uttar Pradesh, with plans to expand across India."),
]
ROLES = ["Medical Representative", "Sales Executive", "Area Sales Manager", "Distribution and Operations", "Office Administration", "Content Creation", "Marketing"]

FAQS = [
    ("How can I become an authorised distributor of Credit Lifesciences?",
     "Fill in the distributor enquiry form on the Become a Distributor page. Our team will contact you to discuss your enquiry. Submitting the form does not by itself make you an authorised distributor."),
    ("What is the minimum initial purchase requirement?", "The minimum initial purchase for a new distributor is ₹{min_purchase}."),
    ("What documents are required to become a distributor?",
     "A valid GST registration and a wholesale drug licence (Form 20B and Form 21B, as applicable to the products and your business). We also look for adequate storage facilities, pharmaceutical distribution experience, an established network of retail chemists and the financial capacity to manage distribution."),
    ("Can multiple distributors operate in the same district?",
     "Yes. We appoint authorised distributors in different districts, and more than one distributor may operate in the same district, with specific territories allocated to each."),
    ("Does Credit Lifesciences provide sales and marketing support?",
     "Yes. Support includes sales representatives, help connecting with local chemists and pharmacies, promotional materials and product catalogues, retailer visits and sales and business guidance."),
    ("How can I place an order?",
     "Registered distributors and authorised business partners can order online through the product catalogue, cart and checkout. You can also send an order enquiry on WhatsApp or through the Contact Us form, and our sales team will follow up."),
    ("What payment methods are accepted?", "UPI, debit cards, credit cards and net banking. An online order is confirmed automatically after successful payment."),
    ("How can I contact customer support?", "Call or WhatsApp {phone}, or write to {email} (general) or {sales_email} (sales and business enquiries)."),
]

# (district, firm, address, contact person, mobile)  from "Distributor Database - Uttar Pradesh.pdf"
DIRECTORY = [
    ("Lucknow", "Shri Balaji Medicals", "Latouche Road, Aminabad, Lucknow", "Madhukar Gupta", "9415519535"),
    ("Lucknow", "Avadh Medical", "Aminabad, Lucknow", "Akshay Agrawal", "9648488408"),
    ("Lucknow", "Raja Traders", "Aminabad, Lucknow", "Sharad Gupta", "9455036570"),
    ("Ayodhya", "Pooja Traders", "Rikabganj, Faizabad", "Sukhdev Sadhwani", "9140726153"),
    ("Ayodhya", "Shri Paramhans Ayurvedic Agencies", "Rikabganj, Faizabad", "Kishore Sadhwani", "9140331197"),
    ("Ayodhya", "Ganga Pharma", "Rikabganj, Faizabad", "", ""),
    ("Ayodhya", "Rekha Ayurvedic Agency", "Rikabganj, Faizabad", "Shubham Agrawal", "9616078690"),
    ("Ayodhya", "Akshat Pharma", "Rikabganj, Faizabad", "Vijay ji", "9628548949"),
    ("Ayodhya", "Pawan Agencies", "Rikabganj, Faizabad", "", "9889221826"),
    ("Ambedkar Nagar", "New Laxmi Medical Store", "Baskhari", "", "9450531882"),
    ("Ambedkar Nagar", "Janta Medical Store", "Ambedkar Nagar", "Guddu Yadav", "9918817198"),
    ("Ambedkar Nagar", "New Kareemi Dawakhana", "Jalalpur", "", ""),
    ("Lakhimpur Kheri", "Laxmi Ayurvedic Agency", "Sarbati Devi Colony, Lakhimpur", "Shivam Verma", "9455682841"),
    ("Lakhimpur Kheri", "Life Care Medical Store", "Gola Gokaran Nath", "Ayatullah Ali", ""),
    ("Lakhimpur Kheri", "Ashish Medical Agency", "Gola Gokaran Nath", "Kapil Purwar", "9415148868"),
    ("Lakhimpur Kheri", "Ali Medical Agency", "Tikunia", "Saddam Hussain", "9559855753"),
    ("Lakhimpur Kheri", "SK Pharma", "Lakhimpur Kheri", "Alok ji", "9565886482"),
    ("Lakhimpur Kheri", "Aman Agencies", "Lakhimpur Kheri", "", "9795447298"),
    ("Lakhimpur Kheri", "Shankar Medical Store", "Lakhimpur Kheri", "Alok Verma", "9984565924 / 8574842204"),
]


class Command(BaseCommand):
    help = "Fill the admin-managed website content with its starting values (only tables that are still empty)."

    def handle(self, *args, **options):
        site = settings.SITE
        if not SiteSettings.objects.exists():
            SiteSettings.objects.create(
                company_name=site["name"], tagline=site["tagline"], established=site["established"], founder_name=site["founder"],
                phone=site["phones"][0][0], whatsapp=site["whatsapp"], email=site["email"], sales_email=site["sales_email"],
                enquiry_recipients="\n".join(site["enquiry_recipients"]), address=site["address"], website=site["website"],
                facebook=next((u for n, _, u in site["social"] if n == "Facebook"), ""),
                instagram=next((u for n, _, u in site["social"] if n == "Instagram"), ""),
                youtube=next((u for n, _, u in site["social"] if n == "YouTube"), ""),
                overview=("Credit Lifesciences was established in 2009 by Mr. Prakash Harendra Singh. It is a pharmaceutical marketing company: we market "
                          "Ayurvedic and Allopathic pharmaceutical products under our own brand name, with a commitment to quality and affordability. "
                          "Today we have a distribution presence across multiple districts of Uttar Pradesh, built on relationships with distributors, "
                          "stockists and retail chemists, and we plan to expand across India."),
                vision="Making the best quality healthcare accessible to every section of society.",
                mission="\n".join([
                    "Provide quality medicines at affordable prices with consistent quality.",
                    "Make medicines accessible in rural and underserved markets alongside mainstream markets.",
                    "Build a reliable nationwide distribution network through long-term relationships with distributors and retailers.",
                    "Expand the pharmaceutical product portfolio while maintaining the company's quality commitment.",
                ]),
                min_purchase="5,00,000",
            )
            self.stdout.write("Created site settings.")
        if not TeamMessage.objects.exists():
            TeamMessage.objects.create(name="Prakash Harendra Singh", designation="Founder & CEO, Credit Lifesciences and Volkscure Private Limited",
                                       heading="Founder & CEO's Message", subheading="Our Journey: Vision, Uncompromised Quality and Commitment to Care",
                                       body=FOUNDER_BODY, show_on_home=True, order=1)
            TeamMessage.objects.create(name="Prabhat Harendra Singh", designation="Director, Credit Lifesciences",
                                       heading="Director's Message", subheading="Social Purpose, Vision, and Legacy", body=DIRECTOR_BODY, order=2)
            self.stdout.write("Created the Founder & CEO and Director messages.")
        if not FAQ.objects.exists():
            for i, (q, a) in enumerate(FAQS, 1):
                FAQ.objects.create(question=q, answer=a, order=i)
        if not JobRole.objects.exists():
            for i, title in enumerate(ROLES, 1):
                JobRole.objects.create(title=title, order=i)
        if not Highlight.objects.exists():
            for kind, rows in (("why", WHY), ("value", VALUES), ("principle", PRINCIPLES)):
                for i, (title, text, icon) in enumerate(rows, 1):
                    Highlight.objects.create(kind=kind, title=title, text=text, icon=icon, order=i)
        if not TimelineItem.objects.exists():
            for i, (period, text) in enumerate(TIMELINE, 1):
                TimelineItem.objects.create(period=period, text=text, order=i)
        added = 0
        for district, firm, address, person, mobile in DIRECTORY:
            _, created = DistributorListing.objects.get_or_create(
                firm_name=firm, district=district, defaults={"address": address, "contact_person": person, "mobile": mobile})
            added += created
        self.stdout.write(f"Directory: {added} new entries (hidden from the public until consent is ticked in the admin).")
        self.stdout.write(self.style.SUCCESS("Website content ready."))
