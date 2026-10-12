#!/usr/bin/env python3
"""Pull all links from a saved HTML file, filtered to likely navigation."""
import re, sys

raw = open(sys.argv[1], encoding="utf-8", errors="replace").read()
hrefs = re.findall(r'href="([^"]+)"', raw)
skip = (".css", ".js", ".png", ".jpg", ".svg", "ico", "font", "mailto",
        "facebook", "twitter", "instagram", "linkedin", "youtu")
seen = set()
for h in hrefs:
    if h.startswith("#") or any(k in h for k in skip):
        continue
    if h in seen:
        continue
    seen.add(h)
    print(h)
