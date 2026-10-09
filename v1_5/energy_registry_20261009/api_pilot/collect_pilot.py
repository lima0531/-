#!/usr/bin/env python3
"""Cache a bounded anonymous public-query pilot; never submit CAPTCHA solutions."""
import hashlib
import json
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import URLError,HTTPError

ROOT=Path(__file__).resolve().parent
BASE='https://yhgscx.miit.gov.cn/fuel-consumption-center/fuel-consumption-center/'
TASKS=[
 ('JX_new_page1','fcSearchCtr/queryNewList',{'pageNum':1,'pageSize':50,'vehicleModel':'JX6550T-M5BEV'},'json'),
 ('JX_old_page1','fcSearchCtr/queryList',{'pageNum':1,'pageSize':50,'vehicleNumber':'JX6550T-M5BEV'},'json'),
 ('JX_2360_full_label','file/file/file/download?m=377db9bc3a76717693fff445fff4b9ae%4080946&p=1',None,'pdf'),
 ('JX_2295_full_label','file/file/file/download?m=8ba4fe7af7c3364b4e85f48231945413%4080956&p=1',None,'pdf'),
 ('GTM_new_page1','fcSearchCtr/queryNewList',{'pageNum':1,'pageSize':50,'vehicleModel':'GTM6470BFEBEV'},'json'),
 ('CC_new_page1','fcSearchCtr/queryNewList',{'pageNum':1,'pageSize':50,'vehicleModel':'CC7000CG00FBEV'},'json'),
 ('GTM_old_page1','fcSearchCtr/queryList',{'pageNum':1,'pageSize':50,'vehicleNumber':'GTM6470BFEBEV'},'json'),
 ('CC_old_page1','fcSearchCtr/queryList',{'pageNum':1,'pageSize':50,'vehicleNumber':'CC7000CG00FBEV'},'json'),
 ('JX_old_detail_2360_candidate','fcSearchCtr/queryDetail',{'applyId':'594e5ea08ab144b98a2c07c2f9a311a6'},'json'),
 ('JX_old_detail_2295_candidate','fcSearchCtr/queryDetail',{'applyId':'b527ea874fd442538c4d0d82adf5f167'},'json'),
]

def collect(name,path,body,extension):
 rp=ROOT/(name+'_receipt.json')
 if rp.exists():
  row=json.loads(rp.read_text());saved=ROOT/row.get('file','missing')
  if saved.is_file() and hashlib.sha256(saved.read_bytes()).hexdigest()==row.get('sha256'):
   if extension=='json':
    try:
     info=json.loads(saved.read_bytes()).get('info')
     if isinstance(info,dict):row.update(totalSize=info.get('totalSize'),pages=info.get('pages'),rows=len(info.get('list') or []))
    except (ValueError,AttributeError):pass
    rp.write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
   return row
 row={'requested_url':BASE+path,'method':'POST' if body is not None else 'GET','observed_utc':datetime.now(timezone.utc).isoformat(),'tls_verified':True,'no_credentials_or_validation_solution_submitted':True}
 if body is not None:row['json_body']=body
 req=Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'} if body is not None else {},method=row['method'])
 try:
  try:r=urlopen(req,timeout=35)
  except HTTPError as e:r=e
  raw=r.read();saved=ROOT/(name+'_response.'+extension);saved.write_bytes(raw)
  row.update(status_code=r.status,final_url=r.geturl(),content_type=r.headers.get('Content-Type'),file=saved.name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
  if extension=='json':
   try:
    d=json.loads(raw);info=d.get('info');row['business_result']=d.get('result')
    if isinstance(info,dict):
     row.update(totalSize=info.get('totalSize'),pages=info.get('pages'),rows=len(info.get('list') or []))
     row['received_models']=sorted({str(x.get('vehicleModel') or x.get('vehicleNumber')) for x in info.get('list') or [] if isinstance(x,dict)})
   except (ValueError,AttributeError):row['json_parse_failed']=True
 except (URLError,TimeoutError,OSError) as e:row.update(error=type(e).__name__,error_detail=str(e))
 rp.write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
 return row

if __name__=='__main__':
 rows=[]
 for name,path,body,extension in TASKS:
  row=collect(name,path,body,extension);rows.append(row)
  print(json.dumps({'name':name,**{k:row.get(k) for k in ['status_code','business_result','totalSize','pages','rows','bytes','error']}},ensure_ascii=False),flush=True)
  if row.get('status_code') in [401,403,429] or row.get('error'):
   print('Stopped at access/rate/network boundary.',flush=True);break
  time.sleep(1)
 (ROOT/'pilot_requests.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
