#!/usr/bin/env python3
"""Collect public search RSS headlines; do not infer institution ratings."""
import datetime as dt
import hashlib
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / 'data' / 'reports.json'
SOURCES = [
 ('Goldman Sachs','https://www.goldmansachs.com/insights/'),
 ('J.P. Morgan Asset Management','https://am.jpmorgan.com/us/en/asset-management/adv/insights/'),
 ('Morgan Stanley','https://www.morganstanley.com/ideas'),
 ('BlackRock','https://www.blackrock.com/corporate/insights'),
 ('UBS','https://www.ubs.com/global/en/wealth-management/insights.html'),
 ('Citi','https://www.citigroup.com/global/insights'),
 ('Bank of America','https://www.bofaml.com/en-us/content/market-strategies-insights.html'),
 ('Fidelity','https://www.fidelity.com/learning-center/trading-investing/markets-sectors'),
 ('Vanguard','https://corporate.vanguard.com/content/corporatesite/us/en/corp/articles.html'),
 ('PIMCO','https://www.pimco.com/us/en/insights'),
 ('Schroders','https://www.schroders.com/en/global/individual/insights/'),
 ('Amundi','https://research-center.amundi.com/'),
 ('State Street','https://www.ssga.com/us/en/individual/insights'),
 ('BNP Paribas','https://wealthmanagement.bnpparibas/en/insights.html'),
 ('Deutsche Bank','https://www.db.com/news'),
]
TOPICS = {'AI・半導体':['artificial intelligence','semiconductor','chip','ai investment','data center'], '株式':['equity','equities','stock','s&p 500','nasdaq'], '債券・金利':['bond','yield','treasury','fixed income','interest rate'], '為替':['currency','forex','dollar','yen','fx '], '景気・金融政策':['inflation','fed ','recession','economy','monetary','central bank'], 'コモディティ':['oil','gold','commodity','copper']}
def clean(s):return re.sub(r'\s+',' ',re.sub(r'<[^>]*>',' ',s or '')).strip()[:350]
def classify(s):
 s=s.lower()
 for name,terms in TOPICS.items():
  if any(term in s for term in terms):return name
 return 'その他'
def fetch(name,url):
 host=urllib.parse.urlparse(url).netloc
 q=f'site:{host} (markets OR outlook OR research OR investment) when:14d'
 rss='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q,'hl':'en-US','gl':'US','ceid':'US:en'})
 req=urllib.request.Request(rss,headers={'User-Agent':'Mozilla/5.0 (compatible; GMICollector/1.0)'})
 with urllib.request.urlopen(req,timeout=18) as res: xml=res.read(1_500_000)
 root=ET.fromstring(xml);items=[]
 for item in root.findall('./channel/item')[:25]:
  title=clean(item.findtext('title'));link=(item.findtext('link') or '').strip()
  if not title or not link:continue
  date=item.findtext('pubDate') or ''
  try:published=parsedate_to_datetime(date).date().isoformat()
  except (TypeError,ValueError):published=''
  desc=clean(item.findtext('description'))
  items.append({'id':hashlib.sha256((name+link).encode()).hexdigest()[:20],'firm':name,'title':title,'url':link,'published':published,'description':desc,'topic':classify(title+' '+desc),'source':'Google News RSS','origin':'検索フィード（公式発表未検証）'})
 return items

def main():
 old={}
 if OUT.exists():
  try:old={r['id']:r for r in json.loads(OUT.read_text())['articles']}
  except (ValueError,KeyError,TypeError):pass
 success=0
 for name,url in SOURCES:
  try:
   entries=fetch(name,url);success+=1
   for entry in entries:old[entry['id']]=entry
   print(f'{name}: {len(entries)}')
  except Exception as exc:print(f'WARNING {name}: {exc}')
 if not success:raise RuntimeError('All source searches failed; preserving existing data')
 cutoff=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=180)).date().isoformat()
 articles=sorted((r for r in old.values() if not r.get('published') or r['published']>=cutoff),key=lambda x:x.get('published',''),reverse=True)[:1500]
 payload={'updated':dt.datetime.now(dt.timezone.utc).isoformat(),'sources':[{'name':n,'url':u} for n,u in SOURCES],'articles':articles,'successful_queries':success,'total_queries':len(SOURCES)}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
 print(f'Saved {len(articles)} articles')
if __name__=='__main__':main()
