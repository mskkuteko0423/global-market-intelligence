#!/usr/bin/env python3
"""GMI source expansion: HTML + bounded official sitemap/RSS discovery.
Run before official_pilot.py. Does not change reports.json or archives.
"""
from pathlib import Path
import re

p = Path(__file__).with_name('official_pilot.py')
src = p.read_text(encoding='utf-8')

sites = '''SITES = [
    ('Goldman Sachs', 'https://www.goldmansachs.com/insights/', 'goldmansachs.com'),
    ('J.P. Morgan Asset Management', 'https://am.jpmorgan.com/us/en/asset-management/adv/insights/', 'jpmorgan.com'),
    ('Morgan Stanley', 'https://www.morganstanley.com/insights', 'morganstanley.com'),
    ('Capital Group', 'https://www.capitalgroup.com/institutional/insights.html', 'capitalgroup.com'),
    ('BlackRock', 'https://www.blackrock.com/us/individual/insights', 'blackrock.com'),
    ('J.P. Morgan Research', 'https://www.jpmorgan.com/insights', 'jpmorgan.com'),
    ('Vanguard', 'https://investor.vanguard.com/resources-education/news-perspectives', 'vanguard.com'),
    ('Fidelity', 'https://www.fidelity.com/learning-center/trading-investing', 'fidelity.com'),
    ('PIMCO', 'https://www.pimco.com/us/en/insights', 'pimco.com'),
    ('BNP Paribas', 'https://economic-research.bnpparibas.com/Thematics/Artificial-intelligence/en-US', 'bnpparibas.com'),
    ('Schroders', 'https://www.schroders.com/en/global/individual/insights/', 'schroders.com'),
    ('Amundi', 'https://research-center.amundi.com/', 'amundi.com'),
    ('State Street', 'https://www.ssga.com/us/en/individual/insights', 'ssga.com'),
    ('Invesco', 'https://www.invesco.com/us/en/insights.html', 'invesco.com'),
]'''
src, n = re.subn(r'(?ms)^SITES\s*=\s*\[.*?^\]', lambda m: sites, src, count=1)
if n != 1:
    raise RuntimeError('SITES not found; refusing to modify collector')

helper = r'''
# Conservative alternate discovery. URLs from feeds/sitemaps are CANDIDATES,
# never verified publications until the article page passes existing checks.
def discover_links(firm, index, domain):
    import xml.etree.ElementTree as ET
    import gzip
    from urllib.request import Request, urlopen
    from urllib.parse import urljoin, urlparse

    fallback = {
        'Vanguard': ['https://investor.vanguard.com/investor-resources-education',
                     'https://investor.vanguard.com/resources-education/news-perspectives',
                     'https://corporate.vanguard.com/content/corporatesite/us/en/corp/articles.html',
                     'https://investor.vanguard.com/investor-resources-education/news'],
        'Fidelity': ['https://www.fidelity.com/viewpoints',
                     'https://www.fidelity.com/learning-center/trading-investing',
                     'https://www.fidelity.com/learning-center/markets-sectors'],
        'PIMCO': ['https://www.pimco.com/us/en/insights',
                  'https://www.pimco.com/us/en/insights/economic-and-market-commentary'],
        'Schroders': ['https://www.schroders.com/en/global/individual/insights/'],
        'Amundi': ['https://research-center.amundi.com/',
                   'https://www.amundi.com/globaldistributor/all-news'],
        'BNP Paribas': [],
    }
    selected = firm in fallback
    sources = list(dict.fromkeys([index] + fallback.get(firm, [])))
    found, seen, diagnostics, first_parser = [], set(), [], None
    source_rank = {}

    def add(url, label, origin='html'):
        url = urldefrag(url)[0]
        if not official(url, domain) or url in seen:
            return
        path = urlparse(url).path.lower().rstrip('/')
        slug = path.rsplit('/', 1)[-1]
        if not slug or len(slug) < 12 or slug in ('insights', 'research', 'articles', 'news'):
            return
        if any(x in path for x in EXCLUDE_PATH):
            return
        # Restrict discovery to publication-shaped paths.
        hints = ('/insights/', '/research/', '/article/', '/articles/', '/commentary/', '/news/',
                 '/outlook/', '/viewpoints/', '/publications/', '/market/',
                 '/investment-views/', '/investment-insights/', '/perspectives/')
        if not any(h in path + '/' for h in hints) and firm != 'BNP Paribas':
            return
        label = re.sub(r'\s+', ' ', label).strip()
        if not 18 <= len(label) <= 220:
            return
        if any(x in label.lower() for x in EXCLUDE_TITLE):
            return
        seen.add(url)
        found.append((url, label))
        source_rank[url] = origin

    for source in sources:
        try:
            page_timeout = 30 if firm == 'BNP Paribas' else 15
            parser = parse(get_html(source, domain, timeout=page_timeout))
            if first_parser is None:
                first_parser = parser
            for url, label in candidates(parser, source, domain):
                add(url, label, 'html')
            # Existing path filters can be too narrow for certain official sites.
            if selected:
                for href, label in parser.links:
                    add(urljoin(source, href), label, 'html')
            diagnostics.append(f'HTML {source}: OK')
        except Exception as exc:
            diagnostics.append(f'HTML {source}: {type(exc).__name__} {str(exc)[:80]}')

    # Keep successful HTML discovery fast; structured sources are a fallback.
    # Do not confuse sitemap modification timestamps with publication dates.
    if selected and len(found) < MAX_PER_FIRM:
        host = urlparse(index).netloc
        origin = 'https://' + host
        feeds = [origin + '/feed', origin + '/rss', origin + '/sitemap.xml']
        if firm == 'BNP Paribas':
            feeds = [origin + '/sitemap.xml']
        # Robots.txt may advertise a sitemap on a different official subdomain.
        try:
            req = Request(origin + '/robots.txt', headers={'User-Agent': 'GMIResearchPilot/3.0'})
            with urlopen(req, timeout=10 if firm == 'BNP Paribas' else 8) as response:
                robots = response.read(250_000).decode('utf-8', 'replace')
            for line in robots.splitlines():
                if line.lower().startswith('sitemap:'):
                    candidate = line.split(':', 1)[1].strip()
                    if official(candidate, domain):
                        feeds.append(candidate)
        except Exception as exc:
            diagnostics.append(f'ROBOTS: {type(exc).__name__}')

        queue = list(dict.fromkeys(feeds))
        visited = set()
        while queue and len(visited) < 7 and len(found) < MAX_PER_FIRM:
            feed = queue.pop(0)
            if feed in visited or not official(feed, domain):
                continue
            visited.add(feed)
            try:
                req = Request(feed, headers={'User-Agent': 'GMIResearchPilot/3.0'})
                with urlopen(req, timeout=15 if firm == 'BNP Paribas' else 9) as response:
                    if not official(response.geturl(), domain):
                        raise ValueError('Redirect outside official domain')
                    raw = response.read(1_500_001)
                if len(raw) > 1_500_000:
                    raise ValueError('XML size limit')
                if raw[:2] == b'\x1f\x8b':
                    raw = gzip.decompress(raw)
                    if len(raw) > 3_000_000:
                        raise ValueError('Decompressed XML size limit')
                root = ET.fromstring(raw)
                tag = root.tag.rsplit('}', 1)[-1].lower()
                if tag == 'sitemapindex':
                    for item in root:
                        loc = next((el.text for el in item if el.tag.rsplit('}', 1)[-1] == 'loc'), None)
                        if loc and official(loc, domain) and loc not in visited and len(queue) < 12:
                            queue.append(loc)
                elif tag == 'urlset':
                    for item in root:
                        loc = next((el.text for el in item if el.tag.rsplit('}', 1)[-1] == 'loc'), None)
                        if loc:
                            slug = urlparse(loc).path.rstrip('/').split('/')[-1]
                            add(loc, slug.replace('-', ' ').replace('_', ' ').title(), 'sitemap')
                elif tag in ('rss', 'feed'):
                    for item in root.iter():
                        if item.tag.rsplit('}', 1)[-1] not in ('item', 'entry'):
                            continue
                        title, link = '', ''
                        for el in item:
                            name = el.tag.rsplit('}', 1)[-1]
                            if name == 'title':
                                title = ''.join(el.itertext()).strip()
                            if name == 'link':
                                link = el.get('href') or (el.text or '')
                        if link:
                            add(urljoin(feed, link.strip()), title, 'feed')
                diagnostics.append(f'XML {feed}: OK')
            except Exception as exc:
                diagnostics.append(f'XML {feed}: {type(exc).__name__} {str(exc)[:70]}')

    if selected:
        print(f'DISCOVERY_DETAIL {firm}: ' + ' | '.join(diagnostics), flush=True)
    # A feed entry is a stronger discovery signal than a generic sitemap URL.
    # A date in a URL is only a ranking hint, NEVER the publication date.
    def rank(item):
        url, label = item
        path = urlparse(url).path.lower()
        dates = re.findall(r'(?<!\d)(20\d{2})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])(?!\d)', path)
        date_hint = ''.join(dates[-1]) if dates else ''
        origin_score = {'feed': 3, 'html': 2, 'sitemap': 1}.get(source_rank.get(url), 0)
        return (bool(date_hint), date_hint, origin_score)
    found.sort(key=rank, reverse=True)
    if first_parser is None:
        # RSS/sitemap discovery may work even if HTML is blocked.
        # Return a neutral parser for the existing diagnostics logic.
        if found:
            first_parser = parse('')
        else:
            raise RuntimeError('All discovery methods failed: ' + ' | '.join(diagnostics))
    return found, first_parser
'''

if 'def discover_links(firm, index, domain):' in src:
    src, n = re.subn(r'(?ms)^# Multi-index discovery for selected institutions\..*?(?=^def main\(\):)', lambda m: helper + '\n', src, count=1)
    if not n:
        src, n = re.subn(r'(?ms)^def discover_links\(firm, index, domain\):.*?(?=^def main\(\):)', lambda m: helper + '\n', src, count=1)
    if not n:
        raise RuntimeError('Existing discovery helper could not be safely replaced')
else:
    if src.count('def main():') != 1:
        raise RuntimeError('main() anchor not found')
    src = src.replace('def main():', helper + '\ndef main():', 1)
old = 'index_parser = parse(get_html(index, domain))\n            links = candidates(index_parser, index, domain)'
new = 'links, index_parser = discover_links(firm, index, domain)'
if old in src:
    src = src.replace(old, new, 1)
elif new not in src:
    raise RuntimeError('Collector discovery call not found')

# BNP Paribas pages are slow from the hosted runner; allow a longer read window
# for its own pages while keeping the existing limits for every other source.
if 'def get_html(url, domain, timeout=15):' not in src:
    src, n = re.subn(r'(?m)^def get_html\(url, domain\):$',
                     'def get_html(url, domain, timeout=15):', src, count=1)
    if n != 1:
        raise RuntimeError('get_html signature not found; refusing timeout update')
if 'with urlopen(req, timeout=timeout) as resp:' not in src:
    src, n = re.subn(r'with urlopen\(\s*req(?:\s*,\s*timeout\s*=\s*[^)]*)?\s*\)\s+as\s+resp:',
                     'with urlopen(req, timeout=timeout) as resp:', src, count=1)
    if n != 1:
        raise RuntimeError('get_html timeout call not found; refusing timeout update')
article_fetch = 'article_html, _ = get_html(url, domain)'
article_fetch_long = "article_html, _ = get_html(url, domain, timeout=30 if firm == 'BNP Paribas' else 15)"
if article_fetch in src:
    src = src.replace(article_fetch, article_fetch_long, 1)
elif article_fetch_long not in src:
    raise RuntimeError('article fetch call not found; refusing timeout update')
compile(src, str(p), 'exec')
p.write_text(src, encoding='utf-8')
print('SOURCE_EXPANSION sources=15; HTML + bounded RSS/sitemap fallback; official URLs only', flush=True)
