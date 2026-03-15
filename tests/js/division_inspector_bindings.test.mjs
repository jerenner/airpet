import test from 'node:test';
import assert from 'node:assert/strict';

import {
    getDivisionInspectorEditableFieldSpecs,
    buildDivisionInspectorPropertyUpdateArgs,
    toDivisionExpressionString,
} from '../../static/divisionInspectorBindings.js';

test('division inspector editable field specs remain stable and expression-backed', () => {
    const specs = getDivisionInspectorEditableFieldSpecs({
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

test('division field specs fall back to deterministic defaults when expressions are missing', () => {
    const specs = getDivisionInspectorEditableFieldSpecs({ number: null, width: undefined });

    assert.equal(specs[0].value, '1');
    assert.equal(specs[1].value, '0');
    assert.equal(specs[2].value, '0');
});

test('division inspector update args lock logical-volume update payload shape', () => {
    const update = buildDivisionInspectorPropertyUpdateArgs(
        '  DetectorDivisionLV  ',
        'content.width',
        12.5
    );

    assert.deepEqual(update, {
        objectType: 'logical_volume',
        objectId: 'DetectorDivisionLV',
        propertyPath: 'content.width',
        newValue: '12.5',
    });
});

test('division inspector update args reject unsupported nested property paths', () => {
    assert.throws(
        () => buildDivisionInspectorPropertyUpdateArgs('DetectorDivisionLV', 'content.axis', 'kzaxis'),
        /Unsupported division inspector property path/
    );
});

test('division expression string coercion preserves explicit empty string and fallback behavior', () => {
    assert.equal(toDivisionExpressionString('', 'fallback'), '');
    assert.equal(toDivisionExpressionString(undefined, 'fallback'), 'fallback');
    assert.equal(toDivisionExpressionString(0, 'fallback'), '0');
});
