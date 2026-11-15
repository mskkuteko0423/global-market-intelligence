#!/usr/bin/env python3
"""Read-only test of public official insight pages; no paid APIs.
Writes data/official_pilot.json without changing existing reports.
"""
import datetime as dt
import json
import pathlib
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'official_pilot.json'
SITES = [
    ('Goldman Sachs', 'https://www.goldmansachs.com/insights/', 'goldmansachs.com'),
    ('J.P. Morgan Asset Management', 'https://am.jpmorgan.com/us/en/asset-management/adv/insights/', 'jpmorgan.com'),
    ('Morgan Stanley', 'https://www.morganstanley.com/insights', 'morganstanley.com'),
]
MAX_PER_FIRM = 3
MAX_BYTES = 2_500_000
BLOCKED = ('/privacy', '/contact', '/terms', '/login', '/subscribe', '/cookie', '/careers', '/about-us')
TOPICS = ('insight', 'article', 'market', 'research', 'idea', 'outlook', 'investment', 'econom', 'technology', 'ai-', 'thought-leadership')


def allowed(url, domain):
    p = urlparse(url)
    h = (p.hostname or '').lower()
    return p.scheme == 'https' and (h == domain or h.endswith('.' + domain))


def get_html(url, domain):
    if not allowed(url, domain):
        raise ValueError('Non-official input URL')
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; GMIResearchPilot/2.0)'})
    with urlopen(req, timeout=15) as resp:
        final = resp.geturl()
        if not allowed(final, domain):
            raise ValueError('Redirect outside official domain')
        if 'text/html' not in resp.headers.get('Content-Type', '').lower():
            raise ValueError('Not an HTML response')
        body = resp.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError('HTML exceeds 2.5 MB')
        charset = resp.headers.get_content_charset() or 'utf-8'
        return body.decode(charset, errors='replace'), len(body)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.href = None
        self.depth = 0
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style'):
            self.skip += 1
        if tag == 'a' and self.href is None:
            self.href = a.get('href')
            self.parts = []
            self.depth = 1
        elif self.href is not None:
            self.depth += 1
        if self.href is not None and tag == 'img' and a.get('alt'):
            self.parts.append(a['alt'])

    def handle_data(self, data):
        if self.href is not None and not self.skip:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if self.href is not None:
            self.depth -= 1
            if self.depth <= 0:
                title = re.sub(r'\s+', ' ', ''.join(self.parts)).strip()
                if title:
                    self.links.append((self.href, title))
                self.href, self.parts, self.depth = None, [], 0
        if tag in ('script', 'style') and self.skip:
            self.skip -= 1


class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.in_p = False
        self.parts = []
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'footer', 'header', 'aside'):
            self.skip += 1
        if tag == 'p' and not self.skip:
            self.in_p = True
            self.current = []

    def handle_data(self, data):
        if self.in_p and not self.skip:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == 'p' and self.in_p:
            value = re.sub(r'\s+', ' ', ''.join(self.current)).strip()
            if len(value) >= 75 and value not in self.parts:
                self.parts.append(value)
            self.in_p = False
            self.current = []
        if tag in ('script', 'style', 'nav', 'footer', 'header', 'aside') and self.skip:
            self.skip -= 1


def main():
    articles, stats = [], []
    for firm, index, domain in SITES:
        found = extracted = raw_links = 0
        error = None
        try:
            html, nbytes = get_html(index, domain)
            parser = Links()
            parser.feed(html)
            raw_links = len(parser.links)
            seen = set()
            for href, title in parser.links:
                url = urljoin(index, href).split('#')[0]
                path = urlparse(url).path.lower().rstrip('/')
                if not allowed(url, domain) or url.rstrip('/') == index.rstrip('/') or url in seen:
                    continue
                if len(title) < 24 or len(title) > 180:
                    continue
                if any(x in path for x in BLOCKED) or not any(x in path for x in TOPICS):
                    continue
                seen.add(url)
                found += 1
                excerpt, note = '', ''
                try:
                    article_html, _ = get_html(url, domain)
                    paragraphs = Paragraphs()
                    paragraphs.feed(article_html)
                    if len(paragraphs.parts) >= 2:
                        excerpt = ' '.join(paragraphs.parts[:5])[:1800]
                        extracted += 1
                    else:
                        note = 'Insufficient paragraphs; not confirmed as article body'
                except Exception as exc:
                    note = f'{type(exc).__name__}: {exc}'[:180]
                articles.append({'firm': firm, 'title': title, 'official_url': url,
                                 'excerpt': excerpt, 'excerpt_status': 'Unverified page excerpt (not a summary)' if excerpt else 'Not extracted',
                                 'error': note})
                if found >= MAX_PER_FIRM:
                    break
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'[:180]
        stats.append({'firm': firm, 'index_links': raw_links,
                      'official_url_candidates': found, 'extracted': extracted, 'error': error})
        print(f'{firm}: index_links {raw_links}; official URL candidates {found}; extracted {extracted}; error {error or "none"}', flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'updated': dt.datetime.now(dt.timezone.utc).isoformat(),
                               'pilot': True, 'stats': stats, 'articles': articles},
                              ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved', OUT)


if __name__ == '__main__':
    main()
