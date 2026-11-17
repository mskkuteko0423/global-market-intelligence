
#!/usr/bin/env python3
"""GMI official article archive merger."""
import json
import pathlib
from urllib.parse import urlsplit, urlunsplit

ROOT = pathlib.Path(__file__).resolve().parent
CURRENT = ROOT / "data" / "official_pilot.json"
PREVIOUS = pathlib.Path("/tmp/gmi_previous_official.json")


def read_data(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    if not isinstance(data.get("articles", []), list):
        raise ValueError(f"Invalid articles list: {path}")
    return data


def article_key(record):
    url = record.get("official_url", "")
    if not isinstance(url, str):
        return ""
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or not parts.hostname:
        return ""
    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path.rstrip("/") or "/",
        "",
        ""
    ))


def valid_article(record):
    return (
        isinstance(record, dict)
        and record.get("page_type") == "article_candidate"
        and bool(record.get("excerpt"))
        and bool(article_key(record))
    )


def merge_record(old, new):
    merged = dict(old)

    for key, value in new.items():
        if value not in (None, "", [], {}):
            merged[key] = value

    # Preserve earlier translations when the latest run
    # reaches its translation limit.
    for field in ("title_ja", "excerpt_ja"):
        if old.get(field) and not new.get(field):
            merged[field] = old[field]

    if merged.get("excerpt_ja"):
        merged["japanese_status"] = (
            "machine_translation_of_partial_excerpt_not_summary"
        )

    return merged


def main():
    previous = read_data(PREVIOUS)
    current = read_data(CURRENT)

    archive = {}

    for record in previous.get("articles", []):
        if valid_article(record):
            archive[article_key(record)] = record

    old_count = len(archive)
    new_count = 0
    updated_count = 0

    for record in current.get("articles", []):
        if not valid_article(record):
            continue

        key = article_key(record)

        if key in archive:
            archive[key] = merge_record(archive[key], record)
            updated_count += 1
        else:
            archive[key] = record
            new_count += 1

    if not archive:
        raise RuntimeError(
            "No valid articles available; refusing empty publication"
        )

    result = dict(current)
    result["articles"] = list(archive.values())
    result["archive_enabled"] = True
    result["archive_count"] = len(archive)
    result["archive_note"] = (
        "Official article candidates; dates and categories "
        "may require verification. Japanese text is a "
        "machine translation of partial excerpts, not a summary."
    )

    CURRENT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )

    print(
        f"ARCHIVE_RESULT previous={old_count} "
        f"added={new_count} updated={updated_count} "
        f"total={len(archive)}",
        flush=True
    )


if __name__ == "__main__":
    main()
