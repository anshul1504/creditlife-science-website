"""Product search with typo tolerance (standard library only; the catalogue is small enough for this)."""
import difflib
import re

from django.core.cache import cache
from django.db.models import Q

from .models import Product

WORD = re.compile(r"[a-z0-9]{3,}")
VOCAB_KEY = "search:vocab"


def vocabulary():
    """Every word a customer might sensibly type: names, generic names, ingredients, uses, tags."""
    words = cache.get(VOCAB_KEY)
    if words is None:
        found = set()
        for p in Product.objects.filter(is_active=True):
            for text in (p.name, p.subtitle, p.tagline, p.composition, p.uses, p.summary, p.highlights):
                found.update(WORD.findall((text or "").lower()))
        words = sorted(found)
        cache.set(VOCAB_KEY, words, 300)
    return words


def correct(query):
    """Fix words that are close to a known word. Returns (corrected query, changed?)."""
    vocab = vocabulary()
    fixed, changed = [], False
    for token in query.lower().split():
        if token in vocab or len(token) < 4 or any(token in w for w in vocab):
            fixed.append(token)
            continue
        match = difflib.get_close_matches(token, vocab, n=1, cutoff=0.72)
        if match:
            fixed.append(match[0])
            changed = True
        else:
            fixed.append(token)
    return " ".join(fixed), changed


def find(query):
    """Products where every word of the query appears in a searchable field, best name matches first."""
    q = Q()
    terms = query.split()
    for term in terms:
        q &= (
            Q(name__icontains=term) | Q(subtitle__icontains=term) | Q(composition__icontains=term)
            | Q(uses__icontains=term) | Q(tagline__icontains=term) | Q(summary__icontains=term) | Q(highlights__icontains=term)
        )
    products = list(Product.objects.filter(is_active=True).filter(q)) if terms else []
    first = terms[0].lower() if terms else ""
    products.sort(key=lambda p: (first not in p.name.lower(), first not in p.subtitle.lower(), p.order))
    return products


def search(query):
    """-> (products, shown_query, corrected?)  Tries the query as typed, then a spelling-corrected one."""
    products = find(query)
    if products:
        return products, query, False
    fixed, changed = correct(query)
    if changed:
        products = find(fixed)
        if products:
            return products, fixed, True
    return [], query, False
