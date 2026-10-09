#!/usr/bin/env python3
"""Verify saved public responses and rebuild draft-only evidence, without network."""
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parent
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

receipts = []
for path in sorted(ROOT.glob('*.receipt.json')):
    row = json.loads(path.read_text())
    target = ROOT / row['file']
    assert target.is_file() and target.stat().st_size == row['bytes']
    assert sha(target) == row['sha256'] and row['tls_verified']
    receipts.append(row)
assert len(receipts) == 8
page = (ROOT / 'catarc_public_draft.html').read_text()
assert '发布日期：2024-05-13' in page and '截止日期：2024-07-12' in page
assert '全国汽车标准化技术委员会汽车节能分技术委员会' in page
pdfs = []
for filename, count in [('amendment_draft.pdf',5),('draft_explanation.pdf',16)]:
    with fitz.open(ROOT / filename) as doc:
        assert len(doc) == count and '征求意见稿' in doc[0].get_text()
        text = '\n'.join(x.get_text() for x in doc)
        assert '18386.1' in text
        (ROOT / (Path(filename).stem+'_text.txt')).write_text(text)
    pdfs.append({'file':filename,'physical_pages':count,'bytes':(ROOT/filename).stat().st_size,'sha256':sha(ROOT/filename),'formal_final_amendment':False})
approval = (ROOT / 'catarc_2025_19_approval.html').read_text()
assert '2025年第19号' in approval and '2025-08-01' in approval
assert '416项推荐性国家标准和3项推荐性国家标准修改单' in approval
assert not re.search(r'18386\s*[.．]\s*1',approval)
summary = {
    'generated_at_utc':datetime.now(timezone.utc).isoformat(),
    'actual_network_responses_verified':len(receipts),
    'public_draft_notice_date':'2024-05-13',
    'public_draft_consultation_deadline':'2024-07-12',
    'draft_explanation_cover_month':'2024-04',
    'issuing_committee':'全国汽车标准化技术委员会汽车节能分技术委员会（TC114SC32）',
    'new_original_public_pdf_documents':pdfs,
    'general_2025_19_notice_on_committee_site':{'date':'2025-08-01','target_standard_number_present':False,'target_amendment_membership_verified':False},
    'target_final_publication_date':None,
    'target_final_implementation_date':None,
    'target_final_approval_notice_number':None,
    'target_final_document_obtained':False,
    'model_specific_low_temperature_report_obtained':False,
    'vehicle_missing_data_gaps_closed':0,
    'scientific_data_changed':False,
    'historical_public_before_2023_12_10_verified':False,
    'scope':'2024公开征求意见原件和基础标准旁证；2025公告本页只有汽车新标准子表，未出现目标编号，不能认证该修改单正式日期。',
}
(ROOT/'standard_extra_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
(ROOT/'actual_requests_verified.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n')
rows = [
    ['征求意见公示发布日期','2024-05-13','catarc_public_draft.html','已证','非正式批准发布日期'],
    ['征求意见截止日期','2024-07-12','catarc_public_draft.html','已证','非正式实施日期'],
    ['草案编制说明封面月份','2024-04','draft_explanation.pdf','已证','正文内部2023历程不证明此版2023公开'],
    ['修改单正式发布日期','','','未证','2025年第19号公告该页不含目标编号'],
    ['修改单正式实施日期','','','未证','不能取草案日期或基础标准日期'],
    ['修改单正式公告号','','','未证','2025年第19号仅一般公告身份确认，尚无该目标成员对应'],
    ['匹配车型低温检测报告','','','未取得','标准草案不是车型报告'],
]
with (ROOT/'标准草案与正式字段_严格区分.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['field','value','source_file','status','limit']);w.writerows(rows)
paths=sorted(x for x in ROOT.rglob('*') if x.is_file() and x.name!='文件_SHA256.csv' and '__pycache__' not in x.parts)
with (ROOT/'文件_SHA256.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['file','bytes','sha256']);w.writeheader()
    w.writerows({'file':x.relative_to(ROOT).as_posix(),'bytes':x.stat().st_size,'sha256':sha(x)} for x in paths)
print(json.dumps({'responses':len(receipts),'draft_pdf_documents':2,'manifest_entries':len(paths),'vehicle_gap_closures':0},ensure_ascii=False))
