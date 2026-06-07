import re
import urllib.request

code = "IPZZ-576"
url = f"https://18mag.net/search?q={code}"
req = urllib.request.Request(
    url,
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
)
html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="replace")
print("len", len(html))
# find result links
for m in re.finditer(r'href="(/[^"]+)"[^>]*>([^<]*IPZZ[^<]*)', html, re.I):
    print("link", m.group(1)[:80], m.group(2)[:60])

for title in ["IPZZ-576-C", "IPZZ-576ch", "ipzz-576ch"]:
    if title.lower() in html.lower():
        print("found title", title)

# detail page probe
detail_urls = re.findall(r'href="(/magnet/[^"]+)"', html)
print("magnet paths", len(detail_urls), detail_urls[:5])

out = __file__.replace("probe_18mag.py", "18mag_sample.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print("wrote", out)

for pat in ["576-C", "576ch", "magnet:", "btih", "search", "result", "18mag"]:
    print(pat, html.lower().count(pat.lower()))
