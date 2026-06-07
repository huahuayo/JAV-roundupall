"""Fail release packaging if private paths or config files are bundled."""

from __future__ import annotations

import sys
from pathlib import Path

FORBIDDEN_SUFFIXES = {".db", ".json", ".env"}
FORBIDDEN_NAMES = {
    "config.json",
    "jav_manager_state.db",
    "library.db",
}
SENSITIVE_MARKERS = (
    "pytest-of-",
    "192.168.",
    "\\users\\",
    ":\\\\",
    "liupeng",
    "huahuayo",
)


def scan_release(root: Path) -> list[str]:
    issues: list[str] = []
    if not root.is_dir():
        return [f"Release folder missing: {root}"]

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        if path.name.lower() in FORBIDDEN_NAMES:
            issues.append(f"Forbidden file in release: {path.relative_to(root)}")
            continue
        if path.suffix.lower() == ".db":
            issues.append(f"Forbidden database in release: {path.relative_to(root)}")
            continue
        if path.name.lower() == "config.json":
            issues.append(f"Forbidden config in release: {path.relative_to(root)}")
            continue
        if path.suffix.lower() in {".txt", ".log", ".md"} and path.parent == root:
            if name not in {"user_guide.txt"}:
                issues.append(f"Unexpected root text file: {path.name}")

        try:
            if path.suffix.lower() in {".txt", ".js", ".html", ".json", ".bat"}:
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
            elif path.suffix.lower() == ".exe":
                continue
            else:
                continue
            if "pytest-of-" in text or "192.168." in text:
                issues.append(f"Sensitive path marker in {path.relative_to(root)}")
        except OSError:
            continue
    return issues


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python packaging/verify_release.py <release-folder>")
    root = Path(sys.argv[1]).resolve()
    issues = scan_release(root)
    if issues:
        print("Release verification FAILED:")
        for item in issues:
            print(f"  - {item}")
        raise SystemExit(1)
    print(f"Release verification OK: {root}")


if __name__ == "__main__":
    main()
