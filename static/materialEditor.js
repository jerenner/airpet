// FILE: virtual-pet/static/materialEditor.js

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
    simpleRadio.addEventListener('change', () => renderParamsUI(null, true)); // Pass a flag to reset
    mixtureRadio.addEventListener('change', () => renderParamsUI(null, true));

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
        
        if (materialData.components && materialData.components.length > 0) {
            mixtureRadio.checked = true;
            materialComponents = JSON.parse(JSON.stringify(materialData.components)); // Deep copy
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

// Helper to create an expression input field with live evaluation
function createExpressionInput(id, label, initialValue = '0') {
    return `
        <div class="property_item" style="flex-direction: column; align-items: flex-start;">
            <label for="${id}">${label}:</label>
            <div style="display: flex; width: 100%; align-items: center;">
                <input type="text" id="${id}" class="expression-input" value="${initialValue}" style="flex-grow: 1; font-family: monospace;">
                <input type="text" id="${id}-result" class="expression-result" style="width: 80px; margin-left: 5px;" readonly disabled>
            </div>
        </div>
    `;
}

// Helper to attach live evaluation logic to an input field
function attachLiveEvaluation(inputId, resultId) {
    const inputEl = document.getElementById(inputId);
    const resultEl = document.getElementById(resultId);
    
    const evaluate = async () => {
        const expression = inputEl.value;
        if (!expression.trim()) {
            resultEl.value = '';
            resultEl.style.borderColor = '#ccc';
            return;
        }
        try {
            // We use the project state passed to the editor
            const response = await APIService.evaluateExpression(expression, currentProjectState);
            if (response.success) {
                resultEl.value = response.result.toPrecision(4);
                resultEl.style.borderColor = '#ccc';
                resultEl.title = `Evaluated: ${response.result}`;
            } else {
                resultEl.value = 'Error';
                resultEl.style.borderColor = 'red';
                resultEl.title = response.error;
            }
        } catch (error) {
            resultEl.value = 'Error';
            resultEl.style.borderColor = 'red';
            resultEl.title = error.message;
        }
    };
    
    inputEl.addEventListener('input', evaluate);
    inputEl.addEventListener('change', evaluate); // Also on change for blur events
    evaluate(); // Trigger initial evaluation
}

function renderParamsUI(matData = null, forceDefaults = false) {
    paramsDiv.innerHTML = '';
    const isSimple = simpleRadio.checked;
    
    if (isSimple) {
        // Use the new expression input helper
        paramsDiv.innerHTML = 
            createExpressionInput('mat_Z', 'Atomic Number (Z)') +
            createExpressionInput('mat_A', 'Atomic Mass (g/mole)') +
            createExpressionInput('mat_density', 'Density (g/cm³)');

        if (matData && !forceDefaults) {
            document.getElementById('mat_Z').value = matData.Z_expr || '';
            document.getElementById('mat_A').value = matData.A_expr || '';
            document.getElementById('mat_density').value = matData.density_expr || '0.0';
        } else {
            // Set default values for a new simple material
            document.getElementById('mat_Z').value = '1';
            document.getElementById('mat_A').value = '1.008';
            document.getElementById('mat_density').value = '1.0';
        }

        // Attach live evaluation listeners
        attachLiveEvaluation('mat_Z', 'mat_Z-result');
        attachLiveEvaluation('mat_A', 'mat_A-result');
        attachLiveEvaluation('mat_density', 'mat_density-result');

    } else { // Mixture
        // Use the new expression input helper for density
        paramsDiv.innerHTML = 
            createExpressionInput('mat_density', 'Density (g/cm³)') +
            `<hr>
            <h6>Components (by mass fraction)</h6>
            <div id="material-components-list"></div>
            <button id="add-mat-comp-btn" class="add_button" style="margin-top: 10px;">+ Add Component</button>`;

        if (matData && !forceDefaults) {
            document.getElementById('mat_density').value = matData.density_expr || '0.0';
        } else {
            document.getElementById('mat_density').value = '1.0';
        }
        
        attachLiveEvaluation('mat_density', 'mat_density-result');
        document.getElementById('add-mat-comp-btn').addEventListener('click', addComponentRow);
        rebuildComponentsUI();
    }
}

function rebuildComponentsUI() {
    const listDiv = document.getElementById('material-components-list');
    if (!listDiv) return;
    listDiv.innerHTML = '';

    // A material mixture can be composed of other materials or elements
    // For now, we only support mixing other materials for simplicity.
    const materials = Object.keys(currentProjectState.materials || {});

    materialComponents.forEach((comp, index) => {
        const row = document.createElement('div');
        row.className = 'property_item';
        row.innerHTML = `
            <label>Material:</label>
            <select class="comp-ref" data-index="${index}"></select>
            <label>Fraction:</label>
            <input type="number" step="any" class="comp-frac" data-index="${index}" value="${comp.fraction}">
            <button class="remove-op-btn" data-index="${index}">×</button>
        `;
        listDiv.appendChild(row);

        const select = row.querySelector('.comp-ref');
        materials.forEach(matName => {
            if (isEditMode && matName === editingMaterialId) return; // Prevent self-reference
            const opt = document.createElement('option');
            opt.value = matName;
            opt.textContent = matName;
            select.appendChild(opt);
        });
        select.value = comp.ref;
    });

    document.querySelectorAll('.comp-ref, .comp-frac').forEach(el => el.addEventListener('change', updateComponentState));
    document.querySelectorAll('.remove-op-btn').forEach(btn => btn.addEventListener('click', removeComponentRow));
}

function addComponentRow() {
    const availableMaterials = Object.keys(currentProjectState.materials || {}).filter(m => m !== editingMaterialId);
    if (availableMaterials.length === 0) {
        alert("No other materials available to add to the mixture.");
        return;
    }
    materialComponents.push({ ref: availableMaterials[0], fraction: 0.0 });
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
        materialComponents[index].fraction = parseFloat(event.target.value) || 0;
    }
}

function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) { alert("Please provide a name."); return; }

    const isSimple = simpleRadio.checked;
    let params = {};

    if (isSimple) {
        // Get the raw expression strings from the inputs
        params = {
            Z_expr: document.getElementById('mat_Z').value,
            A_expr: document.getElementById('mat_A').value,
            density_expr: document.getElementById('mat_density').value,
            components: [] // Empty components for a simple material
        };
    } else {
        const totalFraction = materialComponents.reduce((sum, comp) => sum + (comp.fraction || 0), 0);
        if (Math.abs(totalFraction - 1.0) > 0.01) {
            alert(`Mass fractions must sum to 1.0. Current sum: ${totalFraction.toFixed(4)}`);
            return;
        }
        params = {
            density_expr: document.getElementById('mat_density').value,
            components: materialComponents,
            Z_expr: null, // Simple materials don't have these
            A_expr: null
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