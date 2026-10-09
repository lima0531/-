#!/usr/bin/env python3
"""Read-only whole-source scan of the 2,208-model test-cycle backlog.

No input dates, years, numeric values or model names imply a cycle. Copies and
derived text stay in this audit directory; scientific CSVs are never edited.
"""
import argparse, collections, csv, hashlib, importlib.util, json, re, subprocess, struct, shutil
from pathlib import Path
from xml.etree import ElementTree as ET
import zipfile
import fitz
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
BASE = Path('/workspace/purchase_tax_audit')
REQ = next((p/'requirements' for p in ROOT.parents if (p/'requirements'/'2208数值可用型号_公告前试验工况待核清单.csv').exists()),Path('/workspace/file_export_proposal/v1_5/requirements'))
NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
KEY = re.compile(r'CLTC|NEDC|WLTC|WLTP|CATC|UDDS|FTP|工况|等速|标准|试验|测试|循环|法规|缩短法|常规法|测量法|18386|27840|19233|\b(?:GB(?:\s*/\s*T)?|QC\s*/\s*T|ISO|SAE|UNECE|ECE)\s*[-—–]?\s*\d', re.I)

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def readcsv(p):
    with Path(p).open(encoding='utf-8-sig', newline='') as h: return list(csv.DictReader(h))
def dump(p, rows, fields=None):
    with Path(p).open('w',encoding='utf-8-sig',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)

def source_map():
    rows=readcsv(REQ/'2208型号_工况清单字段来源长表.csv')
    targets=readcsv(REQ/'2208数值可用型号_公告前试验工况待核清单.csv')
    assert len(targets)==2208 and len({r['model_key'] for r in targets})==2208
    assert len(rows)==11040 and {r['model_key'] for r in rows}=={r['model_key'] for r in targets}
    pools=list((BASE/'round3/archive/recovered').rglob('*'))+list((BASE/'round5/originals').rglob('*'))+[BASE/'round4/public_gaps/batch26_tax_catalogue.docx']
    hashes={sha(p):p for p in pools if p.is_file()}
    specs={r['source_file']:r['source_sha256'] for r in rows}
    assert len(specs)==71
    source=[]
    for logical,fingerprint in sorted(specs.items()):
        p=hashes[fingerprint]
        relevant=[r for r in rows if r['source_file']==logical]
        source.append({'source_file':logical,'source_sha256':fingerprint,'physical_path':str(p),'bytes':p.stat().st_size,'backlog_models':len({r['model_key'] for r in relevant}),'range_source_models':len({r['model_key'] for r in relevant if r['field']=='range'}),'source_date_upper_bounds':'|'.join(sorted({r['source_public_date_upper'] for r in relevant}))})
    return targets,rows,source

def xml_units(p, method):
    units=[]
    with zipfile.ZipFile(p) as z:
        # Include the main story and all header/footer/footnote/endnote text parts.
        # Comments are separately identified and never used as technical evidence.
        for name in sorted(z.namelist()):
            if not re.match(r'word/(document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml$',name):continue
            root=ET.fromstring(z.read(name))
            row_locations={}
            for ti,tbl in enumerate(root.findall('.//w:tbl',NS)):
                for ri,tr in enumerate(tbl.findall('w:tr',NS)):
                    scope=' | '.join(''.join(t.text or '' for t in tc.findall('.//w:t',NS)) for tc in tr.findall('w:tc',NS))
                    for para in tr.findall('.//w:p',NS):row_locations[para]=(f'table_{ti}:row_{ri}',scope)
            for i,para in enumerate(root.findall('.//w:p',NS),1):
                txt=''.join(t.text or '' for t in para.findall('.//w:t',NS))
                rowloc,scope=row_locations.get(para,('body_or_additional_story',txt))
                if txt.strip():units.append({'method':method,'location':f'{name}:{rowloc}:paragraph_{i}','text':txt,'row_scope_text':scope})
    return units

def cfb_auxiliary_units(reader, p):
    """Extract non-main text stories with the same bounded native CLX pieces.

    FIB story counts include actual footnotes/endnotes and header textboxes,
    so a derived DOCX alone does not determine whether a story was present.
    """
    cfb=reader.CFB(p.read_bytes());word=cfb.stream('WordDocument')
    flags=reader.u16(word,10);table=cfb.stream('1Table' if flags&(1<<9) else '0Table')
    pos=32;csw=reader.u16(word,pos);pos+=2+csw*2;cslw=reader.u16(word,pos);pos+=2
    assert cslw>=11
    labels=['main','footnotes','headers','macros','comments','endnotes','textboxes','header_textboxes']
    counts={k:reader.u32(word,pos+(i+3)*4) for i,k in enumerate(labels)}
    pos+=cslw*4;pair_count=reader.u16(word,pos);pos+=2;assert pair_count>33
    fc=reader.u32(word,pos+33*8);length=reader.u32(word,pos+33*8+4)
    assert fc+length<=len(table)
    clx=table[fc:fc+length];q=0
    while q<len(clx) and clx[q]==1:q+=3+reader.u16(clx,q+1)
    assert q+5<=len(clx) and clx[q]==2
    length=reader.u32(clx,q+1);plc=clx[q+5:q+5+length]
    assert len(plc)==length and (length-4)%12==0
    n=(length-4)//12;cps=list(struct.unpack_from('<'+str(n+1)+'I',plc,0))
    assert cps[0]==0 and all(a<=b for a,b in zip(cps,cps[1:])) and cps[-1]>=sum(counts.values())
    units=[];start=0
    for label,total in counts.items():
        end=start+total
        if label!='main' and total:
            parts=[];read_units=0
            for i in range(n):
                a=max(start,cps[i]);b=min(end,cps[i+1])
                if a>=b:continue
                rawfc=reader.u32(plc,4*(n+1)+8*i+2);compressed=bool(rawfc&(1<<30));offset=rawfc&0x3fffffff
                if compressed:offset//=2
                width=1 if compressed else 2;offset+=(a-cps[i])*width;byte_count=(b-a)*width
                assert offset+byte_count<=len(word)
                parts.append(word[offset:offset+byte_count].decode('cp1252' if compressed else 'utf-16le',errors='strict'));read_units+=b-a
            assert read_units==total
            text=''.join(parts).replace('\r','\n').replace('\x07','\t').replace('\x0b','\n').replace('\x0c','\n')
            for i,line in enumerate(text.splitlines(),1):
                if line.strip():units.append({'method':'bounded CFB auxiliary story','location':f'{label}:paragraph_{i}','text':line})
        start=end
    return units,counts

def main():
    global BASE,REQ
    parser=argparse.ArgumentParser();parser.add_argument('--convert-ole',action='store_true');parser.add_argument('--root',type=Path,default=BASE,help='extracted original-source package project root');parser.add_argument('--requirements',type=Path,default=REQ);args=parser.parse_args()
    BASE=args.root.resolve();REQ=args.requirements.resolve()
    ROOT.mkdir(parents=True,exist_ok=True)
    for d in ['texts','conversion_inputs','converted','proof']: (ROOT/d).mkdir(exist_ok=True)
    targets,rows,sources=source_map();dump(ROOT/'71份工况来源原件_同字节定位.csv',sources)
    spec=importlib.util.spec_from_file_location('bounded_doc',ROOT/'word_piece_text.py')
    reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    proofs=[];hits=[]
    for src in sources:
        p=Path(src['physical_path']);data=p.read_bytes();stem=Path(src['source_file']).stem
        units=[];proof={'source_file':src['source_file'],'source_sha256':src['source_sha256']}
        if data.startswith(b'%PDF-'):
            doc=fitz.open(p);proof['pages']=len(doc);proof['blank_text_pages']=[]
            proof['pages_with_images']=[]
            for i,page in enumerate(doc,1):
                txt=page.get_text('text',sort=True)
                if not txt.strip():proof['blank_text_pages'].append(i)
                if page.get_images(full=True):proof['pages_with_images'].append(i)
                units.append({'method':'PyMuPDF full page text','location':f'page_{i}','text':txt})
            doc.close()
            alt=PdfReader(str(p));proof['second_reader_pages']=len(alt.pages)
            for i,page in enumerate(alt.pages,1):units.append({'method':'pypdf full page text','location':f'page_{i}','text':page.extract_text() or ''})
            proof['coverage']='all PDF pages using two independent text readers'
        elif data[:4]==b'PK\x03\x04':
            units=xml_units(p,'native DOCX all text stories')
            proof['coverage']='all XML paragraphs in main story, headers, footers, footnotes, endnotes and comments (comments excluded from evidence)'
        elif data[:8]==bytes.fromhex('d0cf11e0a1b11ae1'):
            txt,cfbproof=reader.extract(p);proof['cfb']=cfbproof
            units=[{'method':'bounded CFB main story','location':f'paragraph_{i}','text':t} for i,t in enumerate(txt.splitlines(),1) if t.strip()]
            aux,counts=cfb_auxiliary_units(reader,p);units.extend(aux);proof['native_story_counts_utf16']=counts
            inp=ROOT/'conversion_inputs'/f'{stem}.doc';inp.write_bytes(data)
            assert sha(inp)==src['source_sha256']
            proof['conversion_input_relative_path']=str(inp.relative_to(ROOT));proof['conversion_input_sha256']=sha(inp)
            converted=ROOT/'converted'/f'{stem}.docx'
            if args.convert_ole and not converted.exists():
                profile_path=ROOT/'proof'/f'profile_{stem}';profile=profile_path.as_uri()
                result=subprocess.run(['soffice','-env:UserInstallation='+profile,'--headless','--convert-to','docx','--outdir',str(ROOT/'converted'),str(inp)],capture_output=True,text=True,timeout=50)
                proof['conversion']={'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
                assert converted.exists(),result.stdout+result.stderr
                shutil.rmtree(profile_path,ignore_errors=True)
            if converted.exists():
                units.extend(xml_units(converted,'LibreOffice DOCX all text stories'))
                proof['converted_sha256']=sha(converted)
                proof['coverage']='bounded native main and all auxiliary CLX stories plus fresh LibreOffice all XML text stories'
            else:proof['coverage']='bounded main-story CLX extraction only; additional stories not yet covered'
        else:raise ValueError(p)
        out=ROOT/'texts'/f'{stem}.json'
        out.write_text(json.dumps(units,ensure_ascii=False,indent=2))
        proof.update(extracted_units=len(units),units_file=str(out.relative_to(ROOT)),units_sha256=sha(out))
        for unit in units:
            for m in KEY.finditer(unit['text']):
                hits.append({'source_file':src['source_file'],'source_sha256':src['source_sha256'],'method':unit['method'],'location':unit['location'],'matched_token':m.group(),'context':unit['text'][max(0,m.start()-100):min(len(unit['text']),m.end()+160)],'row_scope_text':unit.get('row_scope_text','')})
        proof['candidate_hits']=sum(h['source_file']==src['source_file'] for h in hits)
        proofs.append(proof);print(stem,len(units),proof['candidate_hits'],flush=True)
    (ROOT/'full_source_extraction_proof.json').write_text(json.dumps(proofs,ensure_ascii=False,indent=2))
    dump(ROOT/'整篇正文_工况与标准检索命中.csv',hits,['source_file','source_sha256','method','location','matched_token','context','row_scope_text'])
    dump(ROOT/'只读输入_SHA256.csv',[{'input':str(REQ/n),'bytes':(REQ/n).stat().st_size,'sha256':sha(REQ/n)} for n in ['2208数值可用型号_公告前试验工况待核清单.csv','2208型号_工况清单字段来源长表.csv']])
    assert all(sha(src['physical_path'])==src['source_sha256'] for src in sources)
    print(json.dumps({'models':len(targets),'source_files':len(sources),'hits':len(hits),'sources_with_hits':len({h['source_file'] for h in hits})},ensure_ascii=False))
if __name__=='__main__':main()
