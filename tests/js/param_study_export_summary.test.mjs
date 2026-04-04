import test from 'node:test';
import assert from 'node:assert/strict';

import { buildResultExportSummary } from '../../static/paramStudyEditor.js';

test('buildResultExportSummary includes simulation source provenance from run results', () => {
    const summary = buildResultExportSummary({
        study_name: 'si_sweep',
        simulation_in_loop: true,
        evaluations_used: 8,
        success_count: 8,
        failure_count: 0,
        objective: { name: 'score', direction: 'maximize' },
        best_run: {
            run_index: 3,
            simulation: {
                selected_source_ids: ['src-1'],
                selected_source_names: ['Beam A'],
            },
        },
        candidates: [],
    });

    assert.equal(summary.study_name, 'si_sweep');
    assert.equal(summary.kind, 'optimizer');
    assert.equal(summary.simulation_in_loop, true);
    assert.equal(summary.best_run_index, 3);
    assert.equal(summary.source_provenance.mode, 'simulation_result');
    assert.deepEqual(summary.source_provenance.selected_source_ids, ['src-1']);
    assert.deepEqual(summary.source_provenance.selected_source_names, ['Beam A']);
    assert.equal(summary.source_provenance.label, 'Beam A');
});

test('buildResultExportSummary falls back to launch payload sources when run-level provenance is absent', () => {
    const summary = buildResultExportSummary(
        {
            study_name: 'launch_only',
            simulation_in_loop: true,
            evaluations_used: 4,
            success_count: 4,
            failure_count: 0,
            candidates: [{ run_index: 0, success: true }],
        },
        {
            launchContext: {
                run_payload: {
                    study_name: 'launch_only',
                    selected_source_ids: ['src-a', 'src-b'],
                    selected_sources: [
                        { id: 'src-a', name: 'Source A' },
                        { id: 'src-b', name: 'Source B' },
                    ],
                },
            },
        },
    );

    assert.equal(summary.source_provenance.mode, 'launch_payload');
    assert.deepEqual(summary.source_provenance.selected_source_ids, ['src-a', 'src-b']);
    assert.deepEqual(summary.source_provenance.selected_source_names, ['Source A', 'Source B']);
    assert.equal(summary.source_provenance.label, 'Source A, Source B');
});

test('buildResultExportSummary marks preview sweeps as having no simulation sources', () => {
    const summary = buildResultExportSummary({
        study_name: 'preview_only',
        requested_runs: 3,
        evaluations_used: 3,
        successful_runs: 3,
        failed_runs: 0,
        runs: [{ run_index: 0, success: true }],
    });

    assert.equal(summary.kind, 'sweep');
    assert.equal(summary.source_provenance.mode, 'preview_only');
    assert.equal(summary.source_provenance.label, 'Preview sweep only; no simulation sources were used.');
    assert.deepEqual(summary.source_provenance.selected_source_ids, []);
    assert.deepEqual(summary.source_provenance.selected_source_names, []);
});
