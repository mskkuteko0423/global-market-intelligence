#!/usr/bin/env python3
"""GMI source configuration patch. Run before official_pilot.py.
Preserves all 15 firms and the existing archive workflow.
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
    ('Fidelity', 'https://www.fidelity.com/viewpoints/market-and-economic-insights', 'fidelity.com'),
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
    raise RuntimeError('Cannot locate SITES; no file changed')

# Per-firm discovery: avoid treating generic navigation as research articles.
# The original candidates() function remains untouched for the other firms.
patch = '''
# GMI_DISCOVERY_PATCH_V2
_original_candidates = candidates

def candidates(parser, index, domain):
    if domain not in ('fidelity.com', 'pimco.com'):
        return _original_candidates(parser, index, domain)
    seen, results = set(), []
    for href, label in parser.links:
        url = urldefrag(urljoin(index, href))[0]
        path = urlparse(url).path.lower().rstrip('/')
        label = re.sub(r'\\s+', ' ', label).strip()
        if url in seen or not official(url, domain) or url.rstrip('/') == index.rstrip('/'):
            continue
        seen.add(url)
        if any(x in path for x in EXCLUDE_PATH) or any(x in label.lower() for x in EXCLUDE_TITLE):
            continue
        if domain == 'fidelity.com':
            # Fidelity market articles live under /viewpoints/, not /insights/.
            if not path.startswith('/viewpoints/') or path in ('/viewpoints/market-and-economic-insights',):
                continue
            if not (12 <= len(label) <= 220):
                continue
        else:
            # PIMCO often uses a short "Read Article" anchor; article title is
            # recovered from the destination's og:title by the main collector.
            if not path.startswith('/us/en/insights/') or path == '/us/en/insights':
                continue
            if not (5 <= len(label) <= 220):
                continue
        results.append((url, label))
    print(f'DISCOVERY_DETAIL {domain}: parsed_links={len(parser.links)} matched={len(results)} sample={results[:3]}', flush=True)
    return results
# END_GMI_DISCOVERY_PATCH_V2
'''
if '# GMI_DISCOVERY_PATCH_V2' not in src:
    # Strip prior injected discovery patch if present; fail rather than risk duplicates.
    if 'GMI_DISCOVERY_PATCH_V' in src:
        raise RuntimeError('Unknown previous discovery patch; no file changed')
    anchor = '\ndef find_date('
    if anchor not in src:
        raise RuntimeError('Cannot find insertion point; no file changed')
    src = src.replace(anchor, '\n' + patch + anchor, 1)
compile(src, str(p), 'exec')
p.write_text(src, encoding='utf-8')
print('SOURCE_EXPANSION sources=15 fidelity_viewpoints=enabled pimco_short_links=enabled')
