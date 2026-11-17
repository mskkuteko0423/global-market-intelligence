#!/usr/bin/env python3
"""GMI: expand official article discovery without changing the archive.

Run before official_pilot.py. No paid APIs. Failed discovery is recorded,
not treated as proof that an institution published no articles.
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
    ('Vanguard', 'https://corporate.vanguard.com/content/corporatesite/us/en/corp/articles.html', 'vanguard.com'),
    ('Fidelity', 'https://www.fidelity.com/viewpoints', 'fidelity.com'),
    ('PIMCO', 'https://www.pimco.com/us/en/insights', 'pimco.com'),
    ('UBS', 'https://www.ubs.com/global/en/wealth-management/insights.html', 'ubs.com'),
    ('BNP Paribas', 'https://group.bnpparibas/en/news', 'group.bnpparibas'),
    ('Schroders', 'https://www.schroders.com/en/global/individual/insights/', 'schroders.com'),
    ('Amundi', 'https://research-center.amundi.com/', 'amundi.com'),
    ('State Street', 'https://www.ssga.com/us/en/individual/insights', 'ssga.com'),
    ('Invesco', 'https://www.invesco.com/us/en/insights.html', 'invesco.com'),
]'''
src, n = re.subn(r'(?ms)^SITES\s*=\s*\[.*?^\]', lambda _: replacement, src, count=1)
if n != 1:
    raise RuntimeError('SITES block missing; nothing written')

helper = '''
# Index URLs are discovery attempts, not claims that they currently work.
DISCOVERY_INDEXES = {
    'Vanguard': [
        'https://corporate.vanguard.com/content/corporatesite/us/en/corp/articles.html',
        'https://investor.vanguard.com/investor-resources-education',
    ],
    'Fidelity': [
        'https://www.fidelity.com/viewpoints',
        'https://www.fidelity.com/learning-center/trading-investing',
        'https://www.fidelity.com/learning-center/trading-investing/market-outlook',
    ],
    'PIMCO': [
        'https://www.pimco.com/us/en/insights',
        'https://www.pimco.com/us/en/insights/economic-and-market-commentary',
        'https://www.pimco.com/us/en/insights/blog',
    ],
}
DISCOVERY_PATH_HINTS = {
    'Vanguard': ('/articles/', '/investor-resources-education/', '/insights/'),
    'Fidelity': ('/viewpoints/', '/learning-center/trading-investing/', '/learning-center/personal-finance/'),
    'PIMCO': ('/insights/',),
}
SECTION_SLUGS = {'insights', 'viewpoints', 'market-outlook', 'blog',
                 'economic-and-market-commentary', 'trading-investing',
                 'personal-finance', 'articles', 'research', 'news'}

def discover_links(firm, index, domain):
    indexes = DISCOVERY_INDEXES.get(firm, [index])
    found, seen, diagnostics = [], set(), []
    first_parser = None
    successful_indexes = 0
    for source in indexes:
        try:
            parser = parse(get_html(source, domain))
            successful_indexes += 1
            if first_parser is None:
                first_parser = parser
            links = candidates(parser, source, domain)
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
                    slug = path.rsplit('/', 1)[-1]
                    if slug in SECTION_SLUGS or len(slug) < 12 or '-' not in slug:
                        continue
                    links.append((url, label))
            new_count = 0
            for url, label in links:
                if url not in seen:
                    seen.add(url)
                    found.append((url, label))
                    new_count += 1
            diagnostics.append(f'{source}: {new_count} new candidates')
        except Exception as exc:
            diagnostics.append(f'{source}: {type(exc).__name__}: {str(exc)[:100]}')
    if firm in DISCOVERY_INDEXES:
        print(f'DISCOVERY_DETAIL {firm}: ' + ' | '.join(diagnostics), flush=True)
        print(f'DISCOVERY_STATUS firm={firm} indexes_ok={successful_indexes}/{len(indexes)} candidates={len(found)}', flush=True)
    if first_parser is None:
        raise RuntimeError('All discovery indexes failed: ' + ' | '.join(diagnostics))
    if not found:
        print(f'DISCOVERY_WARNING {firm}: no candidate URLs; not evidence of zero publications', flush=True)
    return found, first_parser
'''

# Remove any previously injected helper, so repeated runs remain idempotent.
start_marker = '# Multi-index discovery for selected institutions.'
end_marker = 'def main():'
if start_marker in src:
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    src = src[:start] + src[end:]
if src.count(end_marker) != 1:
    raise RuntimeError('main() anchor missing; nothing written')
src = src.replace(end_marker, helper + '\n' + end_marker, 1)
old = 'index_parser = parse(get_html(index, domain))\n            links = candidates(index_parser, index, domain)'
new = 'links, index_parser = discover_links(firm, index, domain)'
if old in src:
    src = src.replace(old, new, 1)
elif new not in src:
    raise RuntimeError('discovery call anchor missing; nothing written')
compile(src, str(p), 'exec')
p.write_text(src, encoding='utf-8')
print('SOURCE_EXPANSION sources=15; multi-index discovery; failures diagnosed; URLs not independently verified', flush=True)
