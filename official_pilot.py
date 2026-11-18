#!/usr/bin/env python3
"""GMI: broad-market official-publication discovery pilot (no paid APIs).
Read-only: writes data/official_pilot.json; never modifies reports.json.
Candidate labels are heuristic and must be checked against the source.
"""
import datetime as dt
import json
import html as html_escape
import html as html_lib
import pathlib
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.request import Request, urlopen

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'official_pilot.json'
PREVIEW = ROOT / 'data' / 'official_pilot_preview.html'
TRANSLATION_LIMIT = 30  # total text fields per run; no paid API
UNCONFIRMED_DATE = '\u672a\u78ba\u8a8d'


SITES = [
    ('Goldman Sachs', 'https://www.goldmansachs.com/insights/', 'goldmansachs.com'),
    ('J.P. Morgan Asset Management', 'https://am.jpmorgan.com/us/en/asset-management/adv/insights/', 'jpmorgan.com'),
    ('Morgan Stanley', 'https://www.morganstanley.com/insights', 'morganstanley.com'),
    ('Capital Group', 'https://www.capitalgroup.com/institutional/insights.html', 'capitalgroup.com'),
    ('BlackRock', 'https://www.blackrock.com/us/individual/insights', 'blackrock.com'),
    ('J.P. Morgan Research', 'https://www.jpmorgan.com/insights', 'jpmorgan.com'),
]


MAX_PER_FIRM = 5
MAX_BYTES = 2_500_000
# Market-wide coverage: AI is just one topic, never a prerequisite.
CATEGORIES = {
    '\u682a\u5f0f': ('equity', 'equities', 'stock', 'earnings', 's&p', 'nasdaq'),
    '\u50b5\u5238\u30fb\u91d1\u5229': ('bond', 'fixed income', 'treasury', 'yield', 'interest rate', 'duration'),
    '\u70ba\u66ff': ('currency', 'currencies', 'forex', 'fx market', 'dollar', 'yen'),
    '\u30de\u30af\u30ed\u7d4c\u6e08': ('macro', 'econom', 'inflation', 'gdp', 'recession', 'central bank'),
    '\u30af\u30ec\u30b8\u30c3\u30c8': ('credit', 'spread', 'high yield', 'private debt'),
    '\u30b3\u30e2\u30c7\u30a3\u30c6\u30a3': ('commodity', 'commodities', 'oil price', 'gold price', 'energy market'),
    '\u6295\u8cc7\u6226\u7565\u30fb\u8cc7\u91d1\u30d5\u30ed\u30fc': ('portfolio', 'asset allocation', 'market outlook', 'investment outlook', 'capital flow', 'liquidity'),
    '\u653f\u7b56\u30fb\u5730\u653f\u5b66': ('geopolit', 'tariff', 'trade policy', 'fiscal policy', 'election'),
    'AI\u30fb\u534a\u5c0e\u4f53': ('artificial intelligence', ' ai ', 'semiconductor', 'chipmaker', 'data center'),
    '\u305d\u306e\u4ed6\u306e\u7523\u696d\u30c6\u30fc\u30de': ('healthcare', 'technology', 'infrastructure', 'industry', 'sector'),
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
        self.body_depth = 0
        self.body_text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tag_stack.append(tag)

        if tag in ('script', 'style', 'nav', 'footer', 'header', 'aside'):
            self.skip_stack.append(len(self.tag_stack))

        if tag in ('main', 'article') and not self.body_depth and not self.skip_stack:
            self.body_depth = len(self.tag_stack)
            self.body_text = []

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

        if self.body_depth and not self.skip_stack:
            self.body_text.append(data)

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

        if self.body_depth == depth:
            body = re.sub(r'\s+', ' ', ''.join(self.body_text)).strip()
            if len(body) >= 75 and not self.paragraphs:
                self.paragraphs.append(body)
            self.body_depth = 0
            self.body_text = []

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


NON_ENGLISH_LOCALE_SEGMENTS = {'zh', 'zh-cn', 'zh-hk', 'zh-tw', 'zh-sg'}


def is_non_english_locale(url):
    segments = [part.lower() for part in urlparse(url).path.split('/') if part]
    return any(part in NON_ENGLISH_LOCALE_SEGMENTS for part in segments)


def candidates(parser, index, domain):
    seen = set()
    found = []
    for href, label in parser.links:
        url = urldefrag(urljoin(index, href))[0]
        path = urlparse(url).path.lower().rstrip('/')
        low_label = label.lower()
        if (not official(url, domain) or is_non_english_locale(url)
                or url.rstrip('/') == index.rstrip('/') or url in seen):
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
    """Extract publication date only; never substitute modified date."""

    def normalize_date(value):
        if not value:
            return None

        value = str(value).strip()

        # ISO format: 2026-11-17 or 2026-11-17T09:00:00
        match = re.search(r'(?<!\d)(20\d{2}-\d{2}-\d{2})(?!\d)', value)
        if match:
            try:
                return dt.date.fromisoformat(match.group(1)).isoformat()
            except ValueError:
                pass

        # English format: November 17, 2026
        match = re.search(
            r'\b(January|February|March|April|May|June|July|'
            r'August|September|October|November|December|'
            r'Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)'
            r'\.?\s+\d{1,2},?\s+20\d{2}\b',
            value,
            re.I
        )
        if match:
            text = match.group(0).replace(',', '').replace('.', '')
            for fmt in ('%B %d %Y', '%b %d %Y'):
                try:
                    return dt.datetime.strptime(text, fmt).date().isoformat()
                except ValueError:
                    continue

        return None

    # 1. Explicit publication metadata
    publication_keys = (
        'article:published_time',
        'datepublished',
        'publishdate',
        'publication_date',
        'dc.date.issued',
        'parsely-pub-date',
        'citation_publication_date',
        'citation_date',
    )

    for key in publication_keys:
        result = normalize_date(meta.get(key))
        if result:
            return result

    # 2. Structured data: JSON-LD datePublished
    # Supports normal and escaped JSON quotation marks.
    decoded = html_lib.unescape(page_html)
    pattern = (
        r'\\?"datePublished\\?"\s*:\s*'
        r'\\?"([^"\\<>]{8,60})'
    )

    for match in re.finditer(pattern, decoded, re.I):
        result = normalize_date(match.group(1))
        if result:
            return result

    # 3. Publication date in HTML time elements
    for match in re.finditer(
        r'<time\b[^>]*\bdatetime\s*=\s*["\']([^"\']+)["\']',
        page_html,
        re.I
    ):
        result = normalize_date(match.group(1))
        if result:
            return result

    # 4. Additional publication metadata
    for key, value in meta.items():
        key_lower = key.lower()
        if any(term in key_lower for term in (
            'published', 'publish_date', 'publicationdate',
            'datecreated', 'date.issued'
        )):
            result = normalize_date(value)
            if result:
                return result

    # 5. Date explicitly included in the article link title
    result = normalize_date(anchor_title)
    if result:
        return result

    return None


def is_topic_page(url, title, meta, paragraphs):
    path = urlparse(url).path.lower().rstrip('/')
    known = (
        '/insights/artificial-intelligence',
        '/insights/mergers-and-acquisitions',
        '/ideas/artificial-intelligence',
        '/ideas/mergers-and-acquisitions',
    )
    return (
        path in known
        or path.endswith('/artificial-intelligence')
        or path.endswith('/mergers-and-acquisitions')
    )


def classify_focus(title, description):
    # Avoid classifying by unrelated boilerplate or all page paragraphs.
    primary = classify(title)
    secondary = [x for x in classify(description) if x not in primary]
    return primary[:2], secondary[:2]


def add_japanese(articles):
    """Translate public excerpts with bounded requests, explicit failure metadata.

    Translation is not summarization. Never label untranslated English as Japanese.
    """
    from translation_fallback import translate_public_text
    attempts = 0
    succeeded = 0
    eligible = [
        r for r in articles
        if r.get('page_type') == 'article_candidate' and r.get('excerpt')
    ]
    offset = dt.date.today().toordinal() % len(eligible) if eligible else 0

    for record in eligible[offset:] + eligible[:offset]:
        record['translation_errors'] = {}
        for field, source in (('title_ja', record.get('title', '')),
                              ('excerpt_ja', record.get('excerpt', '')[:420])):
            if attempts >= TRANSLATION_LIMIT:
                record['translation_errors'][field] = 'run_limit_reached'
                continue
            if not source.strip():
                continue
            attempts += 1
            translated, provider, failure = translate_public_text(source)
            if translated:
                record[field] = translated
                record.setdefault('translation_provider', {})[field] = provider
                succeeded += 1
            else:
                record['translation_errors'][field] = failure
        record['japanese_status'] = ('machine_translation_of_partial_excerpt_not_summary'
                                     if record.get('excerpt_ja') else 'not_translated')
    print(f'TRANSLATION_RESULT attempts={attempts} success={succeeded} failed={attempts-succeeded} limit={TRANSLATION_LIMIT}', flush=True)


def make_preview(articles):
    # Standalone HTML preview.
    items = []
    for r in articles:
        if r.get('page_type') != 'article_candidate' or not r.get('excerpt'):
            continue
        esc = lambda x: html_escape.escape(str(x or ''), quote=True)
        title = esc(r.get('title_ja') or r.get('title'))
        original = esc(r.get('title'))
        excerpt = esc(r.get('excerpt_ja') or r.get('excerpt'))
        lang = '\u65e5\u672c\u8a9e\u6a5f\u68b0\u7ffb\u8a33\uff08\u672c\u6587\u306e\u4e00\u90e8\u30fb\u8981\u7d04\u3067\u306f\u3042\u308a\u307e\u305b\u3093\uff09' if r.get('excerpt_ja') else '\u82f1\u8a9e\u539f\u6587\u629c\u7c8b\uff08\u7ffb\u8a33\u672a\u53d6\u5f97\uff09'
        url = r.get('official_url', '')
        if not url.startswith('https://'):
            continue
        cats = ' / '.join(r.get('primary_categories', []) + r.get('secondary_categories', [])) or '\u5206\u985e\u672a\u78ba\u5b9a'
        items.append(f'''<article><small>{esc(r.get('firm'))} \u00b7 \u516c\u958b\u65e5: {esc(r.get('published') or UNCONFIRMED_DATE)} \u00b7 {esc(cats)}</small>
<h2>{title}</h2><p class="muted">\u539f\u984c: {original}</p><p><b>{lang}</b></p><p>{excerpt}</p>
<p><a href="{esc(url)}" target="_blank" rel="noopener noreferrer">\u516c\u5f0f\u8a18\u4e8b\u3092\u958b\u304f</a></p></article>''')
    page = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GMI \u516c\u5f0f\u8a18\u4e8b \u65e5\u672c\u8a9e\u30d7\u30ec\u30d3\u30e5\u30fc</title><style>body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#f5f6f8;color:#17202a;margin:0;padding:20px;max-width:860px;margin:auto}article{background:white;border:1px solid #ddd;border-radius:12px;padding:18px;margin:14px 0;line-height:1.7}h1{font-size:1.5rem}h2{font-size:1.15rem}small,.muted{color:#626d78}a{color:#155db3}header{line-height:1.6}</style><header><h1>Global Market Intelligence \u00b7 \u516c\u5f0f\u8a18\u4e8b\u30d7\u30ec\u30d3\u30e5\u30fc</h1><p>\u5bfe\u8c61\u306f\u5e02\u5834\u5168\u822c\u3002\u8868\u793a\u6587\u7ae0\u306f\u53d6\u5f97\u3057\u305f\u672c\u6587\u306e\u4e00\u90e8\u306e\u6a5f\u68b0\u7ffb\u8a33\u3067\u3042\u308a\u3001\u8a18\u4e8b\u5168\u4f53\u306e\u8981\u7d04\u3084\u6295\u8cc7\u5224\u65ad\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u3002\u65e5\u4ed8\u30fb\u5206\u985e\u306f\u672a\u691c\u8a3c\u306e\u53ef\u80fd\u6027\u304c\u3042\u308a\u307e\u3059\u3002\u7121\u6599\u516c\u958b\u7ffb\u8a33\u30b5\u30fc\u30d3\u30b9\u306e\u5931\u6557\u6642\u306f\u82f1\u8a9e\u539f\u6587\u3092\u8868\u793a\u3057\u307e\u3059\u3002</p></header>''' + '\n'.join(items) + '</html>'
    PREVIEW.write_text(page, encoding='utf-8')
    print(f'Preview saved {PREVIEW} ({len(items)} article candidates)', flush=True)


def main():
    stats, articles = [], []
    for firm, index, domain in SITES:
        error = None
        links = []
        extracted = 0
        try:
            index_parser = parse(get_html(index, domain))
            links = candidates(index_parser, index, domain)
            links = [
                (candidate_url, candidate_title)
                for candidate_url, candidate_title in links
                if not is_non_english_locale(candidate_url)
            ]
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

                    if firm == 'Schroders':
                        print("SCHRODERS_HTML_DIAG " + json.dumps({
                            "url": url,
                            "html_chars": len(page_html),
                            "p_tags": len(re.findall(r'<p\b', page_html, re.I)),
                            "article_tags": len(re.findall(r'<article\b', page_html, re.I)),
                            "main_tags": len(re.findall(r'<main\b', page_html, re.I)),
                            "json_ld": len(re.findall(
                                r'application/ld\+json', page_html, re.I
                            )),
                            "article_body_keys": len(re.findall(
                                r'articleBody|article-body|article_content',
                                page_html, re.I
                            )),
                            "meta_keys": list(page.meta.keys())[:15],
                        }, ensure_ascii=False), flush=True)
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

                    boilerplate = (
                        'we harness every resource',
                        'goldman sachs\u2019 weekly newsletter',
                        'our weekly newsletter delivers',
                        'we invest the power of goldman sachs',
                        'subscribe now',
                        'privacy policy',
                        'cookie preferences',
                        'to access another blackrock site',
                        'please update your user type',
                        'update your user type',
                    )

                    
                    clean = [p for p in page.paragraphs if not any(b in p.lower() for b in boilerplate)]

                    if firm == 'Schroders' and not clean:
                        for match in re.finditer(
                            r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                            page_html, re.I | re.S
                        ):
                            try:
                                structured = json.loads(html_lib.unescape(match.group(1)))
                            except (ValueError, TypeError):
                                continue

                            pending = [structured]
                            while pending:
                                item = pending.pop()
                                if isinstance(item, list):
                                    pending.extend(item)
                                elif isinstance(item, dict):
                                    pending.extend(
                                        v for k, v in item.items()
                                        if k in ('@graph', 'mainEntity')
                                        and isinstance(v, (dict, list))
                                    )
                                    types = item.get('@type', [])
                                    if isinstance(types, str):
                                        types = [types]
                                    body = item.get('articleBody')
                                    if (
                                        any('Article' in str(t) for t in types)
                                        and isinstance(body, str)
                                        and len(body.strip()) >= 75
                                    ):
                                        body = re.sub(r'\s+', ' ', body).strip()
                                        if not any(b in body.lower() for b in boilerplate):
                                            clean = [body]
                                            break
                            if clean:
                                break
                        print(
                            f'SCHRODERS_JSONLD_EXTRACT chars={len(clean[0]) if clean else 0}',
                            flush=True
                        )

                    if record['page_type'] == 'topic_or_index':
                        record['categories'] = []
                        record['primary_categories'] = []
                        record['secondary_categories'] = []
                        record['excerpt_status'] = 'Topic/index page; not an article'
                    elif clean:
                        record['excerpt'] = ' '.join(clean[:5])[:1800]
                        record['excerpt_status'] = 'Cleaned candidate excerpt; editorial verification required'
                        extracted += 1
                    elif len(description.strip()) >= 75 and not any(
                        b in description.lower() for b in boilerplate
                    ):
                        record['excerpt'] = description.strip()[:1800]
                        record['excerpt_status'] = 'Metadata description excerpt; editorial verification required'
                        extracted += 1
                    else:
                        record['error'] = 'No substantial paragraph or usable metadata description'
                except Exception as exc:
                    record['error'] = f'{type(exc).__name__}: {exc}'[:180]
                print("ARTICLE_RESULT " + json.dumps({
                    "firm": firm,
                    "url": url,
                    "title": record.get("title"),
                    "page_type": record.get("page_type"),
                    "excerpt_chars": len(record.get("excerpt") or ""),
                    "error": record.get("error"),
                    "paragraph_count": len(page.paragraphs) if 'page' in locals() else None,
                    "description_chars": len(description) if 'description' in locals() else None,
                    "html_chars": len(page_html) if 'page_html' in locals() else None,
                }, ensure_ascii=False), flush=True)      
                articles.append(record)
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'[:180]
        stats.append({'firm': firm, 'official_url_candidates': len(links),
                      'tested': min(len(links), MAX_PER_FIRM), 'extracted': extracted,
                      'error': error})
        print(f'{firm}: candidates {len(links)}; tested {min(len(links), MAX_PER_FIRM)}; '
              f'extracted {extracted}; error {error or "none"}', flush=True)
    add_japanese(articles)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    make_preview(articles)
    OUT.write_text(json.dumps({'updated': dt.datetime.now(dt.timezone.utc).isoformat(),
                               'pilot': True, 'method': 'v9: broad-market; bounded dual-provider machine translation; excerpts not summaries; dates unverified; no stance inferred',
                               'stats': stats, 'articles': articles},
                              ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved', OUT)


if __name__ == '__main__':
    main()

