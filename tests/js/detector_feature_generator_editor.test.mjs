import test from 'node:test';
import assert from 'node:assert/strict';

import { coerceTiledSensorArrayPitchValue } from '../../static/detectorFeatureGeneratorEditor.js';

test('coerceTiledSensorArrayPitchValue lifts undersized pitch to the sensor size', () => {
    assert.equal(coerceTiledSensorArrayPitchValue(5, 6), 6);
    assert.equal(coerceTiledSensorArrayPitchValue('', 6), 6);
    assert.equal(coerceTiledSensorArrayPitchValue(0, 6), 6);
});

test('coerceTiledSensorArrayPitchValue preserves valid larger pitch values', () => {
    assert.equal(coerceTiledSensorArrayPitchValue(7.5, 6), 7.5);
    assert.equal(coerceTiledSensorArrayPitchValue(6, 6), 6);
});
