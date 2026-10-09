#!/usr/bin/env python3
"""External index is discovery only; exact-model relevance is mandatory."""
from collect_public_configuration import ROOT,fetch,write_csv
from urllib.parse import urlencode,urlparse,parse_qs
from lxml import html
from concurrent.futures import ThreadPoolExecutor
import csv,json,base64,re

def dest(url):
 try:
  u=parse_qs(urlparse(url).query).get('u',[''])[0]
  if u.startswith('a1'):
   s=u[2:];return base64.urlsafe_b64decode(s+'='*((4-len(s)%4)%4)).decode()
 except Exception:pass
 return url

def search(model):
 args={'q':'"'+model+'"','mkt':'zh-CN','setlang':'zh-hans','count':10}
 rec=fetch('https://www.bing.com/search?'+urlencode(args),'external/model_'+model+'.html');hits=[];query_echo=''
 if rec['status']=='ok':
  doc=html.fromstring((ROOT/rec['relative_path']).read_bytes().decode('utf-8',errors='replace'))
  query_echo=' | '.join(doc.xpath('//input[@name="q"]/@value'))
  for li in doc.xpath('//li[contains(concat(" ",normalize-space(@class)," ")," b_algo ")]'):
   text=' '.join(li.itertext());urls=li.xpath('.//h2/a/@href');url=dest(urls[0]) if urls else ''
   clean=re.sub(r'[^A-Z0-9]','',text.upper());needle=re.sub(r'[^A-Z0-9]','',model.upper())
   relevant=needle in clean
   official=bool(re.search(r'(^|\.)gov\.cn$',urlparse(url).hostname or ''))
   hits.append({'model_key':model,'result_url':url,'result_text':text,'exact_model_in_result_text':int(relevant),'government_domain_candidate':int(official),'usable_as_scientific_evidence':0,'source_search_file':rec['relative_path'],'source_search_sha256':rec['sha256']})
 out={'model_key':model,'requested_q':args['q'],'query_echo':query_echo,'receipt':rec,'hits':hits,'exact_model_relevant_hits':sum(x['exact_model_in_result_text'] for x in hits),'same_model_is_configuration_identity':False,'negative_search_conclusion_permitted':False}
 (ROOT/('external/model_'+model+'.results.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'model':model,'status':rec['status'],'results':len(hits),'exact_hits':out['exact_model_relevant_hits']},ensure_ascii=False),flush=True);return out
if __name__=='__main__':
 targets=[]
 for n in ['32型号_区间跨阈值优先配置材料清单.csv','4型号_单项跨阈值补充清单.csv']:
  targets.extend(row['model_key'] for row in csv.DictReader((ROOT/'inputs'/n).open(encoding='utf-8-sig')))
 with ThreadPoolExecutor(max_workers=4) as p:out=list(p.map(search,targets))
 (ROOT/'36模型_外部索引结果与型号相关性核查.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 write_csv(ROOT/'外部索引_逐结果相关性与候选.csv',[row for x in out for row in x['hits']])
