# AIRPET Physics Environment Refinement Context

Last updated: 2026-04-07

## Roadmap Position

This is the first planned post-workflow-refinement phase in `docs/POST_WORKFLOW_REFINEMENT_ROADMAP.md`.

It should become the active refinement loop once `docs/WORKFLOW_REFINEMENT_TRACKER.md` has no remaining `NEXT` or `PENDING` items, or if workflow refinement is explicitly paused in favor of environment work.

## Mission

Expand AIRPET from a strong geometry-and-workflow tool into a stronger simulation environment tool by adding the highest-value Geant4 environment capabilities that materially change what users can simulate.

This phase starts with magnetic and electric fields, then broadens into adjacent simulation-environment controls that belong in a detector-focused Geant4 workflow layer.

## Product Position

AIRPET should not try to become a full general-purpose CAD package.

The more valuable position is:

- detector-focused geometry and simulation workflow authoring
- strong import-and-augment support for CAD-built parts
- first-class Geant4-specific simulation configuration
- automation and AI support for common detector design tasks

That means physics-environment controls are a better next investment than a full sketch/constraint/kernel CAD expansion.

## Why This Phase Comes Next

Recent work has materially improved:

- AI + GDML correctness
- workflow-level regression coverage
- STEP/smart-import support for CAD-driven geometry handoff

What still limits AIRPET's usefulness for a broader range of Geant4 studies is the lack of run-output visibility and higher-level environment reporting:

- field-aware run metadata and analysis summaries
- richer scoring and environment-aware run controls

These features unlock new classes of detector studies without requiring AIRPET to become a full CAD replacement.

## Current Ground Truth

As of 2026-04-07:

- AIRPET already has a meaningful STEP import and smart CAD path.
- AIRPET already supports detector geometry, materials, sources, param studies, optimization workflows, and a growing regression corpus.
- AIRPET now supports global uniform magnetic fields, global uniform electric fields, local logical-volume magnetic/electric-field assignments, region-specific production cuts and user limits, and field-aware run metadata and analysis summaries in saved state, macro generation, UI, AI, Geant4 runtime plumbing, and outputs.
- The remaining environment work, if any, now belongs to successor phases.

## Scope

In scope:

- magnetic and electric field configuration
- field assignment at global and local scope
- UI / backend / AI plumbing for field definition
- validation, serialization, and regression coverage for field-aware simulations
- closely adjacent simulation-environment controls such as region cuts and user limits

Out of scope for this phase:

- full CAD authoring parity with tools like FreeCAD
- arbitrary mechanical design tooling unrelated to simulation setup
- broad analysis/visualization redesign unless directly needed by the selected task

## Design Principles

Prefer:

- a small, explicit environment model over ad hoc flags
- detector-focused field use cases before exotic generalization
- global-field MVP before local-volume and mixed-field complexity
- one source of truth shared by UI, AI, saved project state, and Geant4 runtime
- compact example assets and regression tests for each new capability

Avoid:

- hidden Geant4 defaults that the user cannot inspect
- field features that only exist in the runtime and not in saved project state
- UI-only features that AI or automation cannot configure

## Candidate Capability Sequence

1. Global uniform magnetic field project-state schema and runtime plumbing.
2. Deterministic field-on versus field-off coverage.
3. UI and AI support for field configuration and inspection.
4. Electric field support on the same abstraction.
5. Field-aware run metadata and analysis summaries. Completed in PER-010.
6. Field-aware scoring or run-configuration follow-ons if needed.

## Suggested Example Assets

Prefer small, deterministic examples that prove environment behavior clearly:

- uniform-field charged-particle deflection
- local drift or field-cage style volume assignment
- a minimal silicon or slab detector with field-on / field-off comparison

## Definition Of Done

A physics-environment task is only `DONE` when:

- the new environment capability is represented in saved AIRPET project state
- the Geant4 runtime consumes it correctly
- at least one focused regression or deterministic smoke test protects it
- the UI and/or AI surfaces expose the capability when appropriate
- the tracker records files changed, tests run, outcome, and next task

## Likely Successor Phases

After this tracker is substantially complete, the next good phases are likely:

1. CAD Interoperability Refinement
2. Detector Feature Generators
3. Advanced Scoring and Run Controls
