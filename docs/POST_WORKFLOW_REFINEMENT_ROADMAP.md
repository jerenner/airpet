# AIRPET Post-Workflow-Refinement Roadmap

Last updated: 2026-04-07

## Purpose

This roadmap sequences the next major AIRPET refinement phases after `docs/WORKFLOW_REFINEMENT_TRACKER.md` is exhausted.

It is intentionally phase-oriented rather than task-oriented:

- this file decides what comes next
- each active phase gets its own context and task tracker
- only one roadmap phase should be active at a time unless there is a deliberate manual override

## Activation Gate

Do not activate the next roadmap phase until one of the following is true:

- `docs/WORKFLOW_REFINEMENT_TRACKER.md` has no `NEXT` or `PENDING` items left
- workflow refinement is manually paused and the next phase is explicitly promoted

As of 2026-04-07, workflow refinement is exhausted, and R1 is now `DONE`.

## Product Direction

The near-term product direction should be:

- stronger Geant4 simulation-environment support
- stronger CAD interoperability and post-import editing
- stronger detector-specific geometry generators
- stronger scoring, run control, and reproducibility support

The near-term product direction should not be:

- trying to become a full general-purpose CAD replacement
- cloning a sketch/constraint/kernel CAD stack before simulation-environment gaps are addressed

## Phase Statuses

Statuses used here:

- `READY`
- `ACTIVE`
- `PLANNED`
- `DONE`
- `DEFERRED`

## Roadmap Overview

| Phase | Status | Why It Comes Next | Exit Signal |
| --- | --- | --- | --- |
| R1: Physics Environment Refinement | DONE | AIRPET already handles geometry and workflows well enough that missing field/environment capabilities were a bigger blocker for real Geant4 use | A user can define, save, inspect, and run field-aware simulations from AIRPET without hand-editing Geant4 code or macros |
| R2: CAD Interoperability Refinement | PLANNED | Complex mechanical shapes should usually come from CAD; AIRPET should be best-in-class at import, reimport, and simulation-oriented augmentation | Imported assemblies can be updated, grouped, annotated, and instrumented reliably inside AIRPET |
| R3: Detector Feature Generators | PLANNED | Many detector users need patterned holes, stacks, arrays, channels, and shields more than generic CAD sketching | Common detector-specific patterned and repeated geometry features can be created directly in AIRPET |
| R4: Advanced Scoring And Run Controls | PLANNED | Once environment and geometry authoring are stronger, users need richer outputs and expert run controls | AIRPET exposes useful scoring/tally/run-control features for broader study classes with strong regression coverage |
| R5: Packaging, Reproducibility, And Templates | PLANNED | As AIRPET becomes more capable, project portability and guided starting points matter more | Users can start from stable templates and carry reproducible run metadata and artifacts across machines |

## Current Next Phase

### R1: Physics Environment Refinement

Status: DONE

Objective:
Add the highest-value Geant4 simulation-environment capabilities, starting with magnetic fields and a shared environment model that later electric fields, cuts, and limits can reuse.

Why now:

- magnetic-field support is a widely useful missing capability
- it unlocks new classes of detector studies immediately
- it strengthens AIRPET as a Geant4 workflow product without pushing it into full CAD scope

Current focus:

- phase complete; field-aware run metadata and analysis summaries are now visible in outputs

Phase docs:

- `docs/PHYSICS_ENVIRONMENT_REFINEMENT_CONTEXT.md`
- `docs/PHYSICS_ENVIRONMENT_REFINEMENT_TRACKER.md`

Entry gate:

- workflow refinement has no remaining `NEXT` or `PENDING` items, or has been manually paused in favor of this phase

Exit criteria:

- global uniform magnetic field support works end to end from saved project state to Geant4 runtime
- the same environment layer can represent later local magnetic fields and electric fields cleanly
- at least one field-aware example or smoke path exists
- key field state is visible in saved project data and run metadata
- the backlog has either been completed or deliberately trimmed to a stable MVP stopping point

## Planned Successor Phases

### R2: CAD Interoperability Refinement

Objective:
Make imported CAD geometry substantially easier to reuse, update, annotate, and simulate inside AIRPET.

Seed backlog:

- stable STEP reimport against an existing AIRPET project without losing simulation-oriented annotations
- imported assembly grouping and selection improvements
- faster post-import material and sensitive-volume assignment flows
- provenance and diff visibility for imported parts
- import-time simplification and primitive-recognition feedback

### R3: Detector Feature Generators

Objective:
Add detector-oriented geometry generators that cover common real use cases without turning AIRPET into a full sketch-based CAD system.

Seed backlog:

- rectangular and circular hole-pattern generators
- layered detector-stack generator
- tiled sensor-array generator
- repeated support-rib and channel generators
- collimator / shield / coil recipe primitives

### R4: Advanced Scoring And Run Controls

Objective:
Expose higher-value Geant4 scoring and expert run controls that broaden the kinds of studies AIRPET can support.

Seed backlog:

- scoring-mesh MVP
- common tallies such as dose, fluence, and current
- richer run manifests and reproducibility metadata
- region-aware output controls
- selected expert controls such as user limits or biasing where practical

### R5: Packaging, Reproducibility, And Templates

Objective:
Make it easier to start useful projects quickly and carry them reliably between users and machines.

Seed backlog:

- project templates for common detector-study starting points
- environment validation and preflight summaries for shared projects
- reproducible run bundles with enough metadata to rerun or audit later
- clearer local-versus-portable dependency boundaries

## Explicitly Deferred

The following are intentionally not the next roadmap phase:

- full general-purpose CAD authoring
- deep sketch/constraint solving
- broad mechanical-design tooling unrelated to simulation setup

Those ideas can be revisited later if CAD interoperability plus detector feature generators still leave major gaps for core AIRPET users.
