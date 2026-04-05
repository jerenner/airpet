import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import numpy as np


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
import app

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


def _resolve_placeholders(value, context):
    if isinstance(value, str) and value.startswith("$"):
        key = value[1:]
        if key not in context:
            raise KeyError(f"Missing workflow context value for placeholder {value!r}")
        return context[key]

    if isinstance(value, dict):
        return {key: _resolve_placeholders(subvalue, context) for key, subvalue in value.items()}

    if isinstance(value, list):
        return [_resolve_placeholders(item, context) for item in value]

    return value


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
    context = {}
    for step in steps:
        step_args = _resolve_placeholders(step["args"], context)
        result = dispatch_ai_tool(pm, step["tool"], step_args)
        expected = step.get("expected")
        if expected is not None:
            _assert_subset(result, expected, f"{step['tool']}.result")
        else:
            assert result.get("success") is True, result
        results.append(result)
        if isinstance(result, dict):
            context.update(result)
    return results


_FAKE_H5_REGISTRY = {}


class _FakeH5Dataset:
    def __init__(self, data):
        self._data = np.asarray(data)

    @property
    def shape(self):
        return self._data.shape

    def __getitem__(self, item):
        return self._data[item]


class _FakeH5Group:
    def __init__(self, name=""):
        self.name = name
        self._children = {}

    def create_group(self, name):
        group = self
        for part in str(name).split("/"):
            if not part:
                continue
            child = group._children.get(part)
            if child is None:
                child = _FakeH5Group(part)
                group._children[part] = child
            elif not isinstance(child, _FakeH5Group):
                raise TypeError(f"Path component '{part}' already exists as a dataset.")
            group = child
        return group

    def create_dataset(self, name, data):
        dataset = _FakeH5Dataset(data)
        self._children[name] = dataset
        return dataset

    def _resolve(self, path):
        obj = self
        for part in str(path).split("/"):
            if not part:
                continue
            if not isinstance(obj, _FakeH5Group) or part not in obj._children:
                raise KeyError(path)
            obj = obj._children[part]
        return obj

    def __contains__(self, path):
        try:
            self._resolve(path)
            return True
        except KeyError:
            return False

    def __getitem__(self, path):
        return self._resolve(path)


class _FakeH5File(_FakeH5Group):
    def __init__(self, path, mode="r"):
        super().__init__("root")
        self.path = str(path)
        self.mode = mode
        if "r" in mode:
            existing = _FAKE_H5_REGISTRY.get(self.path)
            if existing is None:
                raise FileNotFoundError(self.path)
            self._children = existing._children

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if any(flag in self.mode for flag in ("w", "a", "+")):
            _FAKE_H5_REGISTRY[self.path] = self
        return False


def _fake_h5_file_factory(path, mode="r"):
    return _FakeH5File(path, mode=mode)


def _write_fake_simulation_output(run_dir, sensitive_detector):
    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    output_path = run_path / "output.hdf5"
    output_path.touch(exist_ok=True)

    with app.h5py.File(output_path, "w") as h5:
        hits = h5.create_group("default_ntuples/Hits")
        hits.create_dataset("entries", data=4)
        hits.create_dataset("Edep", data=np.array([0.015, 0.020, 0.025, 0.030], dtype=float))
        hits.create_dataset("PosX", data=np.array([0.0, 1.0, 2.0, 3.0], dtype=float))
        hits.create_dataset("PosY", data=np.array([0.0, 1.5, 3.0, 4.5], dtype=float))
        hits.create_dataset("PosZ", data=np.array([0.0, -0.5, -1.0, -1.5], dtype=float))
        hits.create_dataset("CopyNo", data=np.array([0, 0, 1, 1], dtype=int))
        hits.create_dataset("ParticleName", data=np.array([b"e-", b"e-", b"gamma", b"gamma"], dtype="S5"))
        hits.create_dataset(
            "SensitiveDetectorName",
            data=np.array([sensitive_detector.encode("utf-8")] * 4, dtype=f"S{max(8, len(sensitive_detector))}"),
        )


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
    elif case["name"] == "geometry_preflight_simulation_analysis":
        version_dir = tmp_path / "version"
        version_dir.mkdir(parents=True, exist_ok=True)
        pm.current_version_id = "benchmark-version"
        pm.is_changed = False

        sensitive_detector = case["trace"][2]["args"]["sensitive_detector"]

        def fake_run_g4_simulation(job_id, run_dir, executable_path, sim_params):
            _write_fake_simulation_output(run_dir, sensitive_detector)

        class _FakeCounts:
            def __init__(self, counts):
                self.index = np.array(list(counts.keys()), dtype=object)
                self.values = np.array(list(counts.values()), dtype=int)

        class _FakeSeries:
            def __init__(self, values):
                self._values = list(values)

            def value_counts(self):
                from collections import Counter

                return _FakeCounts(Counter(self._values))

        def fake_series(values):
            return _FakeSeries(values)

        with patch.object(app.h5py, "File", side_effect=_fake_h5_file_factory, create=True), \
             patch.object(app.h5py, "Group", _FakeH5Group, create=True), \
             patch.object(app.h5py, "Dataset", _FakeH5Dataset, create=True), \
             patch.object(app.pd, "Series", side_effect=fake_series, create=True), \
             patch.object(pm, "_get_version_dir", return_value=str(version_dir)), \
             patch.object(pm, "generate_macro_file", return_value=str(version_dir / "sim_runs" / "sim-job" / "run.mac")) as mock_macro, \
             patch("app.run_g4_simulation", side_effect=fake_run_g4_simulation) as mock_run_g4, \
             patch("threading.Thread") as mock_thread, \
             patch("app.get_project_manager_for_session", return_value=pm):
            mock_thread.return_value.start.side_effect = lambda: mock_thread.call_args.kwargs["target"](
                *mock_thread.call_args.kwargs["args"]
            )
            results = _run_steps(pm, case["trace"])

        _assert_subset(results[-1], case["trace"][-1]["expected"], "geometry_preflight_simulation_analysis.final_result")
        assert mock_macro.call_args.args[1] == case["trace"][1]["args"]
        assert mock_run_g4.call_count == 1
        assert mock_thread.call_count == 1
    else:
        _run_steps(pm, case["trace"])

    _assert_subset(_state_summary(pm), case["expected_state"], f"{case['name']}.state")
