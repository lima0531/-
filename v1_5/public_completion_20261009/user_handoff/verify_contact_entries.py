#!/usr/bin/env python3
"""Read-only HTTP GET for links already present in official cached pages/scripts."""
import concurrent.futures
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SOURCES=ROOT/'contact_sources'
TARGETS=[
 ('jmc_services','https://www.jmc.com.cn/services.html','江铃汽车股份有限公司','round8/jx_public_final_pass/raw/jmc_common.js literal services.html link; no query/state submitted'),
 ('baw_common','https://www.baw.com.cn/js/common.js','北京汽车制造厂有限公司','round9/public_lowtemp/portals/baw.html script src'),
 ('baw_load','https://www.baw.com.cn/js/load_new.js','北京汽车制造厂有限公司','round9/public_lowtemp/portals/baw.html script src'),
 ('gac_api','https://www.gac-toyota.com.cn/2022/src/utils/api.js','广汽丰田汽车有限公司','round9/public_lowtemp/portals/gac_toyota.html script src'),
 ('gac_maps','https://www.gac-toyota.com.cn/2022/src/utils/maps.js','广汽丰田汽车有限公司','round9/public_lowtemp/portals/gac_toyota.html script src'),
 ('sgmw_dealer','https://www.sgmw.com.cn/dealerSearch','上汽通用五菱汽车股份有限公司','round9/public_lowtemp/portals/sgmw.html 经销商/服务商查询 anchor'),
 ('sgmw_after_sale','https://www.sgmw.com.cn/afterSale','上汽通用五菱汽车股份有限公司','round9/public_lowtemp/portals/sgmw.html 新能源服务承诺 anchor'),
 ('jmev_about','https://www.jmev.com/about/','江西江铃集团新能源汽车有限公司','round9/public_lowtemp/portals/jmev.html 关于我们 anchor'),
 ('baw_contact','https://www.baw.com.cn/contact_us.html','北京汽车制造厂有限公司','round9/public_lowtemp/portals/baw.html literal contact_us.html anchor'),
 ('baw_after','https://www.baw.com.cn/after_service.html','北京汽车制造厂有限公司','round9/public_lowtemp/portals/baw.html literal after_service.html anchor'),
 ('gac_config','https://www.gac-toyota.com.cn/2022/config/index.js','广汽丰田汽车有限公司','round9/public_lowtemp/portals/gac_toyota.html script src'),
 ('gac_footer','https://www.gac-toyota.com.cn/2022/src/components/nav/footer.vue?v=20261007','广汽丰田汽车有限公司','homepage httpVueLoader footer template and config version=20261007'),
 ('gac_header','https://www.gac-toyota.com.cn/2022/src/components/nav/header.vue?v=20261007','广汽丰田汽车有限公司','homepage httpVueLoader header template and config version=20261007'),
]


def fetch(t):
    key,url,firm,basis=t
    rec={'key':key,'firm':firm,'requested_url':url,'url_basis':basis,'retrieved_utc':datetime.now(timezone.utc).isoformat(),'tls_verification':True,'method':'GET_only_no_submission','external_message_sent':False}
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html,application/javascript,*/*;q=0.5'})
        with urllib.request.urlopen(req,timeout=25) as resp:
            data=resp.read(2*1024*1024+1)
            rec.update({'http_status':resp.status,'final_url':resp.geturl(),'content_type':resp.headers.get('Content-Type',''),'truncated':len(data)>2*1024*1024})
        if rec['truncated']:
            rec['status']='response_over_limit_not_certified'
        else:
            p=SOURCES/(key+'.txt');p.write_bytes(data)
            rec.update({'status':'retrieved','source_file':str(p.relative_to(ROOT)),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    except urllib.error.HTTPError as e:
        rec.update({'status':'http_error','http_status':e.code,'error':str(e)})
    except Exception as e:
        rec.update({'status':'fetch_error','error':repr(e)})
    (SOURCES/(key+'.receipt.json')).write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return rec


def main():
    SOURCES.mkdir(parents=True,exist_ok=True)
    selected=[t for t in TARGETS if not sys.argv[1:] or t[0] in sys.argv[1:]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool: rows=list(pool.map(fetch,selected))
    all_rows=[json.loads(p.read_text()) for p in sorted(SOURCES.glob('*.receipt.json'))]
    (ROOT/'contact_fetch_receipts.json').write_text(json.dumps(all_rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps([{k:r.get(k) for k in ['key','status','http_status','bytes']} for r in rows],ensure_ascii=False))


if __name__=='__main__':main()
