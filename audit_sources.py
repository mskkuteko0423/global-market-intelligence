#!/usr/bin/env python3
"""Read-only official-source discovery audit; never modifies production data."""
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from official_pilot import get_html, parse, candidates

SOURCES = [
 ('Goldman Sachs','https://www.goldmansachs.com/insights/','goldmansachs.com'),
 ('J.P. Morgan Asset Management','https://am.jpmorgan.com/us/en/asset-management/adv/insights/','jpmorgan.com'),
 ('Morgan Stanley','https://www.morganstanley.com/insights','morganstanley.com'),
 ('BlackRock','https://www.blackrock.com/us/individual/insights','blackrock.com'),
 ('Vanguard','https://investor.vanguard.com/investor-resources-education','vanguard.com'),
 ('Fidelity','https://www.fidelity.com/learning-center','fidelity.com'),
 ('Capital Group','https://www.capitalgroup.com/institutional/insights.html','capitalgroup.com'),
 ('PIMCO','https://www.pimco.com/us/en/insights','pimco.com'),
 ('UBS','https://www.ubs.com/global/en/wealth-management/insights.html','ubs.com'),
 ('J.P. Morgan Research','https://www.jpmorgan.com/insights','jpmorgan.com'),
 ('BNP Paribas','https://group.bnpparibas/en/news','bnpparibas'),
 ('Schroders','https://www.schroders.com/en/global/individual/insights/','schroders.com'),
 ('Amundi','https://research-center.amundi.com/','amundi.com'),
 ('State Street','https://www.ssga.com/us/en/individual/insights','ssga.com'),
 ('Invesco','https://www.invesco.com/us/en/insights.html','invesco.com'),
]
# Fix a domain typo explicitly, rather than silently accepting it.
SOURCES[10] = ('BNP Paribas','https://group.bnpparibas/en/news','group.bnpparibas')

def main():
    output=[]
    for firm, index, domain in SOURCES:
        row={'firm':firm,'index':index,'domain':domain,'status':'unverified','candidates':0,'examples':[],'error':None}
        try:
            page=parse(get_html(index,domain))
            found=candidates(page,index,domain)
            row['candidates']=len(found)
            row['examples']=[{'title':label[:140],'url':url} for url,label in found[:3]]
            row['status']='candidate_links_found' if found else 'page_accessible_no_matching_links'
        except Exception as exc:
            row['status']='fetch_error'
            row['error']=f'{type(exc).__name__}: {str(exc)[:160]}'
        output.append(row)
        print(f"SOURCE_AUDIT {firm}: {row['status']} candidates={row['candidates']} error={row['error']}",flush=True)
    path=Path('data/source_audit.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'updated':datetime.now(timezone.utc).isoformat(),'note':'Candidate links only; not verified articles. No production data modified.','sources':output},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'SOURCE_AUDIT_TOTAL tested={len(output)} with_candidates={sum(x["candidates"]>0 for x in output)}')
if __name__=='__main__': main()
