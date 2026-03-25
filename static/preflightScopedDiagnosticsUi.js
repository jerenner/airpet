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
