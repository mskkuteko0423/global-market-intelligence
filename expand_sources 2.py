#!/usr/bin/env python3
"""GMI official source expansion and conservative multi-index discovery.

Run by existing publish_official.yml before official_pilot.py.
No paid APIs; keeps original collector and archive workflow intact.
"""
from pathlib import Path
import re

p = Path(__file__).with_name('official_pilot.py')
src = p.read_text(encoding='utf-8')
replacement = '''SITES = [
    ('Goldman Sachs', 'https://www.goldmansachs.com/insights/', 'goldmansachs.com'),
    ('J.P. Morgan Asset Management', 'https://am.jpmorgan.com/us/en/asset-management/adv/insights/', 'jpmorgan.com'),
    ('Morgan Stanley', 'https://www.morganstanley.com/insights', 'morganstanley.com'),
    ('Capital Group', 'https://www.capitalgroup.com/institutional/insights.html', 'capitalgroup.com'),
    ('BlackRock', 'https://www.blackrock.com/us/individual/insights', 'blackrock.com'),
    ('J.P. Morgan Research', 'https://www.jpmorgan.com/insights', 'jpmorgan.com'),
    ('Vanguard', 'https://investor.vanguard.com/investor-resources-education/news', 'vanguard.com'),
    ('Fidelity', 'https://www.fidelity.com/learning-center/trading-investing', 'fidelity.com'),
    ('PIMCO', 'https://www.pimco.com/us/en/insights', 'pimco.com'),
    ('UBS', 'https://www.ubs.com/global/en/wealth-management/insights.html', 'ubs.com'),
    ('BNP Paribas', 'https://group.bnpparibas/en/news', 'group.bnpparibas'),
    ('Schroders', 'https://www.schroders.com/en/global/individual/insights/', 'schroders.com'),
    ('Amundi', 'https://research-center.amundi.com/', 'amundi.com'),
    ('State Street', 'https://www.ssga.com/us/en/individual/insights', 'ssga.com'),
    ('Invesco', 'https://www.invesco.com/us/en/insights.html', 'invesco.com'),
]'''
src, count = re.subn(r'(?ms)^SITES\s*=\s*\[.*?^\]', lambda _: replacement, src, count=1)
if count != 1:
    raise RuntimeError('SITES block not found; collector not modified')

# The fallback URLs are discovery candidates, not assertions of live availability.
# Keep a tight publication-path and title filter for these two institutions.
helper = '''
# Multi-index discovery, intentionally limited to two institutions.
DISCOVERY_INDEXES = {
    'Fidelity': [
        'https://www.fidelity.com/learning-center/trading-investing',
        'https://www.fidelity.com/viewpoints',
        'https://www.fidelity.com/learning-center/trading-investing/market-outlook',
    ],
    'PIMCO': [
        'https://www.pimco.com/us/en/insights',
        'https://www.pimco.com/us/en/insights/economic-and-market-commentary',
        'https://www.pimco.com/us/en/insights/blog',
    ],
}
DISCOVERY_PATH_HINTS = {
    'Fidelity': ('/viewpoints/', '/learning-center/trading-investing/', '/learning-center/personal-finance/'),
    'PIMCO': ('/insights/',),
}

def discover_links(firm, index, domain):
    indexes = DISCOVERY_INDEXES.get(firm, [index])
    found, seen, diagnostics = [], set(), []
    first_parser = None
    for source in indexes:
        try:
            parser = parse(get_html(source, domain))
            if first_parser is None:
                first_parser = parser
            links = candidates(parser, source, domain)
            # A narrowly scoped fallback for article URLs missed by the global path filter.
            if firm in DISCOVERY_PATH_HINTS:
                for href, label in parser.links:
                    url = urldefrag(urljoin(source, href))[0]
                    path = urlparse(url).path.lower().rstrip('/')
                    low = label.lower().strip()
                    if not official(url, domain) or not 18 <= len(label) <= 220:
                        continue
                    if any(x in path for x in EXCLUDE_PATH) or any(x in low for x in EXCLUDE_TITLE):
                        continue
                    if not any(x in path + '/' for x in DISCOVERY_PATH_HINTS[firm]):
                        continue
                    if url.rstrip('/') == source.rstrip('/'):
                        continue
                    # Reject section/category pages with no article-like final slug.
                    slug = path.rsplit('/', 1)[-1]
                    if slug in ('insights', 'viewpoints', 'market-outlook', 'blog',
                                'economic-and-market-commentary', 'trading-investing',
                                'personal-finance', 'articles', 'research'):
                        continue
                    if len(slug) < 12 or '-' not in slug:
                        continue
                    links.append((url, label))
            for url, label in links:
                if url not in seen:
                    seen.add(url)
                    found.append((url, label))
            diagnostics.append(f'{source}: {len(links)} candidates')
        except Exception as exc:
            diagnostics.append(f'{source}: {type(exc).__name__} {str(exc)[:90]}')
    if firm in DISCOVERY_INDEXES:
        print(f'DISCOVERY_DETAIL {firm}: ' + ' | '.join(diagnostics), flush=True)
    if first_parser is None:
        raise RuntimeError('All discovery indexes failed: ' + ' | '.join(diagnostics))
    return found, first_parser

'''
if 'def discover_links(firm, index, domain):' not in src:
    marker = 'def main():'
    if src.count(marker) != 1:
        raise RuntimeError('main() anchor missing; collector not modified')
    src = src.replace(marker, helper + marker, 1)
old = 'index_parser = parse(get_html(index, domain))\n            links = candidates(index_parser, index, domain)'
new = 'links, index_parser = discover_links(firm, index, domain)'
if old in src:
    src = src.replace(old, new, 1)
elif new not in src:
    raise RuntimeError('Discovery call anchor missing; collector not modified')
compile(src, str(p), 'exec')
p.write_text(src, encoding='utf-8')
print('SOURCE_EXPANSION sources=15; Fidelity/PIMCO multi-index discovery enabled; URLs unverified', flush=True)
