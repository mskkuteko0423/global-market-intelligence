#!/usr/bin/env python3
"""GMI: broad-market official-publication discovery pilot (no paid APIs).
Read-only: writes data/official_pilot.json; never modifies reports.json.
Candidate labels are heuristic and must be checked against the source.
"""
import datetime as dt
import json
import pathlib
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.request import Request, urlopen

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'official_pilot.json'
SITES = [
    ('Goldman Sachs', 'https://www.goldmansachs.com/insights/', 'goldmansachs.com'),
    ('J.P. Morgan Asset Management', 'https://am.jpmorgan.com/us/en/asset-management/adv/insights/', 'jpmorgan.com'),
    ('Morgan Stanley', 'https://www.morganstanley.com/insights', 'morganstanley.com'),
]
MAX_PER_FIRM = 5
MAX_BYTES = 2_500_000
# Market-wide coverage: AI is just one topic, never a prerequisite.
CATEGORIES = {
    '株式': ('equity', 'equities', 'stock', 'earnings', 's&p', 'nasdaq'),
    '債券・金利': ('bond', 'fixed income', 'treasury', 'yield', 'interest rate', 'duration'),
    '為替': ('currency', 'currencies', 'forex', 'fx market', 'dollar', 'yen'),
    'マクロ経済': ('macro', 'econom', 'inflation', 'gdp', 'recession', 'growth', 'fed ', 'central bank'),
    'クレジット': ('credit', 'spread', 'high yield', 'private debt'),
    'コモディティ': ('commodity', 'commodities', 'oil price', 'gold price', 'energy market'),
    '投資戦略・資金フロー': ('portfolio', 'asset allocation', 'investor', 'market outlook', 'investment outlook', 'capital flow', 'liquidity', 'market'),
    '政策・地政学': ('geopolit', 'tariff', 'trade policy', 'fiscal policy', 'election'),
    'AI・半導体': ('artificial intelligence', ' ai ', 'semiconductor', 'chipmaker', 'data center'),
    'その他の産業テーマ': ('healthcare', 'technology', 'infrastructure', 'industry', 'sector'),
}
# Exclude clear non-publication destinations, not articles lacking an AI angle.
EXCLUDE_PATH = ('/privacy', '/contact', '/terms', '/login', '/cookie', '/careers', '/about-us',
                '/what-we-do/', '/investment-strategies/', '/products/', '/services/',
                '/account/', '/disclosures', '/legal/', '/investment-management')
EXCLUDE_TITLE = ('sign in', 'log in', 'contact us', 'privacy policy', 'cookie policy',
                 'separately managed accounts', 'commingled pension trust funds',
                 'college planning essentials', 'all investment management',
                 'global investment research', 'alternative and private markets')
PUBLICATION_PATH = ('/insights/', '/insights/articles/', '/insights/goldman-sachs-exchanges/',
                    '/market-insights/', '/research/', '/outlook/', '/articles/', '/commentary/')


def official(url, domain):
    p = urlparse(url)
    host = (p.hostname or '').lower()
    return p.scheme == 'https' and (host == domain or host.endswith('.' + domain))


def get_html(url, domain):
    if not official(url, domain):
        raise ValueError('URL outside verified official domain')
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; GMIResearchPilot/3.0)'})
    with urlopen(req, timeout=15) as response:
        final = response.geturl()
        if not official(final, domain):
            raise ValueError('Redirect outside verified official domain')
        if 'text/html' not in response.headers.get('Content-Type', '').lower():
            raise ValueError('Not HTML')
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('HTML exceeds size limit')
        return raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.meta = {}
        self.href = None
        self.anchor_depth = 0
        self.anchor_text = []
        self.skip_stack = []
        self.tag_stack = []
        self.p_depth = 0
        self.paragraph_text = []
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tag_stack.append(tag)
        if tag in ('script', 'style', 'nav', 'footer', 'header', 'aside'):
            self.skip_stack.append(len(self.tag_stack))
        if tag == 'meta':
            key = (a.get('property') or a.get('name') or '').lower()
            if key and a.get('content') and key not in self.meta:
                self.meta[key] = a['content'].strip()
        if tag == 'a' and self.href is None:
            self.href = a.get('href')
            self.anchor_depth = len(self.tag_stack)
            self.anchor_text = []
        if tag == 'img' and self.href is not None and a.get('alt'):
            self.anchor_text.append(a['alt'])
        if tag == 'p' and not self.skip_stack and not self.p_depth:
            self.p_depth = len(self.tag_stack)
            self.paragraph_text = []

    def handle_data(self, data):
        if self.href is not None and not self.skip_stack:
            self.anchor_text.append(data)
        if self.p_depth and not self.skip_stack:
            self.paragraph_text.append(data)

    def handle_endtag(self, tag):
        # Close the nearest matching tag; nested markup must not prematurely close anchors.
        if tag in self.tag_stack:
            depth = len(self.tag_stack) - self.tag_stack[::-1].index(tag)
        else:
            return
        if tag == 'a' and self.href is not None and depth == self.anchor_depth:
            title = re.sub(r'\s+', ' ', ''.join(self.anchor_text)).strip()
            if self.href and title:
                self.links.append((self.href, title))
            self.href = None
            self.anchor_text = []
            self.anchor_depth = 0
        if tag == 'p' and self.p_depth == depth:
            p = re.sub(r'\s+', ' ', ''.join(self.paragraph_text)).strip()
            if len(p) >= 75 and p not in self.paragraphs:
                self.paragraphs.append(p)
            self.p_depth = 0
            self.paragraph_text = []
        if self.skip_stack and self.skip_stack[-1] >= depth:
            self.skip_stack.pop()
        self.tag_stack = self.tag_stack[:depth - 1]


def parse(html):
    p = PageParser()
    p.feed(html)
    return p


def classify(text):
    normalized = ' ' + text.lower() + ' '
    return [name for name, terms in CATEGORIES.items() if any(term in normalized for term in terms)]


def candidates(parser, index, domain):
    seen = set()
    found = []
    for href, label in parser.links:
        url = urldefrag(urljoin(index, href))[0]
        path = urlparse(url).path.lower().rstrip('/')
        low_label = label.lower()
        if not official(url, domain) or url.rstrip('/') == index.rstrip('/') or url in seen:
            continue
        seen.add(url)
        if len(label) < 18 or len(label) > 220:
            continue
        if any(term in path for term in EXCLUDE_PATH) or any(term in low_label for term in EXCLUDE_TITLE):
            continue
        # Publication-like paths, not all links on an insights landing page.
        if not any(term in path + '/' for term in PUBLICATION_PATH):
            continue
        if path in ('/insights', '/research', '/market-insights'):
            continue
        found.append((url, label))
    return found


def main():
    stats, articles = [], []
    for firm, index, domain in SITES:
        error = None
        links = []
        extracted = 0
        try:
            index_parser = parse(get_html(index, domain))
            links = candidates(index_parser, index, domain)
            for url, anchor_title in links[:MAX_PER_FIRM]:
                record = {'firm': firm, 'official_url': url, 'link_title': anchor_title,
                          'title': anchor_title, 'published': None, 'categories': [],
                          'excerpt': '', 'excerpt_status': 'Not extracted',
                          'market_relevance': 'Needs human review', 'error': None}
                try:
                    page = parse(get_html(url, domain))
                    m = page.meta
                    record['title'] = m.get('og:title') or m.get('twitter:title') or anchor_title
                    record['published'] = (m.get('article:published_time') or
                                           m.get('datepublished') or m.get('date'))
                    # Use page title, metadata and first paragraphs for topic hints.
                    signal = ' '.join([record['title'], m.get('description', ''),
                                       m.get('og:description', ''), ' '.join(page.paragraphs[:3])])
                    record['categories'] = classify(signal)
                    if len(page.paragraphs) >= 2:
                        record['excerpt'] = ' '.join(page.paragraphs[:5])[:1800]
                        record['excerpt_status'] = 'Unverified page excerpt (not a summary)'
                        extracted += 1
                    else:
                        record['error'] = 'Fewer than 2 substantial paragraphs'
                    # Classify as candidate only: automated classification is not editorial verification.
                    record['market_relevance'] = ('Market-related candidate; review required'
                                                  if record['categories'] else 'Unclear; review required')
                except Exception as exc:
                    record['error'] = f'{type(exc).__name__}: {exc}'[:180]
                articles.append(record)
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'[:180]
        stats.append({'firm': firm, 'official_url_candidates': len(links),
                      'tested': min(len(links), MAX_PER_FIRM), 'extracted': extracted,
                      'error': error})
        print(f'{firm}: candidates {len(links)}; tested {min(len(links), MAX_PER_FIRM)}; '
              f'extracted {extracted}; error {error or "none"}', flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'updated': dt.datetime.now(dt.timezone.utc).isoformat(),
                               'pilot': True, 'method': 'heuristic candidate discovery; no investment stance inferred',
                               'stats': stats, 'articles': articles},
                              ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved', OUT)


if __name__ == '__main__':
    main()
