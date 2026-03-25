import test from 'node:test';
import assert from 'node:assert/strict';

import {
    normalizeScopedIssueFamilyCorrelations,
    buildScopedIssueFamilyBucketSummary,
} from '../../static/preflightScopedDiagnosticsUi.js';

test('scoped issue-family normalization is deterministic and removes empty/duplicate codes', () => {
    const normalized = normalizeScopedIssueFamilyCorrelations({
        scope_only_issue_codes: [' unknown_material_reference ', '', 'unknown_material_reference', 'invalid_replica_width'],
        outside_scope_only_issue_codes: ['possible_overlap_aabb', null, ' possible_overlap_aabb '],
        shared_issue_codes: ['placement_hierarchy_cycle', 'unknown_world_volume_reference'],
    });

    assert.deepEqual(normalized, {
        scopeOnlyIssueCodes: ['invalid_replica_width', 'unknown_material_reference'],
        outsideScopeOnlyIssueCodes: ['possible_overlap_aabb'],
        sharedIssueCodes: ['placement_hierarchy_cycle', 'unknown_world_volume_reference'],
    });
});

test('bucket summary text stays stable for scoped diagnostics rendering', () => {
    const summary = buildScopedIssueFamilyBucketSummary({
        scope_only_issue_codes: ['unknown_material_reference', 'invalid_replica_width'],
        outside_scope_only_issue_codes: ['possible_overlap_aabb'],
        shared_issue_codes: ['placement_hierarchy_cycle'],
    });

    assert.equal(
        summary,
        'Issue-family buckets — scope-only: 2 (invalid_replica_width, unknown_material_reference) · outside-scope-only: 1 (possible_overlap_aabb) · shared: 1 (placement_hierarchy_cycle)',
    );
});

test('bucket summary gracefully falls back when scoped payload is unavailable or oversized', () => {
    assert.equal(buildScopedIssueFamilyBucketSummary(null), '');

    const summary = buildScopedIssueFamilyBucketSummary(
        {
            scope_only_issue_codes: ['a', 'b', 'c', 'd'],
            outside_scope_only_issue_codes: [],
            shared_issue_codes: ['x', 'y', 'z'],
        },
        { maxCodesPerBucket: 2 },
    );

    assert.equal(
        summary,
        'Issue-family buckets — scope-only: 4 (a, b (+2 more)) · outside-scope-only: 0 (none) · shared: 3 (x, y (+1 more))',
    );
});
