from unittest.mock import patch

from app import app
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
