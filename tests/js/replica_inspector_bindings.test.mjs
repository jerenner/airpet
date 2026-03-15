import test from 'node:test';
import assert from 'node:assert/strict';

import {
    getReplicaInspectorEditableFieldSpecs,
    buildReplicaInspectorPropertyUpdateArgs,
    toReplicaExpressionString,
} from '../../static/replicaInspectorBindings.js';

test('replica inspector editable field specs remain stable and expression-backed', () => {
    const specs = getReplicaInspectorEditableFieldSpecs({
        number: 'numSlices',
        width: '(detector_pitch/2)',
        offset: 'start_offset + 0.5*mm',
    });

    assert.deepEqual(specs, [
        {
            key: 'number',
            label: 'Number:',
            propertyPath: 'content.number',
            value: 'numSlices',
        },
        {
            key: 'width',
            label: 'Width:',
            propertyPath: 'content.width',
            value: '(detector_pitch/2)',
        },
        {
            key: 'offset',
            label: 'Offset:',
            propertyPath: 'content.offset',
            value: 'start_offset + 0.5*mm',
        },
    ]);
});

test('replica field specs fall back to deterministic defaults when expressions are missing', () => {
    const specs = getReplicaInspectorEditableFieldSpecs({ number: null, width: undefined });

    assert.equal(specs[0].value, '1');
    assert.equal(specs[1].value, '0');
    assert.equal(specs[2].value, '0');
});

test('replica inspector update args lock logical-volume update payload shape', () => {
    const update = buildReplicaInspectorPropertyUpdateArgs(
        '  DetectorReplicaLV  ',
        'content.width',
        12.5
    );

    assert.deepEqual(update, {
        objectType: 'logical_volume',
        objectId: 'DetectorReplicaLV',
        propertyPath: 'content.width',
        newValue: '12.5',
    });
});

test('replica inspector update args reject unsupported nested property paths', () => {
    assert.throws(
        () => buildReplicaInspectorPropertyUpdateArgs('DetectorReplicaLV', 'content.direction.x', '1'),
        /Unsupported replica inspector property path/
    );
});

test('replica expression string coercion preserves explicit empty string and fallback behavior', () => {
    assert.equal(toReplicaExpressionString('', 'fallback'), '');
    assert.equal(toReplicaExpressionString(undefined, 'fallback'), 'fallback');
    assert.equal(toReplicaExpressionString(0, 'fallback'), '0');
});
