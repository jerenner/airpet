import os
import tempfile
from unittest.mock import patch

from app import (
    app,
    compare_autosave_preflight_vs_latest_saved,
    compare_latest_preflight_versions,
    compare_preflight_summaries,
    compare_preflight_versions,
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
