// FILE: virtual-pet/static/defineEditor.js

import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, typeSelect, confirmButton, cancelButton, dynamicParamsDiv;
let onConfirmCallback = null;
let isEditMode = false;
let editingDefineId = null;
let currentProjectState = null;

export function initDefineEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;

    modalElement = document.getElementById('defineEditorModal');
    titleElement = document.getElementById('defineEditorTitle');
    nameInput = document.getElementById('defineEditorName');
    typeSelect = document.getElementById('defineEditorType');
    confirmButton = document.getElementById('defineEditorConfirm');
    cancelButton = document.getElementById('defineEditorCancel');
    dynamicParamsDiv = document.getElementById('define-editor-params');
    
    // Remove the "Expression" option if it exists from previous version
    const expressionOption = typeSelect.querySelector('option[value="expression"]');
    if(expressionOption) expressionOption.remove();

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    typeSelect.addEventListener('change', () => renderParamsUI());

    console.log("Define Editor Initialized.");
}

export function show(defineData = null, projectState = null) {
    currentProjectState = projectState; // Cache the project state for context

    if (defineData && defineData.name) {
        // EDIT MODE
        isEditMode = true;
        editingDefineId = defineData.name;
        titleElement.textContent = `Edit Define: ${defineData.name}`;
        nameInput.value = defineData.name;
        nameInput.disabled = true;
        typeSelect.value = defineData.type;
        typeSelect.disabled = true;
        confirmButton.textContent = "Update Define";
        renderParamsUI(defineData.raw_expression);
    } else {
        // CREATE MODE
        isEditMode = false;
        editingDefineId = null;
        titleElement.textContent = "Create New Define";
        nameInput.value = '';
        nameInput.disabled = false;
        typeSelect.value = 'constant';
        typeSelect.disabled = false;
        confirmButton.textContent = "Create Define";
        renderParamsUI();
    }
    modalElement.style.display = 'block';
}

function hide() {
    modalElement.style.display = 'none';
}

function renderParamsUI(rawExpr = null) {
    dynamicParamsDiv.innerHTML = '';
    const type = typeSelect.value;
    
    if (type === 'constant' || type === 'quantity') {
        // For simple defines, create a single expression input.
        // If editing, `rawExpr` will be a string. If creating, it's null.
        const initialValue = rawExpr !== null ? String(rawExpr) : '0';
        dynamicParamsDiv.appendChild(
            ExpressionInput.create('def_expr_value', 'Value', initialValue, currentProjectState)
        );
    } else if (type === 'position' || type === 'rotation' || type === 'scale') {
        // For compound defines, create an input for each axis.
        // If editing, `rawExpr` is a dict like {x: 'val_x', ...}. If creating, it's null.
        const initialX = rawExpr?.x || '0';
        const initialY = rawExpr?.y || '0';
        const initialZ = rawExpr?.z || '0';

        dynamicParamsDiv.appendChild(ExpressionInput.create('def_expr_x', 'Value X', initialX, currentProjectState));
        dynamicParamsDiv.appendChild(ExpressionInput.create('def_expr_y', 'Value Y', initialY, currentProjectState));
        dynamicParamsDiv.appendChild(ExpressionInput.create('def_expr_z', 'Value Z', initialZ, currentProjectState));
    }
}

async function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) {
        alert("Please provide a name.");
        return;
    }
    
    const type = typeSelect.value;
    let rawExpression, unit, category;

    if (type === 'constant' || type === 'quantity') {
        rawExpression = document.getElementById('def_expr_value').value;
        unit = (type === 'quantity') ? 'mm' : null; // This is a simplification; a unit dropdown could be added.
        category = (type === 'quantity') ? 'length' : 'dimensionless';

    } else if (type === 'position' || type === 'rotation' || type === 'scale') {
        rawExpression = {
            x: document.getElementById('def_expr_x').value,
            y: document.getElementById('def_expr_y').value,
            z: document.getElementById('def_expr_z').value
        };
        if (type === 'rotation') { unit = 'deg'; category = 'angle'; }
        else if (type === 'position') { unit = 'mm'; category = 'length'; }
        else { unit = null; category = 'dimensionless'; }
    } else {
        alert("Unknown define type selected.");
        return;
    }

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingDefineId : name,
        name: name,
        type: type,
        raw_expression: rawExpression,
        unit: unit,
        category: category
    });
    hide();
}