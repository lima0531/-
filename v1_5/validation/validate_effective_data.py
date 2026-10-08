#!/usr/bin/env python3
"""Independent CSV-only review of the explicitly resolved field-correction view; does not import or run the supplied check script.

Dates are ISO dates and compared lexicographically. A missing lower bound is
unbounded to the past. An event can be the last observed event by a cutoff if it
can have occurred by then and its latest feasible date is at least every certain
event's earliest feasible date. Tied last events remain possible; opposite
actions would therefore yield an unknown state, never a fabricated active flag.

These are observed catalogue states within supplied events and date bounds.
They do not certify source completeness, legal qualification, or market exit.
"""
import argparse
import calendar
import collections
import csv
import datetime
import hashlib
import json
import pathlib
import re
import unicodedata
from decimal import Decimal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    inputs = {}
    checks = []
    differences = []

    def read(rel):
        path = args.input / rel
        inputs[rel] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
        inputs[rel].update(rows=len(rows), fields=reader.fieldnames)
        return rows

    def check(name, mismatches, detail=None):
        checks.append({"name": name, "status": "PASS" if mismatches == 0 else "FAIL", "mismatch_count": mismatches, "detail": detail})

    def equal(scope, row, column, expected, actual=None):
        actual = row.get(column) if actual is None else actual
        if expected != actual:
            differences.append({"scope": scope, "model_key": row.get("model_key", ""), "time": row.get("cutoff", row.get("month", "")), "column": column, "expected": repr(expected), "actual": repr(actual)})
            return 1
        return 0

    def split(value):
        return set(value.split("|")) - {""}

    def norm(value):
        return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).upper()

    def possible_last(rows, cutoff):
        possible = [r for r in rows if not r["public_date_lower_bound"] or r["public_date_lower_bound"] <= cutoff]
        certain = [r for r in possible if r["public_date_upper_bound"] <= cutoff]
        required_lower = max((r["public_date_lower_bound"] for r in certain), default="")
        candidates = [r for r in possible if min(r["public_date_upper_bound"], cutoff) >= required_lower]
        return candidates, possible, certain

    def state(rows, cutoff):
        candidates, possible, certain = possible_last(rows, cutoff)
        actions = {r["action"] for r in candidates}
        if not certain:
            actions.add("未观察到列入")
        if actions == {"列入"}:
            label, active, robust = "在册（区间口径下的已收集事件）", "1", "1"
        elif actions == {"撤销"}:
            label, active, robust = "已撤销（区间口径下的已收集事件）", "0", "1"
        elif actions == {"未观察到列入"}:
            label, active, robust = "未列入（已收集记录范围）", "0", "1"
        else:
            label, active, robust = "日期区间导致状态不确定", "", "0"
        exact_dates = {r['publish_date_exact'] for r in candidates}
        last_exact = next(iter(exact_dates)) if len(exact_dates) == 1 else ''
        return {"state": label, "catalogue_active_observed": active, "state_robust_under_date_bounds": robust, "last_event_exact_date": last_exact,
                "ids": {r["event_id"] for r in candidates}, "actions": actions,
                "certain": len(certain), "potential": len(possible)}

    def parameter(rows, cutoff):
        candidates, possible, certain = possible_last(rows, cutoff)
        all_observed = bool(candidates) and all(r["public_date_upper_bound"] <= cutoff for r in candidates)
        result = {"ids": {r["record_id"] for r in candidates}, "all_observed": str(int(all_observed)),
                  "upper": max((r["public_date_upper_bound"] for r in candidates), default="")}
        for column in ["range_point", "curb_mass_point", "battery_mass_point", "battery_energy_point", "density_proxy_point"]:
            values = {r[column] for r in candidates}
            result[column] = next(iter(values)) if all_observed and len(values) == 1 else ""
        return result

    def shortfall(value, threshold):
        return str(max(Decimal(0), (Decimal(threshold) - Decimal(value)) / Decimal(threshold))) if value else ""

    def number_equal(scope, row, column, expected):
        actual = row.get(column, "")
        same = (actual == expected == "") or (actual != "" and expected != "" and Decimal(actual) == Decimal(expected))
        return 0 if same else equal(scope, row, column, expected)

    members = read("研究数据/样本成员重建.csv")
    panel = read("研究数据/车型月度面板_2022至2024.csv")
    snapshots = read("研究数据/重建样本_两截点参数与暴露.csv")
    cutoff_states = read("研究数据/重建样本_三截点状态.csv")
    events = read("研究数据/资格事件_重建去重表.csv")
    event_links = read("研究数据/资格事件_逐原件连接.csv")
    parameter_versions = read("研究数据/参数版本_字段勘误生效视图.csv")
    member_sources = read("研究数据/原件列入_成员来源长表.csv")
    risk = read("研究数据/公告前风险集_连续处理强度输入.csv")
    trajectories = read("研究数据/政策后资格轨迹与重申报标签.csv")
    original_rows = read("1991基线/16753_逐行筛选说明.csv")
    frozen_rows = read("1991基线/1991_独立重建名单.csv")

    member_map = {r["model_key"]: r for r in members}
    member_keys = set(member_map)
    event_by_model = collections.defaultdict(list)
    for row in events:
        event_by_model[row["model_key"]].append(row)
    parameters_by_model = collections.defaultdict(list)
    parameter_by_id = {r["record_id"]: r for r in parameter_versions}
    for row in parameter_versions:
        if row["admitted_to_analysis_cohort"] == "1":
            parameters_by_model[row["model_key"]].append(row)
    sources_by_model = collections.defaultdict(list)
    for row in member_sources:
        sources_by_model[row["model_key"]].append(row)
    snapshot_map = {(r["model_key"], r["cutoff"]): r for r in snapshots}
    risk_map = {r["model_key"]: r for r in risk}

    months = {f"{y}-{m:02}" for y in range(2022, 2025) for m in range(1, 13)}
    panel_keys = [(r["model_key"], r["month"]) for r in panel]
    check("panel_119808_unique_keys_full_3328_times_36", int(len(panel) != 119808) + int(len(set(panel_keys)) != len(panel)) + int(set(panel_keys) != {(k,m) for k in member_keys for m in months}), {"rows": len(panel), "models": len({r['model_key'] for r in panel}), "months": sorted({r['month'] for r in panel})})
    check("member_3328_unique_keys", int(len(members) != 3328) + int(len(member_map) != len(members)))
    check("parameter_snapshot_6656_unique_keys_two_cutoffs", int(len(snapshots) != 6656) + int(len(snapshot_map) != len(snapshots)) + int(set(snapshot_map) != {(k,c) for k in member_keys for c in ['2023-12-10', '2023-12-31']}))
    check("three_cutoff_states_9984_unique_keys", int(len(cutoff_states) != 9984) + int({(r['model_key'],r['cutoff']) for r in cutoff_states} != {(k,c) for k in member_keys for c in ['2023-12-10', '2023-12-31', '2024-12-31']}))

    normalized_mismatches = sum(equal("historical_normalization", r, "model_key", norm(r["model_raw"])) for r in original_rows)
    normalized_mismatches += sum(equal("parameter_normalization", r, "model_key", norm(r["model_raw"])) for r in parameter_versions)
    normalized_mismatches += sum(equal("member_source_normalization", r, "model_key", norm(r["model_raw"])) for r in member_sources)
    check("NFKC_whitespace_uppercase_keys", normalized_mismatches)
    selected = [r for r in original_rows if r['power'] == 'BEV' and r['vehicle_class'] == '乘用车' and norm(r['model_raw'])]
    reconstructed_frozen = {norm(r['model_raw']) for r in selected}
    frozen = {r['model_key'] for r in frozen_rows}
    flagged_frozen = {r['model_key'] for r in members if r['in_frozen_1991'] == '1'}
    recovered = {r['model_key'] for r in members if r['recovered_member'] == '1'}
    check("frozen_1991_reconstructed_from_16753_supplied_rows", int(len(original_rows) != 16753) + int(len(selected) != 2013) + int(reconstructed_frozen != frozen) + int(frozen != flagged_frozen) + int(len(frozen) != 1991), {"selected_rows": len(selected), "deduplicated_models": len(reconstructed_frozen), "duplicates_removed": len(selected)-len(reconstructed_frozen)})
    check("3328_equals_1991_plus_disjoint_1337", int(len(recovered) != 1337) + int(bool(frozen & recovered)) + int(frozen | recovered != member_keys))

    membership_errors = 0
    for row in members:
        sources = sources_by_model[row['model_key']]
        first_upper = min((r['public_date_upper_bound'] for r in sources), default='9999-12-31')
        announcement_member = str(int(first_upper <= '2023-12-10'))
        implementation_member = str(int(first_upper <= '2023-12-31'))
        membership_errors += equal("membership", row, "membership_announcement_cohort", announcement_member)
        membership_errors += equal("membership", row, "membership_implementation_cohort", implementation_member)
        membership_errors += equal("membership", row, "membership_gap_first_listed", str(int('2023-12-10' < first_upper <= '2023-12-31')))
        membership_errors += equal("membership", row, "source_record_ids", {r['record_id'] for r in sources}, split(row['source_record_ids']))
        membership_errors += equal("membership", row, "source_listing_record_count", str(len(sources)))
    check("membership_flags_recomputed_from_supplied_listing_source_upper_dates", membership_errors, {"announcement_members": sum(r['membership_announcement_cohort'] == '1' for r in members), "gap_members": sum(r['membership_gap_first_listed'] == '1' for r in members)})

    event_map = {r['event_id']: r for r in events}
    event_connection_map = collections.defaultdict(list)
    for row in event_links:
        event_connection_map[row['event_id']].append(row)
    event_errors = int(len(event_map) != len(events)) + int(set(event_map) != set(event_connection_map))
    date_errors = 0
    for row in events:
        links = event_connection_map[row['event_id']]
        event_errors += equal("event_connection", row, "source_record_ids", {r['source_record_id'] for r in links}, split(row['source_record_ids']))
        event_errors += equal("event_connection", row, "source_record_count", str(len(links)))
        for link in links:
            for column in ['model_key', 'action', 'system', 'event_batch', 'publish_date_exact', 'public_date_lower_bound', 'public_date_upper_bound', 'effective_date_exception']:
                event_errors += equal("event_connection", row, column, link[column])
        if row['public_date_lower_bound'] and row['public_date_lower_bound'] > row['public_date_upper_bound']:
            date_errors += 1
        if row['publish_date_exact'] and not (row['publish_date_exact'] == row['public_date_lower_bound'] == row['public_date_upper_bound']):
            date_errors += 1
    check("event_keys_and_source_connections", event_errors, {"event_rows": len(events), "connection_rows": len(event_links)})
    check("event_date_intervals_and_exact_values_internally_consistent", date_errors)
    exceptions = [r for r in events if r['effective_date_exception'] == '1']
    check("all_503_effective_date_exceptions_are_june_1_withdrawals", int(len(exceptions) != 503) + sum(not(r['action'] == '撤销' and r['system'] == '减免目录' and r['event_batch'] == '6' and r['public_date_lower_bound'] == r['public_date_upper_bound'] == '2024-06-01') for r in exceptions))

    state_errors = 0
    panel_state_counts = collections.Counter()
    cutoff_state_counts = collections.Counter()
    for scope, rows, date_column in [('monthly_state', panel, 'month_end'), ('three_cutoff_state', cutoff_states, 'cutoff')]:
        group_errors = 0
        for row in rows:
            expected = state(event_by_model[row['model_key']], row[date_column])
            for column in ['state', 'catalogue_active_observed', 'state_robust_under_date_bounds', 'last_event_exact_date']:
                group_errors += equal(scope, row, column, expected[column])
            group_errors += equal(scope, row, 'possible_last_event_ids', expected['ids'], split(row['possible_last_event_ids']))
            if scope == 'three_cutoff_state':
                group_errors += equal(scope, row, 'certain_observed_event_count', str(expected['certain']))
                # The dictionary does not define this auxiliary field. Across
                # all supplied rows it equals the possible-LAST-event count,
                # rather than every event that could have occurred by cutoff.
                group_errors += equal(scope, row, 'potential_event_count', str(len(expected['ids'])))
                group_errors += equal(scope, row, 'possible_last_actions', expected['actions'], split(row['possible_last_actions']))
                cutoff_state_counts[(row['cutoff'], expected['state'])] += 1
            else:
                panel_state_counts[expected['state']] += 1
        check(scope + "_independently_recomputed_from_event_intervals", group_errors, {"rows": len(rows), "comparison_fields": ['state', 'catalogue_active_observed', 'state_robust_under_date_bounds', 'possible_last_event_ids', 'last_event_exact_date']})
        state_errors += group_errors

    calendar_errors = 0
    month_by_model = collections.defaultdict(list)
    for row in panel:
        year, month = map(int, row['month'].split('-'))
        month_end = f"{year}-{month:02}-{calendar.monthrange(year, month)[1]:02}"
        calendar_errors += equal('calendar', row, 'month_end', month_end)
        for column, threshold in [('post_announcement','2023-12-11'), ('post_implementation','2024-01-01'), ('post_transition_end','2024-06-01')]:
            calendar_errors += equal('calendar', row, column, str(int(month_end >= threshold)))
        month_by_model[row['model_key']].append(row)
    check("month_end_calendar_and_policy_flags", calendar_errors)

    parameter_errors = 0
    snapshot_parameter_errors = 0
    for row in snapshots:
        expected = parameter(parameters_by_model[row['model_key']], row['cutoff'])
        snapshot_parameter_errors += equal('snapshot_parameter', row, 'possible_latest_record_ids', expected['ids'], split(row['possible_latest_record_ids']))
        snapshot_parameter_errors += equal('snapshot_parameter', row, 'possible_latest_record_count', str(len(expected['ids'])))
        snapshot_parameter_errors += equal('snapshot_parameter', row, 'all_possible_latest_observed_before_cutoff', expected['all_observed'])
        snapshot_parameter_errors += equal('snapshot_parameter', row, 'possible_date_upper_max', expected['upper'])
        for column in ['range_point','curb_mass_point','battery_mass_point','battery_energy_point','density_proxy_point']:
            snapshot_parameter_errors += number_equal('snapshot_parameter', row, column, expected[column])
    check("both_parameter_snapshots_independent_candidate_sets_and_points", snapshot_parameter_errors)
    for row in panel:
        expected = parameter(parameters_by_model[row['model_key']], row['month_end'])
        parameter_errors += equal('monthly_parameter', row, 'parameter_possible_latest_ids', expected['ids'], split(row['parameter_possible_latest_ids']))
        parameter_errors += equal('monthly_parameter', row, 'parameter_latest_upper', expected['upper'])
        parameter_errors += number_equal('monthly_parameter', row, 'range_record_point', expected['range_point'])
        parameter_errors += number_equal('monthly_parameter', row, 'density_proxy_record_point', expected['density_proxy_point'])
    check("monthly_current_parameter_candidates_upper_dates_and_points", parameter_errors)

    density_errors = 0
    for row in parameter_versions:
        for column, numerator, denominator in [('density_proxy_point','battery_energy_point','battery_mass_point'), ('density_proxy_lower','battery_energy_lower','battery_mass_upper'), ('density_proxy_upper','battery_energy_upper','battery_mass_lower')]:
            value = str(Decimal(1000) * Decimal(row[numerator]) / Decimal(row[denominator])) if row[numerator] and row[denominator] and Decimal(row[denominator]) != 0 else ''
            density_errors += number_equal('density_calculation', row, column, value)
    check("7203_parameter_observations_density_points_and_envelopes", density_errors)

    exposure_errors = 0
    freeze_source_errors = 0
    locked_errors = 0
    risk_ready_count = 0
    risk_active_count = 0
    for row in risk:
        pre = snapshot_map[(row['model_key'], '2023-12-10')]
        observed_state = state(event_by_model[row['model_key']], '2023-12-10')
        exposure_errors += equal('risk_state', row, 'announcement_state', observed_state['state'])
        exposure_errors += equal('risk_state', row, 'announcement_active_observed', observed_state['catalogue_active_observed'])
        range_shortfall = shortfall(pre['range_point'], '200')
        density_shortfall = shortfall(pre['density_proxy_point'], '125')
        joint = str(max(Decimal(range_shortfall), Decimal(density_shortfall))) if range_shortfall and density_shortfall else ''
        for column, value in [('continuous_exposure_range',range_shortfall), ('continuous_exposure_density_proxy',density_shortfall), ('continuous_exposure_joint_max',joint)]:
            exposure_errors += number_equal('risk_exposure', row, column, value)
        exposure_errors += equal('risk_exposure', row, 'exposure_record_ids', split(pre['possible_latest_record_ids']), split(row['exposure_record_ids']))
        exposure_errors += equal('risk_exposure', row, 'exposure_max_observation_upper', pre['possible_date_upper_max'])
        is_risk = row['membership_announcement_cohort'] == '1' and observed_state['catalogue_active_observed'] == '1'
        expected_ready = str(int(is_risk and bool(pre['range_point']) and bool(pre['density_proxy_point'])))
        exposure_errors += equal('risk_ready', row, 'descriptive_continuous_did_input_ready', expected_ready)
        risk_active_count += is_risk
        risk_ready_count += expected_ready == '1'
        for record_id in split(row['exposure_record_ids']):
            source = parameter_by_id.get(record_id)
            if source is None or source['model_key'] != row['model_key'] or source['public_date_upper_bound'] > '2023-12-10':
                freeze_source_errors += 1
        for panel_row in month_by_model[row['model_key']]:
            for target, source in [('exposure_range_locked_preannouncement','continuous_exposure_range'), ('exposure_density_proxy_locked_preannouncement','continuous_exposure_density_proxy'), ('exposure_joint_max_locked_preannouncement','continuous_exposure_joint_max')]:
                locked_errors += number_equal('locked_exposure', panel_row, target, row[source])
            locked_errors += equal('locked_exposure', panel_row, 'exposure_source_ids', split(row['exposure_record_ids']), split(panel_row['exposure_source_ids']))
            locked_errors += equal('locked_exposure', panel_row, 'descriptive_continuous_did_input_ready', row['descriptive_continuous_did_input_ready'])
    check("riskset_states_readiness_and_continuous_formulas", exposure_errors, {"active_preannouncement_risk_models": risk_active_count, "numeric_input_ready": risk_ready_count, "missing_two_single_values": risk_active_count-risk_ready_count})
    check("no_exposure_source_public_upper_after_2023_12_10", freeze_source_errors)
    check("all_36_months_locked_exposures_and_source_sets_match_preannouncement", locked_errors)

    trajectory_errors = 0
    cumulative_errors = 0
    withdrawn_models = set()
    relisted_models = set()
    for row in trajectories:
        observed_events = event_by_model[row['model_key']]
        withdrawals = [r for r in observed_events if r['action'] == '撤销' and '2024-01-01' <= r['public_date_upper_bound'] <= '2024-12-31']
        first = min((r['public_date_upper_bound'] for r in withdrawals), default='9999-12-31')
        relisted = [r for r in observed_events if r['action'] == '列入' and r['public_date_lower_bound'] > first and r['public_date_upper_bound'] <= '2024-12-31']
        trajectory_errors += equal('trajectory', row, 'post2024_withdrawal_observed', str(int(bool(withdrawals))))
        trajectory_errors += equal('trajectory', row, 'relisted_after_2024_withdrawal_observed', str(int(bool(relisted))))
        trajectory_errors += equal('trajectory', row, 'withdrawal_event_ids', {r['event_id'] for r in withdrawals}, split(row['withdrawal_event_ids']))
        trajectory_errors += equal('trajectory', row, 'relisting_event_ids', {r['event_id'] for r in relisted}, split(row['relisting_event_ids']))
        for column, cutoff in [('state_preannouncement', '2023-12-10'), ('state_preimplementation', '2023-12-31'), ('state_year_end_2024', '2024-12-31')]:
            trajectory_errors += equal('trajectory_state', row, column, state(observed_events, cutoff)['state'])
        trajectory_errors += equal('trajectory', row, 'reapplication_observed_by_2024_year_end', str(int(any(r['reapplication_signal'] == '1' and r['public_date_upper_bound'] <= '2024-12-31' for r in observed_events))))
        if withdrawals:
            withdrawn_models.add(row['model_key'])
        if relisted:
            relisted_models.add(row['model_key'])
        for panel_row in month_by_model[row['model_key']]:
            end = panel_row['month_end']
            cumulative_errors += equal('cumulative_event', panel_row, 'explicit_withdrawal_observed_cumulative', str(int(any(r['action'] == '撤销' and r['public_date_upper_bound'] <= end for r in observed_events))))
            cumulative_errors += equal('cumulative_event', panel_row, 'reapplication_observed_cumulative', str(int(any(r['reapplication_signal'] == '1' and r['public_date_upper_bound'] <= end for r in observed_events))))
    check("2024_withdrawal_and_subsequent_relisting_labels_independent", trajectory_errors, {"withdrawn_models": len(withdrawn_models), "relisted_models": len(relisted_models), "relisting_is_withdrawal_subset": relisted_models <= withdrawn_models})
    check("monthly_withdrawal_and_reapplication_cumulative_flags", cumulative_errors)

    boundary_errors = sum(r['configuration_identity_certified'] != '0' or r['production_or_market_exit_inferred'] != '0' for r in panel)
    boundary_errors += sum(r['configuration_identity_certified'] != '0' or r['low_temperature_evidence_obtained'] != '0' for r in snapshots)
    boundary_errors += sum(r['whole_catalogue_population_exhaustiveness_certified'] != '0' or r['vehicle_class_independently_certified'] != '0' for r in members)
    boundary_errors += sum(r['eligibility_classification_certified'] != '0' or r['causal_identification_certified'] != '0' or r['low_temperature_evidence_obtained'] != '0' for r in risk)
    check("unknown_configuration_legal_causal_population_exit_certifications_stay_zero", boundary_errors)

    report = {
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "input_root": str(args.input),
        "method": "Independent standard-library implementation, written from the dictionaries; supplied verification script was neither read nor executed.",
        "scope_limits": ["CSV consistency and observed event/date-bound reconstruction only.", "This validator checks derived CSV reconstruction. Public originals and selected full-table extractions are separately archived; their recovery does not certify a global source/event universe.", "Date inputs use the accepted registered-date version; first-online times and current-site migration metadata remain separate evidence questions.", "Month-end observed states and robust date-bound flags do not certify legal eligibility for a particular vehicle.", "This validator checks the batch-6 effective-date exception in CSV metadata; original text authentication is recorded separately in round3/technical.", "Frozen-source upper dates prevent within-table future parameter backfill; this does not prove all real historical publication times or unchanged configuration identity."],
        "field_semantics_observation": {"potential_event_count": "Not explicitly defined in supplied dictionaries. All 9984 values match the possible-last-event candidate count. It is therefore checked for that observed relationship, without labeling a different interpretation as a data error."},
        "summary": {"checks": len(checks), "pass": sum(c['status'] == 'PASS' for c in checks), "fail": sum(c['status'] == 'FAIL' for c in checks), "differences": len(differences)},
        "checks": checks,
        "month_end_state_counts": dict(panel_state_counts),
        "cutoff_state_counts": [{"cutoff": cutoff, "state": label, "models": count} for (cutoff,label),count in sorted(cutoff_state_counts.items())],
        "inputs": inputs,
    }
    (args.output / 'independent_panel_events_results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with (args.output / 'independent_panel_events_differences.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['scope','model_key','time','column','expected','actual'])
        writer.writeheader()
        writer.writerows(differences)
    print(json.dumps(report['summary'], ensure_ascii=False))
    for result in checks:
        print(result['status'], result['name'], result['mismatch_count'])
    return 1 if report['summary']['fail'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
