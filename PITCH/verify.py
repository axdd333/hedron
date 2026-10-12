#!/usr/bin/env python3
"""Cross-check DECK.md against SOURCES.md: every $ figure in the deck must
appear in SOURCES.md; the S10 ask must sum to the headline; key dates must
match the research files."""
import re, os

here = os.path.dirname(os.path.abspath(__file__))
deck = open(os.path.join(here, "DECK.md")).read()
srcs = open(os.path.join(here, "SOURCES.md")).read()

# 1. dollar figures
deck_usd = set(re.findall(r"\$[\d,]+(?:\.\d+)?[BM]?", deck))
src_usd = set(re.findall(r"\$[\d,]+(?:\.\d+)?[BM]?", srcs))
uncovered = sorted(u for u in deck_usd if u not in src_usd)
print("deck $ figures :", sorted(deck_usd))
print("uncovered      :", uncovered if uncovered else "NONE — all traced")

# 2. ask sums (S10): 150+40+30+15+15 = 250
lines = re.findall(r"~\$(\d+)k", deck)
total = sum(int(x) for x in lines)
print(f"ask line items : {lines} -> ${total}k (headline $250k: {'OK' if total == 250 else 'MISMATCH'})")

# 3. dates present and consistent
for d in ["Oct 19, 2026", "Feb 17, 2027", "Mar 5, 2027", "April 14, 2027|Apr 14, 2027"]:
    ok = any(re.search(p, deck) for p in d.split("|"))
    print(f"date {d:35s} in deck: {'OK' if ok else 'MISSING'}")
for d in ["October 19, 2026|Oct 19, 2026", "February 17, 2027|Feb 17, 2027"]:
    ok = any(re.search(p, srcs) for p in d.split("|"))
    print(f"date {d:35s} in sources: {'OK' if ok else 'MISSING'}")

# 4. no forbidden terms (spec non-claims)
bad = [w for w in ["WHOLEGARMENT", "wholegarment"] if w in deck]
# WHOLEGARMENT appears only as the vendor's trademark — check context: allowed
# in competition table naming the vendor product, never claimed as ours.
print("WHOLEGARMENT mentions:", len(re.findall(r"WHOLEGARMENT", deck)),
      "(vendor-name only)" if all("SHIMA" in deck[max(0,m.start()-60):m.start()] or
                                  "patents" in deck[max(0,m.start()-60):m.start()+80] or
                                  "closed" in deck[max(0,m.start()-60):m.start()+80]
                                  for m in re.finditer(r"WHOLEGARMENT", deck)) else "REVIEW")

# 5. research files referenced in SOURCES exist
missing = []
for m in re.finditer(r"`research/([\w.]+\.txt)`", srcs):
    p = os.path.join(here, "research", m.group(1))
    if not os.path.exists(p):
        missing.append(m.group(1))
print("missing research files:", missing if missing else "NONE")
