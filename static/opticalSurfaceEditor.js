// static/opticalSurfaceEditor.js
import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, modelSelect, finishSelect, typeSelect,
    valueContainer, confirmButton, cancelButton, propertiesListDiv;
let onConfirmCallback = null;
let isEditMode = false;
let editingOSId = null;
let currentProjectState = null;
let surfaceProperties = []; // Local state for key/value properties

export function initOpticalSurfaceEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;
    modalElement = document.getElementById('opticalSurfaceEditorModal');
    titleElement = document.getElementById('opticalSurfaceEditorTitle');
    nameInput = document.getElementById('osEditorName');
    modelSelect = document.getElementById('osEditorModel');
    finishSelect = document.getElementById('osEditorFinish');
    typeSelect = document.getElementById('osEditorType');
    valueContainer = document.getElementById('os-editor-value-container');
    propertiesListDiv = document.getElementById('os-properties-list');
    confirmButton = document.getElementById('osEditorConfirm');
    cancelButton = document.getElementById('osEditorCancel');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    document.getElementById('add-os-property-btn').addEventListener('click', addPropertyRow);

    console.log("Optical Surface Editor Initialized.");
}

export function show(osData = null, projectState = null) {
    currentProjectState = projectState;
    surfaceProperties = []; // Reset local state

    if (osData) { // EDIT MODE
        isEditMode = true;
        editingOSId = osData.name;
        titleElement.textContent = `Edit Optical Surface: ${osData.name}`;
        nameInput.value = osData.name;
        nameInput.disabled = true;
        confirmButton.textContent = "Update Surface";

        modelSelect.value = osData.model;
        finishSelect.value = osData.finish;
        typeSelect.value = osData.type;
        valueContainer.innerHTML = '';
        valueContainer.appendChild(ExpressionInput.create('os_value', 'Value', osData.value || '1.0'));
        
        // Convert properties from {key: value} object to [{key: key, ref: value}] array
        surfaceProperties = Object.entries(osData.properties || {}).map(([key, ref]) => ({ key, ref }));

    } else { // CREATE MODE
        isEditMode = false;
        editingOSId = null;
        titleElement.textContent = "Create New Optical Surface";
        nameInput.value = '';
        nameInput.disabled = false;
        confirmButton.textContent = "Create Surface";
        
        // Set defaults
        modelSelect.value = 'glisur';
        finishSelect.value = 'polished';
        typeSelect.value = 'dielectric_dielectric';
        valueContainer.innerHTML = '';
        valueContainer.appendChild(ExpressionInput.create('os_value', 'Value', '1.0'));
    }

    rebuildPropertiesUI();
    modalElement.style.display = 'block';
}

function hide() {
    modalElement.style.display = 'none';
}

function rebuildPropertiesUI() {
    propertiesListDiv.innerHTML = '';
    const matrixDefines = Object.keys(currentProjectState.defines || {}).filter(k => currentProjectState.defines[k].type === 'matrix');

    surfaceProperties.forEach((prop, index) => {
        const row = document.createElement('div');
        row.className = 'property_item';

        const keyInput = document.createElement('input');
        keyInput.type = 'text';
        keyInput.placeholder = 'Property Name (e.g. REFLECTIVITY)';
        keyInput.value = prop.key;
        keyInput.style.flexGrow = '1';
        keyInput.dataset.index = index;
        keyInput.onchange = updatePropertyState;

        const refSelect = document.createElement('select');
        refSelect.dataset.index = index;
        populateSelect(refSelect, matrixDefines);
        refSelect.value = prop.ref;
        refSelect.onchange = updatePropertyState;

        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-op-btn';
        removeBtn.dataset.index = index;
        removeBtn.textContent = '×';
        removeBtn.onclick = removePropertyRow;

        row.appendChild(keyInput);
        row.appendChild(refSelect);
        row.appendChild(removeBtn);
        propertiesListDiv.appendChild(row);
    });
}

function addPropertyRow() {
    surfaceProperties.push({ key: '', ref: '' });
    rebuildPropertiesUI();
}

function removePropertyRow(event) {
    const index = parseInt(event.target.dataset.index, 10);
    surfaceProperties.splice(index, 1);
    rebuildPropertiesUI();
}

function updatePropertyState(event) {
    const index = parseInt(event.target.dataset.index, 10);
    const row = event.target.parentElement;
    const key = row.querySelector('input').value;
    const ref = row.querySelector('select').value;
    surfaceProperties[index] = { key, ref };
}

function populateSelect(selectElement, optionsArray) {
    selectElement.innerHTML = '<option value="">-- Select Matrix --</option>';
    optionsArray.forEach(optionText => {
        const option = document.createElement('option');
        option.value = optionText;
        option.textContent = optionText;
        selectElement.appendChild(option);
    });
}

function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) {
        alert("Please provide a name.");
        return;
    }

    // Convert local state array back to the object format the backend expects
    const propertiesObject = surfaceProperties.reduce((obj, prop) => {
        if (prop.key) obj[prop.key] = prop.ref;
        return obj;
    }, {});

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingOSId : name,
        name: name,
        model: modelSelect.value,
        finish: finishSelect.value,
        type: typeSelect.value,
        value: document.getElementById('os_value').value,
        properties: propertiesObject
    });

    hide();
}
