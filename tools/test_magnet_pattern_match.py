from src.magnet_pattern_match import matches_pattern

CODE = "IPZZ-576"


def check(pattern: str, title: str, expected: bool) -> None:
    got = matches_pattern(title, pattern, CODE)
    assert got == expected, f"{pattern!r} vs {title!r} => {got}, want {expected}"


def main() -> None:
    check("{CODE}-C", "IPZZ-576-C", True)
    check("{CODE}-C", "IPZZ-576-c", True)
    check("{CODE}-c", "IPZZ-576-C", True)
    check("{CODE}-C", "IPZZ-576", False)
    check("{CODE}", "IPZZ-576-C", False)
    check("{code}-c", "ipzz-576-c", True)
    check("{code}-c", "ipzz-576-C", True)
    check("{code}-C", "IPZZ-576-C", True)
    check("{code}-C", "ipzz-576-c", True)
    check("{CODE}-C.mp4", "IPZZ-576-c.mp4", True)
    print("all pattern match tests passed")


if __name__ == "__main__":
    main()
