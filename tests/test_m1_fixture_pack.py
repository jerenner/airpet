import json
from pathlib import Path

from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager
from src.smart_cad_classifier import summarize_candidates


FIXTURE_DIR = Path(__file__).parent / 'fixtures' / 'm1'


def _make_pm():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    return pm


def _apply_mutation(pm, mutation):
    op = mutation.get('op')

    if op == 'set_lv_material':
        pm.current_geometry_state.logical_volumes[mutation['lv']].material_ref = mutation['value']
        return

    if op == 'set_lv_solid':
        pm.current_geometry_state.logical_volumes[mutation['lv']].solid_ref = mutation['value']
        return

    if op == 'set_solid_param':
        pm.current_geometry_state.solids[mutation['solid']].raw_parameters[mutation['param']] = mutation['value']
        return

    if op == 'duplicate_box_overlap':
        pm.add_physical_volume(
            'World',
            'box_PV_overlap_fixture',
            'box_LV',
            {'x': '0', 'y': '0', 'z': '0'},
            {'x': '0', 'y': '0', 'z': '0'},
            {'x': '1', 'y': '1', 'z': '1'},
        )
        return

    raise ValueError(f'Unknown fixture mutation op: {op}')


def test_smart_import_fixture_pack_summary_contract():
    fixture = json.loads((FIXTURE_DIR / 'smart_import_report_fixture.json').read_text())
    candidates = fixture['candidates']
    expected = fixture['expected_summary']

    summary = summarize_candidates(candidates)

    assert summary['total'] == expected['total']
    assert summary['primitive_count'] == expected['primitive_count']
    assert summary['tessellated_count'] == expected['tessellated_count']
    assert summary['selected_mode_counts']['primitive'] == expected['selected_mode_counts']['primitive']
    assert summary['selected_mode_counts']['tessellated'] == expected['selected_mode_counts']['tessellated']


def test_preflight_fixture_pack_cases():
    cases = json.loads((FIXTURE_DIR / 'preflight_cases.json').read_text())

    for case in cases:
        pm = _make_pm()
        for mutation in case.get('mutations', []):
            _apply_mutation(pm, mutation)

        report = pm.run_preflight_checks()
        codes = [issue['code'] for issue in report.get('issues', [])]

        assert report['summary']['can_run'] == case['expected']['can_run'], case['name']
        for expected_code in case['expected']['codes']:
            assert expected_code in codes, f"{case['name']}: missing expected code '{expected_code}'"
