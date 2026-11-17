#!/usr/bin/env python3
"""Expand GMI official discovery sources for the current workflow run.
Only edits the working copy of official_pilot.py; archive data is untouched.
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
    ('Vanguard', 'https://corporate.vanguard.com/content/corporatesite/us/en/corp/what-we-think/investing-insights/perspectives-and-commentary.html', 'vanguard.com'),
    ('Fidelity', 'https://www.fidelity.com/learning-center/trading-investing', 'fidelity.com'),
    ('PIMCO', 'https://www.pimco.com/us/en/insights', 'pimco.com'),
    ('UBS', 'https://www.ubs.com/global/en/wealth-management/insights.html', 'ubs.com'),
    ('BNP Paribas', 'https://group.bnpparibas/en/news', 'group.bnpparibas'),
    ('Schroders', 'https://www.schroders.com/en/global/individual/insights/', 'schroders.com'),
    ('Amundi', 'https://research-center.amundi.com/', 'amundi.com'),
    ('State Street', 'https://www.ssga.com/us/en/individual/insights', 'ssga.com'),
    ('Invesco', 'https://www.invesco.com/us/en/insights.html', 'invesco.com'),
]'''
updated, count = re.subn(r'(?ms)^SITES\s*=\s*\[.*?^\]', lambda _: replacement, src, count=1)
if count != 1:
    raise RuntimeError('SITES block not found exactly once; no changes written')
# Vanguard corporate articles use /what-we-think/ paths, which the original
# generic publication-path allowlist does not recognize.
needle = "PUBLICATION_PATH = ("
if updated.count(needle) != 1:
    raise RuntimeError('PUBLICATION_PATH block not found exactly once')
updated = updated.replace(needle, "PUBLICATION_PATH = ('/what-we-think/', ", 1)
compile(updated, str(p), 'exec')
p.write_text(updated, encoding='utf-8')
print('SOURCE_EXPANSION sources=15; Vanguard official index and article-path support enabled')
