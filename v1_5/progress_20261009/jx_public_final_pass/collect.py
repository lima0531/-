from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode,urljoin
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor
import json,hashlib,datetime,ssl,re
ROOT=Path(__file__).parent
LOG=[]
def fetch(url,name):
 p=ROOT/name;p.parent.mkdir(exist_ok=True,parents=True)
 receipt=Path(str(p)+'.receipt.json')
 if receipt.exists():return json.loads(receipt.read_text())
 rec={'requested_url':url,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tls_verification':True}
 try:
  with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=20,context=ssl.create_default_context()) as r:
   raw=r.read();p.write_bytes(raw);rec.update(status='ok',http_status=r.status,final_url=r.url,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),response_headers=dict(r.headers.items()),local_path=str(p))
 except HTTPError as e:rec.update(status='http_error',http_status=e.code,error=str(e))
 except Exception as e:rec.update(status='fetch_error',error=repr(e))
 receipt.write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n');return rec
def search(q,name):
 args=dict(websiteid='110000000000000',scope='basic',q=q,pg='40',p='1',cateid='47',pos='title_text,titlepy,infocontent,filenumbername,keyword,contentdescribe',selectFields='title,content,deploytime,_index,url,cdate,infoextends,infocontentattribute,keyword,contentdescribe,sectitle,picpath,columnname,themename,publishgroupname,publishtime,metaid,bexxgk,columnid,infocontenthashcode',group='distinct',level='6',sortFields='[{"name":"deploytime","type":"desc"}]')
 rec=fetch('https://www.miit.gov.cn/search-front-server/api/search/info?'+urlencode(args),'search/'+name+'.json');hits=[]
 def walk(v):
  if isinstance(v,dict):
   if 'title' in v and 'url' in v:hits.append(v)
   for x in v.values():walk(x)
  elif isinstance(v,list):
   for x in v:walk(x)
 if rec['status']=='ok':walk(json.loads(Path(rec['local_path']).read_text()))
 (ROOT/('search/'+name+'.hits.json')).write_text(json.dumps(hits,ensure_ascii=False,indent=2)+'\n')
 summary={'query':q,'rec':rec,'hits':[{k:x.get(k) for k in ['title','url','deploytime','cdate','publishtime']} for x in hits]}
 (ROOT/('search/'+name+'.summary.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'query':q,'status':rec['status'],'hits':summary['hits']},ensure_ascii=False),flush=True);return summary
if __name__=='__main__':
 tasks=[('JX6550T-M5BEV','exact_model'),('JX6550T','model_prefix'),('特顺EV','trade_name'),('免征车辆购置税 第四十八批','tax48'),('新能源汽车推广应用推荐车型目录 2021年第10批','recommend_2021_10')]
 with ThreadPoolExecutor(max_workers=3) as pool:
  results=list(pool.map(lambda x:search(*x),tasks))
 (ROOT/'initial_search_log.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(fetch('https://www.jmc.com.cn/','enterprise_home.html'),ensure_ascii=False),flush=True)
