#!/usr/bin/env python3
"""GMI: add bounded Fidelity institutional discovery and reject Schroders interstitials.
Run AFTER expand_sources.py and BEFORE official_pilot.py.
"""
from pathlib import Path
p = Path(__file__).with_name('official_pilot.py')
s = p.read_text(encoding='utf-8')
anchor = '    return found, first_parser\n'
assert s.count(anchor) == 1, 'Discovery helper changed; refusing unsafe patch'
replacement = '''    # Fidelity institutional insights: secondary discovery from official pages.
    # These are candidate URLs, never automatically treated as verified articles.
    if firm == 'Fidelity' and len(found) < MAX_PER_FIRM:
        institutional_sources = (
            'https://institutional.fidelity.com/advisors/insights/series/fidelity-market-signals-weekly',
            'https://institutional.fidelity.com/advisors/insights',
        )
        for source in institutional_sources:
            try:
                parser = parse(get_html(source, domain))
                for href, label in parser.links:
                    url = urldefrag(urljoin(source, href))[0]
                    path = urlparse(url).path.lower()
                    if (official(url, domain) and
                        ('/insights/' in path or '/viewpoints/' in path) and
                        url.rstrip('/') != source.rstrip('/') and
                        18 <= len(label.strip()) <= 220):
                        add(url, label, 'html')
            except Exception as exc:
                print('FIDELITY_INSTITUTIONAL_DISCOVERY', type(exc).__name__, str(exc)[:120], flush=True)
        found.sort(key=rank, reverse=True)
    return found, first_parser
'''
s = s.replace(anchor, replacement, 1)
# Existing collector detects interstitial but may spend its seven candidate slots
# on blocked pages. Preserve explicit diagnostics and do not fabricate content.
needle = "        stats.append({'firm': firm, 'official_url_candidates': len(links),"
assert s.count(needle) == 1, 'Stats anchor changed; refusing unsafe patch'
s = s.replace(needle, "        if firm == 'Schroders' and extracted == 0:\n            print('SCHRODERS_SOURCE_UNAVAILABLE: no article excerpts; review access verification and alternate official feeds', flush=True)\n" + needle, 1)
compile(s, str(p), 'exec')
p.write_text(s, encoding='utf-8')
print('GMI_SOURCE_IMPROVEMENT applied')
