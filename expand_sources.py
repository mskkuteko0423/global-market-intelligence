#!/usr/bin/env python3
"""Expand GMI's pilot sources without modifying the original collector on disk.
The new source URLs are discovery candidates, not confirmed working article feeds.
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
    ('BNP Paribas', 'https://group.bnpparibas/en/news', 'bnpparibas'),
    ('Schroders', 'https://www.schroders.com/en/global/individual/insights/', 'schroders.com'),
    ('Amundi', 'https://research-center.amundi.com/', 'amundi.com'),
    ('State Street', 'https://www.ssga.com/us/en/individual/insights', 'ssga.com'),
    ('Invesco', 'https://www.invesco.com/us/en/insights.html', 'invesco.com'),
]'''
# The BNP site is group.bnpparibas, not a .com domain.
replacement = replacement.replace("'bnpparibas')", "'group.bnpparibas')")
pattern = r'(?ms)^SITES\s*=\s*\[.*?^\]'
updated, count = re.subn(pattern, lambda _: replacement, src, count=1)
if count != 1:
    raise RuntimeError('SITES block not found exactly once; original collector left unchanged')
compile(updated, str(p), 'exec')
p.write_text(updated, encoding='utf-8')
print('SOURCE_EXPANSION sources=15; candidate URLs unverified; per-source stats will show failures')
