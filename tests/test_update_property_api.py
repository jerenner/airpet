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


def test_update_property_route_propagates_tuple_failure_error(monkeypatch, update_payload):
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

    assert response.status_code == 500
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["error"] == "Invalid property path 'material_ref'."
    assert fake_pm.calls == [
        ("logical_volume", "DetectorLV", "material_ref", "G4_Si")
    ]


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
