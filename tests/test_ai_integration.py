import pytest
import requests
import json
import time
import subprocess
import os
from unittest.mock import MagicMock, patch

BASE_URL = "http://127.0.0.1:5003"

@pytest.fixture(scope="module")
def flask_server():
    # Start the flask server in a subprocess
    # We pass a dummy API key so the client initializes
    process = subprocess.Popen(
        ["/Users/marth/miniconda/envs/airpet/bin/python", "app.py"],
        cwd="/Users/marth/projects/airpet",
        env={**os.environ, "FLASK_RUN_PORT": "5003", "APP_MODE": "local", "GEMINI_API_KEY": "dummy_key"}
    )
    time.sleep(3) # Wait for startup
    yield
    process.terminate()

def test_ai_chat_flow_mocked(flask_server):
    """
    Since we don't want to make real API calls during automated tests 
    (to avoid cost and dependency on keys), we would normally mock the 
    genai client inside the flask app. 
    
    However, since it's a separate process, we'll test the tool dispatch 
    logic directly using the dispatch_ai_tool helper which we already tested in test_ai_api.py.
    
    For THIS integration test, we'll verify the endpoints exist and handle history.
    """
    
    # 1. Clear history
    res = requests.post(f"{BASE_URL}/api/ai/clear")
    assert res.status_code == 200

    # 2. Check initial history
    hist_res = requests.get(f"{BASE_URL}/api/ai/history")
    assert hist_res.status_code == 200
    assert len(hist_res.json()['history']) == 0

    # 3. Verify health check
    health_res = requests.get(f"{BASE_URL}/ai_health_check")
    assert health_res.status_code == 200
    data = health_res.json()
    assert data['success']
    # Gemini should be listed (even if it fails to list models due to dummy key)
    assert 'models' in data

def test_ai_tool_dispatch_integration():
    """Verify that the tool dispatcher is correctly integrated in the app."""
    from src.project_manager import ProjectManager
    from src.expression_evaluator import ExpressionEvaluator
    from app import dispatch_ai_tool
    
    evaluator = ExpressionEvaluator()
    pm = ProjectManager(evaluator)
    pm.create_empty_project()
    
    # Test a complex tool: create_detector_ring
    args = {
        "parent_lv_name": "World",
        "lv_to_place_ref": "box_LV",
        "ring_name": "TestRing",
        "num_detectors": "8",
        "radius": "200",
        "center": {"x": "0", "y": "0", "z": "0"},
        "orientation": {"x": "0", "y": "0", "z": "0"},
        "point_to_center": True,
        "inward_axis": "-z",
        "num_rings": "1",
        "ring_spacing": "0"
    }
    
    result = dispatch_ai_tool(pm, "create_detector_ring", args)
    assert result['success']
    
    # Verify the placements were created in the state
    world_lv = pm.current_geometry_state.logical_volumes["World"]
    placements = [pv for pv in world_lv.content if "TestRing" in pv.name]
    assert len(placements) == 8
