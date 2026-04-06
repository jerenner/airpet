import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.modules["src.step_parser"] = MagicMock()

from src.expression_evaluator import ExpressionEvaluator
from src.geometry_types import Material
from src.project_manager import ProjectManager


GEANT4_EXECUTABLE = Path(__file__).resolve().parents[1] / "geant4" / "build" / "airpet-sim"
GEANT4_BUILD_DIR = GEANT4_EXECUTABLE.parent


def _build_field_smoke_project():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()

    # Use silicon so the charged particle stops in a compact volume instead of looping in vacuum.
    pm.current_geometry_state.add_material(
        Material(
            name="Silicon",
            Z_expr="14",
            A_expr="28.0855",
            density_expr="2.33",
            state="solid",
        )
    )
    pm.current_geometry_state.logical_volumes["box_LV"].material_ref = "Silicon"
    success, error = pm.recalculate_geometry_state()
    assert success, error

    source, error = pm.configure_incident_beam(
        target="box_LV",
        particle="e-",
        energy="100 keV",
        incident_axis="+z",
        offset="1*mm",
        source_name="beam",
        activity=1.0,
        mark_target_sensitive=False,
        activate=True,
    )
    assert error is None
    assert source is not None

    return pm


def _build_electric_field_smoke_project():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()

    source, error = pm.configure_incident_beam(
        target="box_LV",
        particle="e-",
        energy="100 keV",
        incident_axis="+z",
        offset="1*mm",
        source_name="beam",
        activity=1.0,
        mark_target_sensitive=False,
        activate=True,
    )
    assert error is None
    assert source is not None

    return pm


def _run_field_case(pm, tmp_path, *, field_enabled):
    run_root = tmp_path / ("field_on" if field_enabled else "field_off")
    version_dir = run_root / "version"
    run_dir = run_root / "run"
    version_dir.mkdir(parents=True)
    run_dir.mkdir(parents=True)

    pm.current_geometry_state.environment.global_uniform_magnetic_field.enabled = field_enabled
    pm.current_geometry_state.environment.global_uniform_magnetic_field.field_vector_tesla = {
        "x": 0.0,
        "y": 1.0,
        "z": 0.0,
    }
    (version_dir / "version.json").write_text(pm.save_project_to_json_string(), encoding="utf-8")

    pm.generate_macro_file(
        f"field-smoke-{'on' if field_enabled else 'off'}",
        {
            "events": 1,
            "threads": 1,
            "seed1": 12345,
            "seed2": 67890,
            "save_hits": False,
            "save_particles": False,
            "save_hit_metadata": False,
            "save_tracks_range": "0-0",
        },
        str(GEANT4_BUILD_DIR),
        str(run_dir),
        str(version_dir),
    )

    env = os.environ.copy()
    env["G4PHYSICSLIST"] = "FTFP_BERT"
    env.pop("G4OPTICALPHYSICS", None)

    result = subprocess.run(
        [str(GEANT4_EXECUTABLE), "run.mac"],
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"Geant4 run failed for field_enabled={field_enabled}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    track_path = run_dir / "tracks" / "event_0000_tracks.txt"
    assert track_path.exists(), (
        f"Missing track output for field_enabled={field_enabled}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    return track_path


def _run_electric_field_case(pm, tmp_path, *, field_enabled):
    run_root = tmp_path / ("electric_field_on" if field_enabled else "electric_field_off")
    version_dir = run_root / "version"
    run_dir = run_root / "run"
    version_dir.mkdir(parents=True)
    run_dir.mkdir(parents=True)

    pm.current_geometry_state.environment.global_uniform_electric_field.enabled = field_enabled
    pm.current_geometry_state.environment.global_uniform_electric_field.field_vector_volt_per_meter = {
        "x": 0.0,
        # Keep the smoke responsive while still producing a visible bend.
        "y": 5.0e6,
        "z": 0.0,
    }
    (version_dir / "version.json").write_text(pm.save_project_to_json_string(), encoding="utf-8")

    pm.generate_macro_file(
        f"electric-field-smoke-{'on' if field_enabled else 'off'}",
        {
            "events": 1,
            "threads": 1,
            "seed1": 12345,
            "seed2": 67890,
            "save_hits": False,
            "save_particles": False,
            "save_hit_metadata": False,
            "save_tracks_range": "0-0",
        },
        str(GEANT4_BUILD_DIR),
        str(run_dir),
        str(version_dir),
    )

    env = os.environ.copy()
    env["G4PHYSICSLIST"] = "FTFP_BERT"
    env.pop("G4OPTICALPHYSICS", None)

    result = subprocess.run(
        [str(GEANT4_EXECUTABLE), "run.mac"],
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"Geant4 run failed for electric field_enabled={field_enabled}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    track_path = run_dir / "tracks" / "event_0000_tracks.txt"
    assert track_path.exists(), (
        f"Missing track output for electric field_enabled={field_enabled}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    return track_path


def _run_local_field_case(pm, tmp_path, *, field_enabled):
    run_root = tmp_path / ("local_field_on" if field_enabled else "local_field_off")
    version_dir = run_root / "version"
    run_dir = run_root / "run"
    version_dir.mkdir(parents=True)
    run_dir.mkdir(parents=True)

    pm.current_geometry_state.environment.local_uniform_magnetic_field.enabled = field_enabled
    pm.current_geometry_state.environment.local_uniform_magnetic_field.target_volume_names = ["box_LV"]
    pm.current_geometry_state.environment.local_uniform_magnetic_field.field_vector_tesla = {
        "x": 0.0,
        "y": 1.0,
        "z": 0.0,
    }
    (version_dir / "version.json").write_text(pm.save_project_to_json_string(), encoding="utf-8")

    pm.generate_macro_file(
        f"local-field-smoke-{'on' if field_enabled else 'off'}",
        {
            "events": 1,
            "threads": 1,
            "seed1": 12345,
            "seed2": 67890,
            "save_hits": False,
            "save_particles": False,
            "save_hit_metadata": False,
            "save_tracks_range": "0-0",
        },
        str(GEANT4_BUILD_DIR),
        str(run_dir),
        str(version_dir),
    )

    env = os.environ.copy()
    env["G4PHYSICSLIST"] = "FTFP_BERT"
    env.pop("G4OPTICALPHYSICS", None)

    result = subprocess.run(
        [str(GEANT4_EXECUTABLE), "run.mac"],
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"Geant4 run failed for local field_enabled={field_enabled}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    track_path = run_dir / "tracks" / "event_0000_tracks.txt"
    assert track_path.exists(), (
        f"Missing track output for local field_enabled={field_enabled}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    return track_path


def _read_primary_track_points(track_path):
    points = []
    saw_primary_track = False
    for raw_line in track_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("T "):
            if saw_primary_track:
                break
            saw_primary_track = True
            continue
        if saw_primary_track:
            x_str, y_str, z_str = line.split()
            points.append((float(x_str), float(y_str), float(z_str)))

    assert points, f"No trajectory points found in {track_path}"
    return points


@pytest.mark.skipif(not GEANT4_EXECUTABLE.exists(), reason="Geant4 smoke binary is not built")
def test_field_on_vs_field_off_changes_charged_particle_track(tmp_path):
    pm = _build_field_smoke_project()

    off_track = _run_field_case(pm, tmp_path, field_enabled=False)
    on_track = _run_field_case(pm, tmp_path, field_enabled=True)

    off_points = _read_primary_track_points(off_track)
    on_points = _read_primary_track_points(on_track)

    off_max_x = max(abs(x) for x, _, _ in off_points)
    on_max_x = max(abs(x) for x, _, _ in on_points)

    assert off_max_x < 0.05
    assert on_max_x > off_max_x + 0.1


@pytest.mark.skipif(not GEANT4_EXECUTABLE.exists(), reason="Geant4 smoke binary is not built")
def test_electric_field_on_vs_field_off_changes_charged_particle_track(tmp_path):
    pm = _build_electric_field_smoke_project()

    off_track = _run_electric_field_case(pm, tmp_path, field_enabled=False)
    on_track = _run_electric_field_case(pm, tmp_path, field_enabled=True)

    off_points = _read_primary_track_points(off_track)
    on_points = _read_primary_track_points(on_track)

    off_max_y = max(abs(y) for _, y, _ in off_points)
    on_max_y = max(abs(y) for _, y, _ in on_points)

    assert off_max_y < 0.05
    assert on_max_y > off_max_y + 0.02


@pytest.mark.skipif(not GEANT4_EXECUTABLE.exists(), reason="Geant4 smoke binary is not built")
def test_local_field_assignment_changes_track_inside_target_volume(tmp_path):
    pm = _build_field_smoke_project()

    off_track = _run_local_field_case(pm, tmp_path, field_enabled=False)
    on_track = _run_local_field_case(pm, tmp_path, field_enabled=True)

    off_points = _read_primary_track_points(off_track)
    on_points = _read_primary_track_points(on_track)

    off_max_x = max(abs(x) for x, _, _ in off_points)
    on_max_x = max(abs(x) for x, _, _ in on_points)

    assert off_max_x < 0.05
    assert on_max_x > off_max_x + 0.1
