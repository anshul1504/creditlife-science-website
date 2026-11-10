"""Bulk update of prices, tax details and stock from a CSV file (admin upload or `manage.py import_products`).

Columns (header row required, only `slug` is mandatory, extra columns are ignored):
  slug, price, mrp, sale_price, hsn_code, gst_rate, is_active, track_inventory, batch_no, expiry, quantity, mfg_date
* Existing products are updated; unknown slugs are reported as errors (new products are created in the admin).
* A row with `batch_no` + `expiry` + `quantity` creates the batch or sets its quantity to that number.
* Dates are YYYY-MM-DD. Booleans: 1/0, yes/no, true/false.
* The file is applied all or nothing: if any row has an error, nothing is saved.
"""
import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import Batch, Product

TRUE = {"1", "yes", "y", "true", "on"}
FALSE = {"0", "no", "n", "false", "off"}


def _bool(value):
    v = value.strip().lower()
    if v in TRUE:
        return True
    if v in FALSE:
        return False
    raise ValueError(f"'{value}' is not yes/no")


def _int(value, name):
    try:
        n = int(value.strip())
    except ValueError:
        raise ValueError(f"{name} must be a whole number") from None
    if n < 0:
        raise ValueError(f"{name} cannot be negative")
    return n


def _date(value, name):
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise ValueError(f"{name} must look like 2027-03-31") from None


def import_products(fileobj, dry_run=False):
    """-> (changes: list[str], errors: list[str]). Nothing is saved when there are errors or dry_run is set."""
    raw = fileobj.read()
    text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "slug" not in [f.strip().lower() for f in reader.fieldnames]:
        return [], ["The first row must be a header that includes a 'slug' column."]
    changes, errors = [], []
    try:
        with transaction.atomic():
            for line, row in enumerate(reader, start=2):
                row = {(k or "").strip().lower(): (v or "") for k, v in row.items()}
                slug = row.get("slug", "").strip()
                if not slug:
                    continue
                product = Product.objects.filter(slug=slug).first()
                if product is None:
                    errors.append(f"Row {line}: no product with slug '{slug}'.")
                    continue
                try:
                    changes += _apply_row(product, row, line)
                except (ValueError, InvalidOperation) as exc:
                    errors.append(f"Row {line} ({slug}): {exc}")
            if errors or dry_run:
                transaction.set_rollback(True)
    except Exception as exc:  # noqa: BLE001 - report instead of a 500 page
        errors.append(f"Could not read the file: {exc}")
    return changes, errors


def _apply_row(product, row, line):
    done = []
    for field in ("price", "mrp", "sale_price"):
        if row.get(field, "").strip() != "":
            setattr(product, field, _int(row[field], field))
            done.append(f"{product.slug}: {field} = {getattr(product, field)}")
    if row.get("hsn_code", "").strip():
        product.hsn_code = row["hsn_code"].strip()[:10]
        done.append(f"{product.slug}: HSN = {product.hsn_code}")
    if row.get("gst_rate", "").strip():
        rate = Decimal(row["gst_rate"].strip())
        if not (0 <= rate <= 28):
            raise ValueError("gst_rate must be between 0 and 28")
        product.gst_rate = rate
        done.append(f"{product.slug}: GST = {rate}%")
    for field in ("is_active", "track_inventory"):
        if row.get(field, "").strip():
            setattr(product, field, _bool(row[field]))
            done.append(f"{product.slug}: {field} = {getattr(product, field)}")
    if product.sale_price and product.sale_price >= product.price:
        raise ValueError("sale_price must be lower than price (use 0 for no sale)")
    if product.mrp and product.price and product.mrp < product.price:
        raise ValueError("mrp cannot be lower than price")
    product.save()

    if row.get("batch_no", "").strip():
        if not (row.get("expiry", "").strip() and row.get("quantity", "").strip()):
            raise ValueError("a batch row needs batch_no, expiry and quantity")
        expiry = _date(row["expiry"], "expiry")
        qty = _int(row["quantity"], "quantity")
        defaults = {"expiry": expiry, "quantity": qty}
        if row.get("mfg_date", "").strip():
            defaults["mfg_date"] = _date(row["mfg_date"], "mfg_date")
        batch, created = Batch.objects.update_or_create(product=product, batch_no=row["batch_no"].strip(), defaults=defaults)
        done.append(f"{product.slug}: batch {batch.batch_no} {'added' if created else 'set'} to {qty} units, expiry {expiry}")
        if not product.track_inventory:
            product.track_inventory = True
            product.save(update_fields=["track_inventory"])
            done.append(f"{product.slug}: stock tracking switched on")
    return done
