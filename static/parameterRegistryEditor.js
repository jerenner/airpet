let modal, tableBody;
let nameInput, targetTypeInput, targetNameInput, targetFieldInput;
let minInput, maxInput, defaultInput, unitsInput, constraintGroupInput, enabledInput;
let saveBtn, deleteBtn, refreshBtn, cancelBtn;

let callbacks = {
    onSave: async (_payload) => { },
    onDelete: async (_name) => { },
    onRefresh: async () => ({})
};

let activeName = null;

function _setForm(entry = null, name = '') {
    const e = entry || {};
    const targetRef = e.target_ref || {};

    nameInput.value = name || e.name || '';
    targetTypeInput.value = e.target_type || 'define';

    if ((e.target_type || 'define') === 'sim_option') {
        targetNameInput.value = '';
        targetFieldInput.value = targetRef.key || '';
    } else if ((e.target_type || 'define') === 'solid') {
        targetNameInput.value = targetRef.name || '';
        targetFieldInput.value = targetRef.param || '';
    } else if ((e.target_type || 'define') === 'source') {
        targetNameInput.value = targetRef.name || '';
        targetFieldInput.value = targetRef.field || '';
    } else {
        targetNameInput.value = targetRef.name || '';
        targetFieldInput.value = '';
    }

    minInput.value = e.bounds?.min ?? '';
    maxInput.value = e.bounds?.max ?? '';
    defaultInput.value = e.default ?? '';
    unitsInput.value = e.units ?? '';
    constraintGroupInput.value = e.constraint_group ?? '';
    enabledInput.checked = (e.enabled ?? true) === true;
}

function _buildTargetRef() {
    const targetType = targetTypeInput.value;
    const n = targetNameInput.value.trim();
    const f = targetFieldInput.value.trim();

    if (targetType === 'define') return { name: n };
    if (targetType === 'solid') return { name: n, param: f };
    if (targetType === 'source') return { name: n, field: f };
    return { key: f || n };
}

function _entryFromForm() {
    const name = nameInput.value.trim();
    return {
        name,
        target_type: targetTypeInput.value,
        target_ref: _buildTargetRef(),
        bounds: {
            min: Number(minInput.value),
            max: Number(maxInput.value),
        },
        default: Number(defaultInput.value),
        units: unitsInput.value.trim(),
        enabled: !!enabledInput.checked,
        constraint_group: constraintGroupInput.value.trim() || null,
    };
}

function _renderTable(registry = {}) {
    const entries = Object.entries(registry || {}).sort(([a], [b]) => a.localeCompare(b));
    tableBody.innerHTML = '';

    if (entries.length === 0) {
        const tr = document.createElement('tr');
        tr.innerHTML = '<td colspan="5" style="color:#64748b;">No parameters defined.</td>';
        tableBody.appendChild(tr);
        return;
    }

    for (const [name, entry] of entries) {
        const tr = document.createElement('tr');
        if (name === activeName) tr.classList.add('active');

        const targetType = entry.target_type || '';
        const targetRef = entry.target_ref || {};
        const targetDisp = targetType === 'sim_option'
            ? `${targetType}:${targetRef.key || ''}`
            : `${targetType}:${targetRef.name || ''}${targetRef.param ? '.' + targetRef.param : ''}${targetRef.field ? '.' + targetRef.field : ''}`;

        tr.innerHTML = `
            <td>${name}</td>
            <td>${targetDisp}</td>
            <td>[${entry.bounds?.min ?? ''}, ${entry.bounds?.max ?? ''}]</td>
            <td>${entry.default ?? ''}</td>
            <td>${entry.enabled ? 'yes' : 'no'}</td>
        `;
        tr.addEventListener('click', () => {
            activeName = name;
            _setForm(entry, name);
            _renderTable(registry);
        });

        tableBody.appendChild(tr);
    }
}

async function _refreshAndRender() {
    const registry = await callbacks.onRefresh();
    _renderTable(registry || {});
}

async function _handleSave() {
    const payload = _entryFromForm();
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

export function init(newCallbacks = {}) {
    callbacks = { ...callbacks, ...newCallbacks };

    modal = document.getElementById('parameterRegistryModal');
    tableBody = document.getElementById('parameterRegistryTableBody');

    nameInput = document.getElementById('pr_name');
    targetTypeInput = document.getElementById('pr_target_type');
    targetNameInput = document.getElementById('pr_target_name');
    targetFieldInput = document.getElementById('pr_target_field');
    minInput = document.getElementById('pr_min');
    maxInput = document.getElementById('pr_max');
    defaultInput = document.getElementById('pr_default');
    unitsInput = document.getElementById('pr_units');
    constraintGroupInput = document.getElementById('pr_constraint_group');
    enabledInput = document.getElementById('pr_enabled');

    saveBtn = document.getElementById('prSaveBtn');
    deleteBtn = document.getElementById('prDeleteBtn');
    refreshBtn = document.getElementById('prRefreshBtn');
    cancelBtn = document.getElementById('prCancelBtn');

    saveBtn.addEventListener('click', _handleSave);
    deleteBtn.addEventListener('click', _handleDelete);
    refreshBtn.addEventListener('click', _refreshAndRender);
    cancelBtn.addEventListener('click', hide);
}

export async function show(initialRegistry = {}) {
    activeName = null;
    _setForm();
    _renderTable(initialRegistry);
    if (modal) modal.style.display = 'block';
    await _refreshAndRender();
}

export function hide() {
    if (modal) modal.style.display = 'none';
}
