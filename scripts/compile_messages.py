"""Compile locale/<lang>/LC_MESSAGES/django.po into django.mo without needing GNU gettext.

    python scripts/compile_messages.py

Handles the subset of the .po format this project uses: msgid / msgstr (optionally multi-line), msgctxt, and
comments. Entries with an empty msgstr, and "fuzzy" entries, are skipped (so they fall back to English).
"""
import ast
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "locale"


def parse(po_text):
    entries, cur, field, fuzzy = [], {}, None, False
    for raw in po_text.splitlines() + [""]:
        line = raw.strip()
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
            continue
        if line.startswith("#"):
            continue
        if not line:
            if "msgid" in cur and "msgstr" in cur and not fuzzy:
                entries.append(cur)
            cur, field, fuzzy = {}, None, False
            continue
        for key in ("msgctxt", "msgid", "msgstr"):
            if line.startswith(key + " "):
                field = key
                cur[field] = ast.literal_eval(line[len(key) + 1:])
                break
        else:
            if line.startswith('"') and field:
                cur[field] += ast.literal_eval(line)
    return entries


def build_mo(entries):
    table = {}
    for e in entries:
        if not e["msgstr"]:
            continue
        key = e["msgid"] if "msgctxt" not in e else e["msgctxt"] + "\x04" + e["msgid"]
        table[key] = e["msgstr"]
    if "" not in table:
        table[""] = "Content-Type: text/plain; charset=UTF-8\n"
    keys = sorted(table)
    ids = b""
    strs = b""
    offsets = []
    for k in keys:
        kb, vb = k.encode("utf-8"), table[k].encode("utf-8")
        offsets.append((len(ids), len(kb), len(strs), len(vb)))
        ids += kb + b"\0"
        strs += vb + b"\0"
    n = len(keys)
    keystart = 7 * 4 + 16 * n
    valuestart = keystart + len(ids)
    koffsets, voffsets = [], []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]
    header = struct.pack("Iiiiiii", 0x950412DE, 0, n, 7 * 4, 7 * 4 + n * 8, 0, 0)
    return header + struct.pack(f"{len(koffsets)}i", *koffsets) + struct.pack(f"{len(voffsets)}i", *voffsets) + ids + strs


def main():
    count = 0
    for po in ROOT.glob("*/LC_MESSAGES/django.po"):
        entries = parse(po.read_text(encoding="utf-8"))
        po.with_suffix(".mo").write_bytes(build_mo(entries))
        print(f"{po.relative_to(ROOT.parent)} -> {len(entries)} entries")
        count += 1
    if not count:
        sys.exit("No .po files found under locale/")


if __name__ == "__main__":
    main()
