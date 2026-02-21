# AIRPET Benchmarks

## Smart Import Benchmark Harness (M2)

Compares STEP import in two modes:
- `tessellated_baseline` (`smartImport=false`)
- `smart_import` (`smartImport=true`)

Implemented in:
- `scripts/benchmark_smart_import.py`

### Quick start

1. Copy and edit config:

```bash
cp benchmarks/configs/m2_baseline.example.json benchmarks/configs/m2_baseline.local.json
```

Set `step_file` to a real STEP path.

2. Run benchmark:

```bash
python scripts/benchmark_smart_import.py --config benchmarks/configs/m2_baseline.local.json
```

Optional explicit output path:

```bash
python scripts/benchmark_smart_import.py \
  --config benchmarks/configs/m2_baseline.local.json \
  --output benchmarks/results/m2_run1.json
```

Print a compact summary from a result file:

```bash
python scripts/summarize_smart_import_benchmark.py benchmarks/results/m2_run1.json
```

Check result against threshold policy:

```bash
python scripts/check_benchmark_thresholds.py \
  --thresholds benchmarks/thresholds/example_thresholds.json \
  --result benchmarks/results/m2_run1.json
```

### Output

Output JSON includes per-mode metrics:
- import elapsed seconds
- `import.normalized_summary` (stable keys across baseline + smart modes)
  - `imported_solid_count`
  - report availability/enabled flags
  - candidate/selection stats (null when smart report is not enabled)
- raw import report summary (when available)
- optional simulation timing/status (if `simulation.enabled=true`)

Default output directory:
- `benchmarks/results/`

### Notes

- Harness runs in-process via Flask test client (no separate server required).
- Simulation benchmarking is optional and may require local Geant4 runtime setup.
- Use `benchmarks/reports/TEMPLATE.md` to document shareable benchmark results when needed.
