from collect_public_lowtemp import ROOT, ROWS, fetch
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
import json

def run():
    queries=sorted({r['model_key'] for r in ROWS})+['低温','18386.1']
    tasks=[]
    for q in queries:
        tasks.append(('https://www.gatc.ac.cn/search/?'+urlencode(dict(title=q,model='article,pic',navlist='329')),
                      'institution_queries/gatc_'+q+'.html','广州检验中心官网可见GET搜索表单查询',q,[q] if q.endswith('BEV') or 'BEV' in q else []))
        tasks.append(('https://hss.smvic.com.cn/indexsearch?'+urlencode(dict(search=q)),
                      'institution_queries/smvic_'+q+'.html','SMVIC认证平台可见GET搜索表单查询，不能用CCC证书替代附录A报告',q,[q] if 'BEV' in q else []))
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts=list(pool.map(lambda x:fetch(*x),tasks))
    (ROOT/'institution_query_receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n')
    for r in receipts:
        print(r['local_file'],r['status'],r.get('http_status'),r.get('bytes'),flush=True)

if __name__=='__main__':run()
