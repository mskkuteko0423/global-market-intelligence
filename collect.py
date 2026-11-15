#!/usr/bin/env python3
"""Bounded market RSS collection; translate titles and verified article excerpts."""
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from translate_helper import translate
from article_helper import extract

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
TOPICS = {'AIã»åå°ä½':['artificial intelligence','semiconductor','chip','ai investment','data center'], 'æ ªå¼':['equity','equities','stock','s&p 500','nasdaq'], 'åµå¸ã»éå©':['bond','yield','treasury','fixed income','interest rate'], 'çºæ¿':['currency','forex','dollar','yen','fx '], 'æ¯æ°ã»éèæ¿ç­':['inflation','fed ','recession','economy','monetary','central bank'], 'ã³ã¢ãã£ãã£':['oil','gold','commodity','copper']}
AI_RE = re.compile(r'artificial intelligence|\bai\b|genai|\bllm\b|semiconductor|\bchip\b|\bgpu\b|nvidia|nvda|data cent(?:er|re)|hyperscal|hbm|tsmc|åå°ä½|äººå·¥ç¥è½|ãã¼ã¿ã»ã³ã¿ã¼', re.I)

def clean(s):
 return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',s or ''))).strip()[:350]

def classify(s):
 s=s.lower()
 return next((name for name,terms in TOPICS.items() if any(term in s for term in terms)),'ãã®ä»')

def official(url, host):
 try:
  p=urllib.parse.urlparse(html.unescape(url))
  h=(p.hostname or '').lower()
  return p.scheme=='https' and (h==host or h.endswith('.'+host)) and not p.username and not p.password
 except ValueError:return False

class Hrefs(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a':
   for k,v in attrs:
    if k=='href' and v:self.links.append(v)

def resolve_official(item, host):
 """Only accept direct publisher URLs embedded in RSS metadata; no untrusted redirects."""
 for field in ('link','description'):
  raw=item.findtext(field) or ''
  if official(raw.strip(),host):return raw.strip()
  parser=Hrefs()
  try:parser.feed(html.unescape(raw))
  except Exception:continue
  for link in parser.links:
   if official(link,host):return link
 return ''

def fetch(name,url):
 host=urllib.parse.urlparse(url).hostname
 q=f'site:{host} (markets OR outlook OR research OR investment) when:14d'
 rss='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':q,'hl':'en-US','gl':'US','ceid':'US:en'})
 req=urllib.request.Request(rss,headers={'User-Agent':'Mozilla/5.0 (compatible; GMICollector/1.0)'})
 with urllib.request.urlopen(req,timeout=18) as res:xml=res.read(1_500_000)
 root=ET.fromstring(xml);items=[]
 for item in root.findall('./channel/item')[:25]:
  title=clean(item.findtext('title'));link=(item.findtext('link') or '').strip()
  if not title or not link:continue
  try:published=parsedate_to_datetime(item.findtext('pubDate') or '').date().isoformat()
  except (TypeError,ValueError):published=''
  desc=clean(item.findtext('description'))
  entry={'id':hashlib.sha256((name+link).encode()).hexdigest()[:20],'firm':name,'title':title,'url':link,'published':published,'description':desc,'topic':classify(title+' '+desc),'source':'Google News RSS','origin':'æ¤ç´¢ãã£ã¼ãï¼å¬å¼çºè¡¨æªæ¤è¨¼ï¼'}
  direct=resolve_official(item,host)
  if direct:entry['official_url']=direct
  items.append(entry)
 return items

def main():
 old={}
 if OUT.exists():
  try:old={r['id']:r for r in json.loads(OUT.read_text(encoding='utf-8'))['articles']}
  except (ValueError,KeyError,TypeError):pass
 success=0
 for name,url in SOURCES:
  try:
   entries=fetch(name,url);success+=1
   for entry in entries:
    previous=old.get(entry['id'],{})
    for key in ('title_ja','description_ja','excerpt','excerpt_ja','excerpt_status','official_url'):
     if previous.get(key) and not entry.get(key):entry[key]=previous[key]
    old[entry['id']]=entry
   print(f'{name}: {len(entries)}')
  except Exception as exc:print(f'WARNING {name}: {exc}')
 if not success:raise RuntimeError('All source searches failed; preserving existing data')
 cutoff=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=180)).date().isoformat()
 articles=sorted((r for r in old.values() if not r.get('published') or r['published']>=cutoff),key=lambda x:x.get('published',''),reverse=True)[:1500]
 # Single shared hard cap across all translation requests, including excerpts.
 translation_budget=30
 for a in articles:
  for original,translated in [('title','title_ja'),('description','description_ja')]:
   if translation_budget<=0:break
   if a.get(translated) or not a.get(original):continue
   translation_budget-=1
   try:a[translated]=translate(a[original])
   except Exception as exc:print(f'WARNING translation {a["id"]} {original}: {exc}')
  if translation_budget<=0:break
 extraction_budget=5;found=0;extracted=0
 for a in articles:
  if extraction_budget<=0:break
  if a.get('excerpt_ja') or not AI_RE.search(a.get('title','')+' '+a.get('description','')):continue
  source_url=next((u for n,u in SOURCES if n==a.get('firm')),None)
  if not source_url:continue
  allowed=urllib.parse.urlparse(source_url).hostname
  target=a.get('official_url') or (a.get('url') if official(a.get('url',''),allowed) else '')
  if not target or not official(target,allowed):
   a['excerpt_status']='å¬å¼è¨äºURLæªç¢ºèª'
   continue
  found+=1;extraction_budget-=1
  try:
   excerpt=extract(target,allowed)
   if not excerpt:a['excerpt_status']='æ¬ææªåå¾';continue
   a['excerpt']=excerpt;extracted+=1
   if translation_budget>0:
    translation_budget-=1
    a['excerpt_ja']=translate(excerpt[:900])
    a['excerpt_status']='å¬å¼ãã¼ã¸æ¬æã®æç²è¨³ï¼AIè¦ç´ã§ã¯ããã¾ããï¼'
   else:a['excerpt_status']='æ¬æåå¾æ¸ã¿ã»ç¿»è¨³å¾ã¡'
  except Exception as exc:
   a['excerpt_status']='æ¬æåå¾ã¾ãã¯ç¿»è¨³å¤±æ'
   print(f'WARNING excerpt {a["id"]}: {exc}')
 payload={'updated':dt.datetime.now(dt.timezone.utc).isoformat(),'sources':[{'name':n,'url':u} for n,u in SOURCES],'articles':articles,'successful_queries':success,'total_queries':len(SOURCES)}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(f'Saved {len(articles)} articles; official URL candidates {found}; extracted {extracted}; translation attempts <=30; extraction attempts <=5')
if __name__=='__main__':main()
