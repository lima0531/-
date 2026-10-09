#!/usr/bin/env python3
"""Preserve responses from untried public JX search and primary-source leads."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import hashlib
import json
import ssl

ROOT = Path(__file__).resolve().parent
TARGET = 'JX6550T-M5BEV'

def fetch(item):
    name, url, purpose = item
    path = ROOT / 'raw' / (name + '.html')
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = path.with_suffix('.receipt.json')
    if receipt.exists():
        return json.loads(receipt.read_text())
    row = {'name': name, 'requested_url': url, 'purpose': purpose,
           'retrieved_at_utc': datetime.now(timezone.utc).isoformat(), 'tls_verified': True}
    try:
        with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=20,
                     context=ssl.create_default_context()) as response:
            content = response.read(12 * 1024 * 1024 + 1)
            if len(content) > 12 * 1024 * 1024:
                raise ValueError('Response exceeds bounded receipt size')
            path.write_bytes(content)
            row.update(http_status=response.status, final_url=response.url, bytes=len(content),
                       sha256=hashlib.sha256(content).hexdigest(),
                       local_file=path.relative_to(ROOT).as_posix(),
                       response_content_type=response.headers.get('Content-Type'), status='received')
    except HTTPError as error:
        content = error.read(1024 * 1024)
        path.write_bytes(content)
        row.update(http_status=error.code, status='http_error', error=str(error), bytes=len(content),
                   sha256=hashlib.sha256(content).hexdigest(), local_file=path.relative_to(ROOT).as_posix())
    except Exception as error:
        row.update(status='request_failed', error=repr(error))
    receipt.write_text(json.dumps(row, ensure_ascii=False, indent=2) + '\n')
    return row

def search_url(base, key, query):
    return base + '?' + urlencode({key: query})

if __name__ == '__main__':
    tasks = [
        ('bing_exact', search_url('https://www.bing.com/search', 'q', '"'+TARGET+'"'), 'Public index lead discovery; not a primary capacity source'),
        ('bing_config', search_url('https://www.bing.com/search', 'q', '"NC010086"'), 'Public recommendation configuration ID leads'),
        ('baidu_exact', search_url('https://www.baidu.com/s', 'wd', TARGET), 'Independent public index lead discovery'),
        ('google_exact', search_url('https://www.google.com/search', 'q', '"'+TARGET+'"'), 'Independent public index lead discovery'),
        ('bing_storage', search_url('https://www.bing.com/search', 'q', '"L173C01" "江铃"'), 'Storage variant source leads; cannot bridge configurations by name'),
        ('duck_exact', search_url('https://html.duckduckgo.com/html/', 'q', '"'+TARGET+'"'), 'Independent public index lead discovery'),
        ('duck_energy', search_url('https://html.duckduckgo.com/html/', 'q', TARGET+' 总能量'), 'Public energy leads; strict model and date checks required'),
        ('duck_config', search_url('https://html.duckduckgo.com/html/', 'q', '"NC010086"'), 'Public configuration ID leads'),
        ('duck_storage', search_url('https://html.duckduckgo.com/html/', 'q', '"L173C01" 江铃'), 'Storage variant leads; component coincidence cannot identify the vehicle'),
        ('cdqc_JX', 'https://www.cdqc.org.cn/2747/15877/643981', 'Association reproduction of tax48, not a controlling original'),
        ('sohu_reprint', 'https://www.sohu.com/a/499829552_118021', 'Tax48 reproduction, not a controlling original'),
        ('jmc_current_config', 'https://www.jmc.com.cn/config.html?car_type=0&brand_id=1092&configure_id=1007&car_category=2', 'Official current E全顺 lead; not a historical model/config/date match'),
        ('jmc_config_js', 'https://www.jmc.com.cn/js/config.eaf13e68.js', 'Official public frontend for configuration query'),
        ('jmc_common_js', 'https://www.jmc.com.cn/js/chunk-common.319c61b5.js', 'Official public frontend exposing read-only configuration endpoint'),
        ('jmc_current_parameter_api', 'https://sale-api.jmc.com.cn/api/parameter/getconfigurelist?'+urlencode(dict(brand_id=1092,configure_id=1007,car_types=0,sub_model_id=0)), 'Read-only GET exposed by official frontend; not historical certification'),
    ]
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(fetch, tasks))
    (ROOT / 'search_requests.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n')
    for row in rows:
        print(json.dumps({k:v for k,v in row.items() if k in ('name','status','http_status','bytes','error')}, ensure_ascii=False), flush=True)
