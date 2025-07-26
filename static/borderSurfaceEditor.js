// static/borderSurfaceEditor.js

let modalElement, titleElement, nameInput, pv1Select, pv2Select, surfaceSelect,
    confirmButton, cancelButton;
let onConfirmCallback = null;
let isEditMode = false;
let editingBSId = null;
let currentProjectState = null;
let allPhysicalVolumes = {}; // We will store PVs as { id: name }

// Helper function to recursively find all PVs
function findAllPVs(projectState) {
    const pvs = {};
    if (!projectState || !projectState.logical_volumes) return pvs;

    function traverseLV(lv) {
        if (lv.content_type === 'physvol') {
            lv.content.forEach(pv => {
                pvs[pv.id] = pv.name || `(unnamed PV of ${pv.volume_ref})`;
                // Recurse into the placed LV
                const childLV = projectState.logical_volumes[pv.volume_ref];
                if (childLV) {
                    traverseLV(childLV);
                }
            });
        }
        // Note: This simple traversal doesn't unroll procedural volumes.
        // A more advanced version would be needed to select replica instances.
        // For now, we only list explicitly placed PVs.
    }

    // Start traversal from the world volume's children
    const worldLV = projectState.logical_volumes[projectState.world_volume_ref];
    if (worldLV) {
        traverseLV(worldLV);
    }
    
    return pvs;
}


export function initBorderSurfaceEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;
    modalElement = document.getElementById('borderSurfaceEditorModal');
    titleElement = document.getElementById('borderSurfaceEditorTitle');
    nameInput = document.getElementById('bsEditorName');
    pv1Select = document.getElementById('bsEditorPV1Ref');
    pv2Select = document.getElementById('bsEditorPV2Ref');
    surfaceSelect = document.getElementById('bsEditorSurfaceRef');
    confirmButton = document.getElementById('bsEditorConfirm');
    cancelButton = document.getElementById('bsEditorCancel');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);

    console.log("Border Surface Editor Initialized.");
}

export function show(bsData = null, projectState = null) {
    currentProjectState = projectState;
    if (!projectState) return;

    allPhysicalVolumes = findAllPVs(projectState);

    // Populate dropdowns
    populateSelect(pv1Select, allPhysicalVolumes);
    populateSelect(pv2Select, allPhysicalVolumes);
    
    // We need to convert the array of surface names into an object like { name: name }
    // for populateSelect to work correctly.
    const opticalSurfaces = projectState.optical_surfaces || {};
    const surfaceOptions = Object.keys(opticalSurfaces).reduce((acc, name) => {
        acc[name] = name; // The key and the value are both the surface name
        return acc;
    }, {});
    
    populateSelect(surfaceSelect, surfaceOptions);

    if (bsData) { // EDIT MODE
        isEditMode = true;
        editingBSId = bsData.name;
        titleElement.textContent = `Edit Border Surface: ${bsData.name}`;
        nameInput.value = bsData.name;
        nameInput.disabled = true;
        confirmButton.textContent = "Update Surface";

        pv1Select.value = bsData.physvol1_ref;
        pv2Select.value = bsData.physvol2_ref;
        surfaceSelect.value = bsData.surfaceproperty_ref;

    } else { // CREATE MODE
        isEditMode = false;
        editingBSId = null;
        titleElement.textContent = "Create New Border Surface";
        nameInput.value = '';
        nameInput.disabled = false;
        confirmButton.textContent = "Create Surface";
    }

    modalElement.style.display = 'block';
}

function hide() {
    modalElement.style.display = 'none';
}

function populateSelect(selectElement, optionsObject) {
    selectElement.innerHTML = '';
    for (const [key, value] of Object.entries(optionsObject)) {
        const option = document.createElement('option');
        option.value = key;   // The key is the ID (for PVs) or name (for surfaces)
        option.textContent = value; // The value is the display name
        selectElement.appendChild(option);
    }
}

function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) { alert("Please provide a name."); return; }

    const pv1Ref = pv1Select.value;
    const pv2Ref = pv2Select.value;
    const surfaceRef = surfaceSelect.value;

    if (!pv1Ref || !pv2Ref || !surfaceRef) {
        alert("Please select two Physical Volumes and an Optical Surface.");
        return;
    }
    if (pv1Ref === pv2Ref) {
        alert("The two Physical Volumes cannot be the same.");
        return;
    }

    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingBSId : name,
        name: name,
        physvol1_ref: pv1Ref,
        physvol2_ref: pv2Ref,
        surfaceproperty_ref: surfaceRef
    });

    hide();
}
