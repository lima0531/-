#!/usr/bin/env python3
"""Enumerate normally public BEV lists, cache raw pages, stop at access boundaries."""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

ROOT=Path(__file__).resolve().parent
BASE='https://yhgscx.miit.gov.cn/fuel-consumption-center/fuel-consumption-center/fcSearchCtr/'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fetch(lib,page,size,filters):
 folder=ROOT/(lib+'_currentPage');folder.mkdir(parents=True,exist_ok=True)
 body={'currentPage':page,'pageSize':size,**filters}
 prior=[]
 for rp in sorted(folder.glob(f'page{page:04d}*_receipt.json')):
  row=json.loads(rp.read_text());path=ROOT/row.get('file','missing')
  if row.get('request_json')!=body:continue
  prior.append(row)
  if row.get('http_status')==200 and path.is_file() and sha(path)==row.get('sha256'):
   return row,json.loads(path.read_bytes())
 prior.sort(key=lambda x:int(x.get('attempt',1)))
 if prior:
  last=prior[-1]
  if any(x.get('http_status') in [401,403,429] for x in prior):return last,None
  if last.get('http_status') not in [500,502,503,504] and not last.get('error'):
   return last,None
  if len(prior)>=3:return last,None
  time.sleep(5*len(prior))
 attempt=len(prior)+1
 stem=f'page{page:04d}'+(f'_attempt{attempt:02d}' if prior else '')
 path=folder/(stem+'_response.json');rp=folder/(stem+'_receipt.json')
 url=BASE+('queryNewList' if lib=='new' else 'queryList')
 row={'library':lib,'page':page,'attempt':attempt,'requested_url':url,'request_json':body,'method':'POST','observed_utc':datetime.now(timezone.utc).isoformat(),'tls_verified':True,'no_credentials_or_captcha_solution_submitted':True}
 req=Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
 d=None
 try:
  try:r=urlopen(req,timeout=45)
  except HTTPError as e:r=e
  raw=r.read();path.write_bytes(raw)
  row.update(http_status=r.status,final_url=r.geturl(),content_type=r.headers.get('Content-Type'),file=path.relative_to(ROOT).as_posix(),bytes=len(raw),sha256=sha(path),finished_utc=datetime.now(timezone.utc).isoformat())
  try:d=json.loads(raw)
  except ValueError:row['parse_error']='invalid_json'
 except (URLError,TimeoutError,OSError) as e:row.update(error=type(e).__name__,error_detail=str(e))
 rp.write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
 if (row.get('http_status') in [500,502,503,504] or row.get('error')) and attempt<3:
  return fetch(lib,page,size,filters)
 return row,d

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--library',choices=['new','old'],required=True);ap.add_argument('--old-fuel-code');ap.add_argument('--interval',type=float,default=2);ap.add_argument('--page-size',type=int,default=200);ap.add_argument('--max-pages',type=int,default=160);a=ap.parse_args()
 assert a.interval>=1 and 1<=a.page_size<=200
 assert a.library!='old' or a.old_fuel_code is not None,'Old fuel code must come from actual official dictionary.'
 filters={'energyType':'8'} if a.library=='new' else {'fuelType':a.old_fuel_code}
 expected_result=200 if a.library=='new' else 1
 state={'started_utc':datetime.now(timezone.utc).isoformat(),'library':a.library,'filters':filters,'completed':False,'pages_validated':0,'rows':0,'unique_ids':0,'stop_reason':'','transactionally_atomic_snapshot':False,'history_scope':'Only rows returned by this normally public energyType8/fuelType8 filtered view at observed request times; no hidden/history completeness or certified-BEV claim.','source_page_files':[],'response_category_conflict_occurrences':0}
 seen=set();full_rows=set();page=1;expected_total=None;pages=None;all_batches=set()
 try:
  while True:
   receipt,data=fetch(a.library,page,a.page_size,filters)
   if receipt.get('http_status')!=200 or not isinstance(data,dict) or data.get('result')!=expected_result:
    raise RuntimeError(f'Access/network/business boundary on page {page}; no bypass/retry.')
   info=data.get('info')
   assert isinstance(info,dict) and isinstance(info.get('list'),list),'invalid_schema'
   total=int(info['totalSize']);this_pages=int(info['pages']);items=info['list']
   if expected_total is None:expected_total=total;pages=this_pages;state.update(reported_total=total,reported_pages=pages)
   assert total==expected_total and this_pages==pages,'total_or_pages_drift'
   assert info['currentPage']==page and info['pageSize']==a.page_size,'page_parameter_mismatch'
   assert pages<=a.max_pages,'actual_pages_exceed_run_budget'
   expected_size=a.page_size if page<pages else total-a.page_size*(pages-1)
   assert len(items)==expected_size,'unexpected_page_length'
   batch=hashlib.sha256(json.dumps(items,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
   assert batch not in all_batches,'entire_page_content_repeated'
   for item in items:
    if item.get('reportType')!='3' or (a.library=='new' and item.get('energyType')!='8'):
     state['response_category_conflict_occurrences']+=1
    recordid=item.get('uuid') if a.library=='new' else item.get('applyId')
    assert recordid,'missing_stable_id'
    seen.add(recordid)
    full_rows.add(hashlib.sha256(json.dumps(item,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
   all_batches.add(batch)
   state['source_page_files'].append(receipt['file'])
   state.update(pages_validated=page,rows=state['rows']+len(items),unique_ids=len(seen),unique_full_rows=len(full_rows),repeated_id_occurrences=state['rows']+len(items)-len(seen),updated_utc=datetime.now(timezone.utc).isoformat())
   (ROOT/(a.library+'_checkpoint.json')).write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
   print(json.dumps({'library':a.library,'page':page,'pages':pages,'rows':state['rows'],'total':total},ensure_ascii=False),flush=True)
   if page>=pages:
    assert state['rows']==total;state['completed']=True;break
   page+=1;time.sleep(a.interval)
 except Exception as e:
  state['stop_reason']=str(e);print(json.dumps({'library':a.library,'stopped':str(e)},ensure_ascii=False),flush=True)
 state['finished_utc']=datetime.now(timezone.utc).isoformat()
 (ROOT/(a.library+'_checkpoint.json')).write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
 sys.exit(0 if state['completed'] else 1)
if __name__=='__main__':main()
