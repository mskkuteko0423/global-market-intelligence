#!/usr/bin/env python3
"""GMI source expansion. Run before official_pilot.py; standard-library only.
Preserves the existing collector and adds bounded alternate discovery for selected firms.
"""
from pathlib import Path
import re

p = Path(__file__).with_name('official_pilot.py')
src = p.read_text(encoding='utf-8')

# Preserve the six established sources, extend the list to fifteen.
original_block = re.search(r'(?ms)^SITES\s*=\s*\[.*?^\]', src)
if not original_block:
    raise RuntimeError('SITES definition not found; no changes written')
new_sites = '''SITES = [
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
src = src[:original_block.start()] + new_sites + src[original_block.end():]

# Extra indexes are discovery hypotheses, not guaranteed live URLs.
# Do not change the established Vanguard/Fidelity strategy.
addition = '''
# Multiple public official landing pages for sources with zero candidates.
DISCOVERY_ALTERNATES = {
    'PIMCO': [
        'https://www.pimco.com/us/en/insights',
        'https://www.pimco.com/us/en/insights/market-commentary',
        'https://www.pimco.com/us/en/insights/economic-and-market-commentary',
    ],
    'Schroders': [
        'https://www.schroders.com/en/global/individual/insights/',
        'https://www.schroders.com/en-us/us/individual/insights/',
        'https://www.schroders.com/en/global/professional/insights/',
    ],
    'Amundi': [
        'https://research-center.amundi.com/',
        'https://research-center.amundi.com/topics',
        'https://research-center.amundi.com/article',
    ],
}


def discover_candidates(firm, index, domain):
    """Attempt alternate official index URLs, preserving strict official-domain checks."""
    indexes = DISCOVERY_ALTERNATES.get(firm, [index])
    found, seen, failures = [], set(), []
    for landing in indexes:
        try:
            page = parse(get_html(landing, domain))
            links = candidates(page, landing, domain)
            for url, label in links:
                if url not in seen:
                    found.append((url, label))
                    seen.add(url)
            print(f'DISCOVERY_DETAIL firm={firm!r} index={landing!r} candidates={len(links)}', flush=True)
        except Exception as exc:
            failures.append(f'{landing}: {type(exc).__name__}: {exc}')
            print(f'DISCOVERY_DETAIL firm={firm!r} index={landing!r} error={type(exc).__name__}: {exc}', flush=True)
        if len(found) >= MAX_PER_FIRM:
            break
    if not found and len(failures) == len(indexes):
        raise RuntimeError('All discovery indexes failed: ' + '; '.join(failures)[:350])
    return found

'''
# Insert immediately before main, after helper functions are declared.
needle = 'def main():\n'
if src.count(needle) != 1:
    raise RuntimeError('main() entry not found uniquely; no changes written')
src = src.replace(needle, addition + needle, 1)

# Only change index discovery. Existing article validation, date extraction,
# translation and archive code remain untouched.
old = '            index_parser = parse(get_html(index, domain))\n            links = candidates(index_parser, index, domain)\n'
new = '            links = discover_candidates(firm, index, domain)\n'
if src.count(old) != 1:
    raise RuntimeError('Expected discovery call not found; no changes written')
src = src.replace(old, new, 1)
# Existing diagnostic references index_parser; replace with safe message.
start = src.find('            if not links:\n                # Diagnostic only:')
end = src.find('            if not links:\n                print(', start)
if start == -1 or end == -1:
    raise RuntimeError('Expected diagnostic block not found; no changes written')
src = src[:start] + src[end:]
compile(src, str(p), 'exec')
p.write_text(src, encoding='utf-8')
print('SOURCE_EXPANSION sources=15; PIMCO/Schroders/Amundi alternate discovery enabled; other firms unchanged', flush=True)
