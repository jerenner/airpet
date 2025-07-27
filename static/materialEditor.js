// FILE: virtual-pet/static/materialEditor.js

import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, confirmButton, cancelButton, paramsDiv;
let simpleRadio, mixtureRadio, compositeRadio;
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
    compositeRadio = document.getElementById('mat_type_composite');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    simpleRadio.addEventListener('change', () => renderParamsUI()); // Pass a flag to reset
    mixtureRadio.addEventListener('change', () => renderParamsUI());
    compositeRadio.addEventListener('change', () => renderParamsUI());

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
            // Check if it's a composite (by natoms) or mixture (by fraction)
            if (materialData.components[0].natoms !== undefined) {
                compositeRadio.checked = true;
            } else {
                mixtureRadio.checked = true;
            }
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
    const isComposite = compositeRadio.checked;
    
    if (isSimple) {
        // Use the new component for each parameter
        paramsDiv.appendChild(ExpressionInput.create('mat_Z', 'Atomic Number (Z)', matData?.Z_expr || '1', currentProjectState));
        paramsDiv.appendChild(ExpressionInput.create('mat_A', 'Atomic Mass (g/mole)', matData?.A_expr || '1.008', currentProjectState));
        paramsDiv.appendChild(ExpressionInput.create('mat_density', 'Density (g/cm³)', matData?.density_expr || '1.0', currentProjectState));
    } else { // Mixture or Composite
        paramsDiv.appendChild(ExpressionInput.create('mat_density', 'Density (g/cm³)', matData?.density_expr || '1.0', currentProjectState));
        
        const hr = document.createElement('hr');

        // Dynamic title based on type
        const titleText = isComposite ? 'Elements (by # of Atoms)' : 'Components (by Mass Fraction)';

        const mixtureHtml = `
            <h6>${titleText}</h6>
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

    const isComposite = compositeRadio.checked;

    // Get the list of available items for the dropdown
    const availableItems = isComposite 
        ? Object.keys(currentProjectState.elements || {}) 
        : Object.keys(currentProjectState.materials || {});

    //const materials = Object.keys(currentProjectState.materials || {});

    materialComponents.forEach((comp, index) => {
        const row = document.createElement('div');
        row.className = 'property_item';
        
        // --- Create the select dropdown for material reference ---
        const selectLabel = document.createElement('label');
        selectLabel.textContent = "Material:";
        const select = document.createElement('select');
        select.className = 'comp-ref';
        populateSelect(select, availableItems); 
        select.value = comp.ref;

        // --- Input for fraction or number of atoms ---
        const valueLabel = document.createElement('label');
        valueLabel.textContent = isComposite ? "# Atoms:" : "Fraction:";
        valueLabel.style.marginLeft = '10px';

        const valueKey = isComposite ? 'natoms' : 'fraction';
        const initialValue = comp[valueKey] || '0.0';

        const valueInputComponent = ExpressionInput.createInline(
            `mat_comp_val_${index}`,
            initialValue,
            currentProjectState,
            (newValue) => {
                materialComponents[index][valueKey] = newValue;
                // If we are a mixture, we also need to clear the other key
                if (isComposite) delete materialComponents[index].fraction;
                else delete materialComponents[index].natoms;
            }
        );

        // --- Create the remove button ---
        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-op-btn';
        removeBtn.dataset.index = index;
        removeBtn.textContent = '×';
        
        // --- Assemble the row ---
        row.appendChild(selectLabel);
        row.appendChild(select);
        row.appendChild(valueLabel);
        row.appendChild(valueInputComponent);
        row.appendChild(removeBtn);
        listDiv.appendChild(row);
    });

    // Attach listeners for select and remove buttons
    document.querySelectorAll('.comp-ref').forEach(el => el.addEventListener('change', updateComponentState));
    document.querySelectorAll('.remove-op-btn').forEach(btn => btn.addEventListener('click', removeComponentRow));
}

function addComponentRow() {
    const isComposite = compositeRadio.checked;
    const availableItems = isComposite 
        ? Object.keys(currentProjectState.elements || {}) 
        : Object.keys(currentProjectState.materials || {}).filter(m => m !== editingMaterialId);

    if (availableItems.length === 0) {
        alert(`No available ${isComposite ? 'elements' : 'materials'} to add.`);
        return;
    }
    
    const newComponent = { ref: availableItems[0] };
    if (isComposite) {
        newComponent.natoms = '1'; // Default to 1 atom
    } else {
        newComponent.fraction = '0.0'; // Default to 0.0 fraction
    }
    materialComponents.push(newComponent);
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

function populateSelect(selectElement, optionsArray) {
    selectElement.innerHTML = ''; // Clear any existing options
    optionsArray.forEach(optionText => {
        const option = document.createElement('option');
        option.value = optionText;
        option.textContent = optionText;
        selectElement.appendChild(option);
    });
}

function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) { alert("Please provide a name."); return; }

    const isSimple = simpleRadio.checked;
    const isComposite = compositeRadio.checked;

    let params = {};
    if (isSimple) {
        params = {
            Z_expr: document.getElementById('mat_Z').value,
            A_expr: document.getElementById('mat_A').value,
            density_expr: document.getElementById('mat_density').value,
            components: []
        };
    } else {
        // For both Mixture and Composite
        params = {
            density_expr: document.getElementById('mat_density').value,
            components: materialComponents,
            Z_expr: null, // Let Geant4 calculate these
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