#!/usr/bin/env python3
"""Read-only diagnostic for official insight indexes. No paid APIs."""
import datetime as dt
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'official_pilot.json'
SITES = [
    ('Goldman Sachs', 'https://www.goldmansachs.com/insights/', 'goldmansachs.com'),
    ('J.P. Morgan Asset Management', 'https://am.jpmorgan.com/us/en/asset-management/adv/insights/', 'jpmorgan.com'),
    ('Morgan Stanley', 'https://www.morganstanley.com/insights', 'morganstanley.com'),
]
MAX_BYTES = 2_000_000

def official(url, domain):
    p = urlparse(url)
    host = (p.hostname or '').lower()
    return p.scheme == 'https' and (host == domain or host.endswith('.' + domain))

def inspect(firm, url, domain):
    result = {'firm': firm, 'index_url': url, 'official_url_candidates': 0,
              'extracted': 0, 'status': 'unknown', 'http_status': None,
              'final_url': None, 'content_type': None, 'bytes_read': 0,
              'size_limit_hit': False, 'error': None}
    try:
        req = Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })
        with urlopen(req, timeout=20) as response:
            result['http_status'] = response.status
            result['final_url'] = response.geturl()
            result['content_type'] = response.headers.get('Content-Type', '')
            if not official(result['final_url'], domain):
                result['status'] = 'redirected_outside_official_domain'
                return result
            if 'text/html' not in result['content_type'].lower():
                result['status'] = 'not_html'
                return result
            content = response.read(MAX_BYTES + 1)
            result['bytes_read'] = len(content)
            result['size_limit_hit'] = len(content) > MAX_BYTES
            result['status'] = 'html_received' if not result['size_limit_hit'] else 'html_over_2mb'
            # This is intentionally a connectivity diagnostic, not an article extractor.
    except HTTPError as exc:
        result['http_status'] = exc.code
        result['status'] = 'http_error'
        result['error'] = str(exc)[:180]
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        result['status'] = 'connection_error'
        result['error'] = f'{type(exc).__name__}: {exc}'[:180]
    return result

def main():
    stats = []
    for firm, url, domain in SITES:
        r = inspect(firm, url, domain)
        stats.append(r)
        print(f"{firm}: status={r['status']}; http={r['http_status']}; "
              f"bytes={r['bytes_read']}; final={r['final_url']}; error={r['error']}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'updated': dt.datetime.now(dt.timezone.utc).isoformat(),
                               'pilot': True, 'diagnostic': True, 'stats': stats, 'articles': []},
                              ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved', OUT, flush=True)

if __name__ == '__main__':
    main()
