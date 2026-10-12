#!/usr/bin/env python3
"""Direct page fetcher for investor research. Saves text per URL to research/ dir.
Usage: fetch.py <batch_file>  where batch_file has lines:  slug|URL
Fallbacks per URL: 1) direct GET  2) r.jina.ai proxy  3) wayback latest snapshot.
"""
import sys, os, re, json, urllib.request, urllib.error, ssl

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "research")
os.makedirs(OUT, exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
CTX = ssl.create_default_context()  # standard verification; no insecure fallback needed

def get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.status, r.read()

class Redirect308(urllib.request.HTTPRedirectHandler):
    """urllib's default handler misses 308; follow it explicitly."""

OPENER = urllib.request.build_opener(Redirect308)

def get2(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with OPENER.open(req, timeout=timeout) as r:
        return r.status, r.read()

def html_to_text(raw):
    try:
        s = raw.decode("utf-8", errors="replace")
    except Exception:
        return ""
    s = re.sub(r"<script[\s\S]*?</script>", " ", s, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", " ", s, flags=re.I)
    s = re.sub(r"<(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&#0?39;|&rsquo;", "'", s)
    s = re.sub(r"&#0?38;|&quot;|&ldquo;|&rdquo;", '"', s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()

def fetch_one(url):
    # 1) direct
    try:
        st, raw = get2(url)
        txt = html_to_text(raw)
        if txt and len(txt) > 400:
            return txt, f"direct {st}"
    except Exception as e:
        first_err = f"direct: {type(e).__name__} {e}"
    else:
        first_err = "direct: short/empty body"
    # 2) jina proxy
    try:
        st, raw = get("https://r.jina.ai/" + url, timeout=40)
        txt = raw.decode("utf-8", errors="replace")
        if txt and len(txt) > 200:
            return txt, f"jina {st}"
    except Exception as e:
        jina_err = f"jina: {type(e).__name__} {e}"
    else:
        jina_err = "jina: short/empty"
    # 3) wayback latest
    try:
        st, raw = get("https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe=""))
        avail = json.loads(raw.decode("utf-8", errors="replace"))
        snap = (avail.get("archived_snapshots") or {}).get("closest", {}).get("url")
        if not snap:
            raise ValueError("no snapshot")
        st, raw = get(snap, timeout=40)
        txt = html_to_text(raw)
        if txt and len(txt) > 200:
            return txt, f"wayback {snap}"
        wb_err = "wayback: short body"
    except Exception as e:
        wb_err = f"wayback: {type(e).__name__} {e}"
    return None, f"{first_err}; {jina_err}; {wb_err}"

def main():
    batch = sys.argv[1]
    summary = []
    for line in open(batch):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        slug, url = line.split("|", 1)
        txt, how = fetch_one(url)
        if txt:
            with open(os.path.join(OUT, slug + ".txt"), "w") as f:
                f.write(f"URL: {url}\nFETCHED_VIA: {how}\n\n{txt}")
            summary.append(f"OK   {slug:28s} {len(txt):>7d}ch  {how[:70]}")
        else:
            summary.append(f"FAIL {slug:28s} --  {how}")
    print("\n".join(summary))

import urllib.parse
main()
