// FILE: virtual-pet/static/defineEditor.js

import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, typeSelect, confirmButton, cancelButton, dynamicParamsDiv;
let onConfirmCallback = null;
let isEditMode = false;
let editingDefineId = null;
let currentProjectState = null;
let matrixState = { coldim: 2, values: [['', '']] };

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

        // Handle matrix data for editing
        let initialValue = defineData.raw_expression;
        if (defineData.type === 'matrix') {
            const { coldim = 2, values = [] } = defineData.raw_expression || {};
            matrixState.coldim = parseInt(coldim, 10);
            // Convert flat array to 2D array for the UI state
            matrixState.values = [];
            for (let i = 0; i < values.length; i += matrixState.coldim) {
                matrixState.values.push(values.slice(i, i + matrixState.coldim));
            }
            if (matrixState.values.length === 0) matrixState.values.push(Array(matrixState.coldim).fill('')); // Ensure at least one row
            initialValue = null; // We've handled it
        }
        renderParamsUI(initialValue);
    } else {
        // CREATE MODE
        isEditMode = false;
        editingDefineId = null;
        matrixState = { coldim: 2, values: [['', '']] }; // Reset matrix state
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
    } else if (type === 'matrix') { // NEW: Matrix UI rendering
        dynamicParamsDiv.innerHTML = `
            <div class="property_item">
                <label for="def_matrix_coldim">Columns:</label>
                <input type="number" id="def_matrix_coldim" min="1" step="1" value="${matrixState.coldim}" style="width: 60px;">
            </div>
            <div id="def_matrix_grid_container"></div>
            <div style="margin-top: 10px; display: flex; gap: 10px;">
                <button id="def_matrix_add_row" class="add_button" style="font-size: 12px; padding: 3px 8px;">+ Add Row</button>
                <button id="def_matrix_remove_row" class="add_button" style="font-size: 12px; padding: 3px 8px; background-color: #e57373;">- Remove Row</button>
            </div>
        `;
        document.getElementById('def_matrix_coldim').addEventListener('change', handleColDimChange);
        document.getElementById('def_matrix_add_row').addEventListener('click', handleAddMatrixRow);
        document.getElementById('def_matrix_remove_row').addEventListener('click', handleRemoveMatrixRow);
        rebuildMatrixUI();
    }
}

// Helper functions for the matrix editor UI
function handleColDimChange(event) {
    const newColDim = Math.max(1, parseInt(event.target.value, 10));
    matrixState.coldim = newColDim;
    matrixState.values = matrixState.values.map(row => {
        const newRow = row.slice(0, newColDim);
        while (newRow.length < newColDim) {
            newRow.push('');
        }
        return newRow;
    });
    rebuildMatrixUI();
}

function handleAddMatrixRow() {
    matrixState.values.push(Array(matrixState.coldim).fill(''));
    rebuildMatrixUI();

    // Focus the first cell of the new row for better UX
    const newRowIndex = matrixState.values.length - 1;
    const firstInputOfNewRow = document.getElementById(`def_matrix_${newRowIndex}_0`);
    if (firstInputOfNewRow) {
        firstInputOfNewRow.focus();
    }
}

function handleRemoveMatrixRow() {
    if (matrixState.values.length > 1) { // Prevent removing the last row
        matrixState.values.pop();
        rebuildMatrixUI();
    }
}

function rebuildMatrixUI() {
    const container = document.getElementById('def_matrix_grid_container');
    if (!container) return;

    container.innerHTML = '';
    const grid = document.createElement('div');
    grid.style.display = 'grid';
    // Dynamically create a header row
    let gridTemplateColumns = '';
    for (let i = 0; i < matrixState.coldim; i++) {
        gridTemplateColumns += 'minmax(100px, 1fr) '; // Give columns a min width but let them expand
        const header = document.createElement('div');
        header.textContent = `Col ${i + 1}`;
        header.style.fontWeight = 'bold';
        header.style.textAlign = 'center';
        header.style.fontSize = '12px';
        header.style.marginBottom = '4px';
        grid.appendChild(header);
    }
    grid.style.gridTemplateColumns = gridTemplateColumns.trim();
    grid.style.gap = '5px';
    grid.style.alignItems = 'center';

    matrixState.values.forEach((row, rowIndex) => {
        row.forEach((cellValue, colIndex) => {
            // Use our ExpressionInput component for each cell
            const cellComponent = ExpressionInput.createInline(
                `def_matrix_${rowIndex}_${colIndex}`, // Unique ID
                cellValue,
                currentProjectState,
                (newValue) => { // onChange callback
                    matrixState.values[rowIndex][colIndex] = newValue;
                }
            );
            grid.appendChild(cellComponent);
        });
    });
    container.appendChild(grid);
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
    } else if (type === 'matrix') { // Collect matrix data
        const coldim = parseInt(document.getElementById('def_matrix_coldim').value, 10);
        // Flatten the 2D array of expression strings into a 1D array
        const values = matrixState.values.flat(); 

        if (values.some(v => v.trim() === '')) {
            alert('All matrix cells must contain a value or expression.');
            return;
        }
        if (values.length > 0 && values.length % coldim !== 0) {
            alert(`Matrix data is incomplete. The total number of values (${values.length}) must be a multiple of the number of columns (${coldim}).`);
            return;
        }
        rawExpression = {
            coldim: coldim.toString(),
            values: values
        };
        unit = null;
        category = 'matrix';
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