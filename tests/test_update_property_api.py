import pytest

import app as app_module


class _FakeProjectManager:
    def __init__(self, update_result):
        self.update_result = update_result
        self.calls = []

    def update_object_property(self, object_type, object_id, property_path, new_value):
        self.calls.append((object_type, object_id, property_path, new_value))
        return self.update_result


@pytest.fixture
def update_payload():
    return {
        "object_type": "logical_volume",
        "object_id": "DetectorLV",
        "property_path": "material_ref",
        "new_value": "G4_Si",
    }


@pytest.mark.parametrize("raw_body", ["[]", '"not-an-object"', "null"])
def test_update_property_route_rejects_non_object_json_payload(monkeypatch, raw_body):
    app_module.app.config["TESTING"] = True

    def _unexpected_project_manager():
        pytest.fail("Project manager should not be called for malformed payload validation failures")

    monkeypatch.setattr(app_module, "get_project_manager_for_session", _unexpected_project_manager)

    with app_module.app.test_client() as client:
        response = client.post(
            "/update_property",
            data=raw_body,
            content_type="application/json",
        )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Invalid JSON payload for property update"


@pytest.mark.parametrize(
    "field,value",
    [
        ("object_type", None),
        ("object_type", ""),
        ("object_type", "   "),
        ("object_id", None),
        ("object_id", ""),
        ("object_id", "   "),
        ("property_path", None),
        ("property_path", ""),
        ("property_path", "   "),
        ("property_path", 42),
    ],
)
def test_update_property_route_rejects_missing_or_invalid_required_fields(monkeypatch, update_payload, field, value):
    app_module.app.config["TESTING"] = True

    payload = dict(update_payload)
    payload[field] = value

    def _unexpected_project_manager():
        pytest.fail("Project manager should not be called for required-field validation failures")

    monkeypatch.setattr(app_module, "get_project_manager_for_session", _unexpected_project_manager)

    with app_module.app.test_client() as client:
        response = client.post("/update_property", json=payload)

    assert response.status_code == 400
    result = response.get_json()
    assert result["success"] is False
    assert result["error"] == f"Missing or invalid '{field}' for property update"


def test_update_property_route_rejects_unsupported_object_type(monkeypatch, update_payload):
    app_module.app.config["TESTING"] = True

    payload = dict(update_payload)
    payload["object_type"] = "assembly"

    def _unexpected_project_manager():
        pytest.fail("Project manager should not be called for unsupported object_type values")

    monkeypatch.setattr(app_module, "get_project_manager_for_session", _unexpected_project_manager)

    with app_module.app.test_client() as client:
        response = client.post("/update_property", json=payload)

    assert response.status_code == 400
    result = response.get_json()
    assert result["success"] is False
    assert result["error"] == "Unsupported object_type 'assembly' for property update"


@pytest.mark.parametrize("property_path", [".material_ref", "material_ref.", "content..number", "content...number"])
def test_update_property_route_rejects_invalid_property_path_format(monkeypatch, update_payload, property_path):
    app_module.app.config["TESTING"] = True

    payload = dict(update_payload)
    payload["property_path"] = property_path

    def _unexpected_project_manager():
        pytest.fail("Project manager should not be called for invalid property_path values")

    monkeypatch.setattr(app_module, "get_project_manager_for_session", _unexpected_project_manager)

    with app_module.app.test_client() as client:
        response = client.post("/update_property", json=payload)

    assert response.status_code == 400
    result = response.get_json()
    assert result["success"] is False
    assert result["error"] == f"Invalid property_path '{property_path}'"


def test_update_property_route_maps_invalid_property_path_failures_to_400(monkeypatch, update_payload):
    app_module.app.config["TESTING"] = True

    fake_pm = _FakeProjectManager((False, "Invalid property path 'material_ref'."))

    monkeypatch.setattr(app_module, "get_project_manager_for_session", lambda: fake_pm)
    monkeypatch.setattr(
        app_module,
        "create_success_response",
        lambda *_args, **_kwargs: app_module.jsonify({"success": True, "message": "should-not-run"}),
    )

    with app_module.app.test_client() as client:
        response = client.post("/update_property", json=update_payload)

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Invalid property path 'material_ref'."
    assert fake_pm.calls == [
        ("logical_volume", "DetectorLV", "material_ref", "G4_Si")
    ]


def test_update_property_route_maps_missing_object_failures_to_404(monkeypatch, update_payload):
    app_module.app.config["TESTING"] = True

    fake_pm = _FakeProjectManager((False, "Could not find object of type 'logical_volume' with ID/Name 'DetectorLV'"))

    monkeypatch.setattr(app_module, "get_project_manager_for_session", lambda: fake_pm)

    with app_module.app.test_client() as client:
        response = client.post("/update_property", json=update_payload)

    assert response.status_code == 404
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"].startswith("Could not find object of type")


def test_update_property_route_unclassified_tuple_failures_remain_500(monkeypatch, update_payload):
    app_module.app.config["TESTING"] = True

    fake_pm = _FakeProjectManager((False, "Update failed during recalculation: expression parse error"))

    monkeypatch.setattr(app_module, "get_project_manager_for_session", lambda: fake_pm)

    with app_module.app.test_client() as client:
        response = client.post("/update_property", json=update_payload)

    assert response.status_code == 500
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Update failed during recalculation: expression parse error"


@pytest.mark.parametrize("update_result", [True, (True, None)])
def test_update_property_route_accepts_bool_and_tuple_success(monkeypatch, update_payload, update_result):
    app_module.app.config["TESTING"] = True

    fake_pm = _FakeProjectManager(update_result)

    monkeypatch.setattr(app_module, "get_project_manager_for_session", lambda: fake_pm)
    monkeypatch.setattr(
        app_module,
        "create_success_response",
        lambda *_args, **_kwargs: app_module.jsonify({"success": True, "message": "stub-success"}),
    )

    with app_module.app.test_client() as client:
        response = client.post("/update_property", json=update_payload)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {"success": True, "message": "stub-success"}


def test_update_property_route_bool_failure_uses_default_error_message(monkeypatch, update_payload):
    app_module.app.config["TESTING"] = True

    fake_pm = _FakeProjectManager(False)

    monkeypatch.setattr(app_module, "get_project_manager_for_session", lambda: fake_pm)
    monkeypatch.setattr(
        app_module,
        "create_success_response",
        lambda *_args, **_kwargs: app_module.jsonify({"success": True, "message": "should-not-run"}),
    )

    with app_module.app.test_client() as client:
        response = client.post("/update_property", json=update_payload)

    assert response.status_code == 500
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Failed to update property"
