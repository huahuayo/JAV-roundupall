import re
import urllib.request

req = urllib.request.Request(
    "https://javdb.com/",
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
)
html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="replace")
print("len", len(html))
for pat in [
    r'id="videos"[^>]*class="([^"]*)"',
    r'id="videos"[\s\S]{0,500}',
    r'grid-item',
    r'class="box"',
    r'is-one-quarter',
    r'class="container[^"]*"',
]:
    m = re.search(pat, html)
    print(pat, "->", (m.group(0)[:200] if m else "NOT FOUND"))
