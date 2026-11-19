#!/usr/bin/env python3
"""Conservatively confirm publisher-declared publication dates from two matching metadata signals."""
import datetime as dt
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

FILE = Path(__file__).resolve().parent / 'data' / 'official_pilot.json'
MAX_PAGES = 150
MAX_BYTES = 900_000

class Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.jsonld = []
        self.in_ld = False
        self.buf = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'meta':
            key = (a.get('property') or a.get('name') or a.get('itemprop') or '').lower()
            if key and a.get('content'):
                self.meta.setdefault(key, []).append(a['content'])
        if tag == 'script' and 'ld+json' in a.get('type','').lower():
            self.in_ld = True
            self.buf = []
    def handle_data(self, data):
        if self.in_ld: self.buf.append(data)
    def handle_endtag(self, tag):
        if tag == 'script' and self.in_ld:
            self.jsonld.append(''.join(self.buf))
            self.in_ld = False

def date_only(value):
    if not isinstance(value,str): return None
    m = re.match(r'^(20\d\d-\d\d-\d\d)(?:T|\s|$)',value.strip())
    if not m: return None
    try:
        d = dt.date.fromisoformat(m.group(1))
        if dt.date(2000,1,1) <= d <= dt.datetime.now(dt.timezone.utc).date(): return d.isoformat()
    except ValueError: pass
    return None

def json_dates(node):
    found=[]
    if isinstance(node,list):
        for item in node: found += json_dates(item)
    elif isinstance(node,dict):
        types=node.get('@type',[])
        if isinstance(types,str): types=[types]
        if any(t.lower() in ('article','newsarticle','blogposting','analysisnewsarticle','report') for t in types if isinstance(t,str)):
            d=date_only(node.get('datePublished'))
            if d: found.append(d)
        for key in ('@graph','mainEntity'):
            if key in node: found += json_dates(node[key])
    return found

def check(url):
    p=urlsplit(url)
    if p.scheme != 'https' or not p.hostname: return None,'invalid_url'
    # Reject redirects to unrelated hosts, and read only bounded HTML.
    req=Request(url,headers={'User-Agent':'GMIResearchPilot/3.0'})
    with urlopen(req,timeout=7) as response:
        target=urlsplit(response.geturl())
        host=p.hostname.lower(); final=(target.hostname or '').lower()
        if not (final==host or final.endswith('.'+host) or host.endswith('.'+final)):
            return None,'cross_host_redirect'
        if 'text/html' not in response.headers.get('Content-Type','').lower(): return None,'not_html'
        raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES: return None,'too_large'
        page=raw.decode(response.headers.get_content_charset() or 'utf-8','replace')
    parser=Metadata();parser.feed(page)
    meta=[]
    for key in ('article:published_time','datepublished','date','pubdate','dc.date.issued'):
        meta += [d for x in parser.meta.get(key,[]) if (d:=date_only(x))]
    structured=[]
    for block in parser.jsonld:
        try: structured += json_dates(json.loads(block))
        except (ValueError,TypeError): pass
    matches=set(meta)&set(structured)
    if len(matches)==1 and len(set(meta))==1 and len(set(structured))==1:
        return matches.pop(),'matching_article_metadata_and_jsonld'
    if not meta and not structured: return None,'no_publication_metadata'
    return None,'missing_or_conflicting_independent_metadata'

def main():
    data=json.loads(FILE.read_text(encoding='utf-8'))
    verified=0; failures={}; examined=0
    for row in data.get('articles',[]):
        if row.get('page_type')!='article_candidate' or not row.get('official_url'): continue
        if examined>=MAX_PAGES: break
        examined+=1
        try: date,reason=check(row['official_url'])
        except Exception as exc: date,reason=None,'fetch_'+type(exc).__name__
        if date:
            row['published']=date
            row['date_status']='publisher_metadata_crosschecked'
            row['publication_date_status']='publisher_declared_metadata_agreement'
            row['publication_date_evidence']='article:published_time (or equivalent) and article JSON-LD datePublished agree on official page'
            verified+=1
        else:
            row['published']=None
            row['date_status']='unverified'
            row['publication_date_status']='unknown'
            row.pop('publication_date_evidence',None)
            failures[reason]=failures.get(reason,0)+1
    data['date_verification']={'examined':examined,'verified':verified,'unverified_reasons':failures,
        'method':'Official-page publication metadata cross-checked against article JSON-LD; publisher-declared, not independently fact-checked'}
    data.setdefault('archive_quality',{})['published_dates_verified']=verified
    FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('DATE_VERIFICATION',json.dumps(data['date_verification'],ensure_ascii=False),flush=True)
if __name__=='__main__': main()
