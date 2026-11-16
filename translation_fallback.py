"""Best-effort machine translation of public market articles, no paid API.

Uses two unauthenticated public endpoints, each of which can fail or change.
Public source excerpts are sent to third-party translation services.
No retries beyond the two providers; no secrets or user data sent.
"""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TIMEOUT = 7
MAX_CHARS = 450

def _fetch(url):
    req = Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; GMI-translation-pilot/1.0)',
        'Accept': 'application/json',
    })
    with urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)

def _google(text):
    qs = urlencode({'client':'gtx','sl':'en','tl':'ja','dt':'t','q':text})
    data = _fetch('https://translate.googleapis.com/translate_a/single?' + qs)
    return ''.join(seg[0] for seg in data[0] if seg and seg[0])

def _mymemory(text):
    qs = urlencode({'q':text,'langpair':'en|ja'})
    data = _fetch('https://api.mymemory.translated.net/get?' + qs)
    if int(data.get('responseStatus', 0)) != 200:
        raise ValueError('service_status_' + str(data.get('responseStatus')))
    return str(data.get('responseData', {}).get('translatedText', '') or '')

def _looks_japanese(text):
    return bool(re.search(r'[\u3040-\u30ff\u3400-\u9fff]', text))

def translate_public_text(text):
    text = (text or '').strip()[:MAX_CHARS]
    if not text:
        return '', None, 'empty_input'
    errors = []
    for name, fn in [('google_public', _google), ('mymemory_public', _mymemory)]:
        try:
            result = fn(text).strip()
            if result and _looks_japanese(result):
                return result, name, None
            errors.append(name + ':no_japanese_output')
        except HTTPError as e:
            errors.append(f'{name}:HTTP_{e.code}')
        except (URLError, TimeoutError, OSError) as e:
            errors.append(f'{name}:{type(e).__name__}')
        except (ValueError, KeyError, TypeError, IndexError, json.JSONDecodeError) as e:
            errors.append(f'{name}:{type(e).__name__}')
    return '', None, ';'.join(errors)
