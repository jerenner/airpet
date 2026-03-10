import os
import tempfile
from unittest.mock import patch

from app import (
    app,
    compare_autosave_preflight_vs_latest_saved,
    compare_autosave_preflight_vs_latest_snapshot,
    compare_autosave_preflight_vs_manual_saved_for_simulation_run,
    compare_autosave_preflight_vs_manual_saved_for_simulation_run_index,
    compare_autosave_preflight_vs_manual_saved_index,
    compare_autosave_preflight_vs_previous_manual_saved,
    compare_autosave_preflight_vs_previous_snapshot,
    compare_autosave_preflight_vs_saved_version,
    compare_autosave_preflight_vs_snapshot_version,
    compare_autosave_snapshot_preflight_versions,
    compare_latest_autosave_snapshot_preflight_versions,
    compare_latest_preflight_versions,
    compare_preflight_summaries,
    compare_preflight_versions,
    compare_manual_preflight_versions_for_simulation_run_indices,
    list_manual_saved_versions_for_simulation_run,
    list_preflight_versions,
)
from src.project_manager import ProjectManager
from src.expression_evaluator import ExpressionEvaluator


def _make_pm():
    evaluator = ExpressionEvaluator()
    pm = ProjectManager(evaluator)
    pm.create_empty_project()
    return pm


def test_preflight_default_project_can_run():
    pm = _make_pm()
    report = pm.run_preflight_checks()

    assert report['summary']['can_run'] is True
    assert report['summary']['errors'] == 0


def test_preflight_detects_unknown_material_reference():
    pm = _make_pm()
    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'CustomMissingMaterial'

    report = pm.run_preflight_checks()

    codes = [i['code'] for i in report['issues']]
    assert 'unknown_material_reference' in codes
    assert report['summary']['can_run'] is False


def test_preflight_detects_missing_world_volume_reference():
    pm = _make_pm()
    pm.current_geometry_state.world_volume_ref = ''

    report = pm.run_preflight_checks()

    codes = [i['code'] for i in report['issues']]
    assert 'missing_world_volume_reference' in codes
    assert report['summary']['can_run'] is False


def test_preflight_detects_unknown_world_volume_reference():
    pm = _make_pm()
    pm.current_geometry_state.world_volume_ref = 'MissingWorldLV'

    report = pm.run_preflight_checks()

    codes = [i['code'] for i in report['issues']]
    assert 'unknown_world_volume_reference' in codes
    assert report['summary']['can_run'] is False


def test_preflight_detects_unknown_placement_volume_reference():
    pm = _make_pm()
    pm.current_geometry_state.logical_volumes['World'].content[0].volume_ref = 'MissingPlacedRef'

    report = pm.run_preflight_checks()

    codes = [i['code'] for i in report['issues']]
    assert 'unknown_placement_volume_reference' in codes
    assert report['summary']['can_run'] is False


def test_preflight_detects_world_volume_referenced_as_child():
    pm = _make_pm()
    pm.current_geometry_state.logical_volumes['World'].content[0].volume_ref = 'World'

    report = pm.run_preflight_checks()

    codes = [i['code'] for i in report['issues']]
    assert 'world_volume_referenced_as_child' in codes
    assert report['summary']['can_run'] is False


def test_preflight_detects_logical_volume_placement_cycle():
    pm = _make_pm()

    loop_a, err = pm.add_logical_volume('loop_a_LV', 'box_solid', 'G4_Galactic')
    assert err is None
    loop_b, err = pm.add_logical_volume('loop_b_LV', 'box_solid', 'G4_Galactic')
    assert err is None

    _, err = pm.add_physical_volume(
        loop_a['name'],
        'loop_a_to_b',
        loop_b['name'],
        {'x': '0', 'y': '0', 'z': '0'},
        {'x': '0', 'y': '0', 'z': '0'},
        {'x': '1', 'y': '1', 'z': '1'},
    )
    assert err is None

    _, err = pm.add_physical_volume(
        loop_b['name'],
        'loop_b_to_a',
        loop_a['name'],
        {'x': '0', 'y': '0', 'z': '0'},
        {'x': '0', 'y': '0', 'z': '0'},
        {'x': '1', 'y': '1', 'z': '1'},
    )
    assert err is None

    report = pm.run_preflight_checks()

    cycle_issues = [i for i in report['issues'] if i['code'] == 'placement_hierarchy_cycle']
    assert cycle_issues
    assert any(f"LV:{loop_a['name']}" in issue['message'] for issue in cycle_issues)
    assert any(f"LV:{loop_b['name']}" in issue['message'] for issue in cycle_issues)
    assert report['summary']['can_run'] is False


def test_preflight_detects_lv_assembly_placement_cycle():
    pm = _make_pm()

    loop_lv, err = pm.add_logical_volume('loop_lv', 'box_solid', 'G4_Galactic')
    assert err is None
    loop_asm, err = pm.add_assembly('loop_asm', [])
    assert err is None

    ok, err = pm.update_assembly(
        loop_asm['name'],
        [
            {
                'name': 'loop_asm_to_lv',
                'volume_ref': loop_lv['name'],
                'parent_lv_name': loop_asm['name'],
                'position': {'x': '0', 'y': '0', 'z': '0'},
                'rotation': {'x': '0', 'y': '0', 'z': '0'},
                'scale': {'x': '1', 'y': '1', 'z': '1'},
            }
        ],
    )
    assert ok is True
    assert err is None

    _, err = pm.add_physical_volume(
        loop_lv['name'],
        'loop_lv_to_asm',
        loop_asm['name'],
        {'x': '0', 'y': '0', 'z': '0'},
        {'x': '0', 'y': '0', 'z': '0'},
        {'x': '1', 'y': '1', 'z': '1'},
    )
    assert err is None

    report = pm.run_preflight_checks()

    cycle_issues = [i for i in report['issues'] if i['code'] == 'placement_hierarchy_cycle']
    assert cycle_issues
    assert any(f"LV:{loop_lv['name']}" in issue['message'] for issue in cycle_issues)
    assert any(f"ASM:{loop_asm['name']}" in issue['message'] for issue in cycle_issues)
    assert report['summary']['can_run'] is False


def test_preflight_flags_tiny_dimensions_warning():
    pm = _make_pm()
    pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'

    report = pm.run_preflight_checks()

    codes = [i['code'] for i in report['issues']]
    assert 'tiny_dimension' in codes


def test_preflight_flags_possible_overlap_warning():
    pm = _make_pm()
    # Add a second copy of the same volume at the same location to trigger overlap heuristic.
    pm.add_physical_volume(
        'World',
        'box_PV_overlap',
        'box_LV',
        {'x': '0', 'y': '0', 'z': '0'},
        {'x': '0', 'y': '0', 'z': '0'},
        {'x': '1', 'y': '1', 'z': '1'},
    )

    report = pm.run_preflight_checks()
    codes = [i['code'] for i in report['issues']]
    assert 'possible_overlap_aabb' in codes


def test_simulation_run_is_blocked_when_preflight_has_errors():
    app.config['TESTING'] = True
    with app.test_client() as client:
        pm = _make_pm()
        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'

        with patch('app.get_project_manager_for_session', return_value=pm), \
             patch('app.os.path.exists', return_value=True):
            resp = client.post('/api/simulation/run', json={'events': 10, 'threads': 1})

        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'preflight_report' in data
        assert data['preflight_report']['summary']['can_run'] is False


def test_preflight_route_returns_report():
    app.config['TESTING'] = True
    with app.test_client() as client:
        pm = _make_pm()
        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/check', json={})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'preflight_report' in data
        assert 'summary' in data['preflight_report']


def test_preflight_summary_includes_deterministic_metadata():
    pm = _make_pm()
    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'CustomMissingMaterial'
    pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'

    report = pm.run_preflight_checks()
    summary = report['summary']

    assert summary['issue_count'] == len(report['issues'])
    assert isinstance(summary['issue_fingerprint'], str)
    assert len(summary['issue_fingerprint']) == 64

    keys = list(summary['counts_by_code'].keys())
    assert keys == sorted(keys)


def test_preflight_issue_fingerprint_is_order_independent():
    pm = _make_pm()

    report_a = {
        'issues': [
            {
                'severity': 'warning',
                'code': 'tiny_dimension',
                'message': 'tiny',
                'object_refs': ['box_solid'],
            },
            {
                'severity': 'error',
                'code': 'unknown_material_reference',
                'message': 'unknown material',
                'object_refs': ['box_LV', 'MissingMat'],
                'hint': 'Use a valid material',
            },
        ]
    }

    report_b = {
        'issues': list(reversed(report_a['issues']))
    }

    fingerprint_a = pm._preflight_finalize(report_a)['summary']['issue_fingerprint']
    fingerprint_b = pm._preflight_finalize(report_b)['summary']['issue_fingerprint']

    assert fingerprint_a == fingerprint_b



def test_compare_preflight_summaries_tracks_added_and_resolved_codes():
    baseline_summary = {
        'can_run': False,
        'issue_count': 4,
        'counts_by_code': {
            'tiny_dimension': 3,
            'unknown_material_reference': 1,
        },
        'issue_fingerprint': 'a' * 64,
    }
    candidate_summary = {
        'can_run': True,
        'issue_count': 5,
        'counts_by_code': {
            'tiny_dimension': 1,
            'possible_overlap_aabb': 4,
        },
        'issue_fingerprint': 'b' * 64,
    }

    comparison = compare_preflight_summaries(baseline_summary, candidate_summary)

    assert comparison['issue_count_delta'] == 1
    assert comparison['added_issue_codes'] == ['possible_overlap_aabb']
    assert comparison['resolved_issue_codes'] == ['unknown_material_reference']
    assert comparison['added_counts_by_code']['possible_overlap_aabb'] == 4
    assert comparison['resolved_counts_by_code']['unknown_material_reference'] == 1
    assert comparison['reduced_counts_by_code']['tiny_dimension'] == 2
    assert comparison['status']['improved_can_run'] is True
    assert comparison['status']['regressed_can_run'] is False
    assert comparison['status']['fingerprint_changed'] is True



def test_preflight_compare_summaries_route_accepts_report_wrappers():
    app.config['TESTING'] = True
    with app.test_client() as client:
        payload = {
            'baseline_report': {
                'summary': {
                    'can_run': False,
                    'issue_count': 1,
                    'counts_by_code': {'unknown_material_reference': 1},
                    'issue_fingerprint': '1' * 64,
                }
            },
            'candidate_report': {
                'summary': {
                    'can_run': True,
                    'issue_count': 0,
                    'counts_by_code': {},
                    'issue_fingerprint': '2' * 64,
                }
            },
        }

        resp = client.post('/api/preflight/compare_summaries', json=payload)

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    comparison = data['comparison']
    assert comparison['resolved_issue_codes'] == ['unknown_material_reference']
    assert comparison['status']['improved_can_run'] is True


def test_compare_preflight_versions_runs_checks_for_two_saved_versions():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_compare_project'

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        baseline_version_id, _ = pm.save_project_version('baseline_preflight')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'G4_Galactic'
        pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
        pm.recalculate_geometry_state()
        candidate_version_id, _ = pm.save_project_version('candidate_preflight')

        result = compare_preflight_versions(pm, baseline_version_id, candidate_version_id)

    assert result['baseline_version_id'] == baseline_version_id
    assert result['candidate_version_id'] == candidate_version_id
    assert result['comparison']['resolved_issue_codes'] == ['unknown_material_reference']
    assert result['comparison']['added_issue_codes'] == ['tiny_dimension']
    assert result['comparison']['status']['improved_can_run'] is True


def test_compare_latest_preflight_versions_uses_latest_two_saved_versions():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_latest_compare_project'

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        _, _ = pm.save_project_version('a_old_baseline')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'G4_Galactic'
        pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
        pm.recalculate_geometry_state()
        mid_version_id, _ = pm.save_project_version('b_mid_warning')

        pm.add_physical_volume(
            'World',
            'box_PV_overlap_latest',
            'box_LV',
            {'x': '0', 'y': '0', 'z': '0'},
            {'x': '0', 'y': '0', 'z': '0'},
            {'x': '1', 'y': '1', 'z': '1'},
        )
        pm.recalculate_geometry_state()
        latest_version_id, _ = pm.save_project_version('c_latest_overlap')

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        result = compare_latest_preflight_versions(pm)

    assert result['baseline_version_id'] == mid_version_id
    assert result['candidate_version_id'] == latest_version_id
    assert result['comparison']['added_issue_codes'] == ['possible_overlap_aabb']
    assert result['selection']['strategy'] == 'latest_two_saved_versions'
    assert result['selection']['selected_version_ids'] == [latest_version_id, mid_version_id]


def test_compare_latest_preflight_versions_requires_two_saved_versions():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_latest_compare_missing'

        _, _ = pm.save_project_version('only_one')

        try:
            compare_latest_preflight_versions(pm)
            assert False, 'Expected compare_latest_preflight_versions to reject a single saved version.'
        except ValueError as exc:
            assert 'at least two saved versions' in str(exc)


def test_compare_autosave_preflight_vs_latest_saved_uses_latest_saved_baseline():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_compare_project'

        baseline_version_id, _ = pm.save_project_version('manual_baseline')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        result = compare_autosave_preflight_vs_latest_saved(pm)

    assert result['baseline_version_id'] == baseline_version_id
    assert result['candidate_version_id'] == 'autosave'
    assert result['comparison']['added_issue_codes'] == ['unknown_material_reference']
    assert result['comparison']['status']['regressed_can_run'] is True
    assert result['selection']['strategy'] == 'latest_autosave_vs_latest_saved'


def test_compare_autosave_preflight_vs_latest_saved_requires_autosave():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_missing'

        pm.save_project_version('manual_only')

        try:
            compare_autosave_preflight_vs_latest_saved(pm)
            assert False, 'Expected compare_autosave_preflight_vs_latest_saved to require autosave.'
        except FileNotFoundError as exc:
            assert 'autosave' in str(exc)


def test_compare_autosave_preflight_vs_previous_manual_saved_skips_snapshot_baselines():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_previous_manual_saved_project'

        previous_manual_saved_version_id, _ = pm.save_project_version('manual_previous_saved')
        pm.save_project_version('autosave_snapshot_latest_saved')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        result = compare_autosave_preflight_vs_previous_manual_saved(pm)

    assert result['baseline_version_id'] == previous_manual_saved_version_id
    assert result['candidate_version_id'] == 'autosave'
    assert 'unknown_material_reference' in result['comparison']['added_issue_codes']
    assert result['selection']['strategy'] == 'latest_autosave_vs_previous_manual_saved'
    assert result['selection']['previous_manual_saved_version_id'] == previous_manual_saved_version_id
    assert result['selection']['total_snapshot_versions'] == 1
    assert result['selection']['total_manual_saved_versions'] == 1


def test_compare_autosave_preflight_vs_previous_manual_saved_requires_non_snapshot_saved_version():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_previous_manual_saved_missing'

        pm.save_project_version('autosave_snapshot_only')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        try:
            compare_autosave_preflight_vs_previous_manual_saved(pm)
            assert False, 'Expected compare_autosave_preflight_vs_previous_manual_saved to require a non-snapshot saved version.'
        except ValueError as exc:
            assert 'manually saved non-snapshot version' in str(exc)


def test_compare_autosave_preflight_vs_manual_saved_index_selects_n_back_manual_version():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_manual_saved_index_project'

        oldest_manual_version_id, _ = pm.save_project_version('manual_oldest')
        target_manual_version_id, _ = pm.save_project_version('manual_target_n1')
        pm.save_project_version('autosave_snapshot_latest')
        latest_manual_version_id, _ = pm.save_project_version('manual_latest')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        result = compare_autosave_preflight_vs_manual_saved_index(pm, manual_saved_index=1)

    manual_sorted = sorted(
        [oldest_manual_version_id, target_manual_version_id, latest_manual_version_id],
        reverse=True,
    )
    assert result['baseline_version_id'] == manual_sorted[1]
    assert result['candidate_version_id'] == 'autosave'
    assert 'unknown_material_reference' in result['comparison']['added_issue_codes']
    assert result['selection']['strategy'] == 'latest_autosave_vs_manual_saved_index'
    assert result['selection']['manual_saved_index'] == 1
    assert result['selection']['selected_manual_saved_version_id'] == manual_sorted[1]
    assert result['selection']['total_snapshot_versions'] == 1
    assert result['selection']['total_manual_saved_versions'] == 3


def test_compare_autosave_preflight_vs_manual_saved_index_rejects_out_of_range_index():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_manual_saved_index_out_of_range'

        pm.save_project_version('manual_only')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        try:
            compare_autosave_preflight_vs_manual_saved_index(pm, manual_saved_index=1)
            assert False, 'Expected compare_autosave_preflight_vs_manual_saved_index to reject out-of-range index.'
        except ValueError as exc:
            assert 'out of range' in str(exc)



def test_compare_autosave_preflight_vs_manual_saved_for_simulation_run_selects_latest_matching_manual_version():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_manual_saved_for_run_project'

        simulation_run_id = 'job_abc123'

        oldest_matching_version_id, _ = pm.save_project_version('manual_run_match_oldest')
        os.makedirs(os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.save_project_version('autosave_snapshot_run_match')

        latest_matching_version_id, _ = pm.save_project_version('manual_run_match_latest')
        os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.save_project_version('manual_without_run_match')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        result = compare_autosave_preflight_vs_manual_saved_for_simulation_run(
            pm,
            simulation_run_id=simulation_run_id,
        )

    expected_latest_matching_id = sorted(
        [oldest_matching_version_id, latest_matching_version_id],
        reverse=True,
    )[0]

    assert result['baseline_version_id'] == expected_latest_matching_id
    assert result['candidate_version_id'] == 'autosave'
    assert 'unknown_material_reference' in result['comparison']['added_issue_codes']
    assert result['selection']['strategy'] == 'latest_autosave_vs_manual_saved_for_simulation_run'
    assert result['selection']['simulation_run_id'] == simulation_run_id
    assert result['selection']['selected_manual_saved_version_id'] == expected_latest_matching_id
    assert result['selection']['matching_manual_saved_version_ids'] == sorted(
        [oldest_matching_version_id, latest_matching_version_id],
        reverse=True,
    )
    assert result['selection']['total_matching_manual_saved_versions'] == 2


def test_compare_autosave_preflight_vs_manual_saved_for_simulation_run_index_selects_n_back_matching_manual_version():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_manual_saved_for_run_index_project'

        simulation_run_id = 'job_run_index_abc'

        oldest_matching_version_id, _ = pm.save_project_version('manual_run_index_oldest')
        os.makedirs(os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        target_matching_version_id, _ = pm.save_project_version('manual_run_index_target')
        os.makedirs(os.path.join(pm._get_version_dir(target_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.save_project_version('autosave_snapshot_run_index')

        latest_matching_version_id, _ = pm.save_project_version('manual_run_index_latest')
        os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.save_project_version('manual_run_index_non_match')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        result = compare_autosave_preflight_vs_manual_saved_for_simulation_run_index(
            pm,
            simulation_run_id=simulation_run_id,
            manual_saved_index=1,
        )

    matching_sorted = sorted(
        [oldest_matching_version_id, target_matching_version_id, latest_matching_version_id],
        reverse=True,
    )
    assert result['baseline_version_id'] == matching_sorted[1]
    assert result['candidate_version_id'] == 'autosave'
    assert 'unknown_material_reference' in result['comparison']['added_issue_codes']
    assert result['selection']['strategy'] == 'latest_autosave_vs_manual_saved_for_simulation_run_index'
    assert result['selection']['simulation_run_id'] == simulation_run_id
    assert result['selection']['manual_saved_index'] == 1
    assert result['selection']['selected_manual_saved_version_id'] == matching_sorted[1]
    assert result['selection']['matching_manual_saved_version_ids'] == matching_sorted
    assert result['selection']['total_matching_manual_saved_versions'] == 3


def test_compare_autosave_preflight_vs_manual_saved_for_simulation_run_index_rejects_out_of_range_index():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_manual_saved_for_run_index_invalid'

        simulation_run_id = 'job_run_index_missing'

        matching_version_id, _ = pm.save_project_version('manual_run_index_only')
        os.makedirs(os.path.join(pm._get_version_dir(matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.save_project_version('manual_run_index_other')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        try:
            compare_autosave_preflight_vs_manual_saved_for_simulation_run_index(
                pm,
                simulation_run_id=simulation_run_id,
                manual_saved_index=3,
            )
            assert False, 'Expected compare_autosave_preflight_vs_manual_saved_for_simulation_run_index to reject out-of-range index.'
        except ValueError as exc:
            assert 'out of range' in str(exc)
            assert 'simulation_run_id' in str(exc)


def test_list_manual_saved_versions_for_simulation_run_returns_newest_first_indexed_matches():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_list_manual_saved_for_run_project'

        simulation_run_id = 'job_list_run_match'

        oldest_matching_version_id, _ = pm.save_project_version('manual_list_oldest')
        os.makedirs(os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.save_project_version('autosave_snapshot_list_ignored')

        latest_matching_version_id, _ = pm.save_project_version('manual_list_latest')
        os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.save_project_version('manual_list_non_match')

        result = list_manual_saved_versions_for_simulation_run(
            pm,
            simulation_run_id=simulation_run_id,
        )

    matching_sorted = sorted(
        [oldest_matching_version_id, latest_matching_version_id],
        reverse=True,
    )

    assert result['project_name'] == 'preflight_list_manual_saved_for_run_project'
    assert result['simulation_run_id'] == simulation_run_id
    assert result['total_snapshot_versions'] == 1
    assert result['total_manual_saved_versions'] == 3
    assert result['total_matching_manual_saved_versions'] == 2
    assert result['returned_matching_manual_saved_versions'] == 2
    assert [entry['version_id'] for entry in result['matching_manual_saved_versions']] == matching_sorted
    assert [entry['manual_saved_index'] for entry in result['matching_manual_saved_versions']] == [0, 1]


def test_list_manual_saved_versions_for_simulation_run_applies_limit():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_list_manual_saved_for_run_limit'

        simulation_run_id = 'job_list_run_limit'

        old_match_id, _ = pm.save_project_version('manual_list_limit_old')
        os.makedirs(os.path.join(pm._get_version_dir(old_match_id), 'sim_runs', simulation_run_id), exist_ok=True)

        latest_match_id, _ = pm.save_project_version('manual_list_limit_latest')
        os.makedirs(os.path.join(pm._get_version_dir(latest_match_id), 'sim_runs', simulation_run_id), exist_ok=True)

        result = list_manual_saved_versions_for_simulation_run(
            pm,
            simulation_run_id=simulation_run_id,
            limit=1,
        )

    expected_latest = sorted([old_match_id, latest_match_id], reverse=True)[0]

    assert result['total_matching_manual_saved_versions'] == 2
    assert result['returned_matching_manual_saved_versions'] == 1
    assert result['matching_manual_saved_versions'][0]['manual_saved_index'] == 0
    assert result['matching_manual_saved_versions'][0]['version_id'] == expected_latest


def test_compare_autosave_preflight_vs_manual_saved_for_simulation_run_requires_matching_manual_version():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_manual_saved_for_run_missing'

        manual_version_id, _ = pm.save_project_version('manual_other_run')
        os.makedirs(os.path.join(pm._get_version_dir(manual_version_id), 'sim_runs', 'different_job'), exist_ok=True)

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        try:
            compare_autosave_preflight_vs_manual_saved_for_simulation_run(
                pm,
                simulation_run_id='missing_job',
            )
            assert False, 'Expected compare_autosave_preflight_vs_manual_saved_for_simulation_run to require a matching run id.'
        except ValueError as exc:
            assert 'simulation_run_id' in str(exc)
            assert 'No manually saved non-snapshot versions' in str(exc)


def test_compare_manual_preflight_versions_for_simulation_run_indices_selects_requested_matching_versions():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_compare_manual_for_run_indices_project'

        simulation_run_id = 'job_manual_compare_indices'

        oldest_matching_version_id, _ = pm.save_project_version('manual_compare_oldest')
        os.makedirs(os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
        pm.recalculate_geometry_state()
        target_baseline_version_id, _ = pm.save_project_version('manual_compare_baseline_target')
        os.makedirs(os.path.join(pm._get_version_dir(target_baseline_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()
        latest_matching_version_id, _ = pm.save_project_version('manual_compare_candidate_latest')
        os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.save_project_version('manual_compare_non_match')

        result = compare_manual_preflight_versions_for_simulation_run_indices(
            pm,
            simulation_run_id=simulation_run_id,
            baseline_manual_saved_index=1,
            candidate_manual_saved_index=0,
        )

    matching_sorted = sorted(
        [oldest_matching_version_id, target_baseline_version_id, latest_matching_version_id],
        reverse=True,
    )

    assert result['baseline_version_id'] == matching_sorted[1]
    assert result['candidate_version_id'] == matching_sorted[0]
    assert isinstance(result['comparison']['counts_delta_by_code'], dict)
    assert result['selection']['strategy'] == 'manual_saved_versions_for_simulation_run_indices'
    assert result['selection']['simulation_run_id'] == simulation_run_id
    assert result['selection']['baseline_manual_saved_index'] == 1
    assert result['selection']['candidate_manual_saved_index'] == 0
    assert result['selection']['matching_manual_saved_version_ids'] == matching_sorted


def test_compare_manual_preflight_versions_for_simulation_run_indices_rejects_same_indices():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_compare_manual_for_run_indices_same_index'

        simulation_run_id = 'job_manual_compare_same_index'

        old_matching_version_id, _ = pm.save_project_version('manual_compare_same_old')
        os.makedirs(os.path.join(pm._get_version_dir(old_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        latest_matching_version_id, _ = pm.save_project_version('manual_compare_same_latest')
        os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        try:
            compare_manual_preflight_versions_for_simulation_run_indices(
                pm,
                simulation_run_id=simulation_run_id,
                baseline_manual_saved_index=0,
                candidate_manual_saved_index=0,
            )
            assert False, 'Expected compare_manual_preflight_versions_for_simulation_run_indices to reject identical indices.'
        except ValueError as exc:
            assert 'must be different' in str(exc)


def test_compare_autosave_preflight_vs_saved_version_uses_requested_saved_baseline():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_selected_compare_project'

        requested_saved_version_id, _ = pm.save_project_version('manual_requested')

        pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
        pm.recalculate_geometry_state()
        pm.save_project_version('manual_latest')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        result = compare_autosave_preflight_vs_saved_version(pm, requested_saved_version_id)

    assert result['baseline_version_id'] == requested_saved_version_id
    assert result['candidate_version_id'] == 'autosave'
    assert 'unknown_material_reference' in result['comparison']['added_issue_codes']
    assert result['selection']['strategy'] == 'latest_autosave_vs_selected_saved_version'
    assert result['selection']['saved_version_id'] == requested_saved_version_id


def test_compare_autosave_preflight_vs_saved_version_requires_saved_version_id():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_selected_missing_id'

        pm.save_project_version('manual_only')

        try:
            compare_autosave_preflight_vs_saved_version(pm, saved_version_id=None)
            assert False, 'Expected compare_autosave_preflight_vs_saved_version to require saved_version_id.'
        except ValueError as exc:
            assert 'saved_version_id' in str(exc)


def test_compare_autosave_preflight_vs_snapshot_version_uses_requested_snapshot_baseline():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_snapshot_compare_project'

        requested_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_manual_requested')

        pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
        pm.recalculate_geometry_state()
        pm.save_project_version('manual_latest')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        result = compare_autosave_preflight_vs_snapshot_version(pm, requested_snapshot_version_id)

    assert result['baseline_version_id'] == requested_snapshot_version_id
    assert result['candidate_version_id'] == 'autosave'
    assert 'unknown_material_reference' in result['comparison']['added_issue_codes']
    assert result['selection']['strategy'] == 'latest_autosave_vs_selected_autosave_snapshot'
    assert result['selection']['autosave_snapshot_version_id'] == requested_snapshot_version_id


def test_compare_autosave_preflight_vs_snapshot_version_rejects_non_snapshot_version():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_snapshot_invalid_version'

        manual_version_id, _ = pm.save_project_version('manual_only')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        try:
            compare_autosave_preflight_vs_snapshot_version(pm, manual_version_id)
            assert False, 'Expected compare_autosave_preflight_vs_snapshot_version to reject non-snapshot version ids.'
        except ValueError as exc:
            assert 'autosave snapshot' in str(exc)


def test_compare_autosave_preflight_vs_latest_snapshot_uses_most_recent_snapshot_baseline():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_latest_snapshot_project'

        pm.save_project_version('autosave_snapshot_old')
        latest_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_new')
        pm.save_project_version('manual_latest_not_snapshot')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        result = compare_autosave_preflight_vs_latest_snapshot(pm)

    assert result['baseline_version_id'] == latest_snapshot_version_id
    assert result['candidate_version_id'] == 'autosave'
    assert 'unknown_material_reference' in result['comparison']['added_issue_codes']
    assert result['selection']['strategy'] == 'latest_autosave_vs_latest_autosave_snapshot'
    assert result['selection']['autosave_snapshot_version_id'] == latest_snapshot_version_id
    assert result['selection']['total_snapshot_versions'] == 2


def test_compare_autosave_preflight_vs_latest_snapshot_requires_snapshot_version():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_latest_snapshot_missing'

        pm.save_project_version('manual_only')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        try:
            compare_autosave_preflight_vs_latest_snapshot(pm)
            assert False, 'Expected compare_autosave_preflight_vs_latest_snapshot to require at least one snapshot version.'
        except ValueError as exc:
            assert 'at least one saved autosave snapshot version' in str(exc)


def test_compare_autosave_preflight_vs_previous_snapshot_uses_previous_snapshot_baseline():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_previous_snapshot_project'

        pm.save_project_version('autosave_snapshot_old')
        previous_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_previous')
        pm.save_project_version('autosave_snapshot_latest')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        result = compare_autosave_preflight_vs_previous_snapshot(pm)

    assert result['baseline_version_id'] == previous_snapshot_version_id
    assert result['candidate_version_id'] == 'autosave'
    assert 'unknown_material_reference' in result['comparison']['added_issue_codes']
    assert result['selection']['strategy'] == 'latest_autosave_vs_previous_autosave_snapshot'
    assert result['selection']['previous_snapshot_version_id'] == previous_snapshot_version_id
    assert result['selection']['total_snapshot_versions'] == 3


def test_compare_autosave_preflight_vs_previous_snapshot_requires_two_snapshots():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_autosave_previous_snapshot_missing'

        pm.save_project_version('autosave_snapshot_only')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        try:
            compare_autosave_preflight_vs_previous_snapshot(pm)
            assert False, 'Expected compare_autosave_preflight_vs_previous_snapshot to require at least two snapshot versions.'
        except ValueError as exc:
            assert 'at least two saved autosave snapshot versions' in str(exc)


def test_compare_autosave_snapshot_preflight_versions_uses_requested_snapshots():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_snapshot_to_snapshot_project'

        baseline_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_baseline')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()
        candidate_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_candidate')

        result = compare_autosave_snapshot_preflight_versions(
            pm,
            baseline_snapshot_version_id=baseline_snapshot_version_id,
            candidate_snapshot_version_id=candidate_snapshot_version_id,
        )

    assert result['baseline_version_id'] == baseline_snapshot_version_id
    assert result['candidate_version_id'] == candidate_snapshot_version_id
    assert result['comparison']['added_issue_codes'] == ['unknown_material_reference']
    assert result['selection']['strategy'] == 'selected_autosave_snapshot_versions'
    assert result['selection']['selected_version_ids'] == [candidate_snapshot_version_id, baseline_snapshot_version_id]
    assert result['selection']['total_snapshot_versions'] == 2


def test_compare_autosave_snapshot_preflight_versions_rejects_non_snapshot_version():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_snapshot_to_snapshot_invalid'

        baseline_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_baseline')
        manual_version_id, _ = pm.save_project_version('manual_candidate')

        try:
            compare_autosave_snapshot_preflight_versions(
                pm,
                baseline_snapshot_version_id=baseline_snapshot_version_id,
                candidate_snapshot_version_id=manual_version_id,
            )
            assert False, 'Expected compare_autosave_snapshot_preflight_versions to reject non-snapshot version ids.'
        except ValueError as exc:
            assert 'candidate_snapshot_version_id' in str(exc)
            assert 'autosave snapshot' in str(exc)


def test_compare_latest_autosave_snapshot_preflight_versions_uses_latest_two_snapshots():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_latest_snapshot_versions_project'

        pm.save_project_version('autosave_snapshot_old')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()
        latest_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_new')

        result = compare_latest_autosave_snapshot_preflight_versions(pm)

    assert result['baseline_version_id'] != result['candidate_version_id']
    assert result['candidate_version_id'] == latest_snapshot_version_id
    assert result['comparison']['added_issue_codes'] == ['unknown_material_reference']
    assert result['selection']['strategy'] == 'latest_two_autosave_snapshot_versions'
    assert result['selection']['total_snapshot_versions'] == 2


def test_compare_latest_autosave_snapshot_preflight_versions_requires_two_snapshots():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_latest_snapshot_versions_missing'

        pm.save_project_version('autosave_snapshot_only')

        try:
            compare_latest_autosave_snapshot_preflight_versions(pm)
            assert False, 'Expected compare_latest_autosave_snapshot_preflight_versions to require at least two snapshot versions.'
        except ValueError as exc:
            assert 'at least two saved autosave snapshot versions' in str(exc)


def test_list_preflight_versions_returns_autosave_and_saved_metadata():
    pm = _make_pm()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm.projects_dir = tmpdir
        pm.project_name = 'preflight_version_list_project'

        first_version_id, _ = pm.save_project_version('manual_old')
        second_version_id, _ = pm.save_project_version('autosave_snapshot_manual_newer')

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        result = list_preflight_versions(pm)

    assert result['project_name'] == 'preflight_version_list_project'
    assert result['has_autosave'] is True
    assert result['total_versions'] == 3
    assert result['returned_versions'] == 3

    versions = result['versions']
    assert versions[0]['version_id'] == 'autosave'
    assert versions[0]['is_autosave'] is True

    manual_ids = [entry['version_id'] for entry in versions[1:]]
    assert manual_ids == sorted([first_version_id, second_version_id], reverse=True)

    snapshot_entry = next(entry for entry in versions if entry['version_id'] == second_version_id)
    assert snapshot_entry['is_autosave_snapshot'] is True


def test_preflight_list_versions_route_supports_limit_and_include_autosave_toggle():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_preflight_version_list_project'

        pm.save_project_version('manual_old')
        pm.save_project_version('manual_new')

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/list_versions', json={
                'project_name': pm.project_name,
                'include_autosave': False,
                'limit': 1,
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['has_autosave'] is False
    assert data['returned_versions'] == 1
    assert data['versions'][0]['is_autosave'] is False


def test_preflight_list_versions_route_rejects_negative_limit():
    app.config['TESTING'] = True
    with app.test_client() as client:
        pm = _make_pm()
        pm.project_name = 'route_preflight_version_list_invalid_limit'

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/list_versions', json={
                'project_name': pm.project_name,
                'limit': -1,
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'limit' in data['error']


def test_preflight_list_manual_saved_versions_for_simulation_run_route_returns_indexed_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_list_manual_saved_for_run_project'

        simulation_run_id = 'job_route_list_match'

        oldest_matching_version_id, _ = pm.save_project_version('manual_route_list_old')
        os.makedirs(os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        latest_matching_version_id, _ = pm.save_project_version('manual_route_list_latest')
        os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/list_manual_saved_versions_for_simulation_run', json={
                'project_name': pm.project_name,
                'job_id': simulation_run_id,
                'count': 1,
            })

    expected_latest = sorted([oldest_matching_version_id, latest_matching_version_id], reverse=True)[0]

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['simulation_run_id'] == simulation_run_id
    assert data['total_matching_manual_saved_versions'] == 2
    assert data['returned_matching_manual_saved_versions'] == 1
    assert data['matching_manual_saved_versions'][0]['manual_saved_index'] == 0
    assert data['matching_manual_saved_versions'][0]['version_id'] == expected_latest


def test_preflight_list_manual_saved_versions_for_simulation_run_route_rejects_invalid_limit():
    app.config['TESTING'] = True
    with app.test_client() as client:
        pm = _make_pm()
        pm.project_name = 'route_list_manual_saved_for_run_invalid_limit'

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/list_manual_saved_versions_for_simulation_run', json={
                'project_name': pm.project_name,
                'simulation_run_id': 'job_route_invalid_limit',
                'limit': -1,
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'limit' in data['error']


def test_preflight_compare_manual_saved_versions_for_simulation_run_indices_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_manual_for_run_indices_project'

        simulation_run_id = 'job_route_manual_compare'

        oldest_matching_version_id, _ = pm.save_project_version('manual_route_compare_oldest')
        os.makedirs(os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
        pm.recalculate_geometry_state()
        target_baseline_version_id, _ = pm.save_project_version('manual_route_compare_baseline_target')
        os.makedirs(os.path.join(pm._get_version_dir(target_baseline_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()
        latest_matching_version_id, _ = pm.save_project_version('manual_route_compare_candidate_latest')
        os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_manual_saved_versions_for_simulation_run_indices', json={
                'project_name': pm.project_name,
                'run_id': simulation_run_id,
                'baseline_n_back': 1,
                'candidate_n_back': 0,
            })

    matching_sorted = sorted(
        [oldest_matching_version_id, target_baseline_version_id, latest_matching_version_id],
        reverse=True,
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['baseline_version_id'] == matching_sorted[1]
    assert data['candidate_version_id'] == matching_sorted[0]
    assert data['selection']['strategy'] == 'manual_saved_versions_for_simulation_run_indices'
    assert data['selection']['baseline_manual_saved_index'] == 1
    assert data['selection']['candidate_manual_saved_index'] == 0


def test_preflight_compare_manual_saved_versions_for_simulation_run_indices_route_rejects_identical_indices():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_manual_for_run_indices_same_index'

        simulation_run_id = 'job_route_manual_compare_same_index'

        old_matching_version_id, _ = pm.save_project_version('manual_route_compare_same_old')
        os.makedirs(os.path.join(pm._get_version_dir(old_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        latest_matching_version_id, _ = pm.save_project_version('manual_route_compare_same_latest')
        os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_manual_saved_versions_for_simulation_run_indices', json={
                'project_name': pm.project_name,
                'simulation_run_id': simulation_run_id,
                'baseline_manual_saved_index': 0,
                'candidate_manual_saved_index': 0,
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'must be different' in data['error']


def test_preflight_compare_versions_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_project'

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        baseline_version_id, _ = pm.save_project_version('baseline_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'G4_Galactic'
        pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
        pm.recalculate_geometry_state()
        candidate_version_id, _ = pm.save_project_version('candidate_route')

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_versions', json={
                'baseline_version_id': baseline_version_id,
                'candidate_version_id': candidate_version_id,
                'project_name': pm.project_name,
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['comparison']['resolved_issue_codes'] == ['unknown_material_reference']
    assert data['comparison']['added_issue_codes'] == ['tiny_dimension']


def test_preflight_compare_latest_versions_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_latest_project'

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        _, _ = pm.save_project_version('a_old_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'G4_Galactic'
        pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
        pm.recalculate_geometry_state()
        baseline_version_id, _ = pm.save_project_version('b_mid_route')

        pm.add_physical_volume(
            'World',
            'box_PV_overlap_route',
            'box_LV',
            {'x': '0', 'y': '0', 'z': '0'},
            {'x': '0', 'y': '0', 'z': '0'},
            {'x': '1', 'y': '1', 'z': '1'},
        )
        pm.recalculate_geometry_state()
        candidate_version_id, _ = pm.save_project_version('c_latest_route')

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_latest_versions', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['baseline_version_id'] == baseline_version_id
    assert data['candidate_version_id'] == candidate_version_id
    assert data['comparison']['added_issue_codes'] == ['possible_overlap_aabb']


def test_preflight_compare_latest_versions_route_requires_two_versions():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_latest_missing'

        _, _ = pm.save_project_version('only_one')

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_latest_versions', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'at least two saved versions' in data['error']


def test_preflight_compare_autosave_vs_latest_saved_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_project'

        baseline_version_id, _ = pm.save_project_version('manual_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_latest_saved', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['baseline_version_id'] == baseline_version_id
    assert data['candidate_version_id'] == 'autosave'
    assert data['comparison']['added_issue_codes'] == ['unknown_material_reference']


def test_preflight_compare_autosave_vs_latest_saved_route_requires_autosave():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_missing'

        pm.save_project_version('manual_only')

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_latest_saved', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 404
    data = resp.get_json()
    assert data['success'] is False
    assert 'autosave' in data['error']


def test_preflight_compare_autosave_vs_previous_manual_saved_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_previous_manual_saved_project'

        previous_manual_saved_version_id, _ = pm.save_project_version('manual_previous_route')
        pm.save_project_version('autosave_snapshot_latest_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_previous_manual_saved', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['baseline_version_id'] == previous_manual_saved_version_id
    assert data['candidate_version_id'] == 'autosave'
    assert data['selection']['strategy'] == 'latest_autosave_vs_previous_manual_saved'


def test_preflight_compare_autosave_vs_previous_manual_saved_route_requires_non_snapshot_saved_version():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_previous_manual_saved_missing'

        pm.save_project_version('autosave_snapshot_only_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_previous_manual_saved', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'manually saved non-snapshot version' in data['error']


def test_preflight_compare_autosave_vs_manual_saved_index_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_manual_saved_index_project'

        oldest_manual_version_id, _ = pm.save_project_version('manual_oldest_route')
        target_manual_version_id, _ = pm.save_project_version('manual_target_route')
        pm.save_project_version('autosave_snapshot_latest_route')
        latest_manual_version_id, _ = pm.save_project_version('manual_latest_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_manual_saved_index', json={
                'project_name': pm.project_name,
                'n_back': 1,
            })

    assert resp.status_code == 200
    data = resp.get_json()
    manual_sorted = sorted(
        [oldest_manual_version_id, target_manual_version_id, latest_manual_version_id],
        reverse=True,
    )
    assert data['success'] is True
    assert data['baseline_version_id'] == manual_sorted[1]
    assert data['candidate_version_id'] == 'autosave'
    assert data['selection']['strategy'] == 'latest_autosave_vs_manual_saved_index'
    assert data['selection']['manual_saved_index'] == 1


def test_preflight_compare_autosave_vs_manual_saved_index_route_rejects_invalid_index():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_manual_saved_index_invalid'

        pm.save_project_version('manual_only_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_manual_saved_index', json={
                'project_name': pm.project_name,
                'manual_saved_index': 9,
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'out of range' in data['error']



def test_preflight_compare_autosave_vs_manual_saved_for_simulation_run_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_manual_saved_for_run_project'

        simulation_run_id = 'job_route_match'

        oldest_matching_version_id, _ = pm.save_project_version('manual_run_old_route')
        os.makedirs(os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.save_project_version('autosave_snapshot_route')

        latest_matching_version_id, _ = pm.save_project_version('manual_run_latest_route')
        os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.save_project_version('manual_without_run_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run', json={
                'project_name': pm.project_name,
                'run_id': simulation_run_id,
            })

    expected_latest_matching_id = sorted(
        [oldest_matching_version_id, latest_matching_version_id],
        reverse=True,
    )[0]

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['baseline_version_id'] == expected_latest_matching_id
    assert data['candidate_version_id'] == 'autosave'
    assert data['selection']['strategy'] == 'latest_autosave_vs_manual_saved_for_simulation_run'
    assert data['selection']['simulation_run_id'] == simulation_run_id


def test_preflight_compare_autosave_vs_manual_saved_for_simulation_run_index_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_manual_saved_for_run_index_project'

        simulation_run_id = 'job_route_index_match'

        oldest_matching_version_id, _ = pm.save_project_version('manual_run_index_old_route')
        os.makedirs(os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        target_matching_version_id, _ = pm.save_project_version('manual_run_index_target_route')
        os.makedirs(os.path.join(pm._get_version_dir(target_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.save_project_version('autosave_snapshot_route_index')

        latest_matching_version_id, _ = pm.save_project_version('manual_run_index_latest_route')
        os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index', json={
                'project_name': pm.project_name,
                'run_id': simulation_run_id,
                'n_back': 1,
            })

    matching_sorted = sorted(
        [oldest_matching_version_id, target_matching_version_id, latest_matching_version_id],
        reverse=True,
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['baseline_version_id'] == matching_sorted[1]
    assert data['candidate_version_id'] == 'autosave'
    assert data['selection']['strategy'] == 'latest_autosave_vs_manual_saved_for_simulation_run_index'
    assert data['selection']['simulation_run_id'] == simulation_run_id
    assert data['selection']['manual_saved_index'] == 1


def test_preflight_compare_autosave_vs_manual_saved_for_simulation_run_index_route_rejects_invalid_index():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_manual_saved_for_run_index_invalid'

        simulation_run_id = 'job_route_index_invalid'

        matching_version_id, _ = pm.save_project_version('manual_run_index_only_route')
        os.makedirs(os.path.join(pm._get_version_dir(matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index', json={
                'project_name': pm.project_name,
                'simulation_run_id': simulation_run_id,
                'manual_saved_index': 5,
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'out of range' in data['error']
    assert 'simulation_run_id' in data['error']


def test_preflight_compare_autosave_vs_manual_saved_for_simulation_run_route_requires_matching_manual_version():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_manual_saved_for_run_missing'

        manual_version_id, _ = pm.save_project_version('manual_other_run_route')
        os.makedirs(os.path.join(pm._get_version_dir(manual_version_id), 'sim_runs', 'other_job_route'), exist_ok=True)

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run', json={
                'project_name': pm.project_name,
                'simulation_run_id': 'missing_route_job',
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'simulation_run_id' in data['error']
    assert 'No manually saved non-snapshot versions' in data['error']


def test_preflight_compare_autosave_vs_saved_version_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_selected_project'

        requested_saved_version_id, _ = pm.save_project_version('manual_selected')

        pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
        pm.recalculate_geometry_state()
        pm.save_project_version('manual_latest')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_saved_version', json={
                'project_name': pm.project_name,
                'saved_version_id': requested_saved_version_id,
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['baseline_version_id'] == requested_saved_version_id
    assert data['candidate_version_id'] == 'autosave'
    assert 'unknown_material_reference' in data['comparison']['added_issue_codes']


def test_preflight_compare_autosave_vs_saved_version_route_requires_saved_version_id():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_selected_missing'

        pm.save_project_version('manual_only')

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_saved_version', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'saved_version_id' in data['error']


def test_preflight_compare_autosave_vs_snapshot_version_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_snapshot_project'

        requested_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_manual_selected_route')

        pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
        pm.recalculate_geometry_state()
        pm.save_project_version('manual_latest_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_snapshot_version', json={
                'project_name': pm.project_name,
                'snapshot_version_id': requested_snapshot_version_id,
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['baseline_version_id'] == requested_snapshot_version_id
    assert data['candidate_version_id'] == 'autosave'
    assert 'unknown_material_reference' in data['comparison']['added_issue_codes']


def test_preflight_compare_autosave_vs_snapshot_version_route_requires_snapshot_id():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_snapshot_missing'

        pm.save_project_version('autosave_snapshot_manual_only')

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_snapshot_version', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'autosave_snapshot_version_id' in data['error']


def test_preflight_compare_autosave_vs_latest_snapshot_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_latest_snapshot_project'

        pm.save_project_version('autosave_snapshot_old_route')
        latest_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_new_route')
        pm.save_project_version('manual_latest_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_latest_snapshot', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['baseline_version_id'] == latest_snapshot_version_id
    assert data['candidate_version_id'] == 'autosave'
    assert data['selection']['strategy'] == 'latest_autosave_vs_latest_autosave_snapshot'


def test_preflight_compare_autosave_vs_latest_snapshot_route_requires_snapshot_version():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_latest_snapshot_missing'

        pm.save_project_version('manual_only_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_latest_snapshot', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'at least one saved autosave snapshot version' in data['error']


def test_preflight_compare_autosave_vs_previous_snapshot_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_previous_snapshot_project'

        pm.save_project_version('autosave_snapshot_old_route')
        previous_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_previous_route')
        pm.save_project_version('autosave_snapshot_latest_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_previous_snapshot', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['baseline_version_id'] == previous_snapshot_version_id
    assert data['candidate_version_id'] == 'autosave'
    assert data['selection']['strategy'] == 'latest_autosave_vs_previous_autosave_snapshot'


def test_preflight_compare_autosave_vs_previous_snapshot_route_requires_two_snapshots():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_autosave_previous_snapshot_missing'

        pm.save_project_version('autosave_snapshot_only_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()

        autosave_dir = pm._get_version_dir('autosave')
        os.makedirs(autosave_dir, exist_ok=True)
        with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
            handle.write(pm.save_project_to_json_string())

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_autosave_vs_previous_snapshot', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'at least two saved autosave snapshot versions' in data['error']


def test_preflight_compare_snapshot_versions_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_snapshot_versions_project'

        baseline_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_baseline_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()
        candidate_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_candidate_route')

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_snapshot_versions', json={
                'project_name': pm.project_name,
                'baseline_version_id': baseline_snapshot_version_id,
                'candidate_snapshot_version_id': candidate_snapshot_version_id,
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['baseline_version_id'] == baseline_snapshot_version_id
    assert data['candidate_version_id'] == candidate_snapshot_version_id
    assert data['comparison']['added_issue_codes'] == ['unknown_material_reference']
    assert data['selection']['strategy'] == 'selected_autosave_snapshot_versions'


def test_preflight_compare_snapshot_versions_route_requires_both_snapshot_ids():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_snapshot_versions_missing'

        baseline_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_baseline_route')

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_snapshot_versions', json={
                'project_name': pm.project_name,
                'baseline_snapshot_version_id': baseline_snapshot_version_id,
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'candidate_snapshot_version_id' in data['error']


def test_preflight_compare_latest_snapshot_versions_route_returns_comparison_payload():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_latest_snapshot_versions_project'

        pm.save_project_version('autosave_snapshot_old_route')

        pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
        pm.recalculate_geometry_state()
        latest_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_new_route')

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_latest_snapshot_versions', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['candidate_version_id'] == latest_snapshot_version_id
    assert data['comparison']['added_issue_codes'] == ['unknown_material_reference']
    assert data['selection']['strategy'] == 'latest_two_autosave_snapshot_versions'


def test_preflight_compare_latest_snapshot_versions_route_requires_two_snapshots():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_compare_latest_snapshot_versions_missing'

        pm.save_project_version('autosave_snapshot_only_route')

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_latest_snapshot_versions', json={
                'project_name': pm.project_name,
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data['success'] is False
    assert 'at least two saved autosave snapshot versions' in data['error']


def test_preflight_compare_versions_route_returns_404_for_missing_version():
    app.config['TESTING'] = True
    with app.test_client() as client, tempfile.TemporaryDirectory() as tmpdir:
        pm = _make_pm()
        pm.projects_dir = tmpdir
        pm.project_name = 'route_missing_version'

        _, _ = pm.save_project_version('existing_version')

        with patch('app.get_project_manager_for_session', return_value=pm):
            resp = client.post('/api/preflight/compare_versions', json={
                'baseline_version_id': 'does_not_exist',
                'candidate_version_id': 'also_missing',
                'project_name': pm.project_name,
            })

    assert resp.status_code == 404
    data = resp.get_json()
    assert data['success'] is False
    assert 'not found' in data['error']
