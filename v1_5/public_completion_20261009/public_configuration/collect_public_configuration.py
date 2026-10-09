#!/usr/bin/env python3
"""Bounded public discovery for 36 interval models; never edits scientific data."""
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode, urljoin
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,datetime,ssl,csv,re
ROOT=Path(__file__).resolve().parent
DEFAULT_REQ=Path('/workspace/file_export_proposal/v1_5/requirements')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fetch(url,name):
 p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True);rp=Path(str(p)+'.receipt.json')
 if rp.exists():return json.loads(rp.read_text())
 rec={'requested_url':url,'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tls_verification':True}
 try:
  with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=18,context=ssl.create_default_context()) as r:
   raw=r.read();p.write_bytes(raw);rec.update(status='ok',http_status=r.status,final_url=r.url,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),response_headers=dict(r.headers.items()),relative_path=p.relative_to(ROOT).as_posix())
 except HTTPError as e:rec.update(status='http_error',http_status=e.code,error=str(e))
 except Exception as e:rec.update(status='fetch_error',error=repr(e))
 rp.write_text(json.dumps(rec,ensure_ascii=False,indent=2)+'\n');return rec

def search(q,name):
 args=dict(websiteid='110000000000000',scope='basic',q=q,pg='40',p='1',cateid='47',pos='title_text,titlepy,infocontent,filenumbername,keyword,contentdescribe',selectFields='title,content,deploytime,_index,url,cdate,infoextends,infocontentattribute,keyword,contentdescribe,sectitle,picpath,columnname,themename,publishgroupname,publishtime,metaid,bexxgk,columnid,infocontenthashcode',group='distinct',level='6',sortFields='[{"name":"deploytime","type":"desc"}]')
 rec=fetch('https://www.miit.gov.cn/search-front-server/api/search/info?'+urlencode(args),'search/'+name+'.json');hits=[];total=None
 if rec['status']=='ok':
  obj=json.loads((ROOT/rec['relative_path']).read_text());sr=obj.get('data',{}).get('searchResult',{});total=sr.get('total')
  def walk(v):
   if isinstance(v,dict):
    if 'title' in v and 'url' in v:hits.append(v)
    for x in v.values():walk(x)
   elif isinstance(v,list):
    for x in v:walk(x)
  walk(obj)
 out={'query':q,'search_query_page':1,'page_size':40,'reported_total':total,'receipt':rec,'hits':hits}
 (ROOT/('search/'+name+'.hits.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'query':q,'status':rec['status'],'total':total,'hits':len(hits)},ensure_ascii=False),flush=True);return out

def write_csv(path,rows):
 keys=list(dict.fromkeys(k for row in rows for k in row))
 with path.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

if __name__=='__main__':
 sources=[];targets=[]
 for group,name in [('joint32','32型号_区间跨阈值优先配置材料清单.csv'),('single4','4型号_单项跨阈值补充清单.csv')]:
  p=ROOT/'inputs'/name
  if not p.exists():p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((DEFAULT_REQ/name).read_bytes())
  sources.append({'input':name,'bytes':p.stat().st_size,'sha256':digest(p),'upstream':str(DEFAULT_REQ/name)})
  for row in csv.DictReader(p.open(encoding='utf-8-sig')):targets.append(dict(row,scope=group))
 p=ROOT/'inputs'/'285配置版本_跨目录身份材料待补清单.csv'
 if not p.exists():p.write_bytes((DEFAULT_REQ/p.name).read_bytes())
 sources.append({'input':p.name,'bytes':p.stat().st_size,'sha256':digest(p),'upstream':str(DEFAULT_REQ/p.name)})
 write_csv(ROOT/'核查输入_SHA256.csv',sources)
 with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda row:search(row['model_key'],'model_'+row['model_key']),targets))
 (ROOT/'36模型_工信部原生检索完整结果.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
 search('新能源汽车推广应用推荐车型目录 2022年第12批','positive_control_recommendation_2022_12')
