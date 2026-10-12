#!/usr/bin/env python3
"""Save raw HTML for a URL and list its navigation links.
Usage: rawlinks.py <url> <out.html>
"""
import re, sys, urllib.request

url, out = sys.argv[1], sys.argv[2]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
req = urllib.request.Request(url, headers={"User-Agent": UA})
raw = urllib.request.urlopen(req, timeout=30).read()
open(out, "wb").write(raw)
print(f"saved {len(raw)} bytes -> {out}")

skip = (".css", ".js", ".png", ".jpg", ".svg", "ico", "font", "mailto",
        "facebook", "twitter", "instagram", "linkedin", "youtu")
seen = set()
for h in re.findall(r'href="([^"]+)"', raw.decode("utf-8", errors="replace")):
    if h.startswith("#") or any(k in h for k in skip):
        continue
    if h in seen:
        continue
    seen.add(h)
    print(h)
