import json
from pathlib import Path

from src.expression_evaluator import ExpressionEvaluator
from src.geometry_types import EnvironmentState, GeometryState
from src.project_manager import ProjectManager


def test_generate_macro_threads_saved_global_field_into_runtime_initialization(tmp_path):
    pm = ProjectManager(ExpressionEvaluator())

    version_dir = tmp_path / "version"
    version_dir.mkdir()

    saved_environment = {
        "global_uniform_magnetic_field": {
            "enabled": True,
            "field_vector_tesla": {"x": 0.0, "y": 1.5, "z": -0.25},
        },
        "global_uniform_electric_field": {
            "enabled": True,
            "field_vector_volt_per_meter": {"x": 0.0, "y": -2.0, "z": 0.5},
        },
        "local_uniform_magnetic_field": {
            "enabled": True,
            "target_volume_names": ["box_LV"],
            "field_vector_tesla": {"x": 0.0, "y": -0.5, "z": 0.25},
        },
        "local_uniform_electric_field": {
            "enabled": True,
            "target_volume_names": ["box_LV"],
            "field_vector_volt_per_meter": {"x": 0.0, "y": 0.75, "z": -0.25},
        },
    }

    state = GeometryState()
    state.environment = EnvironmentState.from_dict(saved_environment)
    (version_dir / "version.json").write_text(json.dumps(state.to_dict()), encoding="utf-8")

    macro_path = Path(
        pm.generate_macro_file(
            "field-job",
            {"events": 1},
            str(tmp_path),
            str(tmp_path),
            str(version_dir),
        )
    )
    macro_text = macro_path.read_text(encoding="utf-8")
    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))

    read_file_idx = macro_text.index("/g4pet/detector/readFile geometry.gdml")
    field_idx = macro_text.index("/globalField/setValue 0 1.5 -0.25 tesla")
    electric_field_idx = macro_text.index("/globalField/setElectricValue 0 -2 0.5 volt/m")
    local_field_idx = macro_text.index("/g4pet/detector/addLocalMagField box_LV|0|-0.5|0.25")
    local_electric_field_idx = macro_text.index("/g4pet/detector/addLocalElecField box_LV|0|0.75|-0.25")
    init_idx = macro_text.index("/run/initialize")

    assert read_file_idx < field_idx < electric_field_idx < local_field_idx < local_electric_field_idx < init_idx
    assert metadata["environment"] == saved_environment
