"""Optional no-cost translation via public Google Translate web endpoint.
Not an official API; availability and terms may change. Fail open to English.
"""
import json
import time
import urllib.parse
import urllib.request


def translate(text):
    text = (text or '').strip()
    if not text:
        return ''
    params = urllib.parse.urlencode({
        'client': 'gtx', 'sl': 'en', 'tl': 'ja', 'dt': 't', 'q': text
    })
    req = urllib.request.Request(
        'https://translate.googleapis.com/translate_a/single?' + params,
        headers={'User-Agent': 'Mozilla/5.0 (compatible; GMI/1.0)'},
    )
    with urllib.request.urlopen(req, timeout=8) as response:
        data = json.load(response)
    result = ''.join(segment[0] for segment in data[0] if segment and segment[0])
    if not result:
        raise ValueError('Empty translation')
    time.sleep(0.15)
    return result
