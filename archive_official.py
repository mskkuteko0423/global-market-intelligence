#!/usr/bin/env python3
"""Merge official article candidates without confusing discovery and publication dates."""
import datetime as dt
import json
import pathlib
import re
from urllib.parse import urlsplit, urlunsplit

ROOT = pathlib.Path(__file__).resolve().parent
CURRENT = ROOT / 'data' / 'official_pilot.json'
PREVIOUS = pathlib.Path('/tmp/gmi_previous_official.json')


def read_data(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('articles', []), list):
        raise ValueError(f'Invalid archive: {path}')
    return data


def article_key(record):
    url = record.get('official_url', '')
    if not isinstance(url, str):
        return ''
    p = urlsplit(url.strip())
    if p.scheme.lower() != 'https' or not p.hostname:
        return ''
    return urlunsplit(('https', p.netloc.lower(), p.path.rstrip('/') or '/', '', ''))


def valid_article(record):
    return (isinstance(record, dict) and record.get('page_type') == 'article_candidate'
            and bool(record.get('excerpt')) and bool(article_key(record)))


def valid_day(value):
    if not isinstance(value, str) or not re.fullmatch(r'20\d{2}-\d{2}-\d{2}', value):
        return None
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def merge_record(old, new):
    merged = dict(old)
    for key, value in new.items():
        if value not in (None, '', [], {}):
            merged[key] = value
    for field in ('title_ja', 'excerpt_ja'):
        if old.get(field) and not new.get(field):
            merged[field] = old[field]
    if merged.get('excerpt_ja'):
        merged['japanese_status'] = 'machine_translation_of_partial_excerpt_not_summary'
    return merged


def main():
    previous, current = read_data(PREVIOUS), read_data(CURRENT)
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    archive = {}
    for item in previous.get('articles', []):
        if valid_article(item):
            archive[article_key(item)] = dict(item)
    old_count = len(archive)
    added = updated = 0
    for item in current.get('articles', []):
        if not valid_article(item):
            continue
        key = article_key(item)
        if key in archive:
            archive[key] = merge_record(archive[key], item)
            updated += 1
        else:
            archive[key] = dict(item)
            added += 1
    if not archive:
        raise RuntimeError('No valid articles; refusing empty publication')

    for item in archive.values():
        # Existing archived items cannot have their original discovery date reconstructed.
        # Use the first date this tracking version observes them, with explicit provenance.
        existing_first = valid_day(item.get('first_seen'))
        item['first_seen'] = existing_first or today
        item['first_seen_status'] = ('recorded_by_gmi' if existing_first or article_key(item) not in
                                     {article_key(x) for x in previous.get('articles', []) if valid_article(x)}
                                     else 'tracking_started_after_initial_discovery')
        item['last_seen'] = today if article_key(item) in {
            article_key(x) for x in current.get('articles', []) if valid_article(x)
        } else (valid_day(item.get('last_seen')) or item['first_seen'])
        # A machine-detected publication date is NOT automatically independently verified.
        item['publication_date_status'] = ('detected_unverified' if valid_day(item.get('published'))
                                           else 'unknown')
        item['is_verified_new'] = False

    result = dict(current)
    result['articles'] = list(archive.values())
    result['archive_enabled'] = True
    result['archive_count'] = len(archive)
    result['archive_note'] = ('first_seen is a GMI tracking date, never a publication date; '
                              'historical first discovery may be unknown. Publication dates '
                              'require independent verification. Excerpts are partial machine translations.')
    CURRENT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'ARCHIVE_RESULT previous={old_count} added={added} updated={updated} total={len(archive)}', flush=True)
    print(f'DATE_TRACKING first_seen={today} verified_new=0', flush=True)


if __name__ == '__main__':
    main()
