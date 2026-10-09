#!/usr/bin/env python3
from collect_public_configuration import ROOT,fetch,write_csv
from urllib.parse import urlencode,urlparse,parse_qs
from lxml import html
from concurrent.futures import ThreadPoolExecutor
import re,json
MODELS=['GTM6470BFEBEV','CC7000CG00FBEV','LF6461SEV01','LZ6510NPD0EV','SC7001FAMBEV','YGM7000BEVBD1','JNJ7000EVM1','TV6470BEVFFE']
def search(model):
 rec=fetch('https://html.duckduckgo.com/html/?'+urlencode({'q':'"'+model+'"'}),'external/ddg_'+model+'.html');hits=[]
 if rec['status']=='ok':
  doc=html.fromstring((ROOT/rec['relative_path']).read_bytes().decode('utf-8',errors='replace'))
  for a in doc.xpath('//a[contains(concat(" ",normalize-space(@class)," ")," result__a ")]'):
   u=a.get('href','');u=parse_qs(urlparse(u).query).get('uddg',[u])[0];t=a.text_content();clean=re.sub('[^A-Z0-9]','',t.upper());match=re.sub('[^A-Z0-9]','',model.upper()) in clean
   hits.append({'model_key':model,'result_url':u,'result_title':t,'exact_model_in_title':int(match),'government_candidate':int(bool(re.search(r'(^|\.)gov\.cn$',urlparse(u).hostname or ''))),'scientific_evidence_from_search':0,'search_file':rec['relative_path'],'search_sha256':rec['sha256']})
 out={'model_key':model,'receipt':rec,'hits':hits,'search_is_source_evidence':False};(ROOT/('external/ddg_'+model+'.results.json')).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'model':model,'status':rec['status'],'hits':hits},ensure_ascii=False),flush=True);return out
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=3) as p:out=list(p.map(search,MODELS))
 (ROOT/'8型号_相关外部索引候选.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');write_csv(ROOT/'8型号_相关外部索引候选.csv',[h for v in out for h in v['hits']])
