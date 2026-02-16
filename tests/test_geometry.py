import pytest
import numpy as np
import math
from src.geometry_types import PhysicalVolumePlacement

def test_pv_transformation_matrix():
    # Test a simple translation
    pv = PhysicalVolumePlacement("test_pv", "vol_ref")
    pv._evaluated_position = {'x': 10.0, 'y': -5.0, 'z': 0.0}
    pv._evaluated_rotation = {'x': 0, 'y': 0, 'z': 0}
    pv._evaluated_scale = {'x': 1, 'y': 1, 'z': 1}
    
    matrix = pv.get_transform_matrix()
    expected = np.eye(4)
    expected[0, 3] = 10.0
    expected[1, 3] = -5.0
    
    assert np.allclose(matrix, expected)

def test_decompose_matrix():
    # Test rotation decomposition
    angle = math.pi / 4  # 45 degrees
    
    # Create a rotation matrix around Z
    c, s = math.cos(angle), math.sin(angle)
    # ZYX composition for Rz(angle)
    # Rz = [[c, -s, 0], [s, c, 0], [0, 0, 1]]
    
    matrix = np.eye(4)
    matrix[0, 0] = c
    matrix[0, 1] = -s
    matrix[1, 0] = s
    matrix[1, 1] = c
    matrix[0, 3] = 100.0 # translation
    
    pos, rot, scale = PhysicalVolumePlacement.decompose_matrix(matrix)
    
    assert pos['x'] == 100.0
    assert np.allclose(rot['z'], angle)
    assert np.allclose(rot['x'], 0)
    assert np.allclose(rot['y'], 0)
    assert scale['x'] == 1.0

def test_round_trip_transformation():
    pv = PhysicalVolumePlacement("test", "ref")
    pv._evaluated_position = {'x': 10, 'y': 20, 'z': 30}
    pv._evaluated_rotation = {'x': 0.1, 'y': 0.2, 'z': 0.3}
    pv._evaluated_scale = {'x': 1, 'y': 1, 'z': 1}
    
    matrix = pv.get_transform_matrix()
    pos, rot, scale = PhysicalVolumePlacement.decompose_matrix(matrix)
    
    assert np.allclose(pos['x'], 10)
    assert np.allclose(pos['y'], 20)
    assert np.allclose(pos['z'], 30)
    # There might be slight differences in Euler angles due to decomposition paths
    # but the matrix should be identical
    
    pv2 = PhysicalVolumePlacement("test2", "ref")
    pv2._evaluated_position = pos
    pv2._evaluated_rotation = rot
    pv2._evaluated_scale = scale
    matrix2 = pv2.get_transform_matrix()
    
    assert np.allclose(matrix, matrix2)
