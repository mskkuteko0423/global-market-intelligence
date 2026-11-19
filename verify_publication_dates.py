
#!/usr/bin/env python3
"""Classify publisher-declared publication dates without guessing missing dates."""
import datetime as dt
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

FILE = Path(__file__).resolve().parent / 'data' / 'official_pilot.json'
MAX_PAGES = 150
MAX_BYTES = 900_000

class Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.jsonld = []
        self.in_ld = False
        self.buf = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta':
            key = (a.get('property') or a.get('name') or a.get('itemprop') or '').lower()
            if key and a.get('content'):
                self.meta.setdefault(key, []).append(a['content'])
        if tag == 'script' and 'ld+json' in a.get('type', '').lower():
            self.in_ld = True
            self.buf = []
    def handle_data(self, data):
        if self.in_ld:
            self.buf.append(data)
    def handle_endtag(self, tag):
        if tag == 'script' and self.in_ld:
            self.jsonld.append(''.join(self.buf))
            self.in_ld = False

def date_only(value):
    if not isinstance(value, str):
        return None
    m = re.match(r'^(20\d\d-\d\d-\d\d)(?:T|\s|$)', value.strip())
    if not m:
        return None
    try:
        d = dt.date.fromisoformat(m.group(1))
        if dt.date(2000, 1, 1) <= d <= dt.datetime.now(dt.timezone.utc).date():
            return d.isoformat()
    except ValueError:
        pass
    return None

def json_dates(node):
    found = []
    if isinstance(node, list):
        for item in node:
            found.extend(json_dates(item))
    elif isinstance(node, dict):
        types = node.get('@type', [])
        if isinstance(types, str):
            types = [types]
        if any(t.lower() in ('article', 'newsarticle', 'blogposting', 'analysisnewsarticle', 'report')
               for t in types if isinstance(t, str)):
            d = date_only(node.get('datePublished'))
            if d:
                found.append(d)
        for key in ('@graph', 'mainEntity'):
            if key in node:
                found.extend(json_dates(node[key]))
    return found

def classify(meta, structured):
    """Return (date, status, evidence); disagreement never becomes a date."""
    m, s = set(meta), set(structured)
    all_dates = m | s
    if not all_dates:
        return None, 'unknown', 'no_publication_metadata'
    if len(all_dates) > 1:
        return None, 'unknown', 'conflicting_publication_metadata'
    date = next(iter(all_dates))
    if m and s:
        return date, 'publisher_metadata_crosschecked', 'matching_article_metadata_and_jsonld'
    source = 'html_meta' if m else 'article_jsonld'
    return date, 'publisher_declared_unverified', source

def check(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname:
        return None, 'unknown', 'invalid_url'
    req = Request(url, headers={'User-Agent': 'GMIResearchPilot/3.0'})
    with urlopen(req, timeout=7) as response:
        target = urlsplit(response.geturl())
        host, final = p.hostname.lower(), (target.hostname or '').lower()
        if not (final == host or final.endswith('.' + host) or host.endswith('.' + final)):
            return None, 'unknown', 'cross_host_redirect'
        if 'text/html' not in response.headers.get('Content-Type', '').lower():
            return None, 'unknown', 'not_html'
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return None, 'unknown', 'too_large'
        page = raw.decode(response.headers.get_content_charset() or 'utf-8', 'replace')
    parser = Metadata()
    parser.feed(page)
    meta = []
    for key in ('article:published_time', 'datepublished', 'pubdate', 'dc.date.issued'):
        meta.extend(d for x in parser.meta.get(key, []) if (d := date_only(x)))
    structured = []
    for block in parser.jsonld:
        try:
            structured.extend(json_dates(json.loads(block)))
        except (ValueError, TypeError):
            pass
    return classify(meta, structured)

def main():
    data = json.loads(FILE.read_text(encoding='utf-8'))
    counts = Counter()
    reasons = Counter()
    examined = 0
    for row in data.get('articles', []):
        if row.get('page_type') != 'article_candidate' or not row.get('official_url'):
            continue
        if examined >= MAX_PAGES:
            break
        examined += 1
        try:
            date, status, evidence = check(row['official_url'])
        except Exception as exc:
            date, status, evidence = None, 'unknown', 'fetch_' + type(exc).__name__
        row['published'] = date
        row['date_status'] = status
        row['publication_date_status'] = status
        if date:
            row['publication_date_evidence'] = evidence
        else:
            row.pop('publication_date_evidence', None)
            reasons[evidence] += 1
        counts[status] += 1
    verified = counts['publisher_metadata_crosschecked']
    declared = counts['publisher_declared_unverified']
    data['date_verification'] = {
        'examined': examined,
        'verified': verified,
        'publisher_declared_unverified': declared,
        'unknown': counts['unknown'],
        'unverified_reasons': dict(reasons),
        'method': 'Publisher page metadata: matching HTML meta + article JSON-LD = crosschecked; single source = publisher-declared, unverified; conflicting/missing = unknown'
    }
    data.setdefault('archive_quality', {})['published_dates_verified'] = verified
    data['archive_quality']['published_dates_declared_unverified'] = declared
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('DATE_VERIFICATION', json.dumps(data['date_verification'], ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
