import * as THREE from 'three';

let modalElement, titleElement, nameInput, typeSelect, confirmButton, cancelButton, dynamicParamsDiv;
let onConfirmCallback = null;
let isEditMode = false;
let editingDefineId = null;

let currentExpression = '';
let recomputeButton;
let valueDisplay;
let getProjectStateCallback = null; // To get the current state for evaluation

export function initDefineEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;
    getProjectStateCallback = callbacks.getProjectState;

    modalElement = document.getElementById('defineEditorModal');
    titleElement = document.getElementById('defineEditorTitle');
    nameInput = document.getElementById('defineEditorName');
    typeSelect = document.getElementById('defineEditorType');
    confirmButton = document.getElementById('defineEditorConfirm');
    cancelButton = document.getElementById('defineEditorCancel');
    dynamicParamsDiv = document.getElementById('define-editor-params');

    // Add the new "Expression" option to the dropdown
    const expressionOption = document.createElement('option');
    expressionOption.value = "expression";
    expressionOption.textContent = "Expression";
    typeSelect.add(expressionOption, typeSelect.options[3]); // Add after Constant
    
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
        
        // Pass the raw expression or value object to populate the fields
        renderParamsUI(defineData.raw_expression, defineData.value);

    } else {
        // --- CREATE MODE ---
        isEditMode = false;
        editingDefineId = null;
        titleElement.textContent = "Create New Define";
        nameInput.value = '';
        nameInput.disabled = false;
        typeSelect.value = 'constant'; // Default to constant now
        typeSelect.disabled = false;
        confirmButton.textContent = "Create Define";
        renderParamsUI(); // Render with default values
    }
    modalElement.style.display = 'block';
}

function hide() {
    modalElement.style.display = 'none';
}

function renderParamsUI(rawExpr = null, evaluatedValue = null) {
    dynamicParamsDiv.innerHTML = '';
    const type = typeSelect.value;
    const p_in = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
    const raw = rawExpr || {};

    if (type === 'position' || type === 'scale') {
        dynamicParamsDiv.innerHTML = `
            <div class="property_item"><label for="def_x">X:</label><input type="text" id="def_x"></div>
            <div class="property_item"><label for="def_y">Y:</label><input type="text" id="def_y"></div>
            <div class="property_item"><label for="def_z">Z:</label><input type="text" id="def_z"></div>
            <div class="property_item"><label>Unit:</label><input type="text" value="mm" disabled></div>
        `;
        const defaultVal = (type === 'scale') ? '1' : '0';
        p_in('def_x', raw.x ?? defaultVal); p_in('def_y', raw.y ?? defaultVal); p_in('def_z', raw.z ?? defaultVal);

    } else if (type === 'rotation') {
        dynamicParamsDiv.innerHTML = `
            <div class="property_item"><label for="def_x">X:</label><input type="text" id="def_x"></div>
            <div class="property_item"><label for="def_y">Y:</label><input type="text" id="def_y"></div>
            <div class="property_item"><label for="def_z">Z:</label><input type="text" id="def_z"></div>
            <div class="property_item"><label>Unit:</label><input type="text" value="deg" disabled></div>
        `;
        p_in('def_x', raw.x ?? '0'); p_in('def_y', raw.y ?? '0'); p_in('def_z', raw.z ?? '0');

    } else if (type === 'constant') {
        dynamicParamsDiv.innerHTML = `<div class="property_item"><label>Value:</label><input type="number" id="def_const_val" step="any"></div>`;
        p_in('def_const_val', rawExpr || 0);

    } else if (type === 'expression') {
        dynamicParamsDiv.innerHTML = `
            <div class="property_item" style="flex-direction: column; align-items: flex-start;">
                <label for="def_expr_input">Expression:</label>
                <textarea id="def_expr_input" style="width: 95%; height: 60px;"></textarea>
            </div>
            <div class="property_item">
                 <button id="recompute_expr_btn">Recompute</button>
                 <label style="margin-left: 10px; width: auto;">Evaluated Value:</label>
                 <input type="text" id="def_expr_value" readonly style="flex-grow:1; background-color: #eee;">
            </div>
        `;
        document.getElementById('def_expr_input').value = rawExpr || '';
        document.getElementById('def_expr_value').value = evaluatedValue !== null ? evaluatedValue : 'N/A';

        recomputeButton = document.getElementById('recompute_expr_btn');
        valueDisplay = document.getElementById('def_expr_value');
        
        recomputeButton.addEventListener('click', handleRecompute);
    }
}

function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) { alert("Please provide a name."); return; }
    
    const type = typeSelect.value;
    let rawExpression, unit, category;

    if (type === 'position' || type === 'scale') {
        const p = (id) => document.getElementById(id).value;
        rawExpression = { x: p('def_x'), y: p('def_y'), z: p('def_z') };
        unit = 'mm'; category = 'length';
    } else if (type === 'rotation') {
        const p = (id) => document.getElementById(id).value;
        rawExpression = { x: p('def_x'), y: p('def_y'), z: p('def_z') };
        unit = 'deg'; category = 'angle';
    } else if (type === 'constant') {
        rawExpression = document.getElementById('def_const_val').value;
        unit = null; category = 'dimensionless';
    } else if (type === 'expression') {
        rawExpression = document.getElementById('def_expr_input').value;
        unit = null; category = 'dimensionless';
        // Final validation before confirming
        if (!handleRecompute()) { // handleRecompute returns false on error
            alert("Cannot save an invalid expression. Please correct it.");
            return;
        }
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

function handleRecompute() {
    const exprInput = document.getElementById('def_expr_input');
    const expression = exprInput.value;
    
    // Use an external evaluator (like math.js or a custom one)
    // For now, we'll simulate it, assuming we have a function to call
    // that safely evaluates the expression.
    try {
        const result = evaluateInContext(expression);
        valueDisplay.value = result;
        valueDisplay.style.color = 'black';
        return true; // Success
    } catch (error) {
        valueDisplay.value = `Error: ${error.message}`;
        valueDisplay.style.color = 'red';
        return false; // Failure
    }
}

// --- mock evaluator function ---
// In a real app, this would be more robust or call a backend endpoint
function evaluateInContext(expression) {
    const projectState = getProjectStateCallback();
    if (!projectState) {
        throw new Error("Project state not available.");
    }

    const context = {
        pi: Math.PI,
        PI: Math.PI,
        ...Object.fromEntries(
            Object.values(projectState.defines).map(d => [d.name, d.value])
        )
    };
    
    // A simple, safer evaluator using Function constructor
    // WARNING: Still not 100% secure for untrusted input, but better than direct eval()
    const contextKeys = Object.keys(context);
    const contextValues = Object.values(context);
    
    const func = new Function(...contextKeys, `return ${expression}`);
    const result = func(...contextValues);

    if (typeof result !== 'number') {
        throw new Error("Expression did not result in a number.");
    }
    return result;
}