"""GST tax invoice for an order, as a PDF (reportlab, no system libraries needed).

Selling prices already include GST, so each line is split into taxable value and tax. Seller details come from
settings.SELLER; anything the client has not supplied yet is simply left off instead of being invented.
"""
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Order

TWO = Decimal("0.01")
GREEN = colors.HexColor("#0E7A55")


def q(value):
    return Decimal(value).quantize(TWO, rounding=ROUND_HALF_UP)


def financial_year(dt):
    start = dt.year if dt.month >= 4 else dt.year - 1
    return f"{start % 100:02d}-{(start + 1) % 100:02d}"


def ensure_invoice_no(order):
    """Sequential per financial year, assigned the first time the invoice is needed."""
    if order.invoice_no:
        return order.invoice_no
    prefix = f"CL/{financial_year(timezone.localtime(order.created_at))}/"
    last = Order.objects.filter(invoice_no__startswith=prefix).order_by("-invoice_no").values_list("invoice_no", flat=True).first()
    seq = int(last.rsplit("/", 1)[1]) + 1 if last else 1
    order.invoice_no = f"{prefix}{seq:05d}"
    Order.objects.filter(pk=order.pk).update(invoice_no=order.invoice_no)
    return order.invoice_no


def intra_state(order):
    seller_state = (settings.SELLER["state"] or "").strip().lower()
    return bool(seller_state) and seller_state == order.state.strip().lower()


def build_lines(order):
    """Per-line tax split. The order discount is spread over the lines in proportion to their value."""
    items = list(order.items.all())
    gross_total = sum(i.unit_price * i.quantity for i in items) or 1
    lines = []
    for item in items:
        gross = Decimal(item.unit_price * item.quantity)
        share = q(Decimal(order.total_discount) * gross / gross_total) if order.total_discount else Decimal(0)
        paid = gross - share
        rate = Decimal(item.gst_rate)
        taxable = q(paid * 100 / (100 + rate))
        tax = q(paid - taxable)
        lines.append({"item": item, "gross": gross, "discount": share, "taxable": taxable, "rate": rate, "tax": tax})
    return lines


def totals(order, lines):
    taxable = sum((l["taxable"] for l in lines), Decimal(0))
    tax = sum((l["tax"] for l in lines), Decimal(0))
    return {"taxable": taxable, "tax": tax}


def render_pdf(order):
    invoice_no = ensure_invoice_no(order)
    seller = settings.SELLER
    lines = build_lines(order)
    same_state = intra_state(order)

    base = getSampleStyleSheet()["Normal"]
    small = ParagraphStyle("small", parent=base, fontSize=8, leading=10)
    title = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=GREEN)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Invoice {invoice_no}", author=seller["legal_name"])
    story = [Paragraph("TAX INVOICE", title), Spacer(1, 3 * mm)]

    seller_lines = [f"<b>{seller['legal_name']}</b>", f"({settings.SITE['name']})"]
    for label, key in (("", "address"), ("GSTIN: ", "gstin"), ("CIN: ", "cin"), ("Licence: ", "licence")):
        if seller[key]:
            seller_lines.append(f"{label}{seller[key]}")
    buyer_lines = ["<b>Bill to / Ship to</b>", order.name, order.address, f"{order.city}, {order.state} - {order.pincode}", f"Phone: {order.phone}"]
    if order.email:
        buyer_lines.append(order.email)
    meta = [f"<b>Invoice no:</b> {invoice_no}", f"<b>Date:</b> {timezone.localtime(order.created_at):%d %b %Y}",
            f"<b>Order no:</b> {order.number}", f"<b>Payment:</b> {order.get_payment_method_display()}",
            f"<b>Place of supply:</b> {order.state}"]
    head = Table([[Paragraph("<br/>".join(seller_lines), small), Paragraph("<br/>".join(buyer_lines), small), Paragraph("<br/>".join(meta), small)]],
                 colWidths=[62 * mm, 62 * mm, 56 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                              ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.lightgrey)]))
    story += [head, Spacer(1, 5 * mm)]

    if same_state:
        tax_head = ["CGST", "SGST"]
    else:
        tax_head = ["IGST"]
    header = ["#", "Item / HSN", "Qty", "Rate", "Taxable", "GST %"] + tax_head + ["Amount"]
    rows = [header]
    for n, l in enumerate(lines, 1):
        item = l["item"]
        label = Paragraph(f"{item.product_name} <font size=7 color='#666666'>{item.pack}</font><br/><font size=7>HSN {item.hsn_code or '-'}</font>", small)
        if same_state:
            half = q(l["tax"] / 2)
            tax_cells = [f"{half}", f"{l['tax'] - half}"]
        else:
            tax_cells = [f"{l['tax']}"]
        rows.append([n, label, item.quantity, f"{q(item.unit_price)}", f"{l['taxable']}", f"{l['rate']:.1f}"] + tax_cells + [f"{l['gross'] - l['discount']}"])
    t = totals(order, lines)
    body = Table(rows, repeatRows=1, colWidths=[8 * mm, 52 * mm, 10 * mm, 17 * mm, 20 * mm, 13 * mm] + ([17 * mm, 17 * mm] if same_state else [34 * mm]) + [26 * mm][: 1])
    body.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
    ]))
    story += [body, Spacer(1, 4 * mm)]

    summary = [["Taxable value", f"Rs {t['taxable']}"], ["GST (included)", f"Rs {t['tax']}"]]
    if order.total_discount:
        summary.append(["Discounts (coupon, bundle, credit points) - already applied above", f"Rs {order.total_discount}"])
    summary += [["Delivery", "Free" if not order.shipping else f"Rs {order.shipping}"], ["Invoice total", f"Rs {order.total}"]]
    st = Table(summary, colWidths=[110 * mm, 50 * mm], hAlign="RIGHT")
    st.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black)]))
    story += [st, Spacer(1, 6 * mm)]
    note = "Prices are inclusive of GST. This is a computer-generated invoice and needs no signature."
    if not seller["gstin"]:
        note += " (Seller GSTIN to be added before this invoice is used for tax filing.)"
    story.append(Paragraph(note, small))
    doc.build(story)
    return buf.getvalue()
