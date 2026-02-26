let modal, tableBody;
let nameInput, modeInput, paramsInput, objectivesInput, gridStepsInput, samplesInput, seedInput, maxRunsInput, runOutput;
let legacyObjectivesToggleInput, legacyObjectivesRow;
let rankObjectiveSelect, rankDirectionSelect, rankingTableBody;
let decompositionTableBody, compareTopNSelect, compareRefreshBtn, compareTableWrap, whySelectedSummaryEl, whySelectedDetailsEl;
let failureCountEl, failureGroupsCountEl, failureGroupsEl, failureHintsEl;
let optMethodInput, optBudgetInput, optSeedInput, optPopSizeInput, optSigmaRelInput, optStagInput, verifyRepeatsInput;
let summaryStatusEl, summaryMethodEl, summaryStopReasonEl, summaryEvalsEl, summaryObjectiveEl, summaryBestScoreEl;
let runStatusEl, runActionEl, runElapsedEl, runBudgetUsedEl, runSuccessFailureEl, runLastUpdateEl, runTimelineListEl;
let reviewRunIdEl, reviewGateStatusEl, reviewTokenStatusEl, reviewApplyReadyEl;
let reviewTokenInput, reviewGateReasonsInput, reviewVerifyBtn, reviewApplyBtn, reviewCopyTokenBtn;
let reviewAuditRefreshBtn, reviewRollbackBtn, reviewAuditSummaryEl, reviewAuditDetailsInput;
let reviewAuditTargetSelect, reviewAuditTargetHintEl, reviewAuditTableBody, reviewAuditDiagnosticsEl;
let reviewApplyConfirmTextEl, reviewRollbackConfirmTextEl;
let verifyMinSuccessRateInput, verifyMaxStdInput;
let noticeEl;
let saveBtn, deleteBtn, runBtn, runOptimizerBtn, stopRunBtn, replayBestBtn, verifyBestBtn, downloadResultsBtn, refreshBtn, cancelBtn;
let obTemplateInput, obDatasetPathInput, obCostKeyInput, obScoreExprInput, obOutput;
let obPolicyCapsEl, obAllowedFunctionsEl, obFormulaVarsEl, obDatasetHintEl;
let obLoadExampleBtn, obValidateBtn, obBuildBtn, obUpsertBtn, obLaunchDryRunBtn, obGuidedBtn;
let obCopyOutputBtn, obCopyBuildBtn, obCopyLaunchBtn;
let obStatusEl, obStageEl, obErrorsList, obWarningsList;

const ALLOWED_OBJECTIVE_METRICS = new Set([
    'success_flag',
    'solids_count',
    'logical_volumes_count',
    'placements_count',
    'sources_count',
    'parameter_value',
]);

let callbacks = {
    onSave: async (_payload) => { },
    onDelete: async (_name) => { },
    onRun: async (_name, _maxRuns) => ({}),
    onRunOptimizer: async (_payload) => ({}),
    onStopActiveRun: async (_reason) => ({ active: false, stop_requested: false }),
    onReplayBest: async (_runId, _options) => ({}),
    onVerifyBest: async (_runId, _options) => ({}),
    onGetApplyAuditHistory: async (_limit) => ({ audits: [] }),
    onGetApplyAuditDiagnostics: async () => ({}),
    onRollbackLastApply: async (_auditId) => ({}),
    onRefresh: async () => ({}),
    onObjectiveBuilderSchema: async () => ({}),
    onObjectiveBuilderExample: async (_template) => ({}),
    onObjectiveBuilderValidate: async (_payload) => ({}),
    onObjectiveBuilderBuild: async (_payload) => ({}),
    onObjectiveBuilderUpsert: async (_payload) => ({}),
    onObjectiveBuilderLaunch: async (_payload) => ({}),
};

let activeName = null;
let currentStudies = {};
let lastRunResult = null;
let lastVerificationResult = null;
let currentApplyToken = null;
let currentApplyTokenExpiresAtMs = null;
let tokenExpiryTimer = null;
let applyAuditHistory = [];
let applyAuditDiagnostics = null;
let applyAuditHistoryLoading = false;
let applyAuditHistoryError = null;
let applyAuditDiagnosticsLoading = false;
let applyAuditDiagnosticsError = null;
let lastObjectiveBuilderBuild = null;
let lastObjectiveBuilderLaunch = null;
let noticeTimer = null;
let objectiveBuilderSchema = null;
let applyConfirmState = { armed: false, runId: null, token: null, expiresAtMs: 0 };
let rollbackConfirmState = { armed: false, auditId: null, expiresAtMs: 0 };
let applyConfirmTimer = null;
let rollbackConfirmTimer = null;
let runLifecycleState = {
    status: 'idle',
    action: '-',
    startedAtMs: null,
    endedAtMs: null,
    lastUpdateMs: null,
};
let runLifecycleTimer = null;
let runTimelineEvents = [];
let stopRunRequestPending = false;

function _setForm(study = null, name = '') {
    const s = study || {};
    nameInput.value = name || s.name || '';
    modeInput.value = s.mode || 'grid';
    paramsInput.value = (s.parameters || []).join(',');
    objectivesInput.value = (s.objectives || []).map(o => {
        const metric = o.metric || '';
        const namePart = o.name ? `:${o.name}` : '';
        const dirPart = o.direction ? `:${o.direction}` : '';
        const paramPart = o.parameter ? `:${o.parameter}` : '';
        return `${metric}${namePart}${dirPart}${paramPart}`;
    }).join(',');
    _setLegacyObjectivesVisible((s.objectives || []).length > 0);
    gridStepsInput.value = s.grid?.steps ?? 3;
    samplesInput.value = s.random?.samples ?? 10;
    seedInput.value = s.random?.seed ?? 42;
    maxRunsInput.value = '';
}

function _setLegacyObjectivesVisible(visible) {
    if (!legacyObjectivesRow) return;
    legacyObjectivesRow.style.display = visible ? '' : 'none';
    if (legacyObjectivesToggleInput) legacyObjectivesToggleInput.checked = !!visible;
}

function _extractFormulaIdentifiers(expr) {
    const text = String(expr || '');
    const matches = text.match(/[A-Za-z_][A-Za-z0-9_]*/g) || [];
    return [...new Set(matches)];
}

function _renderFormulaVariableHints() {
    if (!obFormulaVarsEl) return;

    const params = (paramsInput?.value || '')
        .split(',')
        .map(x => x.trim())
        .filter(Boolean);

    const costKey = (obCostKeyInput?.value || '').trim();
    const available = new Set(['edep_sum', ...params]);
    if (costKey) available.add(costKey);

    const allowedFuncs = new Set(Array.isArray(objectiveBuilderSchema?.formula?.allowed_functions)
        ? objectiveBuilderSchema.formula.allowed_functions
        : ['abs', 'min', 'max', 'pow', 'sqrt', 'exp', 'log', 'sin', 'cos', 'tan', 'tanh', 'clip']);

    const expr = (obScoreExprInput?.value || '').trim();
    const ids = _extractFormulaIdentifiers(expr);
    const varsUsed = ids.filter(v => !allowedFuncs.has(v));
    const unknown = varsUsed.filter(v => !available.has(v));

    const availableStr = [...available].sort().join(', ') || '(none)';
    const usedStr = varsUsed.join(', ') || '(none)';
    const unknownStr = unknown.join(', ') || '(none)';

    obFormulaVarsEl.textContent = `Variables — available: ${availableStr} · used: ${usedStr} · unknown: ${unknownStr}`;
    obFormulaVarsEl.style.color = unknown.length > 0 ? '#b45309' : '#475569';
}

function _applyObjectiveBuilderSchemaToUI(schema) {
    objectiveBuilderSchema = schema || null;

    const funcs = Array.isArray(schema?.formula?.allowed_functions) ? schema.formula.allowed_functions : [];
    if (obAllowedFunctionsEl) {
        obAllowedFunctionsEl.textContent = funcs.length > 0
            ? `Allowed functions: ${funcs.join(', ')}`
            : 'Allowed functions: (schema unavailable)';
    }

    const rp = schema?.run_policy || {};
    if (obPolicyCapsEl) {
        const bits = [];
        if (rp.max_budget != null) bits.push(`max budget: ${rp.max_budget}`);
        if (rp.max_events_per_candidate != null) bits.push(`max events/candidate: ${rp.max_events_per_candidate}`);
        if (rp.max_threads != null) bits.push(`max threads: ${rp.max_threads}`);
        if (rp.max_total_events != null) bits.push(`max total events: ${rp.max_total_events}`);
        if (rp.verify_min_repeats != null) bits.push(`verify min repeats: ${rp.verify_min_repeats}`);
        obPolicyCapsEl.textContent = bits.length > 0
            ? `Run policy limits — ${bits.join(' · ')}`
            : 'Run policy limits unavailable.';
    }

    const reduceSpec = Array.isArray(schema?.simulation_extract_metrics)
        ? schema.simulation_extract_metrics.find(m => m?.metric === 'hdf5_reduce')
        : null;
    if (obDatasetHintEl && reduceSpec?.reduce_options) {
        obDatasetHintEl.textContent = `HDF5 reduce options: ${reduceSpec.reduce_options.join(', ')}`;
    }

    const templates = Array.isArray(schema?.templates) ? schema.templates : [];
    if (obTemplateInput && templates.length > 0) {
        const current = obTemplateInput.value;
        obTemplateInput.innerHTML = '';
        templates.forEach(t => {
            if (!t || !t.id) return;
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.label ? `${t.id} — ${t.label}` : t.id;
            obTemplateInput.appendChild(opt);
        });
        if (current && [...obTemplateInput.options].some(o => o.value === current)) {
            obTemplateInput.value = current;
        }
    }

    _renderFormulaVariableHints();
}

function _studyFromForm() {
    const mode = modeInput.value;
    const parameters = paramsInput.value.split(',').map(x => x.trim()).filter(Boolean);

    if (parameters.length === 0) {
        throw new Error('Please provide at least one parameter name.');
    }

    const objectives = objectivesInput.value
        .split(',')
        .map(x => x.trim())
        .filter(Boolean)
        .map(token => {
            const parts = token.split(':').map(p => p.trim());
            const metric = parts[0];
            const name = parts[1] || metric;
            const direction = parts[2] || 'maximize';
            const parameter = parts[3] || null;

            if (!ALLOWED_OBJECTIVE_METRICS.has(metric)) {
                throw new Error(`Unsupported objective metric '${metric}'.`);
            }
            if (!['maximize', 'minimize'].includes(direction)) {
                throw new Error(`Invalid objective direction '${direction}'. Use maximize|minimize.`);
            }
            if (metric === 'parameter_value' && !parameter) {
                throw new Error("parameter_value objective requires 4th token: metric:name:direction:parameterName");
            }

            const out = { metric, name, direction };
            if (parameter) out.parameter = parameter;
            return out;
        });

    const gridSteps = Number(gridStepsInput.value || 3);
    const randomSamples = Number(samplesInput.value || 10);
    if (!Number.isFinite(gridSteps) || gridSteps < 2) {
        throw new Error('Grid steps must be >= 2.');
    }
    if (!Number.isFinite(randomSamples) || randomSamples < 1) {
        throw new Error('Random samples must be >= 1.');
    }

    return {
        name: nameInput.value.trim(),
        mode,
        parameters,
        objectives,
        grid: {
            steps: gridSteps,
            per_parameter_steps: {},
        },
        random: {
            samples: randomSamples,
            seed: Number(seedInput.value || 42),
        },
    };
}

function _objectiveBuilderPayloadFromForm() {
    const studyName = (nameInput?.value || '').trim();
    const studyMode = (modeInput?.value || 'random').trim();
    const studyParameters = (paramsInput?.value || '')
        .split(',')
        .map(x => x.trim())
        .filter(Boolean);

    if (!studyName) {
        throw new Error('Objective Builder requires a study name.');
    }
    if (studyParameters.length === 0) {
        throw new Error('Objective Builder requires at least one study parameter.');
    }

    const datasetPath = (obDatasetPathInput?.value || '').trim() || 'default_ntuples/Hits/Edep';
    const costKey = (obCostKeyInput?.value || '').trim();
    const scoreExpr = (obScoreExprInput?.value || '').trim();

    if (!scoreExpr) {
        throw new Error('Objective Builder requires a score expression.');
    }

    const extractObjectives = [
        {
            name: 'edep_sum',
            metric: 'hdf5_reduce',
            dataset_path: datasetPath,
            reduce: 'sum',
        },
    ];

    if (costKey) {
        extractObjectives.push({
            name: costKey,
            metric: 'context_value',
            key: costKey,
            default: 0.0,
        });
    }

    const studyObjectives = [
        {
            name: 'edep_sum',
            metric: 'sim_metric',
            key: 'edep_sum',
            direction: 'maximize',
        },
        {
            name: 'score',
            metric: 'formula',
            expression: scoreExpr,
            direction: 'maximize',
        },
    ];

    const budget = Number(optBudgetInput?.value || 20);
    const seed = Number(optSeedInput?.value || 42);
    const runMethod = (optMethodInput?.value || 'surrogate_gp').trim();

    const payload = {
        study_name: studyName,
        study_mode: studyMode,
        study_parameters: studyParameters,
        study_random: {
            samples: Number(samplesInput?.value || 10),
            seed: Number(seedInput?.value || 42),
        },
        study_grid: {
            steps: Number(gridStepsInput?.value || 3),
        },
        extract_objectives: extractObjectives,
        study_objectives: studyObjectives,
        context: costKey ? { [costKey]: 0.0 } : {},
        run_method: runMethod,
        run_budget: Number.isFinite(budget) ? budget : 20,
        run_seed: Number.isFinite(seed) ? seed : 42,
    };

    return payload;
}

function _setObjectiveBuilderOutput(value) {
    if (!obOutput) return;
    if (typeof value === 'string') {
        obOutput.value = value;
        return;
    }
    try {
        obOutput.value = JSON.stringify(value, null, 2);
    } catch (_e) {
        obOutput.value = String(value);
    }
}

function _showNotice(message, type = 'info', timeoutMs = 4000) {
    if (!noticeEl) return;
    const text = String(message || '');
    if (!text) {
        noticeEl.style.display = 'none';
        noticeEl.textContent = '';
        return;
    }

    const styles = {
        info: { bg: '#eff6ff', border: '#93c5fd', color: '#1e3a8a' },
        success: { bg: '#ecfdf5', border: '#86efac', color: '#14532d' },
        warning: { bg: '#fffbeb', border: '#fcd34d', color: '#92400e' },
        error: { bg: '#fef2f2', border: '#fca5a5', color: '#991b1b' },
    };
    const style = styles[type] || styles.info;

    noticeEl.style.display = 'block';
    noticeEl.style.background = style.bg;
    noticeEl.style.border = `1px solid ${style.border}`;
    noticeEl.style.color = style.color;
    noticeEl.textContent = text;

    if (noticeTimer) {
        clearTimeout(noticeTimer);
        noticeTimer = null;
    }
    if (timeoutMs > 0) {
        noticeTimer = setTimeout(() => {
            if (noticeEl) {
                noticeEl.style.display = 'none';
                noticeEl.textContent = '';
            }
            noticeTimer = null;
        }, timeoutMs);
    }
}

async function _copyTextToClipboard(text) {
    const value = String(text ?? '');
    if (!value) {
        _showNotice('Nothing to copy.', 'warning');
        return;
    }

    try {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(value);
        } else {
            const ta = document.createElement('textarea');
            ta.value = value;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
        }
        _showNotice('Copied to clipboard.', 'success', 2200);
    } catch (e) {
        _showNotice(`Copy failed: ${e?.message || e}`, 'error', 6000);
    }
}

function _toPrettyJson(value) {
    try {
        return JSON.stringify(value, null, 2);
    } catch (_e) {
        return String(value);
    }
}

async function _handleCopyObjectiveBuilderOutput() {
    await _copyTextToClipboard(obOutput?.value || '');
}

async function _handleCopyObjectiveBuilderBuild() {
    if (!lastObjectiveBuilderBuild) {
        _showNotice('No build payload available yet. Run Build or Guided flow first.', 'warning');
        return;
    }
    await _copyTextToClipboard(_toPrettyJson(lastObjectiveBuilderBuild));
}

async function _handleCopyObjectiveBuilderLaunch() {
    if (!lastObjectiveBuilderLaunch) {
        _showNotice('No launch payload available yet. Run Launch Dry Run or Guided flow first.', 'warning');
        return;
    }
    await _copyTextToClipboard(_toPrettyJson(lastObjectiveBuilderLaunch));
}

function _setListItems(listEl, items = [], emptyText = 'none') {
    if (!listEl) return;
    listEl.innerHTML = '';
    const arr = Array.isArray(items) ? items.filter(Boolean) : [];
    if (arr.length === 0) {
        const li = document.createElement('li');
        li.style.color = '#64748b';
        li.textContent = emptyText;
        listEl.appendChild(li);
        return;
    }
    arr.forEach(item => {
        const li = document.createElement('li');
        li.textContent = String(item);
        listEl.appendChild(li);
    });
}

function _extractBuilderErrorsWarnings(result) {
    const errors = [];
    const warnings = [];

    if (!result || typeof result !== 'object') {
        return { errors, warnings };
    }

    if (result.validation && typeof result.validation === 'object') {
        if (Array.isArray(result.validation.errors)) errors.push(...result.validation.errors);
        if (Array.isArray(result.validation.warnings)) warnings.push(...result.validation.warnings);
    }

    if (Array.isArray(result.details)) {
        errors.push(...result.details);
    }

    if (Array.isArray(result.warnings)) {
        warnings.push(...result.warnings);
    }

    if (!result.success && result.error) {
        errors.unshift(result.error);
    }

    return {
        errors: [...new Set(errors.map(x => String(x)))],
        warnings: [...new Set(warnings.map(x => String(x)))],
    };
}

function _renderObjectiveBuilderFeedback(stage, result) {
    const success = !!(result && result.success !== false);
    if (obStatusEl) {
        obStatusEl.textContent = success ? 'ok' : 'error';
        obStatusEl.style.color = success ? '#15803d' : '#b91c1c';
        obStatusEl.style.fontWeight = '700';
    }
    if (obStageEl) {
        obStageEl.textContent = stage || '-';
        obStageEl.style.color = success ? '#0f766e' : '#b45309';
    }

    const { errors, warnings } = _extractBuilderErrorsWarnings(result);
    _setListItems(obErrorsList, errors, 'none');
    _setListItems(obWarningsList, warnings, 'none');

    if (obErrorsList) {
        obErrorsList.style.borderLeft = errors.length > 0 ? '3px solid #ef4444' : '3px solid transparent';
        obErrorsList.style.paddingLeft = '8px';
    }
    if (obWarningsList) {
        obWarningsList.style.borderLeft = warnings.length > 0 ? '3px solid #f59e0b' : '3px solid transparent';
        obWarningsList.style.paddingLeft = '8px';
    }
}

function _renderObjectiveBuilderFailure(stage, error) {
    const data = error?.data && typeof error.data === 'object'
        ? error.data
        : { success: false, error: error?.message || String(error) };
    _renderObjectiveBuilderFeedback(stage, data);
    _setObjectiveBuilderOutput(data);
}

function _applyObjectiveBuilderExample(example) {
    if (!example || typeof example !== 'object') return;

    if (example.study_name && !nameInput.value.trim()) {
        nameInput.value = example.study_name;
    }
    if (example.study_mode) {
        modeInput.value = example.study_mode;
    }
    if (Array.isArray(example.study_parameters) && example.study_parameters.length > 0 && !paramsInput.value.trim()) {
        paramsInput.value = example.study_parameters.join(',');
    }

    const extract = Array.isArray(example.extract_objectives) ? example.extract_objectives : [];
    const edep = extract.find(o => o && o.name === 'edep_sum');
    if (edep?.dataset_path && obDatasetPathInput) {
        obDatasetPathInput.value = edep.dataset_path;
    }
    const contextObj = extract.find(o => o && o.metric === 'context_value');
    if (contextObj?.key && obCostKeyInput) {
        obCostKeyInput.value = contextObj.key;
    }

    const studyObjs = Array.isArray(example.study_objectives) ? example.study_objectives : [];
    const scoreObj = studyObjs.find(o => o && o.name === 'score' && o.metric === 'formula');
    if (scoreObj?.expression && obScoreExprInput) {
        obScoreExprInput.value = scoreObj.expression;
    }

    if (example.run_budget && optBudgetInput) optBudgetInput.value = example.run_budget;
    if (example.run_seed && optSeedInput) optSeedInput.value = example.run_seed;

    _renderFormulaVariableHints();
}

async function _handleObjectiveBuilderLoadExample() {
    try {
        const template = (obTemplateInput?.value || 'weighted_tradeoff').trim() || 'weighted_tradeoff';
        const example = await callbacks.onObjectiveBuilderExample(template);
        _applyObjectiveBuilderExample(example || {});
        const out = { success: true, message: `Loaded template '${template}'.`, payload: example || {} };
        _renderObjectiveBuilderFeedback('load_example', out);
        _setObjectiveBuilderOutput(out);
        _showNotice(`Loaded template '${template}'.`, 'success', 2500);
    } catch (error) {
        _renderObjectiveBuilderFailure('load_example', error);
        _showNotice(error.message || String(error), 'error', 7000);
    }
}

async function _handleObjectiveBuilderValidate() {
    try {
        const payload = _objectiveBuilderPayloadFromForm();
        const result = await callbacks.onObjectiveBuilderValidate(payload);
        _renderObjectiveBuilderFeedback('validate', result || {});
        _setObjectiveBuilderOutput(result || {});
        const valid = !!result?.validation?.valid;
        _showNotice(valid ? 'Validation passed.' : 'Validation completed with issues.', valid ? 'success' : 'warning', 2800);
    } catch (error) {
        _renderObjectiveBuilderFailure('validate', error);
        _showNotice(error.message || String(error), 'error', 7000);
    }
}

async function _handleObjectiveBuilderBuild() {
    try {
        const payload = _objectiveBuilderPayloadFromForm();
        const result = await callbacks.onObjectiveBuilderBuild(payload);
        lastObjectiveBuilderBuild = result?.build || null;
        _renderObjectiveBuilderFeedback('build', result || {});
        _setObjectiveBuilderOutput(result || {});
        _showNotice('Build payload generated.', 'success', 2500);
    } catch (error) {
        _renderObjectiveBuilderFailure('build', error);
        _showNotice(error.message || String(error), 'error', 7000);
    }
}

async function _handleObjectiveBuilderUpsert() {
    try {
        const payload = _objectiveBuilderPayloadFromForm();
        const result = await callbacks.onObjectiveBuilderUpsert(payload);
        _renderObjectiveBuilderFeedback('upsert_study', result || {});
        _setObjectiveBuilderOutput(result || {});
        await _refreshAndRender();
        _showNotice(`Study ${result?.action || 'saved'}.`, 'success', 2600);
    } catch (error) {
        _renderObjectiveBuilderFailure('upsert_study', error);
        _showNotice(error.message || String(error), 'error', 7000);
    }
}

async function _handleObjectiveBuilderLaunchDryRun() {
    _setRunLifecycle('running', 'objective_builder_launch_dry_run', 'Preparing launch payload');
    try {
        const payload = _objectiveBuilderPayloadFromForm();
        payload.dry_run = true;
        const result = await callbacks.onObjectiveBuilderLaunch(payload);
        lastObjectiveBuilderLaunch = result || null;
        _renderObjectiveBuilderFeedback('launch_dry_run', result || {});
        _setObjectiveBuilderOutput(result || {});
        _showNotice('Launch dry run prepared successfully.', 'success', 2800);
        _setRunLifecycle('completed', 'objective_builder_launch_dry_run', 'dry_run prepared');
    } catch (error) {
        _renderObjectiveBuilderFailure('launch_dry_run', error);
        _showNotice(error.message || String(error), 'error', 7000);
        _setRunLifecycle('failed', 'objective_builder_launch_dry_run', error?.message || String(error));
    }
}

async function _handleObjectiveBuilderGuided() {
    const guidedOutput = { success: true, steps: {} };
    try {
        const payload = _objectiveBuilderPayloadFromForm();

        const validateResult = await callbacks.onObjectiveBuilderValidate(payload);
        guidedOutput.steps.validate = validateResult;
        if (!validateResult?.validation?.valid) {
            const out = {
                success: false,
                error: 'Validation failed. Fix errors before build/launch.',
                validation: validateResult?.validation || {},
                steps: guidedOutput.steps,
            };
            _renderObjectiveBuilderFeedback('guided_validate', out);
            _setObjectiveBuilderOutput(out);
            _showNotice('Guided flow stopped at validation step.', 'warning', 3200);
            return;
        }

        const buildResult = await callbacks.onObjectiveBuilderBuild(payload);
        guidedOutput.steps.build = buildResult;
        lastObjectiveBuilderBuild = buildResult?.build || null;

        const launchResult = await callbacks.onObjectiveBuilderLaunch({ build: buildResult?.build, dry_run: true });
        guidedOutput.steps.launch_dry_run = launchResult;
        lastObjectiveBuilderLaunch = launchResult || null;

        const out = { success: true, message: 'Guided flow completed (validate → build → dry run).', ...guidedOutput };
        _renderObjectiveBuilderFeedback('guided_complete', out);
        _setObjectiveBuilderOutput(out);
        _showNotice('Guided flow completed.', 'success', 2800);
    } catch (error) {
        const failure = {
            success: false,
            error: error?.message || String(error),
            steps: guidedOutput.steps,
            details: error?.data?.details || undefined,
            validation: error?.data?.validation || undefined,
        };
        _renderObjectiveBuilderFeedback('guided_failed', failure);
        _setObjectiveBuilderOutput(failure);
        _showNotice(error.message || String(error), 'error', 7000);
    }
}

function _renderTable(studies = {}) {
    currentStudies = studies || {};
    const entries = Object.entries(currentStudies).sort(([a], [b]) => a.localeCompare(b));
    tableBody.innerHTML = '';

    if (entries.length === 0) {
        const tr = document.createElement('tr');
        tr.innerHTML = '<td colspan="3" style="color:#64748b;">No studies defined.</td>';
        tableBody.appendChild(tr);
        return;
    }

    for (const [name, study] of entries) {
        const tr = document.createElement('tr');
        if (name === activeName) tr.classList.add('active');
        tr.innerHTML = `
            <td>${name}</td>
            <td>${study.mode || ''}</td>
            <td>${(study.parameters || []).join(', ')}</td>
        `;
        tr.addEventListener('click', () => {
            activeName = name;
            _setForm(study, name);
            _renderTable(currentStudies);
        });
        tableBody.appendChild(tr);
    }
}

function _extractRunsFromLastResult() {
    if (!lastRunResult) return [];
    if (Array.isArray(lastRunResult.runs)) return lastRunResult.runs;
    if (Array.isArray(lastRunResult.candidates)) return lastRunResult.candidates;
    return [];
}

function _getOptimizerRunIdFromLastResult() {
    if (!lastRunResult) return null;
    if (typeof lastRunResult.run_id === 'string' && lastRunResult.run_id.length > 0) {
        return lastRunResult.run_id;
    }
    return null;
}

function _setApplyConfirmText(text, color = '#64748b') {
    if (!reviewApplyConfirmTextEl) return;
    reviewApplyConfirmTextEl.textContent = text;
    reviewApplyConfirmTextEl.style.color = color;
}

function _setRollbackConfirmText(text, color = '#64748b') {
    if (!reviewRollbackConfirmTextEl) return;
    reviewRollbackConfirmTextEl.textContent = text;
    reviewRollbackConfirmTextEl.style.color = color;
}

function _resetApplyConfirmation() {
    applyConfirmState = { armed: false, runId: null, token: null, expiresAtMs: 0 };
    if (applyConfirmTimer) {
        clearTimeout(applyConfirmTimer);
        applyConfirmTimer = null;
    }
    if (reviewApplyBtn) reviewApplyBtn.textContent = 'Apply Best (Token Required)';
    _setApplyConfirmText('Apply confirmation not armed.', '#64748b');
}

function _armApplyConfirmation(runId, token, summaryText) {
    const ttlMs = 10000;
    const expiresAt = Date.now() + ttlMs;
    applyConfirmState = { armed: true, runId, token, expiresAtMs: expiresAt };
    if (reviewApplyBtn) reviewApplyBtn.textContent = 'Confirm Apply (10s)';
    _setApplyConfirmText(summaryText || 'Apply confirmation armed for 10 seconds.', '#92400e');

    if (applyConfirmTimer) clearTimeout(applyConfirmTimer);
    applyConfirmTimer = setTimeout(() => {
        _resetApplyConfirmation();
    }, ttlMs + 50);
}

function _resetRollbackConfirmation() {
    rollbackConfirmState = { armed: false, auditId: null, expiresAtMs: 0 };
    if (rollbackConfirmTimer) {
        clearTimeout(rollbackConfirmTimer);
        rollbackConfirmTimer = null;
    }
    if (reviewRollbackBtn) reviewRollbackBtn.textContent = 'Rollback Selected';
    _setRollbackConfirmText('Rollback confirmation not armed.', '#64748b');
}

function _armRollbackConfirmation(auditId, summaryText) {
    const ttlMs = 10000;
    const expiresAt = Date.now() + ttlMs;
    rollbackConfirmState = { armed: true, auditId, expiresAtMs: expiresAt };
    if (reviewRollbackBtn) reviewRollbackBtn.textContent = 'Confirm Rollback (10s)';
    _setRollbackConfirmText(summaryText || 'Rollback confirmation armed for 10 seconds.', '#92400e');

    if (rollbackConfirmTimer) clearTimeout(rollbackConfirmTimer);
    rollbackConfirmTimer = setTimeout(() => {
        _resetRollbackConfirmation();
    }, ttlMs + 50);
}

function _stopTokenExpiryTimer() {
    if (tokenExpiryTimer) {
        clearInterval(tokenExpiryTimer);
        tokenExpiryTimer = null;
    }
}

function _ensureTokenExpiryTimer() {
    if (tokenExpiryTimer) return;
    if (!Number.isFinite(currentApplyTokenExpiresAtMs)) return;
    if (!currentApplyToken) return;

    tokenExpiryTimer = setInterval(() => {
        _updateRunReviewPanel();
    }, 1000);
}

function _formatTokenTtlShort(msLeft) {
    const sec = Math.max(0, Math.floor(msLeft / 1000));
    const mm = Math.floor(sec / 60);
    const ss = sec % 60;
    if (mm > 0) return `${mm}m ${String(ss).padStart(2, '0')}s`;
    return `${ss}s`;
}

function _clearReviewToken() {
    currentApplyToken = null;
    currentApplyTokenExpiresAtMs = null;
    _stopTokenExpiryTimer();
    _resetApplyConfirmation();
}

function _formatClockTime(ms) {
    if (!ms) return '-';
    const d = new Date(ms);
    return d.toLocaleTimeString();
}

function _formatElapsedSeconds(ms) {
    if (!Number.isFinite(ms) || ms < 0) return '0.0s';
    return `${(ms / 1000).toFixed(1)}s`;
}

function _computeRunBudgetSummary() {
    if (!lastRunResult || typeof lastRunResult !== 'object') return '-';

    if (Array.isArray(lastRunResult.candidates)) {
        const used = Number(lastRunResult.evaluations_used ?? lastRunResult.candidates.length ?? 0);
        const budget = Number(lastRunResult.budget ?? lastRunResult.candidates.length ?? 0);
        if (Number.isFinite(used) && Number.isFinite(budget) && budget > 0) return `${used}/${budget}`;
        if (Number.isFinite(used)) return String(used);
    }

    if (Array.isArray(lastRunResult.runs)) {
        const used = Number(lastRunResult.runs.length ?? 0);
        const requested = Number(lastRunResult.requested_runs ?? used);
        if (Number.isFinite(used) && Number.isFinite(requested) && requested > 0) return `${used}/${requested}`;
        if (Number.isFinite(used)) return String(used);
    }

    return '-';
}

function _computeRunSuccessFailureSummary() {
    if (!lastRunResult || typeof lastRunResult !== 'object') return '-';

    if (Number.isFinite(Number(lastRunResult.success_count)) || Number.isFinite(Number(lastRunResult.failure_count))) {
        const s = Number(lastRunResult.success_count ?? 0);
        const f = Number(lastRunResult.failure_count ?? 0);
        return `${s}/${f}`;
    }

    if (Array.isArray(lastRunResult.candidates)) {
        let s = 0;
        let f = 0;
        lastRunResult.candidates.forEach(c => {
            if (c?.success) s += 1;
            else f += 1;
        });
        return `${s}/${f}`;
    }

    if (Array.isArray(lastRunResult.runs)) {
        let s = 0;
        let f = 0;
        lastRunResult.runs.forEach(c => {
            if (c?.success) s += 1;
            else f += 1;
        });
        return `${s}/${f}`;
    }

    return '-';
}

function _renderRunTimelineCard() {
    if (!runStatusEl) return;

    const now = Date.now();
    const start = runLifecycleState.startedAtMs;
    const end = runLifecycleState.endedAtMs;
    const elapsedMs = start ? ((runLifecycleState.status === 'running' ? now : (end || now)) - start) : 0;

    runStatusEl.textContent = runLifecycleState.status || 'idle';
    runStatusEl.style.color = runLifecycleState.status === 'running'
        ? '#0369a1'
        : runLifecycleState.status === 'completed'
            ? '#15803d'
            : runLifecycleState.status === 'failed'
                ? '#b91c1c'
                : '#64748b';
    runStatusEl.style.fontWeight = '700';

    if (runActionEl) runActionEl.textContent = runLifecycleState.action || '-';
    if (runElapsedEl) runElapsedEl.textContent = _formatElapsedSeconds(elapsedMs);
    if (runBudgetUsedEl) runBudgetUsedEl.textContent = _computeRunBudgetSummary();
    if (runSuccessFailureEl) runSuccessFailureEl.textContent = _computeRunSuccessFailureSummary();
    if (runLastUpdateEl) runLastUpdateEl.textContent = _formatClockTime(runLifecycleState.lastUpdateMs);

    if (runTimelineListEl) {
        runTimelineListEl.innerHTML = '';
        if (!Array.isArray(runTimelineEvents) || runTimelineEvents.length === 0) {
            const li = document.createElement('li');
            li.style.color = '#64748b';
            li.textContent = 'No run activity yet.';
            runTimelineListEl.appendChild(li);
        } else {
            runTimelineEvents.slice(-12).forEach(ev => {
                const li = document.createElement('li');
                const t = _formatClockTime(ev.timeMs);
                const details = ev.details ? ` — ${ev.details}` : '';
                li.textContent = `[${t}] ${ev.status}/${ev.action}${details}`;
                li.style.color = ev.status === 'failed' ? '#b91c1c' : (ev.status === 'completed' ? '#15803d' : '#334155');
                runTimelineListEl.appendChild(li);
            });
        }
    }
}

function _startRunLifecycleTimer() {
    if (runLifecycleTimer) return;
    runLifecycleTimer = setInterval(() => {
        if (runLifecycleState.status !== 'running') {
            clearInterval(runLifecycleTimer);
            runLifecycleTimer = null;
            return;
        }
        _renderRunTimelineCard();
    }, 250);
}

function _stopRunLifecycleTimer() {
    if (runLifecycleTimer) {
        clearInterval(runLifecycleTimer);
        runLifecycleTimer = null;
    }
}

function _updateStopRunButtonState() {
    if (!stopRunBtn) return;
    const stoppableActions = new Set(['optimizer_run', 'param_study_run']);
    const isRunning = runLifecycleState.status === 'running' && stoppableActions.has(runLifecycleState.action);
    stopRunBtn.disabled = !isRunning || stopRunRequestPending;
    stopRunBtn.textContent = stopRunRequestPending ? 'Stopping…' : 'Stop Active Run';
}

function _setRunLifecycle(status, action, details = '') {
    const now = Date.now();
    if (status === 'running') {
        runLifecycleState.startedAtMs = now;
        runLifecycleState.endedAtMs = null;
    }
    if (status === 'completed' || status === 'failed') {
        if (!runLifecycleState.startedAtMs) runLifecycleState.startedAtMs = now;
        runLifecycleState.endedAtMs = now;
    }

    runLifecycleState.status = status;
    runLifecycleState.action = action || '-';
    runLifecycleState.lastUpdateMs = now;

    runTimelineEvents.push({
        timeMs: now,
        status,
        action: action || '-',
        details: details || '',
    });

    if (runTimelineEvents.length > 50) {
        runTimelineEvents = runTimelineEvents.slice(-50);
    }

    if (status === 'running') _startRunLifecycleTimer();
    else _stopRunLifecycleTimer();

    _updateStopRunButtonState();
    _renderRunTimelineCard();
}

function _updateRunReviewPanel() {
    const runId = _getOptimizerRunIdFromLastResult();

    if (reviewRunIdEl) reviewRunIdEl.textContent = runId || '-';
    if (reviewTokenInput) reviewTokenInput.value = currentApplyToken || '';

    let gatePassed = false;
    let gateReasons = [];

    if (lastVerificationResult?.verification_gate) {
        gatePassed = !!lastVerificationResult.verification_gate.passed;
        gateReasons = Array.isArray(lastVerificationResult.verification_gate.reasons)
            ? lastVerificationResult.verification_gate.reasons
            : [];
    }

    if (reviewGateStatusEl) {
        reviewGateStatusEl.textContent = gatePassed ? 'passed' : 'not passed';
        reviewGateStatusEl.style.color = gatePassed ? '#15803d' : '#b45309';
        reviewGateStatusEl.style.fontWeight = '700';
    }

    const hasToken = !!currentApplyToken;
    const nowMs = Date.now();
    const ttlMs = Number.isFinite(currentApplyTokenExpiresAtMs)
        ? (currentApplyTokenExpiresAtMs - nowMs)
        : null;
    const tokenExpired = !!(hasToken && Number.isFinite(ttlMs) && ttlMs <= 0);

    if (tokenExpired) {
        _clearReviewToken();
    }

    const effectiveHasToken = !!currentApplyToken;
    if (reviewTokenStatusEl) {
        if (!effectiveHasToken) {
            reviewTokenStatusEl.textContent = 'none';
            reviewTokenStatusEl.style.color = '#64748b';
        } else if (Number.isFinite(ttlMs)) {
            reviewTokenStatusEl.textContent = `issued (${_formatTokenTtlShort(ttlMs)} left)`;
            reviewTokenStatusEl.style.color = ttlMs <= 30000 ? '#b45309' : '#15803d';
        } else {
            reviewTokenStatusEl.textContent = 'issued';
            reviewTokenStatusEl.style.color = '#15803d';
        }
    }

    if (effectiveHasToken && Number.isFinite(currentApplyTokenExpiresAtMs)) {
        _ensureTokenExpiryTimer();
    } else {
        _stopTokenExpiryTimer();
    }

    const canApply = !!runId && gatePassed && effectiveHasToken;
    if (reviewApplyReadyEl) {
        reviewApplyReadyEl.textContent = canApply ? 'ready' : 'blocked';
        reviewApplyReadyEl.style.color = canApply ? '#15803d' : '#b91c1c';
        reviewApplyReadyEl.style.fontWeight = '700';
    }

    if (reviewApplyBtn) {
        reviewApplyBtn.disabled = !canApply;
    }

    if (!canApply) {
        _resetApplyConfirmation();
    } else if (!applyConfirmState.armed) {
        const gate = lastVerificationResult?.verification_gate || {};
        const sr = Number(gate.success_rate);
        const std = gate.stats_std;
        const srTxt = Number.isFinite(sr) ? sr.toFixed(3) : 'n/a';
        const stdTxt = _formatMaybeNumber(std, 5);
        const expiryTxt = Number.isFinite(currentApplyTokenExpiresAtMs)
            ? ` Token expires at ${_formatClockTime(currentApplyTokenExpiresAtMs)}.`
            : '';
        _setApplyConfirmText(
            `Apply target summary: run ${runId}, gate passed, success_rate=${srTxt}, std=${stdTxt}.${expiryTxt} Click Apply to arm confirmation.`
        );
    }

    if (reviewGateReasonsInput) {
        if (!lastVerificationResult) {
            reviewGateReasonsInput.value = 'No verification run yet.';
        } else if (gateReasons.length === 0) {
            reviewGateReasonsInput.value = gatePassed
                ? 'Verification gate passed.'
                : 'Verification gate failed without explicit reasons.';
        } else {
            reviewGateReasonsInput.value = gateReasons.map((r, idx) => `${idx + 1}. ${r}`).join('\n');
        }
    }
}

function _renderApplyAuditDiagnostics() {
    if (!reviewAuditDiagnosticsEl) return;

    if (applyAuditDiagnosticsLoading) {
        reviewAuditDiagnosticsEl.textContent = 'Audit diagnostics: loading…';
        reviewAuditDiagnosticsEl.style.color = '#64748b';
        return;
    }

    if (applyAuditDiagnosticsError) {
        reviewAuditDiagnosticsEl.textContent = `Audit diagnostics unavailable: ${applyAuditDiagnosticsError}`;
        reviewAuditDiagnosticsEl.style.color = '#b45309';
        return;
    }

    const d = applyAuditDiagnostics || {};
    const scope = d.project_scope_id || '-';
    const count = Number.isFinite(Number(d.scope_entry_count)) ? Number(d.scope_entry_count) : 0;
    const maxPerScope = Number.isFinite(Number(d?.storage?.max_entries_per_scope))
        ? Number(d.storage.max_entries_per_scope)
        : 'n/a';
    const exists = !!d?.storage?.exists;
    const filePath = d?.storage?.path || '-';

    reviewAuditDiagnosticsEl.textContent = `Audit diagnostics — scope=${scope}, entries=${count}, max/scope=${maxPerScope}, storage=${exists ? 'present' : 'missing'} (${filePath})`;
    reviewAuditDiagnosticsEl.style.color = '#64748b';
}

function _renderApplyAuditPanel() {
    if (!reviewAuditSummaryEl || !reviewAuditDetailsInput) return;

    _renderApplyAuditDiagnostics();

    const audits = Array.isArray(applyAuditHistory) ? applyAuditHistory : [];
    const latestUnrolled = audits.find(a => !a?.rolled_back) || null;

    if (reviewAuditRefreshBtn) reviewAuditRefreshBtn.disabled = !!applyAuditHistoryLoading;

    if (applyAuditHistoryLoading && audits.length === 0) {
        reviewAuditSummaryEl.textContent = 'Loading apply audit history…';
        reviewAuditSummaryEl.style.color = '#0369a1';
        reviewAuditDetailsInput.value = '';

        if (reviewAuditTargetSelect) {
            reviewAuditTargetSelect.innerHTML = '';
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'Loading…';
            reviewAuditTargetSelect.appendChild(opt);
            reviewAuditTargetSelect.disabled = true;
        }

        if (reviewAuditTableBody) {
            reviewAuditTableBody.innerHTML = '<tr><td colspan="4" style="padding:6px; color:#0369a1;">Loading apply audit history…</td></tr>';
        }

        _resetRollbackConfirmation();
        if (reviewRollbackBtn) reviewRollbackBtn.disabled = true;
        if (reviewAuditTargetHintEl) reviewAuditTargetHintEl.textContent = 'Please wait while audit history is loading.';
        return;
    }

    if (applyAuditHistoryError && audits.length === 0) {
        reviewAuditSummaryEl.textContent = 'Unable to load apply audit history.';
        reviewAuditSummaryEl.style.color = '#b91c1c';
        reviewAuditDetailsInput.value = JSON.stringify({ error: applyAuditHistoryError }, null, 2);

        if (reviewAuditTargetSelect) {
            reviewAuditTargetSelect.innerHTML = '';
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'Unavailable';
            reviewAuditTargetSelect.appendChild(opt);
            reviewAuditTargetSelect.disabled = true;
        }

        if (reviewAuditTableBody) {
            reviewAuditTableBody.innerHTML = `<tr><td colspan="4" style="padding:6px; color:#b91c1c;">${applyAuditHistoryError}. Click "Refresh Audit" to retry.</td></tr>`;
        }

        _resetRollbackConfirmation();
        if (reviewRollbackBtn) reviewRollbackBtn.disabled = true;
        if (reviewAuditTargetHintEl) reviewAuditTargetHintEl.textContent = 'Audit history unavailable. Refresh and retry.';
        return;
    }

    if (audits.length === 0) {
        reviewAuditSummaryEl.textContent = 'No apply actions recorded yet. Verify and apply a candidate to create the first audit entry.';
        reviewAuditSummaryEl.style.color = '#64748b';
        reviewAuditDetailsInput.value = '';

        if (reviewAuditTargetSelect) {
            reviewAuditTargetSelect.innerHTML = '';
            const opt = document.createElement('option');
            opt.value = '';
            opt.textContent = 'No audit entries';
            reviewAuditTargetSelect.appendChild(opt);
            reviewAuditTargetSelect.disabled = true;
        }

        if (reviewAuditTableBody) {
            reviewAuditTableBody.innerHTML = '<tr><td colspan="4" style="padding:6px; color:#64748b;">No apply actions recorded yet. Run Verify + Apply to populate history.</td></tr>';
        }

        _resetRollbackConfirmation();
        if (reviewRollbackBtn) reviewRollbackBtn.disabled = true;
        if (reviewAuditTargetHintEl) reviewAuditTargetHintEl.textContent = 'No rollback targets available yet.';
        return;
    }

    const latest = audits[0] || {};
    const rolled = !!latest.rolled_back;
    const runId = latest.run_id || '-';
    const at = latest.created_at || '-';
    let summaryText = `Latest apply: run ${runId} at ${at} (${rolled ? 'rolled back' : 'active'}) · total entries: ${audits.length}`;
    if (applyAuditHistoryLoading) summaryText += ' · refreshing…';
    if (applyAuditHistoryError) summaryText += ` · showing cached data (${applyAuditHistoryError})`;
    reviewAuditSummaryEl.textContent = summaryText;
    if (applyAuditHistoryError) {
        reviewAuditSummaryEl.style.color = '#b45309';
    } else if (applyAuditHistoryLoading) {
        reviewAuditSummaryEl.style.color = '#0369a1';
    } else {
        reviewAuditSummaryEl.style.color = rolled ? '#92400e' : '#14532d';
    }

    if (reviewAuditTargetSelect) {
        const selectedBefore = reviewAuditTargetSelect.value;
        reviewAuditTargetSelect.innerHTML = '';

        audits.slice(0, 30).forEach(a => {
            const opt = document.createElement('option');
            opt.value = a.audit_id || '';
            const marker = a.rolled_back ? 'rolled_back' : (latestUnrolled && a.audit_id === latestUnrolled.audit_id ? 'latest_unapplied' : 'older_unapplied');
            opt.textContent = `${a.created_at || '-'} · run ${a.run_id || '-'} · ${marker}`;
            reviewAuditTargetSelect.appendChild(opt);
        });

        if (selectedBefore && [...reviewAuditTargetSelect.options].some(o => o.value === selectedBefore)) {
            reviewAuditTargetSelect.value = selectedBefore;
        }

        if (!reviewAuditTargetSelect.value && latestUnrolled?.audit_id) {
            reviewAuditTargetSelect.value = latestUnrolled.audit_id;
        }

        reviewAuditTargetSelect.disabled = false;
    }

    if (reviewAuditTableBody) {
        reviewAuditTableBody.innerHTML = '';
        audits.slice(0, 20).forEach(a => {
            const tr = document.createElement('tr');
            const status = a.rolled_back
                ? 'rolled back'
                : (latestUnrolled && a.audit_id === latestUnrolled.audit_id ? 'latest unapplied' : 'older unapplied');
            tr.innerHTML = `
                <td style="padding:4px; border-bottom:1px solid #f1f5f9;">${a.created_at || '-'}</td>
                <td style="padding:4px; border-bottom:1px solid #f1f5f9;">${a.run_id || '-'}</td>
                <td style="padding:4px; border-bottom:1px solid #f1f5f9; color:${a.rolled_back ? '#92400e' : '#334155'};">${status}</td>
                <td style="padding:4px; border-bottom:1px solid #f1f5f9; font-family: ui-monospace, Menlo, monospace;">${a.audit_id || '-'}</td>
            `;
            reviewAuditTableBody.appendChild(tr);
        });
    }

    const selectedAuditId = reviewAuditTargetSelect?.value || latest.audit_id;
    const selected = audits.find(a => a.audit_id === selectedAuditId) || latest;

    const details = {
        selected,
        latest_unapplied_audit_id: latestUnrolled?.audit_id || null,
        recent: audits.slice(0, 10),
    };
    reviewAuditDetailsInput.value = JSON.stringify(details, null, 2);

    const selectableIsLatestUnapplied = !!(selected && latestUnrolled && selected.audit_id === latestUnrolled.audit_id && !selected.rolled_back);

    const now = Date.now();
    const rollbackArmedValid = rollbackConfirmState.armed
        && rollbackConfirmState.auditId === selectedAuditId
        && rollbackConfirmState.expiresAtMs > now;

    if (!rollbackArmedValid) {
        _resetRollbackConfirmation();
    } else {
        _setRollbackConfirmText(`Rollback confirmation armed for audit ${selectedAuditId}. Click Rollback again within 10s.`, '#92400e');
    }

    if (reviewRollbackBtn) {
        reviewRollbackBtn.disabled = !selectableIsLatestUnapplied;
    }

    if (reviewAuditTargetHintEl) {
        if (!latestUnrolled) {
            reviewAuditTargetHintEl.textContent = 'All apply entries are already rolled back.';
        } else if (selectableIsLatestUnapplied) {
            reviewAuditTargetHintEl.textContent = 'Selected target is the latest unapplied entry and can be rolled back.';
        } else {
            reviewAuditTargetHintEl.textContent = `Selected entry cannot be rolled back now. Latest unapplied audit_id: ${latestUnrolled.audit_id}`;
        }
    }

    if (!rollbackArmedValid) {
        const runTxt = selected?.run_id || '-';
        const atTxt = selected?.created_at || '-';
        _setRollbackConfirmText(`Selected rollback target: run ${runTxt} at ${atTxt}. Click Rollback to arm confirmation.`, '#64748b');
    }
}

async function _refreshApplyAuditDiagnostics() {
    applyAuditDiagnosticsLoading = true;
    applyAuditDiagnosticsError = null;
    _renderApplyAuditDiagnostics();

    try {
        const result = await callbacks.onGetApplyAuditDiagnostics();
        applyAuditDiagnostics = result || null;
        return result;
    } catch (error) {
        // Diagnostics are informational; don't block core audit flow.
        applyAuditDiagnosticsError = error?.message || String(error);
        return null;
    } finally {
        applyAuditDiagnosticsLoading = false;
        _renderApplyAuditDiagnostics();
    }
}

async function _refreshApplyAuditHistory() {
    applyAuditHistoryLoading = true;
    applyAuditHistoryError = null;
    _renderApplyAuditPanel();

    try {
        const result = await callbacks.onGetApplyAuditHistory(20);
        applyAuditHistory = Array.isArray(result?.audits) ? result.audits : [];
        if (result?.project_scope_id) {
            applyAuditDiagnostics = {
                ...(applyAuditDiagnostics || {}),
                project_scope_id: result.project_scope_id,
                scope_entry_count: Number(result?.count ?? applyAuditHistory.length),
            };
        }
        await _refreshApplyAuditDiagnostics();
        return result;
    } catch (error) {
        applyAuditHistoryError = error?.message || String(error);
        _showNotice(applyAuditHistoryError, 'error', 7000);
        return null;
    } finally {
        applyAuditHistoryLoading = false;
        _renderApplyAuditPanel();
    }
}

async function _handleReviewAuditRefresh() {
    _setRunLifecycle('running', 'load_apply_audit', 'Refreshing apply audit history');
    const result = await _refreshApplyAuditHistory();
    if (result) {
        _showNotice('Apply audit history refreshed.', 'success', 2400);
        _setRunLifecycle('completed', 'load_apply_audit', `entries=${result?.count ?? (result?.audits?.length ?? 0)}`);
    } else {
        _setRunLifecycle('failed', 'load_apply_audit', 'refresh failed');
    }
}

async function _handleRollbackLastApply() {
    const selectedAuditId = reviewAuditTargetSelect?.value || null;
    if (!selectedAuditId) {
        _showNotice('No rollback target selected.', 'warning');
        return;
    }

    const now = Date.now();
    const armed = rollbackConfirmState.armed
        && rollbackConfirmState.auditId === selectedAuditId
        && rollbackConfirmState.expiresAtMs > now;

    if (!armed) {
        const selected = (applyAuditHistory || []).find(a => a.audit_id === selectedAuditId);
        const summary = `Confirm rollback for audit ${selectedAuditId} (run ${selected?.run_id || '-'}, at ${selected?.created_at || '-'}).`;
        _armRollbackConfirmation(selectedAuditId, summary);
        _showNotice('Rollback confirmation armed for 10s. Click Rollback again to confirm.', 'warning', 3200);
        return;
    }

    _setRunLifecycle('running', 'rollback_last_apply', `target_audit_id=${selectedAuditId || '-'}`);
    try {
        const result = await callbacks.onRollbackLastApply(selectedAuditId);
        runOutput.value = JSON.stringify(result, null, 2);
        _showNotice('Rollback completed.', 'success', 3000);

        if (Array.isArray(result?.apply_audits)) {
            applyAuditHistory = result.apply_audits;
            applyAuditHistoryError = null;
            if (result?.project_scope_id) {
                applyAuditDiagnostics = {
                    ...(applyAuditDiagnostics || {}),
                    project_scope_id: result.project_scope_id,
                    scope_entry_count: Number(result.apply_audits.length),
                };
            }
            await _refreshApplyAuditDiagnostics();
        } else {
            await _refreshApplyAuditHistory();
        }

        _clearReviewToken();
        lastVerificationResult = null;
        _resetRollbackConfirmation();
        _updateRunReviewPanel();
        _renderApplyAuditPanel();
        _setRunLifecycle('completed', 'rollback_last_apply', `audit_id=${selectedAuditId || '-'}`);
    } catch (error) {
        runOutput.value = JSON.stringify(error?.data || { success: false, error: error?.message || String(error) }, null, 2);
        _showNotice(error?.message || String(error), 'error', 7000);
        _setRunLifecycle('failed', 'rollback_last_apply', error?.message || String(error));
    }
}

function _renderOptimizerSummary() {
    if (!summaryStatusEl) return;

    const isOptimizerRun = !!lastRunResult && Array.isArray(lastRunResult.candidates);
    if (!lastRunResult || !isOptimizerRun) {
        summaryStatusEl.textContent = 'No optimizer run yet';
        summaryMethodEl.textContent = '-';
        summaryStopReasonEl.textContent = '-';
        summaryEvalsEl.textContent = '-';
        summaryObjectiveEl.textContent = '-';
        summaryBestScoreEl.textContent = '-';
        _updateRunReviewPanel();
        _renderRunTimelineCard();
        return;
    }

    const objective = lastRunResult.objective || {};
    const bestRun = lastRunResult.best_run || {};

    summaryStatusEl.textContent = 'Completed';
    summaryMethodEl.textContent = lastRunResult.method || '-';
    summaryStopReasonEl.textContent = lastRunResult.stop_reason || '-';
    summaryEvalsEl.textContent = String(lastRunResult.evaluations_used ?? lastRunResult.candidates.length ?? '-');
    summaryObjectiveEl.textContent = `${objective.name || '-'} (${objective.direction || '-'})`;

    const bestScore = bestRun.optimizer_score;
    summaryBestScoreEl.textContent = Number.isFinite(Number(bestScore)) ? Number(bestScore).toFixed(6) : '-';
    _updateRunReviewPanel();
    _renderRunTimelineCard();
}

function _formatMaybeNumber(value, digits = 6) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits) : 'n/a';
}

function _toFiniteNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
}

function _formatValueWithDelta(value, bestValue, digits = 5) {
    const n = _toFiniteNumber(value);
    const b = _toFiniteNumber(bestValue);

    if (n != null) {
        const base = n.toFixed(digits);
        if (b != null) {
            const d = n - b;
            const sign = d >= 0 ? '+' : '';
            return `${base} (Δ${sign}${d.toFixed(digits)})`;
        }
        return base;
    }

    if (value === null || value === undefined || value === '') return '-';
    return String(value);
}

function _rankRunsForObjective(runs, objectiveName, direction = 'maximize') {
    const scored = (runs || []).map(r => {
        const val = objectiveName ? (r.objectives || {})[objectiveName] : null;
        const numeric = Number(val);
        return {
            run: r,
            objective: Number.isFinite(numeric) ? numeric : null,
        };
    });

    scored.sort((a, b) => {
        const av = a.objective;
        const bv = b.objective;
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return direction === 'minimize' ? av - bv : bv - av;
    });

    return scored;
}

function _renderCandidateDecomposition(scored, objectiveName) {
    if (!decompositionTableBody) return;
    decompositionTableBody.innerHTML = '';

    if (!Array.isArray(scored) || scored.length === 0) {
        decompositionTableBody.innerHTML = '<tr><td colspan="5" style="color:#64748b; padding:6px;">Run optimizer to populate decomposition.</td></tr>';
        return;
    }

    const top = scored.slice(0, 8);
    top.forEach((item, idx) => {
        const r = item.run || {};
        const objectives = r.objectives || {};

        const objectiveTerms = Object.entries(objectives)
            .sort((a, b) => a[0].localeCompare(b[0]))
            .map(([k, v]) => `${k}=${_formatMaybeNumber(v, 5)}`)
            .join(', ');

        const selectionBits = [];
        if (r.proposal_source) selectionBits.push(`source=${r.proposal_source}`);
        if (Number.isFinite(Number(r.surrogate_pred_mean))) selectionBits.push(`μ=${_formatMaybeNumber(r.surrogate_pred_mean, 5)}`);
        if (Number.isFinite(Number(r.surrogate_pred_std))) selectionBits.push(`σ=${_formatMaybeNumber(r.surrogate_pred_std, 5)}`);
        if (Number.isFinite(Number(r.surrogate_acquisition))) selectionBits.push(`acq=${_formatMaybeNumber(r.surrogate_acquisition, 5)}`);
        if (Number.isFinite(Number(r.optimizer_score))) selectionBits.push(`optimizer_score=${_formatMaybeNumber(r.optimizer_score, 5)}`);

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="padding:4px; border-bottom:1px solid #e2e8f0;">${idx + 1}</td>
            <td style="padding:4px; border-bottom:1px solid #e2e8f0;">${r.run_index ?? '-'}</td>
            <td style="padding:4px; border-bottom:1px solid #e2e8f0;">${item.objective == null ? 'n/a' : _formatMaybeNumber(item.objective, 6)}</td>
            <td style="padding:4px; border-bottom:1px solid #e2e8f0;">${objectiveTerms || '(none)'}</td>
            <td style="padding:4px; border-bottom:1px solid #e2e8f0;">${selectionBits.join(' · ') || '-'}</td>
        `;
        decompositionTableBody.appendChild(tr);
    });
}

function _renderCandidateCompare(scored, objectiveName, direction) {
    if (!compareTableWrap) return;

    const topN = Math.max(2, Math.min(5, Number(compareTopNSelect?.value || 3)));
    const top = Array.isArray(scored) ? scored.slice(0, topN) : [];

    if (top.length < 2) {
        compareTableWrap.innerHTML = '<div style="padding:6px; color:#64748b;">Need at least 2 ranked candidates to compare.</div>';
        return;
    }

    const best = top[0];
    const bestRun = best.run || {};
    const bestObjectives = bestRun.objectives || {};
    const bestValues = bestRun.values || {};

    const objKeys = new Set();
    const paramKeys = new Set();
    top.forEach(item => {
        const r = item.run || {};
        Object.keys(r.objectives || {}).forEach(k => objKeys.add(k));
        Object.keys(r.values || {}).forEach(k => paramKeys.add(k));
    });

    const objList = [...objKeys].sort((a, b) => a.localeCompare(b));
    const paramList = [...paramKeys].sort((a, b) => a.localeCompare(b));

    const header = top.map((item, idx) => {
        const r = item.run || {};
        return `<th style="text-align:left; padding:6px; border-bottom:1px solid #e2e8f0;">#${idx + 1} (run ${r.run_index ?? '-'})</th>`;
    }).join('');

    const rows = [];

    const pushRow = (label, getter, bestGetter = getter) => {
        const bestVal = bestGetter(bestRun, best);
        const tds = top.map(item => {
            const r = item.run || {};
            const v = getter(r, item);
            return `<td style="padding:6px; border-bottom:1px solid #f1f5f9;">${_formatValueWithDelta(v, bestVal)}</td>`;
        }).join('');
        rows.push(`<tr><td style="padding:6px; border-bottom:1px solid #f1f5f9; font-weight:600; color:#0f172a;">${label}</td>${tds}</tr>`);
    };

    pushRow(`score [${objectiveName || '-'} | ${direction}]`, (r, item) => item.objective, (_r, item) => item.objective);
    pushRow('optimizer_score', (r) => r.optimizer_score, (r) => r.optimizer_score);

    rows.push(`<tr><td colspan="${top.length + 1}" style="padding:4px 6px; font-weight:700; color:#334155; background:#f8fafc; border-top:1px solid #e2e8f0;">Objective terms</td></tr>`);
    objList.forEach(k => {
        pushRow(k, (r) => (r.objectives || {})[k], (r) => (bestObjectives || {})[k]);
    });

    rows.push(`<tr><td colspan="${top.length + 1}" style="padding:4px 6px; font-weight:700; color:#334155; background:#f8fafc; border-top:1px solid #e2e8f0;">Parameter values</td></tr>`);
    paramList.forEach(k => {
        pushRow(k, (r) => (r.values || {})[k], (r) => (bestValues || {})[k]);
    });

    pushRow('success_flag', (r) => (r.success ? 1 : 0), (r) => (r.success ? 1 : 0));

    const sourceCells = top.map(item => {
        const r = item.run || {};
        const txt = r.proposal_source || (lastRunResult?.method || '-');
        const bestTxt = bestRun.proposal_source || (lastRunResult?.method || '-');
        const delta = txt === bestTxt ? '(Δsame)' : '(Δdiff)';
        return `<td style="padding:6px; border-bottom:1px solid #f1f5f9;">${txt} ${delta}</td>`;
    }).join('');
    rows.push(`<tr><td style="padding:6px; border-bottom:1px solid #f1f5f9; font-weight:600; color:#0f172a;">proposal_source</td>${sourceCells}</tr>`);

    compareTableWrap.innerHTML = `
        <table style="width:100%; border-collapse:collapse; font-size:12px; min-width:${Math.max(520, 240 + top.length * 220)}px;">
            <thead>
                <tr>
                    <th style="text-align:left; padding:6px; border-bottom:1px solid #e2e8f0; width:220px;">Metric</th>
                    ${header}
                </tr>
            </thead>
            <tbody>
                ${rows.join('')}
            </tbody>
        </table>
    `;
}

function _renderWhySelected(scored, objectiveName, direction) {
    if (!whySelectedSummaryEl || !whySelectedDetailsEl) return;

    if (!Array.isArray(scored) || scored.length === 0) {
        whySelectedSummaryEl.textContent = 'No optimizer selection yet.';
        whySelectedDetailsEl.value = '';
        return;
    }

    const best = scored[0]?.run || {};
    const method = lastRunResult?.method || '-';
    const objectiveValue = scored[0]?.objective;
    const status = best.success ? 'successful' : 'failed';

    let summary = `Best candidate is run ${best.run_index ?? '-'} (${status}) for objective '${objectiveName || '-'}' (${direction}).`;
    if (objectiveValue != null) {
        summary += ` Value=${_formatMaybeNumber(objectiveValue, 6)}.`;
    }
    whySelectedSummaryEl.textContent = summary;

    const detail = {
        method,
        objective: {
            name: objectiveName,
            direction,
            value: objectiveValue,
        },
        run_index: best.run_index,
        proposal_source: best.proposal_source || null,
        surrogate_prediction: {
            mean: best.surrogate_pred_mean ?? null,
            std: best.surrogate_pred_std ?? null,
            acquisition: best.surrogate_acquisition ?? null,
        },
        optimizer_score: best.optimizer_score ?? null,
        values: best.values || {},
        objectives: best.objectives || {},
        success: !!best.success,
        error: best.error || null,
        rationale: (() => {
            const bits = [];
            if (best.proposal_source) bits.push(`candidate proposed via ${best.proposal_source}`);
            if (Number.isFinite(Number(best.surrogate_pred_mean)) && Number.isFinite(Number(best.surrogate_pred_std))) {
                bits.push(`surrogate predicted μ=${_formatMaybeNumber(best.surrogate_pred_mean, 5)}, σ=${_formatMaybeNumber(best.surrogate_pred_std, 5)}`);
            }
            bits.push(`selected by ranking top ${direction} on '${objectiveName || '-'}'`);
            return bits;
        })(),
    };

    whySelectedDetailsEl.value = JSON.stringify(detail, null, 2);
}

function _normalizeFailureMessage(msg) {
    const text = String(msg || '').trim();
    if (!text) return 'Unknown failure';

    const lowered = text.toLowerCase();
    if (lowered.includes('simulation evaluator')) return 'Simulation evaluator failure';
    if (lowered.includes('macro') && lowered.includes('failed')) return 'Macro generation failure';
    if (lowered.includes('output.hdf5') && lowered.includes('not found')) return 'Simulation produced no output file';
    if (lowered.includes('geometry') && lowered.includes('not found')) return 'Invalid geometry reference';
    if (lowered.includes('not found in registry')) return 'Parameter registry mismatch';
    if (lowered.includes('invalid') && lowered.includes('parameter')) return 'Invalid parameter value';
    if (lowered.includes('preflight')) return 'Preflight failure';

    return text.length > 120 ? `${text.slice(0, 117)}...` : text;
}

function _failureHintsFromGroups(groups, failedRuns) {
    const hints = [];
    if (failedRuns <= 0) return hints;

    const total = Math.max(1, failedRuns);
    const hasNoOutput = groups.some(g => g.key === 'Simulation produced no output file');
    const hasEval = groups.some(g => g.key === 'Simulation evaluator failure');
    const hasRegistry = groups.some(g => g.key === 'Parameter registry mismatch');
    const hasGeometryRef = groups.some(g => g.key === 'Invalid geometry reference');

    if (hasNoOutput) {
        hints.push('Enable save_hits/save_particles and ensure event count is high enough to produce output.hdf5 consistently.');
    }
    if (hasEval) {
        hints.push('Inspect simulation evaluator errors; verify sim_objectives dataset paths and context keys.');
    }
    if (hasRegistry || hasGeometryRef) {
        hints.push('Re-check parameter registry targets and geometry/source references before rerunning optimization.');
    }

    const top = groups[0];
    if (top && (top.count / total) > 0.4) {
        hints.push(`Most failures are '${top.key}'. Prioritize fixing this class first.`);
    }

    if (groups.length >= 3) {
        hints.push('Failure modes are diverse; try reducing search bounds or adding stronger parameter constraints.');
    }

    if (hints.length === 0) {
        hints.push('Review top failure messages and tighten bounds/constraints for unstable regions.');
    }

    return [...new Set(hints)];
}

function _renderFailureDiagnostics(runs) {
    if (!failureCountEl || !failureGroupsEl || !failureHintsEl || !failureGroupsCountEl) return;

    const allRuns = Array.isArray(runs) ? runs : [];
    const failed = allRuns.filter(r => !r?.success);

    failureCountEl.textContent = String(failed.length);

    if (failed.length === 0) {
        failureGroupsCountEl.textContent = '0';
        failureGroupsEl.textContent = 'No failure groups yet.';
        failureHintsEl.innerHTML = '<li style="color:#64748b;">No hints yet.</li>';
        return;
    }

    const grouped = new Map();
    failed.forEach(r => {
        const key = _normalizeFailureMessage(r?.error || 'Unknown failure');
        if (!grouped.has(key)) grouped.set(key, { key, count: 0, examples: [] });
        const g = grouped.get(key);
        g.count += 1;
        if (g.examples.length < 2) {
            g.examples.push({
                run_index: r?.run_index,
                error: String(r?.error || ''),
            });
        }
    });

    const groups = [...grouped.values()].sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
    failureGroupsCountEl.textContent = String(groups.length);

    failureGroupsEl.innerHTML = groups.map(g => {
        const examples = g.examples.map(ex => `run ${ex.run_index ?? '-'}: ${ex.error || '(no details)'}`).join(' · ');
        return `<div style="margin-bottom:6px;"><b>${g.key}</b> — ${g.count} runs<br><span style="color:#64748b;">${examples}</span></div>`;
    }).join('');

    const hints = _failureHintsFromGroups(groups, failed.length);
    failureHintsEl.innerHTML = '';
    hints.forEach(h => {
        const li = document.createElement('li');
        li.textContent = h;
        failureHintsEl.appendChild(li);
    });
}

function _renderRankingTable() {
    if (!rankingTableBody) return;

    const runs = _extractRunsFromLastResult();
    rankingTableBody.innerHTML = '';

    if (runs.length === 0) {
        rankingTableBody.innerHTML = '<tr><td colspan="5" style="color:#64748b;">Run a study to populate ranking results.</td></tr>';
        _renderCandidateDecomposition([], '', 'maximize');
        _renderCandidateCompare([], '', 'maximize');
        _renderWhySelected([], '', 'maximize');
        _renderFailureDiagnostics([]);
        return;
    }

    const objectiveName = rankObjectiveSelect?.value || '';
    const direction = rankDirectionSelect?.value || 'maximize';

    const scored = _rankRunsForObjective(runs, objectiveName, direction);

    scored.forEach((item, idx) => {
        const r = item.run;
        const tr = document.createElement('tr');
        const paramsStr = Object.entries(r.values || {}).map(([k, v]) => `${k}=${_formatMaybeNumber(v, 4)}`).join(', ');
        tr.innerHTML = `
            <td>${idx + 1}</td>
            <td>${r.run_index}</td>
            <td>${item.objective == null ? 'n/a' : _formatMaybeNumber(item.objective, 6)}</td>
            <td>${r.success ? 'yes' : 'no'}</td>
            <td>${paramsStr}</td>
        `;
        rankingTableBody.appendChild(tr);
    });

    _renderCandidateDecomposition(scored, objectiveName);
    _renderCandidateCompare(scored, objectiveName, direction);
    _renderWhySelected(scored, objectiveName, direction);
    _renderFailureDiagnostics(runs);
}

function _updateObjectiveSelector() {
    if (!rankObjectiveSelect) return;
    rankObjectiveSelect.innerHTML = '';

    const runs = _extractRunsFromLastResult();
    const names = new Set();
    for (const r of runs) {
        Object.keys(r.objectives || {}).forEach(k => names.add(k));
    }

    if (names.size === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'no objectives';
        rankObjectiveSelect.appendChild(opt);
        rankObjectiveSelect.disabled = true;
    } else {
        rankObjectiveSelect.disabled = false;
        [...names].sort().forEach(name => {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            rankObjectiveSelect.appendChild(opt);
        });
    }
}

async function _refreshAndRender() {
    const studies = await callbacks.onRefresh();
    _renderTable(studies || {});
}

async function _handleSave() {
    try {
        const payload = _studyFromForm();
        await callbacks.onSave(payload);
        activeName = payload.name;
        await _refreshAndRender();
    } catch (error) {
        _showNotice(error.message || String(error), 'error', 7000);
    }
}

async function _handleDelete() {
    const name = nameInput.value.trim() || activeName;
    if (!name) return;
    await callbacks.onDelete(name);
    activeName = null;
    _setForm();
    await _refreshAndRender();
}

async function _handleRun() {
    const name = nameInput.value.trim() || activeName;
    if (!name) return;

    const maxRunsRaw = maxRunsInput.value.trim();
    const maxRuns = maxRunsRaw ? Number(maxRunsRaw) : null;

    _setRunLifecycle('running', 'param_study_run', `study=${name}`);

    try {
        const result = await callbacks.onRun(name, Number.isFinite(maxRuns) ? maxRuns : null);
        lastRunResult = result || null;
        lastVerificationResult = null;
        _clearReviewToken();
        runOutput.value = JSON.stringify(result, null, 2);
        _updateObjectiveSelector();
        _renderRankingTable();
        _renderOptimizerSummary();

        const runsCount = Array.isArray(result?.runs) ? result.runs.length : 0;
        const stopReason = result?.stop_reason;
        const detail = stopReason && stopReason !== 'completed'
            ? `runs=${runsCount}, stop_reason=${stopReason}`
            : `runs=${runsCount}`;
        _setRunLifecycle('completed', 'param_study_run', detail);
    } catch (error) {
        runOutput.value = JSON.stringify(error?.data || { success: false, error: error?.message || String(error) }, null, 2);
        _setRunLifecycle('failed', 'param_study_run', error?.message || String(error));
        _showNotice(error?.message || String(error), 'error', 7000);
    }
}

async function _handleRunOptimizer() {
    const studyName = nameInput.value.trim() || activeName;
    if (!studyName) return;

    const objectiveName = rankObjectiveSelect?.value || null;
    const direction = rankDirectionSelect?.value || 'maximize';
    const method = optMethodInput?.value || 'random_search';
    const budget = Number(optBudgetInput?.value || 20);
    const seed = Number(optSeedInput?.value || 42);

    const cmaes = {};
    const popSize = Number(optPopSizeInput?.value);
    const sigmaRel = Number(optSigmaRelInput?.value);
    const stag = Number(optStagInput?.value);
    if (Number.isFinite(popSize) && popSize > 1) cmaes.population_size = popSize;
    if (Number.isFinite(sigmaRel) && sigmaRel > 0) cmaes.sigma_rel = sigmaRel;
    if (Number.isFinite(stag) && stag >= 1) cmaes.stagnation_generations = stag;

    const payload = {
        study_name: studyName,
        method,
        budget: Number.isFinite(budget) ? budget : 20,
        seed: Number.isFinite(seed) ? seed : 42,
        objective_name: objectiveName,
        direction,
    };
    if (method === 'cmaes') payload.cmaes = cmaes;

    _setRunLifecycle('running', 'optimizer_run', `method=${method}, study=${studyName}`);

    try {
        const result = await callbacks.onRunOptimizer(payload);

        lastRunResult = result || null;
        lastVerificationResult = null;
        _clearReviewToken();
        runOutput.value = JSON.stringify(result, null, 2);
        _updateObjectiveSelector();
        if (objectiveName) rankObjectiveSelect.value = objectiveName;
        if (direction) rankDirectionSelect.value = direction;
        _renderRankingTable();
        _renderOptimizerSummary();

        const evals = Number(result?.evaluations_used ?? result?.candidates?.length ?? 0);
        const stopReason = result?.stop_reason;
        const detail = stopReason && stopReason !== 'budget_exhausted'
            ? `evaluations=${Number.isFinite(evals) ? evals : 'n/a'}, stop_reason=${stopReason}`
            : `evaluations=${Number.isFinite(evals) ? evals : 'n/a'}`;
        _setRunLifecycle('completed', 'optimizer_run', detail);
    } catch (error) {
        runOutput.value = JSON.stringify(error?.data || { success: false, error: error?.message || String(error) }, null, 2);
        _setRunLifecycle('failed', 'optimizer_run', error?.message || String(error));
        _showNotice(error?.message || String(error), 'error', 7000);
    }
}

async function _handleStopActiveRun() {
    if (runLifecycleState.status !== 'running') {
        _showNotice('No active run to stop.', 'warning', 2200);
        return;
    }
    if (stopRunRequestPending) return;

    stopRunRequestPending = true;
    _updateStopRunButtonState();
    try {
        const result = await callbacks.onStopActiveRun('user_requested_stop');
        runOutput.value = JSON.stringify(result, null, 2);
        if (result?.active && result?.stop_requested) {
            _showNotice('Stop requested. Current candidate will finish before the run exits.', 'warning', 4200);
        } else {
            _showNotice('No active run was found to stop.', 'warning', 3000);
        }
    } catch (error) {
        _showNotice(error?.message || String(error), 'error', 7000);
    } finally {
        stopRunRequestPending = false;
        _updateStopRunButtonState();
    }
}

async function _handleReplayBest() {
    const runId = _getOptimizerRunIdFromLastResult();
    if (!runId) {
        _showNotice('No optimizer run selected yet. Run optimizer first.', 'warning');
        return;
    }

    if (!currentApplyToken) {
        _showNotice('Apply is blocked. Run Verify Best to issue a token first.', 'warning');
        return;
    }

    const now = Date.now();
    const armed = applyConfirmState.armed
        && applyConfirmState.runId === runId
        && applyConfirmState.token === currentApplyToken
        && applyConfirmState.expiresAtMs > now;

    if (!armed) {
        const gate = lastVerificationResult?.verification_gate || {};
        const summary = `Confirm apply for run ${runId}. Gate passed=${!!gate.passed}, success_rate=${_formatMaybeNumber(gate.success_rate, 3)}, std=${_formatMaybeNumber(gate.stats_std, 5)}.`;
        _armApplyConfirmation(runId, currentApplyToken, summary);
        _showNotice('Apply confirmation armed for 10s. Click Apply again to confirm.', 'warning', 3200);
        return;
    }

    _setRunLifecycle('running', 'apply_best', `run_id=${runId}`);

    try {
        const result = await callbacks.onReplayBest(runId, {
            applyToProject: true,
            allowApply: true,
            verificationToken: currentApplyToken,
        });
        runOutput.value = JSON.stringify(result, null, 2);
        _showNotice('Best candidate applied successfully.', 'success', 3000);
        _clearReviewToken();
        _updateRunReviewPanel();
        if (Array.isArray(result?.apply_audits)) {
            applyAuditHistory = result.apply_audits;
            applyAuditHistoryError = null;
            if (result?.project_scope_id) {
                applyAuditDiagnostics = {
                    ...(applyAuditDiagnostics || {}),
                    project_scope_id: result.project_scope_id,
                    scope_entry_count: Number(result.apply_audits.length),
                };
            }
            await _refreshApplyAuditDiagnostics();
            _renderApplyAuditPanel();
        } else {
            await _refreshApplyAuditHistory();
        }
        _setRunLifecycle('completed', 'apply_best', `run_id=${runId}`);
    } catch (error) {
        runOutput.value = JSON.stringify(error?.data || { success: false, error: error?.message || String(error) }, null, 2);
        _showNotice(error?.message || String(error), 'error', 7000);
        _setRunLifecycle('failed', 'apply_best', error?.message || String(error));
    }
}

async function _handleVerifyBest() {
    const runId = _getOptimizerRunIdFromLastResult();
    if (!runId) {
        _showNotice('No optimizer run selected yet. Run optimizer first.', 'warning');
        return;
    }

    const repeats = Number(verifyRepeatsInput?.value || 3);
    const safeRepeats = Number.isFinite(repeats) && repeats > 0 ? repeats : 3;

    const minSuccessRateRaw = Number(verifyMinSuccessRateInput?.value);
    const minSuccessRate = Number.isFinite(minSuccessRateRaw) ? Math.max(0, Math.min(1, minSuccessRateRaw)) : 1.0;

    const maxStdRaw = verifyMaxStdInput?.value?.trim?.() || '';
    const maxStdNum = Number(maxStdRaw);
    const maxStd = maxStdRaw !== '' && Number.isFinite(maxStdNum) ? maxStdNum : null;

    _setRunLifecycle('running', 'verify_best', `run_id=${runId}, repeats=${safeRepeats}`);

    try {
        const result = await callbacks.onVerifyBest(runId, {
            repeats: safeRepeats,
            minRepeats: safeRepeats,
            minSuccessRate,
            maxStd,
        });

        runOutput.value = JSON.stringify(result, null, 2);
        lastVerificationResult = result || null;
        currentApplyToken = result?.apply_token || null;
        const expiresAtSec = Number(result?.apply_token_record?.expires_at);
        currentApplyTokenExpiresAtMs = Number.isFinite(expiresAtSec) ? expiresAtSec * 1000 : null;

        const stats = result?.verification_result?.verification_record?.stats;
        if (stats && summaryStatusEl) {
            summaryStatusEl.textContent = `Verified (${stats.count} runs)`;
            if (summaryBestScoreEl && Number.isFinite(Number(stats.mean))) {
                summaryBestScoreEl.textContent = `${Number(stats.mean).toFixed(6)} ± ${Number(stats.std || 0).toFixed(6)}`;
            }
        }

        if (result?.verification_gate?.passed) {
            _showNotice('Verification gate passed. Apply token issued.', 'success', 3200);
            _setRunLifecycle('completed', 'verify_best', 'gate=passed');
        } else {
            _showNotice('Verification gate did not pass. Apply token not issued.', 'warning', 4200);
            _setRunLifecycle('completed', 'verify_best', 'gate=failed');
        }

        _updateRunReviewPanel();
    } catch (error) {
        runOutput.value = JSON.stringify(error?.data || { success: false, error: error?.message || String(error) }, null, 2);
        _showNotice(error?.message || String(error), 'error', 7000);
        _setRunLifecycle('failed', 'verify_best', error?.message || String(error));
    }
}

async function _handleCopyReviewToken() {
    if (!currentApplyToken) {
        _showNotice('No verification token available. Verify best candidate first.', 'warning');
        return;
    }
    await _copyTextToClipboard(currentApplyToken);
}

function _handleDownloadResults() {
    if (!lastRunResult) {
        _showNotice('No run result to download yet.', 'warning');
        return;
    }
    const studyName = (nameInput?.value || activeName || 'study').trim() || 'study';
    const kind = Array.isArray(lastRunResult?.candidates) ? 'optimizer' : 'sweep';
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `${studyName}_${kind}_results_${ts}.json`;

    const blob = new Blob([JSON.stringify(lastRunResult, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

export function init(newCallbacks = {}) {
    callbacks = { ...callbacks, ...newCallbacks };

    modal = document.getElementById('paramStudiesModal');
    noticeEl = document.getElementById('psNotice');
    tableBody = document.getElementById('paramStudiesTableBody');

    nameInput = document.getElementById('ps_name');
    modeInput = document.getElementById('ps_mode');
    paramsInput = document.getElementById('ps_parameters');
    legacyObjectivesToggleInput = document.getElementById('ps_show_legacy_objectives');
    legacyObjectivesRow = document.getElementById('psLegacyObjectivesRow');
    objectivesInput = document.getElementById('ps_objectives');
    gridStepsInput = document.getElementById('ps_grid_steps');
    samplesInput = document.getElementById('ps_samples');
    seedInput = document.getElementById('ps_seed');
    maxRunsInput = document.getElementById('ps_max_runs');
    runOutput = document.getElementById('ps_run_output');
    rankObjectiveSelect = document.getElementById('ps_rank_objective');
    rankDirectionSelect = document.getElementById('ps_rank_direction');
    rankingTableBody = document.getElementById('psRankingTableBody');
    decompositionTableBody = document.getElementById('psDecompositionTableBody');
    compareTopNSelect = document.getElementById('psCompareTopN');
    compareRefreshBtn = document.getElementById('psCompareRefreshBtn');
    compareTableWrap = document.getElementById('psCompareTableWrap');
    whySelectedSummaryEl = document.getElementById('psWhySelectedSummary');
    whySelectedDetailsEl = document.getElementById('psWhySelectedDetails');
    failureCountEl = document.getElementById('psFailureCount');
    failureGroupsCountEl = document.getElementById('psFailureGroupsCount');
    failureGroupsEl = document.getElementById('psFailureGroups');
    failureHintsEl = document.getElementById('psFailureHints');
    optMethodInput = document.getElementById('ps_opt_method');
    optBudgetInput = document.getElementById('ps_opt_budget');
    optSeedInput = document.getElementById('ps_opt_seed');
    optPopSizeInput = document.getElementById('ps_opt_popsize');
    optSigmaRelInput = document.getElementById('ps_opt_sigma_rel');
    optStagInput = document.getElementById('ps_opt_stag');
    verifyRepeatsInput = document.getElementById('ps_verify_repeats');
    verifyMinSuccessRateInput = document.getElementById('ps_verify_min_success_rate');
    verifyMaxStdInput = document.getElementById('ps_verify_max_std');

    reviewRunIdEl = document.getElementById('psReviewRunId');
    reviewGateStatusEl = document.getElementById('psReviewGateStatus');
    reviewTokenStatusEl = document.getElementById('psReviewTokenStatus');
    reviewApplyReadyEl = document.getElementById('psReviewApplyReady');
    reviewTokenInput = document.getElementById('psReviewToken');
    reviewApplyConfirmTextEl = document.getElementById('psReviewApplyConfirmText');
    reviewGateReasonsInput = document.getElementById('psReviewGateReasons');
    reviewVerifyBtn = document.getElementById('psReviewVerifyBtn');
    reviewApplyBtn = document.getElementById('psReviewApplyBtn');
    reviewCopyTokenBtn = document.getElementById('psReviewCopyTokenBtn');
    reviewAuditRefreshBtn = document.getElementById('psReviewAuditRefreshBtn');
    reviewRollbackBtn = document.getElementById('psReviewRollbackBtn');
    reviewAuditSummaryEl = document.getElementById('psReviewAuditSummary');
    reviewAuditDiagnosticsEl = document.getElementById('psReviewAuditDiagnostics');
    reviewAuditDetailsInput = document.getElementById('psReviewAuditDetails');
    reviewAuditTargetSelect = document.getElementById('psReviewAuditTarget');
    reviewAuditTargetHintEl = document.getElementById('psReviewAuditTargetHint');
    reviewRollbackConfirmTextEl = document.getElementById('psReviewRollbackConfirmText');
    reviewAuditTableBody = document.getElementById('psReviewAuditTableBody');

    obTemplateInput = document.getElementById('ps_ob_template');
    obDatasetPathInput = document.getElementById('ps_ob_dataset_path');
    obDatasetHintEl = document.getElementById('psObDatasetHint');
    obCostKeyInput = document.getElementById('ps_ob_cost_key');
    obScoreExprInput = document.getElementById('ps_ob_score_expr');
    obAllowedFunctionsEl = document.getElementById('psObAllowedFunctions');
    obFormulaVarsEl = document.getElementById('psObFormulaVars');
    obPolicyCapsEl = document.getElementById('psObPolicyCaps');
    obOutput = document.getElementById('ps_ob_output');
    obLoadExampleBtn = document.getElementById('psObLoadExampleBtn');
    obValidateBtn = document.getElementById('psObValidateBtn');
    obBuildBtn = document.getElementById('psObBuildBtn');
    obUpsertBtn = document.getElementById('psObUpsertBtn');
    obLaunchDryRunBtn = document.getElementById('psObLaunchDryRunBtn');
    obGuidedBtn = document.getElementById('psObGuidedBtn');
    obCopyOutputBtn = document.getElementById('psObCopyOutputBtn');
    obCopyBuildBtn = document.getElementById('psObCopyBuildBtn');
    obCopyLaunchBtn = document.getElementById('psObCopyLaunchBtn');

    obStatusEl = document.getElementById('psObStatus');
    obStageEl = document.getElementById('psObStage');
    obErrorsList = document.getElementById('psObErrors');
    obWarningsList = document.getElementById('psObWarnings');

    summaryStatusEl = document.getElementById('psSummaryStatus');
    summaryMethodEl = document.getElementById('psSummaryMethod');
    summaryStopReasonEl = document.getElementById('psSummaryStopReason');
    summaryEvalsEl = document.getElementById('psSummaryEvals');
    summaryObjectiveEl = document.getElementById('psSummaryObjective');
    summaryBestScoreEl = document.getElementById('psSummaryBestScore');

    runStatusEl = document.getElementById('psRunStatus');
    runActionEl = document.getElementById('psRunAction');
    runElapsedEl = document.getElementById('psRunElapsed');
    runBudgetUsedEl = document.getElementById('psRunBudgetUsed');
    runSuccessFailureEl = document.getElementById('psRunSuccessFailure');
    runLastUpdateEl = document.getElementById('psRunLastUpdate');
    runTimelineListEl = document.getElementById('psRunTimelineList');

    saveBtn = document.getElementById('psSaveBtn');
    deleteBtn = document.getElementById('psDeleteBtn');
    runBtn = document.getElementById('psRunBtn');
    runOptimizerBtn = document.getElementById('psRunOptimizerBtn');
    stopRunBtn = document.getElementById('psStopRunBtn');
    replayBestBtn = document.getElementById('psReplayBestBtn');
    verifyBestBtn = document.getElementById('psVerifyBestBtn');
    downloadResultsBtn = document.getElementById('psDownloadResultsBtn');
    refreshBtn = document.getElementById('psRefreshBtn');
    cancelBtn = document.getElementById('psCancelBtn');

    saveBtn.addEventListener('click', _handleSave);
    deleteBtn.addEventListener('click', _handleDelete);
    runBtn.addEventListener('click', _handleRun);
    if (runOptimizerBtn) runOptimizerBtn.addEventListener('click', _handleRunOptimizer);
    if (stopRunBtn) stopRunBtn.addEventListener('click', _handleStopActiveRun);
    if (replayBestBtn) replayBestBtn.addEventListener('click', _handleReplayBest);
    if (verifyBestBtn) verifyBestBtn.addEventListener('click', _handleVerifyBest);
    if (reviewVerifyBtn) reviewVerifyBtn.addEventListener('click', _handleVerifyBest);
    if (reviewApplyBtn) reviewApplyBtn.addEventListener('click', _handleReplayBest);
    if (reviewCopyTokenBtn) reviewCopyTokenBtn.addEventListener('click', _handleCopyReviewToken);
    if (reviewAuditRefreshBtn) reviewAuditRefreshBtn.addEventListener('click', _handleReviewAuditRefresh);
    if (reviewRollbackBtn) reviewRollbackBtn.addEventListener('click', _handleRollbackLastApply);
    if (reviewAuditTargetSelect) reviewAuditTargetSelect.addEventListener('change', _renderApplyAuditPanel);
    if (downloadResultsBtn) downloadResultsBtn.addEventListener('click', _handleDownloadResults);
    refreshBtn.addEventListener('click', _refreshAndRender);
    cancelBtn.addEventListener('click', hide);
    if (rankObjectiveSelect) rankObjectiveSelect.addEventListener('change', _renderRankingTable);
    if (rankDirectionSelect) rankDirectionSelect.addEventListener('change', _renderRankingTable);
    if (compareTopNSelect) compareTopNSelect.addEventListener('change', _renderRankingTable);
    if (compareRefreshBtn) compareRefreshBtn.addEventListener('click', _renderRankingTable);

    if (legacyObjectivesToggleInput) {
        legacyObjectivesToggleInput.addEventListener('change', () => {
            _setLegacyObjectivesVisible(!!legacyObjectivesToggleInput.checked);
        });
    }

    if (paramsInput) paramsInput.addEventListener('input', _renderFormulaVariableHints);
    if (obCostKeyInput) obCostKeyInput.addEventListener('input', _renderFormulaVariableHints);
    if (obScoreExprInput) obScoreExprInput.addEventListener('input', _renderFormulaVariableHints);

    if (obLoadExampleBtn) obLoadExampleBtn.addEventListener('click', _handleObjectiveBuilderLoadExample);
    if (obValidateBtn) obValidateBtn.addEventListener('click', _handleObjectiveBuilderValidate);
    if (obBuildBtn) obBuildBtn.addEventListener('click', _handleObjectiveBuilderBuild);
    if (obUpsertBtn) obUpsertBtn.addEventListener('click', _handleObjectiveBuilderUpsert);
    if (obLaunchDryRunBtn) obLaunchDryRunBtn.addEventListener('click', _handleObjectiveBuilderLaunchDryRun);
    if (obGuidedBtn) obGuidedBtn.addEventListener('click', _handleObjectiveBuilderGuided);
    if (obCopyOutputBtn) obCopyOutputBtn.addEventListener('click', _handleCopyObjectiveBuilderOutput);
    if (obCopyBuildBtn) obCopyBuildBtn.addEventListener('click', _handleCopyObjectiveBuilderBuild);
    if (obCopyLaunchBtn) obCopyLaunchBtn.addEventListener('click', _handleCopyObjectiveBuilderLaunch);

    // Populate schema-driven UI hints/caps/templates.
    callbacks.onObjectiveBuilderSchema().then(schema => {
        _applyObjectiveBuilderSchemaToUI(schema || {});
    }).catch(() => {
        _applyObjectiveBuilderSchemaToUI(null);
    });
}

export async function show(initialStudies = {}) {
    activeName = null;
    lastRunResult = null;
    lastVerificationResult = null;
    _clearReviewToken();
    _resetRollbackConfirmation();
    lastObjectiveBuilderBuild = null;
    lastObjectiveBuilderLaunch = null;
    applyAuditHistory = [];
    applyAuditDiagnostics = null;
    applyAuditHistoryLoading = false;
    applyAuditHistoryError = null;
    applyAuditDiagnosticsLoading = false;
    applyAuditDiagnosticsError = null;
    runLifecycleState = {
        status: 'idle',
        action: '-',
        startedAtMs: null,
        endedAtMs: null,
        lastUpdateMs: Date.now(),
    };
    runTimelineEvents = [];
    stopRunRequestPending = false;
    _stopRunLifecycleTimer();

    _setForm();
    runOutput.value = '';
    if (obOutput) obOutput.value = '';
    _showNotice('', 'info', 0);
    _renderFormulaVariableHints();
    _renderObjectiveBuilderFeedback('idle', { success: true, validation: { errors: [], warnings: [] } });
    _renderApplyAuditPanel();
    _renderTable(initialStudies);
    _updateObjectiveSelector();
    _renderRankingTable();
    _renderOptimizerSummary();
    _renderRunTimelineCard();
    _updateStopRunButtonState();
    if (modal) modal.style.display = 'block';
    await _refreshAndRender();
    await _refreshApplyAuditHistory();
}

export function hide() {
    if (modal) modal.style.display = 'none';
    if (noticeTimer) {
        clearTimeout(noticeTimer);
        noticeTimer = null;
    }
    _stopRunLifecycleTimer();
    _stopTokenExpiryTimer();
    stopRunRequestPending = false;
    _updateStopRunButtonState();
    _resetApplyConfirmation();
    _resetRollbackConfirmation();
    _showNotice('', 'info', 0);
}
