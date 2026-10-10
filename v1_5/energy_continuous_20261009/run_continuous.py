#!/usr/bin/env python3
"""Resume saved public evidence queues, validate each batch and publish progress."""
import argparse, csv, fcntl, hashlib, json, os, re, subprocess, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
V5, REPO = ROOT.parent, ROOT.parent.parent
BASE = V5 / 'energy_new_complete_20261009'
NAME = ROOT.name
BRANCH = 'purchase-tax-v1-4-files'
IN_ACTIONS = os.environ.get('GITHUB_ACTIONS') == 'true'
RUN_ID = os.environ.get('GITHUB_RUN_ID', '') if IN_ACTIONS else ''
RUN_URL = 'https://github.com/lima0531/-/actions/runs/' + RUN_ID if RUN_ID.isdigit() else None
ZIPS = {
    'purchase_tax_data_v1_5.zip': '3fd50d6aa95eca0d8483b5bcc409b4c246b024b1dd707ef8e67d95df84e70f20',
    'purchase_tax_sources_v1_5.zip': '17b10d905721b38526a6fc0191680721bb10dc977e8efbad6a28e2385d0f06a2',
    'review_20261009/review_supplement_20261009.zip': 'd5dfad8e6f2cfd5ae50ef0a76c2e384b5c8e1306a45ca928c96f4fb6ca5bb521',
    'progress_20261009/progress_and_evidence_20261009.zip': '01fe60c3d5418dd1d5c0534c13d0b813a7e15c988e68624f8baf8502eea6c6c1',
    'public_completion_20261009/public_completion_and_handoff_20261009.zip': '814ecec75a01323257ca17ccfab905f41c4513a8c08a9a00709ab03bb16c3e11',
    'energy_registry_20261009/energy_records_and_review_20261009.zip': '3bf75d9b8c33f51de3cb7b2690db2142d31b68e727fae224a43d7b2ffa2b9184',
    'energy_new_complete_20261009/energy_new_snapshot_and_first_labels_20261009.zip': 'bf4fc3cc799e5ce5222c37064dfe18cbf21be71a89354d42f4c6fbe70447f4e1',
}

def now(): return datetime.now(timezone.utc).isoformat()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_bytes())
def jwrite(p, value):
    temp = p.with_suffix(p.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n'); temp.replace(p)
def files(root):
    return sorted(p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and not p.name.endswith('.tmp'))
def row(p, root): return dict(file=p.relative_to(root).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
def manifest(root):
    dest = root / '文件_SHA256.csv'
    previous = dest.read_bytes() if dest.exists() else b'\r\n'
    fields = next(csv.reader(previous.decode('utf-8-sig').splitlines()), [])
    if set(fields) != {'file', 'bytes', 'sha256'}: fields = ['file', 'bytes', 'sha256']
    with dest.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\r\n' if b'\r\n' in previous else '\n')
        writer.writeheader(); writer.writerows(row(p, root) for p in files(root) if p != dest)
def run(command):
    result = subprocess.run(command, cwd=REPO, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode().strip()
def protect():
    gold = ROOT / 'inputs/scientific_golden.json'
    assert sha(gold) == '5738854737fc12902a608d89300acf049f620075ead07866973fb6f36ce69f33'
    expected = load(gold); assert len(expected) == 52
    for name, info in expected.items():
        p = V5 / name; assert sha(p) == info['sha256'] and p.stat().st_size == info['bytes'], name
    for name, digest in ZIPS.items(): assert sha(V5 / name) == digest, name

def validate_labels():
    import fitz
    from pypdf import PdfReader
    folder = ROOT / 'label_archive'
    jobs = [json.loads(line) for line in (folder / 'label_download_queue.jsonl').read_text().splitlines() if line]
    by_id = {job['label_job_id']: job for job in jobs}
    seen, standards = set(), Counter()
    standard_re = re.compile(r'GB\s*/\s*T\s*18386(?:\s*\.\s*1)?\s*[-—–]\s*(?:2017|2021)')
    for receipt_file in sorted((folder / 'receipts').glob('*_receipt.json')):
        receipt = load(receipt_file)
        if not receipt.get('accepted'): continue
        job = by_id[receipt['label_job_id']]
        p = folder / receipt['response_file']
        assert receipt['http_status'] == 200 and receipt['tls_verified']
        assert sha(p) == receipt['sha256'] and p.stat().st_size == receipt['bytes']
        query = parse_qs(urlsplit(receipt['requested_url']).query)
        assert query['m'] == [job['fullLabel']] and query['p'] == ['1']
        with fitz.open(p) as pdf: text1 = '\n'.join(page.get_text() for page in pdf); pages1 = len(pdf)
        pdf2 = PdfReader(str(p)); text2 = '\n'.join(page.extract_text() or '' for page in pdf2.pages)
        normalize = lambda value: re.sub(r'\s+', '', value).replace('—', '-').replace('–', '-')
        found1 = {normalize(m.group()) for m in standard_re.finditer(text1)}
        found2 = {normalize(m.group()) for m in standard_re.finditer(text2)}
        assert found1 and found1 == found2 and pages1 == len(pdf2.pages)
        for ref in job['record_refs']:
            source = folder / ref['source_file']; assert sha(source) == ref['source_page_sha256']
            index = int(ref['json_pointer'].split('/')[-1]); raw = load(source)['info']['list'][index]
            assert raw['uuid'] == ref['uuid'] and raw['fullLabel'] == job['fullLabel']
            assert raw['vehicleModel'] == ref['vehicleModel_raw'] == ref['model_key']
            assert hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()).hexdigest() == ref['full_row_sha256']
            assert normalize(ref['model_key']) in normalize(text1) and normalize(ref['model_key']) in normalize(text2)
            assert ref['recordNumber'] in normalize(text1) and ref['recordNumber'] in normalize(text2)
        assert job['label_job_id'] not in seen
        seen.add(job['label_job_id']); standards[','.join(sorted(found1))] += 1
    cp = load(folder / 'label_checkpoint.json'); assert len(seen) == cp['accepted_pdfs']
    return {'validated_pdfs': len(seen), 'standards_literal_counts': dict(standards), 'dual_text_engines': True,
            'source_pointer_and_actual_fullLabel_pass': True, 'same_tax_configuration_certified': False}

def validate_old():
    folder = ROOT / 'old_details'; cp = load(folder / 'checkpoint.json')
    sources = {r['stable_id_raw']: r for r in map(json.loads, (ROOT / 'independent_old_review/4497记录_旧库精确命中固定来源键.jsonl').read_text().splitlines())}
    seen, codes = set(), Counter()
    provider_records = 0
    for receipt_file in sorted((folder / 'raw').glob('*_receipt.json')):
        receipt = load(receipt_file)
        if not receipt.get('accepted'): continue
        identity = receipt['request_json']['applyId']; source = sources[identity]
        p = folder / receipt['file']; body = load(p); info = body['info']
        assert receipt['http_status'] == 200 and body['result'] == 1
        if receipt.get('imported_external_delivery'):
            original = folder / receipt['provider_original_receipt_file']
            assert sha(original) == receipt['provider_original_receipt_sha256']
            original_receipt = load(original)
            assert original_receipt['applyId'] == identity
            assert original_receipt['sha256'] == receipt['sha256']
            original_response = folder / receipt['provider_original_response_file']
            assert sha(original_response) == sha(p) == receipt['provider_original_response_sha256']
            assert receipt['tls_verified'] is None
            provider_records += 1
        else:
            assert receipt['tls_verified'] is True
        assert sha(p) == receipt['sha256'] and p.stat().st_size == receipt['bytes']
        assert info['vehicleNumber'] == source['model_key'] and receipt['input_record_key'] == source['record_key']
        if info.get('applyId'): assert info['applyId'] == identity
        if info.get('uniqId'): assert info['uniqId'] == source['record_number_raw']
        assert identity not in seen
        seen.add(identity); codes[str(info.get('testBasisStandard'))] += 1
    assert len(seen) == cp['accepted_records']
    return {'validated_details': len(seen), 'standard_fields_raw_counts': dict(codes), 'identity_echo_not_invented': True,
            'imported_provider_records': provider_records,
            'provider_tls_attestation_unavailable_records': provider_records,
            'same_tax_configuration_certified': False}

def publish(state, validate=True):
    protect()
    state.update(updated_utc=now(), labels=load(ROOT / 'label_archive/label_checkpoint.json')['accepted_pdfs'],
                 old_details=load(ROOT / 'old_details/checkpoint.json')['accepted_records'])
    state.update(remaining_labels=936-state['labels'], remaining_old_details=4497-state['old_details'],
                 frozen_cycle_gaps_closed=0, scientific_csv_modified=False)
    if validate:
        jwrite(ROOT / 'batch_independent_validation.json', {'generated_utc': now(), 'labels': validate_labels(), 'old_details': validate_old(), 'protected_scientific_csv': 52, 'protected_zips': 7})
    jwrite(ROOT / 'job_status.json', state)
    execution_note = (f'本轮由[GitHub云端任务]({RUN_URL})执行，关闭聊天不影响该任务。每100条核验后提交本分支；页面计数仅代表最后一次成功发布。任务最多运行330分钟，完成队列、遇访问边界或本地/发布异常时停止。若被取消或达到任务时限，使用仓库Actions页面的Run workflow从已提交断点恢复；最后一次running不等于此刻仍在线。'
                      if IN_ACTIONS else
                      '本轮在实际云工作区进程中执行，工作区保持运行时续采。工作区停止后须从已提交checkpoint恢复；最后一次running不等于此刻仍在线。')
    if state['status'] == 'ready_for_github_resume':
        execution_note = '本轮新增原件及缓存已核验，等待GitHub云端任务从已保存断点继续。是否启动以[实际Actions任务](https://github.com/lima0531/-/actions/workflows/continue-energy-evidence.yml)为准；等待交接状态不声称后台已运行。'
    (ROOT / 'README.md').write_text(f'''# 官方能耗证据连续续采

状态：**{state['status']}**。更新UTC：{state['updated_utc']}（北京时间＝UTC＋8小时）。

| 固定自动队列 | 累计已归档 | 待取 |
|---|---:|---:|
| 新库原样精确标签 | {state['labels']} / 936 | {state['remaining_labels']} |
| 旧库匹配applyId详情 | {state['old_details']} / 4497 | {state['remaining_old_details']} |

{state.get('message', '')}

单worker、至少2秒间隔，先余下标签，再余下旧详情；按100条一批落盘、来源/SHA/双文本引擎核验并提交同一分支。{execution_note} 网络拒绝、登录/验证码、429等保存断点并停，不切换路由或凭证。

以首100实测节奏，剩余公开原件约数小时；这不是全部科学缺口闭合时间。新库53页不重复采，复用已核验原字节；2条BMW空白候选保留在原阶段，不增加936口径。两库并集1246与被冻结的2208缺口不同。历史配置身份、历史公开时间、低温或逐车资格未经认证，不修改主CSV。JX历史电池总能量仍需企业/检测机构材料。

每份新PDF使用自身标准原文，不按代码/年份推工况；旧详情的空applyId/uniqId保留，不能虚构唯一回显。每批保护52份科学CSV和7个已有ZIP原SHA，原阶段包不重打。

- [机器状态与真实计数](job_status.json)
- [本批独立字节及来源核验](batch_independent_validation.json)
- [新标签、原件与剩余队列](label_archive/README.md)
- [旧详情、原件与剩余队列](old_details/README.md)
- [固定旧库输入](independent_old_review/README.md)
- [首100＋2及新库完整验收](../energy_new_complete_20261009/README.md)
- [实际运行脚本](run_continuous.py)
- [输出SHA清单](文件_SHA256.csv)

运行：仓库Actions页面可手动运行`Continue official energy evidence`；或在已有原仓库checkout中执行`python v1_5/energy_continuous_20261009/run_continuous.py --batch-size 100`。需Python/PDF依赖、正常公开网络；自动提交需已有GitHub写入连接。不需要官网账户凭证。`--no-publish`仅采集与本地验证，不提交Git。当前是否运行以实际Actions任务或本地进程为准，checkpoint是已保存证据的观察时间。
''')
    # The first-stage analysis files remain dated evidence, while this header reports current counts.
    old_header = f'''# 旧库详情连续续采：{state['old_details']} / 4497

最新剩余{state['remaining_old_details']}条。以[checkpoint](checkpoint.json)和[全部已取详情](details_readonly.jsonl)为准；本目录archive_review_summary及旧标准CSV是原首100阶段快照，不冒充当前全量复核。本轮当前来源/字节独立验证见[当前批次校验](../batch_independent_validation.json)。

`--limit N`是累计前N预算，复跑校验缓存后续取；0是完整4497。正常单worker，至少2秒间隔；访问拒绝保存断点停。详情applyId/uniqId为空时不虚构回显。固定输入来自相邻independent_old_review，旧列表原件位于[原公开视图](../../energy_registry_20261009/public_energy_registry/README.md)。

第101—200条复用用户已上传的DeepSeek原响应，经[逐条来源与原字节导入核查](../provider_import_review.json)后加入断点缓存。原收据、101次尝试和提供方时间保留在原目录；其TLS/匿名请求证明字段缺失，规范收据明确记为null，不声称这100条是本环境重新网络取得。
'''
    (ROOT/'old_details/README.md').write_text(old_header)
    for p, link in [(REPO/'README.md', 'v1_5/'+NAME), (V5/'README.md', NAME)]:
        content = p.read_text()
        if NAME not in content: p.write_text('> [当前自动续采进度]('+link+'/README.md)逐批更新，首阶段验收与科学版本v1.5保持独立。\n\n'+content)
    for folder in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        if folder.name == '__pycache__': continue
        # Recompute nested inventories first, avoiding stale inherited CSV rows.
        for sub in sorted({p.parent for p in folder.rglob('文件_SHA256.csv')}, key=lambda p: len(p.parts), reverse=True): manifest(sub)
        manifest(folder)
    manifest(ROOT)
    gp = V5 / 'file_manifest.json'; data = load(gp)
    data['latest_continuous_energy_evidence_directory'] = NAME
    data['continuous_energy_collection_counts'] = {key: state[key] for key in ['status','updated_utc','labels','old_details','remaining_labels','remaining_old_details']}
    data['scientific_csv_bytes_changed'] = False
    artifacts = {r['file']: r for r in data['artifacts']}
    artifacts.setdefault(NAME+'/README.md', {'file':NAME+'/README.md'})
    for name, item in artifacts.items(): item.update(bytes=(V5/name).stat().st_size, sha256=sha(V5/name), github_file_page='https://github.com/lima0531/-/blob/'+BRANCH+'/v1_5/'+name)
    data['artifacts'] = list(artifacts.values())
    data['files_excluding_this_manifest'] = [row(p,V5) for p in files(V5) if p != gp]
    jwrite(gp, data); protect()
    if args.no_publish: return
    visibility = json.loads(run(['gh','api','repos/lima0531/-']))
    assert visibility['private'] is False, 'User requested the repository remain public; do not change visibility.'
    remote = run(['gh','api','repos/lima0531/-/git/ref/heads/'+BRANCH]); remote_sha=json.loads(remote)['object']['sha']
    assert remote_sha == run(['git','rev-parse','HEAD']), 'Concurrent remote update: keep local evidence and stop for reconciliation; no force push.'
    run(['git','add','--','README.md','v1_5'])
    gold = load(ROOT/'inputs/scientific_golden.json')
    staged = set(run(['git','diff','--cached','--name-only','-z']).split('\0')) - {''}
    assert 'export_proposal.json' not in staged
    assert not staged & {'v1_5/'+name for name in gold}
    assert all(p=='README.md' or p.startswith('v1_5/') for p in staged)
    if not staged: return
    run(['git','-c','user.name=Codex','-c','user.email=codex@local','commit','--quiet','-m',f'Archive energy evidence progress: labels {state["labels"]}, details {state["old_details"]}'])
    run(['git','-c','credential.helper=','-c','credential.helper=!gh auth git-credential','push','https://github.com/lima0531/-.git','HEAD:refs/heads/'+BRANCH])
    expected = run(['git','rev-parse','HEAD'])
    actual = json.loads(run(['gh','api','repos/lima0531/-/git/ref/heads/'+BRANCH]))['object']['sha']
    assert expected == actual
    print(json.dumps({'published_commit':expected,'labels':state['labels'],'old_details':state['old_details'],'status':state['status']},ensure_ascii=False),flush=True)

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--batch-size',type=int,default=100)
parser.add_argument('--no-publish',action='store_true')
parser.add_argument('--publish-only',action='store_true')
parser.add_argument('--handoff-only',action='store_true',help='Revalidate saved evidence and publish a truthful ready-for-cloud handoff without collecting.')
args=parser.parse_args(); assert 1<=args.batch_size<=200
lock = (REPO/'.git/purchase_tax_energy_collection.lock').open('w')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
state={'started_utc':now(),'pid':os.getpid(),'status':'ready_for_github_resume' if args.handoff_only else 'running','active_library':'starting',
       'execution_environment':'github_actions' if IN_ACTIONS else 'local_workspace',
       'workflow_run_url':RUN_URL,
       'message':'新增原件和缓存重新核验；准备交由GitHub任务续采。' if args.handoff_only else '实际续采进程已启动，准备核验缓存并继续下一批。'}
try:
    # Revalidate the actual copied PDF cache before publishing the seeded count.
    seed_count = sum(bool(load(p).get('accepted')) for p in (ROOT/'label_archive/receipts').glob('*_receipt.json'))
    subprocess.run([sys.executable,str(ROOT/'label_archive/collect_matched_labels.py'),'--stop-after-total',str(seed_count),'--source-root',str(BASE/'public_new_snapshot'),'--output-root',str(ROOT/'label_archive'),'--target-model-file',str(ROOT/'label_archive/inputs/2208型号_固定工况待核清单.csv'),'--old-exact-model-file',str(ROOT/'label_archive/inputs/1233型号_旧库原文精确命中集合.csv')],check=True)
    publish(state)
    if not args.publish_only and not args.handoff_only:
        for kind,total in [('new_labels',936),('old_details',4497)]:
            while True:
                progress=load(ROOT/('label_archive/label_checkpoint.json' if kind=='new_labels' else 'old_details/checkpoint.json'))
                count=progress['accepted_pdfs' if kind=='new_labels' else 'accepted_records']
                if count>=total:break
                target=min(count+args.batch_size,total)
                state.update(active_library=kind,message=f'正在顺序取{kind}第{count+1}—{target}条；已发布页面保留上一完整批次，勿把进行中的本地请求计作已上传。')
                jwrite(ROOT/'job_status.json',state)
                command=([sys.executable,str(ROOT/'label_archive/collect_matched_labels.py'),'--source-root',str(BASE/'public_new_snapshot'),'--output-root',str(ROOT/'label_archive'),'--target-model-file',str(ROOT/'label_archive/inputs/2208型号_固定工况待核清单.csv'),'--old-exact-model-file',str(ROOT/'label_archive/inputs/1233型号_旧库原文精确命中集合.csv'),'--stop-after-total',str(target)] if kind=='new_labels' else [sys.executable,str(ROOT/'old_details/collect_old_details.py'),'--limit',str(target)])
                with (ROOT/f'{kind}_latest_log.txt').open('w') as log:
                    result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
                if result.returncode:
                    latest=load(ROOT/('label_archive/label_checkpoint.json' if kind=='new_labels' else 'old_details/checkpoint.json'))
                    state.update(status='stopped_at_recorded_boundary',message=str(latest.get('stop_reason','collector returned nonzero')))
                    publish(state); raise SystemExit(2)
                publish(state)
        state.update(status='completed_public_queues',active_library='finished',finished_utc=now(),message='936份精确标签与4497条旧详情公开队列已完成。原件数是证据数，冻结配置/工况闭合仍需另审。')
        publish(state)
except Exception as error:
    state.update(status='stopped_local_or_publication_error',updated_utc=now(),message=str(error),failure_type=type(error).__name__)
    jwrite(ROOT/'job_status.json',state)
    print(json.dumps({'error':type(error).__name__,'message':str(error),'evidence_preserved':True},ensure_ascii=False),flush=True)
    raise
