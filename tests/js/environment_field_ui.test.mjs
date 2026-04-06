import test from 'node:test';
import assert from 'node:assert/strict';

import {
    formatGlobalMagneticFieldSummary,
    normalizeGlobalMagneticFieldState,
} from '../../static/environmentFieldUi.js';

test('global magnetic field ui helpers normalize malformed values deterministically', () => {
    assert.deepEqual(
        normalizeGlobalMagneticFieldState({
            enabled: 'false',
            field_vector_tesla: {
                x: '1.25',
                y: 'bad-value',
                z: Infinity,
            },
        }),
        {
            enabled: false,
            field_vector_tesla: {
                x: 1.25,
                y: 0,
                z: 0,
            },
        },
    );
});

test('global magnetic field ui summary reflects saved enabled state and vector', () => {
    assert.equal(
        formatGlobalMagneticFieldSummary({
            enabled: true,
            field_vector_tesla: {
                x: 0,
                y: 1.5,
                z: -0.25,
            },
        }),
        'Global magnetic field: enabled (0, 1.5, -0.25) T',
    );
});
