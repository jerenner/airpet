// static/elementEditor.js

import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, formulaInput,
    confirmButton, cancelButton, paramsDiv, contentTypeRadios;
let onConfirmCallback = null;
let isEditMode = false;
let editingElementId = null;
let currentProjectState = null;
let isotopeComponents = []; // Local state for isotope fractions

export function initElementEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;
    modalElement = document.getElementById('elementEditorModal');
    titleElement = document.getElementById('elementEditorTitle');
    nameInput = document.getElementById('elEditorName');
    formulaInput = document.getElementById('elEditorFormula');
    paramsDiv = document.getElementById('element-editor-params');
    contentTypeRadios = modalElement.querySelectorAll('input[name="el_type"]');
    confirmButton = document.getElementById('elEditorConfirm');
    cancelButton = document.getElementById('elEditorCancel');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    contentTypeRadios.forEach(radio => radio.addEventListener('change', () => renderParamsUI()));

    console.log("Element Editor Initialized.");
}

export function show(elData = null, projectState = null) {
    currentProjectState = projectState;
    isotopeComponents = [];

    // Get the radio buttons for easy access
    const simpleRadio = document.getElementById('el_type_simple');
    const isotopeRadio = document.getElementById('el_type_isotope');

    if (elData) { // EDIT MODE
        isEditMode = true;
        editingElementId = elData.name;
        titleElement.textContent = `Edit Element: ${elData.name}`;
        nameInput.value = elData.name;
        nameInput.disabled = true;
        formulaInput.value = elData.formula || '';
        confirmButton.textContent = "Update Element";

        // Disable the radio buttons in edit mode
        simpleRadio.disabled = true;
        isotopeRadio.disabled = true;

        if (elData.components && elData.components.length > 0) {
            isotopeRadio.checked = true;
            isotopeComponents = JSON.parse(JSON.stringify(elData.components));
        } else {
            simpleRadio.checked = true;
        }
        renderParamsUI(elData);
    } else { // CREATE MODE
        isEditMode = false;
        editingElementId = null;
        titleElement.textContent = "Create New Element";
        nameInput.value = '';
        nameInput.disabled = false;
        formulaInput.value = '';

        // Ensure the radio buttons are enabled in create mode
        simpleRadio.disabled = false;
        isotopeRadio.disabled = false;

        simpleRadio.checked = true;
        confirmButton.textContent = "Create Element";
        renderParamsUI();
    }
    modalElement.style.display = 'block';
}

function renderParamsUI(elData = null) {
    paramsDiv.innerHTML = '';
    const defType = document.querySelector('input[name="el_type"]:checked').value;

    if (defType === 'simple') {
        paramsDiv.appendChild(ExpressionInput.create('elEditorZ', 'Atomic Number (Z)', elData?.Z || '1', currentProjectState));
        paramsDiv.appendChild(ExpressionInput.create('elEditorA', 'Atomic Mass (A)', elData?.A_expr || '1.008', currentProjectState));
    } else { // By isotope fraction
        const html = `
            <h6>Isotope Fractions</h6>
            <div id="isotope-components-list"></div>
            <button id="add-isotope-comp-btn" class="add_button" style="margin-top: 10px;">+ Add Isotope</button>
        `;
        paramsDiv.innerHTML = html;
        document.getElementById('add-isotope-comp-btn').addEventListener('click', addIsotopeComponentRow);
        rebuildIsotopeUI();
    }
}

function rebuildIsotopeUI() {
    const listDiv = document.getElementById('isotope-components-list');
    if (!listDiv) return;
    listDiv.innerHTML = '';
    const availableIsotopes = Object.keys(currentProjectState.isotopes || {});
    
    if (availableIsotopes.length === 0) {
        listDiv.innerHTML = '<p style="font-style: italic; color: #888;">No isotopes defined in project. Please create some in the Properties tab first.</p>';
    }

    isotopeComponents.forEach((comp, index) => {
        const row = document.createElement('div');
        row.className = 'property_item'; // A simple flex row for alignment

        // --- Isotope Selector Dropdown ---
        const select = document.createElement('select');
        select.className = 'comp-ref';
        select.dataset.index = index;
        populateSelect(select, availableIsotopes);
        select.value = comp.ref;

        // --- Fraction Input ---
        const valueLabel = document.createElement('label');
        valueLabel.textContent = "Fraction:";
        valueLabel.style.marginLeft = '10px';
        const valueInputComponent = ExpressionInput.createInline(
            `el_iso_frac_${index}`,
            comp.fraction || '0.0',
            currentProjectState,
            (newValue) => { // Live update the state
                isotopeComponents[index].fraction = newValue;
            }
        );

        // --- Remove Button ---
        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-op-btn';
        removeBtn.textContent = '×';
        removeBtn.title = 'Remove Isotope';
        removeBtn.onclick = () => {
            isotopeComponents.splice(index, 1);
            rebuildIsotopeUI();
        };

        row.appendChild(select);
        row.appendChild(valueLabel);
        row.appendChild(valueInputComponent);
        row.appendChild(removeBtn);
        listDiv.appendChild(row);
    });
    
    // Attach event listeners for the dropdowns
    document.querySelectorAll('.comp-ref').forEach(el => el.addEventListener('change', (event) => {
        const index = parseInt(event.target.dataset.index, 10);
        isotopeComponents[index].ref = event.target.value;
    }));
}

// Helper function to add a new row to the UI
function addIsotopeComponentRow() {
    const availableIsotopes = Object.keys(currentProjectState.isotopes || {});
    if (availableIsotopes.length === 0) {
        alert("Cannot add component because no isotopes are defined in the project.");
        return;
    }
    // Add a new entry to our local state
    isotopeComponents.push({
        ref: availableIsotopes[0], // Default to the first available isotope
        fraction: '0.0'
    });
    // Re-render the entire list
    rebuildIsotopeUI();
}

// Helper to populate a select element
function populateSelect(selectElement, optionsArray) {
    selectElement.innerHTML = ''; // Clear existing options
    if (optionsArray.length === 0) {
        const option = document.createElement('option');
        option.textContent = "No Isotopes Available";
        option.disabled = true;
        selectElement.appendChild(option);
    } else {
        optionsArray.forEach(optionText => {
            const option = document.createElement('option');
            option.value = optionText;
            option.textContent = optionText;
            selectElement.appendChild(option);
        });
    }
}

function hide() {
    modalElement.style.display = 'none';
}

function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) {
        alert("Please provide a name.");
        return;
    }

    const defType = document.querySelector('input[name="el_type"]:checked').value;
    let Z = null, A_expr = null, components = [];

    if (defType === 'simple') {
        Z = document.getElementById('elEditorZ').value;
        A_expr = document.getElementById('elEditorA').value;
    } else {
        // Use the local state populated by the interactive UI
        if (isotopeComponents.some(c => !c.ref || c.fraction.trim() === '')) {
            alert("All isotope components must have an isotope selected and a fraction defined.");
            return;
        }
        components = isotopeComponents;
    }
    
    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingElementId : name,
        name: name,
        formula: formulaInput.value.trim(),
        Z: Z,
        A_expr: A_expr,
        components: components
    });

    hide();
}
