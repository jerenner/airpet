import test from 'node:test';
import assert from 'node:assert/strict';

import {
    buildCadImportReimportContext,
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
        created_object_ids: {
            solid_ids: ['solid-1'],
            logical_volume_ids: ['lv-1'],
            assembly_ids: ['assembly-1'],
            placement_ids: ['placement-1', 'placement-2'],
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
        'STEP import from fixture.step · placement mode: assembly · smart CAD on',
    );
    assert.equal(described.createdObjectSummary, '1 solid, 1 logical volume, 1 assembly, 2 placements');
    assert.equal(
        described.createdGroupSummary,
        'fixture_import_solids, fixture_import_lvs, fixture_import_assemblies',
    );
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
            'Created Objects',
            'Created Groups',
        ],
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
        'Reimport target: fixture.step (step_import_abc123). Supported annotations will be preserved where the backend can match them.',
    );
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

