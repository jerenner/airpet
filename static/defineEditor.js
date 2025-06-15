import * as THREE from 'three';

let modalElement, titleElement, nameInput, typeSelect, confirmButton, cancelButton, dynamicParamsDiv;
let onConfirmCallback = null;
let isEditMode = false;
let editingDefineId = null;

export function initDefineEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;

    modalElement = document.getElementById('defineEditorModal');
    titleElement = document.getElementById('defineEditorTitle');
    nameInput = document.getElementById('defineEditorName');
    typeSelect = document.getElementById('defineEditorType');
    confirmButton = document.getElementById('defineEditorConfirm');
    cancelButton = document.getElementById('defineEditorCancel');
    dynamicParamsDiv = document.getElementById('define-editor-params');
    
    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    typeSelect.addEventListener('change', () => renderParamsUI()); // Pass no params on change

    console.log("Define Editor Initialized.");
}

export function show(defineData = null) {
    if (defineData && defineData.name) {
        // --- EDIT MODE ---
        isEditMode = true;
        editingDefineId = defineData.name;
        titleElement.textContent = `Edit Define: ${defineData.name}`;
        nameInput.value = defineData.name;
        nameInput.disabled = true;
        typeSelect.value = defineData.type;
        typeSelect.disabled = true;
        confirmButton.textContent = "Update Define";
        // Pass the define's value object to populate the fields
        renderParamsUI(defineData.value);
    } else {
        // --- CREATE MODE ---
        isEditMode = false;
        editingDefineId = null;
        titleElement.textContent = "Create New Define";
        nameInput.value = '';
        nameInput.disabled = false;
        typeSelect.value = 'position'; // Default to position
        typeSelect.disabled = false;
        confirmButton.textContent = "Create Define";
        renderParamsUI(); // Render with default values
    }
    modalElement.style.display = 'block';
}

function hide() {
    modalElement.style.display = 'none';
}

function renderParamsUI(value = null) {
    dynamicParamsDiv.innerHTML = '';
    const type = typeSelect.value;
    const p_in = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
    const v = value || {}; // Use empty object for defaults if value is null

    if (type === 'position' || type === 'scale') {
        dynamicParamsDiv.innerHTML = `
            <div class="property_item"><label for="def_x">X:</label><input type="number" id="def_x" step="any" value="0"></div>
            <div class="property_item"><label for="def_y">Y:</label><input type="number" id="def_y" step="any" value="0"></div>
            <div class="property_item"><label for="def_z">Z:</label><input type="number" id="def_z" step="any" value="0"></div>
            <div class="property_item"><label>Unit:</label><input type="text" value="mm" disabled></div>
        `;
        // For scale, the default should be 1
        const defaultVal = (type === 'scale') ? 1 : 0;
        p_in('def_x', v.x ?? defaultVal); p_in('def_y', v.y ?? defaultVal); p_in('def_z', v.z ?? defaultVal);

    } else if (type === 'rotation') {
        dynamicParamsDiv.innerHTML = `
            <div class="property_item"><label for="def_x">X:</label><input type="number" id="def_x" step="any" value="0"></div>
            <div class="property_item"><label for="def_y">Y:</label><input type="number" id="def_y" step="any" value="0"></div>
            <div class="property_item"><label for="def_z">Z:</label><input type="number" id="def_z" step="any" value="0"></div>
            <div class="property_item"><label>Unit:</label><input type="text" value="deg" disabled></div>
        `;
        // Convert rad from backend to deg for UI
        p_in('def_x', THREE.MathUtils.radToDeg(v.x || 0));
        p_in('def_y', THREE.MathUtils.radToDeg(v.y || 0));
        p_in('def_z', THREE.MathUtils.radToDeg(v.z || 0));

    } else if (type === 'constant') {
        dynamicParamsDiv.innerHTML = `<div class="property_item"><label>Value:</label><input type="number" id="def_const_val" step="any" value="0"></div>`;
        p_in('def_const_val', v || 0);
    }
}

function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) { alert("Please provide a name."); return; }
    
    const type = typeSelect.value;
    let value, unit, category;

    if (type === 'position' || type === 'scale') {
        const p = (id) => parseFloat(document.getElementById(id).value);
        value = { x: p('def_x'), y: p('def_y'), z: p('def_z') };
        unit = 'mm'; category = 'length';
    } else if (type === 'rotation') {
        const p = (id) => parseFloat(document.getElementById(id).value);
        const degValue = { x: p('def_x'), y: p('def_y'), z: p('def_z') };
        // Convert UI deg to backend rad before sending
        value = { x: THREE.MathUtils.degToRad(degValue.x), y: THREE.MathUtils.degToRad(degValue.y), z: THREE.MathUtils.degToRad(degValue.z) };
        unit = 'rad'; category = 'angle';
    } else if (type === 'constant') {
        value = parseFloat(document.getElementById('def_const_val').value);
        unit = null; category = 'dimensionless';
    }

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingDefineId : name,
        name: name, // Name is same as ID for defines
        type: type,
        value: value,
        unit: unit,
        category: category
    });
    hide();
}