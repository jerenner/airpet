// static/isotopeEditor.js

let modalElement, titleElement, nameInput, zInput, nInput, aInput,
    confirmButton, cancelButton;
let onConfirmCallback = null;
let isEditMode = false;
let editingIsotopeId = null;

export function initIsotopeEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;
    modalElement = document.getElementById('isotopeEditorModal');
    titleElement = document.getElementById('isotopeEditorTitle');
    nameInput = document.getElementById('isoEditorName');
    zInput = document.getElementById('isoEditorZ');
    nInput = document.getElementById('isoEditorN');
    aInput = document.getElementById('isoEditorA');
    confirmButton = document.getElementById('isoEditorConfirm');
    cancelButton = document.getElementById('isoEditorCancel');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);

    console.log("Isotope Editor Initialized.");
}

export function show(isoData = null) {
    if (isoData) { // EDIT MODE
        isEditMode = true;
        editingIsotopeId = isoData.name;
        titleElement.textContent = `Edit Isotope: ${isoData.name}`;
        nameInput.value = isoData.name;
        nameInput.disabled = true;
        zInput.value = isoData.Z || '';
        nInput.value = isoData.N || '';
        aInput.value = isoData.A_expr || '';
        confirmButton.textContent = "Update Isotope";
    } else { // CREATE MODE
        isEditMode = false;
        editingIsotopeId = null;
        titleElement.textContent = "Create New Isotope";
        nameInput.value = '';
        nameInput.disabled = false;
        zInput.value = '';
        nInput.value = '';
        aInput.value = '';
        confirmButton.textContent = "Create Isotope";
    }
    modalElement.style.display = 'block';
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
    
    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingIsotopeId : name,
        name: name,
        Z: zInput.value.trim(),
        N: nInput.value.trim(),
        A_expr: aInput.value.trim()
    });

    hide();
}
