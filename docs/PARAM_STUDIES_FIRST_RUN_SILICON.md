# Param Studies — First Run Draft (Silicon Detector)

## Why this example
Use the silicon slab beam monitor as the canonical first optimization example:
- Real detector geometry (not toy math)
- Few intuitive parameters
- Clear objective (`Edep` in silicon)
- Fast enough for short tutorial runs

**Starter project asset:**
- [`examples/silicon_detector/silicon_optimizer_starter.project.json`](../examples/silicon_detector/silicon_optimizer_starter.project.json)

---

## 1) Objective Builder wording (draft copy)

### Section title
**Objective Builder**

### Field labels + helper text

- **Template**
  - Helper: "Start with `weighted_tradeoff` unless you need a custom objective."

- **Simulation metric dataset path**
  - Default: `default_ntuples/Hits/Edep`
  - Helper: "For silicon detector optimization, this should usually stay `default_ntuples/Hits/Edep`."

- **Context cost key (optional)**
  - Placeholder: `optional (e.g. cost_norm)`
  - Helper: "Leave blank for your first run. Add only if you already pass a cost term in run context."

- **Score expression**
  - Default: `edep_sum`
  - Placeholder: `edep_sum - 0.15*si_thickness - 0.02*abs(src_z)`
  - Helper: "Start simple with `edep_sum`, then add penalties for thickness/cost if needed."

- **Guided button text**
  - `Guided Prep: Validate → Build → Dry Run`

- **Run button text (simulation-in-loop)**
  - `Run Simulation-in-Loop`

---

## 2) Default parameter bounds (starter profile)

Use this minimal 2-parameter setup for the first tutorial run:

Implementation mapping in the starter asset:
- `si_thickness` → define target `si_thickness_mm`
- `src_z` → define target `src_z_mm` (used by source `src_electron.position.z`)

| Parameter | Meaning | Min | Max | Default | Notes |
|---|---|---:|---:|---:|---|
| `si_thickness` | Silicon slab thickness (mm) | 0.05 | 6.0 | 1.5 | Controls interaction depth and material usage |
| `src_z` | Source z-position (mm) | -50.0 | -5.0 | -20.0 | Controls source-to-detector distance |

Optional third parameter for step 2 tutorial:

| Parameter | Meaning | Min | Max | Default | Notes |
|---|---|---:|---:|---:|---|
| `si_half_x` | Half-width of slab in x (mm) | 5.0 | 35.0 | 12.5 | Adds area/cost tradeoff |

---

## 3) One-page "first run" script (user-facing)

## First Optimization Run (Silicon Detector)

This walkthrough shows the shortest path from "no study" to "first useful result."

### Step 0 — Open the starter project
1. In AIRPET, go to **File → Load Geometry (JSON)...**
2. Load `examples/silicon_detector/silicon_optimizer_starter.project.json`.
3. Confirm the parameter registry includes `si_thickness` and `src_z`.
4. Open **Param Studies**.
5. Keep **View mode = Basic**.

### Step 1 — Select or create the study
The starter project already includes `si_first_run`. You can use it directly, or recreate it with:
1. **Name**: `si_first_run`
2. **Mode**: `random`
3. **Parameters**: `si_thickness,src_z`
4. **Random Samples**: `16`
5. **Seed**: `42`

### Step 2 — Define objective (simple)
1. In **Objective Builder**, click **Load Example**.
2. Set/confirm:
   - Dataset path: `default_ntuples/Hits/Edep`
   - Score expression: `edep_sum`
   - Context cost key: *(blank)*
3. Click **Guided Prep: Validate → Build → Dry Run**.
4. If validation is clean, click **Save**.

### Step 3 — Run real simulation-in-loop optimization
1. In the modal footer, click **Run Simulation-in-Loop**.
2. Wait for completion.
3. Inspect **Last run output** and ranking table.

> Note: **Run Sweep (No Simulation)** in the modal footer only evaluates geometry/parameter sweeps and does not launch Geant4 runs.

### Step 4 — Interpret quickly
- Higher `edep_sum` = better for this first run.
- Check whether best points cluster at extreme `si_thickness` or extreme `src_z`.
- If all best points sit on bounds, widen bounds in that direction for run 2.

### Step 5 — Run 2 (add realistic penalty)
1. Keep same parameters.
2. Change score to:
   - `edep_sum - 0.15*si_thickness - 0.02*abs(src_z)`
3. Run again with 20–30 samples.
4. Compare top candidates with run 1:
   - Did thickness drop?
   - Did source move closer/farther?
   - How much `edep_sum` was traded for lower "cost"?

### Done criteria for this tutorial
You are done when you can answer:
1. Which configuration maximizes raw `edep_sum`?
2. Which configuration gives the best penalized score?
3. What tradeoff did the penalty introduce?

---

## Suggested next tutorial after this one
- Add `si_half_x` and `si_half_y` to introduce geometry/cost tradeoff.
- Then switch users to **Advanced** view for optimizer diagnostics and verify/apply workflow.
