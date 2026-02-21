import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.geometry_types import GeometryState
from src.smart_cad_classifier import (
    ALLOWED_FALLBACK_REASONS,
    get_smart_import_policy,
    resolve_candidate_selection,
)
from src.step_parser import process_solid


FIXTURE_PATH = Path(__file__).parent / 'fixtures' / 'm1' / 'smart_import_report_fixture.json'
SELECTION_FIXTURE_PATH = Path(__file__).parent / 'fixtures' / 'm2' / 'reliability_selection_cases.json'


def _mock_minimal_tessellation_stack(MockExplorer, MockTriangulation, MockMesh):
    mock_mesh_instance = MockMesh.return_value
    mock_mesh_instance.IsDone.return_value = True

    explorer_instance = MockExplorer.return_value
    explorer_instance.More.side_effect = [True, False]
    mock_face = MagicMock()
    explorer_instance.Current.return_value = mock_face
    mock_face.Orientation.return_value = 0

    mock_poly = MagicMock()
    MockTriangulation.return_value = mock_poly

    class MockNode:
        def __init__(self, x, y, z):
            self._x, self._y, self._z = x, y, z

        def X(self): return self._x
        def Y(self): return self._y
        def Z(self): return self._z

    nodes = [MockNode(0, 0, 0), MockNode(1, 0, 0), MockNode(0, 1, 0)]
    mock_poly.NbNodes.return_value = 3
    mock_node_array = MagicMock()
    mock_node_array.Value.side_effect = lambda i: nodes[i-1]
    mock_poly.MapNodeArray.return_value = mock_node_array

    class MockTriangle:
        def __init__(self, n1, n2, n3):
            self.nodes = (n1, n2, n3)

        def Get(self):
            return self.nodes

    mock_poly.NbTriangles.return_value = 1
    mock_tri_array = MagicMock()
    mock_tri_array.Value.side_effect = lambda i: MockTriangle(1, 2, 3)
    mock_poly.MapTriangleArray.return_value = mock_tri_array


def test_fixture_tessellated_candidates_use_allowed_fallback_codes():
    fixture = json.loads(FIXTURE_PATH.read_text())
    for candidate in fixture['candidates']:
        if candidate.get('selected_mode') == 'tessellated':
            assert candidate.get('fallback_reason') in ALLOWED_FALLBACK_REASONS


def test_step_parser_normalizes_invalid_tessellated_fallback_reason():
    state = GeometryState()
    state.smart_import_report = {'enabled': True, 'candidates': [], 'summary': {}}

    with patch('src.step_parser.classify_shape') as MockClassify, \
         patch('src.step_parser.TopExp_Explorer') as MockExplorer, \
         patch('src.step_parser.BRep_Tool.Triangulation') as MockTriangulation, \
         patch('src.step_parser.BRepMesh_IncrementalMesh') as MockMesh:

        MockClassify.return_value = {
            'source_id': 'smart_group_solid_0',
            'classification': 'tessellated',
            'confidence': 0.0,
            'params': {},
            'fallback_reason': 'INVALID_REASON_FROM_CLASSIFIER',
        }

        _mock_minimal_tessellation_stack(MockExplorer, MockTriangulation, MockMesh)
        lv = process_solid(MagicMock(), state, 'smart_group', smart_import=True)

        assert lv is not None
        candidate = state.smart_import_report['candidates'][0]
        assert candidate['selected_mode'] == 'tessellated'
        assert candidate['fallback_reason'] == 'no_primitive_match_v1'
        assert candidate['fallback_reason'] in ALLOWED_FALLBACK_REASONS


def test_selection_policy_regression_fixture_cases():
    cases = json.loads(SELECTION_FIXTURE_PATH.read_text())

    for case in cases:
        policy = get_smart_import_policy(case.get('policy', {}))
        selected = resolve_candidate_selection(
            candidate=case['candidate'],
            primitive_mappable=case['primitive_mappable'],
            policy=policy,
        )

        expected = case['expected']
        assert selected['selected_mode'] == expected['selected_mode'], case['name']
        assert selected.get('fallback_reason') == expected['fallback_reason'], case['name']


def test_policy_option_parsing_and_clamping():
    p1 = get_smart_import_policy({'smartImportConfidenceThreshold': 0.65})
    p2 = get_smart_import_policy({'smart_import_confidence_threshold': 5.0})

    assert p1['primitive_confidence_threshold'] == 0.65
    assert p2['primitive_confidence_threshold'] == 1.0
