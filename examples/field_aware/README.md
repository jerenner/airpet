# Field-Aware Silicon Example Assets

## Field-aware silicon starter project

Use this file when you want a compact silicon detector project with saved field settings already enabled:

- `field_aware_silicon_starter.project.json`

### How to load in AIRPET

1. Open AIRPET.
2. Go to **File → Load Geometry (JSON)...**
3. Select `examples/field_aware/field_aware_silicon_starter.project.json`.
4. Open **Properties** and inspect the **Environment** accordion to see the saved global field settings.

### Included starter setup

- Geometry: the same small silicon slab detector used by the original first-run tutorial.
- Fields: global magnetic and electric fields are enabled; local field assignments stay off so you can add them deliberately later.
- Parameter registry: `si_thickness`, `src_z` (both mapped to formal defines: `si_thickness_mm`, `src_z_mm`).
- Starter param study: `si_first_run` (random, 16 samples, seed 42).
- Starter objective: maximize `edep_sum` (via score `edep_sum`).

### Reusable field template

If you want a compact probe volume in another project, use the `field_probe_slab` physics template.

- Parameters: `size` and `thickness`
- Default material: `G4_SILICON`
- Result: a sensitive square slab that works well as a local field target or field-on / field-off comparator
