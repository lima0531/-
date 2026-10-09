from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor
import ssl,hashlib,datetime,json,re
ROOT=Path(__file__).parent

def fetch(name,url,purpose):
    target=ROOT/(name+'.html');receipt=ROOT/(name+'.receipt.json')
    r={'request_url':url,'purpose':purpose,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tls_verification':True,'request_method':'GET'}
    if receipt.exists():return json.loads(receipt.read_text())
    try:
        with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.miit.gov.cn/'}),timeout=25,context=ssl.create_default_context()) as response:
            raw=response.read();r.update(http_status=response.status,final_url=response.url,response_headers=dict(response.headers),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),evidence_file=str(target))
        target.write_bytes(raw)
        r['status']='retrieved'
    except Exception as e:r.update(status='not_retrieved',error_type=type(e).__name__,error=str(e))
    receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2));return r


def search_url(q,begin='',end=''):
    a=dict(websiteid='110000000000000',scope='basic',q=q,pg='40',p='1',cateid='47',pos='title_text,titlepy,infocontent,filenumbername,keyword,contentdescribe',pq='',oq='',eq='',begin=begin,end=end,dateField='deploytime',selectFields='title,content,deploytime,_index,url,cdate,infoextends,infocontentattribute,keyword,contentdescribe,sectitle,picpath,columnname,themename,publishgroupname,publishtime,metaid,bexxgk,columnid,infocontenthashcode',group='distinct',highlightFields='title_text,infocontent,webid',level='6',sortFields='[{"name":"deploytime","type":"desc"}]')
    return 'https://www.miit.gov.cn/search-front-server/api/search/info?'+urlencode(a)

JOBS=[
    ('miit_first_nev_window',search_url('新能源汽车','2014-08-25','2014-09-05'),'第一批主管部门原页最后定向发现；2014-08-25至2014-09-05部署时间窗口内新能源汽车关键词；命中不直接等于首批登记日'),
    ('miit_first_number_year',search_url('第54号','2014-01-01','2014-12-31'),'第一批主管部门原页最后定向发现；2014年部署时间内第54号关键词，须正文及文件号匹配才可作证'),
    ('standard_registry_query','https://std.samr.gov.cn/gb/search/gbQueryPage?'+urlencode({'searchText':'GB/T 18386.1-2021'}),'全国标准信息公共服务平台公共检索页面的一次最终定向可达性检查；不关闭TLS、不循环重试；所查标准元数据须完整编号详情页匹配'),
]
if __name__=='__main__':
    results=list(ThreadPoolExecutor(max_workers=3).map(lambda args:fetch(*args),JOBS))
    (ROOT/'attempts.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    for result in results:
        print(json.dumps({k:v for k,v in result.items() if k!='response_headers'},ensure_ascii=False),flush=True)
        if result['status']=='retrieved' and 'search-front-server' in result['request_url']:
            text=Path(result['evidence_file']).read_text(errors='replace')
            try:
                obj=json.loads(text);hits=[]
                def walk(x):
                    if isinstance(x,dict):
                        if 'title' in x and 'url' in x:hits.append({k:x.get(k) for k in ['title','url','deploytime','cdate','columnname','infocontent','content']})
                        for v in x.values():walk(v)
                    elif isinstance(x,list):
                        for v in x:walk(v)
                walk(obj['data']['searchResult']['dataResults']);path=Path(result['evidence_file']).with_suffix('.hits.json');path.write_text(json.dumps(hits,ensure_ascii=False,indent=2));print('HITS',len(hits),json.dumps(hits,ensure_ascii=False)[:6500],flush=True)
            except Exception as e:print('JSON_PARSE_ERROR',str(e),flush=True)
