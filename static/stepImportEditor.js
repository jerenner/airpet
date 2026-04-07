// static/stepImportEditor.js
import * as ExpressionInput from './expressionInput.js';
import { buildCadImportReimportContext } from './cadImportUi.js';

// --- Module-level variables ---
let modalElement, confirmButton, cancelButton, stepFileNameEl,
    stepImportGroupName, stepImportParentLV, stepImportOffsetContainer,
    stepSmartImportCheckbox, stepImportModalTitle, stepImportContextNotice;

let reportModalElement, closeReportButton, stepImportReportSummary, stepImportReportTableBody;

let currentFile = null;
let onConfirmCallback = null;
let currentProjectState = null;
let currentImportContext = null;

/**
 * Initializes the STEP Import Editor modal and its event listeners.
 * @param {object} callbacks - An object containing callback functions, expecting `onConfirm`.
 */
export function initStepImportEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;

    modalElement = document.getElementById('stepImportModal');
    confirmButton = document.getElementById('confirmStepImport');
    cancelButton = document.getElementById('cancelStepImport');
    stepFileNameEl = document.getElementById('stepFileName');
    stepImportGroupName = document.getElementById('stepImportGroupName');
    stepImportParentLV = document.getElementById('stepImportParentLV');
    stepImportOffsetContainer = document.getElementById('stepImportOffsetInputs');
    stepSmartImportCheckbox = document.getElementById('stepSmartImportCheckbox');
    stepImportModalTitle = document.getElementById('stepImportModalTitle');
    stepImportContextNotice = document.getElementById('stepImportContextNotice');

    reportModalElement = document.getElementById('stepImportReportModal');
    closeReportButton = document.getElementById('closeStepImportReport');
    stepImportReportSummary = document.getElementById('stepImportReportSummary');
    stepImportReportTableBody = document.getElementById('stepImportReportTableBody');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    if (closeReportButton) closeReportButton.addEventListener('click', hideReport);
    
    console.log("STEP Import Editor Initialized.");
}

/**
 * Shows the STEP import modal and populates it with initial data.
 * @param {File} file - The STEP file selected by the user.
 * @param {object} projectState - The current full project state for context.
 */
export function show(file, projectState, importRecord = null) {
    currentFile = file;
    currentProjectState = projectState;
    currentImportContext = importRecord ? buildCadImportReimportContext(importRecord) : null;
    
    stepFileNameEl.textContent = file.name;
    if (stepImportModalTitle) {
        stepImportModalTitle.textContent = currentImportContext
            ? 'Reimport STEP File Options'
            : 'Import STEP File Options';
    }

    if (stepImportContextNotice) {
        if (currentImportContext) {
            stepImportContextNotice.hidden = false;
            stepImportContextNotice.textContent = currentImportContext.noticeText;
        } else {
            stepImportContextNotice.hidden = true;
            stepImportContextNotice.textContent = '';
        }
    }

    // Create a default grouping name from the filename, sanitized for GDML.
    stepImportGroupName.value = currentImportContext?.groupingName || file.name.replace(/\.[^/.]+$/, "").replace(/[\s\W]/g, '_');

    // Populate the parent LV dropdown with LVs that can contain children.
    const placeableLVs = Object.keys(projectState.logical_volumes || {})
        .filter(lvName => projectState.logical_volumes[lvName]?.content_type === 'physvol');
    populateSelect(stepImportParentLV, placeableLVs);

    // Default the selection to the world volume if it exists.
    const preferredParentLV = currentImportContext?.parentLVName;
    if (preferredParentLV && placeableLVs.includes(preferredParentLV)) {
        stepImportParentLV.value = preferredParentLV;
    } else if (projectState.world_volume_ref && placeableLVs.includes(projectState.world_volume_ref)) {
        stepImportParentLV.value = projectState.world_volume_ref;
    }

    // Create the expression inputs for the placement offset.
    stepImportOffsetContainer.innerHTML = '';
    const offset = currentImportContext?.offset || { x: '0', y: '0', z: '0' };
    stepImportOffsetContainer.appendChild(ExpressionInput.create('step_offset_x', 'X', offset.x || '0'));
    stepImportOffsetContainer.appendChild(ExpressionInput.create('step_offset_y', 'Y', offset.y || '0'));
    stepImportOffsetContainer.appendChild(ExpressionInput.create('step_offset_z', 'Z', offset.z || '0'));

    const assemblyRadio = document.getElementById('step_mode_assembly');
    const individualRadio = document.getElementById('step_mode_individual');
    const placementMode = currentImportContext?.placementMode || 'assembly';
    if (assemblyRadio && individualRadio) {
        assemblyRadio.checked = placementMode !== 'individual';
        individualRadio.checked = placementMode === 'individual';
    }

    if (stepSmartImportCheckbox) {
        stepSmartImportCheckbox.checked = currentImportContext ? Boolean(currentImportContext.smartImport) : true;
    }

    if (confirmButton) {
        confirmButton.textContent = currentImportContext ? 'Reimport' : 'Import';
    }

    modalElement.style.display = 'block';
}

/**
 * Hides the STEP import modal.
 */
function hide() {
    modalElement.style.display = 'none';
    currentFile = null;
    currentProjectState = null;
    currentImportContext = null;
    if (confirmButton) {
        confirmButton.textContent = 'Import';
    }
    if (stepImportModalTitle) {
        stepImportModalTitle.textContent = 'Import STEP File Options';
    }
    if (stepImportContextNotice) {
        stepImportContextNotice.hidden = true;
        stepImportContextNotice.textContent = '';
    }
}

/**
 * Handles the confirm button click, gathering data and calling the main controller.
 */
function handleConfirm() {
    if (onConfirmCallback) {
        const options = {
            file: currentFile,
            groupingName: stepImportGroupName.value.trim(),
            placementMode: document.querySelector('input[name="step_placement_mode"]:checked').value,
            parentLVName: stepImportParentLV.value,
            offset: {
                x: document.getElementById('step_offset_x').value,
                y: document.getElementById('step_offset_y').value,
                z: document.getElementById('step_offset_z').value
            },
            smartImport: !!(stepSmartImportCheckbox && stepSmartImportCheckbox.checked)
        };
        if (currentImportContext?.reimportTargetImportId) {
            options.reimportTargetImportId = currentImportContext.reimportTargetImportId;
        }
        onConfirmCallback(options);
    }
    hide();
}

function hideReport() {
    if (reportModalElement) reportModalElement.style.display = 'none';
}

function _formatModeCell(mode) {
    const safeMode = (mode === 'primitive') ? 'primitive' : 'tessellated';
    return `<span class="step-report-mode-pill ${safeMode}">${safeMode}</span>`;
}

export function showImportReport(report, fileName = '') {
    if (!reportModalElement || !stepImportReportSummary || !stepImportReportTableBody) return;

    const summary = report?.summary || {};
    const total = summary.total || 0;
    const selected = summary.selected_mode_counts || {};
    const primitiveSelected = selected.primitive || 0;
    const tessSelected = selected.tessellated || 0;
    const primitivePct = total > 0 ? ((summary.selected_primitive_ratio || 0) * 100).toFixed(1) : '0.0';

    stepImportReportSummary.textContent = [
        fileName ? `File: ${fileName}` : null,
        `Total solids: ${total}`,
        `Selected primitive: ${primitiveSelected} (${primitivePct}%)`,
        `Selected tessellated fallback: ${tessSelected}`
    ].filter(Boolean).join(' | ');

    const candidates = Array.isArray(report?.candidates) ? report.candidates : [];
    stepImportReportTableBody.innerHTML = '';

    if (candidates.length === 0) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td colspan="5" style="color:#64748b;">No candidate details available.</td>`;
        stepImportReportTableBody.appendChild(tr);
    } else {
        const maxRows = 500;
        const rows = candidates.slice(0, maxRows);

        rows.forEach(c => {
            const tr = document.createElement('tr');
            const selectedMode = c?.selected_mode || 'tessellated';
            const conf = Number.isFinite(Number(c?.confidence)) ? Number(c.confidence).toFixed(3) : 'n/a';
            tr.innerHTML = `
                <td>${c?.source_id || ''}</td>
                <td>${c?.classification || ''}</td>
                <td>${_formatModeCell(selectedMode)}</td>
                <td>${conf}</td>
                <td>${c?.fallback_reason || ''}</td>
            `;
            stepImportReportTableBody.appendChild(tr);
        });

        if (candidates.length > maxRows) {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td colspan="5" style="color:#64748b;">Showing first ${maxRows} rows of ${candidates.length} candidates.</td>`;
            stepImportReportTableBody.appendChild(tr);
        }
    }

    reportModalElement.style.display = 'block';
}

/**
 * Helper function to populate a select dropdown.
 * @param {HTMLSelectElement} selectElement - The dropdown element.
 * @param {string[]} optionsArray - An array of strings for the options.
 */
function populateSelect(selectElement, optionsArray) {
    selectElement.innerHTML = '';
    optionsArray.forEach(optionText => {
        const option = document.createElement('option');
        option.value = optionText;
        option.textContent = optionText;
        selectElement.appendChild(option);
    });
}
