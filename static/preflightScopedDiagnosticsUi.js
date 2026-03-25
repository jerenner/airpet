const SCOPED_BUCKET_FILTERS = new Set(['all', 'scope_only', 'outside_scope_only', 'shared']);

const SCOPED_BUCKET_LABELS = {
    all: 'All scoped issues',
    scope_only: 'Scope-only issues',
    outside_scope_only: 'Outside-scope-only issues',
    shared: 'Shared issues',
};

const SCOPED_BUCKET_EMPTY_MESSAGES = {
    all: 'No issues detected in the selected scope.',
    scope_only: 'No scope-only issues detected in the selected scope.',
    outside_scope_only: 'No outside-scope-only issues detected in the selected scope.',
    shared: 'No shared issues detected in the selected scope.',
};

function normalizeIssueCodeList(rawCodes) {
    if (!Array.isArray(rawCodes)) return [];

    const seen = new Set();
    const normalized = [];
    rawCodes.forEach((code) => {
        const codeNorm = String(code || '').trim();
        if (!codeNorm) return;
        if (seen.has(codeNorm)) return;
        seen.add(codeNorm);
        normalized.push(codeNorm);
    });

    normalized.sort();
    return normalized;
}

function normalizeIssueCode(value) {
    return String(value || '').trim();
}

export function normalizeScopedIssueFamilyCorrelations(correlations) {
    if (!correlations || typeof correlations !== 'object') {
        return null;
    }

    const scopeOnlyIssueCodes = normalizeIssueCodeList(correlations.scope_only_issue_codes);
    const outsideScopeOnlyIssueCodes = normalizeIssueCodeList(correlations.outside_scope_only_issue_codes);
    const sharedIssueCodes = normalizeIssueCodeList(correlations.shared_issue_codes);

    return {
        scopeOnlyIssueCodes,
        outsideScopeOnlyIssueCodes,
        sharedIssueCodes,
    };
}

function formatIssueCodeExcerpt(codes, maxCodesPerBucket = 3) {
    if (!Array.isArray(codes) || codes.length === 0) {
        return 'none';
    }

    const maxCodes = Math.max(1, Number(maxCodesPerBucket) || 3);
    if (codes.length <= maxCodes) {
        return codes.join(', ');
    }

    const shown = codes.slice(0, maxCodes).join(', ');
    const hiddenCount = codes.length - maxCodes;
    return `${shown} (+${hiddenCount} more)`;
}

export function buildScopedIssueFamilyBucketSummary(correlations, options = {}) {
    const normalized = normalizeScopedIssueFamilyCorrelations(correlations);
    if (!normalized) return '';

    const maxCodesPerBucket = options.maxCodesPerBucket;

    return [
        `Issue-family buckets — scope-only: ${normalized.scopeOnlyIssueCodes.length} (${formatIssueCodeExcerpt(normalized.scopeOnlyIssueCodes, maxCodesPerBucket)})`,
        `outside-scope-only: ${normalized.outsideScopeOnlyIssueCodes.length} (${formatIssueCodeExcerpt(normalized.outsideScopeOnlyIssueCodes, maxCodesPerBucket)})`,
        `shared: ${normalized.sharedIssueCodes.length} (${formatIssueCodeExcerpt(normalized.sharedIssueCodes, maxCodesPerBucket)})`,
    ].join(' · ');
}

export function normalizeScopedBucketFilterSelection(selection) {
    const normalized = String(selection || '').trim().toLowerCase();
    return SCOPED_BUCKET_FILTERS.has(normalized) ? normalized : 'all';
}

export function getScopedIssueBucketDisplayLabel(selection) {
    const normalized = normalizeScopedBucketFilterSelection(selection);
    return SCOPED_BUCKET_LABELS[normalized] || SCOPED_BUCKET_LABELS.all;
}

export function filterScopedIssuesByBucket(issues, correlations, selection = 'all') {
    const requestedBucket = normalizeScopedBucketFilterSelection(selection);
    const normalizedIssues = Array.isArray(issues) ? issues : [];
    const normalizedCorrelations = normalizeScopedIssueFamilyCorrelations(correlations);

    if (!normalizedCorrelations) {
        return {
            requestedBucket,
            effectiveBucket: 'all',
            hasBucketMetadata: false,
            filteredIssues: normalizedIssues,
            emptyMessage: normalizedIssues.length === 0 ? SCOPED_BUCKET_EMPTY_MESSAGES.all : '',
        };
    }

    const bucketCodesBySelection = {
        scope_only: normalizedCorrelations.scopeOnlyIssueCodes,
        outside_scope_only: normalizedCorrelations.outsideScopeOnlyIssueCodes,
        shared: normalizedCorrelations.sharedIssueCodes,
    };

    const hasBucketMetadata = Object.values(bucketCodesBySelection).some((codes) => codes.length > 0);
    if (!hasBucketMetadata) {
        return {
            requestedBucket,
            effectiveBucket: 'all',
            hasBucketMetadata: false,
            filteredIssues: normalizedIssues,
            emptyMessage: normalizedIssues.length === 0 ? SCOPED_BUCKET_EMPTY_MESSAGES.all : '',
        };
    }

    const effectiveBucket = requestedBucket;
    if (effectiveBucket === 'all') {
        return {
            requestedBucket,
            effectiveBucket,
            hasBucketMetadata: true,
            filteredIssues: normalizedIssues,
            emptyMessage: normalizedIssues.length === 0 ? SCOPED_BUCKET_EMPTY_MESSAGES.all : '',
        };
    }

    const allowedCodes = new Set(bucketCodesBySelection[effectiveBucket] || []);
    const filteredIssues = normalizedIssues.filter((issue) => {
        const issueCode = normalizeIssueCode(issue?.code);
        if (!issueCode) return false;
        return allowedCodes.has(issueCode);
    });

    return {
        requestedBucket,
        effectiveBucket,
        hasBucketMetadata: true,
        filteredIssues,
        emptyMessage: filteredIssues.length === 0 ? SCOPED_BUCKET_EMPTY_MESSAGES[effectiveBucket] : '',
    };
}
