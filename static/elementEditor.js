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

    if (elData) { // EDIT MODE
        isEditMode = true;
        editingElementId = elData.name;
        titleElement.textContent = `Edit Element: ${elData.name}`;
        nameInput.value = elData.name;
        nameInput.disabled = true;
        formulaInput.value = elData.formula || '';
        confirmButton.textContent = "Update Element";

        if (elData.components && elData.components.length > 0) {
            document.getElementById('el_type_isotope').checked = true;
            isotopeComponents = JSON.parse(JSON.stringify(elData.components));
        } else {
            document.getElementById('el_type_simple').checked = true;
        }
        renderParamsUI(elData);
    } else { // CREATE MODE
        isEditMode = false;
        editingElementId = null;
        titleElement.textContent = "Create New Element";
        nameInput.value = '';
        nameInput.disabled = false;
        formulaInput.value = '';
        document.getElementById('el_type_simple').checked = true;
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
            <p style="font-size: 11px; color: #555;"><i>Note: Isotopes must be defined in the GDML file manually for now.</i></p>
        `;
        paramsDiv.innerHTML = html;
        rebuildIsotopeUI();
    }
}

function rebuildIsotopeUI() {
    const listDiv = document.getElementById('isotope-components-list');
    if (!listDiv) return;
    listDiv.innerHTML = '';
    // For now, we assume isotopes are predefined in the project state
    const availableIsotopes = Object.keys(currentProjectState.isotopes || {});

    // This UI is read-only for now, as creating isotopes isn't implemented
    isotopeComponents.forEach(comp => {
        const row = document.createElement('div');
        row.className = 'property_item readonly';
        row.innerHTML = `<label>${comp.ref}:</label><span>${comp.fraction}</span>`;
        listDiv.appendChild(row);
    });

    if (isotopeComponents.length === 0 && availableIsotopes.length === 0) {
        listDiv.innerHTML = '<p style="font-style: italic; color: #888;">No isotopes defined in project.</p>';
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
