// FILE: virtual-pet/static/defineEditor.js

import * as THREE from 'three';
import * as APIService from './apiService.js';

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
    
    // Remove the "Expression" option if it exists from previous version
    const expressionOption = typeSelect.querySelector('option[value="expression"]');
    if(expressionOption) expressionOption.remove();

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    typeSelect.addEventListener('change', () => renderParamsUI());

    console.log("Define Editor Initialized.");
}

export function show(defineData = null) {
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
    
    const createExpressionUI = (label, exprId, initialExpr) => `
        <div class="property_item" style="flex-direction: column; align-items: flex-start;">
            <label for="${exprId}">${label}:</label>
            <input type="text" id="${exprId}" class="expression-input" value="${initialExpr}" style="width: 95%; font-family: monospace;">
        </div>
    `;

    if (type === 'constant' || type === 'quantity') {
        dynamicParamsDiv.innerHTML = createExpressionUI('Value / Expression', 'def_expr_input', rawExpr !== null ? rawExpr : '0');
    } else if (type === 'position' || type === 'rotation' || type === 'scale') {
        let uiHTML = '';
        const raw = (rawExpr && typeof rawExpr === 'object') ? rawExpr : {};
        ['x', 'y', 'z'].forEach(axis => {
            uiHTML += createExpressionUI(axis.toUpperCase(), `def_expr_${axis}`, raw[axis] !== undefined ? raw[axis] : '0');
        });
        uiHTML += `<div class="property_item"><label>Unit:</label><input type="text" value="${type === 'rotation' ? 'deg' : (type === 'position' ? 'mm' : 'N/A')}" disabled></div>`;
        dynamicParamsDiv.innerHTML = uiHTML;
    }
}

async function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) { alert("Please provide a name."); return; }
    
    const type = typeSelect.value;
    let rawExpression, unit, category;

    if (type === 'constant' || type === 'quantity') {
        rawExpression = document.getElementById('def_expr_input').value;
        unit = (type === 'quantity') ? 'mm' : null; // Example, could be made dynamic
        category = 'dimensionless';
    } else if (type === 'position' || type === 'rotation' || type === 'scale') {
        rawExpression = {
            x: document.getElementById('def_expr_x').value,
            y: document.getElementById('def_expr_y').value,
            z: document.getElementById('def_expr_z').value
        };
        if (type === 'rotation') { unit = 'deg'; category = 'angle'; }
        else if (type === 'position') { unit = 'mm'; category = 'length'; }
        else { unit = null; category = 'dimensionless'; }
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