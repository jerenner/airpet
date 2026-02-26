# M5.3 Decision Checklist — Surrogate/PINN Go-No-Go

_Last updated: 2026-02-24_

## Purpose
Use this checklist to decide whether AIRPET should proceed to a Phase 4 surrogate-assisted optimization scope, and under what constraints.

---

## Decision Gates

### Gate A — Objective Definition (**must pass**)
- [x] Primary objective(s) are defined in user terms **and** explicit formulas/metrics.
- [x] Constraints are explicit (hard constraints vs penalties).
- [x] Success criteria are fixed before evaluation.

**Current pre-fill (M5 synthetic benchmark):**
- Objective used: `score` (maximize)
- Additional tracked outputs: `score_noiseless`, `stability_flag`
- Synthetic failure flag integrated in data (`success` / `failed`)

**Status:** ✅ Pass (for synthetic benchmark scope)

---

### Gate B — Data Readiness (**must pass**)
- [x] Dataset export is reproducible (manifest + source run IDs + schema).
- [x] Adequate sample count for initial feasibility pass.
- [x] Failure metadata is retained.
- [x] Deterministic train/val split (seeded).

**Current pre-fill (`m5_synth_bench1`):**
- Rows total: **500**
- Train/Val: **400 / 100**
- Success/Failed: **450 / 50**
- Missing target: **50** (aligned with failed runs)
- Manifest + source run IDs present

**Status:** ✅ Pass

---

### Gate C — Surrogate Accuracy (**must pass for at least one model family**)
Target thresholds:
- R² ≥ 0.85
- NRMSE ≤ 15% target range (or agreed domain-equivalent)
- Stable across seeds
- Acceptable error in top-candidate region

**Current pre-fill (single-seed benchmark run):**
- **GP baseline:** RMSE **0.1987**, MAE **0.1499**, R² **0.9487**
- **MLP baseline:** RMSE **0.7324**, MAE **0.6251**, R² **0.3037**
- **MLP tuned (192 trials) best:** RMSE **0.7237**, R² **0.3201**

**Status:** ✅ Pass for GP; ❌ Fail for current MLP implementation

---

### Gate D — Optimization Value (**must pass**)
Compared to classical optimizer baseline:
- [ ] Surrogate-assisted loop gives ≥1.5x wall-clock speedup at equal objective quality
  - OR better objective at fixed wall-clock/simulation budget
- [ ] Best candidate replay/verify succeeds on true simulation repeats
- [ ] No increased invalid-geometry rate at final candidate stage

**Current pre-fill:**
- Surrogate model training/inference speed is demonstrated.
- End-to-end surrogate-assisted optimization loop vs classical baseline not yet benchmarked on real detector tasks.

**Status:** ⏳ Not yet evaluated (blocking gate)

---

### Gate E — Robustness & Safeguards (**should pass**)
- [x] Failed runs / missing targets handled safely in dataset pipeline.
- [x] Provenance artifacts captured (manifest, configs, reports).
- [ ] Out-of-domain detection + automatic fallback policy finalized.

**Status:** ⚠️ Partial

---

### Gate F — UX Readiness (**should pass for productized scope**)
- [ ] Intuitive objective builder UI (weights, constraints, penalties).
- [ ] Surrogate run controls and diagnostics in UI.
- [ ] User-facing explainability for selected candidate.

**Status:** ❌ Not started (CLI/API-first stage)

---

## Go/No-Go Rule
- **GO**: Gates A–D pass, with at least one of E/F sufficiently covered.
- **CONDITIONAL GO**: A/B pass, C passes for at least one model, D partially complete.
- **NO-GO / DEFER**: Any of A–D materially fails.

---

## Current Recommendation (pre-filled)
**Recommendation:** **CONDITIONAL GO (GP-first)**

Rationale:
1. Data/export and reproducibility foundations are in place.
2. GP shows strong predictive quality on benchmarked synthetic objective.
3. MLP baseline is not currently competitive (even after tuning sweep).
4. Blocking item remains Gate D: prove end-to-end optimization value against classical baseline on real detector objectives.

---

## Required Next Steps (to close M5.3)
1. Run at least one **real detector objective** benchmark (not synthetic only).
2. Implement and benchmark **surrogate-assisted optimization loop** vs classical optimizer.
3. Add replay/verification and safety checks to final-candidate handoff.
4. Produce a compact decision memo with quantitative results and Phase 4 minimum scope.

---

## Evidence Paths (current pre-fill)
- Dataset manifest:
  - `/Users/marth/projects/airpet/surrogate/datasets/m5_synth_bench1/manifest.json`
- GP report:
  - `/Users/marth/projects/airpet/surrogate/benchmarks/m5_synth_bench1/surrogate/experiments/m5_synth_bench1_gp/report.json`
- MLP report:
  - `/Users/marth/projects/airpet/surrogate/benchmarks/m5_synth_bench1/surrogate/experiments/m5_synth_bench1_mlp/report.json`
- MLP tuning sweep:
  - `/Users/marth/projects/airpet/surrogate/benchmarks/m5_synth_bench1/mlp_tuning_sweep.json`
