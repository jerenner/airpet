import test from 'node:test';
import assert from 'node:assert/strict';

import {
    normalizeScopedIssueFamilyCorrelations,
    buildScopedIssueFamilyBucketSummary,
    filterScopedIssuesByBucket,
    buildScopedIssueCodeChips,
    buildScopedIssueFilterContextCopyText,
    getScopedIssueBucketDisplayLabel,
    normalizeScopedBucketFilterSelection,
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

test('bucket filter selection normalization and labels are deterministic', () => {
    assert.equal(normalizeScopedBucketFilterSelection('scope_only'), 'scope_only');
    assert.equal(normalizeScopedBucketFilterSelection(' SHARED '), 'shared');
    assert.equal(normalizeScopedBucketFilterSelection('bad_value'), 'all');

    assert.equal(getScopedIssueBucketDisplayLabel('outside_scope_only'), 'Outside-scope-only issues');
    assert.equal(getScopedIssueBucketDisplayLabel('not_real'), 'All scoped issues');
});

test('bucket filtering keeps selected state when metadata exists and falls back when metadata is absent', () => {
    const issues = [
        { code: 'invalid_replica_width', message: 'Replica width is invalid.' },
        { code: 'possible_overlap_aabb', message: 'Potential overlap.' },
        { code: 'placement_hierarchy_cycle', message: 'Placement cycle found.' },
    ];
    const correlations = {
        scope_only_issue_codes: ['invalid_replica_width'],
        outside_scope_only_issue_codes: ['possible_overlap_aabb'],
        shared_issue_codes: ['placement_hierarchy_cycle'],
    };

    const sharedView = filterScopedIssuesByBucket(issues, correlations, 'shared');
    assert.equal(sharedView.hasBucketMetadata, true);
    assert.equal(sharedView.effectiveBucket, 'shared');
    assert.deepEqual(sharedView.filteredIssues.map((item) => item.code), ['placement_hierarchy_cycle']);

    const fallbackView = filterScopedIssuesByBucket(issues, null, 'shared');
    assert.equal(fallbackView.hasBucketMetadata, false);
    assert.equal(fallbackView.effectiveBucket, 'all');
    assert.deepEqual(fallbackView.filteredIssues.map((item) => item.code), [
        'invalid_replica_width',
        'possible_overlap_aabb',
        'placement_hierarchy_cycle',
    ]);
});

test('bucket filtering returns deterministic empty-result messaging', () => {
    const issues = [
        { code: 'invalid_replica_width', message: 'Replica width is invalid.' },
    ];
    const correlations = {
        scope_only_issue_codes: ['invalid_replica_width'],
        outside_scope_only_issue_codes: ['possible_overlap_aabb'],
        shared_issue_codes: ['placement_hierarchy_cycle'],
    };

    const outsideOnlyView = filterScopedIssuesByBucket(issues, correlations, 'outside_scope_only');
    assert.equal(outsideOnlyView.filteredIssues.length, 0);
    assert.equal(
        outsideOnlyView.emptyMessage,
        'No outside-scope-only issues detected in the selected scope.',
    );
});

test('issue-code chips are deterministic and bucket-aware when scoped metadata is available', () => {
    const issues = [
        { code: 'possible_overlap_aabb', message: 'Potential overlap A.' },
        { code: 'invalid_replica_width', message: 'Replica width is invalid.' },
        { code: 'possible_overlap_aabb', message: 'Potential overlap B.' },
        { code: 'placement_hierarchy_cycle', message: 'Placement cycle found.' },
    ];
    const correlations = {
        scope_only_issue_codes: ['invalid_replica_width'],
        outside_scope_only_issue_codes: ['possible_overlap_aabb'],
        shared_issue_codes: ['placement_hierarchy_cycle'],
    };

    const allChips = buildScopedIssueCodeChips(issues, correlations, 'all');
    assert.equal(allChips.hasBucketMetadata, true);
    assert.deepEqual(allChips.chips, [
        {
            code: 'invalid_replica_width',
            count: 1,
            bucket: 'scope_only',
            bucketLabel: 'Scope-only issues',
        },
        {
            code: 'possible_overlap_aabb',
            count: 2,
            bucket: 'outside_scope_only',
            bucketLabel: 'Outside-scope-only issues',
        },
        {
            code: 'placement_hierarchy_cycle',
            count: 1,
            bucket: 'shared',
            bucketLabel: 'Shared issues',
        },
    ]);

    const outsideOnlyChips = buildScopedIssueCodeChips(issues, correlations, 'outside_scope_only');
    assert.equal(outsideOnlyChips.effectiveBucket, 'outside_scope_only');
    assert.deepEqual(outsideOnlyChips.chips.map((chip) => chip.code), ['possible_overlap_aabb']);
    assert.equal(outsideOnlyChips.chips[0].count, 2);
});

test('issue-code chips fall back gracefully when scoped bucket metadata is absent', () => {
    const issues = [
        { code: 'unknown_world_volume_reference', message: 'Unknown world volume.' },
        { code: 'unknown_world_volume_reference', message: 'Unknown world volume again.' },
        { code: 'possible_overlap_aabb', message: 'Potential overlap.' },
    ];

    const fallbackView = buildScopedIssueCodeChips(issues, null, 'shared');
    assert.equal(fallbackView.hasBucketMetadata, false);
    assert.equal(fallbackView.effectiveBucket, 'all');
    assert.deepEqual(fallbackView.chips, [
        {
            code: 'possible_overlap_aabb',
            count: 1,
            bucket: null,
            bucketLabel: '',
        },
        {
            code: 'unknown_world_volume_reference',
            count: 2,
            bucket: null,
            bucketLabel: '',
        },
    ]);
});

test('copy-context helper emits deterministic scoped bucket/code context text', () => {
    const text = buildScopedIssueFilterContextCopyText({
        scopeLabel: 'LV "detector_module"',
        hasBucketMetadata: true,
        bucketSelection: ' SHARED ',
        issueCodeFocus: ' possible_overlap_aabb ',
        visibleIssueCount: 2,
        totalScopedIssueCount: 5,
    });

    assert.equal(
        text,
        'Scoped preflight filter context; scope=LV "detector_module"; bucket=shared (Shared issues); issue_code=possible_overlap_aabb; visible_issues=2; total_scoped_issues=5',
    );
});

test('copy-context helper falls back cleanly when bucket metadata/focus are unavailable', () => {
    const text = buildScopedIssueFilterContextCopyText({
        scopeLabel: 'Assembly "wheel"',
        hasBucketMetadata: false,
        bucketSelection: 'scope_only',
        issueCodeFocus: '',
    });

    assert.equal(
        text,
        'Scoped preflight filter context; scope=Assembly "wheel"; bucket=metadata_unavailable; issue_code=all',
    );
    assert.equal(buildScopedIssueFilterContextCopyText({}), '');
});
