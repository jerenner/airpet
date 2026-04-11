export const SCORING_OBJECT_TYPE = 'scoring';
export const SCORING_OBJECT_ID = 'scoring_state';

export const SUPPORTED_SCORING_TALLY_QUANTITIES = [
    'energy_deposit',
    'dose_deposit',
    'cell_flux',
    'passage_cell_flux',
    'track_length',
    'n_of_step',
    'n_of_track',
];

export const RUNTIME_READY_SCORING_QUANTITIES = ['energy_deposit', 'n_of_step'];

const DEFAULT_RUN_MANIFEST_DEFAULTS = {
    events: 1000,
    threads: 1,
    seed1: 0,
    seed2: 0,
    print_progress: 0,
    save_hits: true,
    save_hit_metadata: true,
    save_particles: false,
    production_cut: '1.0 mm',
    hit_energy_threshold: '1 eV',
};

function normalizeString(value, fallback = '') {
    const text = String(value ?? '').trim();
    return text || fallback;
}

function normalizeBoolean(value, fallback = true) {
    if (typeof value === 'boolean') {
        return value;
    }
    if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        if (['true', '1', 'yes', 'on'].includes(normalized)) {
            return true;
        }
        if (['false', '0', 'no', 'off'].includes(normalized)) {
            return false;
        }
    }
    return fallback;
}

function normalizeFiniteNumber(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizePositiveNumber(value, fallback = 10) {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function normalizePositiveInt(value, fallback = 10) {
    const parsed = Number.parseInt(String(value ?? ''), 10);
    return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function normalizeNonNegativeInt(value, fallback = 0) {
    const parsed = Number.parseInt(String(value ?? ''), 10);
    return Number.isInteger(parsed) && parsed >= 0 ? parsed : fallback;
}

function formatNumber(value) {
    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
        return '0';
    }
    return String(Number(numericValue.toFixed(6)));
}

function pluralize(count, singular, plural = `${singular}s`) {
    return `${count} ${count === 1 ? singular : plural}`;
}

function normalizeScoringMesh(rawMesh, index = 0) {
    const mesh = rawMesh && typeof rawMesh === 'object' ? rawMesh : {};
    return {
        mesh_id: normalizeString(mesh.mesh_id, `scoring_mesh_ui_${index + 1}`),
        name: normalizeString(mesh.name, `box_mesh_${index + 1}`),
        schema_version: 1,
        enabled: normalizeBoolean(mesh.enabled, true),
        mesh_type: 'box',
        reference_frame: 'world',
        geometry: {
            center_mm: {
                x: normalizeFiniteNumber(mesh?.geometry?.center_mm?.x, 0),
                y: normalizeFiniteNumber(mesh?.geometry?.center_mm?.y, 0),
                z: normalizeFiniteNumber(mesh?.geometry?.center_mm?.z, 0),
            },
            size_mm: {
                x: normalizePositiveNumber(mesh?.geometry?.size_mm?.x, 10),
                y: normalizePositiveNumber(mesh?.geometry?.size_mm?.y, 10),
                z: normalizePositiveNumber(mesh?.geometry?.size_mm?.z, 10),
            },
        },
        bins: {
            x: normalizePositiveInt(mesh?.bins?.x, 10),
            y: normalizePositiveInt(mesh?.bins?.y, 10),
            z: normalizePositiveInt(mesh?.bins?.z, 10),
        },
    };
}

function normalizeTallyQuantity(value) {
    const quantity = normalizeString(value, 'energy_deposit');
    return SUPPORTED_SCORING_TALLY_QUANTITIES.includes(quantity) ? quantity : 'energy_deposit';
}

function normalizeScoringTally(rawTally, index = 0) {
    const tally = rawTally && typeof rawTally === 'object' ? rawTally : {};
    const quantity = normalizeTallyQuantity(tally.quantity);
    const meshRef = tally.mesh_ref && typeof tally.mesh_ref === 'object' ? tally.mesh_ref : {};
    return {
        tally_id: normalizeString(tally.tally_id, `scoring_tally_ui_${index + 1}`),
        name: normalizeString(tally.name, `${quantity}_tally_${index + 1}`),
        schema_version: 1,
        enabled: normalizeBoolean(tally.enabled, true),
        mesh_ref: {
            mesh_id: normalizeString(meshRef.mesh_id, ''),
            name: normalizeString(meshRef.name, ''),
        },
        quantity,
    };
}

export function normalizeScoringState(rawState) {
    const state = rawState && typeof rawState === 'object' ? rawState : {};
    const scoringMeshes = Array.isArray(state.scoring_meshes)
        ? state.scoring_meshes.map((mesh, index) => normalizeScoringMesh(mesh, index))
        : [];
    const tallyRequests = Array.isArray(state.tally_requests)
        ? state.tally_requests.map((tally, index) => normalizeScoringTally(tally, index))
        : [];
    const runManifestDefaults = state.run_manifest_defaults && typeof state.run_manifest_defaults === 'object'
        ? { ...DEFAULT_RUN_MANIFEST_DEFAULTS, ...state.run_manifest_defaults }
        : { ...DEFAULT_RUN_MANIFEST_DEFAULTS };

    return {
        schema_version: 1,
        scoring_meshes: scoringMeshes,
        tally_requests: tallyRequests,
        run_manifest_defaults: runManifestDefaults,
    };
}

function findNextAvailableToken(existingValues, prefix) {
    let index = 1;
    let candidate = `${prefix}${index}`;
    while (existingValues.has(candidate)) {
        index += 1;
        candidate = `${prefix}${index}`;
    }
    return candidate;
}

function buildDefaultScoringTally(scoringState, mesh, quantity = 'energy_deposit') {
    const normalizedScoring = normalizeScoringState(scoringState);
    const usedTallyIds = new Set(normalizedScoring.tally_requests.map((tally) => tally.tally_id));
    const tallyId = findNextAvailableToken(usedTallyIds, 'scoring_tally_ui_');
    return {
        tally_id: tallyId,
        name: `${mesh.name}_${quantity}`,
        schema_version: 1,
        enabled: true,
        mesh_ref: {
            mesh_id: mesh.mesh_id,
            name: mesh.name,
        },
        quantity,
    };
}

export function buildDefaultScoringMesh(rawScoringState) {
    const scoringState = normalizeScoringState(rawScoringState);
    const usedMeshIds = new Set(scoringState.scoring_meshes.map((mesh) => mesh.mesh_id));
    const usedMeshNames = new Set(scoringState.scoring_meshes.map((mesh) => mesh.name));
    const meshId = findNextAvailableToken(usedMeshIds, 'scoring_mesh_ui_');
    const meshName = findNextAvailableToken(usedMeshNames, 'box_mesh_');

    return {
        mesh_id: meshId,
        name: meshName,
        schema_version: 1,
        enabled: true,
        mesh_type: 'box',
        reference_frame: 'world',
        geometry: {
            center_mm: { x: 0, y: 0, z: 0 },
            size_mm: { x: 10, y: 10, z: 10 },
        },
        bins: { x: 10, y: 10, z: 10 },
    };
}

export function findTalliesForMesh(rawScoringState, meshId) {
    const scoringState = normalizeScoringState(rawScoringState);
    const targetMeshId = normalizeString(meshId, '');
    if (!targetMeshId) {
        return [];
    }
    return scoringState.tally_requests.filter((tally) => tally.mesh_ref.mesh_id === targetMeshId);
}

export function isMeshTallyEnabled(rawScoringState, meshId, quantity) {
    return findTalliesForMesh(rawScoringState, meshId).some(
        (tally) => tally.enabled && tally.quantity === quantity
    );
}

export function buildScoringStateWithAddedMesh(rawScoringState) {
    const scoringState = normalizeScoringState(rawScoringState);
    const mesh = buildDefaultScoringMesh(scoringState);
    return {
        ...scoringState,
        scoring_meshes: [...scoringState.scoring_meshes, mesh],
        tally_requests: [...scoringState.tally_requests, buildDefaultScoringTally(scoringState, mesh)],
    };
}

export function buildScoringStateWithRemovedMesh(rawScoringState, meshId) {
    const scoringState = normalizeScoringState(rawScoringState);
    const normalizedMeshId = normalizeString(meshId, '');
    return {
        ...scoringState,
        scoring_meshes: scoringState.scoring_meshes.filter((mesh) => mesh.mesh_id !== normalizedMeshId),
        tally_requests: scoringState.tally_requests.filter((tally) => tally.mesh_ref.mesh_id !== normalizedMeshId),
    };
}

export function replaceScoringMesh(rawScoringState, meshId, nextMesh) {
    const scoringState = normalizeScoringState(rawScoringState);
    const normalizedMeshId = normalizeString(meshId, '');
    const meshIndex = scoringState.scoring_meshes.findIndex((mesh) => mesh.mesh_id === normalizedMeshId);
    if (meshIndex === -1) {
        return scoringState;
    }

    const normalizedMesh = normalizeScoringMesh(nextMesh, meshIndex);
    const nextMeshes = scoringState.scoring_meshes.map((mesh) => (
        mesh.mesh_id === normalizedMeshId ? normalizedMesh : mesh
    ));
    const nextTallies = scoringState.tally_requests.map((tally) => {
        if (tally.mesh_ref.mesh_id !== normalizedMeshId) {
            return tally;
        }
        return {
            ...tally,
            mesh_ref: {
                mesh_id: normalizedMesh.mesh_id,
                name: normalizedMesh.name,
            },
        };
    });

    return {
        ...scoringState,
        scoring_meshes: nextMeshes,
        tally_requests: nextTallies,
    };
}

export function setMeshTallyEnabled(rawScoringState, mesh, quantity, enabled) {
    const scoringState = normalizeScoringState(rawScoringState);
    const normalizedMesh = normalizeScoringMesh(
        mesh,
        scoringState.scoring_meshes.findIndex((candidate) => candidate.mesh_id === mesh?.mesh_id),
    );
    const normalizedQuantity = normalizeTallyQuantity(quantity);
    const matchingTallies = [];
    const remainingTallies = [];

    scoringState.tally_requests.forEach((tally) => {
        if (tally.mesh_ref.mesh_id === normalizedMesh.mesh_id && tally.quantity === normalizedQuantity) {
            matchingTallies.push(tally);
            return;
        }
        remainingTallies.push(tally);
    });

    if (!enabled) {
        return {
            ...scoringState,
            tally_requests: remainingTallies,
        };
    }

    const nextTallies = [...remainingTallies];
    if (matchingTallies.length > 0) {
        const nextTally = matchingTallies[0];
        nextTallies.push({
            ...nextTally,
            enabled: true,
            mesh_ref: {
                mesh_id: normalizedMesh.mesh_id,
                name: normalizedMesh.name,
            },
        });
    } else {
        nextTallies.push(buildDefaultScoringTally(scoringState, normalizedMesh, normalizedQuantity));
    }

    return {
        ...scoringState,
        tally_requests: nextTallies,
    };
}

export function formatScoringQuantityLabel(quantity) {
    return normalizeString(quantity, 'energy_deposit').replace(/_/g, ' ');
}

export function describeScoringMesh(rawMesh, rawScoringState) {
    const mesh = normalizeScoringMesh(rawMesh);
    const meshTallies = findTalliesForMesh(rawScoringState, mesh.mesh_id);
    const enabledTallies = meshTallies.filter((tally) => tally.enabled);
    return {
        title: mesh.name,
        statusBadge: mesh.enabled ? 'enabled' : 'disabled',
        summary: `World box mesh · center ${formatNumber(mesh.geometry.center_mm.x)} x ${formatNumber(mesh.geometry.center_mm.y)} x ${formatNumber(mesh.geometry.center_mm.z)} mm · size ${formatNumber(mesh.geometry.size_mm.x)} x ${formatNumber(mesh.geometry.size_mm.y)} x ${formatNumber(mesh.geometry.size_mm.z)} mm · bins ${mesh.bins.x} x ${mesh.bins.y} x ${mesh.bins.z} · ${pluralize(enabledTallies.length, 'enabled tally')}`,
    };
}

export function describeScoringPanelState(projectState) {
    const scoringState = normalizeScoringState(projectState?.scoring);
    const enabledMeshes = scoringState.scoring_meshes.filter((mesh) => mesh.enabled);
    const enabledTallies = scoringState.tally_requests.filter((tally) => tally.enabled);

    return {
        intro: `${pluralize(enabledMeshes.length, 'enabled scoring mesh')} across ${pluralize(enabledTallies.length, 'enabled tally request')}.`,
        hint: 'energy_deposit and n_of_step tallies currently emit runtime scoring artifacts. Other saved tallies remain editable here for upcoming runtime slices.',
        empty: 'No scoring meshes saved yet. Add one world-space box mesh to start a scoring study.',
        defaultExpandedIndex: scoringState.scoring_meshes.length === 1 ? 0 : -1,
    };
}

function formatScoringResultValue(value, unit = '') {
    const normalizedUnit = normalizeString(unit, '');
    return `${formatNumber(value)}${normalizedUnit ? ` ${normalizedUnit}` : ''}`;
}

function normalizeQuantitySummary(rawSummary) {
    const summary = rawSummary && typeof rawSummary === 'object' ? rawSummary : {};
    const quantity = normalizeString(summary.quantity, '');
    if (!quantity) {
        return null;
    }

    const unit = normalizeString(summary.unit, '');
    const totalValue = Number(summary.total_value);
    const generatedArtifactCount = normalizeNonNegativeInt(summary.generated_artifact_count, 0);

    return {
        quantity,
        label: formatScoringQuantityLabel(quantity),
        unit,
        generatedArtifactCount,
        totalValue: Number.isFinite(totalValue) ? Number(totalValue.toFixed(6)) : 0,
        totalValueText: formatScoringResultValue(totalValue, unit),
    };
}

function normalizeComparisonKeys(rawKeys) {
    const keys = rawKeys && typeof rawKeys === 'object' ? rawKeys : {};
    return {
        geometrySha256: normalizeString(keys.geometrySha256 ?? keys.geometry_sha256, ''),
        environmentSignature: normalizeString(keys.environmentSignature ?? keys.environment_signature, ''),
        scoringSignature: normalizeString(keys.scoringSignature ?? keys.scoring_signature, ''),
        runManifestSignature: normalizeString(keys.runManifestSignature ?? keys.run_manifest_signature, ''),
        executionSignature: normalizeString(keys.executionSignature ?? keys.execution_signature, ''),
    };
}

function buildScoringResultRunLabel(summary) {
    const jobId = normalizeString(summary?.jobId, '');
    const versionId = normalizeString(summary?.versionId, '');
    const shortJobId = jobId ? `${jobId.slice(0, 8)}...` : 'unknown';
    return versionId ? `${versionId} · ${shortJobId}` : `Run ${shortJobId}`;
}

export function buildScoringResultSummary(rawMetadata, context = {}) {
    const metadata = rawMetadata && typeof rawMetadata === 'object' ? rawMetadata : {};
    const runManifestSummary = metadata.run_manifest_summary && typeof metadata.run_manifest_summary === 'object'
        ? metadata.run_manifest_summary
        : {};
    const artifactBundle = runManifestSummary.artifact_bundle && typeof runManifestSummary.artifact_bundle === 'object'
        ? runManifestSummary.artifact_bundle
        : {};
    const scoringArtifacts = metadata.scoring_artifacts && typeof metadata.scoring_artifacts === 'object'
        ? metadata.scoring_artifacts
        : {};
    const scoringArtifactSummary = scoringArtifacts.summary && typeof scoringArtifacts.summary === 'object'
        ? scoringArtifacts.summary
        : {};
    const scoringSummary = metadata.scoring_summary && typeof metadata.scoring_summary === 'object'
        ? metadata.scoring_summary
        : (
            runManifestSummary.scoring && typeof runManifestSummary.scoring === 'object'
                && runManifestSummary.scoring.summary && typeof runManifestSummary.scoring.summary === 'object'
                ? runManifestSummary.scoring.summary
                : {}
        );
    const scoringRuntime = runManifestSummary.scoring && typeof runManifestSummary.scoring === 'object'
        && runManifestSummary.scoring.runtime && typeof runManifestSummary.scoring.runtime === 'object'
        ? runManifestSummary.scoring.runtime
        : {};
    const resolvedRunManifest = runManifestSummary.resolved_run_manifest
        && typeof runManifestSummary.resolved_run_manifest === 'object'
        ? runManifestSummary.resolved_run_manifest
        : {};
    const executionSettings = runManifestSummary.execution_settings
        && typeof runManifestSummary.execution_settings === 'object'
        ? runManifestSummary.execution_settings
        : {};
    const quantitySource = Array.isArray(scoringArtifactSummary.quantity_summaries)
        && scoringArtifactSummary.quantity_summaries.length > 0
        ? scoringArtifactSummary.quantity_summaries
        : (
            Array.isArray(artifactBundle.quantity_summaries)
                ? artifactBundle.quantity_summaries
                : []
        );
    const quantitySummaries = quantitySource
        .map((entry) => normalizeQuantitySummary(entry))
        .filter(Boolean);
    const versionId = normalizeString(context.versionId ?? runManifestSummary.version_id, '');
    const jobId = normalizeString(context.jobId ?? metadata.job_id ?? runManifestSummary.job_id, '');
    const generatedArtifactCount = normalizeNonNegativeInt(
        scoringArtifacts.generated_artifact_count ?? artifactBundle.generated_artifact_count,
        quantitySummaries.reduce((count, entry) => count + entry.generatedArtifactCount, 0),
    );
    const artifactRequestCount = normalizeNonNegativeInt(
        scoringSummary.artifact_request_count ?? scoringRuntime.artifact_request_count,
        0,
    );
    const summaryText = quantitySummaries.length > 0
        ? quantitySummaries.map((entry) => `${entry.label} ${entry.totalValueText}`).join(' · ')
        : (
            generatedArtifactCount > 0
                ? `${pluralize(generatedArtifactCount, 'scoring artifact')} recorded for this run.`
                : (
                    artifactRequestCount > 0
                        ? `Requested ${pluralize(artifactRequestCount, 'scoring artifact')}, but no scoring bundle was recorded.`
                        : 'No scoring artifacts recorded for this run.'
                )
        );

    return {
        runKey: `${versionId}:${jobId}`,
        versionId,
        jobId,
        runLabel: buildScoringResultRunLabel({ versionId, jobId }),
        timestamp: normalizeString(metadata.timestamp ?? runManifestSummary.timestamp, ''),
        totalEvents: normalizeNonNegativeInt(metadata.total_events ?? resolvedRunManifest.events, 0),
        threads: normalizeNonNegativeInt(resolvedRunManifest.threads, 0),
        physicsList: normalizeString(executionSettings.physics_list ?? metadata?.sim_options?.physics_list, ''),
        opticalPhysics: Boolean(
            executionSettings.optical_physics
            ?? metadata?.sim_options?.optical_physics
        ),
        enabledMeshCount: normalizeNonNegativeInt(scoringSummary.enabled_mesh_count, 0),
        enabledTallyCount: normalizeNonNegativeInt(scoringSummary.enabled_tally_count, 0),
        artifactRequestCount,
        generatedArtifactCount,
        skippedTallyCount: normalizeNonNegativeInt(
            scoringArtifacts.skipped_tally_count ?? artifactBundle.skipped_tally_count,
            0,
        ),
        bundlePath: normalizeString(scoringArtifacts.artifact_bundle_path ?? artifactBundle.path, ''),
        bundleExists: Boolean(
            artifactBundle.exists
            ?? normalizeString(scoringArtifacts.artifact_bundle_path, '')
        ),
        sourceOutputExists: Boolean(artifactBundle?.source_output?.exists),
        quantitySummaries,
        comparisonKeys: normalizeComparisonKeys(runManifestSummary.comparison_keys),
        hasScoringOutputs: quantitySummaries.length > 0 || generatedArtifactCount > 0,
        summaryText,
    };
}

export function compareScoringResultSummaries(rawBaseline, rawCandidate) {
    const baseline = rawBaseline && typeof rawBaseline === 'object' ? rawBaseline : null;
    const candidate = rawCandidate && typeof rawCandidate === 'object' ? rawCandidate : null;
    if (!baseline || !candidate || baseline.runKey === candidate.runKey) {
        return null;
    }

    const changedFlags = {
        geometry: baseline.comparisonKeys?.geometrySha256 !== candidate.comparisonKeys?.geometrySha256,
        environment: baseline.comparisonKeys?.environmentSignature !== candidate.comparisonKeys?.environmentSignature,
        scoringSetup: baseline.comparisonKeys?.scoringSignature !== candidate.comparisonKeys?.scoringSignature,
        runManifest: baseline.comparisonKeys?.runManifestSignature !== candidate.comparisonKeys?.runManifestSignature,
        execution: baseline.comparisonKeys?.executionSignature !== candidate.comparisonKeys?.executionSignature,
    };
    const changedSections = [
        changedFlags.geometry ? 'geometry' : '',
        changedFlags.environment ? 'environment' : '',
        changedFlags.scoringSetup ? 'scoring setup' : '',
        changedFlags.runManifest ? 'run manifest' : '',
        changedFlags.execution ? 'execution settings' : '',
    ].filter(Boolean);

    const baselineQuantities = new Map(
        Array.isArray(baseline.quantitySummaries)
            ? baseline.quantitySummaries.map((entry) => [entry.quantity, entry])
            : [],
    );
    const candidateQuantities = new Map(
        Array.isArray(candidate.quantitySummaries)
            ? candidate.quantitySummaries.map((entry) => [entry.quantity, entry])
            : [],
    );
    const quantities = [...new Set([
        ...baselineQuantities.keys(),
        ...candidateQuantities.keys(),
    ])].sort();
    const quantityDeltas = quantities.map((quantity) => {
        const baselineQuantity = baselineQuantities.get(quantity) || null;
        const candidateQuantity = candidateQuantities.get(quantity) || null;
        const unit = normalizeString(candidateQuantity?.unit ?? baselineQuantity?.unit, '');
        const baselineTotalValue = Number(baselineQuantity?.totalValue ?? 0);
        const candidateTotalValue = Number(candidateQuantity?.totalValue ?? 0);
        const deltaValue = Number((candidateTotalValue - baselineTotalValue).toFixed(6));
        const direction = deltaValue > 0 ? 'up' : (deltaValue < 0 ? 'down' : 'unchanged');
        const prefix = deltaValue > 0 ? '+' : '';
        return {
            quantity,
            label: formatScoringQuantityLabel(quantity),
            unit,
            baselineTotalValue,
            candidateTotalValue,
            deltaValue,
            deltaText: `${prefix}${formatScoringResultValue(deltaValue, unit)}`,
            baselineArtifactCount: normalizeNonNegativeInt(baselineQuantity?.generatedArtifactCount, 0),
            candidateArtifactCount: normalizeNonNegativeInt(candidateQuantity?.generatedArtifactCount, 0),
            direction,
        };
    });
    const changedQuantityDeltas = quantityDeltas.filter((entry) => (
        entry.deltaValue !== 0
        || entry.baselineArtifactCount !== entry.candidateArtifactCount
    ));
    const summaryParts = [];
    if (changedQuantityDeltas.length > 0) {
        summaryParts.push(
            changedQuantityDeltas
                .map((entry) => `${entry.label} ${entry.deltaText}`)
                .join(' · '),
        );
    }
    if (changedSections.length > 0) {
        summaryParts.push(`Changed ${changedSections.join(', ')}`);
    }

    return {
        baselineRunKey: baseline.runKey,
        baselineRunLabel: baseline.runLabel,
        baselineVersionId: baseline.versionId,
        baselineJobId: baseline.jobId,
        candidateRunKey: candidate.runKey,
        candidateRunLabel: candidate.runLabel,
        candidateVersionId: candidate.versionId,
        candidateJobId: candidate.jobId,
        changedFlags,
        changedSections,
        quantityDeltas,
        summaryText: summaryParts.length > 0
            ? summaryParts.join(' | ')
            : 'No scoring-result or manifest changes versus the previous loaded run.',
    };
}

export function describeScoringResultSummary(rawSummary) {
    const summary = rawSummary && typeof rawSummary === 'object' ? rawSummary : null;
    if (!summary) {
        return null;
    }

    const metaBits = [];
    if (summary.totalEvents > 0) {
        metaBits.push(`${summary.totalEvents} events`);
    }
    if (summary.threads > 0) {
        metaBits.push(pluralize(summary.threads, 'thread'));
    }
    if (summary.physicsList) {
        metaBits.push(summary.physicsList);
    }
    if (summary.opticalPhysics) {
        metaBits.push('optical on');
    }

    const detailLines = [
        `${pluralize(summary.enabledMeshCount, 'enabled mesh')} · ${pluralize(summary.enabledTallyCount, 'enabled tally request')}`,
        summary.bundleExists
            ? `Bundle: ${summary.bundlePath || 'scoring_artifacts.json'}`
            : 'Bundle: not recorded',
    ];

    return {
        title: summary.runLabel,
        statusBadge: summary.hasScoringOutputs ? 'artifacts ready' : 'no artifacts',
        summary: summary.summaryText,
        meta: metaBits.join(' · '),
        detailLines,
        quantityLines: (summary.quantitySummaries || []).map((entry) => (
            `${entry.label}: ${entry.totalValueText} across ${pluralize(entry.generatedArtifactCount, 'artifact')}`
        )),
    };
}

export function describeScoringResultComparison(rawComparison) {
    const comparison = rawComparison && typeof rawComparison === 'object' ? rawComparison : null;
    if (!comparison) {
        return null;
    }

    const deltaLines = (comparison.quantityDeltas || [])
        .filter((entry) => entry.deltaValue !== 0 || entry.baselineArtifactCount !== entry.candidateArtifactCount)
        .map((entry) => `${entry.label}: ${entry.deltaText}`);

    return {
        title: 'Compared To Previous Loaded Run',
        statusBadge: deltaLines.length > 0 || comparison.changedSections.length > 0 ? 'delta detected' : 'matched',
        summary: comparison.summaryText,
        meta: `Baseline ${comparison.baselineRunLabel || 'previous run'}`,
        detailLines: comparison.changedSections.length > 0
            ? [`Changed: ${comparison.changedSections.join(', ')}`]
            : ['Changed: none'],
        deltaLines,
    };
}
