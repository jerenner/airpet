# M5.3 Decision Memo — Surrogate/PINN Go-No-Go

_Last updated: 2026-02-24_

## 1) Executive Summary

**Decision:** **CONDITIONAL GO (GP-first)** for Phase 4 prototype scope.

We should proceed with a narrow surrogate-assisted path built around a GP baseline, while deferring broader MLP/PINN ambitions until real-task evidence improves.

Why:
- M5.1 data/export foundations are complete and reproducible.
- GP performs strongly on the current benchmark dataset.
- MLP is currently not competitive (even after tuning).
- Critical business gate still open: prove end-to-end wall-clock value on real detector objectives versus classical optimization.

---

## 2) Scope of this decision

This memo evaluates whether Phase 4 should begin surrogate-assisted optimization work.
It does **not** claim production readiness yet.

In scope:
- dataset pipeline readiness,
- surrogate baseline quality,
- experimental evidence from current benchmark,
- recommendation for next implementation scope.

Out of scope:
- full UI productization,
- PINN architecture commitment,
- final production SLOs.

---

## 3) What was implemented in M5

### M5.1 — Training dataset builder
Implemented pipeline that exports training-ready data from study/optimizer outputs with:
- parameter values,
- objective values,
- success/failure flags,
- run metadata,
- train/val split,
- manifest (schema, sources, target objective, counts).

Outputs:
- `dataset.csv`, `dataset.jsonl`, `train.csv`, `val.csv`, `train.jsonl`, `val.jsonl`, `manifest.json`.

### M5.2 — Surrogate baseline runner
Implemented config-driven experiment runner (CLI/API) for:
- GP baseline,
- MLP baseline,
- feature scaling,
- train/val evaluation,
- report and prediction artifacts.

### Synthetic benchmark harness
Implemented a minimal synthetic benchmark generator to validate pipeline behavior under controlled objective/noise/failure settings.

---

## 4) Evidence summary (current benchmark)

Benchmark dataset: `m5_synth_bench1`
- rows_total: **500**
- rows_train / rows_val: **400 / 100**
- success / failed: **450 / 50**
- missing target: **50**

Model results (same dataset):
- **GP:** RMSE **0.1987**, MAE **0.1499**, R² **0.9487**
- **MLP baseline:** RMSE **0.7324**, MAE **0.6251**, R² **0.3037**
- **MLP tuned (192 trials, best):** RMSE **0.7237**, MAE **0.6196**, R² **0.3201**

Interpretation:
- GP is currently a strong surrogate candidate for next-stage prototype work.
- Current MLP implementation/config class is not sufficient for this objective family.

---

## 5) Gate-by-gate status (from checklist)

- **Gate A (Objective Definition):** Pass for benchmark scope
- **Gate B (Data Readiness):** Pass
- **Gate C (Surrogate Accuracy):** Pass for GP; fail for current MLP
- **Gate D (Optimization Value vs classical):** Not yet closed (blocking)
- **Gate E (Robustness/Safeguards):** Partial
- **Gate F (UX readiness):** Not started (expected at this stage)

---

## 6) Risks and implications

### Key risk
Strong predictive metrics alone do not guarantee optimization value. We still need proof that surrogate-assisted search improves time/quality compared to classical optimizers on real detector tasks.

### Practical implication
Proceeding now is justified only with tight scope control:
- GP-first,
- objective-specific evaluation,
- fallback to classical optimization,
- replay/verification on true simulation before accepting candidates.

---

## 7) Decision

### Final decision
**CONDITIONAL GO** to Phase 4 prototype, with the following constraints:

1. **Model strategy:** GP-first only (MLP/PINN deferred).
2. **Validation requirement:** Must demonstrate end-to-end speed/quality advantage over classical baseline on at least one real detector objective.
3. **Safety requirement:** Best-candidate replay + verification required before adoption.
4. **Fallback requirement:** Automatic classical fallback for low-confidence/out-of-domain regions.

If these conditions are not met, default back to classical optimizer-first roadmap.

---

## 8) Minimum Phase 4 scope (recommended)

1. Surrogate-assisted propose/evaluate loop with periodic true-simulation checks.
2. Single real objective family with clear intuitive mapping and constraints.
3. Quantitative benchmark harness (same budget, same seed family) comparing:
   - classical optimizer,
   - surrogate-assisted optimizer.
4. Decision dashboard/report with:
   - objective value,
   - wall-clock,
   - simulation call count,
   - failure rate,
   - replay verification stats.

---

## 9) Exit criteria to close conditional status

Move from **Conditional Go** to **Go** when:
- a real-task benchmark shows meaningful wall-clock advantage (e.g., ≥1.5x) at acceptable objective error,
- replay/verification confirms candidate stability,
- no unacceptable increase in invalid runs,
- minimum fallback safeguards are in place.

---

## 10) Evidence paths

- Checklist:
  - `/Users/marth/projects/airpet/docs/M5_3_DECISION_CHECKLIST.md`
- Benchmark dataset manifest:
  - `/Users/marth/projects/airpet/surrogate/datasets/m5_synth_bench1/manifest.json`
- GP report:
  - `/Users/marth/projects/airpet/surrogate/benchmarks/m5_synth_bench1/surrogate/experiments/m5_synth_bench1_gp/report.json`
- MLP report:
  - `/Users/marth/projects/airpet/surrogate/benchmarks/m5_synth_bench1/surrogate/experiments/m5_synth_bench1_mlp/report.json`
- MLP tuning sweep:
  - `/Users/marth/projects/airpet/surrogate/benchmarks/m5_synth_bench1/mlp_tuning_sweep.json`
