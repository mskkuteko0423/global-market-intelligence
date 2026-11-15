"""Best-effort public HTML extraction; no paid services, no AI inference."""
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import re

class Reader(HTMLParser):
    def __init__(self):
        super().__init__(); self.depth=0; self.parts=[]; self.in_p=0; self.buf=[]
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','nav','footer','header','aside'): self.depth+=1
        if tag=='p' and not self.depth: self.in_p+=1; self.buf=[]
    def handle_endtag(self, tag):
        if tag=='p' and self.in_p:
            t=re.sub(r'\s+',' ',''.join(self.buf)).strip()
            if len(t)>=75: self.parts.append(t)
            self.in_p-=1; self.buf=[]
        if tag in ('script','style','nav','footer','header','aside') and self.depth: self.depth-=1
    def handle_data(self, data):
        if self.in_p and not self.depth: self.buf.append(data)

def extract(url, allowed_host, max_bytes=350_000):
    """Only fetch HTTPS pages on the configured institution's own domain."""
    parsed=urlparse(url)
    host=(parsed.hostname or '').lower()
    allowed=(allowed_host or '').lower()
    if parsed.scheme!='https' or not (host==allowed or host.endswith('.'+allowed)):
        return None
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; GMICollector/1.0)'})
    with urlopen(req,timeout=8) as resp:
        final=urlparse(resp.geturl())
        fh=(final.hostname or '').lower()
        if final.scheme!='https' or not (fh==allowed or fh.endswith('.'+allowed)): return None
        ct=resp.headers.get('Content-Type','')
        if 'text/html' not in ct: return None
        raw=resp.read(max_bytes+1)
        if len(raw)>max_bytes: return None
        charset=resp.headers.get_content_charset() or 'utf-8'
    p=Reader(); p.feed(raw.decode(charset,errors='replace'))
    unique=[]; seen=set()
    for item in p.parts:
        if item not in seen: unique.append(item); seen.add(item)
    if len(unique)<2: return None
    return ' '.join(unique[:5])[:1800]
