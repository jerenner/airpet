import test from 'node:test';
import assert from 'node:assert/strict';

import {
    buildHistoryDeleteConfirmationMessage,
    normalizeHistoryDeleteSelection,
} from '../../static/historyDeleteFlow.js';

test('history delete selection normalization drops duplicates and selected-version child runs', () => {
    const normalized = normalizeHistoryDeleteSelection({
        versionIds: ['version-a', 'version-a', 'version-b'],
        runs: [
            { versionId: 'version-a', runId: 'run-1' },
            { versionId: 'version-b', runId: 'run-2' },
            { versionId: 'version-c', runId: 'run-3' },
            { versionId: 'version-c', runId: 'run-3' },
            { versionId: 'version-c', runId: '' },
            null,
        ],
    });

    assert.deepEqual(normalized, {
        versionIds: ['version-a', 'version-b'],
        runs: [
            { versionId: 'version-c', runId: 'run-3' },
        ],
        versionCount: 2,
        runCount: 1,
    });

    assert.equal(
        buildHistoryDeleteConfirmationMessage(normalized),
        'Delete 2 versions and 1 run? This cannot be undone.'
    );
});

test('history delete selection confirmation copy handles single-item selections', () => {
    assert.equal(
        buildHistoryDeleteConfirmationMessage({
            versionIds: ['version-a'],
            runs: [],
        }),
        'Delete 1 version? This cannot be undone.'
    );

    assert.equal(
        buildHistoryDeleteConfirmationMessage({
            versionIds: [],
            runs: [{ versionId: 'version-a', runId: 'run-1' }],
        }),
        'Delete 1 run? This cannot be undone.'
    );
});
