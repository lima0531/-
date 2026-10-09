#!/usr/bin/env python3
"""Bounded public archive requests; preserve successful bodies and HTTP errors."""
import csv
import hashlib
import json
import ssl
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent


def fetch(name, url, purpose, timeout=25, payload=None, extra_headers=None):
    body_path = ROOT / (name + '.html')
    receipt_path = ROOT / (name + '.receipt.json')
    if receipt_path.exists():
        return json.loads(receipt_path.read_text())
    row = {'request_url': url, 'purpose': purpose, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
           'request_method': 'POST' if payload is not None else 'GET', 'tls_verification': True, 'retry_policy': 'one request; cache receipt thereafter'}
    if payload is not None:
        row['request_body_utf8'] = payload.decode('utf-8')
    raw = None
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        headers.update(extra_headers or {})
        with urlopen(Request(url, headers=headers, data=payload), context=ssl.create_default_context(), timeout=timeout) as response:
            raw = response.read()
            row.update(http_status=response.status, final_url=response.url, response_headers=dict(response.headers), status='retrieved')
    except HTTPError as error:
        raw = error.read()
        row.update(http_status=error.code, final_url=error.url, response_headers=dict(error.headers),
                   status='http_error', error_type=type(error).__name__, error=str(error))
    except Exception as error:
        row.update(status='not_retrieved', error_type=type(error).__name__, error=str(error))
    if raw is not None:
        body_path.write_bytes(raw)
        row.update(evidence_file=str(body_path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    receipt_path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + '\n')
    return row


def batch(jobs):
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda job: fetch(*job), jobs))
    for row in results:
        print(json.dumps({k: row.get(k) for k in ('request_url','purpose','status','http_status','bytes','sha256','error')}, ensure_ascii=False), flush=True)
    return results


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('jobs_json', help='JSON list of [name,url,purpose] jobs')
    args = parser.parse_args()
    batch(json.loads(Path(args.jobs_json).read_text()))
