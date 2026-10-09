#!/usr/bin/env python3
"""Offline supplementary review of two PDF responses and main-process HTTP receipts."""
from pathlib import Path
import argparse,csv,hashlib,json,re
from datetime import datetime,timezone
import fitz,pypdf

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main(pilot,uploaded_pdf,uploaded_json,out):
    out.mkdir(parents=True,exist_ok=True)
    candidates=[('JX_2360',2360,'GD20240715105558048'),('JX_2295',2295,'GD20240715105576581')]
    source_paths=[uploaded_pdf,uploaded_json,pilot/'JX_new_page1_response.json',pilot/'JX_new_page1_receipt.json']
    for prefix,_,_ in candidates:source_paths += [pilot/(prefix+'_full_label_response.pdf'),pilot/(prefix+'_full_label_receipt.json')]
    before={str(p):sha(p) for p in source_paths}
    reviews=[]
    for prefix,mass,number in candidates:
        pdf=pilot/(prefix+'_full_label_response.pdf')
        receipt_path=pilot/(prefix+'_full_label_receipt.json')
        receipt=json.loads(receipt_path.read_text());doc=fitz.open(pdf);reader=pypdf.PdfReader(pdf)
        texts={'PyMuPDF':'\n\n'.join(p.get_text() for p in doc),'pypdf':'\n\n'.join(p.extract_text() or '' for p in reader.pages)}
        required=['JX6550T-M5BEV',str(mass),number,'293','19.2','120','3490','GB/T18386.1—2021',
                  '高温开空调行业续驶里程平均约下降：15%','低温开暖风行业续驶里程平均约下降：40%']
        checks={engine:{t:t in re.sub(r'\s+','',text) for t in required} for engine,text in texts.items()}
        for engine,text in texts.items():(out/(prefix+'_PDF文本_'+engine+'.txt')).write_text(text,encoding='utf-8')
        doc[0].get_pixmap(matrix=fitz.Matrix(2,2)).save(out/(prefix+'_标签_第1页.png'))
        pdf_sha=sha(pdf)
        assert receipt['status_code']==200 and receipt['tls_verified'] is True
        assert receipt['sha256']==pdf_sha and receipt['bytes']==pdf.stat().st_size
        assert all(all(c.values()) for c in checks.values())
        reviews.append({'pdf_file':pdf.name,'receipt_file':receipt_path.name,'bytes':pdf.stat().st_size,'sha256':pdf_sha,
            'observed_utc_main_process':receipt['observed_utc'],'main_process_receipt_verified_to_pdf':True,
            'pages_pymupdf':len(doc),'pages_pypdf':len(reader.pages),'metadata':doc.metadata,
            'record_number':number,'mass_kg':mass,'range_km':293,'electricity_consumption_kwh_per_100km':19.2,
            'explicit_standard_in_own_pdf':'GB/T 18386.1—2021','explicit_cycle_in_own_pdf':None,
            'visible_enable_date':'2024-07-15','visible_issue_date':None,'battery_energy_kwh':None,
            'temperature_text_kind':'行业续驶里程平均约下降','config_specific_low_temperature_report':False,
            'dual_engine_checks':checks,'same_bytes_as_uploaded_pdf':pdf.read_bytes()==uploaded_pdf.read_bytes()})
    query_receipt=json.loads((pilot/'JX_new_page1_receipt.json').read_text())
    live_json=pilot/'JX_new_page1_response.json'
    assert query_receipt['status_code']==200 and query_receipt['tls_verified'] is True
    assert query_receipt['sha256']==sha(live_json) and query_receipt['bytes']==live_json.stat().st_size
    same_json=live_json.read_bytes()==uploaded_json.read_bytes()
    after={str(p):sha(p) for p in source_paths};assert before==after
    result={'review_utc':datetime.now(timezone.utc).isoformat(),'method':'Offline read-only supplementary review. Main-process network receipts independently matched against response file size/SHA; both PDFs inspected with PyMuPDF/pypdf.',
            'labels':reviews,'uploaded_pdf_matches_live_2360_exact_bytes':reviews[0]['same_bytes_as_uploaded_pdf'],
            'uploaded_json_matches_live_new_list_exact_bytes':same_json,
            'live_new_json_sha256':sha(live_json),'live_new_json_bytes':live_json.stat().st_size,
            'live_query_observed_utc_main_process':query_receipt['observed_utc'],
            'migration_and_issue_date_boundary_unchanged':True,'source_files_unchanged':before==after,
            'source_sha256s':before,'scientific_inputs_modified':False,
            'conclusion':'Both own PDFs now explicitly verify GB/T18386.1—2021 for their respective labels. This does not certify a pre-freeze public date, tax-catalogue configuration identity, battery energy, configuration-specific low-temperature performance, or reduce the 2208 ready-model list.'}
    (out/'live_label_pair_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    manifest=out/'文件_SHA256.csv'
    with manifest.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['file','bytes','sha256'])
        for p in sorted(out.rglob('*')):
            if p.is_file() and p!=manifest:w.writerow([p.relative_to(out).as_posix(),p.stat().st_size,sha(p)])
    print(json.dumps({'pair_dual_engine_all_pass':True,'uploaded_pdf_equal':result['uploaded_pdf_matches_live_2360_exact_bytes'],
                      'uploaded_json_equal':same_json,'inputs_unchanged':before==after,'supplement_sha256':sha(out/'live_label_pair_review.json')},ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pilot',type=Path,required=True);p.add_argument('--uploaded-pdf',type=Path,required=True);p.add_argument('--uploaded-json',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();main(a.pilot,a.uploaded_pdf,a.uploaded_json,a.out)
