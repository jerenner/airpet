import os
import pytest
from unittest.mock import MagicMock, patch
from flask import jsonify, session
from src.project_manager import ProjectManager
from src.expression_evaluator import ExpressionEvaluator
from src.geometry_types import DivisionVolume, ReplicaVolume
from app import dispatch_ai_tool, app as flask_app

@pytest.fixture
def pm():
    evaluator = ExpressionEvaluator()
    pm = ProjectManager(evaluator)
    pm.create_empty_project()
    return pm


def _build_multi_cycle_lv_triangle(pm):
    loop_a, err = pm.add_logical_volume('ai_trunc_cycle_a_lv', 'box_solid', 'G4_Galactic')
    assert err is None
    loop_b, err = pm.add_logical_volume('ai_trunc_cycle_b_lv', 'box_solid', 'G4_Galactic')
    assert err is None
    loop_c, err = pm.add_logical_volume('ai_trunc_cycle_c_lv', 'box_solid', 'G4_Galactic')
    assert err is None

    edges = [
        (loop_a['name'], loop_b['name']),
        (loop_a['name'], loop_c['name']),
        (loop_b['name'], loop_a['name']),
        (loop_b['name'], loop_c['name']),
        (loop_c['name'], loop_a['name']),
        (loop_c['name'], loop_b['name']),
    ]

    for idx, (parent_name, child_name) in enumerate(edges, start=1):
        _, err = pm.add_physical_volume(
            parent_name,
            f'ai_trunc_edge_{idx}',
            child_name,
            {'x': '0', 'y': '0', 'z': '0'},
            {'x': '0', 'y': '0', 'z': '0'},
            {'x': '1', 'y': '1', 'z': '1'},
        )
        assert err is None


def _assert_single_cycle_truncation_issue(issues):
    truncation_issues = [
        issue
        for issue in issues
        if issue['code'] == 'placement_hierarchy_cycle_report_truncated'
    ]
    assert len(truncation_issues) == 1
    assert truncation_issues[0]['message'] == (
        'Cycle reporting truncated at max_cycles=1; reported 1 cycle findings.'
    )
    assert truncation_issues[0]['metadata'] == {
        'max_cycles': 1,
        'reported_cycles': 1,
        'truncated': True,
    }


def _assert_compare_ai_selection_and_source_metadata(
    data,
    *,
    baseline_version_id,
    candidate_version_id,
    selection_ordering_basis=None,
):
    assert data['ordering_metadata']['ordering_basis'] == 'explicit_version_ids'

    baseline_source = data['version_sources']['baseline']
    candidate_source = data['version_sources']['candidate']

    assert baseline_source['version_id'] == baseline_version_id
    assert candidate_source['version_id'] == candidate_version_id

    for source in (baseline_source, candidate_source):
        assert source['version_json_exists'] is True
        assert source['version_json_mtime_utc'] is not None
        assert source['source_path_checks']['versions_root_exists'] is True
        assert source['source_path_checks']['version_dir_within_versions_root'] is True
        assert source['source_path_checks']['version_json_within_versions_root'] is True

    if selection_ordering_basis is not None:
        assert data['selection']['ordering_basis'] == selection_ordering_basis


def _assert_compare_ai_error_payload_excludes_success_metadata(data):
    assert data['success'] is False
    assert isinstance(data.get('error'), str)

    for field_name in (
        'baseline_version_id',
        'candidate_version_id',
        'baseline_report',
        'candidate_report',
        'comparison',
        'selection',
        'ordering_metadata',
        'version_sources',
    ):
        assert field_name not in data


def _assert_preflight_list_ai_error_payload_excludes_success_metadata(data):
    assert data['success'] is False
    assert isinstance(data.get('error'), str)

    for field_name in (
        'project_name',
        'simulation_run_id',
        'ordering_basis',
        'manual_saved_ordering_basis',
        'versions_root',
        'versions_root_exists',
        'total_versions',
        'returned_versions',
        'has_autosave',
        'versions',
        'ordered_manual_saved_version_ids',
        'total_saved_versions',
        'total_snapshot_versions',
        'total_manual_saved_versions',
        'total_matching_manual_saved_versions',
        'returned_matching_manual_saved_versions',
        'matching_manual_saved_versions',
    ):
        assert field_name not in data


def _call_preflight_route_with_pm(pm, route_path, payload):
    with patch('app.get_project_manager_for_session', return_value=pm):
        with flask_app.test_client() as client:
            resp = client.post(route_path, json=payload)
    return resp.status_code, resp.get_json()


def _seed_preflight_compare_route_ai_parity_fixture(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_route_compare_parity_project"

    simulation_run_id = "job_ai_route_compare_parity"

    oldest_matching_version_id, _ = pm.save_project_version('manual_ai_route_parity_old')
    os.makedirs(
        os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id),
        exist_ok=True,
    )

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()
    latest_matching_version_id, _ = pm.save_project_version('manual_ai_route_parity_latest')
    os.makedirs(
        os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id),
        exist_ok=True,
    )

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    return {
        'simulation_run_id': simulation_run_id,
        'oldest_matching_version_id': oldest_matching_version_id,
        'latest_matching_version_id': latest_matching_version_id,
    }


def _seed_preflight_compare_versions_error_parity_fixture(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_route_compare_versions_error_parity_project"

    baseline_version_id, _ = pm.save_project_version('manual_ai_route_compare_versions_baseline')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()
    candidate_version_id, _ = pm.save_project_version('manual_ai_route_compare_versions_candidate')

    return {
        'baseline_version_id': baseline_version_id,
        'candidate_version_id': candidate_version_id,
    }


def _seed_preflight_run_selector_stale_version_fixture(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_route_compare_parity_stale_selector_project"

    simulation_run_id = "job_ai_route_compare_stale_selector"

    oldest_matching_version_id, _ = pm.save_project_version('manual_ai_route_stale_a_old')
    os.makedirs(
        os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id),
        exist_ok=True,
    )

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()
    stale_selected_version_id, _ = pm.save_project_version('manual_ai_route_stale_z_latest')
    os.makedirs(
        os.path.join(pm._get_version_dir(stale_selected_version_id), 'sim_runs', simulation_run_id),
        exist_ok=True,
    )

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    os.remove(os.path.join(pm._get_version_dir(stale_selected_version_id), 'version.json'))

    return {
        'simulation_run_id': simulation_run_id,
        'oldest_matching_version_id': oldest_matching_version_id,
        'stale_selected_version_id': stale_selected_version_id,
    }

def _seed_preflight_snapshot_route_ai_parity_fixture(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_route_compare_snapshot_parity_project"

    requested_saved_version_id, _ = pm.save_project_version('manual_ai_route_saved_selected')
    baseline_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_ai_route_old')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()
    candidate_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_ai_route_new')

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    return {
        'requested_saved_version_id': requested_saved_version_id,
        'baseline_snapshot_version_id': baseline_snapshot_version_id,
        'candidate_snapshot_version_id': candidate_snapshot_version_id,
    }


def _seed_preflight_snapshot_insufficient_versions_fixture(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_route_compare_snapshot_parity_insufficient_project"

    only_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_ai_route_only')

    return {
        'only_snapshot_version_id': only_snapshot_version_id,
    }


def _seed_preflight_global_selector_route_ai_parity_fixture(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_route_global_selector_parity_project"

    manual_baseline_version_id, _ = pm.save_project_version('manual_ai_global_selector_baseline')

    pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
    pm.recalculate_geometry_state()
    manual_candidate_version_id, _ = pm.save_project_version('manual_ai_global_selector_candidate')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()
    snapshot_baseline_version_id, _ = pm.save_project_version('autosave_snapshot_ai_global_selector_baseline')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'G4_Galactic'
    pm.recalculate_geometry_state()
    snapshot_candidate_version_id, _ = pm.save_project_version('autosave_snapshot_ai_global_selector_candidate')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()
    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    return {
        'manual_baseline_version_id': manual_baseline_version_id,
        'manual_candidate_version_id': manual_candidate_version_id,
        'snapshot_baseline_version_id': snapshot_baseline_version_id,
        'snapshot_candidate_version_id': snapshot_candidate_version_id,
    }


def _seed_preflight_global_selector_stale_route_ai_parity_fixture(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_route_global_selector_stale_parity_project"

    active_manual_version_id, _ = pm.save_project_version('manual_ai_global_selector_active')
    stale_manual_version_id, _ = pm.save_project_version('manual_ai_global_selector_stale')
    active_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_ai_global_selector_active')
    stale_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_ai_global_selector_stale')

    os.remove(os.path.join(pm._get_version_dir(stale_manual_version_id), 'version.json'))
    os.remove(os.path.join(pm._get_version_dir(stale_snapshot_version_id), 'version.json'))

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()
    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    return {
        'active_manual_version_id': active_manual_version_id,
        'stale_manual_version_id': stale_manual_version_id,
        'active_snapshot_version_id': active_snapshot_version_id,
        'stale_snapshot_version_id': stale_snapshot_version_id,
    }


def _seed_preflight_corpus_missing_world_volume_reference(pm):
    pm.current_geometry_state.world_volume_ref = ''


def _seed_preflight_corpus_unknown_world_volume_reference(pm):
    pm.current_geometry_state.world_volume_ref = 'MissingWorldLV'


def _seed_preflight_corpus_bad_replica_reference_and_bounds(pm):
    container_lv = pm.current_geometry_state.logical_volumes['box_LV']
    container_lv.content_type = 'replica'
    container_lv.content = ReplicaVolume(
        name='bad_replica',
        volume_ref='MissingReplicaTarget',
        number='0',
        direction={'x': '0', 'y': '0', 'z': '0'},
        width='0',
        offset='0',
    )


def _seed_preflight_corpus_bad_division_axis_and_bounds(pm):
    child_lv, err = pm.add_logical_volume('division_child_lv', 'box_solid', 'G4_Galactic')
    assert err is None

    container_lv = pm.current_geometry_state.logical_volumes['box_LV']
    container_lv.content_type = 'division'
    container_lv.content = DivisionVolume(
        name='bad_division',
        volume_ref=child_lv['name'],
        axis='kBadAxis',
        number='0',
        width='0',
        offset='0',
        unit='mm',
    )


def _seed_preflight_corpus_logical_volume_cycle(pm):
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


def _save_seeded_preflight_corpus_version(pm, *, seed, description):
    pm.create_empty_project()
    seed(pm)
    version_id, message = pm.save_project_version(description)
    assert isinstance(version_id, str) and version_id
    assert isinstance(message, str) and message
    return version_id


def test_ai_tool_manage_define(pm):
    # Test creation
    res = dispatch_ai_tool(pm, "manage_define", {
        "name": "test_var",
        "define_type": "constant",
        "value": "123.45"
    })
    assert res['success']
    assert pm.current_geometry_state.defines['test_var'].value == 123.45

    # Test update
    res = dispatch_ai_tool(pm, "manage_define", {
        "name": "test_var",
        "define_type": "constant",
        "value": "500"
    })
    assert res['success']
    assert pm.current_geometry_state.defines['test_var'].value == 500

def test_ai_tool_create_primitive_solid(pm):
    res = dispatch_ai_tool(pm, "create_primitive_solid", {
        "name": "AI_Box",
        "solid_type": "box",
        "params": {"x": "50", "y": "50", "z": "50"}
    })
    assert res['success']
    assert "AI_Box" in pm.current_geometry_state.solids
    assert pm.current_geometry_state.solids["AI_Box"]._evaluated_parameters['x'] == 50


def test_ai_tool_create_tube_with_alias_params(pm):
    res = dispatch_ai_tool(pm, "create_primitive_solid", {
        "name": "AI_Tube_Alias",
        "solid_type": "tube",
        "params": {
            "innerRadius": "70",
            "outerRadius": "90",
            "halfZ": "50",
            "startAngle": "0",
            "spanAngle": "360"
        }
    })

    assert res['success'], res
    s = pm.current_geometry_state.solids["AI_Tube_Alias"]
    ep = s._evaluated_parameters
    assert ep['rmin'] == 70
    assert ep['rmax'] == 90
    assert ep['z'] == 50
    # 360 deg should map to 2*pi rad
    assert abs(ep['deltaphi'] - 6.283185307179586) < 1e-6


def test_ai_tool_create_tube_with_unit_suffix_and_camelcase(pm):
    res = dispatch_ai_tool(pm, "create_primitive_solid", {
        "name": "AI_Tube_Units",
        "solid_type": "tube",
        "params": {
            "rMin": "70 mm",
            "rMax": "90mm",
            "halfZ": "50mm",
            "startPhi": "0deg",
            "deltaPhi": "360deg"
        }
    })

    assert res['success'], res
    s = pm.current_geometry_state.solids["AI_Tube_Units"]
    ep = s._evaluated_parameters
    assert ep['rmin'] == 70
    assert ep['rmax'] == 90
    assert ep['z'] == 50
    assert abs(ep['deltaphi'] - 6.283185307179586) < 1e-6


def test_ai_tool_create_tube_missing_required_params_returns_repairable_error(pm):
    res = dispatch_ai_tool(pm, "create_primitive_solid", {
        "name": "BadTube",
        "solid_type": "tube",
        "params": {
            "outerRadius": "90"
        }
    })

    assert not res['success']
    assert "missing required param" in res['error']
    assert "rmin" in res['error']
    assert "rmax" in res['error']

def test_ai_tool_place_volume(pm):
    # Setup: Create a solid and LV first
    pm.add_solid("SmallBox", "box", {"x": "10", "y": "10", "z": "10"})
    pm.add_logical_volume("SmallLV", "SmallBox", "G4_Galactic")
    
    res = dispatch_ai_tool(pm, "place_volume", {
        "parent_lv_name": "World",
        "placed_lv_ref": "SmallLV",
        "name": "AI_Placement",
        "position": {"x": "100", "y": "0", "z": "0"}
    })
    
    assert res['success']
    world_lv = pm.current_geometry_state.logical_volumes["World"]
    assert any(pv.name == "AI_Placement" for pv in world_lv.content)

def test_ai_tool_delete_autodetect_type(pm):
    # Setup: Create a solid
    pm.add_solid("BoxToDelete", "box", {"x": "10", "y": "10", "z": "10"})
    assert "BoxToDelete" in pm.current_geometry_state.solids
    
    # Delete without specifying type
    res = dispatch_ai_tool(pm, "delete_objects", {
        "objects": [{"id": "BoxToDelete"}] # type is missing
    })
    assert res['success']
    assert "BoxToDelete" not in pm.current_geometry_state.solids

def test_ai_tool_delete_ring_macro(pm):
    # Setup: Create a ring
    pm.add_solid("RingCrystal", "box", {"x": "10", "y": "10", "z": "10"})
    pm.add_logical_volume("RingLV", "RingCrystal", "G4_Galactic")
    pm.create_detector_ring("World", "RingLV", "PET_Ring", num_detectors=8, radius=100, center={'x':0,'y':0,'z':0}, orientation={'x':0,'y':0,'z':0}, point_to_center=True, inward_axis='+x')
    
    # Delete via macro
    res = dispatch_ai_tool(pm, "delete_detector_ring", {"ring_name": "PET_Ring"})
    assert res['success']
    world_lv = pm.current_geometry_state.logical_volumes["World"]
    assert not any(pv.name == "PET_Ring" for pv in world_lv.content)

def test_ai_tool_set_appearance(pm):
    pm.add_solid("Box", "box", {"x": 10, "y": 10, "z": 10})
    pm.add_material("Lead", {"density_expr": "11.35", "Z_expr": "82"})
    pm.add_logical_volume("LeadLV", "Box", "Lead")
    
    res = dispatch_ai_tool(pm, "set_volume_appearance", {
        "name": "LeadLV",
        "color": "blue",
        "opacity": 0.5
    })
    assert res['success']
    lv = pm.current_geometry_state.logical_volumes["LeadLV"]
    assert lv.vis_attributes['color']['b'] == 1.0
    assert lv.vis_attributes['color']['a'] == 0.5

def test_ai_tool_search_components(pm):
    # Setup: Create some components
    pm.add_solid("DetectorBox", "box", {"x": "10", "y": "10", "z": "10"})
    pm.add_solid("ShieldingBox", "box", {"x": "100", "y": "100", "z": "100"})
    
    res = dispatch_ai_tool(pm, "search_components", {
        "component_type": "solid",
        "pattern": "Detector"
    })
    assert res['success']
    assert "DetectorBox" in res['results']
    assert "ShieldingBox" not in res['results']

def test_project_summary_context_string(pm):
    pm.add_solid("TestSolid", "box", {"x": 10, "y": 10, "z": 10})
    pm.add_material("Lead", {"density_expr": "11.35", "Z_expr": "82"})
    pm.add_logical_volume("TestLV", "TestSolid", "Lead")
    
    summary = pm.get_summarized_context()
    assert "World Volume: World" in summary
    assert "Materials: G4_Galactic, Lead" in summary
    assert "TestLV(TestSolid)" in summary

def test_ai_tool_run_preflight_checks_returns_report_and_summary(pm):
    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'

    res = dispatch_ai_tool(pm, "run_preflight_checks", {})

    assert res['success'] is True
    assert 'preflight_report' in res
    assert 'preflight_summary' in res
    summary = res['preflight_summary']
    assert summary['can_run'] is False
    assert summary['issue_count'] == len(res['preflight_report']['issues'])
    assert 'issue_fingerprint' in summary
    assert len(summary['issue_fingerprint']) == 64


def test_ai_tool_compare_preflight_summaries_returns_code_deltas(pm):
    baseline = {
        "can_run": False,
        "issue_count": 2,
        "counts_by_code": {
            "unknown_material_reference": 1,
            "tiny_dimension": 1,
        },
        "issue_fingerprint": "a" * 64,
    }
    candidate = {
        "can_run": True,
        "issue_count": 3,
        "counts_by_code": {
            "tiny_dimension": 2,
            "possible_overlap_aabb": 1,
        },
        "issue_fingerprint": "b" * 64,
    }

    res = dispatch_ai_tool(pm, "compare_preflight_summaries", {
        "before_summary": baseline,
        "after_summary": candidate,
    })

    assert res["success"] is True
    comparison = res["comparison"]
    assert comparison["added_issue_codes"] == ["possible_overlap_aabb"]
    assert comparison["resolved_issue_codes"] == ["unknown_material_reference"]
    assert comparison["increased_issue_codes"] == ["tiny_dimension"]
    assert comparison["status"]["improved_can_run"] is True


def test_ai_tool_compare_preflight_versions_runs_saved_version_checks(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_project"

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    baseline_version_id, _ = pm.save_project_version('baseline_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'G4_Galactic'
    pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
    pm.recalculate_geometry_state()
    candidate_version_id, _ = pm.save_project_version('candidate_ai')

    res = dispatch_ai_tool(pm, "compare_preflight_versions", {
        "before_version": baseline_version_id,
        "after_version": candidate_version_id,
    })

    assert res["success"] is True
    assert res["baseline_version_id"] == baseline_version_id
    assert res["candidate_version_id"] == candidate_version_id
    comparison = res["comparison"]
    assert comparison["resolved_issue_codes"] == ["unknown_material_reference"]
    assert comparison["added_issue_codes"] == ["tiny_dimension"]
    assert comparison["status"]["improved_can_run"] is True
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=baseline_version_id,
        candidate_version_id=candidate_version_id,
    )


def test_ai_tool_compare_preflight_versions_rejects_missing_versions_without_success_metadata(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_missing_versions"

    pm.save_project_version('existing_version_ai')

    res = dispatch_ai_tool(pm, "compare_preflight_versions", {
        "baseline_version_id": "does_not_exist",
        "candidate_version_id": "also_missing",
    })

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "not found" in res["error"]


def test_ai_tool_compare_preflight_versions_preserves_cycle_truncation_metadata(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_versions_truncation_metadata"

    baseline_version_id, _ = pm.save_project_version('baseline_ai')
    _build_multi_cycle_lv_triangle(pm)
    candidate_version_id, _ = pm.save_project_version('candidate_ai')

    original_find_cycles = ProjectManager._find_preflight_hierarchy_cycles
    with patch.object(
        ProjectManager,
        '_find_preflight_hierarchy_cycles',
        autospec=True,
        side_effect=lambda self, state, max_cycles=20: original_find_cycles(self, state, max_cycles=1),
    ):
        res = dispatch_ai_tool(pm, "compare_preflight_versions", {
            "before_version": baseline_version_id,
            "after_version": candidate_version_id,
        })

    assert res["success"] is True
    assert res["baseline_version_id"] == baseline_version_id
    assert res["candidate_version_id"] == candidate_version_id
    assert 'placement_hierarchy_cycle_report_truncated' in res["comparison"]["added_issue_codes"]
    _assert_single_cycle_truncation_issue(res['candidate_report']['issues'])


def test_ai_tool_compare_latest_preflight_versions_uses_latest_two_saved_versions(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_latest_project"

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    _, _ = pm.save_project_version('a_old_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'G4_Galactic'
    pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
    pm.recalculate_geometry_state()
    baseline_version_id, _ = pm.save_project_version('b_mid_ai')

    pm.add_physical_volume(
        'World',
        'box_PV_overlap_ai',
        'box_LV',
        {'x': '0', 'y': '0', 'z': '0'},
        {'x': '0', 'y': '0', 'z': '0'},
        {'x': '1', 'y': '1', 'z': '1'},
    )
    pm.recalculate_geometry_state()
    candidate_version_id, _ = pm.save_project_version('c_latest_ai')

    res = dispatch_ai_tool(pm, "compare_latest_preflight_versions", {})

    assert res["success"] is True
    assert res["baseline_version_id"] == baseline_version_id
    assert res["candidate_version_id"] == candidate_version_id
    assert res["comparison"]["added_issue_codes"] == ["possible_overlap_aabb"]
    assert res["selection"]["strategy"] == "latest_two_saved_versions"
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=baseline_version_id,
        candidate_version_id=candidate_version_id,
        selection_ordering_basis='manual_saved_versions_sorted_desc_lexicographic',
    )


def test_ai_tool_compare_latest_preflight_versions_requires_two_saved_versions(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_latest_missing"

    pm.save_project_version('only_one_ai')

    res = dispatch_ai_tool(pm, "compare_latest_preflight_versions", {})

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "at least two saved versions" in res["error"]



def test_ai_tool_compare_autosave_preflight_vs_latest_saved(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_project"

    baseline_version_id, _ = pm.save_project_version('manual_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_latest_saved", {})

    assert res["success"] is True
    assert res["baseline_version_id"] == baseline_version_id
    assert res["candidate_version_id"] == "autosave"
    assert res["comparison"]["added_issue_codes"] == ["unknown_material_reference"]
    assert res["selection"]["strategy"] == "latest_autosave_vs_latest_saved"
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=baseline_version_id,
        candidate_version_id='autosave',
        selection_ordering_basis='manual_saved_versions_sorted_desc_lexicographic',
    )


def test_ai_tool_compare_autosave_preflight_vs_latest_saved_preserves_cycle_truncation_metadata(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_truncation_metadata"

    _, _ = pm.save_project_version('manual_ai_baseline')
    _build_multi_cycle_lv_triangle(pm)

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    original_find_cycles = ProjectManager._find_preflight_hierarchy_cycles
    with patch.object(
        ProjectManager,
        '_find_preflight_hierarchy_cycles',
        autospec=True,
        side_effect=lambda self, state, max_cycles=20: original_find_cycles(self, state, max_cycles=1),
    ):
        res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_latest_saved", {})

    assert res["success"] is True
    assert 'placement_hierarchy_cycle_report_truncated' in res["comparison"]["added_issue_codes"]

    _assert_single_cycle_truncation_issue(res['candidate_report']['issues'])


def test_ai_tool_compare_autosave_preflight_vs_latest_saved_requires_autosave(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_missing"

    pm.save_project_version('manual_only_ai')

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_latest_saved", {})

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "autosave" in res["error"]



def test_ai_tool_compare_autosave_preflight_vs_previous_manual_saved(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_previous_manual_saved_project"

    previous_manual_saved_version_id, _ = pm.save_project_version('manual_previous_ai')
    pm.save_project_version('autosave_snapshot_latest_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_previous_manual_saved", {
        "project": pm.project_name,
    })

    assert res["success"] is True
    assert res["baseline_version_id"] == previous_manual_saved_version_id
    assert res["candidate_version_id"] == "autosave"
    assert res["selection"]["strategy"] == "latest_autosave_vs_previous_manual_saved"
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=previous_manual_saved_version_id,
        candidate_version_id='autosave',
        selection_ordering_basis='manual_saved_versions_sorted_desc_lexicographic',
    )


def test_ai_tool_compare_autosave_preflight_vs_previous_manual_saved_requires_non_snapshot_saved_version(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_previous_manual_saved_missing"

    pm.save_project_version('autosave_snapshot_only_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_previous_manual_saved", {})

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "manually saved non-snapshot version" in res["error"]


def test_ai_tool_compare_autosave_preflight_vs_manual_saved_index(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_manual_saved_index_project"

    oldest_manual_version_id, _ = pm.save_project_version('manual_oldest_ai')
    target_manual_version_id, _ = pm.save_project_version('manual_target_ai')
    pm.save_project_version('autosave_snapshot_latest_ai')
    latest_manual_version_id, _ = pm.save_project_version('manual_latest_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_manual_saved_index", {
        "project": pm.project_name,
        "n_back": 1,
    })

    manual_sorted = sorted(
        [oldest_manual_version_id, target_manual_version_id, latest_manual_version_id],
        reverse=True,
    )
    assert res["success"] is True
    assert res["baseline_version_id"] == manual_sorted[1]
    assert res["candidate_version_id"] == "autosave"
    assert res["selection"]["strategy"] == "latest_autosave_vs_manual_saved_index"
    assert res["selection"]["manual_saved_index"] == 1
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=manual_sorted[1],
        candidate_version_id='autosave',
        selection_ordering_basis='manual_saved_versions_sorted_desc_lexicographic',
    )


def test_ai_tool_compare_autosave_preflight_vs_manual_saved_index_preserves_cycle_truncation_metadata(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_manual_saved_index_truncation"

    baseline_manual_version_id, _ = pm.save_project_version('manual_baseline_ai')
    _build_multi_cycle_lv_triangle(pm)

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    original_find_cycles = ProjectManager._find_preflight_hierarchy_cycles
    with patch.object(
        ProjectManager,
        '_find_preflight_hierarchy_cycles',
        autospec=True,
        side_effect=lambda self, state, max_cycles=20: original_find_cycles(self, state, max_cycles=1),
    ):
        res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_manual_saved_index", {
            "manual_saved_index": 0,
        })

    assert res["success"] is True
    assert res["baseline_version_id"] == baseline_manual_version_id
    assert res["candidate_version_id"] == "autosave"
    assert "placement_hierarchy_cycle_report_truncated" in res["comparison"]["added_issue_codes"]
    _assert_single_cycle_truncation_issue(res['candidate_report']['issues'])


def test_ai_tool_compare_autosave_preflight_vs_manual_saved_index_rejects_out_of_range_index(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_manual_saved_index_invalid"

    pm.save_project_version('manual_only_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_manual_saved_index", {
        "manual_saved_index": 5,
    })

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "out of range" in res["error"]



def test_ai_tool_compare_autosave_preflight_vs_manual_saved_for_simulation_run(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_manual_saved_for_run_project"

    simulation_run_id = "job_ai_match"

    oldest_matching_version_id, _ = pm.save_project_version('manual_run_old_ai')
    os.makedirs(os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    pm.save_project_version('autosave_snapshot_ai')

    latest_matching_version_id, _ = pm.save_project_version('manual_run_latest_ai')
    os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    pm.save_project_version('manual_without_run_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_manual_saved_for_simulation_run", {
        "project": pm.project_name,
        "run_id": simulation_run_id,
    })

    expected_latest_matching_id = sorted(
        [oldest_matching_version_id, latest_matching_version_id],
        reverse=True,
    )[0]

    assert res["success"] is True
    assert res["baseline_version_id"] == expected_latest_matching_id
    assert res["candidate_version_id"] == "autosave"
    assert res["selection"]["strategy"] == "latest_autosave_vs_manual_saved_for_simulation_run"
    assert res["selection"]["simulation_run_id"] == simulation_run_id
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=expected_latest_matching_id,
        candidate_version_id='autosave',
        selection_ordering_basis='matching_manual_saved_versions_sorted_desc_lexicographic',
    )


def test_ai_tool_compare_autosave_preflight_vs_manual_saved_for_simulation_run_preserves_cycle_truncation_metadata(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_manual_saved_for_run_truncation"

    simulation_run_id = "job_ai_match_truncation"

    baseline_manual_version_id, _ = pm.save_project_version('manual_run_baseline_ai')
    os.makedirs(os.path.join(pm._get_version_dir(baseline_manual_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    _build_multi_cycle_lv_triangle(pm)

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    original_find_cycles = ProjectManager._find_preflight_hierarchy_cycles
    with patch.object(
        ProjectManager,
        '_find_preflight_hierarchy_cycles',
        autospec=True,
        side_effect=lambda self, state, max_cycles=20: original_find_cycles(self, state, max_cycles=1),
    ):
        res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_manual_saved_for_simulation_run", {
            "simulation_run_id": simulation_run_id,
        })

    assert res["success"] is True
    assert res["baseline_version_id"] == baseline_manual_version_id
    assert res["candidate_version_id"] == "autosave"
    assert "placement_hierarchy_cycle_report_truncated" in res["comparison"]["added_issue_codes"]
    _assert_single_cycle_truncation_issue(res['candidate_report']['issues'])


def test_ai_tool_compare_autosave_preflight_vs_manual_saved_for_simulation_run_index(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_manual_saved_for_run_index_project"

    simulation_run_id = "job_ai_index_match"

    oldest_matching_version_id, _ = pm.save_project_version('manual_run_index_old_ai')
    os.makedirs(os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    target_matching_version_id, _ = pm.save_project_version('manual_run_index_target_ai')
    os.makedirs(os.path.join(pm._get_version_dir(target_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    pm.save_project_version('autosave_snapshot_index_ai')

    latest_matching_version_id, _ = pm.save_project_version('manual_run_index_latest_ai')
    os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index", {
        "project": pm.project_name,
        "job_id": simulation_run_id,
        "n_back": 1,
    })

    matching_sorted = sorted(
        [oldest_matching_version_id, target_matching_version_id, latest_matching_version_id],
        reverse=True,
    )

    assert res["success"] is True
    assert res["baseline_version_id"] == matching_sorted[1]
    assert res["candidate_version_id"] == "autosave"
    assert res["selection"]["strategy"] == "latest_autosave_vs_manual_saved_for_simulation_run_index"
    assert res["selection"]["simulation_run_id"] == simulation_run_id
    assert res["selection"]["manual_saved_index"] == 1
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=matching_sorted[1],
        candidate_version_id='autosave',
        selection_ordering_basis='matching_manual_saved_versions_sorted_desc_lexicographic',
    )


def test_ai_tool_compare_autosave_preflight_vs_manual_saved_for_simulation_run_index_preserves_cycle_truncation_metadata(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_manual_saved_for_run_index_truncation"

    simulation_run_id = "job_ai_index_match_truncation"

    baseline_manual_version_id, _ = pm.save_project_version('manual_run_index_baseline_ai')
    os.makedirs(os.path.join(pm._get_version_dir(baseline_manual_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    _build_multi_cycle_lv_triangle(pm)

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    original_find_cycles = ProjectManager._find_preflight_hierarchy_cycles
    with patch.object(
        ProjectManager,
        '_find_preflight_hierarchy_cycles',
        autospec=True,
        side_effect=lambda self, state, max_cycles=20: original_find_cycles(self, state, max_cycles=1),
    ):
        res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index", {
            "simulation_run_id": simulation_run_id,
            "manual_saved_index": 0,
        })

    assert res["success"] is True
    assert res["baseline_version_id"] == baseline_manual_version_id
    assert res["candidate_version_id"] == "autosave"
    assert "placement_hierarchy_cycle_report_truncated" in res["comparison"]["added_issue_codes"]
    _assert_single_cycle_truncation_issue(res['candidate_report']['issues'])


def test_ai_tool_compare_autosave_preflight_vs_manual_saved_for_simulation_run_index_rejects_out_of_range(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_manual_saved_for_run_index_invalid"

    simulation_run_id = "job_ai_index_invalid"

    matching_version_id, _ = pm.save_project_version('manual_run_index_only_ai')
    os.makedirs(os.path.join(pm._get_version_dir(matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index", {
        "simulation_run_id": simulation_run_id,
        "manual_saved_index": 2,
    })

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "out of range" in res["error"]
    assert "simulation_run_id" in res["error"]


def test_ai_tool_compare_autosave_preflight_vs_manual_saved_for_simulation_run_requires_simulation_run_id(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_manual_saved_for_run_requires_id"

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_manual_saved_for_simulation_run", {})

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "missing required field" in res["error"].lower()
    assert "simulation_run_id" in res["error"]



def test_ai_tool_compare_autosave_preflight_vs_manual_saved_for_simulation_run_index_requires_simulation_run_id(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_manual_saved_for_run_index_requires_id"

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index", {
        "manual_saved_index": 0,
    })

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "missing required field" in res["error"].lower()
    assert "simulation_run_id" in res["error"]



def test_ai_tool_compare_manual_preflight_versions_for_simulation_run_indices_requires_simulation_run_id(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_manual_for_run_indices_requires_id"

    res = dispatch_ai_tool(pm, "compare_manual_preflight_versions_for_simulation_run_indices", {
        "baseline_manual_saved_index": 1,
        "candidate_manual_saved_index": 0,
    })

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "missing required field" in res["error"].lower()
    assert "simulation_run_id" in res["error"]



def test_ai_tool_compare_autosave_preflight_vs_manual_saved_for_simulation_run_requires_match(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_manual_saved_for_run_missing"

    manual_version_id, _ = pm.save_project_version('manual_other_run_ai')
    os.makedirs(os.path.join(pm._get_version_dir(manual_version_id), 'sim_runs', 'other_job_ai'), exist_ok=True)

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_manual_saved_for_simulation_run", {
        "simulation_run_id": "missing_ai_job",
    })

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "simulation_run_id" in res["error"]
    assert "No manually saved non-snapshot versions" in res["error"]


def test_ai_tool_compare_autosave_preflight_vs_saved_version(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_selected_project"

    requested_saved_version_id, _ = pm.save_project_version('manual_selected_ai')

    pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
    pm.recalculate_geometry_state()
    pm.save_project_version('manual_latest_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_saved_version", {
        "saved_version": requested_saved_version_id,
    })

    assert res["success"] is True
    assert res["baseline_version_id"] == requested_saved_version_id
    assert res["candidate_version_id"] == "autosave"
    assert "unknown_material_reference" in res["comparison"]["added_issue_codes"]
    assert res["selection"]["strategy"] == "latest_autosave_vs_selected_saved_version"
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=requested_saved_version_id,
        candidate_version_id='autosave',
        selection_ordering_basis='explicit_saved_version_id',
    )


def test_ai_tool_compare_autosave_preflight_vs_saved_version_requires_saved_version_id(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_selected_missing"

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_saved_version", {})

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "saved_version_id" in res["error"]


def test_ai_tool_compare_autosave_preflight_vs_saved_version_returns_not_found_for_unknown_saved_version(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_selected_missing_version"

    pm.save_project_version("manual_existing_ai")

    pm.current_geometry_state.logical_volumes["box_LV"].material_ref = "MissingMat"
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir("autosave")
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, "version.json"), "w") as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_saved_version", {
        "saved_version_id": "missing_manual_ai_version",
    })

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "not found" in res["error"].lower()


def test_ai_tool_compare_autosave_preflight_vs_snapshot_version(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_snapshot_project"

    requested_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_manual_selected_ai')

    pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
    pm.recalculate_geometry_state()
    pm.save_project_version('manual_latest_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_snapshot_version", {
        "snapshot_version": requested_snapshot_version_id,
    })

    assert res["success"] is True
    assert res["baseline_version_id"] == requested_snapshot_version_id
    assert res["candidate_version_id"] == "autosave"
    assert "unknown_material_reference" in res["comparison"]["added_issue_codes"]
    assert res["selection"]["strategy"] == "latest_autosave_vs_selected_autosave_snapshot"
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=requested_snapshot_version_id,
        candidate_version_id='autosave',
        selection_ordering_basis='explicit_autosave_snapshot_version_id',
    )


def test_ai_tool_compare_autosave_preflight_vs_snapshot_version_requires_snapshot_id(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_snapshot_missing"

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_snapshot_version", {})

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "autosave_snapshot_version_id" in res["error"]


def test_ai_tool_compare_autosave_preflight_vs_snapshot_version_returns_not_found_for_unknown_snapshot_version(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_snapshot_missing_version"

    pm.save_project_version("autosave_snapshot_existing_ai")

    pm.current_geometry_state.logical_volumes["box_LV"].material_ref = "MissingMat"
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir("autosave")
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, "version.json"), "w") as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_snapshot_version", {
        "autosave_snapshot_version_id": "20990101_autosave_snapshot_missing_ai",
    })

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "not found" in res["error"].lower()


def test_ai_tool_compare_autosave_preflight_vs_snapshot_version_rejects_non_snapshot_version(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_snapshot_invalid"

    manual_version_id, _ = pm.save_project_version('manual_selected_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_snapshot_version", {
        "autosave_snapshot_version_id": manual_version_id,
    })

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "autosave snapshot" in res["error"]


def test_ai_tool_compare_autosave_preflight_vs_latest_snapshot(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_latest_snapshot_project"

    pm.save_project_version('autosave_snapshot_old_ai')
    latest_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_new_ai')
    pm.save_project_version('manual_latest_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_latest_snapshot", {})

    assert res["success"] is True
    assert res["baseline_version_id"] == latest_snapshot_version_id
    assert res["candidate_version_id"] == "autosave"
    assert res["selection"]["strategy"] == "latest_autosave_vs_latest_autosave_snapshot"
    assert res["selection"]["total_snapshot_versions"] == 2
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=latest_snapshot_version_id,
        candidate_version_id='autosave',
        selection_ordering_basis='autosave_snapshot_versions_sorted_by_mtime_then_version_id_desc',
    )


def test_ai_tool_compare_autosave_preflight_vs_latest_snapshot_requires_snapshot_version(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_latest_snapshot_missing"

    pm.save_project_version('manual_only_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_latest_snapshot", {})

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "at least one saved autosave snapshot version" in res["error"]


def test_ai_tool_compare_autosave_preflight_vs_previous_snapshot(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_previous_snapshot_project"

    pm.save_project_version('autosave_snapshot_old_ai')
    previous_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_previous_ai')
    pm.save_project_version('autosave_snapshot_latest_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_previous_snapshot", {
        "project": pm.project_name,
    })

    assert res["success"] is True
    assert res["baseline_version_id"] == previous_snapshot_version_id
    assert res["candidate_version_id"] == "autosave"
    assert "unknown_material_reference" in res["comparison"]["added_issue_codes"]
    assert res["selection"]["strategy"] == "latest_autosave_vs_previous_autosave_snapshot"
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=previous_snapshot_version_id,
        candidate_version_id='autosave',
        selection_ordering_basis='autosave_snapshot_versions_sorted_by_mtime_then_version_id_desc',
    )


def test_ai_tool_compare_autosave_preflight_vs_previous_snapshot_requires_two_snapshots(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_autosave_previous_snapshot_missing"

    pm.save_project_version('autosave_snapshot_only_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "compare_autosave_preflight_vs_previous_snapshot", {})

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "at least two saved autosave snapshot versions" in res["error"]


def test_ai_tool_compare_autosave_snapshot_preflight_versions(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_snapshot_versions_project"

    baseline_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_baseline_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()
    candidate_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_candidate_ai')

    res = dispatch_ai_tool(pm, "compare_autosave_snapshot_preflight_versions", {
        "baseline_version": baseline_snapshot_version_id,
        "candidate_snapshot_version": candidate_snapshot_version_id,
    })

    assert res["success"] is True
    assert res["baseline_version_id"] == baseline_snapshot_version_id
    assert res["candidate_version_id"] == candidate_snapshot_version_id
    assert res["comparison"]["added_issue_codes"] == ["unknown_material_reference"]
    assert res["selection"]["strategy"] == "selected_autosave_snapshot_versions"
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=baseline_snapshot_version_id,
        candidate_version_id=candidate_snapshot_version_id,
        selection_ordering_basis='explicit_autosave_snapshot_version_ids',
    )


def test_ai_tool_compare_autosave_snapshot_preflight_versions_preserves_cycle_truncation_metadata(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_snapshot_versions_truncation_metadata"

    baseline_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_baseline_ai')
    _build_multi_cycle_lv_triangle(pm)
    candidate_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_candidate_ai')

    original_find_cycles = ProjectManager._find_preflight_hierarchy_cycles
    with patch.object(
        ProjectManager,
        '_find_preflight_hierarchy_cycles',
        autospec=True,
        side_effect=lambda self, state, max_cycles=20: original_find_cycles(self, state, max_cycles=1),
    ):
        res = dispatch_ai_tool(pm, "compare_autosave_snapshot_preflight_versions", {
            "baseline_snapshot_version_id": baseline_snapshot_version_id,
            "candidate_snapshot_version_id": candidate_snapshot_version_id,
        })

    assert res["success"] is True
    assert res["baseline_version_id"] == baseline_snapshot_version_id
    assert res["candidate_version_id"] == candidate_snapshot_version_id
    assert 'placement_hierarchy_cycle_report_truncated' in res["comparison"]["added_issue_codes"]
    _assert_single_cycle_truncation_issue(res['candidate_report']['issues'])


def test_ai_tool_compare_autosave_snapshot_preflight_versions_rejects_non_snapshot(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_snapshot_versions_invalid"

    baseline_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_baseline_ai')
    manual_version_id, _ = pm.save_project_version('manual_candidate_ai')

    res = dispatch_ai_tool(pm, "compare_autosave_snapshot_preflight_versions", {
        "baseline_snapshot_version_id": baseline_snapshot_version_id,
        "candidate_snapshot_version_id": manual_version_id,
    })

    assert res["success"] is False
    assert "candidate_snapshot_version_id" in res["error"]
    assert "autosave snapshot" in res["error"]


def test_ai_tool_compare_autosave_snapshot_preflight_versions_returns_not_found_for_unknown_snapshot_version(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_snapshot_versions_missing_version"

    baseline_snapshot_version_id, _ = pm.save_project_version("autosave_snapshot_baseline_ai")

    res = dispatch_ai_tool(pm, "compare_autosave_snapshot_preflight_versions", {
        "baseline_snapshot_version_id": baseline_snapshot_version_id,
        "candidate_snapshot_version_id": "20990101_autosave_snapshot_missing_ai",
    })

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "not found" in res["error"].lower()


def test_ai_tool_compare_latest_autosave_snapshot_preflight_versions(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_latest_snapshot_versions_project"

    baseline_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_old_ai')

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()
    latest_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_new_ai')

    res = dispatch_ai_tool(pm, "compare_latest_autosave_snapshot_preflight_versions", {
        "project": pm.project_name,
    })

    assert res["success"] is True
    assert res["candidate_version_id"] == latest_snapshot_version_id
    assert res["comparison"]["added_issue_codes"] == ["unknown_material_reference"]
    assert res["selection"]["strategy"] == "latest_two_autosave_snapshot_versions"
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=baseline_snapshot_version_id,
        candidate_version_id=latest_snapshot_version_id,
        selection_ordering_basis='autosave_snapshot_versions_sorted_by_mtime_then_version_id_desc',
    )


def test_ai_tool_compare_latest_autosave_snapshot_preflight_versions_requires_two_snapshots(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_latest_snapshot_versions_missing"

    pm.save_project_version('autosave_snapshot_only_ai')

    res = dispatch_ai_tool(pm, "compare_latest_autosave_snapshot_preflight_versions", {})

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "at least two saved autosave snapshot versions" in res["error"]


def test_ai_tool_list_manual_saved_versions_for_simulation_run_supports_aliases(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_list_manual_saved_for_run_project"

    simulation_run_id = "job_ai_list_match"

    oldest_matching_version_id, _ = pm.save_project_version('manual_ai_list_old')
    os.makedirs(os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    latest_matching_version_id, _ = pm.save_project_version('manual_ai_list_latest')
    os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    res = dispatch_ai_tool(pm, "list_manual_saved_versions_for_simulation_run", {
        "project": pm.project_name,
        "job_id": simulation_run_id,
        "count": 1,
    })

    expected_latest = sorted([oldest_matching_version_id, latest_matching_version_id], reverse=True)[0]

    assert res["success"] is True
    assert res["simulation_run_id"] == simulation_run_id
    assert res["total_matching_manual_saved_versions"] == 2
    assert res["returned_matching_manual_saved_versions"] == 1
    assert res["matching_manual_saved_versions"][0]["manual_saved_index"] == 0
    assert res["matching_manual_saved_versions"][0]["version_id"] == expected_latest


def test_ai_tool_list_manual_saved_versions_for_simulation_run_rejects_invalid_limit(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_list_manual_saved_for_run_invalid_limit"

    res = dispatch_ai_tool(pm, "list_manual_saved_versions_for_simulation_run", {
        "simulation_run_id": "job_ai_list_invalid_limit",
        "limit": -1,
    })

    _assert_preflight_list_ai_error_payload_excludes_success_metadata(res)
    assert "limit" in res["error"]


def test_ai_tool_list_manual_saved_versions_for_simulation_run_requires_simulation_run_id_without_success_metadata(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_list_manual_saved_for_run_missing_selector"

    res = dispatch_ai_tool(pm, "list_manual_saved_versions_for_simulation_run", {
        "project_name": pm.project_name,
    })

    _assert_preflight_list_ai_error_payload_excludes_success_metadata(res)
    assert "simulation_run_id" in res["error"]


def test_ai_tool_compare_manual_preflight_versions_for_simulation_run_indices_supports_aliases(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_manual_for_run_indices_project"

    simulation_run_id = "job_ai_manual_compare"

    oldest_matching_version_id, _ = pm.save_project_version('manual_ai_compare_oldest')
    os.makedirs(os.path.join(pm._get_version_dir(oldest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    pm.current_geometry_state.solids['box_solid'].raw_parameters['x'] = '1e-6'
    pm.recalculate_geometry_state()
    target_baseline_version_id, _ = pm.save_project_version('manual_ai_compare_baseline_target')
    os.makedirs(os.path.join(pm._get_version_dir(target_baseline_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    pm.current_geometry_state.logical_volumes['box_LV'].material_ref = 'MissingMat'
    pm.recalculate_geometry_state()
    latest_matching_version_id, _ = pm.save_project_version('manual_ai_compare_candidate_latest')
    os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    res = dispatch_ai_tool(pm, "compare_manual_preflight_versions_for_simulation_run_indices", {
        "project": pm.project_name,
        "job_id": simulation_run_id,
        "baseline_n_back": 1,
        "candidate_n_back": 0,
    })

    matching_sorted = sorted(
        [oldest_matching_version_id, target_baseline_version_id, latest_matching_version_id],
        reverse=True,
    )

    assert res["success"] is True
    assert res["baseline_version_id"] == matching_sorted[1]
    assert res["candidate_version_id"] == matching_sorted[0]
    assert res["selection"]["strategy"] == "manual_saved_versions_for_simulation_run_indices"
    assert res["selection"]["baseline_manual_saved_index"] == 1
    assert res["selection"]["candidate_manual_saved_index"] == 0
    _assert_compare_ai_selection_and_source_metadata(
        res,
        baseline_version_id=matching_sorted[1],
        candidate_version_id=matching_sorted[0],
        selection_ordering_basis='matching_manual_saved_versions_sorted_desc_lexicographic',
    )


def test_ai_tool_compare_manual_preflight_versions_for_simulation_run_indices_preserves_cycle_truncation_metadata(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_manual_for_run_indices_truncation"

    simulation_run_id = "job_ai_manual_compare_truncation"

    baseline_version_id, _ = pm.save_project_version('manual_ai_compare_baseline_truncation')
    os.makedirs(os.path.join(pm._get_version_dir(baseline_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    _build_multi_cycle_lv_triangle(pm)
    candidate_version_id, _ = pm.save_project_version('manual_ai_compare_candidate_truncation')
    os.makedirs(os.path.join(pm._get_version_dir(candidate_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    original_find_cycles = ProjectManager._find_preflight_hierarchy_cycles
    with patch.object(
        ProjectManager,
        '_find_preflight_hierarchy_cycles',
        autospec=True,
        side_effect=lambda self, state, max_cycles=20: original_find_cycles(self, state, max_cycles=1),
    ):
        res = dispatch_ai_tool(pm, "compare_manual_preflight_versions_for_simulation_run_indices", {
            "simulation_run_id": simulation_run_id,
            "baseline_manual_saved_index": 1,
            "candidate_manual_saved_index": 0,
        })

    assert res["success"] is True
    assert res["baseline_version_id"] == baseline_version_id
    assert res["candidate_version_id"] == candidate_version_id
    assert "placement_hierarchy_cycle_report_truncated" in res["comparison"]["added_issue_codes"]
    _assert_single_cycle_truncation_issue(res['candidate_report']['issues'])


def test_ai_tool_compare_manual_preflight_versions_for_simulation_run_indices_rejects_identical_indices(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_manual_for_run_indices_same_index"

    simulation_run_id = "job_ai_manual_compare_same_index"

    old_matching_version_id, _ = pm.save_project_version('manual_ai_compare_same_old')
    os.makedirs(os.path.join(pm._get_version_dir(old_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    latest_matching_version_id, _ = pm.save_project_version('manual_ai_compare_same_latest')
    os.makedirs(os.path.join(pm._get_version_dir(latest_matching_version_id), 'sim_runs', simulation_run_id), exist_ok=True)

    res = dispatch_ai_tool(pm, "compare_manual_preflight_versions_for_simulation_run_indices", {
        "simulation_run_id": simulation_run_id,
        "baseline_manual_saved_index": 0,
        "candidate_manual_saved_index": 0,
    })

    _assert_compare_ai_error_payload_excludes_success_metadata(res)
    assert "must be different" in res["error"]


def test_ai_tool_list_preflight_versions_supports_aliases(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_preflight_versions_project"

    first_version_id, _ = pm.save_project_version('manual_old_ai')
    second_version_id, _ = pm.save_project_version('autosave_snapshot_manual_newer_ai')

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "list_preflight_versions", {
        "project": pm.project_name,
        "count": 2,
    })

    assert res["success"] is True
    assert res["returned_versions"] == 2
    assert res["versions"][0]["version_id"] == "autosave"

    manual_candidates = [entry["version_id"] for entry in res["versions"] if not entry["is_autosave"]]
    assert manual_candidates[0] == sorted([first_version_id, second_version_id], reverse=True)[0]


def test_ai_tool_list_preflight_versions_can_exclude_autosave(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_preflight_versions_no_autosave"

    pm.save_project_version('manual_old_ai')
    pm.save_project_version('manual_new_ai')

    autosave_dir = pm._get_version_dir('autosave')
    os.makedirs(autosave_dir, exist_ok=True)
    with open(os.path.join(autosave_dir, 'version.json'), 'w') as handle:
        handle.write(pm.save_project_to_json_string())

    res = dispatch_ai_tool(pm, "list_preflight_versions", {
        "include_latest_autosave": False,
    })

    assert res["success"] is True
    assert res["has_autosave"] is False
    assert all(not entry["is_autosave"] for entry in res["versions"])


def test_ai_tool_list_preflight_versions_rejects_invalid_limit_without_success_metadata(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_preflight_versions_invalid_limit"

    res = dispatch_ai_tool(pm, "list_preflight_versions", {
        "project_name": pm.project_name,
        "limit": -1,
    })

    _assert_preflight_list_ai_error_payload_excludes_success_metadata(res)
    assert "limit" in res["error"]


def test_ai_tool_list_preflight_versions_rejects_missing_project_name_without_success_metadata(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = ""

    res = dispatch_ai_tool(pm, "list_preflight_versions", {})

    _assert_preflight_list_ai_error_payload_excludes_success_metadata(res)
    assert "project_name" in res["error"]


def test_preflight_list_routes_and_ai_wrappers_share_success_payloads(pm, tmp_path):
    fixture = _seed_preflight_compare_route_ai_parity_fixture(pm, tmp_path)

    cases = [
        {
            "name": "list_versions",
            "route": "/api/preflight/list_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "include_latest_autosave": True,
                "max_versions": 3,
            },
            "tool": "list_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "include_latest_autosave": True,
                "count": 3,
            },
        },
        {
            "name": "list_manual_saved_versions_for_simulation_run",
            "route": "/api/preflight/list_manual_saved_versions_for_simulation_run",
            "route_payload": {
                "project_name": pm.project_name,
                "job_id": fixture["simulation_run_id"],
                "count": 1,
            },
            "tool": "list_manual_saved_versions_for_simulation_run",
            "ai_args": {
                "project": pm.project_name,
                "run_id": fixture["simulation_run_id"],
                "max_versions": 1,
            },
        },
    ]

    expected_latest_matching_version_id = sorted(
        [fixture["oldest_matching_version_id"], fixture["latest_matching_version_id"]],
        reverse=True,
    )[0]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == 200
        assert route_data == ai_data
        assert route_data["success"] is True

        if case["name"] == "list_versions":
            assert route_data["ordering_basis"] == "autosave_first_then_manual_saved_desc_lexicographic"
            assert route_data["manual_saved_ordering_basis"] == "manual_saved_versions_sorted_desc_lexicographic"
            assert route_data["total_versions"] == 3
            assert route_data["returned_versions"] == 3
            assert route_data["versions"][0]["version_id"] == "autosave"
            assert route_data["versions"][0]["timestamp_source"] == "version_json_mtime_utc"
            assert route_data["versions"][0]["source_path_checks"]["version_json_within_versions_root"] is True
        else:
            assert route_data["simulation_run_id"] == fixture["simulation_run_id"]
            assert route_data["ordering_basis"] == "matching_manual_saved_versions_sorted_desc_lexicographic"
            assert route_data["total_matching_manual_saved_versions"] == 2
            assert route_data["returned_matching_manual_saved_versions"] == 1
            assert route_data["matching_manual_saved_versions"][0]["manual_saved_index"] == 0
            assert route_data["matching_manual_saved_versions"][0]["version_id"] == expected_latest_matching_version_id
            assert route_data["matching_manual_saved_versions"][0]["timestamp_source"] == "version_id_prefix"
            assert route_data["matching_manual_saved_versions"][0]["source_path_checks"]["version_json_within_versions_root"] is True


def test_preflight_list_versions_route_and_ai_wrappers_share_alias_invalid_limit_error_payloads(pm, tmp_path):
    _seed_preflight_compare_route_ai_parity_fixture(pm, tmp_path)

    route_status_code, route_data = _call_preflight_route_with_pm(
        pm,
        "/api/preflight/list_versions",
        {
            "project_name": pm.project_name,
            "max_versions": -1,
            "include_latest_autosave": True,
        },
    )
    ai_data = dispatch_ai_tool(pm, "list_preflight_versions", {
        "project": pm.project_name,
        "count": -1,
        "include_latest_autosave": True,
    })

    assert route_status_code == 400
    assert route_data == ai_data
    _assert_preflight_list_ai_error_payload_excludes_success_metadata(route_data)
    assert "limit" in route_data["error"]



def test_preflight_list_versions_route_and_ai_wrappers_share_canonical_alias_precedence_payloads(pm, tmp_path):
    _seed_preflight_compare_route_ai_parity_fixture(pm, tmp_path)

    cases = [
        {
            "name": "canonical_include_autosave_overrides_conflicting_alias",
            "route_payload": {
                "project_name": pm.project_name,
                "include_autosave": False,
                "include_latest_autosave": True,
            },
            "ai_args": {
                "project": pm.project_name,
                "include_autosave": False,
                "include_latest_autosave": True,
            },
            "expected_status": 200,
            "expected_has_autosave": False,
            "expected_total_versions": 2,
            "expected_returned_versions": 2,
            "expect_no_autosave_versions": True,
        },
        {
            "name": "null_canonical_include_autosave_does_not_fall_back_to_alias",
            "route_payload": {
                "project_name": pm.project_name,
                "include_autosave": None,
                "include_latest_autosave": True,
            },
            "ai_args": {
                "project": pm.project_name,
                "include_autosave": None,
                "include_latest_autosave": True,
            },
            "expected_status": 200,
            "expected_has_autosave": False,
            "expected_total_versions": 2,
            "expected_returned_versions": 2,
            "expect_no_autosave_versions": True,
        },
        {
            "name": "canonical_limit_overrides_conflicting_alias_limits",
            "route_payload": {
                "project_name": pm.project_name,
                "include_autosave": True,
                "limit": 1,
                "max_versions": 3,
                "count": 2,
            },
            "ai_args": {
                "project": pm.project_name,
                "include_autosave": True,
                "limit": 1,
                "max_versions": 3,
                "count": 2,
            },
            "expected_status": 200,
            "expected_has_autosave": True,
            "expected_total_versions": 3,
            "expected_returned_versions": 1,
            "expect_autosave_first": True,
        },
        {
            "name": "null_canonical_limit_does_not_fall_back_to_alias",
            "route_payload": {
                "project_name": pm.project_name,
                "include_autosave": True,
                "limit": None,
                "max_versions": 1,
                "count": 1,
            },
            "ai_args": {
                "project": pm.project_name,
                "include_autosave": True,
                "limit": None,
                "max_versions": 1,
                "count": 1,
            },
            "expected_status": 200,
            "expected_has_autosave": True,
            "expected_total_versions": 3,
            "expected_returned_versions": 3,
            "expect_autosave_first": True,
        },
        {
            "name": "empty_canonical_limit_does_not_fall_back_to_alias",
            "route_payload": {
                "project_name": pm.project_name,
                "include_autosave": True,
                "limit": "",
                "max_versions": 1,
            },
            "ai_args": {
                "project": pm.project_name,
                "include_autosave": True,
                "limit": "",
                "max_versions": 1,
            },
            "expected_status": 400,
            "error_substrings": ["limit", "non-negative integer"],
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            "/api/preflight/list_versions",
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, "list_preflight_versions", case["ai_args"])

        assert status_code == case["expected_status"], case["name"]
        assert route_data == ai_data, case["name"]

        if case["expected_status"] == 200:
            assert route_data["success"] is True, case["name"]
            assert route_data["has_autosave"] == case["expected_has_autosave"], case["name"]
            assert route_data["total_versions"] == case["expected_total_versions"], case["name"]
            assert route_data["returned_versions"] == case["expected_returned_versions"], case["name"]

            if case.get("expect_no_autosave_versions"):
                assert all(not entry["is_autosave"] for entry in route_data["versions"]), case["name"]

            if case.get("expect_autosave_first"):
                assert route_data["versions"][0]["version_id"] == "autosave", case["name"]

            continue

        _assert_preflight_list_ai_error_payload_excludes_success_metadata(route_data)
        error_lower = route_data["error"].lower()
        for expected_substring in case["error_substrings"]:
            assert expected_substring.lower() in error_lower, case["name"]


def test_preflight_global_list_selector_workflows_route_and_ai_wrappers_share_payloads(pm, tmp_path):
    fixture = _seed_preflight_global_selector_route_ai_parity_fixture(pm, tmp_path)

    list_status_code, list_route_data = _call_preflight_route_with_pm(
        pm,
        "/api/preflight/list_versions",
        {
            "project_name": pm.project_name,
            "include_autosave": True,
        },
    )
    list_ai_data = dispatch_ai_tool(pm, "list_preflight_versions", {
        "project": pm.project_name,
        "include_latest_autosave": True,
    })

    assert list_status_code == 200
    assert list_route_data == list_ai_data
    assert list_route_data["success"] is True
    assert list_route_data["has_autosave"] is True

    listed_manual_ids = [
        entry["version_id"]
        for entry in list_route_data["versions"]
        if (not entry["is_autosave"]) and (not entry["is_autosave_snapshot"]) and entry["has_version_json"]
    ]
    listed_snapshot_ids = [
        entry["version_id"]
        for entry in list_route_data["versions"]
        if entry["is_autosave_snapshot"] and entry["has_version_json"]
    ]

    assert len(listed_manual_ids) == 2
    assert len(listed_snapshot_ids) == 2
    assert fixture["manual_baseline_version_id"] in listed_manual_ids
    assert fixture["manual_candidate_version_id"] in listed_manual_ids
    assert fixture["snapshot_baseline_version_id"] in listed_snapshot_ids
    assert fixture["snapshot_candidate_version_id"] in listed_snapshot_ids

    workflow_cases = [
        {
            "name": "compare_versions_from_listed_manual_ids",
            "route": "/api/preflight/compare_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version_id": listed_manual_ids[1],
                "candidate_version_id": listed_manual_ids[0],
            },
            "tool": "compare_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "baseline_version": listed_manual_ids[1],
                "candidate": listed_manual_ids[0],
            },
            "selection_ordering_basis": None,
            "baseline_version_id": listed_manual_ids[1],
            "candidate_version_id": listed_manual_ids[0],
        },
        {
            "name": "compare_autosave_vs_saved_from_listed_manual_id",
            "route": "/api/preflight/compare_autosave_vs_saved_version",
            "route_payload": {
                "project_name": pm.project_name,
                "saved_version_id": listed_manual_ids[0],
            },
            "tool": "compare_autosave_preflight_vs_saved_version",
            "ai_args": {
                "project": pm.project_name,
                "version": listed_manual_ids[0],
            },
            "selection_ordering_basis": "explicit_saved_version_id",
            "baseline_version_id": listed_manual_ids[0],
            "candidate_version_id": "autosave",
        },
        {
            "name": "compare_autosave_vs_snapshot_from_listed_snapshot_id",
            "route": "/api/preflight/compare_autosave_vs_snapshot_version",
            "route_payload": {
                "project_name": pm.project_name,
                "autosave_snapshot_version_id": listed_snapshot_ids[0],
            },
            "tool": "compare_autosave_preflight_vs_snapshot_version",
            "ai_args": {
                "project": pm.project_name,
                "snapshot_version": listed_snapshot_ids[0],
            },
            "selection_ordering_basis": "explicit_autosave_snapshot_version_id",
            "baseline_version_id": listed_snapshot_ids[0],
            "candidate_version_id": "autosave",
        },
        {
            "name": "compare_snapshot_versions_from_listed_snapshot_ids",
            "route": "/api/preflight/compare_snapshot_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_snapshot_version_id": listed_snapshot_ids[1],
                "candidate_snapshot_version_id": listed_snapshot_ids[0],
            },
            "tool": "compare_autosave_snapshot_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "baseline_version": listed_snapshot_ids[1],
                "candidate_version": listed_snapshot_ids[0],
            },
            "selection_ordering_basis": "explicit_autosave_snapshot_version_ids",
            "baseline_version_id": listed_snapshot_ids[1],
            "candidate_version_id": listed_snapshot_ids[0],
        },
    ]

    for case in workflow_cases:
        status_code, route_data = _call_preflight_route_with_pm(pm, case["route"], case["route_payload"])
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == 200, case["name"]
        assert route_data == ai_data, case["name"]
        assert route_data["success"] is True, case["name"]

        _assert_compare_ai_selection_and_source_metadata(
            route_data,
            baseline_version_id=case["baseline_version_id"],
            candidate_version_id=case["candidate_version_id"],
            selection_ordering_basis=case["selection_ordering_basis"],
        )


def test_preflight_global_list_stale_selector_workflows_route_and_ai_wrappers_share_404_error_envelopes(pm, tmp_path):
    fixture = _seed_preflight_global_selector_stale_route_ai_parity_fixture(pm, tmp_path)

    list_status_code, list_route_data = _call_preflight_route_with_pm(
        pm,
        "/api/preflight/list_versions",
        {
            "project_name": pm.project_name,
        },
    )
    list_ai_data = dispatch_ai_tool(pm, "list_preflight_versions", {
        "project": pm.project_name,
    })

    assert list_status_code == 200
    assert list_route_data == list_ai_data
    assert list_route_data["success"] is True

    stale_manual_entry = next(entry for entry in list_route_data["versions"] if entry["version_id"] == fixture["stale_manual_version_id"])
    stale_snapshot_entry = next(entry for entry in list_route_data["versions"] if entry["version_id"] == fixture["stale_snapshot_version_id"])

    assert stale_manual_entry["has_version_json"] is False
    assert stale_manual_entry["version_json_mtime_utc"] is None
    assert stale_snapshot_entry["has_version_json"] is False
    assert stale_snapshot_entry["version_json_mtime_utc"] is None

    stale_workflow_cases = [
        {
            "name": "autosave_vs_saved_with_stale_manual_id",
            "route": "/api/preflight/compare_autosave_vs_saved_version",
            "route_payload": {
                "project_name": pm.project_name,
                "saved_version_id": fixture["stale_manual_version_id"],
            },
            "tool": "compare_autosave_preflight_vs_saved_version",
            "ai_args": {
                "project": pm.project_name,
                "saved_version": fixture["stale_manual_version_id"],
            },
        },
        {
            "name": "autosave_vs_snapshot_with_stale_snapshot_id",
            "route": "/api/preflight/compare_autosave_vs_snapshot_version",
            "route_payload": {
                "project_name": pm.project_name,
                "autosave_snapshot_version_id": fixture["stale_snapshot_version_id"],
            },
            "tool": "compare_autosave_preflight_vs_snapshot_version",
            "ai_args": {
                "project": pm.project_name,
                "snapshot_version_id": fixture["stale_snapshot_version_id"],
            },
        },
        {
            "name": "compare_versions_with_stale_manual_candidate_id",
            "route": "/api/preflight/compare_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version_id": fixture["active_manual_version_id"],
                "candidate_version_id": fixture["stale_manual_version_id"],
            },
            "tool": "compare_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "baseline": fixture["active_manual_version_id"],
                "candidate_version": fixture["stale_manual_version_id"],
            },
        },
        {
            "name": "compare_snapshot_versions_with_stale_candidate_id",
            "route": "/api/preflight/compare_snapshot_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_snapshot_version_id": fixture["active_snapshot_version_id"],
                "candidate_snapshot_version_id": fixture["stale_snapshot_version_id"],
            },
            "tool": "compare_autosave_snapshot_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "baseline_snapshot_version": fixture["active_snapshot_version_id"],
                "candidate": fixture["stale_snapshot_version_id"],
            },
        },
    ]

    for case in stale_workflow_cases:
        status_code, route_data = _call_preflight_route_with_pm(pm, case["route"], case["route_payload"])
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == 404, case["name"]
        assert route_data == ai_data, case["name"]
        _assert_compare_ai_error_payload_excludes_success_metadata(route_data)
        assert "not found" in route_data["error"].lower(), case["name"]


def test_preflight_list_manual_saved_versions_for_simulation_run_route_and_ai_wrappers_share_stale_version_metadata_payloads(pm, tmp_path):
    fixture = _seed_preflight_run_selector_stale_version_fixture(pm, tmp_path)

    status_code, route_data = _call_preflight_route_with_pm(
        pm,
        "/api/preflight/list_manual_saved_versions_for_simulation_run",
        {
            "project_name": pm.project_name,
            "run_id": fixture["simulation_run_id"],
        },
    )
    ai_data = dispatch_ai_tool(pm, "list_manual_saved_versions_for_simulation_run", {
        "project": pm.project_name,
        "simulation_run_id": fixture["simulation_run_id"],
    })

    assert status_code == 200
    assert route_data == ai_data
    assert route_data["success"] is True
    assert route_data["total_matching_manual_saved_versions"] == 2
    assert route_data["returned_matching_manual_saved_versions"] == 2

    ordered_ids = [entry["version_id"] for entry in route_data["matching_manual_saved_versions"]]

    stale_entry = next(
        entry
        for entry in route_data["matching_manual_saved_versions"]
        if entry["version_id"] == fixture["stale_selected_version_id"]
    )
    assert stale_entry["manual_saved_index"] == ordered_ids.index(fixture["stale_selected_version_id"])
    assert stale_entry["has_version_json"] is False
    assert stale_entry["version_json_mtime_utc"] is None
    assert stale_entry["timestamp_source"] == "version_id_prefix"
    assert stale_entry["source_path_checks"]["version_json_within_versions_root"] is True

    older_entry = next(
        entry
        for entry in route_data["matching_manual_saved_versions"]
        if entry["version_id"] == fixture["oldest_matching_version_id"]
    )
    assert older_entry["manual_saved_index"] == ordered_ids.index(fixture["oldest_matching_version_id"])
    assert older_entry["has_version_json"] is True
    assert older_entry["version_json_mtime_utc"] is not None


def test_preflight_run_selector_list_to_compare_workflow_route_and_ai_is_reproducible_with_mixed_stale_artifacts(pm, tmp_path):
    fixture = _seed_preflight_run_selector_stale_version_fixture(pm, tmp_path)

    list_status_code, list_route_data = _call_preflight_route_with_pm(
        pm,
        "/api/preflight/list_manual_saved_versions_for_simulation_run",
        {
            "project_name": pm.project_name,
            "job_id": fixture["simulation_run_id"],
        },
    )
    list_ai_data = dispatch_ai_tool(pm, "list_manual_saved_versions_for_simulation_run", {
        "project": pm.project_name,
        "run_id": fixture["simulation_run_id"],
    })

    assert list_status_code == 200
    assert list_route_data == list_ai_data
    assert list_route_data["success"] is True
    assert list_route_data["total_matching_manual_saved_versions"] == 2
    assert list_route_data["returned_matching_manual_saved_versions"] == 2

    matching_versions = list_route_data["matching_manual_saved_versions"]
    stale_entry = next(entry for entry in matching_versions if entry["has_version_json"] is False)
    valid_entry = next(entry for entry in matching_versions if entry["has_version_json"] is True)

    workflow_cases = [
        {
            "name": "autosave_vs_run_index_stale_entry",
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index",
            "route_payload": {
                "project_name": pm.project_name,
                "run_id": fixture["simulation_run_id"],
                "n_back": stale_entry["manual_saved_index"],
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index",
            "ai_args": {
                "project": pm.project_name,
                "job_id": fixture["simulation_run_id"],
                "index": stale_entry["manual_saved_index"],
            },
            "expected_status": 404,
            "expect_error_version_id": stale_entry["version_id"],
        },
        {
            "name": "manual_run_indices_with_stale_candidate",
            "route": "/api/preflight/compare_manual_saved_versions_for_simulation_run_indices",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": fixture["simulation_run_id"],
                "baseline_n_back": valid_entry["manual_saved_index"],
                "candidate_n_back": stale_entry["manual_saved_index"],
            },
            "tool": "compare_manual_preflight_versions_for_simulation_run_indices",
            "ai_args": {
                "project": pm.project_name,
                "run_id": fixture["simulation_run_id"],
                "baseline_index": valid_entry["manual_saved_index"],
                "candidate_index": stale_entry["manual_saved_index"],
            },
            "expected_status": 404,
            "expect_error_version_id": stale_entry["version_id"],
        },
        {
            "name": "explicit_compare_with_stale_id_from_list",
            "route": "/api/preflight/compare_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version": valid_entry["version_id"],
                "candidate_version_id": stale_entry["version_id"],
            },
            "tool": "compare_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "before_version": valid_entry["version_id"],
                "new_version": stale_entry["version_id"],
            },
            "expected_status": 404,
            "expect_error_version_id": stale_entry["version_id"],
        },
        {
            "name": "autosave_vs_run_index_valid_entry",
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": fixture["simulation_run_id"],
                "manual_saved_index": valid_entry["manual_saved_index"],
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index",
            "ai_args": {
                "project_name": pm.project_name,
                "simulation_run_id": fixture["simulation_run_id"],
                "manual_saved_n_back": valid_entry["manual_saved_index"],
            },
            "expected_status": 200,
            "expected_baseline_version_id": valid_entry["version_id"],
            "expected_candidate_version_id": "autosave",
            "expected_selection_ordering_basis": "matching_manual_saved_versions_sorted_desc_lexicographic",
        },
    ]

    successful_case_response = None
    successful_case = None

    for case in workflow_cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == case["expected_status"], case["name"]
        assert route_data == ai_data, case["name"]

        if case["expected_status"] == 200:
            assert route_data["success"] is True, case["name"]
            assert route_data["baseline_version_id"] == case["expected_baseline_version_id"], case["name"]
            assert route_data["candidate_version_id"] == case["expected_candidate_version_id"], case["name"]
            _assert_compare_ai_selection_and_source_metadata(
                route_data,
                baseline_version_id=case["expected_baseline_version_id"],
                candidate_version_id=case["expected_candidate_version_id"],
                selection_ordering_basis=case["expected_selection_ordering_basis"],
            )
            successful_case_response = route_data
            successful_case = case
        else:
            _assert_compare_ai_error_payload_excludes_success_metadata(route_data)
            assert "not found" in route_data["error"].lower(), case["name"]
            assert case["expect_error_version_id"] in route_data["error"], case["name"]

    assert successful_case_response is not None
    assert successful_case is not None

    replay_pm = ProjectManager(ExpressionEvaluator())
    replay_pm.create_empty_project()
    replay_pm.projects_dir = pm.projects_dir
    replay_pm.project_name = pm.project_name

    replay_list_status_code, replay_list_route_data = _call_preflight_route_with_pm(
        replay_pm,
        "/api/preflight/list_manual_saved_versions_for_simulation_run",
        {
            "project_name": replay_pm.project_name,
            "run_id": fixture["simulation_run_id"],
        },
    )
    replay_list_ai_data = dispatch_ai_tool(replay_pm, "list_manual_saved_versions_for_simulation_run", {
        "project_name": replay_pm.project_name,
        "job_id": fixture["simulation_run_id"],
    })

    assert replay_list_status_code == 200
    assert replay_list_route_data == list_route_data
    assert replay_list_ai_data == list_route_data

    replay_success_status_code, replay_success_route_data = _call_preflight_route_with_pm(
        replay_pm,
        successful_case["route"],
        successful_case["route_payload"],
    )
    replay_success_ai_data = dispatch_ai_tool(
        replay_pm,
        successful_case["tool"],
        successful_case["ai_args"],
    )

    assert replay_success_status_code == 200
    assert replay_success_route_data == successful_case_response
    assert replay_success_ai_data == successful_case_response


def test_preflight_compare_versions_route_and_ai_wrappers_share_missing_and_stale_error_envelopes(pm, tmp_path):
    fixture = _seed_preflight_compare_versions_error_parity_fixture(pm, tmp_path)

    missing_baseline_version_id = "20990101_missing_compare_versions_baseline_for_route_ai_parity"
    missing_candidate_version_id = "20990101_missing_compare_versions_candidate_for_route_ai_parity"

    cases = [
        {
            "name": "missing_baseline_version_id",
            "route_payload": {
                "project_name": pm.project_name,
                "candidate_version": fixture["candidate_version_id"],
            },
            "ai_args": {
                "project": pm.project_name,
                "after_version": fixture["candidate_version_id"],
            },
            "expected_status": 400,
            "error_substring": "missing required fields",
        },
        {
            "name": "missing_candidate_version_id",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version": fixture["baseline_version_id"],
            },
            "ai_args": {
                "project": pm.project_name,
                "before_version": fixture["baseline_version_id"],
            },
            "expected_status": 400,
            "error_substring": "missing required fields",
        },
        {
            "name": "stale_baseline_version_id",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version": missing_baseline_version_id,
                "candidate_version_id": fixture["candidate_version_id"],
            },
            "ai_args": {
                "project_name": pm.project_name,
                "baseline": missing_baseline_version_id,
                "candidate": fixture["candidate_version_id"],
            },
            "expected_status": 404,
            "error_substring": "not found",
            "missing_version_id": missing_baseline_version_id,
        },
        {
            "name": "stale_candidate_version_id",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version_id": fixture["baseline_version_id"],
                "candidate_version": missing_candidate_version_id,
            },
            "ai_args": {
                "project": pm.project_name,
                "before_version": fixture["baseline_version_id"],
                "new_version": missing_candidate_version_id,
            },
            "expected_status": 404,
            "error_substring": "not found",
            "missing_version_id": missing_candidate_version_id,
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            "/api/preflight/compare_versions",
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, "compare_preflight_versions", case["ai_args"])

        assert status_code == case["expected_status"], case["name"]
        assert route_data == ai_data, case["name"]
        _assert_compare_ai_error_payload_excludes_success_metadata(route_data)
        assert case["error_substring"] in route_data["error"].lower(), case["name"]

        missing_version_id = case.get("missing_version_id")
        if missing_version_id is not None:
            assert missing_version_id in route_data["error"], case["name"]



def test_preflight_compare_versions_route_and_ai_wrappers_share_invalid_id_validation_error_envelopes(pm, tmp_path):
    fixture = _seed_preflight_compare_versions_error_parity_fixture(pm, tmp_path)

    cases = [
        {
            "name": "empty_baseline_id",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version": "",
                "candidate_version": fixture["candidate_version_id"],
            },
            "ai_args": {
                "project": pm.project_name,
                "before_version": "",
                "new_version": fixture["candidate_version_id"],
            },
            "error_substrings": ["version_id", "non-empty string"],
        },
        {
            "name": "whitespace_candidate_id",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version_id": fixture["baseline_version_id"],
                "candidate_version": "   ",
            },
            "ai_args": {
                "project_name": pm.project_name,
                "baseline_version_id": fixture["baseline_version_id"],
                "candidate_version": "   ",
            },
            "error_substrings": ["version_id", "non-empty string"],
        },
        {
            "name": "path_traversal_baseline_id",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version_id": "../outside_versions_root",
                "candidate_version_id": fixture["candidate_version_id"],
            },
            "ai_args": {
                "project": pm.project_name,
                "baseline": "../outside_versions_root",
                "candidate": fixture["candidate_version_id"],
            },
            "error_substrings": ["invalid version_id", "outside_versions_root"],
        },
        {
            "name": "absolute_path_candidate_id",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version": fixture["baseline_version_id"],
                "candidate_version_id": "/tmp/airpet_escape_candidate",
            },
            "ai_args": {
                "project": pm.project_name,
                "before_version": fixture["baseline_version_id"],
                "new_version": "/tmp/airpet_escape_candidate",
            },
            "error_substrings": ["invalid version_id", "/tmp/airpet_escape_candidate"],
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            "/api/preflight/compare_versions",
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, "compare_preflight_versions", case["ai_args"])

        assert status_code == 400, case["name"]
        assert route_data == ai_data, case["name"]
        _assert_compare_ai_error_payload_excludes_success_metadata(route_data)

        error_lower = route_data["error"].lower()
        for expected_substring in case["error_substrings"]:
            assert expected_substring.lower() in error_lower, case["name"]



def test_preflight_compare_versions_route_and_ai_wrappers_share_canonical_alias_precedence_payloads(pm, tmp_path):
    fixture = _seed_preflight_compare_versions_error_parity_fixture(pm, tmp_path)

    cases = [
        {
            "name": "canonical_ids_override_conflicting_alias_ids",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version_id": fixture["baseline_version_id"],
                "baseline_version": "20990101_missing_alias_baseline_conflict",
                "candidate_version_id": fixture["candidate_version_id"],
                "candidate_version": "20990101_missing_alias_candidate_conflict",
            },
            "ai_args": {
                "project": pm.project_name,
                "baseline_version_id": fixture["baseline_version_id"],
                "before_version": "20990101_missing_alias_baseline_conflict",
                "candidate_version_id": fixture["candidate_version_id"],
                "new_version": "20990101_missing_alias_candidate_conflict",
            },
            "expected_status": 200,
            "expected_baseline_version_id": fixture["baseline_version_id"],
            "expected_candidate_version_id": fixture["candidate_version_id"],
        },
        {
            "name": "null_canonical_ids_fall_back_to_alias_ids",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version_id": None,
                "baseline_version": fixture["baseline_version_id"],
                "candidate_version_id": None,
                "candidate_version": fixture["candidate_version_id"],
            },
            "ai_args": {
                "project": pm.project_name,
                "baseline_version_id": None,
                "before_version": fixture["baseline_version_id"],
                "candidate_version_id": None,
                "new_version": fixture["candidate_version_id"],
            },
            "expected_status": 200,
            "expected_baseline_version_id": fixture["baseline_version_id"],
            "expected_candidate_version_id": fixture["candidate_version_id"],
        },
        {
            "name": "empty_canonical_baseline_id_does_not_fall_back_to_alias",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version_id": "",
                "baseline_version": fixture["baseline_version_id"],
                "candidate_version": fixture["candidate_version_id"],
            },
            "ai_args": {
                "project": pm.project_name,
                "baseline_version_id": "",
                "before_version": fixture["baseline_version_id"],
                "new_version": fixture["candidate_version_id"],
            },
            "expected_status": 400,
            "error_substrings": ["version_id", "non-empty string"],
        },
        {
            "name": "whitespace_canonical_candidate_id_does_not_fall_back_to_alias",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version": fixture["baseline_version_id"],
                "candidate_version_id": "   ",
                "candidate_version": fixture["candidate_version_id"],
            },
            "ai_args": {
                "project": pm.project_name,
                "before_version": fixture["baseline_version_id"],
                "candidate_version_id": "   ",
                "new_version": fixture["candidate_version_id"],
            },
            "expected_status": 400,
            "error_substrings": ["version_id", "non-empty string"],
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            "/api/preflight/compare_versions",
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, "compare_preflight_versions", case["ai_args"])

        assert status_code == case["expected_status"], case["name"]
        assert route_data == ai_data, case["name"]

        if case["expected_status"] == 200:
            assert route_data["success"] is True, case["name"]
            _assert_compare_ai_selection_and_source_metadata(
                route_data,
                baseline_version_id=case["expected_baseline_version_id"],
                candidate_version_id=case["expected_candidate_version_id"],
            )
            continue

        _assert_compare_ai_error_payload_excludes_success_metadata(route_data)
        error_lower = route_data["error"].lower()
        for expected_substring in case["error_substrings"]:
            assert expected_substring.lower() in error_lower, case["name"]



def test_preflight_explicit_compare_selector_routes_and_ai_wrappers_share_required_field_validation_error_envelopes(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_route_compare_required_selector_parity_project"

    cases = [
        {
            "name": "compare_autosave_vs_saved_version_missing_saved_version_id",
            "route": "/api/preflight/compare_autosave_vs_saved_version",
            "route_payload": {
                "project_name": pm.project_name,
            },
            "tool": "compare_autosave_preflight_vs_saved_version",
            "ai_args": {
                "project": pm.project_name,
            },
            "error_substrings": ["missing required field", "saved_version_id"],
        },
        {
            "name": "compare_autosave_vs_snapshot_version_missing_snapshot_version_id",
            "route": "/api/preflight/compare_autosave_vs_snapshot_version",
            "route_payload": {
                "project_name": pm.project_name,
            },
            "tool": "compare_autosave_preflight_vs_snapshot_version",
            "ai_args": {
                "project": pm.project_name,
            },
            "error_substrings": ["missing required field", "autosave_snapshot_version_id"],
        },
        {
            "name": "compare_snapshot_versions_missing_baseline_snapshot_version_id",
            "route": "/api/preflight/compare_snapshot_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "candidate_snapshot_version_id": "20990101_autosave_snapshot_candidate_present",
            },
            "tool": "compare_autosave_snapshot_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "candidate_snapshot_version_id": "20990101_autosave_snapshot_candidate_present",
            },
            "error_substrings": ["missing required field", "baseline_snapshot_version_id"],
        },
        {
            "name": "compare_snapshot_versions_missing_candidate_snapshot_version_id",
            "route": "/api/preflight/compare_snapshot_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version_id": "20990101_autosave_snapshot_baseline_present",
            },
            "tool": "compare_autosave_snapshot_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "baseline_version_id": "20990101_autosave_snapshot_baseline_present",
            },
            "error_substrings": ["missing required field", "candidate_snapshot_version_id"],
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == 400, case["name"]
        assert route_data == ai_data, case["name"]
        _assert_compare_ai_error_payload_excludes_success_metadata(route_data)

        error_lower = route_data["error"].lower()
        for expected_substring in case["error_substrings"]:
            assert expected_substring in error_lower, case["name"]



def test_preflight_run_selector_routes_and_ai_wrappers_share_required_field_validation_error_envelopes(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_route_run_selector_required_field_parity_project"

    cases = [
        {
            "name": "compare_autosave_vs_manual_saved_for_run_missing_simulation_run_id",
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run",
            "route_payload": {
                "project_name": pm.project_name,
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run",
            "ai_args": {
                "project": pm.project_name,
            },
            "assert_error_shape": _assert_compare_ai_error_payload_excludes_success_metadata,
        },
        {
            "name": "compare_autosave_vs_manual_saved_for_run_index_missing_simulation_run_id",
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index",
            "route_payload": {
                "project_name": pm.project_name,
                "manual_saved_index": 0,
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index",
            "ai_args": {
                "project": pm.project_name,
                "manual_saved_index": 0,
            },
            "assert_error_shape": _assert_compare_ai_error_payload_excludes_success_metadata,
        },
        {
            "name": "compare_manual_saved_for_run_indices_missing_simulation_run_id",
            "route": "/api/preflight/compare_manual_saved_versions_for_simulation_run_indices",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_manual_saved_index": 1,
                "candidate_manual_saved_index": 0,
            },
            "tool": "compare_manual_preflight_versions_for_simulation_run_indices",
            "ai_args": {
                "project": pm.project_name,
                "baseline_manual_saved_index": 1,
                "candidate_manual_saved_index": 0,
            },
            "assert_error_shape": _assert_compare_ai_error_payload_excludes_success_metadata,
        },
        {
            "name": "list_manual_saved_for_run_missing_simulation_run_id",
            "route": "/api/preflight/list_manual_saved_versions_for_simulation_run",
            "route_payload": {
                "project_name": pm.project_name,
            },
            "tool": "list_manual_saved_versions_for_simulation_run",
            "ai_args": {
                "project": pm.project_name,
            },
            "assert_error_shape": _assert_preflight_list_ai_error_payload_excludes_success_metadata,
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == 400, case["name"]
        assert route_data == ai_data, case["name"]
        case["assert_error_shape"](route_data)

        error_lower = route_data["error"].lower()
        for expected_substring in ("missing required field", "simulation_run_id", "run_id/job_id"):
            assert expected_substring in error_lower, case["name"]



def test_preflight_run_selector_routes_and_ai_wrappers_honor_run_id_aliases_when_canonical_ids_are_null(pm, tmp_path):
    fixture = _seed_preflight_compare_route_ai_parity_fixture(pm, tmp_path)

    cases = [
        {
            "name": "compare_autosave_vs_manual_saved_for_run_uses_run_id_alias_when_simulation_run_id_is_null",
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": None,
                "run_id": fixture["simulation_run_id"],
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": None,
                "run_id": fixture["simulation_run_id"],
            },
            "is_list_case": False,
        },
        {
            "name": "compare_autosave_vs_manual_saved_for_run_index_uses_job_id_alias_when_simulation_run_id_is_null",
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": None,
                "job_id": fixture["simulation_run_id"],
                "manual_saved_index": 0,
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": None,
                "job_id": fixture["simulation_run_id"],
                "manual_saved_index": 0,
            },
            "is_list_case": False,
        },
        {
            "name": "compare_manual_saved_for_run_indices_uses_run_id_alias_when_simulation_run_id_is_null",
            "route": "/api/preflight/compare_manual_saved_versions_for_simulation_run_indices",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": None,
                "run_id": fixture["simulation_run_id"],
                "baseline_manual_saved_index": 1,
                "candidate_manual_saved_index": 0,
            },
            "tool": "compare_manual_preflight_versions_for_simulation_run_indices",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": None,
                "run_id": fixture["simulation_run_id"],
                "baseline_manual_saved_index": 1,
                "candidate_manual_saved_index": 0,
            },
            "is_list_case": False,
        },
        {
            "name": "list_manual_saved_for_run_uses_job_id_alias_when_simulation_run_id_is_null",
            "route": "/api/preflight/list_manual_saved_versions_for_simulation_run",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": None,
                "job_id": fixture["simulation_run_id"],
                "count": 1,
            },
            "tool": "list_manual_saved_versions_for_simulation_run",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": None,
                "job_id": fixture["simulation_run_id"],
                "count": 1,
            },
            "is_list_case": True,
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == 200, case["name"]
        assert route_data == ai_data, case["name"]

        if case["is_list_case"]:
            assert route_data["success"] is True
            assert route_data["simulation_run_id"] == fixture["simulation_run_id"]
            assert route_data["returned_matching_manual_saved_versions"] == 1
        else:
            assert route_data["success"] is True
            assert route_data["selection"]["simulation_run_id"] == fixture["simulation_run_id"]



def test_preflight_run_selector_routes_and_ai_wrappers_share_canonical_alias_precedence_payloads(pm, tmp_path):
    fixture = _seed_preflight_compare_route_ai_parity_fixture(pm, tmp_path)
    conflicting_alias_run_id = "job_ai_route_compare_conflicting_alias"

    cases = [
        {
            "name": "compare_for_run_canonical_simulation_run_id_overrides_conflicting_run_id_alias",
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": fixture["simulation_run_id"],
                "run_id": conflicting_alias_run_id,
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": fixture["simulation_run_id"],
                "run_id": conflicting_alias_run_id,
            },
            "expected_status": 200,
            "expected_simulation_run_id": fixture["simulation_run_id"],
            "is_list_case": False,
        },
        {
            "name": "compare_for_run_index_null_canonical_prefers_run_id_alias_over_job_id_alias",
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": None,
                "run_id": fixture["simulation_run_id"],
                "job_id": conflicting_alias_run_id,
                "manual_saved_index": 0,
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": None,
                "run_id": fixture["simulation_run_id"],
                "job_id": conflicting_alias_run_id,
                "manual_saved_index": 0,
            },
            "expected_status": 200,
            "expected_simulation_run_id": fixture["simulation_run_id"],
            "is_list_case": False,
        },
        {
            "name": "compare_manual_indices_canonical_simulation_run_id_overrides_conflicting_job_id_alias",
            "route": "/api/preflight/compare_manual_saved_versions_for_simulation_run_indices",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": fixture["simulation_run_id"],
                "job_id": conflicting_alias_run_id,
                "baseline_manual_saved_index": 1,
                "candidate_manual_saved_index": 0,
            },
            "tool": "compare_manual_preflight_versions_for_simulation_run_indices",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": fixture["simulation_run_id"],
                "job_id": conflicting_alias_run_id,
                "baseline_manual_saved_index": 1,
                "candidate_manual_saved_index": 0,
            },
            "expected_status": 200,
            "expected_simulation_run_id": fixture["simulation_run_id"],
            "is_list_case": False,
        },
        {
            "name": "list_manual_saved_null_canonical_falls_back_to_job_id_alias_when_run_id_missing",
            "route": "/api/preflight/list_manual_saved_versions_for_simulation_run",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": None,
                "job_id": fixture["simulation_run_id"],
                "count": 1,
            },
            "tool": "list_manual_saved_versions_for_simulation_run",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": None,
                "job_id": fixture["simulation_run_id"],
                "count": 1,
            },
            "expected_status": 200,
            "expected_simulation_run_id": fixture["simulation_run_id"],
            "is_list_case": True,
            "expected_returned_matching_manual_saved_versions": 1,
        },
        {
            "name": "compare_for_run_empty_canonical_simulation_run_id_does_not_fall_back_to_alias",
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": "",
                "run_id": fixture["simulation_run_id"],
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": "",
                "run_id": fixture["simulation_run_id"],
            },
            "expected_status": 400,
            "is_list_case": False,
            "assert_error_shape": _assert_compare_ai_error_payload_excludes_success_metadata,
            "error_substrings": ["simulation_run_id", "required"],
        },
        {
            "name": "list_manual_saved_whitespace_canonical_simulation_run_id_does_not_fall_back_to_alias",
            "route": "/api/preflight/list_manual_saved_versions_for_simulation_run",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": "   ",
                "job_id": fixture["simulation_run_id"],
                "count": 1,
            },
            "tool": "list_manual_saved_versions_for_simulation_run",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": "   ",
                "job_id": fixture["simulation_run_id"],
                "count": 1,
            },
            "expected_status": 400,
            "is_list_case": True,
            "assert_error_shape": _assert_preflight_list_ai_error_payload_excludes_success_metadata,
            "error_substrings": ["simulation_run_id", "required"],
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == case["expected_status"], case["name"]
        assert route_data == ai_data, case["name"]

        if case["expected_status"] == 200:
            assert route_data["success"] is True, case["name"]
            expected_run_id = case["expected_simulation_run_id"]
            if case["is_list_case"]:
                assert route_data["simulation_run_id"] == expected_run_id, case["name"]
                expected_count = case.get("expected_returned_matching_manual_saved_versions")
                if expected_count is not None:
                    assert route_data["returned_matching_manual_saved_versions"] == expected_count, case["name"]
            else:
                assert route_data["selection"]["simulation_run_id"] == expected_run_id, case["name"]
            continue

        case["assert_error_shape"](route_data)
        error_lower = route_data["error"].lower()
        for expected_substring in case["error_substrings"]:
            assert expected_substring.lower() in error_lower, case["name"]



def test_preflight_run_selector_routes_and_ai_wrappers_share_malformed_id_validation_error_envelopes(pm, tmp_path):
    _seed_preflight_compare_route_ai_parity_fixture(pm, tmp_path)

    cases = [
        {
            "name": "compare_for_run_rejects_path_traversal_simulation_run_id",
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": "../outside_sim_runs_root",
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": "../outside_sim_runs_root",
            },
            "assert_error_shape": _assert_compare_ai_error_payload_excludes_success_metadata,
            "error_substrings": ["invalid simulation_run_id", "outside_sim_runs_root"],
        },
        {
            "name": "compare_for_run_index_rejects_absolute_path_run_id_alias",
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": None,
                "run_id": "/tmp/airpet_escape_run_id",
                "manual_saved_index": 0,
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": None,
                "run_id": "/tmp/airpet_escape_run_id",
                "manual_saved_index": 0,
            },
            "assert_error_shape": _assert_compare_ai_error_payload_excludes_success_metadata,
            "error_substrings": ["invalid simulation_run_id", "airpet_escape_run_id"],
        },
        {
            "name": "compare_manual_indices_rejects_dotdot_run_id_alias",
            "route": "/api/preflight/compare_manual_saved_versions_for_simulation_run_indices",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": None,
                "job_id": "..",
                "baseline_manual_saved_index": 1,
                "candidate_manual_saved_index": 0,
            },
            "tool": "compare_manual_preflight_versions_for_simulation_run_indices",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": None,
                "job_id": "..",
                "baseline_manual_saved_index": 1,
                "candidate_manual_saved_index": 0,
            },
            "assert_error_shape": _assert_compare_ai_error_payload_excludes_success_metadata,
            "error_substrings": ["invalid simulation_run_id", "'..'"],
        },
        {
            "name": "list_manual_saved_rejects_nested_path_simulation_run_id",
            "route": "/api/preflight/list_manual_saved_versions_for_simulation_run",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": "nested/run/id",
                "count": 1,
            },
            "tool": "list_manual_saved_versions_for_simulation_run",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": "nested/run/id",
                "count": 1,
            },
            "assert_error_shape": _assert_preflight_list_ai_error_payload_excludes_success_metadata,
            "error_substrings": ["invalid simulation_run_id", "nested/run/id"],
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == 400, case["name"]
        assert route_data == ai_data, case["name"]

        case["assert_error_shape"](route_data)
        error_lower = route_data["error"].lower()
        for expected_substring in case["error_substrings"]:
            assert expected_substring.lower() in error_lower, case["name"]



def test_preflight_explicit_compare_selector_routes_and_ai_wrappers_honor_aliases_when_canonical_ids_are_null(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_route_compare_null_canonical_alias_selector_parity_project"

    existing_snapshot_version_id, _ = pm.save_project_version('autosave_snapshot_existing_alias_target')

    missing_saved_version_id = "20990101_manual_missing_alias_fallback"
    missing_snapshot_baseline_id = "20990101_autosave_snapshot_missing_alias_baseline"
    missing_snapshot_candidate_id = "20990101_autosave_snapshot_missing_alias_candidate"

    cases = [
        {
            "name": "compare_autosave_vs_saved_version_uses_alias_when_saved_version_id_is_null",
            "route": "/api/preflight/compare_autosave_vs_saved_version",
            "route_payload": {
                "project_name": pm.project_name,
                "saved_version_id": None,
                "version_id": missing_saved_version_id,
            },
            "tool": "compare_autosave_preflight_vs_saved_version",
            "ai_args": {
                "project": pm.project_name,
                "saved_version_id": None,
                "version_id": missing_saved_version_id,
            },
            "expected_missing_version_id": missing_saved_version_id,
        },
        {
            "name": "compare_autosave_vs_snapshot_version_uses_alias_when_snapshot_id_is_null",
            "route": "/api/preflight/compare_autosave_vs_snapshot_version",
            "route_payload": {
                "project_name": pm.project_name,
                "autosave_snapshot_version_id": None,
                "snapshot_version": missing_snapshot_baseline_id,
            },
            "tool": "compare_autosave_preflight_vs_snapshot_version",
            "ai_args": {
                "project": pm.project_name,
                "autosave_snapshot_version_id": None,
                "snapshot_version": missing_snapshot_baseline_id,
            },
            "expected_missing_version_id": missing_snapshot_baseline_id,
        },
        {
            "name": "compare_snapshot_versions_uses_candidate_alias_when_candidate_id_is_null",
            "route": "/api/preflight/compare_snapshot_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_snapshot_version_id": None,
                "baseline_version_id": existing_snapshot_version_id,
                "candidate_snapshot_version_id": None,
                "candidate_version_id": missing_snapshot_candidate_id,
            },
            "tool": "compare_autosave_snapshot_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "baseline_snapshot_version_id": None,
                "baseline_version_id": existing_snapshot_version_id,
                "candidate_snapshot_version_id": None,
                "candidate_version_id": missing_snapshot_candidate_id,
            },
            "expected_missing_version_id": missing_snapshot_candidate_id,
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == 404, case["name"]
        assert route_data == ai_data, case["name"]
        _assert_compare_ai_error_payload_excludes_success_metadata(route_data)
        assert "not found" in route_data["error"].lower(), case["name"]
        assert case["expected_missing_version_id"] in route_data["error"], case["name"]



def test_preflight_snapshot_and_explicit_selector_routes_and_ai_wrappers_share_canonical_alias_precedence_payloads(pm, tmp_path):
    fixture = _seed_preflight_snapshot_route_ai_parity_fixture(pm, tmp_path)

    missing_saved_alias_conflict = "20990101_manual_missing_saved_alias_conflict"
    missing_snapshot_alias_conflict = "20990101_autosave_snapshot_missing_alias_conflict"
    missing_snapshot_baseline_alias_conflict = "20990101_autosave_snapshot_missing_baseline_alias_conflict"
    missing_snapshot_candidate_alias_conflict = "20990101_autosave_snapshot_missing_candidate_alias_conflict"

    cases = [
        {
            "name": "compare_autosave_vs_saved_version_canonical_saved_version_id_overrides_conflicting_aliases",
            "route": "/api/preflight/compare_autosave_vs_saved_version",
            "route_payload": {
                "project_name": pm.project_name,
                "saved_version_id": fixture["requested_saved_version_id"],
                "saved_version": missing_saved_alias_conflict,
                "version_id": "20990101_manual_missing_secondary_alias_conflict",
            },
            "tool": "compare_autosave_preflight_vs_saved_version",
            "ai_args": {
                "project": pm.project_name,
                "saved_version_id": fixture["requested_saved_version_id"],
                "saved_version": missing_saved_alias_conflict,
                "version_id": "20990101_manual_missing_secondary_alias_conflict",
            },
            "expected_status": 200,
            "expected_baseline_version_id": fixture["requested_saved_version_id"],
            "expected_selection_fields": {
                "saved_version_id": fixture["requested_saved_version_id"],
            },
        },
        {
            "name": "compare_autosave_vs_saved_version_null_canonical_prefers_saved_version_alias_over_version_id",
            "route": "/api/preflight/compare_autosave_vs_saved_version",
            "route_payload": {
                "project_name": pm.project_name,
                "saved_version_id": None,
                "saved_version": missing_saved_alias_conflict,
                "version_id": fixture["requested_saved_version_id"],
            },
            "tool": "compare_autosave_preflight_vs_saved_version",
            "ai_args": {
                "project": pm.project_name,
                "saved_version_id": None,
                "saved_version": missing_saved_alias_conflict,
                "version_id": fixture["requested_saved_version_id"],
            },
            "expected_status": 404,
            "assert_error_shape": _assert_compare_ai_error_payload_excludes_success_metadata,
            "error_substrings": ["not found"],
            "expected_error_version_id": missing_saved_alias_conflict,
        },
        {
            "name": "compare_autosave_vs_saved_version_empty_canonical_saved_version_id_does_not_fall_back_to_alias",
            "route": "/api/preflight/compare_autosave_vs_saved_version",
            "route_payload": {
                "project_name": pm.project_name,
                "saved_version_id": "",
                "saved_version": fixture["requested_saved_version_id"],
            },
            "tool": "compare_autosave_preflight_vs_saved_version",
            "ai_args": {
                "project": pm.project_name,
                "saved_version_id": "",
                "saved_version": fixture["requested_saved_version_id"],
            },
            "expected_status": 400,
            "assert_error_shape": _assert_compare_ai_error_payload_excludes_success_metadata,
            "error_substrings": ["saved_version_id", "required"],
        },
        {
            "name": "compare_autosave_vs_snapshot_version_canonical_snapshot_id_overrides_conflicting_aliases",
            "route": "/api/preflight/compare_autosave_vs_snapshot_version",
            "route_payload": {
                "project_name": pm.project_name,
                "autosave_snapshot_version_id": fixture["baseline_snapshot_version_id"],
                "snapshot_version_id": missing_snapshot_alias_conflict,
                "snapshot_version": "20990101_autosave_snapshot_missing_secondary_alias_conflict",
            },
            "tool": "compare_autosave_preflight_vs_snapshot_version",
            "ai_args": {
                "project": pm.project_name,
                "autosave_snapshot_version_id": fixture["baseline_snapshot_version_id"],
                "snapshot_version_id": missing_snapshot_alias_conflict,
                "snapshot_version": "20990101_autosave_snapshot_missing_secondary_alias_conflict",
            },
            "expected_status": 200,
            "expected_baseline_version_id": fixture["baseline_snapshot_version_id"],
            "expected_selection_fields": {
                "autosave_snapshot_version_id": fixture["baseline_snapshot_version_id"],
            },
        },
        {
            "name": "compare_autosave_vs_snapshot_version_null_canonical_prefers_snapshot_version_id_alias_over_snapshot_version",
            "route": "/api/preflight/compare_autosave_vs_snapshot_version",
            "route_payload": {
                "project_name": pm.project_name,
                "autosave_snapshot_version_id": None,
                "snapshot_version_id": missing_snapshot_alias_conflict,
                "snapshot_version": fixture["baseline_snapshot_version_id"],
            },
            "tool": "compare_autosave_preflight_vs_snapshot_version",
            "ai_args": {
                "project": pm.project_name,
                "autosave_snapshot_version_id": None,
                "snapshot_version_id": missing_snapshot_alias_conflict,
                "snapshot_version": fixture["baseline_snapshot_version_id"],
            },
            "expected_status": 404,
            "assert_error_shape": _assert_compare_ai_error_payload_excludes_success_metadata,
            "error_substrings": ["not found"],
            "expected_error_version_id": missing_snapshot_alias_conflict,
        },
        {
            "name": "compare_autosave_vs_snapshot_version_whitespace_canonical_snapshot_id_does_not_fall_back_to_alias",
            "route": "/api/preflight/compare_autosave_vs_snapshot_version",
            "route_payload": {
                "project_name": pm.project_name,
                "autosave_snapshot_version_id": "   ",
                "snapshot_version": fixture["baseline_snapshot_version_id"],
            },
            "tool": "compare_autosave_preflight_vs_snapshot_version",
            "ai_args": {
                "project": pm.project_name,
                "autosave_snapshot_version_id": "   ",
                "snapshot_version": fixture["baseline_snapshot_version_id"],
            },
            "expected_status": 400,
            "assert_error_shape": _assert_compare_ai_error_payload_excludes_success_metadata,
            "error_substrings": ["autosave_snapshot_version_id", "required"],
        },
        {
            "name": "compare_snapshot_versions_canonical_snapshot_ids_override_conflicting_aliases",
            "route": "/api/preflight/compare_snapshot_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_snapshot_version_id": fixture["baseline_snapshot_version_id"],
                "baseline_version_id": missing_snapshot_baseline_alias_conflict,
                "candidate_snapshot_version_id": fixture["candidate_snapshot_version_id"],
                "candidate_version_id": missing_snapshot_candidate_alias_conflict,
            },
            "tool": "compare_autosave_snapshot_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "baseline_snapshot_version_id": fixture["baseline_snapshot_version_id"],
                "baseline_version_id": missing_snapshot_baseline_alias_conflict,
                "candidate_snapshot_version_id": fixture["candidate_snapshot_version_id"],
                "candidate_version_id": missing_snapshot_candidate_alias_conflict,
            },
            "expected_status": 200,
            "expected_baseline_version_id": fixture["baseline_snapshot_version_id"],
            "expected_candidate_version_id": fixture["candidate_snapshot_version_id"],
            "expected_selection_fields": {
                "baseline_snapshot_version_id": fixture["baseline_snapshot_version_id"],
                "candidate_snapshot_version_id": fixture["candidate_snapshot_version_id"],
            },
        },
        {
            "name": "compare_snapshot_versions_null_canonical_prefers_snapshot_aliases_over_version_id_aliases",
            "route": "/api/preflight/compare_snapshot_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_snapshot_version_id": None,
                "baseline_snapshot_version": fixture["baseline_snapshot_version_id"],
                "baseline_version_id": missing_snapshot_baseline_alias_conflict,
                "candidate_snapshot_version_id": None,
                "candidate_snapshot_version": fixture["candidate_snapshot_version_id"],
                "candidate_version_id": missing_snapshot_candidate_alias_conflict,
            },
            "tool": "compare_autosave_snapshot_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "baseline_snapshot_version_id": None,
                "baseline_snapshot_version": fixture["baseline_snapshot_version_id"],
                "baseline_version_id": missing_snapshot_baseline_alias_conflict,
                "candidate_snapshot_version_id": None,
                "candidate_snapshot_version": fixture["candidate_snapshot_version_id"],
                "candidate_version_id": missing_snapshot_candidate_alias_conflict,
            },
            "expected_status": 200,
            "expected_baseline_version_id": fixture["baseline_snapshot_version_id"],
            "expected_candidate_version_id": fixture["candidate_snapshot_version_id"],
            "expected_selection_fields": {
                "baseline_snapshot_version_id": fixture["baseline_snapshot_version_id"],
                "candidate_snapshot_version_id": fixture["candidate_snapshot_version_id"],
            },
        },
        {
            "name": "compare_snapshot_versions_empty_canonical_candidate_snapshot_id_does_not_fall_back_to_alias",
            "route": "/api/preflight/compare_snapshot_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_snapshot_version": fixture["baseline_snapshot_version_id"],
                "candidate_snapshot_version_id": "",
                "candidate_version_id": fixture["candidate_snapshot_version_id"],
            },
            "tool": "compare_autosave_snapshot_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "baseline_snapshot_version": fixture["baseline_snapshot_version_id"],
                "candidate_snapshot_version_id": "",
                "candidate_version_id": fixture["candidate_snapshot_version_id"],
            },
            "expected_status": 400,
            "assert_error_shape": _assert_compare_ai_error_payload_excludes_success_metadata,
            "error_substrings": ["candidate_snapshot_version_id", "required"],
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == case["expected_status"], case["name"]
        assert route_data == ai_data, case["name"]

        if case["expected_status"] == 200:
            assert route_data["success"] is True, case["name"]

            expected_baseline_version_id = case.get("expected_baseline_version_id")
            if expected_baseline_version_id is not None:
                assert route_data["baseline_version_id"] == expected_baseline_version_id, case["name"]

            expected_candidate_version_id = case.get("expected_candidate_version_id")
            if expected_candidate_version_id is not None:
                assert route_data["candidate_version_id"] == expected_candidate_version_id, case["name"]

            for key, value in case.get("expected_selection_fields", {}).items():
                assert route_data["selection"][key] == value, case["name"]
            continue

        case["assert_error_shape"](route_data)
        error_lower = route_data["error"].lower()
        for expected_substring in case["error_substrings"]:
            assert expected_substring.lower() in error_lower, case["name"]

        expected_error_version_id = case.get("expected_error_version_id")
        if expected_error_version_id is not None:
            assert expected_error_version_id in route_data["error"], case["name"]



def test_preflight_compare_versions_route_and_ai_wrappers_share_topology_reference_corpus_transition_matrix_payloads(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_route_compare_corpus_transition_matrix"

    cases = [
        {
            "name": "missing_world_to_unknown_world",
            "baseline_seed": _seed_preflight_corpus_missing_world_volume_reference,
            "candidate_seed": _seed_preflight_corpus_unknown_world_volume_reference,
            "baseline_fingerprint": "e200719a2748b5a1257d7834478313d603069b4af59e02d1591b63198e9ad655",
            "candidate_fingerprint": "4e1d1b9ae63ee52a7b0a79ab3eef17e34c2cbad316e97a07b2bc677af946943e",
            "added_issue_codes": ["unknown_world_volume_reference"],
            "resolved_issue_codes": ["missing_world_volume_reference"],
            "counts_delta_by_code": {
                "missing_world_volume_reference": -1,
                "unknown_world_volume_reference": 1,
            },
            "issue_count_delta": 0,
        },
        {
            "name": "replica_bounds_to_division_bounds",
            "baseline_seed": _seed_preflight_corpus_bad_replica_reference_and_bounds,
            "candidate_seed": _seed_preflight_corpus_bad_division_axis_and_bounds,
            "baseline_fingerprint": "77e2b23966d15dedfd239104c5c0f9ded7f2097d26cc5553c337f9b1e102e9b5",
            "candidate_fingerprint": "f5eb06213fb26a40c39308753c6a740665cd651994d73642dc440a9ca9ba6094",
            "added_issue_codes": ["invalid_division_axis", "invalid_division_partition_bounds"],
            "resolved_issue_codes": [
                "invalid_replica_direction",
                "invalid_replica_instance_count",
                "invalid_replica_width",
                "unknown_procedural_volume_reference",
            ],
            "counts_delta_by_code": {
                "invalid_division_axis": 1,
                "invalid_division_partition_bounds": 1,
                "invalid_replica_direction": -1,
                "invalid_replica_instance_count": -1,
                "invalid_replica_width": -1,
                "unknown_procedural_volume_reference": -1,
            },
            "issue_count_delta": -2,
        },
        {
            "name": "division_bounds_to_lv_cycle",
            "baseline_seed": _seed_preflight_corpus_bad_division_axis_and_bounds,
            "candidate_seed": _seed_preflight_corpus_logical_volume_cycle,
            "baseline_fingerprint": "f5eb06213fb26a40c39308753c6a740665cd651994d73642dc440a9ca9ba6094",
            "candidate_fingerprint": "7401a86ee10d69b29b204e78a22a34ca7f8d481297c02193615ea33cb7e3d7d3",
            "added_issue_codes": ["placement_hierarchy_cycle"],
            "resolved_issue_codes": ["invalid_division_axis", "invalid_division_partition_bounds"],
            "counts_delta_by_code": {
                "invalid_division_axis": -1,
                "invalid_division_partition_bounds": -1,
                "placement_hierarchy_cycle": 1,
            },
            "issue_count_delta": -1,
        },
    ]

    expected_status = {
        "can_run_changed": False,
        "regressed_can_run": False,
        "improved_can_run": False,
        "fingerprint_changed": True,
    }

    for case in cases:
        baseline_version_id = _save_seeded_preflight_corpus_version(
            pm,
            seed=case["baseline_seed"],
            description=f"{case['name']}_baseline",
        )
        candidate_version_id = _save_seeded_preflight_corpus_version(
            pm,
            seed=case["candidate_seed"],
            description=f"{case['name']}_candidate",
        )

        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            "/api/preflight/compare_versions",
            {
                "project_name": pm.project_name,
                "baseline_version": baseline_version_id,
                "candidate_version_id": candidate_version_id,
            },
        )
        ai_data = dispatch_ai_tool(pm, "compare_preflight_versions", {
            "project": pm.project_name,
            "before_version": baseline_version_id,
            "after_version": candidate_version_id,
        })

        assert status_code == 200, case["name"]
        assert route_data == ai_data, case["name"]
        assert route_data["success"] is True, case["name"]

        comparison = route_data["comparison"]
        assert comparison["baseline"]["issue_fingerprint"] == case["baseline_fingerprint"], case["name"]
        assert comparison["candidate"]["issue_fingerprint"] == case["candidate_fingerprint"], case["name"]
        assert comparison["added_issue_codes"] == case["added_issue_codes"], case["name"]
        assert comparison["resolved_issue_codes"] == case["resolved_issue_codes"], case["name"]
        assert comparison["counts_delta_by_code"] == case["counts_delta_by_code"], case["name"]
        assert comparison["issue_count_delta"] == case["issue_count_delta"], case["name"]
        assert comparison["status"] == expected_status, case["name"]

        _assert_compare_ai_selection_and_source_metadata(
            route_data,
            baseline_version_id=baseline_version_id,
            candidate_version_id=candidate_version_id,
        )

        replay_pm = ProjectManager(ExpressionEvaluator())
        replay_pm.create_empty_project()
        replay_pm.projects_dir = pm.projects_dir
        replay_pm.project_name = pm.project_name

        replay_status_code, replay_route_data = _call_preflight_route_with_pm(
            replay_pm,
            "/api/preflight/compare_versions",
            {
                "project_name": replay_pm.project_name,
                "baseline_version_id": baseline_version_id,
                "candidate_version": candidate_version_id,
            },
        )
        replay_ai_data = dispatch_ai_tool(replay_pm, "compare_preflight_versions", {
            "project_name": replay_pm.project_name,
            "baseline_version_id": baseline_version_id,
            "candidate": candidate_version_id,
        })

        assert replay_status_code == 200, case["name"]
        assert replay_route_data == route_data, case["name"]
        assert replay_ai_data == route_data, case["name"]


def test_preflight_compare_routes_and_ai_wrappers_share_success_payloads(pm, tmp_path):
    fixture = _seed_preflight_compare_route_ai_parity_fixture(pm, tmp_path)

    cases = [
        {
            "route": "/api/preflight/compare_latest_versions",
            "route_payload": {"project_name": pm.project_name},
            "tool": "compare_latest_preflight_versions",
            "ai_args": {"project": pm.project_name},
        },
        {
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index",
            "route_payload": {
                "project_name": pm.project_name,
                "job_id": fixture["simulation_run_id"],
                "manual_saved_n_back": 0,
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index",
            "ai_args": {
                "project": pm.project_name,
                "job_id": fixture["simulation_run_id"],
                "manual_saved_n_back": 0,
            },
        },
        {
            "route": "/api/preflight/compare_manual_saved_versions_for_simulation_run_indices",
            "route_payload": {
                "project_name": pm.project_name,
                "run_id": fixture["simulation_run_id"],
                "baseline_n_back": 1,
                "candidate_n_back": 0,
            },
            "tool": "compare_manual_preflight_versions_for_simulation_run_indices",
            "ai_args": {
                "project": pm.project_name,
                "job_id": fixture["simulation_run_id"],
                "baseline_n_back": 1,
                "candidate_n_back": 0,
            },
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == 200
        assert route_data == ai_data
        assert route_data["success"] is True
        assert route_data["ordering_metadata"]["ordering_basis"] == "explicit_version_ids"


def test_preflight_compare_routes_and_ai_wrappers_share_failure_error_envelopes(pm, tmp_path):
    fixture = _seed_preflight_compare_route_ai_parity_fixture(pm, tmp_path)

    cases = [
        {
            "route": "/api/preflight/compare_autosave_vs_saved_version",
            "route_payload": {
                "project_name": pm.project_name,
                "saved_version_id": "20990101_missing_saved_for_parity",
            },
            "tool": "compare_autosave_preflight_vs_saved_version",
            "ai_args": {
                "project": pm.project_name,
                "saved_version": "20990101_missing_saved_for_parity",
            },
            "expected_status": 404,
            "error_substring": "not found",
        },
        {
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index",
            "route_payload": {
                "project_name": pm.project_name,
                "simulation_run_id": fixture["simulation_run_id"],
                "manual_saved_index": 99,
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": fixture["simulation_run_id"],
                "manual_saved_index": 99,
            },
            "expected_status": 400,
            "error_substring": "out of range",
        },
        {
            "route": "/api/preflight/compare_manual_saved_versions_for_simulation_run_indices",
            "route_payload": {
                "project_name": pm.project_name,
                "run_id": fixture["simulation_run_id"],
                "baseline_manual_saved_index": 0,
                "candidate_manual_saved_index": 0,
            },
            "tool": "compare_manual_preflight_versions_for_simulation_run_indices",
            "ai_args": {
                "project": pm.project_name,
                "job_id": fixture["simulation_run_id"],
                "baseline_index": 0,
                "candidate_index": 0,
            },
            "expected_status": 400,
            "error_substring": "must be different",
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == case["expected_status"]
        assert route_data == ai_data
        _assert_compare_ai_error_payload_excludes_success_metadata(route_data)
        assert case["error_substring"] in route_data["error"].lower()


def test_preflight_run_selector_routes_and_ai_wrappers_share_stale_id_404_error_envelopes(pm, tmp_path):
    fixture = _seed_preflight_run_selector_stale_version_fixture(pm, tmp_path)

    cases = [
        {
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run",
            "route_payload": {
                "project_name": pm.project_name,
                "run_id": fixture["simulation_run_id"],
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run",
            "ai_args": {
                "project": pm.project_name,
                "job_id": fixture["simulation_run_id"],
            },
        },
        {
            "route": "/api/preflight/compare_autosave_vs_manual_saved_for_simulation_run_index",
            "route_payload": {
                "project_name": pm.project_name,
                "job_id": fixture["simulation_run_id"],
                "n_back": 0,
            },
            "tool": "compare_autosave_preflight_vs_manual_saved_for_simulation_run_index",
            "ai_args": {
                "project": pm.project_name,
                "run_id": fixture["simulation_run_id"],
                "manual_saved_n_back": 0,
            },
        },
        {
            "route": "/api/preflight/compare_manual_saved_versions_for_simulation_run_indices",
            "route_payload": {
                "project_name": pm.project_name,
                "run_id": fixture["simulation_run_id"],
                "baseline_n_back": 1,
                "candidate_n_back": 0,
            },
            "tool": "compare_manual_preflight_versions_for_simulation_run_indices",
            "ai_args": {
                "project": pm.project_name,
                "simulation_run_id": fixture["simulation_run_id"],
                "baseline_index": 1,
                "candidate_index": 0,
            },
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == 404
        assert route_data == ai_data
        _assert_compare_ai_error_payload_excludes_success_metadata(route_data)
        assert "not found" in route_data["error"].lower()
        assert fixture["stale_selected_version_id"] in route_data["error"]



def test_preflight_compare_snapshot_and_explicit_routes_and_ai_wrappers_share_success_payloads(pm, tmp_path):
    fixture = _seed_preflight_snapshot_route_ai_parity_fixture(pm, tmp_path)

    cases = [
        {
            "name": "compare_autosave_vs_saved_version",
            "route": "/api/preflight/compare_autosave_vs_saved_version",
            "route_payload": {
                "project_name": pm.project_name,
                "version_id": fixture["requested_saved_version_id"],
            },
            "tool": "compare_autosave_preflight_vs_saved_version",
            "ai_args": {
                "project": pm.project_name,
                "saved_version": fixture["requested_saved_version_id"],
            },
            "selection_ordering_basis": "explicit_saved_version_id",
        },
        {
            "name": "compare_autosave_vs_snapshot_version",
            "route": "/api/preflight/compare_autosave_vs_snapshot_version",
            "route_payload": {
                "project_name": pm.project_name,
                "snapshot_version_id": fixture["baseline_snapshot_version_id"],
            },
            "tool": "compare_autosave_preflight_vs_snapshot_version",
            "ai_args": {
                "project": pm.project_name,
                "version_id": fixture["baseline_snapshot_version_id"],
            },
            "selection_ordering_basis": "explicit_autosave_snapshot_version_id",
        },
        {
            "name": "compare_autosave_vs_latest_snapshot",
            "route": "/api/preflight/compare_autosave_vs_latest_snapshot",
            "route_payload": {
                "project_name": pm.project_name,
            },
            "tool": "compare_autosave_preflight_vs_latest_snapshot",
            "ai_args": {
                "project": pm.project_name,
            },
            "selection_ordering_basis": "autosave_snapshot_versions_sorted_by_mtime_then_version_id_desc",
        },
        {
            "name": "compare_autosave_vs_previous_snapshot",
            "route": "/api/preflight/compare_autosave_vs_previous_snapshot",
            "route_payload": {
                "project_name": pm.project_name,
            },
            "tool": "compare_autosave_preflight_vs_previous_snapshot",
            "ai_args": {
                "project": pm.project_name,
            },
            "selection_ordering_basis": "autosave_snapshot_versions_sorted_by_mtime_then_version_id_desc",
        },
        {
            "name": "compare_snapshot_versions",
            "route": "/api/preflight/compare_snapshot_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_version": fixture["baseline_snapshot_version_id"],
                "candidate_version_id": fixture["candidate_snapshot_version_id"],
            },
            "tool": "compare_autosave_snapshot_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "baseline": fixture["baseline_snapshot_version_id"],
                "candidate_version": fixture["candidate_snapshot_version_id"],
            },
            "selection_ordering_basis": "explicit_autosave_snapshot_version_ids",
        },
        {
            "name": "compare_latest_snapshot_versions",
            "route": "/api/preflight/compare_latest_snapshot_versions",
            "route_payload": {
                "project_name": pm.project_name,
            },
            "tool": "compare_latest_autosave_snapshot_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
            },
            "selection_ordering_basis": "autosave_snapshot_versions_sorted_by_mtime_then_version_id_desc",
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == 200
        assert route_data == ai_data
        assert route_data["success"] is True
        assert route_data["ordering_metadata"]["ordering_basis"] == "explicit_version_ids"
        assert route_data["selection"]["ordering_basis"] == case["selection_ordering_basis"]



def test_preflight_snapshot_selector_routes_and_ai_wrappers_share_stale_id_404_error_envelopes(pm, tmp_path):
    fixture = _seed_preflight_snapshot_route_ai_parity_fixture(pm, tmp_path)

    missing_snapshot_version_id = "20990101_autosave_snapshot_missing_for_route_ai_parity"

    cases = [
        {
            "route": "/api/preflight/compare_autosave_vs_snapshot_version",
            "route_payload": {
                "project_name": pm.project_name,
                "snapshot_version": missing_snapshot_version_id,
            },
            "tool": "compare_autosave_preflight_vs_snapshot_version",
            "ai_args": {
                "project": pm.project_name,
                "autosave_snapshot_version": missing_snapshot_version_id,
            },
            "expected_status": 404,
        },
        {
            "route": "/api/preflight/compare_snapshot_versions",
            "route_payload": {
                "project_name": pm.project_name,
                "baseline_snapshot_version_id": fixture["baseline_snapshot_version_id"],
                "candidate_snapshot_version": missing_snapshot_version_id,
            },
            "tool": "compare_autosave_snapshot_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
                "baseline_snapshot_version": fixture["baseline_snapshot_version_id"],
                "candidate": missing_snapshot_version_id,
            },
            "expected_status": 404,
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == case["expected_status"]
        assert route_data == ai_data
        _assert_compare_ai_error_payload_excludes_success_metadata(route_data)
        assert "not found" in route_data["error"].lower()
        assert missing_snapshot_version_id in route_data["error"]



def test_preflight_snapshot_selector_routes_and_ai_wrappers_share_not_enough_versions_400_error_envelopes(pm, tmp_path):
    _seed_preflight_snapshot_insufficient_versions_fixture(pm, tmp_path)

    cases = [
        {
            "route": "/api/preflight/compare_autosave_vs_previous_snapshot",
            "route_payload": {
                "project_name": pm.project_name,
            },
            "tool": "compare_autosave_preflight_vs_previous_snapshot",
            "ai_args": {
                "project": pm.project_name,
            },
            "error_substring": "at least two saved autosave snapshot versions",
        },
        {
            "route": "/api/preflight/compare_latest_snapshot_versions",
            "route_payload": {
                "project_name": pm.project_name,
            },
            "tool": "compare_latest_autosave_snapshot_preflight_versions",
            "ai_args": {
                "project": pm.project_name,
            },
            "error_substring": "at least two saved autosave snapshot versions",
        },
    ]

    for case in cases:
        status_code, route_data = _call_preflight_route_with_pm(
            pm,
            case["route"],
            case["route_payload"],
        )
        ai_data = dispatch_ai_tool(pm, case["tool"], case["ai_args"])

        assert status_code == 400
        assert route_data == ai_data
        _assert_compare_ai_error_payload_excludes_success_metadata(route_data)
        assert case["error_substring"] in route_data["error"].lower()


def test_ai_simulation_tools(pm):
    # Setup for simulation
    with patch('threading.Thread') as MockThread, \
         patch('app.run_g4_simulation') as MockRunSim:
        
        # 1. Run simulation
        res = dispatch_ai_tool(pm, "run_simulation", {"events": 500})
        assert res['success']
        assert 'job_id' in res
        assert MockThread.called

        # 2. Check status
        from app import SIMULATION_STATUS, SIMULATION_LOCK
        job_id = res['job_id']
        with SIMULATION_LOCK:
            SIMULATION_STATUS[job_id] = {"status": "Finished", "progress": 500, "total_events": 500, "stdout": [], "stderr": []}
        
        res_status = dispatch_ai_tool(pm, "get_simulation_status", {"job_id": job_id})
        assert res_status['success']
        assert res_status['status'] == "Finished"


def test_ai_tool_get_simulation_status_supports_since_cursor(pm):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-cursor-1"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 20,
            "total_events": 100,
            "stdout": ["line-0", "line-1"],
            "stderr": ["err-0"],
        }

    res = dispatch_ai_tool(pm, "get_simulation_status", {
        "job_id": job_id,
        "since": 1,
        "include_logs": True,
    })

    assert res["success"], res
    assert res["status"] == "Running"
    assert res["log_total_lines"] == 3
    assert res["next_since"] == 3
    assert res["log_lines"] == ["line-1", "stderr: err-0"]


def test_ai_tool_get_simulation_status_tail_lines(pm):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-tail-1"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 2,
            "total_events": 10,
            "stdout": ["line-a", "line-b"],
            "stderr": ["err-a", "err-b"],
        }

    res = dispatch_ai_tool(pm, "get_simulation_status", {
        "job_id": job_id,
        "tail_lines": 2,
    })

    assert res["success"], res
    assert res["log_lines"] == ["stderr: err-a", "stderr: err-b"]
    assert res["returned_lines"] == 2


def test_ai_tool_get_simulation_status_supports_max_lines_pagination(pm):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-max-lines"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 20,
            "total_events": 100,
            "stdout": ["line-0", "line-1", "line-2"],
            "stderr": ["err-0"],
        }

    res_page_1 = dispatch_ai_tool(pm, "get_simulation_status", {
        "job_id": job_id,
        "since": 1,
        "max_lines": 2,
        "include_log_entries": True,
    })

    assert res_page_1["success"], res_page_1
    assert res_page_1["log_lines"] == ["line-1", "line-2"]
    assert res_page_1["next_since"] == 3
    assert res_page_1["has_more_logs"] is True
    assert res_page_1["log_entries"] == [
        {"cursor": 1, "source": "stdout", "line": "line-1"},
        {"cursor": 2, "source": "stdout", "line": "line-2"},
    ]

    res_page_2 = dispatch_ai_tool(pm, "get_simulation_status", {
        "job_id": job_id,
        "since": res_page_1["next_since"],
        "max_lines": 2,
    })

    assert res_page_2["success"], res_page_2
    assert res_page_2["log_lines"] == ["stderr: err-0"]
    assert res_page_2["next_since"] == 4
    assert res_page_2["has_more_logs"] is False


def test_ai_tool_get_simulation_status_limit_alias_maps_to_max_lines(pm):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-max-lines-alias"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 2,
            "total_events": 10,
            "stdout": ["line-a", "line-b", "line-c"],
            "stderr": [],
        }

    res = dispatch_ai_tool(pm, "get_simulation_status", {
        "job_id": job_id,
        "since": 0,
        "limit": 1,
    })

    assert res["success"], res
    assert res["log_lines"] == ["line-a"]
    assert res["next_since"] == 1
    assert res["has_more_logs"] is True


def test_ai_tool_get_simulation_status_log_source_filter(pm):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-log-source"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 42,
            "total_events": 100,
            "stdout": ["line-x", "line-y"],
            "stderr": ["error-1"],
        }

    res_stderr = dispatch_ai_tool(pm, "get_simulation_status", {
        "job_id": job_id,
        "log_source": "stderr",
        "include_logs": True,
    })

    assert res_stderr["success"], res_stderr
    assert res_stderr["log_lines"] == ["stderr: error-1"]
    assert res_stderr["log_total_lines"] == 1

    res_stdout = dispatch_ai_tool(pm, "get_simulation_status", {
        "job_id": job_id,
        "log_source": "stdout",
        "include_logs": True,
    })

    assert res_stdout["success"], res_stdout
    assert res_stdout["log_lines"] == ["line-x", "line-y"]
    assert res_stdout["log_total_lines"] == 2


def test_ai_tool_get_simulation_status_log_contains_filter(pm):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-log-contains"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 42,
            "total_events": 100,
            "stdout": ["init", "Warning: drift"],
            "stderr": ["fatal: overflow", "note: ignored"],
        }

    res = dispatch_ai_tool(pm, "get_simulation_status", {
        "job_id": job_id,
        "contains": "WARN",
        "include_logs": True,
        "include_log_entries": True,
    })

    assert res["success"], res
    assert res["log_lines"] == ["Warning: drift"]
    assert res["log_total_lines"] == 1
    assert res["next_since"] == 1
    assert res["log_entries"] == [
        {"cursor": 0, "source": "stdout", "line": "Warning: drift"},
    ]


def test_ai_tool_get_simulation_status_log_contains_any_filter(pm):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-log-contains-any"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 64,
            "total_events": 100,
            "stdout": ["init", "warning: drift", "done"],
            "stderr": ["fatal: overflow", "note: ignored"],
        }

    res = dispatch_ai_tool(pm, "get_simulation_status", {
        "job_id": job_id,
        "search_any": ["WARN", "fatal"],
        "include_logs": True,
        "include_log_entries": True,
    })

    assert res["success"], res
    assert res["log_lines"] == ["warning: drift", "stderr: fatal: overflow"]
    assert res["log_total_lines"] == 2
    assert res["next_since"] == 2
    assert res["log_entries"] == [
        {"cursor": 0, "source": "stdout", "line": "warning: drift"},
        {"cursor": 1, "source": "stderr", "line": "fatal: overflow"},
    ]


def test_ai_tool_get_simulation_status_log_contains_any_filter_supports_comma_separated_string(pm):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-log-contains-any-csv"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 90,
            "total_events": 100,
            "stdout": ["init", "warning: drift", "done"],
            "stderr": ["fatal: overflow", "note: ignored"],
        }

    res = dispatch_ai_tool(pm, "get_simulation_status", {
        "job_id": job_id,
        "log_contains_any": "WARN, fatal",
        "include_logs": True,
        "include_log_entries": True,
    })

    assert res["success"], res
    assert res["log_lines"] == ["warning: drift", "stderr: fatal: overflow"]
    assert res["log_total_lines"] == 2
    assert res["next_since"] == 2
    assert res["log_entries"] == [
        {"cursor": 0, "source": "stdout", "line": "warning: drift"},
        {"cursor": 1, "source": "stderr", "line": "fatal: overflow"},
    ]


def test_simulation_status_http_and_ai_share_log_payload_shape(pm):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-http-ai-parity"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 77,
            "total_events": 200,
            "stdout": ["boot", "warning: drift", "done"],
            "stderr": ["fatal: overflow", "note: ignored"],
        }

    try:
        ai_res = dispatch_ai_tool(pm, "get_simulation_status", {
            "job_id": job_id,
            "since": 0,
            "max_lines": 1,
            "include_log_summary": True,
            "include_log_entries": True,
            "log_contains_any": ["warn", "fatal"],
        })

        with flask_app.test_client() as client:
            http_res = client.get(
                f"/api/simulation/status/{job_id}"
                "?since=0"
                "&max_lines=1"
                "&include_log_summary=true"
                "&include_log_entries=true"
                "&log_contains_any=warn"
                "&log_contains_any=fatal"
            )

        assert ai_res["success"], ai_res
        assert http_res.status_code == 200

        http_status = http_res.get_json()["status"]

        for key in [
            "log_summary",
            "log_total_lines",
            "next_since",
            "has_more_logs",
            "log_lines",
            "returned_lines",
            "log_entries",
        ]:
            assert http_status[key] == ai_res[key]

        # HTTP route keeps legacy polling keys while matching AI payload content.
        assert http_status["new_stdout"] == ai_res["log_lines"]
        assert http_status["total_lines"] == ai_res["log_total_lines"]
    finally:
        with SIMULATION_LOCK:
            SIMULATION_STATUS.pop(job_id, None)


def test_simulation_status_http_and_ai_share_boundary_pagination_semantics(pm):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-http-ai-boundary-parity"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 77,
            "total_events": 200,
            "stdout": ["line-0", "line-1", "line-2"],
            "stderr": ["err-0"],
        }

    cases = [
        {
            "ai_args": {"since": 999, "include_log_entries": True},
            "http_query": "?since=999&include_log_entries=true",
        },
        {
            "ai_args": {"since": 1, "max_lines": 0, "include_log_entries": True},
            "http_query": "?since=1&max_lines=0&include_log_entries=true",
        },
    ]

    try:
        with flask_app.test_client() as client:
            for case in cases:
                ai_res = dispatch_ai_tool(pm, "get_simulation_status", {
                    "job_id": job_id,
                    **case["ai_args"],
                })
                http_res = client.get(f"/api/simulation/status/{job_id}{case['http_query']}")

                assert ai_res["success"], ai_res
                assert http_res.status_code == 200

                http_status = http_res.get_json()["status"]

                for key in [
                    "log_total_lines",
                    "next_since",
                    "has_more_logs",
                    "log_lines",
                    "returned_lines",
                    "log_entries",
                ]:
                    assert http_status[key] == ai_res[key]

                # HTTP route keeps legacy polling keys while matching AI payload content.
                assert http_status["new_stdout"] == ai_res["log_lines"]
                assert http_status["total_lines"] == ai_res["log_total_lines"]
    finally:
        with SIMULATION_LOCK:
            SIMULATION_STATUS.pop(job_id, None)


def test_ai_tool_get_simulation_status_include_log_entries(pm):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-log-entries"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 55,
            "total_events": 100,
            "stdout": ["line-0", "line-1"],
            "stderr": ["err-0"],
        }

    res = dispatch_ai_tool(pm, "get_simulation_status", {
        "job_id": job_id,
        "since": 1,
        "include_log_entries": True,
    })

    assert res["success"], res
    assert res["log_lines"] == ["line-1", "stderr: err-0"]
    assert res["log_entries"] == [
        {"cursor": 1, "source": "stdout", "line": "line-1"},
        {"cursor": 2, "source": "stderr", "line": "err-0"},
    ]


def test_ai_tool_get_simulation_status_includes_log_summary_without_logs(pm):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-summary-1"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 7,
            "total_events": 50,
            "stdout": ["boot", "step-1"],
            "stderr": ["warn-1"],
        }

    res = dispatch_ai_tool(pm, "get_simulation_status", {
        "job_id": job_id,
        "include_logs": False,
    })

    assert res["success"], res
    assert "log_lines" not in res
    assert res["log_summary"] == {
        "stdout_lines": 2,
        "stderr_lines": 1,
        "has_errors": True,
        "latest_stdout": "step-1",
        "latest_stderr": "warn-1",
    }


def test_ai_tool_get_simulation_status_can_disable_log_summary(pm):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-summary-2"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 1,
            "total_events": 10,
            "stdout": ["line-only"],
            "stderr": [],
        }

    res = dispatch_ai_tool(pm, "get_simulation_status", {
        "job_id": job_id,
        "include_logs": False,
        "include_log_summary": False,
    })

    assert res["success"], res
    assert "log_summary" not in res


def test_ai_analysis_summary(pm):
    # Mocking h5py File
    with patch('h5py.File') as MockFile:
        job_id = "test-job-id"
        pm.current_version_id = "test-version"
        
        mock_f = MockFile.return_value.__enter__.return_value
        
        # Mock 'default_ntuples/Hits' group
        mock_hits = MagicMock()
        mock_f.__contains__.side_effect = lambda k: k == 'default_ntuples/Hits'
        mock_f.__getitem__.return_value = mock_hits
        
        # Mock 'entries' dataset
        mock_entries = MagicMock()
        mock_entries.shape = ()
        mock_entries.__getitem__.return_value = 10
        
        # Mock 'ParticleName' dataset
        mock_names = MagicMock()
        mock_names.__getitem__.return_value = [b"gamma"] * 10
        
        # Setup __contains__ and __getitem__ for hits group
        def hits_getitem(key):
            if key == 'entries': return mock_entries
            if key == 'ParticleName': return mock_names
            return MagicMock()
            
        mock_hits.__getitem__.side_effect = hits_getitem
        mock_hits.__contains__.side_effect = lambda k: k in ['entries', 'ParticleName']
        
        with patch('os.path.exists', return_value=True):
            res = dispatch_ai_tool(pm, "get_analysis_summary", {"job_id": job_id})
            assert res['success'], f"Error: {res.get('error')}"
            assert res['summary']['total_hits'] == 10
            assert res['summary']['particle_breakdown']['gamma'] == 10

def test_ai_physics_template(pm):
    # Test inserting a phantom template
    res = dispatch_ai_tool(pm, "insert_physics_template", {
        "template_name": "phantom",
        "params": {"radius": 100, "length": 200},
        "parent_lv_name": "World",
        "position": {"x": 0, "y": 0, "z": 0}
    })
    
    assert res['success']
    assert any("Phantom_LV" in name for name in pm.current_geometry_state.logical_volumes)
    assert any("Phantom_Solid" in name for name in pm.current_geometry_state.solids)
    
    # Check if PV was placed
    world_lv = pm.current_geometry_state.logical_volumes["World"]
    assert any("Phantom_LV" in pv.volume_ref for pv in world_lv.content)


def test_ai_tool_accepts_stringified_json_args(pm):
    # Simulates providers that pass function arguments as a JSON string.
    res = dispatch_ai_tool(pm, "create_primitive_solid", '{"name":"S1","solid_type":"box","params":{"x":"1","y":"2","z":"3"}}')
    assert res['success'], res
    assert "S1" in pm.current_geometry_state.solids


def test_ai_tool_manage_surface_link_propagates_update_error(pm):
    # Setup a valid optical surface and LV + skin link.
    pm.add_optical_surface("Surf1", {
        "model": "unified",
        "finish": "polished",
        "surf_type": "dielectric_metal",
        "value": "1.0",
        "properties": {}
    })
    pm.add_solid("SkinBox", "box", {"x": "1", "y": "1", "z": "1"})
    pm.add_logical_volume("SkinLV", "SkinBox", "G4_Galactic")
    pm.add_skin_surface("Link1", "SkinLV", "Surf1")

    # Update existing link with invalid volume_ref should fail (not report false success).
    res = dispatch_ai_tool(pm, "manage_surface_link", {
        "name": "Link1",
        "link_type": "skin",
        "surface_ref": "Surf1",
        "volume_ref": "MissingLV"
    })

    assert not res['success']
    assert "not found" in res['error'].lower()


def test_ai_tool_manage_ui_group_invalid_action_returns_clean_error(pm):
    res = dispatch_ai_tool(pm, "manage_ui_group", {
        "group_type": "solid",
        "group_name": "G1",
        "action": "rename"
    })
    assert not res['success']
    assert "action" in res['error'].lower()


def test_ai_tool_camelcase_arg_normalization(pm):
    pm.add_solid("SmallBox2", "box", {"x": "10", "y": "10", "z": "10"})
    pm.add_logical_volume("SmallLV2", "SmallBox2", "G4_Galactic")

    # parentLvName / placedLvRef should normalize to snake_case keys.
    res = dispatch_ai_tool(pm, "place_volume", {
        "parentLvName": "World",
        "placedLvRef": "SmallLV2",
        "name": "PlacedViaCamel"
    })

    assert res['success'], res
    world_lv = pm.current_geometry_state.logical_volumes["World"]
    assert any(pv.name == "PlacedViaCamel" for pv in world_lv.content)


def test_ai_tool_manage_particle_source_create_and_update(pm):
    create_res = dispatch_ai_tool(pm, "manage_particle_source", {
        "action": "create",
        "name": "SrcAI",
        "gps_commands": {"particle": "gamma"},
        "activity": 2.5
    })
    assert create_res['success'], create_res
    source_id = create_res.get('source_id')
    assert source_id

    upd_res = dispatch_ai_tool(pm, "manage_particle_source", {
        "action": "update_transform",
        "source_id": source_id,
        "position": {"x": 1, "y": 2, "z": 3}
    })
    assert upd_res['success'], upd_res


def test_ai_tool_rename_ui_group(pm):
    dispatch_ai_tool(pm, "manage_ui_group", {
        "group_type": "solid",
        "group_name": "OldG",
        "action": "create"
    })

    res = dispatch_ai_tool(pm, "rename_ui_group", {
        "group_type": "solid",
        "old_name": "OldG",
        "new_name": "NewG"
    })
    assert res['success'], res


def test_ai_tool_route_bridge_process_lors(pm):
    with flask_app.test_request_context('/api/ai/chat', json={}):
        session['user_id'] = 'local_user'
        with patch('app.process_lors_route', return_value=(jsonify({"success": True, "message": "LOR processing started."}), 202)):
            res = dispatch_ai_tool(pm, "process_lors", {
                "version_id": "v1",
                "job_id": "job-1"
            })
    assert res['success'], res


def test_ai_tool_route_bridge_run_reconstruction(pm):
    with flask_app.test_request_context('/api/ai/chat', json={}):
        session['user_id'] = 'local_user'
        with patch('app.run_reconstruction_route', return_value=jsonify({"success": True, "message": "Reconstruction complete.", "image_shape": [64, 64, 64]})):
            res = dispatch_ai_tool(pm, "run_reconstruction", {
                "version_id": "v1",
                "job_id": "job-1",
                "iterations": 2
            })
    assert res['success'], res
    assert res.get('image_shape') == [64, 64, 64]


def test_ai_tool_stop_simulation(pm):
    fake_proc = MagicMock()
    fake_proc.poll.return_value = None

    with patch.dict('app.SIMULATION_PROCESSES', {'job-stop': fake_proc}, clear=False):
        res = dispatch_ai_tool(pm, "stop_simulation", {"job_id": "job-stop"})

    assert res['success'], res
    assert fake_proc.terminate.called


def test_ai_tool_set_active_source(pm):
    create_res = dispatch_ai_tool(pm, "manage_particle_source", {
        "action": "create",
        "name": "SrcActive",
        "gps_commands": {"particle": "gamma"}
    })
    source_id = create_res.get('source_id')

    on_res = dispatch_ai_tool(pm, "set_active_source", {"source_id": source_id})
    assert on_res['success'], on_res

    off_res = dispatch_ai_tool(pm, "set_active_source", {"source_id": source_id})
    assert off_res['success'], off_res


def test_ai_tool_route_bridge_compute_sensitivity(pm):
    with flask_app.test_request_context('/api/ai/chat', json={}):
        session['user_id'] = 'local_user'
        with patch('app.compute_sensitivity_route', return_value=jsonify({"success": True, "message": "Sensitivity Matrix computed."})):
            res = dispatch_ai_tool(pm, "compute_sensitivity", {
                "version_id": "v1",
                "job_id": "job-1"
            })
    assert res['success'], res


def test_ai_tool_route_bridge_get_metadata_and_analysis(pm):
    with flask_app.test_request_context('/api/ai/chat', json={}):
        session['user_id'] = 'local_user'

        with patch('app.get_simulation_metadata', return_value=jsonify({"success": True, "metadata": {"events": 1000}})):
            meta_res = dispatch_ai_tool(pm, "get_simulation_metadata", {
                "version_id": "v1",
                "job_id": "job-1"
            })

        with patch('app.get_simulation_analysis', return_value=jsonify({"success": True, "analysis": {"total_hits": 5}})):
            analysis_res = dispatch_ai_tool(pm, "get_simulation_analysis", {
                "version_id": "v1",
                "job_id": "job-1",
                "energy_bins": 64,
                "spatial_bins": 32
            })

    assert meta_res['success'], meta_res
    assert meta_res['metadata']['events'] == 1000
    assert analysis_res['success'], analysis_res
    assert analysis_res['analysis']['total_hits'] == 5


def test_ai_tool_batch_geometry_update_accepts_type_alias(pm):
    res = dispatch_ai_tool(pm, "batch_geometry_update", {
        "operations": [
            {
                "type": "create_primitive_solid",
                "args": {
                    "name": "BatchAliasBox",
                    "solid_type": "box",
                    "params": {"x": "5", "y": "5", "z": "5"}
                }
            }
        ]
    })

    assert res['success'], res
    assert res['batch_results'][0]['success'], res['batch_results']
    assert "BatchAliasBox" in pm.current_geometry_state.solids


def test_ai_tool_create_boolean_accepts_action_and_solid_aliases(pm):
    pm.add_solid("BaseSolid", "box", {"x": "20", "y": "20", "z": "20"})
    pm.add_solid("HoleSolid", "tube", {"rmin": "0", "rmax": "2", "z": "25", "startphi": "0", "deltaphi": "360"})

    res = dispatch_ai_tool(pm, "create_boolean_solid", {
        "name": "BoolAlias",
        "recipe": [
            {"action": "base", "solid": "BaseSolid"},
            {
                "action": "subtract",
                "solid": "HoleSolid",
                "transform": {"pos": {"x": "0", "y": "0", "z": "0"}}
            }
        ]
    })

    assert res['success'], res
    assert "BoolAlias" in pm.current_geometry_state.solids


def test_ai_tool_create_boolean_invalid_recipe_returns_repair_hint(pm):
    pm.add_solid("BaseSolid2", "box", {"x": "20", "y": "20", "z": "20"})

    res = dispatch_ai_tool(pm, "create_boolean_solid", {
        "name": "BadBool",
        "recipe": [{"op": "difference", "solid_ref": "BaseSolid2"}]
    })

    assert not res['success']
    assert "expected recipe format" in res['error'].lower() or "must start" in res['error'].lower()


@pytest.mark.parametrize(
    "arg_name,arg_value",
    [
        ("since", -1),
        ("tail_lines", 2.5),
        ("max_lines", True),
    ],
)
def test_ai_tool_get_simulation_status_rejects_invalid_nonnegative_integer_args(pm, arg_name, arg_value):
    from app import SIMULATION_STATUS, SIMULATION_LOCK

    job_id = "sim-invalid-args"
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": "Running",
            "progress": 5,
            "total_events": 10,
            "stdout": ["line-0"],
            "stderr": [],
        }

    try:
        res = dispatch_ai_tool(pm, "get_simulation_status", {
            "job_id": job_id,
            arg_name: arg_value,
        })

        assert not res["success"]
        assert arg_name in res["error"]
        assert "integer >= 0" in res["error"]
    finally:
        with SIMULATION_LOCK:
            SIMULATION_STATUS.pop(job_id, None)
