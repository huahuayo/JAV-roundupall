"""Scan magnet-saved library folders for actress directories and magnet TXT files."""



from __future__ import annotations



import re

from pathlib import Path



from src.library_location_settings import load_library_locations
from src.sync_folder_rename import (
    is_sync_complete_folder as is_magnet_saved_complete_folder,
    strip_sync_status_prefix as strip_magnet_sync_status_prefix,
)
from src.sync_folder_rename import apply_sync_folder_renames as apply_magnet_saved_folder_renames
from src.sync_folder_rename import rename_sync_folder as rename_magnet_saved_folder

from src.parser import (

    build_magnet_code_media_info,

    code_sort_key,

    extract_code_from_magnet_line,

    extract_code_from_text,

    has_subtitle_in_magnet_line,

    is_4k_in_magnet_line,

    normalize_code,

)



MAGNET_SAVED_KEY = "magnet_saved"

STORAGE_115_PREFIX = re.compile(r"^(\d+)\s+")

TRAILING_COUNT_SUFFIX = re.compile(r"\s+\d+$")





def parse_magnet_saved_folder_name(raw_name: str) -> dict[str, str]:

    """Parse folder naming conventions for storage type and actress matching."""

    raw = str(raw_name or "").strip()

    base = strip_magnet_sync_status_prefix(raw)



    storage_type = "local_magnet"

    storage_prefix = ""

    match_115 = STORAGE_115_PREFIX.match(base)

    if match_115:

        storage_type = "115"

        storage_prefix = match_115.group(1)

        base = base[match_115.end() :].strip()



    actress_match_name = TRAILING_COUNT_SUFFIX.sub("", base).strip() or base.strip()



    return {

        "folder_name": raw,

        "base_name": base,

        "actress_match_name": actress_match_name,

        "storage_type": storage_type,

        "storage_prefix": storage_prefix,

    }





def scan_folder_subtitle_codes(folder_path: Path) -> set[str]:

    codes: set[str] = set()

    for pattern in ("*.srt", "*.ass"):

        for file_path in folder_path.glob(pattern):

            code = extract_code_from_text(file_path.stem)

            if code:

                codes.add(normalize_code(code))

    return codes





def scan_magnet_saved_folders(roots: list[str] | None = None) -> tuple[list[dict], list[str]]:

    """Return folder records with extracted codes and scanned root paths."""

    if roots is None:

        roots = load_library_locations().get(MAGNET_SAVED_KEY, [])



    folders: list[dict] = []

    valid_roots: list[str] = []

    seen_names: set[str] = set()



    for root in roots:

        root_path = Path(root)

        if not root_path.is_dir():

            continue

        valid_roots.append(str(root_path.resolve()))

        try:

            children = list(root_path.iterdir())

        except OSError:

            continue



        for child in children:

            if not child.is_dir():

                continue

            name = child.name.strip()

            if not name or name.startswith(".") or is_magnet_saved_complete_folder(name):

                continue



            txt_files = sorted(child.glob("*.txt"))

            if not txt_files:

                continue



            parsed = parse_magnet_saved_folder_name(name)

            subtitle_codes = scan_folder_subtitle_codes(child)

            buckets: dict[str, dict] = {}



            for txt_path in txt_files:

                if txt_path.name.startswith("磁链已保存同步"):

                    continue

                try:

                    content = txt_path.read_text(encoding="utf-8", errors="replace")

                except OSError:

                    continue

                for line_no, raw_line in enumerate(content.splitlines(), start=1):

                    line = raw_line.strip()

                    if not line or line.startswith("#"):

                        continue

                    code = extract_code_from_magnet_line(line)

                    if not code:

                        continue



                    normalized = normalize_code(code)

                    is_4k = is_4k_in_magnet_line(line)

                    has_sub_magnet = has_subtitle_in_magnet_line(line, normalized)

                    bucket = buckets.setdefault(

                        normalized,

                        {

                            "has_4k_magnet": False,

                            "has_subtitle_magnet": False,

                            "has_non_4k_subtitle_magnet": False,

                            "source_file": txt_path.name,

                            "source_line": line_no,

                            "raw_line": line[:500],

                        },

                    )



                    if is_4k:

                        bucket["has_4k_magnet"] = True

                    if has_sub_magnet:

                        bucket["has_subtitle_magnet"] = True

                        if not is_4k:

                            bucket["has_non_4k_subtitle_magnet"] = True



            codes: list[dict] = []

            for normalized, bucket in buckets.items():

                codes.append(

                    build_magnet_code_media_info(

                        code=normalized,

                        has_4k_magnet=bool(bucket["has_4k_magnet"]),

                        has_subtitle_magnet=bool(bucket["has_subtitle_magnet"]),

                        has_non_4k_subtitle_magnet=bool(bucket["has_non_4k_subtitle_magnet"]),

                        has_subtitle_file=normalized in subtitle_codes,

                        source_file=str(bucket["source_file"]),

                        source_line=int(bucket["source_line"]),

                        raw_line=str(bucket["raw_line"]),

                    )

                )



            if not codes:

                continue



            codes.sort(key=lambda item: code_sort_key(str(item.get("code") or "")))



            key = name.casefold()

            if key in seen_names:

                continue

            seen_names.add(key)



            folders.append(

                {

                    "folder_name": name,

                    "folder_path": str(child.resolve()),

                    "root": str(root_path.resolve()),

                    "codes": codes,

                    "txt_files": [p.name for p in txt_files if not p.name.startswith("磁链已保存同步")],

                    "actress_match_name": parsed["actress_match_name"],

                    "storage_type": parsed["storage_type"],

                    "storage_prefix": parsed["storage_prefix"],

                    "base_name": parsed["base_name"],

                }

            )



    return folders, valid_roots


