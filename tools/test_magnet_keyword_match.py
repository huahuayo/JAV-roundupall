from src.magnet_keyword_match import match_preview_keyword_content


def check(files: list[str], keywords: list[str], expected: bool) -> None:
    got = match_preview_keyword_content(files, keywords)
    assert got == expected, f"files={files!r} keywords={keywords!r} => {got}, want {expected}"


def main() -> None:
    check(["最新电影抢先看.mp4"], ["最新"], True)
    check(["最 新 电 影 抢 先 看.mp4"], ["最新"], True)
    check(["最 新 电 影 抢 先 看.mp4"], ["最 新"], True)
    check(["社区最新情报.mp4"], ["社区最新情报"], True)
    check(["社 区 最 新 情 报.mp4"], ["社区最新情报"], True)
    check(["SSIS-204-C.mp4", "xuu62.com.mp4"], ["最新"], False)
    check(["SSIS-204-C.mp4", "最 新 位 址 获 取.txt"], ["最新"], True)
    check(["a.mp4", "b.mp4"], ["最新", "情报"], False)
    check(["最新情报.mp4"], ["最新", "情报"], True)
    print("all keyword match tests passed")


if __name__ == "__main__":
    main()
