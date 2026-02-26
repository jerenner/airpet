import h5py
import numpy as np

from src.objective_engine import extract_objective_values_from_hdf5


def test_extract_objective_values_from_hdf5_formula_and_context(tmp_path):
    out = tmp_path / "output.hdf5"
    with h5py.File(out, "w") as f:
        g = f.create_group("default_ntuples/Hits")
        g.create_dataset("Edep", data=np.array([1.0, 2.0, 3.0], dtype=float))
        g.create_dataset("CopyNo", data=np.array([1, 1, 2], dtype=int))
        g.create_dataset("ParticleName", data=np.array([b"gamma", b"e-", b"gamma"]))
        g.create_dataset("entries", data=np.array([3], dtype=int))

    values, warnings, available = extract_objective_values_from_hdf5(
        output_path=str(out),
        objectives=[
            {"name": "sum1", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"},
            {"name": "cost", "metric": "context_value", "key": "cost_norm"},
            {"name": "score", "metric": "formula", "expression": "0.5*sum1 - cost"},
        ],
        context={"cost_norm": 1.0},
    )

    assert values["sum1"] == 6.0
    assert values["cost"] == 1.0
    assert values["score"] == 2.0
    assert warnings == []
    assert "hdf5_reduce" in available
    assert "formula" in available
