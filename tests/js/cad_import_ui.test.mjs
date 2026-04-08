import test from 'node:test';
import assert from 'node:assert/strict';

import {
    buildCadImportBatchContext,
    buildCadImportReimportContext,
    buildCadImportSelectionContext,
    describeCadImportRecord,
} from '../../static/cadImportUi.js';

test('cad import provenance helpers describe a full STEP import deterministically', () => {
    const record = {
        import_id: 'step_import_abc123',
        source: {
            format: 'step',
            filename: 'fixture.step',
            sha256: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
            size_bytes: 42,
        },
        options: {
            grouping_name: 'fixture_import',
            placement_mode: 'assembly',
            parent_lv_name: 'World',
            offset: { x: '1', y: '2', z: '3' },
            smart_import_enabled: true,
        },
        smart_import_summary: {
            enabled: true,
            summary: {
                total: 3,
                primitive_count: 2,
                tessellated_count: 1,
                primitive_ratio: 2 / 3,
                selected_mode_counts: { primitive: 1, tessellated: 2 },
                selected_primitive_ratio: 1 / 3,
                counts_by_classification: {
                    box: 1,
                    cylinder: 1,
                    sphere: 0,
                    cone: 0,
                    torus: 0,
                    tessellated: 1,
                },
            },
            summary_text: '2 primitive candidates, 2 tessellated fallbacks',
            primitive_candidate_count: 2,
            selected_primitive_count: 1,
            selected_tessellated_count: 2,
            fallback_reason_counts: {
                below_confidence_threshold: 1,
                no_primitive_match_v1: 1,
            },
            top_fallback_reasons: [
                { reason: 'below_confidence_threshold', count: 1 },
                { reason: 'no_primitive_match_v1', count: 1 },
            ],
        },
        created_object_ids: {
            solid_ids: ['solid-1'],
            logical_volume_ids: ['lv-1'],
            assembly_ids: ['assembly-1'],
            placement_ids: ['placement-1', 'placement-2'],
            top_level_placement_ids: ['placement-1'],
        },
        created_group_names: {
            solid: 'fixture_import_solids',
            logical_volume: 'fixture_import_lvs',
            assembly: 'fixture_import_assemblies',
        },
    };

    const described = describeCadImportRecord(record);

    assert.equal(described.title, 'fixture_import');
    assert.equal(
        described.summary,
        'STEP import from fixture.step · placement mode: assembly · smart CAD on · 2 primitive candidates, 2 tessellated fallbacks',
    );
    assert.equal(described.createdObjectSummary, '1 solid, 1 logical volume, 1 assembly, 2 placements');
    assert.equal(
        described.createdGroupSummary,
        'fixture_import_solids, fixture_import_lvs, fixture_import_assemblies',
    );
    assert.equal(described.selectionContext.selectionSummary, '1 top-level placement');
    assert.deepEqual(described.selectionContext.selectionIds, ['placement-1']);
    assert.deepEqual(
        described.detailRows.map((row) => row.label),
        [
            'Import ID',
            'Source File',
            'Source SHA256',
            'Grouping Name',
            'Placement Mode',
            'Parent LV',
            'Placement Offset',
            'Smart CAD',
            'Smart CAD Outcome',
            'Created Objects',
            'Created Groups',
            'Imported Logical Volumes',
            'Top-Level Selection',
        ],
    );
    assert.equal(described.detailRows.find((row) => row.label === 'Smart CAD Outcome').value.text, '2 primitive candidates, 2 tessellated fallbacks');
    assert.equal(
        described.detailRows.find((row) => row.label === 'Smart CAD Outcome').value.title,
        'Total solids: 3\nPrimitive candidates: 2\nSelected primitive: 1\nSelected tessellated fallback: 2\nTop fallback reasons: below_confidence_threshold x1, no_primitive_match_v1 x1',
    );
    assert.equal(described.detailRows[2].value.text, '0123456789ab...');
    assert.equal(described.detailRows[2].value.title, '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef');
    assert.equal(described.reimportContext.reimportTargetImportId, 'step_import_abc123');
    assert.equal(described.reimportContext.groupingName, 'fixture_import');
    assert.equal(described.reimportContext.placementMode, 'assembly');
    assert.equal(described.reimportContext.parentLVName, 'World');
    assert.deepEqual(described.reimportContext.offset, { x: '1', y: '2', z: '3' });
    assert.equal(described.reimportContext.smartImport, true);
    assert.equal(
        described.reimportContext.noticeText,
        'Reimport target: fixture.step (step_import_abc123). Supported annotations will be preserved where the backend can match them. Obsolete imported parts will be removed if the revised STEP drops them.',
    );
});

test('cad import provenance helpers surface deterministic reimport diff summaries', () => {
    const record = {
        import_id: 'step_import_abc123',
        source: {
            format: 'step',
            filename: 'fixture.step',
            sha256: '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
            size_bytes: 42,
        },
        options: {
            grouping_name: 'fixture_import',
            placement_mode: 'assembly',
            parent_lv_name: 'World',
            offset: { x: '1', y: '2', z: '3' },
            smart_import_enabled: true,
        },
        created_object_ids: {
            solid_ids: ['solid-1'],
            logical_volume_ids: ['lv-1'],
            assembly_ids: ['assembly-1'],
            placement_ids: ['placement-1', 'placement-2'],
            top_level_placement_ids: ['placement-1'],
        },
        created_group_names: {
            solid: 'fixture_import_solids',
            logical_volume: 'fixture_import_lvs',
            assembly: 'fixture_import_assemblies',
        },
        reimport_diff_summary: {
            summary: {
                total_before: 3,
                total_after: 3,
                unchanged_count: 0,
                added_count: 1,
                removed_count: 1,
                renamed_count: 1,
                changed_count: 1,
            },
            summary_text: 'Part changes: 1 added, 1 removed, 1 renamed, 1 changed.',
            added_parts: [
                { kind: 'logical_volume', name: 'fixture_part_d', signature: 'sig-added' },
            ],
            removed_parts: [
                { kind: 'logical_volume', name: 'fixture_part_c', signature: 'sig-removed' },
            ],
            renamed_parts: [
                {
                    kind: 'logical_volume',
                    before_name: 'fixture_part_b',
                    after_name: 'fixture_part_b_renamed',
                    signature: 'sig-renamed',
                },
            ],
            changed_parts: [
                {
                    kind: 'logical_volume',
                    name: 'fixture_part_a',
                    before_signature: 'sig-before',
                    after_signature: 'sig-after',
                },
            ],
            cleanup_policy: {
                replacement_mode: 'replace_in_place',
                obsolete_part_action: 'remove',
                removed_count: 1,
                summary_text: 'Supported STEP reimport replaces the target import in place and removes obsolete imported parts.',
            },
        },
    };

    const described = describeCadImportRecord(record);

    assert.equal(described.summary, 'STEP reimport from fixture.step · placement mode: assembly · smart CAD on');
    assert.equal(
        described.detailRows.find((row) => row.label === 'Reimport Diff').value,
        'Part changes: 1 added, 1 removed, 1 renamed, 1 changed.',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Reimport Cleanup').value.text,
        'Supported STEP reimport replaces the target import in place and removes obsolete imported parts.',
    );
    assert.equal(
        described.detailRows.find((row) => row.label === 'Reimport Cleanup').value.title,
        'Replacement mode: replace in place\nObsolete parts action: remove\nObsolete parts removed: 1',
    );
    assert.equal(described.detailRows.find((row) => row.label === 'Added Parts').value.text, 'fixture_part_d (sig-added...)');
    assert.equal(described.detailRows.find((row) => row.label === 'Removed Parts').value.text, 'fixture_part_c (sig-removed...)');
    assert.equal(described.detailRows.find((row) => row.label === 'Renamed Parts').value.text, 'fixture_part_b -> fixture_part_b_renamed');
    assert.equal(described.detailRows.find((row) => row.label === 'Changed Parts').value.text, 'fixture_part_a');
});

test('cad import provenance helpers stay stable when optional fields are missing', () => {
    const described = describeCadImportRecord({});
    const reimportContext = buildCadImportReimportContext({});

    assert.equal(described.title, 'unknown.step');
    assert.equal(
        described.summary,
        'STEP import from unknown.step · placement mode: assembly · smart CAD off',
    );
    assert.equal(described.createdObjectSummary, 'No imported object ids recorded.');
    assert.equal(described.createdGroupSummary, 'No created groups recorded.');
    assert.equal(reimportContext.reimportTargetImportId, 'unknown');
    assert.deepEqual(reimportContext.offset, { x: '0', y: '0', z: '0' });
    assert.equal(reimportContext.smartImport, false);
});

test('cad import selection helpers fall back to the first recorded placement for legacy records', () => {
    const selectionContext = buildCadImportSelectionContext({
        created_object_ids: {
            placement_ids: ['placement-a', 'placement-b'],
        },
    });

    assert.deepEqual(selectionContext.selectionIds, ['placement-a']);
    assert.equal(selectionContext.selectionSummary, '1 top-level placement');
});

test('cad import batch helpers normalize imported logical volume ids and summaries', () => {
    const batchContext = buildCadImportBatchContext({
        created_object_ids: {
            logical_volume_ids: ['lv-a', '', null, 'lv-b'],
        },
    });

    assert.deepEqual(batchContext.logicalVolumeIds, ['lv-a', 'lv-b']);
    assert.equal(batchContext.logicalVolumeCount, 2);
    assert.equal(batchContext.logicalVolumeSummary, '2 logical volumes');
    assert.equal(batchContext.hasLogicalVolumes, true);
});
