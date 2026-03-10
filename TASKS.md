# AIRPET Task Tracker

## In Progress

- None.

## Recently Completed

- **Preflight integrity hardening for world/placement references** (2026-03-10)
  - Added new preflight error checks for:
    - missing `world_volume_ref`
    - unknown `world_volume_ref`
    - missing placement `volume_ref`
    - unknown placement `volume_ref` (LV/assembly not found)
    - world volume incorrectly referenced as a child placement
  - Added regression tests in `tests/test_preflight.py` to lock behavior.
  - Why: these are simulation-blocking topology problems that should fail fast in deterministic preflight instead of surfacing later during run/export.

## Next Candidates

1. **Preflight graph cycle detection for LV/assembly placement hierarchy**
   - Detect recursive placement loops and report minimal cycle path.
   - Impact: high (prevents hard-to-debug traversal/export failures).

2. **Version selection diagnostics for preflight compare endpoints**
   - Include explicit ordering metadata (`ordering_basis`, timestamps, source path checks) in compare/list responses.
   - Impact: medium-high (improves reproducibility/debugging for AI + human workflows).

3. **Preflight check for procedural volume references (replica/division/parameterised)**
   - Validate referenced target volumes exist and bounds are sane before simulation.
   - Impact: medium (catches stale references outside plain `physvol`).
