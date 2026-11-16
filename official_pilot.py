#!/usr/bin/env python3
"""GMI: broad-market official-publication discovery pilot (no paid APIs).
Read-only: writes data/official_pilot.json; never modifies reports.json.
Candidate labels are heuristic and must be checked against the source.
"""
import datetime as dt
import json
import html as html_lib
import pathlib
import re
from html import unescape
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
    'マクロ経済': ('macro', 'econom', 'inflation', 'gdp', 'recession', 'central bank'),
    'クレジット': ('credit', 'spread', 'high yield', 'private debt'),
    'コモディティ': ('commodity', 'commodities', 'oil price', 'gold price', 'energy market'),
    '投資戦略・資金フロー': ('portfolio', 'asset allocation', 'market outlook', 'investment outlook', 'capital flow', 'liquidity'),
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
    return [name for name, terms in CATEGORIES.items() if any(re.search(r'(?<![a-z])' + re.escape(term.strip()) + r'(?![a-z])', normalized) for term in terms)]


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


def find_date(page_html, meta, anchor_title):
    for key in ('article:published_time', 'datepublished', 'date', 'publishdate',
                'dc.date', 'dc.date.issued', 'parsely-pub-date'):
        value = meta.get(key)
        if value:
            m = re.search(r'20\d{2}-\d{2}-\d{2}', value)
            if m:
                return m.group()
    # JSON-LD datePublished; HTML entities are decoded before matching.
    decoded = html_lib.unescape(page_html)
    m = re.search(r'["\\]datePublished["\\]\s*:\s*["\\](20\d{2}-\d{2}-\d{2})', decoded, re.I)
    if m:
        return m.group(1)
    m = re.search(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+20\d{2}\b', anchor_title, re.I)
    if m:
        try:
            return dt.datetime.strptime(m.group().replace(',', ''), '%b %d %Y').date().isoformat()
        except ValueError:
            pass
    return None


def is_topic_page(url, title, meta, paragraphs):
    path = urlparse(url).path.lower().rstrip('/')
    # Known landing paths observed in the prior pilot artifact.
    known = ('/insights/artificial-intelligence', '/insights/mergers-and-acquisitions',
             '/ideas/artificial-intelligence', '/ideas/mergers-and-acquisitions')
    if path in known or path.endswith('/artificial-intelligence') or path.endswith('/mergers-and-acquisitions'):
        return True
    # Explicit webpage metadata, if present, is stronger than paragraph count.
    ogtype = (meta.get('og:type') or '').lower()
    if ogtype == 'website' and not any(meta.get(k) for k in ('article:published_time', 'datepublished')) and len(paragraphs) < 4:
        return True
    # Do not reject genuine short articles merely because their date is missing.
    if len(paragraphs) < 2 and not any(meta.get(k) for k in ('article:published_time', 'datepublished')):
        return True
    return False


def classify_focus(title, description):
    # Avoid classifying by unrelated boilerplate or all page paragraphs.
    primary = classify(title)
    secondary = [x for x in classify(description) if x not in primary]
    return primary[:2], secondary[:2]


def main():
    stats, articles = [], []
    for firm, index, domain in SITES:
        error = None
        links = []
        extracted = 0
        try:
            index_parser = parse(get_html(index, domain))
            links = candidates(index_parser, index, domain)
            if not links:
                # Diagnostic only: do not publish unverified links as articles.
                samples = []
                for href, label in index_parser.links:
                    candidate_url = urldefrag(urljoin(index, href))[0]
                    if official(candidate_url, domain) and len(label) >= 18:
                        samples.append({'title': label[:100], 'url': candidate_url[:250]})
                    if len(samples) == 8:
                        break
                print(f'{firm}: diagnostic official links {json.dumps(samples, ensure_ascii=False)}', flush=True)
            if not links:
                print(f'{firm}: no candidate links matched publication path/title filters; source page may require a different discovery strategy', flush=True)
            for url, anchor_title in links[:MAX_PER_FIRM]:
                record = {'firm': firm, 'official_url': url, 'link_title': anchor_title,
                          'title': anchor_title, 'published': None, 'categories': [],
                          'excerpt': '', 'excerpt_status': 'Not extracted', 'page_type': 'unverified',
                          'market_relevance': 'Needs human review', 'error': None}
                try:
                    page_html = get_html(url, domain)
                    page = parse(page_html)
                    m = page.meta
                    record['title'] = m.get('og:title') or m.get('twitter:title') or anchor_title
                    record['published'] = find_date(page_html, m, anchor_title)
                    record['date_status'] = 'metadata_or_link_detected_not_independently_verified' if record['published'] else 'unverified'
                    record['page_type'] = ('topic_or_index' if is_topic_page(url, record['title'], m, page.paragraphs)
                                           else 'article_candidate')
                    description = m.get('description', '') or m.get('og:description', '')
                    primary, secondary = classify_focus(record['title'], description)
                    record['primary_categories'] = primary
                    record['secondary_categories'] = secondary
                    record['categories'] = primary + secondary
                    boilerplate = ('we harness every resource', 'goldman sachs’ weekly newsletter',
                                   'our weekly newsletter delivers', 'we invest the power of goldman sachs',
                                   'subscribe now', 'privacy policy', 'cookie preferences')
                    clean = [p for p in page.paragraphs if not any(b in p.lower() for b in boilerplate)]
                    if record['page_type'] == 'topic_or_index':
                        record['categories'] = []
                        record['primary_categories'] = []
                        record['secondary_categories'] = []
                        record['excerpt_status'] = 'Topic/index page; not an article'
                    elif len(clean) >= 2:
                        record['excerpt'] = ' '.join(clean[:5])[:1800]
                        record['excerpt_status'] = 'Cleaned candidate excerpt; editorial verification required'
                        extracted += 1
                    else:
                        record['error'] = 'Fewer than 2 substantial non-boilerplate paragraphs'
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
                               'pilot': True, 'method': 'v7: broad-market diagnostic; topic pages flagged; dates are unverified detections; no stance inferred',
                               'stats': stats, 'articles': articles},
                              ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved', OUT)


if __name__ == '__main__':
    main()
