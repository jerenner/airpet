import io
from pathlib import Path
from unittest.mock import patch

import pytest

from app import app
from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def _build_project_manager(tmp_path: Path) -> ProjectManager:
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    pm.projects_dir = str(projects_dir)
    return pm


def _payload_for_artifact(artifact: dict) -> dict:
    return {
        "regions": [
            {
                "region_id": "region_b",
                "label": "inner detector",
                "page_index": 1,
                "bbox": {"x": 0.4, "y": 0.2, "width": 0.2, "height": 0.3},
                "confidence": 0.81,
                "provenance": {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_sha256": artifact["sha256"],
                    "page_index": 1,
                    "source": "ocr-region",
                },
            },
            {
                "region_id": "region_a",
                "label": "outer vessel",
                "page_index": 0,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.6, "height": 0.7},
                "confidence": 0.93,
                "provenance": {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_sha256": artifact["sha256"],
                    "page_index": 0,
                    "source": "manual-markup",
                },
            },
        ],
        "dimensions": [
            {
                "dimension_id": "dim_b",
                "region_id": "region_b",
                "value": 17.25,
                "unit": "mm",
                "raw_text": "17.25 mm",
                "confidence": 0.77,
                "provenance": {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_sha256": artifact["sha256"],
                    "page_index": 1,
                    "source": "ocr-text",
                },
            },
            {
                "dimension_id": "dim_a",
                "region_id": "region_a",
                "value": 120.0,
                "unit": "mm",
                "raw_text": "120 mm",
                "confidence": 0.9,
                "provenance": {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_sha256": artifact["sha256"],
                    "page_index": 0,
                    "source": "ocr-text",
                },
            },
        ],
        "symbols": [
            {
                "symbol_id": "sym_b",
                "region_id": "region_b",
                "symbol_type": "material",
                "text": "Si",
                "confidence": 0.86,
                "provenance": {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_sha256": artifact["sha256"],
                    "page_index": 1,
                    "source": "ocr-symbol",
                },
            },
            {
                "symbol_id": "sym_a",
                "region_id": "region_a",
                "symbol_type": "annotation",
                "text": "beam axis",
                "confidence": 0.74,
                "provenance": {
                    "artifact_id": artifact["artifact_id"],
                    "artifact_sha256": artifact["sha256"],
                    "page_index": 0,
                    "source": "manual-markup",
                },
            },
        ],
    }


def test_artifact_extraction_review_route_normalizes_and_builds_review_envelope(client, tmp_path):
    pm = _build_project_manager(tmp_path)

    with patch('app.get_project_manager_for_session', return_value=pm):
        upload_response = client.post(
            '/api/ai/artifacts/upload',
            data={
                'artifact': (io.BytesIO(b'\x89PNG\r\n\x1a\nimage'), 'detector.png'),
            },
            content_type='multipart/form-data',
        )
        assert upload_response.status_code == 200
        artifact = upload_response.get_json()['artifact']

        response = client.post(
            f"/api/ai/artifacts/{artifact['artifact_id']}/extraction/review",
            json={
                'review_status': 'needs_changes',
                'extraction': _payload_for_artifact(artifact),
            },
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['schema_version'].endswith('checkpoint3')
    assert payload['artifact']['artifact_id'] == artifact['artifact_id']

    extraction = payload['extraction']
    assert extraction['artifact_id'] == artifact['artifact_id']
    assert extraction['artifact_sha256'] == artifact['sha256']
    assert [item['region_id'] for item in extraction['regions']] == ['region_a', 'region_b']
    assert [item['dimension_id'] for item in extraction['dimensions']] == ['dim_a', 'dim_b']
    assert [item['symbol_id'] for item in extraction['symbols']] == ['sym_a', 'sym_b']
    assert extraction['stats'] == {
        'region_count': 2,
        'dimension_count': 2,
        'symbol_count': 2,
    }

    review = payload['review_envelope']
    assert review['status'] == 'needs_changes'
    assert review['summary']['total_items'] == 6
    assert [item['item_type'] for item in review['items']] == [
        'dimension',
        'dimension',
        'region',
        'region',
        'symbol',
        'symbol',
    ]


def test_artifact_extraction_review_route_rejects_missing_artifact(client, tmp_path):
    pm = _build_project_manager(tmp_path)

    with patch('app.get_project_manager_for_session', return_value=pm):
        response = client.post(
            '/api/ai/artifacts/artifact_missing/extraction/review',
            json={'extraction': {}},
        )

    assert response.status_code == 404
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['error_code'] == 'artifact_not_found'


def test_artifact_extraction_review_route_rejects_stale_missing_blob(client, tmp_path):
    pm = _build_project_manager(tmp_path)

    with patch('app.get_project_manager_for_session', return_value=pm):
        upload_response = client.post(
            '/api/ai/artifacts/upload',
            data={
                'artifact': (io.BytesIO(b'%PDF-1.7\n1 0 obj\n<<>>\nendobj\n'), 'detector.pdf'),
            },
            content_type='multipart/form-data',
        )
        assert upload_response.status_code == 200
        artifact = upload_response.get_json()['artifact']

        blob_path = Path(pm.projects_dir) / '.airpet_ai_artifacts' / 'blobs' / artifact['stored_filename']
        blob_path.unlink()

        response = client.post(
            f"/api/ai/artifacts/{artifact['artifact_id']}/extraction/review",
            json={'extraction': {}},
        )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['error_code'] == 'artifact_blob_missing'


def test_artifact_extraction_review_route_rejects_artifact_id_mismatch(client, tmp_path):
    pm = _build_project_manager(tmp_path)

    with patch('app.get_project_manager_for_session', return_value=pm):
        upload_response = client.post(
            '/api/ai/artifacts/upload',
            data={
                'artifact': (io.BytesIO(b'\x89PNG\r\n\x1a\nimage'), 'detector.png'),
            },
            content_type='multipart/form-data',
        )
        assert upload_response.status_code == 200
        artifact = upload_response.get_json()['artifact']

        response = client.post(
            f"/api/ai/artifacts/{artifact['artifact_id']}/extraction/review",
            json={
                'extraction': {
                    'artifact_id': 'artifact_wrong',
                    'artifact_sha256': artifact['sha256'],
                }
            },
        )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload['success'] is False
    assert payload['error_code'] == 'extraction_validation_error'
    assert 'artifact_id' in payload['error']


def test_artifact_planning_route_builds_deterministic_planning_envelope(client, tmp_path):
    pm = _build_project_manager(tmp_path)

    with patch('app.get_project_manager_for_session', return_value=pm):
        upload_response = client.post(
            '/api/ai/artifacts/upload',
            data={
                'artifact': (io.BytesIO(b'\x89PNG\r\n\x1a\nimage'), 'detector.png'),
            },
            content_type='multipart/form-data',
        )
        assert upload_response.status_code == 200
        artifact = upload_response.get_json()['artifact']

        extraction_response = client.post(
            f"/api/ai/artifacts/{artifact['artifact_id']}/extraction/review",
            json={
                'review_status': 'approved',
                'extraction': _payload_for_artifact(artifact),
            },
        )
        assert extraction_response.status_code == 200
        extraction_payload = extraction_response.get_json()

        planning_response = client.post(
            f"/api/ai/artifacts/{artifact['artifact_id']}/planning/envelope",
            json={
                'extraction': extraction_payload['extraction'],
                'review_envelope': extraction_payload['review_envelope'],
            },
        )

    assert planning_response.status_code == 200
    payload = planning_response.get_json()
    assert payload['success'] is True
    assert payload['schema_version'].endswith('checkpoint4')
    assert payload['planning_schema_version'].endswith('checkpoint4')

    planning = payload['planning_envelope']
    assert planning['schema_version'].endswith('checkpoint4')
    assert planning['status'] == 'ready'
    assert planning['summary']['error_count'] == 0
    assert planning['summary']['candidate_operation_count'] == 4
    assert [operation['operation_type'] for operation in planning['operations']] == [
        'apply_region_dimension_hint',
        'apply_region_dimension_hint',
        'apply_region_material_hint',
        'capture_region_annotation',
    ]


def test_artifact_planning_route_emits_diagnostics_for_unsupported_and_ambiguous_reviewed_items(client, tmp_path):
    pm = _build_project_manager(tmp_path)

    with patch('app.get_project_manager_for_session', return_value=pm):
        upload_response = client.post(
            '/api/ai/artifacts/upload',
            data={
                'artifact': (io.BytesIO(b'\x89PNG\r\n\x1a\nimage'), 'detector.png'),
            },
            content_type='multipart/form-data',
        )
        assert upload_response.status_code == 200
        artifact = upload_response.get_json()['artifact']

        extraction_payload = _payload_for_artifact(artifact)
        extraction_payload['dimensions'].append(
            {
                'dimension_id': 'dim_c',
                'region_id': 'region_a',
                'value': 7.5,
                'unit': 'inch',
                'raw_text': '7.5 in',
                'confidence': 0.88,
                'provenance': {
                    'artifact_id': artifact['artifact_id'],
                    'artifact_sha256': artifact['sha256'],
                    'page_index': 0,
                    'source': 'ocr-text',
                },
            }
        )
        extraction_payload['symbols'].append(
            {
                'symbol_id': 'sym_c',
                'region_id': 'region_b',
                'symbol_type': 'material',
                'text': 'Al',
                'confidence': 0.83,
                'provenance': {
                    'artifact_id': artifact['artifact_id'],
                    'artifact_sha256': artifact['sha256'],
                    'page_index': 1,
                    'source': 'ocr-symbol',
                },
            }
        )

        extraction_response = client.post(
            f"/api/ai/artifacts/{artifact['artifact_id']}/extraction/review",
            json={
                'review_status': 'approved',
                'extraction': extraction_payload,
            },
        )
        assert extraction_response.status_code == 200
        extraction = extraction_response.get_json()

        planning_response = client.post(
            f"/api/ai/artifacts/{artifact['artifact_id']}/planning/envelope",
            json={
                'extraction': extraction['extraction'],
                'review_envelope': extraction['review_envelope'],
            },
        )

    assert planning_response.status_code == 200
    payload = planning_response.get_json()
    assert payload['success'] is True

    planning = payload['planning_envelope']
    assert planning['status'] == 'blocked'
    assert planning['summary']['error_count'] == 2
    assert planning['summary']['diagnostic_count'] == 2
    assert [entry['code'] for entry in planning['diagnostics']] == [
        'ambiguous_region_material_symbols',
        'unsupported_dimension_unit',
    ]


def test_artifact_planning_route_rejects_mismatched_review_envelope(client, tmp_path):
    pm = _build_project_manager(tmp_path)

    with patch('app.get_project_manager_for_session', return_value=pm):
        upload_response = client.post(
            '/api/ai/artifacts/upload',
            data={
                'artifact': (io.BytesIO(b'\x89PNG\r\n\x1a\nimage'), 'detector.png'),
            },
            content_type='multipart/form-data',
        )
        assert upload_response.status_code == 200
        artifact = upload_response.get_json()['artifact']

        extraction_response = client.post(
            f"/api/ai/artifacts/{artifact['artifact_id']}/extraction/review",
            json={
                'review_status': 'approved',
                'extraction': _payload_for_artifact(artifact),
            },
        )
        assert extraction_response.status_code == 200
        extraction = extraction_response.get_json()
        review_envelope = extraction['review_envelope']
        review_envelope['artifact_id'] = 'artifact_wrong'

        planning_response = client.post(
            f"/api/ai/artifacts/{artifact['artifact_id']}/planning/envelope",
            json={
                'extraction': extraction['extraction'],
                'review_envelope': review_envelope,
            },
        )

    assert planning_response.status_code == 400
    payload = planning_response.get_json()
    assert payload['success'] is False
    assert payload['error_code'] == 'planning_validation_error'
    assert 'review_envelope.artifact_id' in payload['error']


def test_artifact_planning_execute_route_applies_ready_plan_through_batch_geometry_tools(client, tmp_path):
    pm = _build_project_manager(tmp_path)

    with patch('app.get_project_manager_for_session', return_value=pm):
        upload_response = client.post(
            '/api/ai/artifacts/upload',
            data={
                'artifact': (io.BytesIO(b'\x89PNG\r\n\x1a\nimage'), 'detector.png'),
            },
            content_type='multipart/form-data',
        )
        assert upload_response.status_code == 200
        artifact = upload_response.get_json()['artifact']

        extraction_response = client.post(
            f"/api/ai/artifacts/{artifact['artifact_id']}/extraction/review",
            json={
                'review_status': 'approved',
                'extraction': _payload_for_artifact(artifact),
            },
        )
        assert extraction_response.status_code == 200
        extraction = extraction_response.get_json()

        execute_response = client.post(
            f"/api/ai/artifacts/{artifact['artifact_id']}/planning/execute",
            json={
                'extraction': extraction['extraction'],
                'review_envelope': extraction['review_envelope'],
                'region_bindings': {
                    'region_b': {
                        'logical_volume_name': 'box_LV',
                        'material_map': {
                            'si': 'G4_Galactic',
                        },
                    },
                },
            },
        )

    assert execute_response.status_code == 200
    payload = execute_response.get_json()
    assert payload['success'] is True
    assert payload['schema_version'].endswith('checkpoint5')
    assert payload['planning_envelope']['status'] == 'ready'
    assert payload['execution_plan']['status'] == 'ready'
    assert payload['execution_plan']['summary']['candidate_operation_count'] == 4
    assert payload['execution_plan']['summary']['mutation_operation_count'] == 3
    assert payload['execution_plan']['summary']['annotation_note_count'] == 1

    execution = payload['execution']
    assert execution['attempted'] is True
    assert execution['executed'] is True
    assert execution['operation_count'] == 3
    assert execution['batch_result']['success'] is True
    assert len(execution['batch_result']['batch_results']) == 3
    assert all(entry['success'] for entry in execution['batch_result']['batch_results'])

    assert 'MM_DIM_region_a_dim_a' in pm.current_geometry_state.defines
    assert 'MM_DIM_region_b_dim_b' in pm.current_geometry_state.defines
    assert pm.current_geometry_state.logical_volumes['box_LV'].material_ref == 'G4_Galactic'


def test_artifact_planning_execute_route_blocks_mutations_when_planning_is_blocked(client, tmp_path):
    pm = _build_project_manager(tmp_path)

    with patch('app.get_project_manager_for_session', return_value=pm):
        upload_response = client.post(
            '/api/ai/artifacts/upload',
            data={
                'artifact': (io.BytesIO(b'\x89PNG\r\n\x1a\nimage'), 'detector.png'),
            },
            content_type='multipart/form-data',
        )
        assert upload_response.status_code == 200
        artifact = upload_response.get_json()['artifact']

        extraction_payload = _payload_for_artifact(artifact)
        extraction_payload['dimensions'][0]['unit'] = 'inch'

        extraction_response = client.post(
            f"/api/ai/artifacts/{artifact['artifact_id']}/extraction/review",
            json={
                'review_status': 'approved',
                'extraction': extraction_payload,
            },
        )
        assert extraction_response.status_code == 200
        extraction = extraction_response.get_json()

        execute_response = client.post(
            f"/api/ai/artifacts/{artifact['artifact_id']}/planning/execute",
            json={
                'extraction': extraction['extraction'],
                'review_envelope': extraction['review_envelope'],
                'region_bindings': {
                    'region_b': {
                        'logical_volume_name': 'box_LV',
                        'material_map': {'si': 'G4_Galactic'},
                    },
                },
            },
        )

    assert execute_response.status_code == 409
    payload = execute_response.get_json()
    assert payload['success'] is False
    assert payload['error_code'] == 'planning_not_ready_for_execution'
    assert payload['planning_envelope']['status'] == 'blocked'
    assert payload['execution']['attempted'] is False
    assert 'MM_DIM_region_a_dim_a' not in pm.current_geometry_state.defines
