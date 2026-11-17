#!/usr/bin/env python3
"""GMI official-source configuration, applied before collection.

The 15 sources are defined exactly once below. This script updates only the
SITES assignment in official_pilot.py; it preserves its extraction rules.
It does not touch archived data or article history.
"""
from pathlib import Path
import ast
import re

SOURCES = [
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
]


def main():
    assert len(SOURCES) == 15
    assert len({name for name, _, _ in SOURCES}) == len(SOURCES)
    target = Path(__file__).with_name('official_pilot.py')
    source = target.read_text(encoding='utf-8')
    tree = ast.parse(source, filename=str(target))
    matches = [node for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'SITES' for t in node.targets)]
    if len(matches) != 1:
        raise RuntimeError(f'Expected one SITES assignment; found {len(matches)}. No files changed.')
    node = matches[0]
    lines = source.splitlines(keepends=True)
    new_block = 'SITES = ' + repr(SOURCES) + '\n'
    updated = ''.join(lines[:node.lineno - 1]) + new_block + ''.join(lines[node.end_lineno:])
    compile(updated, str(target), 'exec')
    if updated != source:
        target.write_text(updated, encoding='utf-8')
    print('SOURCE_CONFIG total=15; Vanguard=corporate.vanguard.com; Fidelity/PIMCO=preserved; archive=untouched', flush=True)
    print('SOURCE_CONFIG_NOTE Article discovery remains subject to official_pilot.py filters; success must be verified in Actions.', flush=True)


if __name__ == '__main__':
    main()
