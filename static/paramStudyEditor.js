let modal, tableBody;
let nameInput, modeInput, paramsInput, objectivesInput, gridStepsInput, samplesInput, seedInput, maxRunsInput, runOutput;
let rankObjectiveSelect, rankDirectionSelect, rankingTableBody;
let optMethodInput, optBudgetInput, optSeedInput, optPopSizeInput, optSigmaRelInput, optStagInput, verifyRepeatsInput;
let summaryStatusEl, summaryMethodEl, summaryStopReasonEl, summaryEvalsEl, summaryObjectiveEl, summaryBestScoreEl;
let saveBtn, deleteBtn, runBtn, runOptimizerBtn, replayBestBtn, verifyBestBtn, downloadResultsBtn, refreshBtn, cancelBtn;

const ALLOWED_OBJECTIVE_METRICS = new Set([
    'success_flag',
    'solids_count',
    'logical_volumes_count',
    'placements_count',
    'sources_count',
]);

let callbacks = {
    onSave: async (_payload) => { },
    onDelete: async (_name) => { },
    onRun: async (_name, _maxRuns) => ({}),
    onRunOptimizer: async (_payload) => ({}),
    onReplayBest: async (_runId, _applyToProject) => ({}),
    onVerifyBest: async (_runId, _repeats) => ({}),
    onRefresh: async () => ({})
};

let activeName = null;
let currentStudies = {};
let lastRunResult = null;

function _setForm(study = null, name = '') {
    const s = study || {};
    nameInput.value = name || s.name || '';
    modeInput.value = s.mode || 'grid';
    paramsInput.value = (s.parameters || []).join(',');
    objectivesInput.value = (s.objectives || []).map(o => {
        const metric = o.metric || '';
        const namePart = o.name ? `:${o.name}` : '';
        const dirPart = o.direction ? `:${o.direction}` : '';
        return `${metric}${namePart}${dirPart}`;
    }).join(',');
    gridStepsInput.value = s.grid?.steps ?? 3;
    samplesInput.value = s.random?.samples ?? 10;
    seedInput.value = s.random?.seed ?? 42;
    maxRunsInput.value = '';
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

            if (!ALLOWED_OBJECTIVE_METRICS.has(metric)) {
                throw new Error(`Unsupported objective metric '${metric}'.`);
            }
            if (!['maximize', 'minimize'].includes(direction)) {
                throw new Error(`Invalid objective direction '${direction}'. Use maximize|minimize.`);
            }

            return { metric, name, direction };
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
}

function _renderRankingTable() {
    if (!rankingTableBody) return;

    const runs = _extractRunsFromLastResult();
    rankingTableBody.innerHTML = '';

    if (runs.length === 0) {
        rankingTableBody.innerHTML = '<tr><td colspan="5" style="color:#64748b;">Run a study to populate ranking results.</td></tr>';
        return;
    }

    const objectiveName = rankObjectiveSelect?.value || '';
    const direction = rankDirectionSelect?.value || 'maximize';

    const scored = runs.map(r => {
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

    scored.forEach((item, idx) => {
        const r = item.run;
        const tr = document.createElement('tr');
        const paramsStr = Object.entries(r.values || {}).map(([k, v]) => `${k}=${Number(v).toFixed(4)}`).join(', ');
        tr.innerHTML = `
            <td>${idx + 1}</td>
            <td>${r.run_index}</td>
            <td>${item.objective == null ? 'n/a' : item.objective}</td>
            <td>${r.success ? 'yes' : 'no'}</td>
            <td>${paramsStr}</td>
        `;
        rankingTableBody.appendChild(tr);
    });
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
        window.alert(error.message || String(error));
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

    const result = await callbacks.onRun(name, Number.isFinite(maxRuns) ? maxRuns : null);
    lastRunResult = result || null;
    runOutput.value = JSON.stringify(result, null, 2);
    _updateObjectiveSelector();
    _renderRankingTable();
    _renderOptimizerSummary();
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

    const result = await callbacks.onRunOptimizer(payload);

    lastRunResult = result || null;
    runOutput.value = JSON.stringify(result, null, 2);
    _updateObjectiveSelector();
    if (objectiveName) rankObjectiveSelect.value = objectiveName;
    if (direction) rankDirectionSelect.value = direction;
    _renderRankingTable();
    _renderOptimizerSummary();
}

async function _handleReplayBest() {
    const runId = _getOptimizerRunIdFromLastResult();
    if (!runId) {
        window.alert('No optimizer run selected yet. Run optimizer first.');
        return;
    }

    const result = await callbacks.onReplayBest(runId, true);
    runOutput.value = JSON.stringify(result, null, 2);
    if (result?.replay_result?.run_record) {
        // keep optimizer summary card context; do not overwrite optimizer lastRunResult
    }
}

async function _handleVerifyBest() {
    const runId = _getOptimizerRunIdFromLastResult();
    if (!runId) {
        window.alert('No optimizer run selected yet. Run optimizer first.');
        return;
    }

    const repeats = Number(verifyRepeatsInput?.value || 3);
    const safeRepeats = Number.isFinite(repeats) && repeats > 0 ? repeats : 3;
    const result = await callbacks.onVerifyBest(runId, safeRepeats);
    runOutput.value = JSON.stringify(result, null, 2);

    const stats = result?.verification_result?.verification_record?.stats;
    if (stats && summaryStatusEl) {
        summaryStatusEl.textContent = `Verified (${stats.count} runs)`;
        if (summaryBestScoreEl && Number.isFinite(Number(stats.mean))) {
            summaryBestScoreEl.textContent = `${Number(stats.mean).toFixed(6)} ± ${Number(stats.std || 0).toFixed(6)}`;
        }
    }
}

function _handleDownloadResults() {
    if (!lastRunResult) {
        window.alert('No run result to download yet.');
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
    tableBody = document.getElementById('paramStudiesTableBody');

    nameInput = document.getElementById('ps_name');
    modeInput = document.getElementById('ps_mode');
    paramsInput = document.getElementById('ps_parameters');
    objectivesInput = document.getElementById('ps_objectives');
    gridStepsInput = document.getElementById('ps_grid_steps');
    samplesInput = document.getElementById('ps_samples');
    seedInput = document.getElementById('ps_seed');
    maxRunsInput = document.getElementById('ps_max_runs');
    runOutput = document.getElementById('ps_run_output');
    rankObjectiveSelect = document.getElementById('ps_rank_objective');
    rankDirectionSelect = document.getElementById('ps_rank_direction');
    rankingTableBody = document.getElementById('psRankingTableBody');
    optMethodInput = document.getElementById('ps_opt_method');
    optBudgetInput = document.getElementById('ps_opt_budget');
    optSeedInput = document.getElementById('ps_opt_seed');
    optPopSizeInput = document.getElementById('ps_opt_popsize');
    optSigmaRelInput = document.getElementById('ps_opt_sigma_rel');
    optStagInput = document.getElementById('ps_opt_stag');
    verifyRepeatsInput = document.getElementById('ps_verify_repeats');

    summaryStatusEl = document.getElementById('psSummaryStatus');
    summaryMethodEl = document.getElementById('psSummaryMethod');
    summaryStopReasonEl = document.getElementById('psSummaryStopReason');
    summaryEvalsEl = document.getElementById('psSummaryEvals');
    summaryObjectiveEl = document.getElementById('psSummaryObjective');
    summaryBestScoreEl = document.getElementById('psSummaryBestScore');

    saveBtn = document.getElementById('psSaveBtn');
    deleteBtn = document.getElementById('psDeleteBtn');
    runBtn = document.getElementById('psRunBtn');
    runOptimizerBtn = document.getElementById('psRunOptimizerBtn');
    replayBestBtn = document.getElementById('psReplayBestBtn');
    verifyBestBtn = document.getElementById('psVerifyBestBtn');
    downloadResultsBtn = document.getElementById('psDownloadResultsBtn');
    refreshBtn = document.getElementById('psRefreshBtn');
    cancelBtn = document.getElementById('psCancelBtn');

    saveBtn.addEventListener('click', _handleSave);
    deleteBtn.addEventListener('click', _handleDelete);
    runBtn.addEventListener('click', _handleRun);
    if (runOptimizerBtn) runOptimizerBtn.addEventListener('click', _handleRunOptimizer);
    if (replayBestBtn) replayBestBtn.addEventListener('click', _handleReplayBest);
    if (verifyBestBtn) verifyBestBtn.addEventListener('click', _handleVerifyBest);
    if (downloadResultsBtn) downloadResultsBtn.addEventListener('click', _handleDownloadResults);
    refreshBtn.addEventListener('click', _refreshAndRender);
    cancelBtn.addEventListener('click', hide);
    if (rankObjectiveSelect) rankObjectiveSelect.addEventListener('change', _renderRankingTable);
    if (rankDirectionSelect) rankDirectionSelect.addEventListener('change', _renderRankingTable);
}

export async function show(initialStudies = {}) {
    activeName = null;
    lastRunResult = null;
    _setForm();
    runOutput.value = '';
    _renderTable(initialStudies);
    _updateObjectiveSelector();
    _renderRankingTable();
    _renderOptimizerSummary();
    if (modal) modal.style.display = 'block';
    await _refreshAndRender();
}

export function hide() {
    if (modal) modal.style.display = 'none';
}
