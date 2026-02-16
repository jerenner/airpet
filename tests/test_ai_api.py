import pytest
from unittest.mock import MagicMock, patch
from src.project_manager import ProjectManager
from src.expression_evaluator import ExpressionEvaluator
from app import dispatch_ai_tool

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

def test_ai_tool_get_summary(pm):
    res = dispatch_ai_tool(pm, "get_project_summary", {})
    assert res['success']
    assert "counts" in res['result']
    assert res['result']['world_volume'] == "World"

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
