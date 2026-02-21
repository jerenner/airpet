let modal, tableBody;
let nameInput, modeInput, paramsInput, gridStepsInput, samplesInput, seedInput, maxRunsInput, runOutput;
let saveBtn, deleteBtn, runBtn, refreshBtn, cancelBtn;

let callbacks = {
    onSave: async (_payload) => { },
    onDelete: async (_name) => { },
    onRun: async (_name, _maxRuns) => ({}),
    onRefresh: async () => ({})
};

let activeName = null;
let currentStudies = {};

function _setForm(study = null, name = '') {
    const s = study || {};
    nameInput.value = name || s.name || '';
    modeInput.value = s.mode || 'grid';
    paramsInput.value = (s.parameters || []).join(',');
    gridStepsInput.value = s.grid?.steps ?? 3;
    samplesInput.value = s.random?.samples ?? 10;
    seedInput.value = s.random?.seed ?? 42;
    maxRunsInput.value = '';
}

function _studyFromForm() {
    const mode = modeInput.value;
    const parameters = paramsInput.value.split(',').map(x => x.trim()).filter(Boolean);

    return {
        name: nameInput.value.trim(),
        mode,
        parameters,
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
    runOutput.value = JSON.stringify(result, null, 2);
}

export function init(newCallbacks = {}) {
    callbacks = { ...callbacks, ...newCallbacks };

    modal = document.getElementById('paramStudiesModal');
    tableBody = document.getElementById('paramStudiesTableBody');

    nameInput = document.getElementById('ps_name');
    modeInput = document.getElementById('ps_mode');
    paramsInput = document.getElementById('ps_parameters');
    gridStepsInput = document.getElementById('ps_grid_steps');
    samplesInput = document.getElementById('ps_samples');
    seedInput = document.getElementById('ps_seed');
    maxRunsInput = document.getElementById('ps_max_runs');
    runOutput = document.getElementById('ps_run_output');

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
}

export async function show(initialStudies = {}) {
    activeName = null;
    _setForm();
    runOutput.value = '';
    _renderTable(initialStudies);
    if (modal) modal.style.display = 'block';
    await _refreshAndRender();
}

export function hide() {
    if (modal) modal.style.display = 'none';
}
