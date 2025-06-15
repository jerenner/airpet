let modalElement, titleElement, nameInput, confirmButton, cancelButton, paramsDiv;
let simpleRadio, mixtureRadio;
let onConfirmCallback = null;
let isEditMode = false;
let editingMaterialId = null;
let currentProjectState = null;
let materialComponents = []; // For mixture mode

export function initMaterialEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;

    modalElement = document.getElementById('materialEditorModal');
    titleElement = document.getElementById('materialEditorTitle');
    nameInput = document.getElementById('materialEditorName');
    confirmButton = document.getElementById('materialEditorConfirm');
    cancelButton = document.getElementById('materialEditorCancel');
    paramsDiv = document.getElementById('material-editor-params');
    simpleRadio = document.getElementById('mat_type_simple');
    mixtureRadio = document.getElementById('mat_type_mixture');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    simpleRadio.addEventListener('change', renderParamsUI);
    mixtureRadio.addEventListener('change', renderParamsUI);

    console.log("Material Editor Initialized.");
}

export function show(materialData = null, projectState = null) {
    currentProjectState = projectState;
    materialComponents = []; // Reset components

    if (materialData && materialData.name) {
        // --- EDIT MODE ---
        isEditMode = true;
        editingMaterialId = materialData.name;
        titleElement.textContent = `Edit Material: ${materialData.name}`;
        nameInput.value = materialData.name;
        nameInput.disabled = true;
        confirmButton.textContent = "Update Material";
        
        // Determine if it's simple or mixture
        if (materialData.components && materialData.components.length > 0) {
            mixtureRadio.checked = true;
            materialComponents = materialData.components; // Load existing components
        } else {
            simpleRadio.checked = true;
        }
        renderParamsUI(materialData);

    } else {
        // --- CREATE MODE ---
        isEditMode = false;
        editingMaterialId = null;
        titleElement.textContent = "Create New Material";
        nameInput.value = '';
        nameInput.disabled = false;
        simpleRadio.checked = true; // Default to simple
        confirmButton.textContent = "Create Material";
        renderParamsUI();
    }
    modalElement.style.display = 'block';
}

function hide() {
    modalElement.style.display = 'none';
}

function renderParamsUI(matData = null) {
    paramsDiv.innerHTML = '';
    const isSimple = simpleRadio.checked;
    
    if (isSimple) {
        paramsDiv.innerHTML = `
            <div class="property_item"><label for="mat_Z">Atomic Number (Z):</label><input type="number" id="mat_Z" value="${matData?.Z || 1}"></div>
            <div class="property_item"><label for="mat_A">Atomic Mass (g/mole):</label><input type="number" step="any" id="mat_A" value="${matData?.A || 1.008}"></div>
            <div class="property_item"><label for="mat_density">Density (g/cm³):</label><input type="number" step="any" id="mat_density" value="${matData?.density || 1.0}"></div>
        `;
    } else { // Mixture
        paramsDiv.innerHTML = `
            <div class="property_item"><label for="mat_density">Density (g/cm³):</label><input type="number" step="any" id="mat_density" value="${matData?.density || 1.0}"></div>
            <hr>
            <h6>Components (by mass fraction)</h6>
            <div id="material-components-list"></div>
            <button id="add-mat-comp-btn" class="add_button" style="margin-top: 10px;">+ Add Component</button>
        `;
        document.getElementById('add-mat-comp-btn').addEventListener('click', addComponentRow);
        rebuildComponentsUI();
    }
}

function rebuildComponentsUI() {
    const listDiv = document.getElementById('material-components-list');
    if (!listDiv) return;
    listDiv.innerHTML = '';

    const elements = Object.keys(currentProjectState.elements || {}); // Assumes elements are defined separately - a better model
    // For now, let's just use other materials
    const materials = Object.keys(currentProjectState.materials || {});


    materialComponents.forEach((comp, index) => {
        const row = document.createElement('div');
        row.className = 'property_item';
        row.innerHTML = `
            <label>Element/Mat:</label>
            <select class="comp-ref" data-index="${index}"></select>
            <label>Fraction:</label>
            <input type="number" step="any" class="comp-frac" data-index="${index}" value="${comp.fraction}">
            <button class="remove-op-btn" data-index="${index}">×</button>
        `;
        listDiv.appendChild(row);

        const select = row.querySelector('.comp-ref');
        // TODO: Populate with elements AND materials
        materials.forEach(matName => {
            if (isEditMode && matName === editingMaterialId) return; // Prevent self-reference
            const opt = document.createElement('option');
            opt.value = matName;
            opt.textContent = matName;
            select.appendChild(opt);
        });
        select.value = comp.ref; // Set current value
    });

    // Attach listeners
    document.querySelectorAll('.comp-ref, .comp-frac').forEach(el => el.addEventListener('change', updateComponentState));
    document.querySelectorAll('.remove-op-btn').forEach(btn => btn.addEventListener('click', removeComponentRow));
}

function addComponentRow() {
    materialComponents.push({ ref: '', fraction: 0.0 });
    rebuildComponentsUI();
}

function removeComponentRow(event) {
    const index = parseInt(event.target.dataset.index, 10);
    materialComponents.splice(index, 1);
    rebuildComponentsUI();
}

function updateComponentState(event) {
    const index = parseInt(event.target.dataset.index, 10);
    if (event.target.classList.contains('comp-ref')) {
        materialComponents[index].ref = event.target.value;
    } else {
        materialComponents[index].fraction = parseFloat(event.target.value);
    }
}

function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) { alert("Please provide a name."); return; }

    const isSimple = simpleRadio.checked;
    let params = {};

    if (isSimple) {
        params = {
            Z: parseFloat(document.getElementById('mat_Z').value),
            A: parseFloat(document.getElementById('mat_A').value),
            density: parseFloat(document.getElementById('mat_density').value),
            components: []
        };
    } else {
        // Validate fractions sum to ~1.0
        const totalFraction = materialComponents.reduce((sum, comp) => sum + comp.fraction, 0);
        if (Math.abs(totalFraction - 1.0) > 0.01) {
            alert(`Mass fractions must sum to 1.0. Current sum: ${totalFraction.toFixed(4)}`);
            return;
        }
        params = {
            density: parseFloat(document.getElementById('mat_density').value),
            components: materialComponents
        };
    }
    
    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingMaterialId : name,
        name: name,
        params: params
    });
    hide();
}
