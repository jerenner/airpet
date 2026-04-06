import test from 'node:test';
import assert from 'node:assert/strict';

import {
    formatGlobalElectricFieldSummary,
    formatGlobalMagneticFieldSummary,
    formatLocalElectricFieldSummary,
    formatLocalMagneticFieldSummary,
    normalizeGlobalElectricFieldState,
    normalizeGlobalMagneticFieldState,
    normalizeLocalElectricFieldState,
    normalizeLocalMagneticFieldState,
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

test('global electric field ui helpers normalize malformed values deterministically', () => {
    assert.deepEqual(
        normalizeGlobalElectricFieldState({
            enabled: 'true',
            field_vector_volt_per_meter: {
                x: '2.5',
                y: 'bad-value',
                z: Infinity,
            },
        }),
        {
            enabled: true,
            field_vector_volt_per_meter: {
                x: 2.5,
                y: 0,
                z: 0,
            },
        },
    );
});

test('global electric field ui summary reflects saved enabled state and vector', () => {
    assert.equal(
        formatGlobalElectricFieldSummary({
            enabled: true,
            field_vector_volt_per_meter: {
                x: 0,
                y: 2.5,
                z: -1.25,
            },
        }),
        'Global electric field: enabled (0, 2.5, -1.25) V/m',
    );
});

test('local magnetic field ui helpers normalize malformed target volumes and vectors deterministically', () => {
    assert.deepEqual(
        normalizeLocalMagneticFieldState({
            enabled: 'true',
            target_volume_names: 'box_LV, detector_LV; box_LV',
            field_vector_tesla: {
                x: '1.25',
                y: 'bad-value',
                z: Infinity,
            },
        }),
        {
            enabled: true,
            target_volume_names: ['box_LV', 'detector_LV'],
            field_vector_tesla: {
                x: 1.25,
                y: 0,
                z: 0,
            },
        },
    );
});

test('local magnetic field ui summary reflects saved enabled state, targets, and vector', () => {
    assert.equal(
        formatLocalMagneticFieldSummary({
            enabled: true,
            target_volume_names: ['box_LV', 'detector_LV'],
            field_vector_tesla: {
                x: 0,
                y: 1.5,
                z: -0.25,
            },
        }),
        'Local magnetic field: enabled (targets box_LV, detector_LV) (0, 1.5, -0.25) T',
    );
});

test('local electric field ui helpers normalize malformed target volumes and vectors deterministically', () => {
    assert.deepEqual(
        normalizeLocalElectricFieldState({
            enabled: 'false',
            target_volume_names: 'box_LV, detector_LV; box_LV',
            field_vector_volt_per_meter: {
                x: '2.5',
                y: 'bad-value',
                z: Infinity,
            },
        }),
        {
            enabled: false,
            target_volume_names: ['box_LV', 'detector_LV'],
            field_vector_volt_per_meter: {
                x: 2.5,
                y: 0,
                z: 0,
            },
        },
    );
});

test('local electric field ui summary reflects saved enabled state, targets, and vector', () => {
    assert.equal(
        formatLocalElectricFieldSummary({
            enabled: true,
            target_volume_names: ['box_LV', 'detector_LV'],
            field_vector_volt_per_meter: {
                x: 0,
                y: 2.5,
                z: -1.25,
            },
        }),
        'Local electric field: enabled (targets box_LV, detector_LV) (0, 2.5, -1.25) V/m',
    );
});
