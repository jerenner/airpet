# Silicon Detector Example Assets

## Optimizer starter project

Use this file for the Param Studies/Objective Builder first-run tutorial:

- `silicon_optimizer_starter.project.json`

### How to load in AIRPET

1. Open AIRPET.
2. Go to **File → Load Geometry (JSON)...**
3. Select `examples/silicon_detector/silicon_optimizer_starter.project.json`.
4. Open **Param Studies** and keep **View mode = Basic** for the first run.
5. Use **Guided Prep: Validate → Build → Dry Run**, then click **Run Simulation-in-Loop** in the modal footer.

### Included starter setup

- Geometry: simple silicon slab detector + mono-energetic electron source.
- Parameter registry: `si_thickness`, `src_z` (both mapped to formal defines: `si_thickness_mm`, `src_z_mm`).
- Starter param study: `si_first_run` (random, 16 samples, seed 42).
- Starter objective: maximize `edep_sum` (via score `edep_sum`).
