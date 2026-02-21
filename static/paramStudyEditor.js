let modal, tableBody;
let nameInput, modeInput, paramsInput, objectivesInput, gridStepsInput, samplesInput, seedInput, maxRunsInput, runOutput;
let rankObjectiveSelect, rankDirectionSelect, rankingTableBody;
let saveBtn, deleteBtn, runBtn, refreshBtn, cancelBtn;

let callbacks = {
    onSave: async (_payload) => { },
    onDelete: async (_name) => { },
    onRun: async (_name, _maxRuns) => ({}),
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

    const objectives = objectivesInput.value
        .split(',')
        .map(x => x.trim())
        .filter(Boolean)
        .map(token => {
            const parts = token.split(':').map(p => p.trim());
            const metric = parts[0];
            const name = parts[1] || metric;
            const direction = parts[2] || 'maximize';
            return { metric, name, direction };
        });

    return {
        name: nameInput.value.trim(),
        mode,
        parameters,
        objectives,
        grid: {
            steps: Number(gridStepsInput.value || 3),
            per_parameter_steps: {},
        },
        random: {
            samples: Number(samplesInput.value || 10),
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

function _renderRankingTable() {
    if (!rankingTableBody) return;

    const runs = (lastRunResult && Array.isArray(lastRunResult.runs)) ? lastRunResult.runs : [];
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

    const runs = (lastRunResult && Array.isArray(lastRunResult.runs)) ? lastRunResult.runs : [];
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
    const payload = _studyFromForm();
    await callbacks.onSave(payload);
    activeName = payload.name;
    await _refreshAndRender();
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

    saveBtn = document.getElementById('psSaveBtn');
    deleteBtn = document.getElementById('psDeleteBtn');
    runBtn = document.getElementById('psRunBtn');
    refreshBtn = document.getElementById('psRefreshBtn');
    cancelBtn = document.getElementById('psCancelBtn');

    saveBtn.addEventListener('click', _handleSave);
    deleteBtn.addEventListener('click', _handleDelete);
    runBtn.addEventListener('click', _handleRun);
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
    if (modal) modal.style.display = 'block';
    await _refreshAndRender();
}

export function hide() {
    if (modal) modal.style.display = 'none';
}
