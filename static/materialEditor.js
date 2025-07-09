// FILE: virtual-pet/static/materialEditor.js

import * as ExpressionInput from './expressionInput.js';

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

function renderParamsUI(matData = null) {
    paramsDiv.innerHTML = '';
    const isSimple = simpleRadio.checked;
    
    if (isSimple) {
        // Use the new component for each parameter
        paramsDiv.appendChild(ExpressionInput.create('mat_Z', 'Atomic Number (Z)', matData?.Z_expr || '1', currentProjectState));
        paramsDiv.appendChild(ExpressionInput.create('mat_A', 'Atomic Mass (g/mole)', matData?.A_expr || '1.008', currentProjectState));
        paramsDiv.appendChild(ExpressionInput.create('mat_density', 'Density (g/cm³)', matData?.density_expr || '1.0', currentProjectState));
    } else { // Mixture
        paramsDiv.appendChild(ExpressionInput.create('mat_density', 'Density (g/cm³)', matData?.density_expr || '1.0', currentProjectState));
        
        const hr = document.createElement('hr');
        const mixtureHtml = `
            <h6>Components (by mass fraction)</h6>
            <div id="material-components-list"></div>
            <button id="add-mat-comp-btn" class="add_button" style="margin-top: 10px;">+ Add Component</button>`;
        const mixtureDiv = document.createElement('div');
        mixtureDiv.innerHTML = mixtureHtml;

        paramsDiv.appendChild(hr);
        paramsDiv.appendChild(mixtureDiv);
        
        document.getElementById('add-mat-comp-btn').addEventListener('click', addComponentRow);
        rebuildComponentsUI();
    }
}

function rebuildComponentsUI() {
    const listDiv = document.getElementById('material-components-list');
    if (!listDiv) return;
    listDiv.innerHTML = '';

    const materials = Object.keys(currentProjectState.materials || {});

    materialComponents.forEach((comp, index) => {
        const row = document.createElement('div');
        row.className = 'property_item';
        
        // --- Create the select dropdown for material reference ---
        const selectLabel = document.createElement('label');
        selectLabel.textContent = "Material:";
        const select = document.createElement('select');
        select.className = 'comp-ref';
        select.dataset.index = index;
        materials.forEach(matName => {
            if (isEditMode && matName === editingMaterialId) return;
            const opt = document.createElement('option');
            opt.value = matName;
            opt.textContent = matName;
            select.appendChild(opt);
        });
        select.value = comp.ref;

        // --- Create the fraction label and expression input ---
        const fractionLabel = document.createElement('label');
        fractionLabel.textContent = "Fraction:";
        fractionLabel.style.marginLeft = '10px';

        // ## FIX: Use the new inline expression component for the fraction
        const fractionInputComponent = ExpressionInput.createInline(
            `mat_comp_frac_${index}`,
            comp.fraction, // This is now an expression string
            currentProjectState,
            (newValue) => { // onChange callback
                materialComponents[index].fraction = newValue;
            }
        );
        fractionInputComponent.id = `mat-comp-frac-wrapper-${index}`; // Add an ID to the wrapper itself

        // --- Create the remove button ---
        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-op-btn';
        removeBtn.dataset.index = index;
        removeBtn.textContent = '×';
        
        // --- Assemble the row ---
        row.appendChild(selectLabel);
        row.appendChild(select);
        row.appendChild(fractionLabel);
        row.appendChild(fractionInputComponent);
        row.appendChild(removeBtn);
        listDiv.appendChild(row);
    });

    // Attach listeners for select and remove buttons
    document.querySelectorAll('.comp-ref').forEach(el => el.addEventListener('change', updateComponentState));
    document.querySelectorAll('.remove-op-btn').forEach(btn => btn.addEventListener('click', removeComponentRow));
}

function addComponentRow() {
    const availableMaterials = Object.keys(currentProjectState.materials || {}).filter(m => m !== editingMaterialId);
    if (availableMaterials.length === 0) {
        alert("No other materials available to add to the mixture.");
        return;
    }
    // Initialize fraction as a string expression
    materialComponents.push({ ref: availableMaterials[0], fraction: '0.0' });
    rebuildComponentsUI();
}

function removeComponentRow(event) {
    const index = parseInt(event.target.dataset.index, 10);
    materialComponents.splice(index, 1);
    rebuildComponentsUI();
}

function updateComponentState(event) {
    const index = parseInt(event.target.dataset.index, 10);
    // The fraction is updated live by the component's onChange callback.
    // We only need to handle the dropdown change here.
    if (event.target.classList.contains('comp-ref')) {
        materialComponents[index].ref = event.target.value;
    }
}

function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) { alert("Please provide a name."); return; }

    const isSimple = simpleRadio.checked;
    let params = {};

    if (isSimple) {
        params = {
            Z_expr: document.getElementById('mat_Z').value,
            A_expr: document.getElementById('mat_A').value,
            density_expr: document.getElementById('mat_density').value,
            components: []
        };
    } else {
        // TODO: NEED TO VALIDATE THE FRACTIONAL COMPONENTS
        params = {
            density_expr: document.getElementById('mat_density').value,
            components: materialComponents, // This now contains string expressions for fractions
            Z_expr: null,
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