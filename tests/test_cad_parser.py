import pytest
from unittest.mock import MagicMock, patch
from src.step_parser import process_solid, process_label, _trsf_to_dict
from src.geometry_types import GeometryState
import math

# Use a mock for TopLoc_Location and gp_Trsf
class MockLocation:
    def __init__(self, val=1):
        self.val = val
    def Multiplied(self, other):
        return MockLocation(self.val * other.val)
    def Transformation(self):
        return MockTrsf(self.val)

class MockTrsf:
    def __init__(self, val):
        self.val = val
    def GetRotation(self):
        m = MagicMock()
        m.GetEulerAngles.return_value = (self.val * 0.1, self.val * 0.2, self.val * 0.3)
        return m
    def TranslationPart(self):
        m = MagicMock()
        m.X.return_value = self.val * 10.0
        m.Y.return_value = self.val * 20.0
        m.Z.return_value = self.val * 30.0
        return m

def test_assembly_hierarchy_traversal():
    state = GeometryState()
    shape_tool = MagicMock()
    
    root_label = MagicMock(name="root")
    sub_asm_label = MagicMock(name="sub_asm")
    solid1_label = MagicMock(name="solid1")
    solid2_label = MagicMock(name="solid2")
    
    # Initialize identity to None for comparison
    for l in [root_label, sub_asm_label, solid1_label, solid2_label]:
        l.identity = None

    comp_root_sub = MagicMock(name="comp_root_sub")
    comp_root_s2 = MagicMock(name="comp_root_s2")
    comp_sub_s1 = MagicMock(name="comp_sub_s1")
    
    def get_real_label(l):
        if hasattr(l, 'identity') and l.identity is not None:
            return l.identity
        return l

    def is_assembly(l):
        real_l = get_real_label(l)
        res = real_l in [root_label, sub_asm_label]
        # print(f"DEBUG MOCK: is_assembly({real_l}) -> {res}")
        return res
    shape_tool.IsAssembly.side_effect = is_assembly
    
    def is_simple(l):
        real_l = get_real_label(l)
        res = real_l in [solid1_label, solid2_label]
        # print(f"DEBUG MOCK: is_simple({real_l}) -> {res}")
        return res
    shape_tool.IsSimpleShape.side_effect = is_simple

    def get_new_label():
        m = MagicMock(name="label_instance")
        m.identity = None
        return m

    def get_new_seq():
        m = MagicMock(name="seq_instance")
        m.Length.return_value = 0
        return m

    with patch('src.step_parser.TDF_Label', side_effect=get_new_label), \
         patch('src.step_parser.TDF_LabelSequence', side_effect=get_new_seq), \
         patch('src.step_parser.process_solid') as MockProcessSolid, \
         patch('src.step_parser.TopLoc_Location', side_effect=lambda: MockLocation(1)), \
         patch('src.step_parser.TopAbs_SOLID', 0):
        
        def side_effect_components(l, seq):
            real_l = get_real_label(l)
            if real_l == root_label:
                seq.Length.return_value = 2
                seq.Value.side_effect = [comp_root_sub, comp_root_s2]
            elif real_l == sub_asm_label:
                seq.Length.return_value = 1
                seq.Value.side_effect = [comp_sub_s1]
            return None
        shape_tool.GetComponents.side_effect = side_effect_components
        
        def side_effect_referred(comp, label):
            if comp == comp_root_sub:
                label.identity = sub_asm_label
            elif comp == comp_root_s2:
                label.identity = solid2_label
            elif comp == comp_sub_s1:
                label.identity = solid1_label
            return True
        shape_tool.GetReferredShape.side_effect = side_effect_referred
        
        shape_tool.GetLocation.side_effect = lambda l: MockLocation(2 if get_real_label(l) == sub_asm_label else 1)
        
        def side_effect_shape(l):
            s = MagicMock()
            s.ShapeType.return_value = 0 # TopAbs_SOLID
            return s
        shape_tool.GetShape.side_effect = side_effect_shape
        
        # VERY IMPORTANT: process_solid must return something TRUTHY
        MockProcessSolid.return_value = MagicMock(name="mock_lv")
        
        results = process_label(root_label, shape_tool, state, MockLocation(1), "test")
        
        assert len(results) == 2
        loc_vals = [r[1]['position']['x'] / 10.0 for r in results]
        assert 1.0 in loc_vals 
        assert 2.0 in loc_vals

def test_degenerate_triangle_filtering():
    state = GeometryState()
    grouping_name = "test_group"
    mock_solid = MagicMock()
    mock_solid.ShapeType.return_value = None 
    
    with patch('src.step_parser.TopExp_Explorer') as MockExplorer, \
         patch('src.step_parser.BRep_Tool.Triangulation') as MockTriangulation, \
         patch('src.step_parser.BRepMesh_IncrementalMesh') as MockMesh:
        
        mock_mesh_instance = MockMesh.return_value
        mock_mesh_instance.IsDone.return_value = True
        
        explorer_instance = MockExplorer.return_value
        explorer_instance.More.side_effect = [True, False] 
        mock_face = MagicMock()
        explorer_instance.Current.return_value = mock_face
        mock_face.Orientation.return_value = 0 # TopAbs_FORWARD
        
        mock_poly = MagicMock()
        MockTriangulation.return_value = mock_poly
        
        class MockNode:
            def __init__(self, x, y, z): self._x, self._y, self._z = x, y, z
            def X(self): return self._x
            def Y(self): return self._y
            def Z(self): return self._z
            
        nodes = [
            MockNode(0, 0, 0),       # V0
            MockNode(1, 0, 0),       # V1
            MockNode(0, 1, 0),       # V2
            MockNode(1e-15, 0, 0)    # V3
        ]
        
        mock_poly.NbNodes.return_value = 4
        mock_node_array = MagicMock()
        mock_node_array.Value.side_effect = lambda i: nodes[i-1]
        mock_poly.MapNodeArray.return_value = mock_node_array
        
        class MockTriangle:
            def __init__(self, n1, n2, n3): self.nodes = (n1, n2, n3)
            def Get(self): return self.nodes
            
        triangles = [
            MockTriangle(1, 2, 3), # Valid
            MockTriangle(1, 2, 4), # Degenerate
            MockTriangle(1, 2, 2)  # Degenerate
        ]
        
        mock_poly.NbTriangles.return_value = 3
        mock_tri_array = MagicMock()
        mock_tri_array.Value.side_effect = lambda i: triangles[i-1]
        mock_poly.MapTriangleArray.return_value = mock_tri_array
        
        lv = process_solid(mock_solid, state, grouping_name)
        assert lv is not None
        assert len(state.solids) == 1
        solid = list(state.solids.values())[0]
        facets = solid.raw_parameters['facets']
        assert len(facets) == 1
