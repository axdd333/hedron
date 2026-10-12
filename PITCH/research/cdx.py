#!/usr/bin/env python3
"""CDX search: what snapshots exist for a URL? Usage: cdx.py <url-suffix-pattern>"""
import sys, urllib.request, json

q = sys.argv[1]
url = f"https://web.archive.org/cdx/search/cdx?url={q}&output=json&limit=12&filter=statuscode:200&collapse=digest"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
rows = json.loads(urllib.request.urlopen(req, timeout=45).read().decode())
for r in rows[1:]:
    print(r[1], r[2])
