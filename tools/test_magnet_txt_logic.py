"""Validate 18mag magnet selection rules against live pages for IPZZ-576."""

import re
import urllib.request

BASE = "https://18mag.net"
CODE = "IPZZ-576"

BAD = [
    re.compile(p, re.I)
    for p in [
        r"乐鱼体育",
        r"少女激情游戏",
        r"广告合作\.txt",
        r"日韩欧美国产同步",
        r"有趣台妹小视频",
    ]
]


def fetch(path: str) -> str:
    url = path if path.startswith("http") else BASE + path
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="replace")


def collapse(text: str) -> str:
    return re.sub(r"\s+", "", text).upper()


def parse_search_rows(html: str) -> list[dict[str, str]]:
    rows = []
    for match in re.finditer(r'<a href="(/![^"]+)">([\s\S]*?)</a>', html):
        block = match.group(2)
        block = re.split(r'<p class="sample"', block, maxsplit=1)[0]
        title = re.sub(r"<[^>]+>", "", block)
        title = re.sub(r"\s+", " ", title).strip()
        rows.append({"title": title, "path": match.group(1)})
    return rows


def parse_files(html: str) -> list[str]:
    files = []
    for block in re.findall(
        r'<table class="table table-hover file-list">[\s\S]*?</table>', html, flags=re.I
    ):
        if "文件" not in block:
            continue
        for row in re.findall(r"<tr><td>\s*([\s\S]*?)\s*</td><td", block):
            name = re.sub(r"<[^>]+>", "", row)
            name = re.sub(r"\s+", " ", name).strip()
            if name:
                files.append(name)
        break
    return files


def main() -> None:
    search = fetch(f"/search?q={CODE}")
    rows = parse_search_rows(search)
    p1 = [r for r in rows if collapse(r["title"]) == collapse(f"{CODE}-C")]
    p2 = [r for r in rows if collapse(r["title"]) == collapse(f"{CODE}ch")]
    print("p1 candidates", len(p1), [r["title"] for r in p1[:3]])
    print("p2 candidates", len(p2), [r["title"] for r in p2[:3]])

    if p1:
        detail = fetch(p1[0]["path"])
        files = parse_files(detail)
        print("p1 files", files)
        bad = any(p.search(f) for f in files for p in BAD)
        main_ok = any(collapse(f) == collapse(f"{CODE}-C.mp4") for f in files)
        print("p1 valid", main_ok and not bad)

    for idx, row in enumerate(p2):
        detail = fetch(row["path"])
        files = parse_files(detail)
        valid = len(files) == 1 and collapse(files[0]) == collapse(f"{CODE}ch.mp4")
        print(f"p2[{idx}] {row['title']!r} valid={valid} files={files}")


if __name__ == "__main__":
    main()
