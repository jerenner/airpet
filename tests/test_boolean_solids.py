#!/usr/bin/env python3
"""
Test suite for boolean solids via AI chat and direct API.

Tests:
- Union of two boxes
- Subtraction (box with cylindrical hole)
- Intersection of two solids
- Multi-step recipe ((A ∪ B) - C)
"""

import requests
import json
import time
import socket

import pytest

BASE_URL = "http://127.0.0.1:5003"


def _server_available(host="127.0.0.1", port=5003, timeout=0.2):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


pytestmark = pytest.mark.skipif(
    not _server_available(),
    reason="requires a running AIRPET server on 127.0.0.1:5003",
)

def create_project():
    """Create a new project."""
    print("Creating new project...")
    response = requests.post(f"{BASE_URL}/new_project", json={})
    assert response.status_code == 200, f"Failed to create project: {response.text}"
    return response.json()

def test_boolean_union_direct():
    """Test 50: Union of two boxes via direct API."""
    create_project()
    print("\n" + "="*70)
    print("Test 50 Direct API: Union of two boxes")
    print("="*70)
    
    # Create two boxes first
    box1 = requests.post(f"{BASE_URL}/add_primitive_solid", json={
        "name": "box_a",
        "type": "box",
        "params": {"x": "50", "y": "50", "z": "50"}
    }).json()
    
    box2 = requests.post(f"{BASE_URL}/add_primitive_solid", json={
        "name": "box_b",
        "type": "box",
        "params": {"x": "50", "y": "50", "z": "50"}
    }).json()
    
    # Create union
    union = requests.post(f"{BASE_URL}/add_boolean_solid", json={
        "name": "union_ab",
        "recipe": [
            {"op": "base", "solid_ref": "box_a"},
            {"op": "union", "solid_ref": "box_b", "transform": {"position": {"x": "50", "y": "0", "z": "0"}}}
        ]
    }).json()
    
    assert union.get("success"), f"Failed to create union_ab: {union.get('error')}"
    print("✅ Boolean solid 'union_ab' created successfully")
    print(f"   Recipe: {union.get('solid', {}).get('raw_parameters', {}).get('recipe')}")

def test_boolean_union_ai():
    """Test 50: Union of two boxes via AI chat."""
    create_project()
    print("\n" + "="*70)
    print("Test 50 AI Chat: Union of two boxes")
    print("="*70)
    
    message = """Create two box solids named box_a and box_b, each with dimensions 50x50x50 mm.
Then create a boolean union solid named union_ab that combines box_a with box_b, 
where box_b is positioned at x=50mm relative to box_a."""
    
    print(f"Message: {message}\n")
    
    start = time.time()
    response = requests.post(f"{BASE_URL}/api/ai/chat", json={
        "message": message,
        "model": "llama_cpp::Qwen3.5-27B-Q6_K",
        "turn_limit": 30
    })
    elapsed = time.time() - start
    
    print(f"Response time: {elapsed:.1f}s")
    print(f"Status: {response.status_code}")
    assert response.status_code == 200, f"HTTP Error {response.status_code}: {response.text[:200]}"
    
    data = response.json()
    print(f"\nAI Response: {data.get('text', 'N/A')[:200]}")
    
    # Check if solids were created
    state = requests.get(f"{BASE_URL}/get_project_state").json()
    solids = state.get('project_state', {}).get('solids', {})
    
    assert 'union_ab' in solids or any('union' in s.lower() for s in solids.keys()), (
        f"Boolean solid not found in project state. Available solids: {list(solids.keys())}"
    )
    print("✅ Boolean union solid created successfully")
    for name, solid in solids.items():
        if solid.get('type') == 'boolean':
            print(f"   Solid: {name}, Type: {solid.get('type')}")
            print(f"   Recipe: {solid.get('raw_parameters', {}).get('recipe')}")

def test_boolean_subtraction_direct():
    """Test 51: Subtraction (box with cylindrical hole) via direct API."""
    create_project()
    print("\n" + "="*70)
    print("Test 51 Direct API: Box with cylindrical hole")
    print("="*70)
    
    # Create box
    box = requests.post(f"{BASE_URL}/add_primitive_solid", json={
        "name": "outer_box",
        "type": "box",
        "params": {"x": "100", "y": "100", "z": "100"}
    }).json()
    
    # Create tube for hole
    tube = requests.post(f"{BASE_URL}/add_primitive_solid", json={
        "name": "hole_tube",
        "type": "tube",
        "params": {"rmin": "0", "rmax": "20", "dz": "100", "sphi": "0", "dphi": "360*deg"}
    }).json()
    
    # Create subtraction
    subtraction = requests.post(f"{BASE_URL}/add_boolean_solid", json={
        "name": "box_with_hole",
        "recipe": [
            {"op": "base", "solid_ref": "outer_box"},
            {"op": "subtraction", "solid_ref": "hole_tube"}
        ]
    }).json()
    
    assert subtraction.get("success"), f"Failed to create box_with_hole: {subtraction.get('error')}"
    print("✅ Boolean solid 'box_with_hole' created successfully")
    print(f"   Recipe: {subtraction.get('solid', {}).get('raw_parameters', {}).get('recipe')}")

def test_boolean_subtraction_ai():
    """Test 51: Subtraction via AI chat."""
    create_project()
    print("\n" + "="*70)
    print("Test 51 AI Chat: Box with cylindrical hole")
    print("="*70)
    
    message = """Create a box solid 100x100x100 mm named outer_box.
Create a tube solid with inner radius 0, outer radius 20mm, and half-length 100mm named hole_tube.
Create a boolean subtraction solid named box_with_hole that subtracts hole_tube from outer_box."""
    
    print(f"Message: {message}\n")
    
    start = time.time()
    response = requests.post(f"{BASE_URL}/api/ai/chat", json={
        "message": message,
        "model": "llama_cpp::Qwen3.5-27B-Q6_K",
        "turn_limit": 30
    })
    elapsed = time.time() - start
    
    print(f"Response time: {elapsed:.1f}s")
    print(f"Status: {response.status_code}")
    assert response.status_code == 200, f"HTTP Error {response.status_code}: {response.text[:200]}"
    
    data = response.json()
    print(f"\nAI Response: {data.get('text', 'N/A')[:200]}")
    
    # Check if solids were created
    state = requests.get(f"{BASE_URL}/get_project_state").json()
    solids = state.get('project_state', {}).get('solids', {})
    
    assert any('hole' in s.lower() or 'subtraction' in s.lower() for s in solids.keys()), (
        f"Boolean solid not found in project state. Available solids: {list(solids.keys())}"
    )
    print("✅ Boolean subtraction solid created successfully")
    for name, solid in solids.items():
        if solid.get('type') == 'boolean':
            print(f"   Solid: {name}, Type: {solid.get('type')}")
            print(f"   Recipe: {solid.get('raw_parameters', {}).get('recipe')}")

def test_boolean_intersection_direct():
    """Test 52: Intersection of two solids via direct API."""
    create_project()
    print("\n" + "="*70)
    print("Test 52 Direct API: Intersection of box and tube")
    print("="*70)
    
    # Create box
    box = requests.post(f"{BASE_URL}/add_primitive_solid", json={
        "name": "intersect_box",
        "type": "box",
        "params": {"x": "100", "y": "100", "z": "100"}
    }).json()
    
    # Create tube
    tube = requests.post(f"{BASE_URL}/add_primitive_solid", json={
        "name": "intersect_tube",
        "type": "tube",
        "params": {"rmin": "0", "rmax": "80", "dz": "100", "sphi": "0", "dphi": "360*deg"}
    }).json()
    
    # Create intersection
    intersection = requests.post(f"{BASE_URL}/add_boolean_solid", json={
        "name": "box_tube_intersection",
        "recipe": [
            {"op": "base", "solid_ref": "intersect_box"},
            {"op": "intersection", "solid_ref": "intersect_tube"}
        ]
    }).json()
    
    assert intersection.get("success"), (
        f"Failed to create box_tube_intersection: {intersection.get('error')}"
    )
    print("✅ Boolean solid 'box_tube_intersection' created successfully")
    print(f"   Recipe: {intersection.get('solid', {}).get('raw_parameters', {}).get('recipe')}")

def test_boolean_intersection_ai():
    """Test 52: Intersection via AI chat."""
    create_project()
    print("\n" + "="*70)
    print("Test 52 AI Chat: Intersection of box and tube")
    print("="*70)
    
    message = """Create a box solid 100x100x100 mm and a tube with radius 80mm and half-length 100mm.
Create a boolean intersection solid that shows only the overlapping region of these two solids."""
    
    print(f"Message: {message}\n")
    
    start = time.time()
    response = requests.post(f"{BASE_URL}/api/ai/chat", json={
        "message": message,
        "model": "llama_cpp::Qwen3.5-27B-Q6_K",
        "turn_limit": 30
    })
    elapsed = time.time() - start
    
    print(f"Response time: {elapsed:.1f}s")
    print(f"Status: {response.status_code}")
    assert response.status_code == 200, f"HTTP Error {response.status_code}: {response.text[:200]}"
    
    data = response.json()
    print(f"\nAI Response: {data.get('text', 'N/A')[:200]}")
    
    # Check if solids were created
    state = requests.get(f"{BASE_URL}/get_project_state").json()
    solids = state.get('project_state', {}).get('solids', {})
    
    boolean_solids = {k: v for k, v in solids.items() if v.get('type') == 'boolean'}
    assert boolean_solids, f"Boolean solid not found in project state. Available solids: {list(solids.keys())}"
    print("✅ Boolean intersection solid created successfully")
    for name, solid in boolean_solids.items():
        print(f"   Solid: {name}, Type: {solid.get('type')}")
        print(f"   Recipe: {solid.get('raw_parameters', {}).get('recipe')}")
