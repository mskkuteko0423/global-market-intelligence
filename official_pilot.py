#!/usr/bin/env python3
"""Small, read-only pilot of three official insight indexes. No paid API.
Writes data/official_pilot.json; does not modify reports.json.
"""
import datetime as dt
import json
import pathlib
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / 'data' / 'official_pilot.json'
SITES = [
    ('Goldman Sachs', 'https://www.goldmansachs.com/insights/', 'goldmansachs.com'),
    ('J.P. Morgan Asset Management', 'https://am.jpmorgan.com/us/en/asset-management/adv/insights/', 'jpmorgan.com'),
    ('Morgan Stanley', 'https://www.morganstanley.com/insights', 'morganstanley.com'),
]
MAX_PER_FIRM = 3
class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.href = None; self.parts = []; self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href'); self.parts = []
    def handle_data(self, data):
        if self.href is not None: self.parts.append(data)
    def handle_endtag(self, tag):
        if tag == 'a' and self.href is not None:
            title = re.sub(r'\s+', ' ', ''.join(self.parts)).strip()
            if title: self.links.append((self.href, title))
            self.href = None; self.parts = []
def allowed(url, domain):
    p = urlparse(url); h = (p.hostname or '').lower()
    return p.scheme == 'https' and (h == domain or h.endswith('.' + domain))
def get_html(url, domain):
    if not allowed(url, domain): return None
    req = Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; GMIResearchPilot/1.0)'})
    with urlopen(req, timeout=12) as resp:
        if not allowed(resp.geturl(), domain): return None
        if 'text/html' not in resp.headers.get('Content-Type',''): return None
        body = resp.read(350001)
        if len(body) > 350000: return None
        charset = resp.headers.get_content_charset() or 'utf-8'
        return body.decode(charset, errors='replace')
def main():
    # Imports existing extraction helper from the repository.
    from article_helper import extract
    results=[]; stats=[]
    for firm, index, domain in SITES:
        found=0; extracted=0; error=None
        try:
            page=get_html(index, domain)
            if not page: raise ValueError('Index page unavailable or not verified')
            parser=Links(); parser.feed(page)
            seen=set()
            for href, title in parser.links:
                url=urljoin(index, href).split('#')[0]
                path=urlparse(url).path.rstrip('/')
                if not allowed(url,domain) or url==index or url in seen: continue
                if len(title)<24 or len(title)>180: continue
                if path in ('/insights','/ideas') or any(x in path.lower() for x in ('/privacy','/contact','/terms','/login','/subscribe')): continue
                if not any(x in path.lower() for x in ('insight','article','market','research','idea','outlook','investment','econom','technology','ai-')): continue
                seen.add(url); found+=1
                try: excerpt=extract(url, domain)
                except Exception as exc: excerpt=None; note=str(exc)[:120]
                else: note=''
                if excerpt: extracted+=1
                results.append({'firm':firm,'title':title,'official_url':url,'excerpt':excerpt or '',
                    'excerpt_status':'公式ページの本文抜粋（要約ではありません）' if excerpt else '本文未取得',
                    'error':note})
                if found>=MAX_PER_FIRM: break
        except Exception as exc: error=str(exc)[:200]
        stats.append({'firm':firm,'official_url_candidates':found,'extracted':extracted,'error':error})
        print(f'{firm}: official URL candidates {found}; extracted {extracted}; error {error or "none"}')
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({'updated':dt.datetime.now(dt.timezone.utc).isoformat(),'pilot':True,'stats':stats,'articles':results},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Saved',OUT)
if __name__=='__main__': main()
