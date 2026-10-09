#!/usr/bin/env python3
"""Save at most nine directed HTTPS requests; never repeat a recorded URL."""
import argparse
import hashlib
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
MAX_REQUESTS = 9


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(url, name, purpose):
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / 'requests.json'
    records = [json.loads(p.read_text()) for p in sorted(OUT.glob('*.receipt.json'))]
    prior = next((x for x in records if x['request_url'] == url), None)
    if prior:
        return prior
    if len(records) >= MAX_REQUESTS:
        raise RuntimeError('Final nine-request budget exhausted')
    if urllib.parse.urlparse(url).scheme != 'https':
        raise ValueError('Only HTTPS with default TLS verification is allowed')
    if '/' in name or name in ('.', '..'):
        raise ValueError('Evidence filename must be a basename')
    receipt = {'request_url': url, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
               'purpose': purpose, 'tls_verification': True, 'proxy_environment_preserved': True,
               'request_method': 'GET', 'automatic_redirects': False, 'same_url_retries': 0}
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'purchase-tax-public-source-audit/1.0'})
        try:
            response = opener.open(req, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read()
            receipt.update(http_status=response.code, final_url=response.geturl(), response_headers=dict(response.headers))
        path = OUT / name
        path.write_bytes(body)
        receipt.update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), evidence_file=name,
                       status='retrieved' if receipt['http_status'] == 200 else 'http_error',
                       stored_body_representation='urllib.read after transfer decoding; Content-Encoding preserved')
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        receipt.update(status='request_failed', error_type=type(error).__name__, error=str(error))
    receipt['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    (OUT / (name + '.receipt.json')).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    records = [json.loads(p.read_text()) for p in sorted(OUT.glob('*.receipt.json'))]
    log.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url')
    parser.add_argument('name')
    parser.add_argument('purpose')
    args = parser.parse_args()
    print(json.dumps(fetch(args.url, args.name, args.purpose), ensure_ascii=False))
