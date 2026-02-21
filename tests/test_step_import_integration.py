import io
import json
from unittest.mock import patch

from app import app
from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


def _make_pm():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    return pm


def test_import_step_route_returns_smart_import_report_payload():
    app.config['TESTING'] = True
    with app.test_client() as client:
        pm = _make_pm()

        fake_report = {
            'enabled': True,
            'candidates': [
                {
                    'source_id': 'fixture_1',
                    'classification': 'box',
                    'confidence': 0.95,
                    'params': {'x': 1, 'y': 2, 'z': 3},
                    'fallback_reason': None,
                    'selected_mode': 'primitive',
                },
                {
                    'source_id': 'fixture_2',
                    'classification': 'tessellated',
                    'confidence': 0.0,
                    'params': {},
                    'fallback_reason': 'no_primitive_match_v1',
                    'selected_mode': 'tessellated',
                },
            ],
            'summary': {
                'total': 2,
                'primitive_count': 1,
                'tessellated_count': 1,
                'primitive_ratio': 0.5,
                'selected_mode_counts': {'primitive': 1, 'tessellated': 1},
                'selected_primitive_ratio': 0.5,
                'counts_by_classification': {
                    'box': 1,
                    'cylinder': 0,
                    'sphere': 0,
                    'cone': 0,
                    'torus': 0,
                    'tessellated': 1,
                },
            },
        }

        with patch('app.get_project_manager_for_session', return_value=pm), \
             patch.object(pm, 'import_step_with_options', return_value=(True, None, fake_report)):
            data = {
                'stepFile': (io.BytesIO(b'STEP-DATA'), 'fixture.step'),
                'options': json.dumps({
                    'groupingName': 'fixture_import',
                    'placementMode': 'assembly',
                    'parentLVName': 'World',
                    'offset': {'x': '0', 'y': '0', 'z': '0'},
                    'smartImport': True,
                }),
            }
            resp = client.post('/import_step_with_options', data=data, content_type='multipart/form-data')

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload['success'] is True
        assert 'step_import_report' in payload
        assert payload['step_import_report']['summary']['selected_mode_counts']['primitive'] == 1
        assert payload['step_import_report']['candidates'][1]['fallback_reason'] == 'no_primitive_match_v1'
