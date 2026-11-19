#!/usr/bin/env python3
"""GMI official-article archive: conservative deduplication and date provenance."""
import datetime as dt
import json
import pathlib
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

ROOT = pathlib.Path(__file__).resolve().parent
CURRENT = ROOT / "data" / "official_pilot.json"
PREVIOUS = pathlib.Path("/tmp/gmi_previous_official.json")
TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
            "utm_content", "fbclid", "gclid", "mc_cid", "mc_eid"}

def read_data(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("articles", []), list):
        raise ValueError(f"Invalid archive: {path}")
    return data

def article_key(record):
    url = record.get("official_url", "")
    if not isinstance(url, str):
        return ""
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return ""
    if p.scheme.lower() != "https" or not p.hostname:
        return ""
    host = p.hostname.lower()
    if p.port and p.port != 443:
        host += ":" + str(p.port)
    path = re.sub(r"/+", "/", p.path).rstrip("/") or "/"
    # Query parameters can identify genuinely different articles; remove tracking only.
    query = urlencode(sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                             if k.lower() not in TRACKING and not k.lower().startswith("utm_")))
    return urlunsplit(("https", host, path, query, ""))

def valid_article(item):
    return (isinstance(item, dict) and item.get("page_type") == "article_candidate"
            and bool(item.get("excerpt")) and bool(article_key(item)))

def valid_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", value):
        return None
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        return None

def merge_record(old, new):
    merged = dict(old)
    for key, value in new.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    for field in ("title_ja", "excerpt_ja"):
        if old.get(field) and not new.get(field):
            merged[field] = old[field]
    if merged.get("excerpt_ja"):
        merged["japanese_status"] = "machine_translation_of_partial_excerpt_not_summary"
    return merged

def main():
    previous, current = read_data(PREVIOUS), read_data(CURRENT)
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    archive = {}
    previous_keys = set()
    current_keys = set()
    duplicates_previous = duplicates_current = 0
    for item in previous.get("articles", []):
        if valid_article(item):
            key = article_key(item)
            if key in archive:
                duplicates_previous += 1
                archive[key] = merge_record(archive[key], item)
            else:
                archive[key] = dict(item)
            previous_keys.add(key)
    old_count = len(archive)
    added = updated = 0
    for item in current.get("articles", []):
        if not valid_article(item):
            continue
        key = article_key(item)
        if key in current_keys:
            duplicates_current += 1
        current_keys.add(key)
        if key in archive:
            archive[key] = merge_record(archive[key], item)
            updated += 1
        else:
            archive[key] = dict(item)
            added += 1
    if not archive:
        raise RuntimeError("No valid articles; refusing empty publication")
    for key, item in archive.items():
        first = valid_day(item.get("first_seen"))
        item["first_seen"] = first or today
        item["first_seen_status"] = ("recorded_by_gmi" if first or key not in previous_keys
                                     else "tracking_started_after_initial_discovery")
        item["last_seen"] = today if key in current_keys else (
            valid_day(item.get("last_seen")) or item["first_seen"])
        candidate = valid_day(item.get("published")) or valid_day(item.get("published_candidate"))
        if candidate:
            item["published_candidate"] = candidate
        item["published"] = None
        item["date_status"] = "unverified"
        item["publication_date_status"] = "unknown"
        item["is_verified_new"] = False
    result = dict(current)
    result["articles"] = list(archive.values())
    result["archive_enabled"] = True
    result["archive_count"] = len(archive)
    result["archive_quality"] = {
        "previous_unique": old_count,
        "new_unique": added,
        "current_unique": len(current_keys),
        "duplicate_urls_previous": duplicates_previous,
        "duplicate_urls_current": duplicates_current,
        "total_unique": len(archive),
        "published_dates_verified": 0,
        "translation_available": sum(bool(x.get("excerpt_ja")) for x in archive.values()),
    }
    result["archive_note"] = ("first_seen is a GMI tracking date, never a publication date. "
        "Unverified dates remain published_candidate, never displayed as confirmed. "
        "Excerpts are partial and machine translations are not full-article summaries.")
    CURRENT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ARCHIVE_RESULT previous={old_count} added={added} updated={updated} total={len(archive)}")
    print("ARCHIVE_QUALITY", json.dumps(result["archive_quality"], ensure_ascii=False))

if __name__ == "__main__":
    main()
