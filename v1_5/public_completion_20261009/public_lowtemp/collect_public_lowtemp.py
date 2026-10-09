from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode, urljoin
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor
import csv, json, hashlib, datetime, ssl, re

ROOT = Path(__file__).parent
INPUT = ROOT / '19配置版本_输入范围.csv'
if not INPUT.exists():
    INPUT = Path('/workspace/file_export_proposal/v1_5/requirements/19配置版本_低温报告优先待补清单.csv')
ROWS = list(csv.DictReader(INPUT.open(encoding='utf-8-sig')))
MAX_RESPONSE = 16 * 1024 * 1024

def fetch(url, name, purpose, query='', targets=None):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = Path(str(path) + '.receipt.json')
    if receipt.exists():
        return json.loads(receipt.read_text())
    rec = dict(requested_url=url, retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
               local_file=name, purpose=purpose, query=query, target_models=targets or [], tls_verification=True)
    try:
        with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=18,
                     context=ssl.create_default_context()) as response:
            data = response.read(MAX_RESPONSE + 1)
            truncated = len(data) > MAX_RESPONSE
            if truncated:
                data = data[:MAX_RESPONSE]
            path.write_bytes(data)
            rec.update(status='response_truncated' if truncated else 'ok', http_status=response.status,
                       final_url=response.url, response_headers=dict(response.headers.items()),
                       bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), truncated=truncated)
    except HTTPError as exc:
        data = exc.read(MAX_RESPONSE)
        path.write_bytes(data)
        rec.update(status='http_error', http_status=exc.code, error=str(exc),
                   final_url=exc.url, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    except Exception as exc:
        rec.update(status='fetch_error', error=repr(exc))
    receipt.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + '\n')
    return rec

def search(q, name, targets=None):
    params = dict(websiteid='110000000000000', scope='basic', q=q, pg='10', p='1', cateid='47',
                  pos='title_text,titlepy,infocontent,filenumbername,keyword,contentdescribe',
                  selectFields='title,content,deploytime,_index,url,cdate,infoextends,infocontentattribute,keyword,contentdescribe,sectitle,picpath,columnname,themename,publishgroupname,publishtime,metaid,bexxgk,columnid,infocontenthashcode',
                  group='distinct', level='6',sortFields='[{"name":"deploytime","type":"desc"}]')
    rec = fetch('https://www.miit.gov.cn/search-front-server/api/search/info?' + urlencode(params),
                'search_validated/' + name + '.json', '工信部公共全文搜索：查同型号/配置公开低温检测证据（完整有效接口参数）', q, targets)
    hits = []
    def walk(value):
        if isinstance(value, dict):
            if 'title' in value and 'url' in value:
                hits.append(value)
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
    parsed = False
    if rec['status'] == 'ok':
        try:
            data = json.loads((ROOT / rec['local_file']).read_text())
            walk(data)
            parsed = True
        except Exception as exc:
            rec['json_parse_error'] = repr(exc)
    unique = []
    seen = set()
    for h in hits:
        key = (h.get('url'), h.get('title'))
        if key not in seen:
            # The authoritative complete response is retained separately. Keep derived
            # hit summaries small instead of repeating entire article bodies.
            unique.append({k:h.get(k) for k in ['title','url','deploytime','cdate','publishtime']})
            seen.add(key)
    result = dict(query=q, receipt=rec, json_parsed=parsed, returned_hits=len(unique),
                  pagination_scope='第1页pg=10；同文章可能返回多个栏目URL；不是全网穷尽搜索', hits=unique)
    (ROOT / ('search_validated/' + name + '.hits.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(query=q, status=rec['status'], hits=len(unique)), ensure_ascii=False), flush=True)
    return result

def run():
    targets = []
    for model in sorted({r['model_key'] for r in ROWS}):
        targets.append((model, 'model_' + model, [model]))
    for row in ROWS:
        cfg = row['recommendation_config_id']
        targets.append((cfg, 'config_' + cfg, [row['model_key']]))
    targets += [
        ('新能源汽车 低温 检测报告', 'lowtemp_reports', []),
        ('附录A 18386.1', 'annex_A', []),
        ('低温续驶里程衰减率', 'lowtemp_degradation', []),
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda task: search(*task), targets))
    (ROOT / 'miit_search_results_validated.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
    sites = [
        ('baw', 'https://www.baw.com.cn/', '北京汽车制造厂公共官网入口', ['BAW7000UB44BEV','BAW7000UL47BEV']),
        ('dfxiaokang', 'https://www.dfxiaokang.com/', '东风小康公共官网入口', ['DXK7001RD2BEV','DXK7001RD5BEV']),
        ('gac_toyota', 'https://www.gac-toyota.com.cn/', '广汽丰田公共官网入口', ['GTM6470BFEBEV']),
        ('sgmw', 'https://www.sgmw.com.cn/', '上汽通用五菱公共官网入口', ['LZW7005EVA5KBJA','LZW7005EVC1EBJ']),
        ('yema', 'https://www.yemacar.com/', '野马汽车候选官网入口，须核实站点身份', ['SQJ7002YAC1BEV','SQJ7002YACBEV']),
        ('jmev', 'https://www.jmev.com/', '江铃集团新能源公共官网入口', ['JX7004ESABEV']),
        ('catarc', 'https://www.catarc.ac.cn/', '中汽中心公开检测/认证入口', []),
        ('caeri', 'https://www.caeri.com.cn/', '中国汽研公开检测/认证入口', []),
        ('smvic', 'https://www.smvic.com.cn/', '上海机动车检测认证技术研究中心公开入口', []),
        ('cqc', 'https://www.cqc.com.cn/', '中国质量认证中心公开认证入口；CCC不能替代附录A报告', []),
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        site_results = list(pool.map(lambda x: fetch(x[1], 'portals/' + x[0] + '.html', x[2], targets=x[3]), sites))
    (ROOT / 'portal_results.json').write_text(json.dumps(site_results, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'portal_statuses':[(x['local_file'],x['status'],x.get('http_status')) for x in site_results]}, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    run()
