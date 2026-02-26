# Surrogate experiments (M5)

## M5.1 Dataset builder

Build a training dataset from existing AIRPET study/optimizer outputs:

```bash
python scripts/export_surrogate_dataset.py \
  --input /path/to/project/versions \
  --output-root surrogate/datasets \
  --dataset-name m5_dataset \
  --target-objective success \
  --val-ratio 0.2 \
  --split-seed 42
```

Outputs are written to `surrogate/datasets/<dataset-name>/`:

- `dataset.csv`
- `dataset.jsonl`
- `train.csv`
- `val.csv`
- `train.jsonl`
- `val.jsonl`
- `manifest.json`

## API flow

- `POST /api/surrogate/dataset/export`
  - Uses current session optimizer runs by default.
  - Optional payload keys: `dataset_name`, `target_objective`, `val_ratio`, `split_seed`, `only_success`, `output_root`.
  - Can also include `study_result` and/or `optimizer_runs` in request body.

- `POST /api/surrogate/experiment/run`
  - Run with either:
    - `{"config_path": "path/to/config.json"}`
    - `{"config": { ...inline config... }}`

- `POST /api/param_optimizer/head_to_head`
  - Runs classical optimizer vs surrogate optimizer on the same study/budget/seed.
  - Payload supports:
    - `study_name`, `budget`, `seed`, `objective_name`, `direction`
    - `classical_method` (`random_search` or `cmaes`)
    - `cmaes` config
    - `surrogate` config (`warmup_runs`, `candidate_pool_size`, `exploration_beta`, `gp_noise`)

## Synthetic benchmark generator (recommended for early M5 validation)

Generate a controlled synthetic dataset + ready-to-run experiment configs:

```bash
python scripts/generate_synthetic_surrogate_benchmark.py \
  --preset nonlinear_3d \
  --runs 400 \
  --seed 42
```

This writes:

- synthetic optimizer-run payload (`surrogate/benchmarks/<dataset>/synthetic_optimizer_runs.json`)
- benchmark report (`surrogate/benchmarks/<dataset>/benchmark_report.json`)
- generated configs:
  - `example_experiment_gp.json`
  - `example_experiment_mlp.json`
- dataset files under `surrogate/datasets/<dataset>/...`

Equivalent API route:

- `POST /api/surrogate/synthetic/generate`

## M5.2 experiment runner

Run baseline surrogate experiment from config:

```bash
python scripts/run_surrogate_experiment.py --config surrogate/configs/example_experiment.json
```

Artifacts are written to:

- `surrogate/experiments/<experiment_name>/report.json`
- `surrogate/experiments/<experiment_name>/val_predictions.csv`

## Head-to-head runner (classical vs surrogate)

```bash
python scripts/run_optimizer_head_to_head.py \
  --project-json /path/to/version.json \
  --study-name my_study \
  --budget 40 \
  --classical-method cmaes
```

This outputs a JSON comparison with:
- best objective values,
- winner (`classical` / `surrogate` / `tie`),
- elapsed time for each side,
- run IDs and full run details.

## Silicon Slab v1.1 (simulation-backed objective path)

Generate a self-contained starter project + v1.1 objective spec:

```bash
python scripts/create_silicon_slab_v1_project.py \
  --output surrogate/benchmarks/silicon_slab_v1/project.json
```

Evaluate objective spec directly on an HDF5 output:

```bash
python scripts/evaluate_objectives_from_hdf5.py \
  --hdf5 /path/to/output.hdf5 \
  --objectives surrogate/benchmarks/silicon_slab_v1/silicon_slab_v1_1_objectives.json
```

Simulation-in-loop optimizer routes:

- `POST /api/param_optimizer/run_simulation_in_loop`
  - Runs one optimizer (`surrogate_gp`, `random_search`, or `cmaes`) with per-candidate simulation.
- `POST /api/param_optimizer/head_to_head_simulation_in_loop`
  - Runs classical vs surrogate comparison, both backed by simulation-in-loop evaluation.

Both routes require:
- `study_name`
- `sim_params` (events/threads/seeds/etc.)
- `sim_objectives` (objective extraction spec for simulation output)

Supported simulation objective extraction metrics include:
- `hdf5_reduce` (any HDF5 dataset path + reducer)
- `context_value`
- `constant`
- `formula`

And study objectives can compose these via:
- `sim_metric` + `parameter_value` + `formula`
