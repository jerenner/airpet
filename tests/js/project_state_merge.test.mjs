import test from 'node:test';
import assert from 'node:assert/strict';

import { mergeProjectStateWithExclusions } from '../../static/projectStateMerge.js';

test('mergeProjectStateWithExclusions preserves only explicitly excluded solids', () => {
    const merged = mergeProjectStateWithExclusions(
        {
            solids: {
                preserved_mesh: { name: 'preserved_mesh', type: 'tessellated' },
                deleted_generated_box: { name: 'deleted_generated_box', type: 'box' },
            },
            logical_volumes: {},
        },
        {
            solids: {
                world_solid: { name: 'world_solid', type: 'box' },
            },
            logical_volumes: {},
        },
        ['preserved_mesh'],
    );

    assert.deepEqual(Object.keys(merged.solids).sort(), ['preserved_mesh', 'world_solid']);
    assert.equal(merged.solids.preserved_mesh.type, 'tessellated');
    assert.equal(merged.solids.world_solid.type, 'box');
    assert.equal(Object.prototype.hasOwnProperty.call(merged.solids, 'deleted_generated_box'), false);
});

test('mergeProjectStateWithExclusions lets incoming solids override preserved ones', () => {
    const merged = mergeProjectStateWithExclusions(
        {
            solids: {
                shared_mesh: { name: 'shared_mesh', type: 'tessellated', old: true },
            },
        },
        {
            solids: {
                shared_mesh: { name: 'shared_mesh', type: 'tessellated', old: false },
            },
        },
        ['shared_mesh'],
    );

    assert.equal(merged.solids.shared_mesh.old, false);
});
