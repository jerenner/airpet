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
