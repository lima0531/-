#!/usr/bin/env python3
"""Read-only trace of one legacy artifact and its risk/numeric-ready deltas."""
import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REL = '官方技术清单/重建3328_官方清单标记与资格轨迹.csv'
OLD_SHA = '73b31afdaf90fd5efa32063308a9ac4123b0bf2d86f941abbe3e9c4db09e7a3d'
FINAL_SHA = '1963fd09c4502d60c90a4a4a28660d9236ae19a3d126520c54c4ba5c98a5863d'
V15_SHA = '11e493ec70376fde3b463dcbc701bbda91f2bb7fc94c1a567e41e031a4fb8ce7'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, records):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    out = (args.output or root / 'round7/legacy_fingerprint').resolve()
    out.mkdir(parents=True, exist_ok=True)
    compact = root / 'compact_input_20261008/购置税项目_必要数据精简包_20261008'
    tracked = {}

    def track(path):
        path = path.resolve()
        if path not in tracked:
            tracked[path] = {'sha256_before': sha(path), 'bytes': path.stat().st_size}
        return path

    def read_json(path):
        return json.loads(track(path).read_text(encoding='utf-8'))

    def read_csv(path):
        with track(path).open(encoding='utf-8-sig', newline='') as f:
            return list(csv.DictReader(f))

    def relative(path):
        return str(path.relative_to(root))

    # Preserve the independently reviewed build-label evidence; this script does
    # not infer a complete archive identity from the single target file.
    build_evidence = read_json(out / 'legacy_build_evidence.json')
    historical = read_json(compact / '历史验收/完整包v1_1_34产物两次构建字节对账.json')
    compact_manifest = track(compact / '文件清单_SHA256.txt').read_text(encoding='utf-8-sig')
    provenance = read_csv(compact / '内容来源与指纹.csv')
    date_manifest = read_csv(root / 'round3/versioning/data_version_manifest.csv')
    final_summary = read_json(root / 'round3/reconstruction/reconstruction_summary.json')
    v15_summary = read_json(root / 'round5/reconstruction/effective_correction_rebuild_summary.json')
    prior = read_csv(root / 'round6/risk_change/风险集变动_74型号逐源对照.csv')
    prior_by_model = {x['model_key']: x for x in prior}
    new_events = read_csv(root / 'round3/coverage/new_withdrawal_events.csv')
    new_links = read_csv(root / 'round3/coverage/new_withdrawal_source_links.csv')
    event_by_model = {x['model_key']: x for x in new_events}
    links_by_model = {x['model_key']: x for x in new_links}
    risk_summary = read_json(root / 'round6/risk_change/risk_change_summary.json')
    recovery = read_csv(root / 'round5/source_recovery/106原件回收清单_v1_5.csv')
    sgm_source = next(x for x in recovery if x['source_sha256'] == v15_summary['source_original_sha256_verified'])
    for source in risk_summary['new_source_groups']:
        raw = track(root / 'round3/coverage/raw' / Path(source['source_file']).name)
        assert sha(raw) == source['source_sha256']
    sgm_raw = track(root / 'round5/originals' / Path(sgm_source['recovered_path']).name)
    assert sha(sgm_raw) == sgm_source['source_sha256']

    stages = [
        ('compact_legacy', compact / REL, OLD_SHA, '保留具体文件；精简包声明从v1.1逐字节提取'),
        ('date_v1_2', root / 'round3/versioning/data_v1_2' / REL, OLD_SHA, '日期v1.2实际输出；目标文件field_updates=0'),
        ('final_v1_3', root / 'round3/reconstruction/data_v1_3' / REL, FINAL_SHA, '本地最终重建v1.3'),
        ('v1_4', root / 'round4/data_v1_4' / REL, FINAL_SHA, 'v1.4继承同一轨迹文件'),
        ('v1_5', root / 'round5/reconstruction/data_v1_5' / REL, V15_SHA, 'v1.5包含SGM参数生效修订'),
    ]
    tables, fingerprints = {}, []
    for stage, path, expected, declaration in stages:
        rows = read_csv(path)
        table = {x['model_key']: x for x in rows}
        assert len(rows) == len(table) == 3328
        assert sha(path) == expected
        tables[stage] = table
        fingerprints.append({
            'evidence_id': stage, 'verification_level': 'actual_file_bytes_and_counts',
            'evidence_file': relative(path), 'artifact_relative_path': REL,
            'artifact_sha256': expected, 'artifact_bytes': path.stat().st_size,
            'rows': len(rows), 'risk_models': sum(x['in_preannouncement_active_riskset'] == '1' for x in rows),
            'numeric_ready_models': sum(x['numeric_input_ready'] == '1' for x in rows),
            'version_declaration': declaration,
            'recorded_generation_time_utc': final_summary['generated_at_utc'] if stage == 'final_v1_3' else '',
            'generation_time_scope': '最终重建摘要记录时刻' if stage == 'final_v1_3' else '目标文件精确生成时刻未在所读来源记录',
            'evidence_locator': '逐字节SHA256及逐行model_key唯一性/0-1标记复算',
        })

    target = next(x for x in historical['files'] if x['file'] == REL)
    dtarget = next(x for x in date_manifest if x['relative_path'] == REL)
    ptarget = next(x for x in provenance if x['精简包文件'] == REL)
    assert target['first_run_sha256'] == target['fresh_run_sha256'] == OLD_SHA
    assert dtarget['input_sha256'] == dtarget['v1_2_sha256'] == ptarget['源文件SHA256'] == OLD_SHA
    assert dtarget['field_updates'] == '0'
    assert OLD_SHA + '  ' + REL in compact_manifest
    declarations = [
        ('historical_first_build', compact / '历史验收/完整包v1_1_34产物两次构建字节对账.json', 'files[file=目标].first_run_sha256', historical['scope']),
        ('historical_fresh_build', compact / '历史验收/完整包v1_1_34产物两次构建字节对账.json', 'files[file=目标].fresh_run_sha256', historical['scope']),
        ('compact_manifest_record', compact / '文件清单_SHA256.txt', '第27行', '保留文件清单'),
        ('compact_provenance_record', compact / '内容来源与指纹.csv', '精简包文件=目标；复制方式=逐字节原样复制', '精简包内容来源记录'),
        ('date_v1_2_manifest_record', root / 'round3/versioning/data_version_manifest.csv', 'relative_path=目标；input_sha256=v1_2_sha256；field_updates=0', '日期v1.2清单'),
    ]
    for stage, path, locator, declaration in declarations:
        fingerprints.append({
            'evidence_id': stage, 'verification_level': 'retained_record_matches_verified_actual_file',
            'evidence_file': relative(path), 'artifact_relative_path': REL, 'artifact_sha256': OLD_SHA,
            'artifact_bytes': 852354, 'rows': 3328, 'risk_models': 2877, 'numeric_ready_models': 2488,
            'version_declaration': declaration, 'recorded_generation_time_utc': '',
            'generation_time_scope': '旧精确生成时间未记录；2026-10-08仅为历史报告日期；人数由同SHA实际文件复算',
            'evidence_locator': locator,
        })

    def chosen(stage, column):
        return {k for k, row in tables[stage].items() if row[column] == '1'}

    old_risk, final_risk, v15_risk = [chosen(s, 'in_preannouncement_active_riskset') for s in ('compact_legacy', 'final_v1_3', 'v1_5')]
    old_ready, final_ready, v15_ready = [chosen(s, 'numeric_input_ready') for s in ('compact_legacy', 'final_v1_3', 'v1_5')]
    exited = old_risk - final_risk
    restored = final_risk - old_risk
    ready_exited = old_ready - final_ready
    ready_restored = final_ready - old_ready
    sgm_added = v15_ready - final_ready
    checks = {
        'all_stage_keys_identical': all(set(t) == set(tables['compact_legacy']) for t in tables.values()),
        'legacy_risk_and_ready_2877_2488': (len(old_risk), len(old_ready)) == (2877, 2488),
        'final_risk_and_ready_2805_2424': (len(final_risk), len(final_ready)) == (2805, 2424),
        'v15_risk_and_ready_2805_2425': (len(v15_risk), len(v15_ready)) == (2805, 2425),
        'risk_exits_exact_new_73_models': exited == set(event_by_model) and len(exited) == 73,
        'risk_and_ready_restore_only_CSA': restored == ready_restored == {'CSA6461FBEV3'},
        'ready_exits_are_65_of_73_risk_exits': ready_exited <= exited and len(ready_exited) == 65,
        'remaining_8_exits_were_not_numeric_ready': len(exited - old_ready) == 8,
        'v15_risk_set_unchanged': v15_risk == final_risk,
        'v15_ready_add_only_SGM_without_removals': sgm_added == {'SGM6500BEBEV'} and not (final_ready - v15_ready),
        'SGM_already_in_risk_before_v15': 'SGM6500BEBEV' in old_risk & final_risk,
        'v12_target_byte_identical_to_legacy': sha(stages[0][1]) == sha(stages[1][1]),
        'v14_target_byte_identical_to_final_v13': sha(stages[2][1]) == sha(stages[3][1]),
        'historical_34_retained_hash_pairs_equal': len(historical['files']) == 34 and not historical['mismatches'] and all(x['first_run_sha256'] == x['fresh_run_sha256'] and x['equal'] for x in historical['files']),
    }
    assert all(checks.values()), checks

    changes = []
    for model in sorted(exited | restored | sgm_added):
        legacy, final, current = [tables[s][model] for s in ('compact_legacy', 'final_v1_3', 'v1_5')]
        p = prior_by_model.get(model, {})
        if model in exited:
            reason = '新增历史撤销：退出风险集；原ready=1' if model in ready_exited else '新增历史撤销：退出风险集；原已不足未计入ready'
        elif model in restored:
            reason = '第27批撤销错日期修复：恢复风险及ready'
        else:
            reason = 'v1.5 SGM显式参数修订：只增加ready，风险身份不变'
        changes.append({
            'model_key': model, 'change_reason': reason,
            'legacy_sha256': OLD_SHA, 'final_v1_3_sha256': FINAL_SHA, 'current_v1_5_sha256': V15_SHA,
            'legacy_risk': legacy['in_preannouncement_active_riskset'], 'final_v1_3_risk': final['in_preannouncement_active_riskset'], 'v1_5_risk': current['in_preannouncement_active_riskset'],
            'legacy_numeric_ready': legacy['numeric_input_ready'], 'final_v1_3_numeric_ready': final['numeric_input_ready'], 'v1_5_numeric_ready': current['numeric_input_ready'],
            'old_ready_minus65': int(model in ready_exited), 'final_ready_plus1_CSA': int(model in ready_restored), 'v15_ready_plus1_SGM': int(model in sgm_added),
            'trigger_event_id': p.get('trigger_event_id', ''),
            'trigger_batch': p.get('trigger_event_batch', '64'),
            'trigger_date': p.get('trigger_observed_date', '2023-04-17'),
            'source_record_id': p.get('trigger_source_record_id', v15_summary['corrected_record_id']),
            'source_sha256': p.get('trigger_source_sha256', sgm_source['source_sha256']),
            'source_location': p.get('trigger_source_location', '第64批勘误，显式目标old-62-Word97--0-7'),
            'source_url': p.get('trigger_source_url', sgm_source['download_url']),
            'announcement_url': p.get('trigger_announcement_url', ''),
            'source_origin': '用户本轮提供历史原件' if model in sgm_added else '主管部门公开来源与保存原件',
            'evidence_file': 'round5/reconstruction/effective_correction_rebuild_summary.json' if model in sgm_added else 'round6/risk_change/风险集变动_74型号逐源对照.csv',
            'CSA_old_withdrawal_date': '2020-06-02' if model in restored else '',
            'CSA_corrected_withdrawal_date': '2019-10-25' if model in restored else '',
            'CSA_relisting_date': '2019-12-10' if model in restored else '',
        })
        if model in prior_by_model:
            assert p['old_numeric_ready'] == legacy['numeric_input_ready']
            assert p['final_v1_3_numeric_ready'] == final['numeric_input_ready']
        if model in exited:
            assert p['trigger_event_id'] == event_by_model[model]['event_id'] == links_by_model[model]['event_id']

    groups = []
    for source in risk_summary['new_source_groups']:
        members = {k for k, row in links_by_model.items() if row['source_sha256'] == source['source_sha256']}
        groups.append({
            'source_tag': source['source_tag'], 'source_sha256': source['source_sha256'],
            'risk_exits': len(members), 'numeric_ready_exits': len(members & ready_exited),
            'previously_insufficient_exits': len(members - old_ready),
            'registered_public_date': source['registered_public_observation_date'],
            'source_url': source['source_url'], 'announcement_url': source['announcement_url'],
        })
    assert sum(x['risk_exits'] for x in groups) == 73
    assert sum(x['numeric_ready_exits'] for x in groups) == 65
    assert sum(x['previously_insufficient_exits'] for x in groups) == 8

    write_csv(out / '逐指纹_实际文件与保留构建记录.csv', fingerprints)
    write_csv(out / '输入准备与风险变动_75型号逐源对照.csv', changes)
    write_csv(out / '新增撤销_风险与ready退出分配.csv', groups)
    input_hashes = []
    for path, before in sorted(tracked.items(), key=lambda pair: str(pair[0])):
        after = sha(path)
        assert after == before['sha256_before'], path
        input_hashes.append({'relative_path': relative(path), 'bytes': before['bytes'], 'sha256_before': before['sha256_before'], 'sha256_after': after, 'unchanged': True})
    write_csv(out / '只读核查输入_SHA256.csv', input_hashes)
    summary = {
        'audit_generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_relative_file': REL, 'supplied_old_prefix': OLD_SHA[:16],
        'resolved_legacy_sha256': OLD_SHA, 'final_v1_3_sha256': FINAL_SHA, 'current_v1_5_sha256': V15_SHA,
        'legacy_counts': {'risk': 2877, 'numeric_ready': 2488},
        'final_v1_3_counts': {'risk': 2805, 'numeric_ready': 2424},
        'current_v1_5_counts': {'risk': 2805, 'numeric_ready': 2425},
        'risk_equation': '2877 − 73 + 1 = 2805',
        'numeric_ready_equation': '2488 − 65 + 1 = 2424; 2424 + 1 = 2425',
        'risk_exits': sorted(exited), 'numeric_ready_exits': sorted(ready_exited),
        'previously_insufficient_risk_exits': sorted(exited - old_ready),
        'risk_and_numeric_ready_restore': sorted(restored), 'v15_numeric_ready_only_add': sorted(sgm_added),
        'new_withdrawal_source_allocation': groups,
        'historic_two_build_scope': historical['scope'], 'historic_two_build_recorded_files': 34,
        'historic_target_both_builds_same_sha': True, 'historic_builds_reexecuted_this_round': False,
        'legacy_exact_generation_time_utc': None,
        'legacy_time_limit': '保留两次构建JSON、日期v1.2清单/摘要均未记录目标精确生成时刻；历史报告仅明确2026-10-08',
        'final_v1_3_summary_generation_time_utc': final_summary['generated_at_utc'],
        'specific_csv_identity_now_resolved': True,
        'whole_user_named_legacy_v1_3_archive_identity_resolved': False,
        'version_label_conclusion': '该旧SHA不是本地最终v1.3轨迹文件；若将它称为最终v1.3，应订正该文件标签。单文件证据不认证未打开40MB归档的交付名称。',
        'prior_round6_reports_preserved': True, 'v15_caused_2877_to_2805_risk_change': False,
        'fingerprint_record_rows': len(fingerprints), 'changed_model_rows': len(changes),
        'checks': checks, 'all_checks_pass': all(checks.values()),
        'all_tracked_inputs_unchanged': True, 'read_only_input_file_count': len(input_hashes),
    }
    (out / 'legacy_fingerprint_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    readme = f'''# 旧轨迹表指纹与2488→2424→2425的闭合说明

本轮新增的旧指纹 `73b31afdaf90fd5e` 已定位到完整SHA `{OLD_SHA}`。已打开精简包内的具体轨迹表与日期v1.2实际轨迹表都是852354字节、3328型号、风险2877、数值输入准备2488；两份文件逐字节相同。因此，原round6尚未定位的**具体CSV身份**现已闭合。原报告保留；用户当时所称整包“v1.3”的交付名称和未打开40MB归档内容仍不能仅由此单文件证明。

本地最终v1.3/v1.4轨迹表SHA为 `{FINAL_SHA}`，855683字节，风险2805、输入准备2424；当前v1.5 SHA为 `{V15_SHA}`，风险2805、输入准备2425。旧SHA与最终v1.3实际文件不同。若此前把旧指纹文件称为“最终v1.3”，该文件标签应更正；这不等于将未核实的整包强行命名为v1.1或v1.2。

| 已打开文件或保留证据 | SHA前16位 | 风险 | 输入准备 |
|---|---|---:|---:|
| 精简包实际文件；历史v1.1两次构建记录对应项 | `73b31afdaf90fd5e` | 2877 | 2488 |
| 日期v1.2实际文件，清单记field_updates=0 | `73b31afdaf90fd5e` | 2877 | 2488 |
| 最终v1.3及v1.4实际文件 | `1963fd09c4502d60` | 2805 | 2424 |
| 当前v1.5实际文件 | `11e493ec70376fde` | 2805 | 2425 |

历史两次构建JSON明确声明“{historical['scope']}”，目标文件first_run与fresh_run均为旧全SHA；34组保留记录均相等且mismatches为空。本轮核实记录及目标当前字节，未重新执行两个历史完整构建。精简包README明确从2026-10-08完整包v1.1逐字节提取。旧构建JSON与日期v1.2清单/摘要没有目标精确生成时间，历史报告日期仅为2026-10-08，不能用提取时间或文件mtime替代。本地最终v1.3摘要记录时间为 `{final_summary['generated_at_utc']}`。

人数调整来自可追溯新证据并已重算，不是同一CSV的统计口径猜测：

- **风险：2877 − 73 + 1 = 2805。** 新补2018-05-22独立撤销公告使65型号退出，第28批撤销使8型号退出。第27批旧原件误挂第32批2020-06-02，修正为第27批2019-10-25后，CSA6461FBEV3在2019-12-10的重新列入变为截点前最新事件，恢复1型号。
- **输入准备：2488 − 65 + 1 = 2424。** 上述73个风险退出型号中，原ready=1有65个，原已不足有8个。按原件来源拆开分别为2018-05-22的58个ready退出/7个原不足，以及第28批的7个ready退出/1个原不足。CSA同时由ready=0恢复为1。“2018来源65个风险退出”和“合计65个ready退出”是不同集合。
- **v1.5输入准备：2424 + 1 = 2425。** 仅SGM6500BEBEV因第64批显式参数勘误生效，ready从0变1；它前后已在风险集内，风险集合保持2805。因此本轮v1.5未引起2877→2805调整。

[75型号逐源对照](输入准备与风险变动_75型号逐源对照.csv)保留73退出、CSA恢复、SGM准备变化的逐型号旧新标记、事件/记录ID、原件SHA及来源；[逐指纹表](逐指纹_实际文件与保留构建记录.csv)区分实际字节验证与保留记录；[逐来源分配](新增撤销_风险与ready退出分配.csv)将58+7及7+1分开。两份新撤销原件分别SHA `f943ccd1…` 与 `666f5bef…`，本轮再次验证实际字节。SGM原件SHA `c4e23898…`来自用户本轮提供的历史原件，来源不冒称新官网下载。

复跑：`python trace_legacy_fingerprint.py --root /path/to/purchase_tax_audit`。需保留项目中的compact_input、round3、round4、round5、round6及本目录独立构建证据JSON。脚本只读源数据，输出本目录CSV/摘要；[{len(input_hashes)}份输入的前后SHA](只读核查输入_SHA256.csv)全部一致。旧数据和旧报告未改写。源码、输出及独立证据列在排除自身的文件清单中。
'''
    (out / 'README.md').write_text(readme, encoding='utf-8')
    print(json.dumps({'all_checks_pass': True, 'risk_equation': summary['risk_equation'], 'ready_equation': summary['numeric_ready_equation'], 'changed_models': len(changes), 'source_allocation': groups, 'inputs_unchanged': len(input_hashes)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
