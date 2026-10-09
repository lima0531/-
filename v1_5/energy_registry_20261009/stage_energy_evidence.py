#!/usr/bin/env python3
"""Publish reviewable evidence beside the unchanged v1.5 scientific tables."""
import argparse,csv,hashlib,json,re,shutil,zipfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import unquote,urlsplit

p=argparse.ArgumentParser();p.add_argument('--audit-root',type=Path,default=Path('/workspace/purchase_tax_audit'));p.add_argument('--export-root',type=Path,default=Path('/workspace/file_export_proposal'));a=p.parse_args()
AUDIT=a.audit_root.resolve();EXPORT=a.export_root.resolve();SOURCE=AUDIT/'round10';V5=EXPORT/'v1_5';NAME='energy_registry_20261009';OUT=V5/NAME
GOLD=json.loads((AUDIT/'round6/pre_review_scientific_csv_sha256.json').read_text())
OLD_ZIPS={'purchase_tax_data_v1_5.zip':'3fd50d6aa95eca0d8483b5bcc409b4c246b024b1dd707ef8e67d95df84e70f20','purchase_tax_sources_v1_5.zip':'17b10d905721b38526a6fc0191680721bb10dc977e8efbad6a28e2385d0f06a2','review_20261009/review_supplement_20261009.zip':'d5dfad8e6f2cfd5ae50ef0a76c2e384b5c8e1306a45ca928c96f4fb6ca5bb521','progress_20261009/progress_and_evidence_20261009.zip':'01fe60c3d5418dd1d5c0534c13d0b813a7e15c988e68624f8baf8502eea6c6c1','public_completion_20261009/public_completion_and_handoff_20261009.zip':'814ecec75a01323257ca17ccfab905f41c4513a8c08a9a00709ab03bb16c3e11'}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def files(root):return sorted(x for x in root.rglob('*') if x.is_file() and '__pycache__' not in x.parts)
def row(path,root):return {'file':path.relative_to(root).as_posix(),'bytes':path.stat().st_size,'sha256':sha(path)}
def manifest(root,name='文件_SHA256.csv',exclude=()):
 rows=[row(x,root) for x in files(root) if x!=root/name and x.relative_to(root).as_posix() not in exclude]
 old=(root/name).read_bytes() if (root/name).exists() else b'\r\n'
 newline='\r\n' if b'\r\n' in old else '\n'
 header=next(csv.reader(old.decode('utf-8-sig').splitlines()),[])
 columns=header if set(header)=={'file','bytes','sha256'} else ['file','bytes','sha256']
 with (root/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=columns,lineterminator=newline);w.writeheader();w.writerows(rows)
 return len(rows)
def protect():
 assert len(GOLD)==52
 for rel,d in GOLD.items():assert sha(V5/rel)==d['sha256'] and (V5/rel).stat().st_size==d['bytes'],rel
 for rel,s in OLD_ZIPS.items():assert sha(V5/rel)==s,rel
def note(path,text):
 raw=path.read_text()
 if NAME not in raw:path.write_text(text+'\n\n'+raw)

protect()
assert (SOURCE/'README.md').is_file() and (SOURCE/'energy_evidence_summary.json').is_file()
for lib in ['new','old']:
 checkpoint=json.loads((SOURCE/'public_energy_registry'/f'{lib}_checkpoint.json').read_text())
 assert checkpoint.get('finished_utc'),'Do not stage while collector is active.'
shutil.copytree(SOURCE,OUT,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','staging_energy_evidence_verification.json'))
checks={}
for folder in sorted(x for x in OUT.iterdir() if x.is_dir()):
 assert (folder/'README.md').is_file(),folder.name
 count=0
 for inventory in folder.rglob('文件_SHA256.csv'):
  for d in csv.DictReader(inventory.open(encoding='utf-8-sig')):
   target=inventory.parent/d['file'];assert target.is_file() and sha(target)==d['sha256'] and target.stat().st_size==int(d['bytes']),str(target)
   count+=1
 checks[folder.name]=count
note(EXPORT/'README.md','> 最新[官方能耗记录、JX标签复核及批量任务](v1_5/'+NAME+'/README.md)已发布：已验证匿名查询与正确分页，用户交回原件已收录。科学版本仍为v1.5。')
v5note='> 最新[官方能耗库实取证据与严格边界]('+NAME+'/README.md)及[可直接交给DeepSeek的批量要求]('+NAME+'/bulk_handoff/README.md)已发布。JX不在2208数值齐备清单，issueDate不作为历史首次公开证明，主数据保持原字节。'
for file in ['README.md','audit_report.md','原件补齐与字段勘误修订报告_v1_5_20261009.md']:note(V5/file,v5note)
req=V5/'requirements'
note(req/'需要用户亲自提供的数据.md','> 最新[官方能耗来源实取、已取得与待取的页及模型匹配](../'+NAME+'/README.md)已更新；能耗查询可由正常公开接口自动采集，已取得的部分无需再手查。此前条件用途清单保留，未以命中数直接关闭冻结工况缺口。')
q=json.loads((req/'requirements_summary.json').read_text());q['official_energy_registry_20261009']={'report':'../'+NAME+'/README.md','collection_contract':'../'+NAME+'/bulk_handoff/README.md','scientific_inputs_changed':False,'jx_core_energy_missing':True,'jx_in_2208':False,'issueDate_not_first_public_availability':True};(req/'requirements_summary.json').write_text(json.dumps(q,ensure_ascii=False,indent=2)+'\n');manifest(req)
canonical=V5/'reconstruction/data_v1_5'
note(canonical/'README.md','> [官方能耗资料新旁证](../../'+NAME+'/README.md)先存独立证据层；本轮52份科学CSV未改。')
gold_manifest=canonical/'文件清单_SHA256.txt';members=[x for x in files(canonical) if x!=gold_manifest];assert len(members)==58;gold_manifest.write_text(''.join(sha(x)+'  '+x.relative_to(canonical).as_posix()+'\n' for x in members))
# Retain each prior observation as a dated snapshot, with a clear current follow-up.
prior=V5/'public_completion_20261009'
note(prior/'README.md','> 后续[官方能耗库实际重取与查询说明订正](../'+NAME+'/README.md)已有新证据；本页以下是此前公开补查快照，不代表后续接口能力或本轮新增采集数量。')
note(prior/'public_configuration/README.md','> 后续[能耗接口真实POST与标签证据](../../'+NAME+'/README.md)已取得；本目录下面的0份结果和滑块前端观察属于此前时点。不能将前端组件泛化为接口必需验证。')
note(prior/'public_configuration/人工官网查询_操作与交回格式.md','> 订正：[后续正常匿名POST查询及正确分页](../../'+NAME+'/api_pilot/README.md)已验证可取记录和标签。本页原步骤是此前人工UI流程，滑块不是已验证的接口前置条件；可按[自动核查任务](../../'+NAME+'/bulk_handoff/README.md)处理。只有明确出现访问限制时才停止。')
note(prior/'user_handoff/README.md','> 最新[官方能耗资料采集与剩余任务](../../'+NAME+'/README.md)已经启动；取得的页面及型号旁表无需重复人工查询。JX能量仍缺，原企业材料用途清单保留。')
manifest(prior/'public_configuration');manifest(prior/'user_handoff');manifest(prior,exclude=('public_completion_and_handoff_20261009.zip',))
zip_path=OUT/'energy_records_and_review_20261009.zip'
payload_count=manifest(OUT,exclude=(zip_path.name,))
payload=[x for x in files(OUT) if x!=zip_path];prefix='购置税v1_5_官方能耗资料与批量核查_20261009'
with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for path in payload:
  i=zipfile.ZipInfo(prefix+'/'+path.relative_to(OUT).as_posix(),(2026,10,9,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=0o100644<<16;z.writestr(i,path.read_bytes(),compresslevel=9)
with zipfile.ZipFile(zip_path) as z:
 assert z.testzip() is None and len(z.infolist())==len(payload)
 for path in payload:assert hashlib.sha256(z.read(prefix+'/'+path.relative_to(OUT).as_posix())).hexdigest()==sha(path)
assert zip_path.stat().st_size<32*1024*1024
docs=[EXPORT/'README.md',V5/'README.md',req/'需要用户亲自提供的数据.md',canonical/'README.md']+list(OUT.rglob('*.md'))+list(prior.rglob('*.md'))
links=0
for doc in docs:
 for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)',doc.read_text()):
  target=target.strip().strip('<>')
  if urlsplit(target).scheme or target.startswith('#'):continue
  assert (doc.parent/unquote(target.split('#')[0])).resolve().exists(),(str(doc),target)
  links+=1
protect()
gp=V5/'file_manifest.json';g=json.loads(gp.read_text());g.update(latest_official_energy_evidence_directory=NAME,scientific_csv_bytes_changed=False,original_data_and_source_zips_unchanged=True)
artifacts={x['file']:x for x in g['artifacts']}
for rel in [NAME+'/README.md',NAME+'/'+zip_path.name]:artifacts.setdefault(rel,{'file':rel})
for rel,d in artifacts.items():d.update(bytes=(V5/rel).stat().st_size,sha256=sha(V5/rel),github_file_page='https://github.com/lima0531/-/blob/purchase-tax-v1-4-files/v1_5/'+rel)
artifacts[NAME+'/'+zip_path.name].update(member_files=len(payload),all_members_crc_and_sha_verified=True,includes_scientific_data_replacement=False,original_file_name=prefix+'.zip')
g['artifacts']=list(artifacts.values());g['files_excluding_this_manifest']=[row(x,V5) for x in files(V5) if x!=gp];gp.write_text(json.dumps(g,ensure_ascii=False,indent=2)+'\n')
proof={'generated_utc':datetime.now(timezone.utc).isoformat(),'scientific_csv_count':52,'scientific_csv_unchanged':True,'five_historical_zips_unchanged':True,'canonical_sha_entries':58,'submanifest_entries_verified':checks,'payload_manifest_entries':payload_count,'zip_members_verified':len(payload),'zip_bytes':zip_path.stat().st_size,'zip_sha256':sha(zip_path),'relative_links_verified':links,'delivery_manifest_entries':len(g['files_excluding_this_manifest'])}
(SOURCE/'staging_energy_evidence_verification.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n');print(json.dumps(proof,ensure_ascii=False))
