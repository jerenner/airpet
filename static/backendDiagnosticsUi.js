// static/backendDiagnosticsUi.js

export function getBackendLabel(backendId) {
    if (backendId === 'llama_cpp') return 'llama.cpp';
    if (backendId === 'lm_studio') return 'LM Studio';
    return backendId || 'AI backend';
}

const BACKEND_FAILURE_STAGE_LABELS = Object.freeze({
    selector_validation: 'selector validation',
    selector_requirements: 'selector requirements mismatch',
    backend_runtime: 'backend runtime failure',
});

const REMEDIATION_ACTION_LABELS = Object.freeze({
    use_backend_model_selector_format: "Use '<backend>::<model_name>' local selector format.",
    select_nonempty_local_model_name: 'Select a local model with a non-empty model name.',
    disable_tool_requirement_for_local_backends: 'Set require_tools=false for local text-first backends.',
    allow_backend_fallback: 'Enable allow_fallback=true to permit Gemini/Ollama fallback.',
    switch_to_cloud_backend_for_tool_calls: 'Use a Gemini/Ollama model when tool calling is required.',
    increase_backend_timeout: 'Increase backend timeout_seconds or reduce prompt size.',
    retry_after_backend_idle: 'Retry after the local model server is idle.',
    verify_local_host_resources: 'Verify local CPU/RAM resources are not saturated.',
    start_local_backend_service: 'Start the local backend service.',
    verify_backend_base_url_and_port: 'Verify backend base_url and port configuration.',
    verify_models_endpoint_reachable: "Confirm '<base_url>/v1/models' is reachable.",
    fix_backend_configuration: 'Fix local backend runtime_config fields.',
    set_valid_local_model_name: "Set a valid local model name exposed by '/v1/models'.",
    validate_openai_compatible_models_payload: "Validate '/v1/models' returns an OpenAI-compatible payload.",
    retry_request: 'Retry once to rule out a transient backend failure.',
    inspect_backend_logs: 'Inspect local backend logs for runtime errors.',
    refresh_backend_diagnostics: 'Refresh backend diagnostics and retry.',
});

export function getBackendFailureStageLabel(stage) {
    return BACKEND_FAILURE_STAGE_LABELS[stage] || 'backend diagnostics error';
}

export function getBackendRemediationActions(remediation) {
    if (!remediation || typeof remediation !== 'object') return [];

    if (Array.isArray(remediation.actions) && remediation.actions.length > 0) {
        return remediation.actions
            .map(action => String(action || '').trim())
            .filter(Boolean);
    }

    if (Array.isArray(remediation.action_codes) && remediation.action_codes.length > 0) {
        return remediation.action_codes
            .map(code => REMEDIATION_ACTION_LABELS[String(code)] || null)
            .filter(Boolean);
    }

    return [];
}

export function formatBackendDiagnosticsError(err) {
    const diagnostics = err?.data?.backend_diagnostics;
    if (!diagnostics || typeof diagnostics !== 'object') return null;

    const stage = String(diagnostics.failure_stage || '').toLowerCase();
    const stageLabel = getBackendFailureStageLabel(stage);

    const backendLabel = getBackendLabel(diagnostics.backend_id);
    const readiness = diagnostics.readiness && typeof diagnostics.readiness === 'object'
        ? diagnostics.readiness
        : {};

    const readinessStatus = String(readiness.status || 'unknown');
    const readinessCode = String(readiness.readiness_code || 'unknown');
    const readinessMessage = String(readiness.message || diagnostics.message || err.message || 'Unknown backend error.');

    const remediation = diagnostics.remediation && typeof diagnostics.remediation === 'object'
        ? diagnostics.remediation
        : null;
    const remediationSummary = remediation?.summary
        ? String(remediation.summary)
        : 'Follow backend diagnostics guidance and retry.';
    const remediationActions = getBackendRemediationActions(remediation);

    const alertMessage = `${backendLabel}: ${stageLabel} (${readinessStatus})`;
    const detailLines = [
        'AI backend failure',
        `Stage: ${stageLabel}`,
        `Backend: ${backendLabel}`,
        `Readiness: ${readinessStatus} (${readinessCode})`,
        `Detail: ${readinessMessage}`,
        `Remediation: ${remediationSummary}`,
    ];

    if (typeof diagnostics.error_code === 'string' && diagnostics.error_code) {
        detailLines.push(`Error code: ${diagnostics.error_code}`);
    }

    if (remediationActions.length > 0) {
        detailLines.push('Next steps:');
        remediationActions.forEach((step, index) => {
            detailLines.push(`${index + 1}. ${step}`);
        });
    }

    return {
        alertMessage,
        chatMessage: detailLines.join('\n'),
        readiness,
    };
}

export function normalizeAiBackendDiagnostics(localBackendDiagnostics) {
    if (Array.isArray(localBackendDiagnostics)) {
        return localBackendDiagnostics.reduce((acc, item) => {
            if (item && typeof item === 'object' && item.backend_id) {
                acc[item.backend_id] = item;
            }
            return acc;
        }, {});
    }

    if (localBackendDiagnostics && typeof localBackendDiagnostics === 'object') {
        return Object.entries(localBackendDiagnostics).reduce((acc, [backendId, diagnostic]) => {
            if (diagnostic && typeof diagnostic === 'object') {
                acc[backendId] = diagnostic;
            }
            return acc;
        }, {});
    }

    return {};
}

export function getLocalBackendIdForModel(modelValue) {
    if (typeof modelValue !== 'string') return null;
    if (modelValue.startsWith('llama_cpp::')) return 'llama_cpp';
    if (modelValue.startsWith('lm_studio::')) return 'lm_studio';
    return null;
}

export function getBackendDisplayName(backendId) {
    if (backendId === 'llama_cpp') return 'llama.cpp';
    if (backendId === 'lm_studio') return 'LM Studio';
    return backendId || 'Local backend';
}

export function getReadinessBadge(status) {
    switch ((status || '').toLowerCase()) {
        case 'healthy':
            return '🟢';
        case 'timeout':
            return '🟠';
        case 'unreachable':
            return '🔴';
        case 'misconfigured':
            return '🟣';
        default:
            return '⚪';
    }
}

export function getReadinessLabel(status) {
    switch ((status || '').toLowerCase()) {
        case 'healthy':
            return 'healthy';
        case 'timeout':
            return 'timeout';
        case 'unreachable':
            return 'unreachable';
        case 'misconfigured':
            return 'misconfigured';
        default:
            return 'unknown';
    }
}

export function buildLocalBackendTooltip(backendId, diagnostic) {
    const backendLabel = getBackendDisplayName(backendId);
    const status = getReadinessLabel(diagnostic?.status);
    const readinessCode = diagnostic?.readiness_code || 'n/a';
    const message = diagnostic?.message || 'No readiness diagnostics available yet.';
    const endpoint = diagnostic?.models_endpoint;

    const lines = [
        `${backendLabel} readiness: ${status}`,
        `Code: ${readinessCode}`,
        message,
    ];

    if (endpoint) {
        lines.push(`Probe: ${endpoint}`);
    }

    return lines.join('\n');
}

export function formatLocalModelOptionLabel(modelName, diagnostic) {
    return `${getReadinessBadge(diagnostic?.status)} ${modelName}`;
}

export function buildBackendStatusChip(selectedModel, diagnosticsById = {}) {
    if (!selectedModel) {
        return {
            text: 'Backend: n/a',
            title: 'No AI model selected.',
            statusClass: null,
        };
    }

    const backendId = getLocalBackendIdForModel(selectedModel);
    if (!backendId) {
        return {
            text: 'Backend: cloud',
            title: 'Gemini/Ollama routing does not require local backend readiness probes.',
            statusClass: null,
        };
    }

    const diagnostic = diagnosticsById[backendId] || null;
    const status = getReadinessLabel(diagnostic?.status);
    const badge = getReadinessBadge(diagnostic?.status);

    return {
        text: `${badge} ${getBackendDisplayName(backendId)}: ${status}`,
        title: buildLocalBackendTooltip(backendId, diagnostic),
        statusClass: `status-${status}`,
    };
}

export function applyBackendStatusChip(element, chip) {
    if (!element || !chip) return;

    element.className = 'ai-model-info ai-backend-status';
    if (chip.statusClass && element.classList?.add) {
        element.classList.add(chip.statusClass);
    }

    element.textContent = chip.text;
    element.title = chip.title;
}

export const __TEST_ONLY__ = {
    BACKEND_FAILURE_STAGE_LABELS,
    REMEDIATION_ACTION_LABELS,
};
