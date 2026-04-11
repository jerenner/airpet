import test from 'node:test';
import assert from 'node:assert/strict';

import {
    buildResolvedSimulationOptions,
    buildScoringResultSummary,
    buildScoringStateWithAddedMesh,
    buildScoringStateWithRemovedMesh,
    buildScoringStateWithUpdatedRunManifestDefaults,
    buildSimulationOptionOverrides,
    compareScoringResultSummaries,
    describeScoringMesh,
    describeScoringPanelState,
    describeScoringRunControls,
    describeScoringResultComparison,
    describeScoringResultSummary,
    formatScoringQuantityLabel,
    isMeshTallyEnabled,
    replaceScoringMesh,
    setMeshTallyEnabled,
} from '../../static/scoringUi.js';

test('adding a scoring mesh creates a default energy deposit tally and deterministic summary', () => {
    const nextState = buildScoringStateWithAddedMesh({
        scoring_meshes: [],
        tally_requests: [],
    });

    assert.equal(nextState.scoring_meshes.length, 1);
    assert.equal(nextState.tally_requests.length, 1);
    assert.equal(nextState.scoring_meshes[0].mesh_id, 'scoring_mesh_ui_1');
    assert.equal(nextState.scoring_meshes[0].name, 'box_mesh_1');
    assert.equal(nextState.tally_requests[0].mesh_ref.mesh_id, 'scoring_mesh_ui_1');
    assert.equal(nextState.tally_requests[0].mesh_ref.name, 'box_mesh_1');
    assert.equal(nextState.tally_requests[0].quantity, 'energy_deposit');

    const described = describeScoringMesh(nextState.scoring_meshes[0], nextState);
    assert.equal(
        described.summary,
        'World box mesh · center 0 x 0 x 0 mm · size 10 x 10 x 10 mm · bins 10 x 10 x 10 · 1 enabled tally',
    );

    const panelState = describeScoringPanelState({ scoring: nextState });
    assert.equal(panelState.intro, '1 enabled scoring mesh across 1 enabled tally request.');
    assert.equal(
        panelState.hint,
        'energy_deposit and n_of_step tallies currently emit runtime scoring artifacts. Other saved tallies remain editable here for upcoming runtime slices.',
    );
});

test('saved scoring run controls normalize cleanly and drive resolved simulation defaults', () => {
    const projectState = {
        scoring: {
            run_manifest_defaults: {
                threads: '3',
                seed1: '11',
                seed2: 22,
                print_progress: '250',
                save_hits: false,
                save_hit_metadata: false,
                save_particles: true,
                production_cut: '0.25 mm',
                hit_energy_threshold: '7 eV',
            },
        },
    };

    const nextScoringState = buildScoringStateWithUpdatedRunManifestDefaults(projectState.scoring, {
        print_progress: '0',
        save_hits: true,
    });
    assert.deepEqual(nextScoringState.run_manifest_defaults, {
        events: 1000,
        threads: 3,
        seed1: 11,
        seed2: 22,
        print_progress: 0,
        save_hits: true,
        save_hit_metadata: false,
        save_particles: true,
        production_cut: '0.25 mm',
        hit_energy_threshold: '7 eV',
    });

    const described = describeScoringRunControls(projectState.scoring);
    assert.equal(
        described.summary,
        '3 threads · seeds 11/22 · print every 250 event(s) · cut 0.25 mm · hit threshold 7 eV',
    );
    assert.deepEqual(described.detailLines, [
        'Saved outputs: particles',
        'Simulation Options can override these defaults for a single run.',
    ]);

    const resolvedOptions = buildResolvedSimulationOptions(projectState, {
        threads: 4,
        save_tracks_range: '12-18',
        physics_list: 'QGSP_BERT',
        optical_physics: true,
    });
    assert.deepEqual(resolvedOptions, {
        events: 1000,
        threads: 4,
        seed1: 11,
        seed2: 22,
        print_progress: 250,
        save_hits: false,
        save_hit_metadata: false,
        save_particles: true,
        production_cut: '0.25 mm',
        hit_energy_threshold: '7 eV',
        save_tracks_range: '12-18',
        physics_list: 'QGSP_BERT',
        optical_physics: true,
    });

    const overrides = buildSimulationOptionOverrides(projectState, {
        threads: 3,
        seed1: 11,
        seed2: 22,
        print_progress: 250,
        save_hits: false,
        save_hit_metadata: false,
        save_particles: true,
        production_cut: '0.5 mm',
        hit_energy_threshold: '7 eV',
        save_tracks_range: '4-9',
        physics_list: 'QGSP_BERT',
        optical_physics: true,
    });
    assert.deepEqual(overrides, {
        production_cut: '0.5 mm',
        save_tracks_range: '4-9',
        physics_list: 'QGSP_BERT',
        optical_physics: true,
    });
});

test('replacing a scoring mesh name keeps linked tally references aligned', () => {
    const initialState = buildScoringStateWithAddedMesh({
        scoring_meshes: [],
        tally_requests: [],
    });
    const mesh = initialState.scoring_meshes[0];

    const renamedState = replaceScoringMesh(initialState, mesh.mesh_id, {
        ...mesh,
        name: 'study_mesh',
        geometry: {
            ...mesh.geometry,
            size_mm: { x: 25, y: 15, z: 5 },
        },
    });

    assert.equal(renamedState.scoring_meshes[0].name, 'study_mesh');
    assert.equal(renamedState.tally_requests[0].mesh_ref.mesh_id, mesh.mesh_id);
    assert.equal(renamedState.tally_requests[0].mesh_ref.name, 'study_mesh');
    assert.equal(
        describeScoringMesh(renamedState.scoring_meshes[0], renamedState).summary,
        'World box mesh · center 0 x 0 x 0 mm · size 25 x 15 x 5 mm · bins 10 x 10 x 10 · 1 enabled tally',
    );
});

test('tally toggles add and remove per-mesh quantity requests deterministically', () => {
    const initialState = buildScoringStateWithAddedMesh({
        scoring_meshes: [],
        tally_requests: [],
    });
    const mesh = initialState.scoring_meshes[0];

    const withDose = setMeshTallyEnabled(initialState, mesh, 'dose_deposit', true);
    assert.equal(isMeshTallyEnabled(withDose, mesh.mesh_id, 'energy_deposit'), true);
    assert.equal(isMeshTallyEnabled(withDose, mesh.mesh_id, 'dose_deposit'), true);
    assert.equal(withDose.tally_requests.length, 2);

    const withStepCount = setMeshTallyEnabled(withDose, mesh, 'n_of_step', true);
    assert.equal(isMeshTallyEnabled(withStepCount, mesh.mesh_id, 'n_of_step'), true);
    assert.equal(withStepCount.tally_requests.length, 3);

    const withoutEnergyDeposit = setMeshTallyEnabled(withStepCount, mesh, 'energy_deposit', false);
    assert.equal(isMeshTallyEnabled(withoutEnergyDeposit, mesh.mesh_id, 'energy_deposit'), false);
    assert.equal(isMeshTallyEnabled(withoutEnergyDeposit, mesh.mesh_id, 'dose_deposit'), true);
    assert.equal(isMeshTallyEnabled(withoutEnergyDeposit, mesh.mesh_id, 'n_of_step'), true);
    assert.equal(withoutEnergyDeposit.tally_requests.length, 2);
    assert.equal(formatScoringQuantityLabel('passage_cell_flux'), 'passage cell flux');

    const removedMeshState = buildScoringStateWithRemovedMesh(withoutEnergyDeposit, mesh.mesh_id);
    assert.deepEqual(removedMeshState.scoring_meshes, []);
    assert.deepEqual(removedMeshState.tally_requests, []);
});

test('buildScoringResultSummary derives compact loaded-run scoring totals from metadata', () => {
    const summary = buildScoringResultSummary({
        timestamp: '2026-04-11T15:00:00',
        total_events: 12,
        scoring_summary: {
            enabled_mesh_count: 2,
            enabled_tally_count: 2,
        },
        scoring_artifacts: {
            artifact_bundle_path: 'scoring_artifacts.json',
            generated_artifact_count: 2,
            skipped_tally_count: 0,
            summary: {
                quantity_summaries: [
                    {
                        quantity: 'energy_deposit',
                        unit: 'MeV',
                        generated_artifact_count: 1,
                        total_value: 7.25,
                    },
                    {
                        quantity: 'n_of_step',
                        unit: 'steps',
                        generated_artifact_count: 1,
                        total_value: 12,
                    },
                ],
            },
        },
        run_manifest_summary: {
            version_id: 'version_a',
            job_id: 'job_a_12345678',
            resolved_run_manifest: {
                events: 12,
                threads: 2,
            },
            execution_settings: {
                physics_list: 'FTFP_BERT',
                optical_physics: true,
            },
            artifact_bundle: {
                exists: true,
                path: 'scoring_artifacts.json',
                source_output: {
                    exists: true,
                },
            },
            comparison_keys: {
                geometry_sha256: 'geom-a',
                environment_signature: 'env-a',
                scoring_signature: 'score-a',
                run_manifest_signature: 'manifest-a',
                execution_signature: 'exec-a',
            },
        },
    });

    assert.equal(summary.runKey, 'version_a:job_a_12345678');
    assert.equal(summary.summaryText, 'energy deposit 7.25 MeV · n of step 12 steps');
    assert.equal(summary.bundleExists, true);
    assert.equal(summary.totalEvents, 12);
    assert.equal(summary.threads, 2);
    assert.equal(summary.physicsList, 'FTFP_BERT');
    assert.equal(summary.opticalPhysics, true);
    assert.deepEqual(summary.quantitySummaries, [
        {
            quantity: 'energy_deposit',
            label: 'energy deposit',
            unit: 'MeV',
            generatedArtifactCount: 1,
            totalValue: 7.25,
            totalValueText: '7.25 MeV',
        },
        {
            quantity: 'n_of_step',
            label: 'n of step',
            unit: 'steps',
            generatedArtifactCount: 1,
            totalValue: 12,
            totalValueText: '12 steps',
        },
    ]);

    const described = describeScoringResultSummary(summary);
    assert.equal(described.statusBadge, 'artifacts ready');
    assert.equal(described.meta, '12 events · 2 threads · FTFP_BERT · optical on');
    assert.deepEqual(described.quantityLines, [
        'energy deposit: 7.25 MeV across 1 artifact',
        'n of step: 12 steps across 1 artifact',
    ]);
});

test('compareScoringResultSummaries reports quantity deltas and manifest drift', () => {
    const baseline = buildScoringResultSummary({
        scoring_summary: {
            enabled_mesh_count: 1,
            enabled_tally_count: 1,
        },
        scoring_artifacts: {
            generated_artifact_count: 1,
            summary: {
                quantity_summaries: [
                    {
                        quantity: 'energy_deposit',
                        unit: 'MeV',
                        generated_artifact_count: 1,
                        total_value: 3.5,
                    },
                ],
            },
        },
        run_manifest_summary: {
            version_id: 'version_a',
            job_id: 'job_old_12345678',
            resolved_run_manifest: {
                events: 8,
                threads: 1,
            },
            execution_settings: {
                physics_list: 'FTFP_BERT',
                optical_physics: false,
            },
            artifact_bundle: {
                exists: true,
                path: 'scoring_artifacts.json',
            },
            comparison_keys: {
                geometry_sha256: 'geom-a',
                environment_signature: 'env-a',
                scoring_signature: 'score-a',
                run_manifest_signature: 'manifest-a',
                execution_signature: 'exec-a',
            },
        },
    });
    const candidate = buildScoringResultSummary({
        scoring_summary: {
            enabled_mesh_count: 1,
            enabled_tally_count: 2,
        },
        scoring_artifacts: {
            generated_artifact_count: 2,
            summary: {
                quantity_summaries: [
                    {
                        quantity: 'energy_deposit',
                        unit: 'MeV',
                        generated_artifact_count: 1,
                        total_value: 5,
                    },
                    {
                        quantity: 'n_of_step',
                        unit: 'steps',
                        generated_artifact_count: 1,
                        total_value: 9,
                    },
                ],
            },
        },
        run_manifest_summary: {
            version_id: 'version_b',
            job_id: 'job_new_12345678',
            resolved_run_manifest: {
                events: 10,
                threads: 2,
            },
            execution_settings: {
                physics_list: 'QGSP_BERT',
                optical_physics: true,
            },
            artifact_bundle: {
                exists: true,
                path: 'scoring_artifacts.json',
            },
            comparison_keys: {
                geometry_sha256: 'geom-b',
                environment_signature: 'env-a',
                scoring_signature: 'score-b',
                run_manifest_signature: 'manifest-b',
                execution_signature: 'exec-b',
            },
        },
    });

    const comparison = compareScoringResultSummaries(baseline, candidate);
    assert.equal(
        comparison.summaryText,
        'energy deposit +1.5 MeV · n of step +9 steps | Changed geometry, scoring setup, run manifest, execution settings',
    );
    assert.deepEqual(comparison.changedSections, [
        'geometry',
        'scoring setup',
        'run manifest',
        'execution settings',
    ]);
    assert.deepEqual(comparison.quantityDeltas, [
        {
            quantity: 'energy_deposit',
            label: 'energy deposit',
            unit: 'MeV',
            baselineTotalValue: 3.5,
            candidateTotalValue: 5,
            deltaValue: 1.5,
            deltaText: '+1.5 MeV',
            baselineArtifactCount: 1,
            candidateArtifactCount: 1,
            direction: 'up',
        },
        {
            quantity: 'n_of_step',
            label: 'n of step',
            unit: 'steps',
            baselineTotalValue: 0,
            candidateTotalValue: 9,
            deltaValue: 9,
            deltaText: '+9 steps',
            baselineArtifactCount: 0,
            candidateArtifactCount: 1,
            direction: 'up',
        },
    ]);

    const described = describeScoringResultComparison(comparison);
    assert.equal(described.statusBadge, 'delta detected');
    assert.equal(described.meta, `Baseline ${baseline.runLabel}`);
    assert.deepEqual(described.detailLines, ['Changed: geometry, scoring setup, run manifest, execution settings']);
    assert.deepEqual(described.deltaLines, [
        'energy deposit: +1.5 MeV',
        'n of step: +9 steps',
    ]);
});
