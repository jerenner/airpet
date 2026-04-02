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

BASE_URL = "http://127.0.0.1:5003"

def create_project():
    """Create a new project."""
    print("Creating new project...")
    response = requests.post(f"{BASE_URL}/new_project", json={})
    if response.status_code != 200:
        raise Exception(f"Failed to create project: {response.text}")
    return response.json()

def test_boolean_union_direct():
    """Test 50: Union of two boxes via direct API."""
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
    
    if union.get("success"):
        print("✅ Boolean solid 'union_ab' created successfully")
        print(f"   Recipe: {union.get('solid', {}).get('raw_parameters', {}).get('recipe')}")
        return True
    else:
        print(f"❌ Failed: {union.get('error')}")
        return False

def test_boolean_union_ai():
    """Test 50: Union of two boxes via AI chat."""
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
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nAI Response: {data.get('text', 'N/A')[:200]}")
        
        # Check if solids were created
        state = requests.get(f"{BASE_URL}/get_project_state").json()
        solids = state.get('project_state', {}).get('solids', {})
        
        if 'union_ab' in solids or any('union' in s.lower() for s in solids.keys()):
            print("✅ Boolean union solid created successfully")
            for name, solid in solids.items():
                if solid.get('type') == 'boolean':
                    print(f"   Solid: {name}, Type: {solid.get('type')}")
                    print(f"   Recipe: {solid.get('raw_parameters', {}).get('recipe')}")
            return True
        else:
            print("❌ Boolean solid not found in project state")
            print(f"Available solids: {list(solids.keys())}")
            return False
    else:
        print(f"❌ HTTP Error {response.status_code}: {response.text[:200]}")
        return False

def test_boolean_subtraction_direct():
    """Test 51: Subtraction (box with cylindrical hole) via direct API."""
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
    
    if subtraction.get("success"):
        print("✅ Boolean solid 'box_with_hole' created successfully")
        print(f"   Recipe: {subtraction.get('solid', {}).get('raw_parameters', {}).get('recipe')}")
        return True
    else:
        print(f"❌ Failed: {subtraction.get('error')}")
        return False

def test_boolean_subtraction_ai():
    """Test 51: Subtraction via AI chat."""
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
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nAI Response: {data.get('text', 'N/A')[:200]}")
        
        # Check if solids were created
        state = requests.get(f"{BASE_URL}/get_project_state").json()
        solids = state.get('project_state', {}).get('solids', {})
        
        if any('hole' in s.lower() or 'subtraction' in s.lower() for s in solids.keys()):
            print("✅ Boolean subtraction solid created successfully")
            for name, solid in solids.items():
                if solid.get('type') == 'boolean':
                    print(f"   Solid: {name}, Type: {solid.get('type')}")
                    print(f"   Recipe: {solid.get('raw_parameters', {}).get('recipe')}")
            return True
        else:
            print("❌ Boolean solid not found in project state")
            print(f"Available solids: {list(solids.keys())}")
            return False
    else:
        print(f"❌ HTTP Error {response.status_code}: {response.text[:200]}")
        return False

def test_boolean_intersection_direct():
    """Test 52: Intersection of two solids via direct API."""
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
    
    if intersection.get("success"):
        print("✅ Boolean solid 'box_tube_intersection' created successfully")
        print(f"   Recipe: {intersection.get('solid', {}).get('raw_parameters', {}).get('recipe')}")
        return True
    else:
        print(f"❌ Failed: {intersection.get('error')}")
        return False

def test_boolean_intersection_ai():
    """Test 52: Intersection via AI chat."""
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
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nAI Response: {data.get('text', 'N/A')[:200]}")
        
        # Check if solids were created
        state = requests.get(f"{BASE_URL}/get_project_state").json()
        solids = state.get('project_state', {}).get('solids', {})
        
        boolean_solids = {k: v for k, v in solids.items() if v.get('type') == 'boolean'}
        if boolean_solids:
            print("✅ Boolean intersection solid created successfully")
            for name, solid in boolean_solids.items():
                print(f"   Solid: {name}, Type: {solid.get('type')}")
                print(f"   Recipe: {solid.get('raw_parameters', {}).get('recipe')}")
            return True
        else:
            print("❌ Boolean solid not found in project state")
            print(f"Available solids: {list(solids.keys())}")
            return False
    else:
        print(f"❌ HTTP Error {response.status_code}: {response.text[:200]}")
        return False

def main():
    """Run all tests."""
    results = {}
    
    # Test 50: Union
    create_project()
    results['50_direct'] = test_boolean_union_direct()
    create_project()
    results['50_ai'] = test_boolean_union_ai()
    
    # Test 51: Subtraction
    create_project()
    results['51_direct'] = test_boolean_subtraction_direct()
    create_project()
    results['51_ai'] = test_boolean_subtraction_ai()
    
    # Test 52: Intersection
    create_project()
    results['52_direct'] = test_boolean_intersection_direct()
    create_project()
    results['52_ai'] = test_boolean_intersection_ai()
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test}: {status}")
    
    all_passed = all(results.values())
    print(f"\nOverall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
