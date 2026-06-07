import re
import urllib.request

BASE = "https://18mag.net"

def fetch(path):
    url = path if path.startswith("http") else BASE + path
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="replace")

# IPZZ-576-C from sample
html = fetch("/!jOOu")
print("detail len", len(html))
print("magnet:", "magnet:?" in html)
m = re.search(r'magnet:\?xt=[^\s"<>]+', html)
print("magnet sample", (m.group(0)[:120] if m else "none"))
# file list
for row in re.finditer(r"<tr[^>]*>[\s\S]*?</tr>", html):
    t = re.sub(r"<[^>]+>", " ", row.group(0))
    t = re.sub(r"\s+", " ", t).strip()
    if ".mp4" in t.lower() or ".txt" in t.lower() or "文件" in t:
        print("row:", t[:120])

# actress
for pat in [r"演员[^<]*</[^>]+>[^<]*<[^>]+>([^<]+)", r"明里", r"影片信息"]:
    m = re.search(pat, html)
    print(pat, bool(m), m.group(0)[:80] if m else "")

with open(__file__.replace("probe_18mag_detail.py", "18mag_detail.html"), "w", encoding="utf-8") as f:
    f.write(html)
