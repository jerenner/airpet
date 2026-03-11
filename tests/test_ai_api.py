import os
import pytest
from unittest.mock import MagicMock, patch
from flask import jsonify, session
from src.project_manager import ProjectManager
from src.expression_evaluator import ExpressionEvaluator
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

    assert res["success"] is False
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

    assert res["success"] is False
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

    assert res["success"] is False
    assert "out of range" in res["error"]
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

    assert res["success"] is False
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

    assert res["success"] is False
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

    assert res["success"] is False
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

    assert res["success"] is False
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


def test_ai_tool_compare_latest_autosave_snapshot_preflight_versions(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_latest_snapshot_versions_project"

    pm.save_project_version('autosave_snapshot_old_ai')

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


def test_ai_tool_compare_latest_autosave_snapshot_preflight_versions_requires_two_snapshots(pm, tmp_path):
    pm.projects_dir = str(tmp_path)
    pm.project_name = "ai_compare_latest_snapshot_versions_missing"

    pm.save_project_version('autosave_snapshot_only_ai')

    res = dispatch_ai_tool(pm, "compare_latest_autosave_snapshot_preflight_versions", {})

    assert res["success"] is False
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

    assert res["success"] is False
    assert "limit" in res["error"]


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

    assert res["success"] is False
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
