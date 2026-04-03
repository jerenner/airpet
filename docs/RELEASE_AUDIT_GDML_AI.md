# GDML + AI Release Audit Checklist

Date: 2026-04-02

## Overall Status

Conditional pass.

This release looks reasonable to ship if the release notes describe AIRPET AI as an AI-assisted geometry/simulation workflow, not a full natural-language front end for every UI feature, and if GDML support is described as strong for AIRPET-authored/core cases rather than universally complete for all external GDML variants.

## Release-Blocking Claims To Avoid

- Fail if release messaging says the AI can do everything the UI can do.
- Fail if release messaging implies full/general GDML compatibility for arbitrary third-party files.

## Automated Checks Completed

Pass:
- GDML writer/parser targeted suite
- AI integration streaming/history suite
- AI API slice for simulation/material/source/analysis/preflight/route-bridge behavior
- Preflight deterministic validation suite
- Parameter study / objective builder suite

Commands run:

```bash
conda run --no-capture-output -n virtualpet pytest tests/test_gdml.py tests/test_ai_integration.py -q
conda run --no-capture-output -n virtualpet pytest tests/test_ai_api.py -q -k 'simulation or incident_beam or particle_source or material or analysis or preflight or route_bridge'
conda run --no-capture-output -n virtualpet pytest tests/test_preflight.py -q
conda run --no-capture-output -n virtualpet pytest tests/test_param_study.py -q
```

Observed results:
- `30 passed`
- `117 passed, 31 deselected`
- `112 passed`
- `46 passed`

## Key Findings

### 1. AI feature coverage is strong but not full UI parity

Pass:
- geometry creation/modification
- define/material/source workflows
- incident beam setup
- simulation launch/status/summary
- analysis fetch
- preflight comparison workflows
- parameter registry / optimization workflows

Conditional:
- the AI simulation tool schema only exposes `events` and `threads` directly
- the UI exposes additional simulation controls such as production cut, hit threshold, metadata saving, physics list, and optical physics
- the AI analysis schema still does not expose every UI filter, but sensitive-detector selection is now available

Implication:
- ship-safe if scoped honestly
- not ship-safe if marketed as complete AI parity with the whole UI

### 2. GDML support is solid for core AIRPET flows, but external/import coverage is not universal

Pass:
- core writer coverage for AIRPET-authored geometry
- material density unit serialization fix
- tessellated solid vertex deduplication

Conditional:
- parameterised solid import mappings are explicitly partial
- parser rejects unsupported external entities and modular file references
- some malformed or partially supported constructs are skipped with warnings rather than repaired

Implication:
- ship-safe if described as robust for AIRPET/core GDML workflows
- not ship-safe if described as complete support for arbitrary external GDML

## Manual Release Checklist

Mark each item pass/fail on the release candidate build.

### AI Core

- [ ] Pass / Fail: Gemini creates a simple slab + beam setup without tool or history errors
- [ ] Pass / Fail: Directed beam created by AI shows a correct arrow and launches along that direction
- [ ] Pass / Fail: AI can modify an existing define-driven geometry and the render updates immediately
- [ ] Pass / Fail: AI run-simulation flow performs preflight and reports failures cleanly
- [ ] Pass / Fail: AI thoughts/tool activity card appears live and persists after final response
- [ ] Pass / Fail: Refresh after an AI turn preserves prompt, reply, and saved thoughts/tool trace

### Simulation / Analysis

- [ ] Pass / Fail: Sensitive detector hits are written when a sensitive LV is present
- [ ] Pass / Fail: Analysis modal opens from Simulation and renders plots for a completed run
- [ ] Pass / Fail: Sensitive-detector filter in Analysis works on runs saved with hit metadata
- [ ] Pass / Fail: Simulation Options correctly persist hit threshold, production cut, and metadata toggle
- [ ] Pass / Fail: Thin-target electron study behaves plausibly with a lowered production cut

### GDML Export / Import

- [ ] Pass / Fail: Exported GDML with custom material density loads in Geant4 without absurd cut-table behavior
- [ ] Pass / Fail: AIRPET-authored GDML re-imports into AIRPET for at least one representative detector geometry
- [ ] Pass / Fail: Boolean solids with transforms export and reload correctly
- [ ] Pass / Fail: Tessellated solids export and reload correctly
- [ ] Pass / Fail: At least one parameterised-volume example imports correctly if this feature is advertised

### Param Studies

- [ ] Pass / Fail: Wizard auto-detect finds define-driven parameters for a simple slab-thickness study
- [ ] Pass / Fail: Review in Basic and Save Study work without registry errors
- [ ] Pass / Fail: Preview sweep shows ranked results in the modal
- [ ] Pass / Fail: Simulation-in-loop sweep respects selected source subset
- [ ] Pass / Fail: Downloaded study JSON includes top-level source provenance summary

### History / UX

- [ ] Pass / Fail: Single delete for runs and versions works correctly
- [ ] Pass / Fail: Bulk-select delete works without collapsing the wrong history sections
- [ ] Pass / Fail: Bottom panel resize and full-collapse behavior are stable

## Recommended Release Positioning

Safe wording:
- AI-assisted geometry design, simulation setup, and quick analysis
- strong support for AIRPET-authored GDML and core Geant4 workflows

Unsafe wording:
- complete AI control over every AIRPET feature
- full compatibility with arbitrary GDML files from any source

## Suggested First Post-Release Audit Targets

1. Expand GDML parser/import coverage for parameterised solids beyond the currently mapped cases.
2. Bring AI simulation/analysis tool schemas closer to UI parity for advanced simulation options and analysis filters.
3. Build a small named regression corpus of real GDML files and benchmark AI prompts for recurring release checks.
