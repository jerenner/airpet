import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch


def _ensure_stub(module_name, **attrs):
    try:
        if importlib.util.find_spec(module_name) is not None:
            return None
    except Exception:
        pass

    module = types.ModuleType(module_name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[module_name] = module
    return module


_ensure_stub(
    "requests",
    get=lambda *args, **kwargs: None,
    post=lambda *args, **kwargs: None,
)
if "requests" in sys.modules:
    _requests_exc = type("_RequestsExc", (Exception,), {})
    sys.modules["requests"].exceptions = types.SimpleNamespace(
        RequestException=_requests_exc,
        ConnectTimeout=_requests_exc,
        ReadTimeout=_requests_exc,
        Timeout=_requests_exc,
        ConnectionError=_requests_exc,
        InvalidURL=_requests_exc,
        InvalidSchema=_requests_exc,
        MissingSchema=_requests_exc,
        SSLError=_requests_exc,
    )

_ensure_stub("ollama", Client=object)
_ensure_stub("dotenv", load_dotenv=lambda *args, **kwargs: None, set_key=lambda *args, **kwargs: None, find_dotenv=lambda *args, **kwargs: "")
_ensure_stub("h5py")
_ensure_stub("pandas")
_ensure_stub("flask_cors", CORS=lambda *args, **kwargs: None)

google = _ensure_stub("google")
genai = _ensure_stub("google.genai")
if genai is not None:
    genai.client = types.SimpleNamespace(Client=object)
    genai.types = types.SimpleNamespace(GenerateContentConfig=object)
    if google is not None:
        google.genai = genai
    sys.modules["google.genai.client"] = genai.client
    sys.modules["google.genai.types"] = genai.types

_ensure_stub("PIL", Image=object)

occ = _ensure_stub("OCC")
core = _ensure_stub("OCC.Core")
if occ is not None and core is not None:
    occ.Core = core
    for submodule, names in {
        "STEPControl": ["STEPControl_Reader"],
        "TopAbs": ["TopAbs_SOLID", "TopAbs_FACE", "TopAbs_REVERSED"],
        "TopExp": ["TopExp_Explorer"],
        "BRep": ["BRep_Tool"],
        "BRepMesh": ["BRepMesh_IncrementalMesh"],
        "TopLoc": ["TopLoc_Location"],
        "gp": ["gp_Trsf"],
        "TDF": ["TDF_Label", "TDF_LabelSequence"],
        "XCAFDoc": ["XCAFDoc_DocumentTool"],
        "TDocStd": ["TDocStd_Document"],
        "STEPCAFControl": ["STEPCAFControl_Reader"],
    }.items():
        module = _ensure_stub(f"OCC.Core.{submodule}")
        if module is None:
            continue
        for name in names:
            setattr(module, name, type(name, (), {}))
        setattr(core, submodule, module)

import pytest

from app import dispatch_ai_tool
from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


CORPUS_PATH = Path(__file__).parent / "fixtures" / "ai" / "benchmark_corpus.json"
CORPUS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def _make_pm(tmp_path):
    pm = ProjectManager(ExpressionEvaluator())
    pm.projects_dir = str(tmp_path / "projects")
    pm.project_name = "ai_benchmark"
    pm.create_empty_project()
    return pm


def _state_summary(pm):
    summary = pm.current_geometry_state.to_dict()
    summary["current_version_id"] = pm.current_version_id
    summary["is_changed"] = pm.is_changed
    summary["project_name"] = pm.project_name
    return summary


def _assert_subset(actual, expected, path="root"):
    if isinstance(expected, dict):
        marker_keys = {"$contains", "$len", "$exists", "$any", "$approx"}
        if set(expected.keys()) & marker_keys:
            assert len(expected) == 1, f"{path}: marker dicts must not mix with nested keys"
            marker, value = next(iter(expected.items()))
            if marker == "$contains":
                assert isinstance(actual, str), f"{path}: expected string for contains check"
                assert value in actual, f"{path}: expected substring {value!r} in {actual!r}"
            elif marker == "$len":
                assert len(actual) == value, f"{path}: expected length {value}, got {len(actual)}"
            elif marker == "$exists":
                if value:
                    assert actual is not None, f"{path}: expected value to exist"
                else:
                    assert actual is None, f"{path}: expected value to be absent"
            elif marker == "$any":
                assert actual is not None, f"{path}: expected any non-null value"
            elif marker == "$approx":
                assert actual == pytest.approx(value), f"{path}: expected approx {value}, got {actual}"
            else:
                raise AssertionError(f"{path}: unsupported marker {marker!r}")
            return

        assert isinstance(actual, dict), f"{path}: expected dict, got {type(actual).__name__}"
        for key, value in expected.items():
            assert key in actual, f"{path}: missing key {key!r}"
            _assert_subset(actual[key], value, f"{path}.{key}")
        return

    if isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected list, got {type(actual).__name__}"
        assert len(actual) == len(expected), f"{path}: expected list length {len(expected)}, got {len(actual)}"
        for idx, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            _assert_subset(actual_item, expected_item, f"{path}[{idx}]")
        return

    assert actual == expected, f"{path}: expected {expected!r}, got {actual!r}"


def _run_steps(pm, steps):
    results = []
    for step in steps:
        result = dispatch_ai_tool(pm, step["tool"], step["args"])
        expected = step.get("expected")
        if expected is not None:
            _assert_subset(result, expected, f"{step['tool']}.result")
        else:
            assert result.get("success") is True, result
        results.append(result)
    return results


@pytest.mark.parametrize("case", CORPUS, ids=[case["name"] for case in CORPUS])
def test_ai_benchmark_corpus_cases(case, tmp_path):
    pm = _make_pm(tmp_path)

    _run_steps(pm, case.get("preconditions", []))

    if case["name"] == "run_simulation":
        version_dir = tmp_path / "version"
        version_dir.mkdir(parents=True, exist_ok=True)
        pm.current_version_id = "benchmark-version"
        pm.is_changed = False
        with patch.object(pm, "run_preflight_checks", return_value={"summary": {"can_run": True, "issue_count": 0}, "issues": []}), \
             patch.object(pm, "generate_macro_file", return_value=str(version_dir / "sim_runs" / "sim-job" / "run.mac")) as mock_macro, \
             patch.object(pm, "_get_version_dir", return_value=str(version_dir)), \
             patch("threading.Thread") as mock_thread:
            mock_thread.return_value.start.return_value = None

            results = _run_steps(pm, case["trace"])

        _assert_subset(results[-1], case["trace"][-1]["expected"], "run_simulation.final_result")
        assert mock_macro.call_args.args[1] == case["trace"][-1]["args"]
        assert mock_thread.call_args.kwargs["args"][3] == case["trace"][-1]["args"]
    elif case["name"] == "analysis_filter":
        with patch("app.get_simulation_analysis") as mock_route:
            def fake_get_simulation_analysis(version_id, job_id):
                from flask import jsonify, request

                return jsonify({
                    "success": True,
                    "analysis": {
                        "total_hits": 5,
                        "version_id": version_id,
                        "job_id": job_id,
                        "energy_bins": request.args.get("energy_bins"),
                        "spatial_bins": request.args.get("spatial_bins"),
                        "sensitive_detector": request.args.get("sensitive_detector", ""),
                    }
                })

            mock_route.side_effect = fake_get_simulation_analysis
            _run_steps(pm, case["trace"])
    else:
        _run_steps(pm, case["trace"])

    _assert_subset(_state_summary(pm), case["expected_state"], f"{case['name']}.state")
