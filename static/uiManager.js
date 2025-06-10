// static/uiManager.js
import * as THREE from 'three';

import * as SolidEditor from './solidEditor.js';

// --- Module-level variables for DOM elements ---
let gdmlFileInput, newProjectButton, loadGdmlButton, exportGdmlButton,
    saveProjectButton, loadProjectButton, projectFileInput,
    deleteSelectedObjectButton,
    modeObserveButton, modeTranslateButton, modeRotateButton, modeScaleButton,
    toggleWireframeButton, toggleGridButton,
    cameraModeOrbitButton, cameraModeFlyButton,
    toggleSnapToGridButton, gridSnapSizeInput, angleSnapSizeInput,
    currentModeDisplay;

// Hierarchy and Inspector
let structureTreeRoot, definesListRoot, materialsListRoot, solidsListRoot;
let inspectorContentDiv;
let currentlyInspectedUIItem = null; // { type, id, name, element (DOM in hierarchy) }

// Add Object Modal
let addObjectModal, modalBackdrop, newObjectTypeSelect, newObjectNameInput, newObjectParamsDiv, confirmAddObjectButton, cancelAddObjectButton;

// Callbacks to main.js (controller logic)
let callbacks = {
    onNewProjectClicked: () => {},
    onLoadGdmlClicked: () => {},
    onLoadProjectClicked: () => {},
    onGdmlFileSelected: (file) => {},
    onEditSolidClicked: (solidData) => {},
    onProjectFileSelected: (file) => {},
    onSaveProjectClicked: () => {},
    onExportGdmlClicked: () => {},
    onAddObjectClicked: () => {}, // To show modal
    onConfirmAddObject: (type, name, params) => {},
    onDeleteSelectedClicked: () => {},
    onModeChangeClicked: (mode) => {},
    onSnapToggleClicked: () => {},
    onSnapSettingsChanged: (transSnap, angleSnap) => {},
    onCameraModeChangeClicked: (mode) => {},
    onWireframeToggleClicked: () => {},
    onGridToggleClicked: () => {},
    onHierarchyItemSelected: (itemContext) => {}, // {type, id, name, data}
    onInspectorPropertyChanged: (type, id, path, value) => {}
};

// --- Initialization ---
export function initUI(cb) {
    callbacks = {...callbacks, ...cb}; // Merge provided callbacks

    // Get Menu Buttons
    newProjectButton = document.getElementById('newProjectButton');
    loadGdmlButton = document.getElementById('loadGdmlButton');
    gdmlFileInput = document.getElementById('gdmlFile');
    exportGdmlButton = document.getElementById('exportGdmlButton');
    saveProjectButton = document.getElementById('saveProjectButton');
    loadProjectButton = document.getElementById('loadProjectButton');
    projectFileInput = document.getElementById('projectFile');
    deleteSelectedObjectButton = document.getElementById('deleteSelectedObjectButton');

    // Add buttons
    const addButtons = document.querySelectorAll('.add_button');

    // Mode Buttons
    modeObserveButton = document.getElementById('modeObserveButton');
    modeTranslateButton = document.getElementById('modeTranslateButton');
    modeRotateButton = document.getElementById('modeRotateButton');
    modeScaleButton = document.getElementById('modeScaleButton'); // If you add it
    currentModeDisplay = document.getElementById('currentModeDisplay');

    // View Menu Buttons
    toggleWireframeButton = document.getElementById('toggleWireframeButton');
    toggleGridButton = document.getElementById('toggleGridButton');
    cameraModeOrbitButton = document.getElementById('cameraModeOrbitButton');
    cameraModeFlyButton = document.getElementById('cameraModeFlyButton');

    // Edit Menu / Snap Buttons
    toggleSnapToGridButton = document.getElementById('toggleSnapToGridButton');
    gridSnapSizeInput = document.getElementById('gridSnapSizeInput');
    angleSnapSizeInput = document.getElementById('angleSnapSizeInput');

    // Hierarchy and Inspector Roots
    structureTreeRoot = document.getElementById('structure_tree_root');
    definesListRoot = document.getElementById('defines_list_root');
    materialsListRoot = document.getElementById('materials_list_root');
    solidsListRoot = document.getElementById('solids_list_root');
    inspectorContentDiv = document.getElementById('inspector_content');

    // Add Object Modal Elements
    addObjectModal = document.getElementById('addObjectModal');
    modalBackdrop = document.getElementById('modalBackdrop');
    newObjectTypeSelect = document.getElementById('newObjectType');
    newObjectNameInput = document.getElementById('newObjectName');
    newObjectParamsDiv = document.getElementById('newObjectParams');
    confirmAddObjectButton = document.getElementById('confirmAddObject');
    cancelAddObjectButton = document.getElementById('cancelAddObject');

    // Attach Event Listeners
    newProjectButton.addEventListener('click', callbacks.onNewProjectClicked);
    loadGdmlButton.addEventListener('click', callbacks.onLoadGdmlClicked);
    gdmlFileInput.addEventListener('change', (event) => callbacks.onGdmlFileSelected(event.target.files[0]));
    exportGdmlButton.addEventListener('click', callbacks.onExportGdmlClicked);
    saveProjectButton.addEventListener('click', callbacks.onSaveProjectClicked);
    loadProjectButton.addEventListener('click', callbacks.onLoadProjectClicked);
    projectFileInput.addEventListener('change', (event) => callbacks.onProjectFileSelected(event.target.files[0]));

    deleteSelectedObjectButton.addEventListener('click', callbacks.onDeleteSelectedClicked);

    modeObserveButton.addEventListener('click', () => { setActiveModeButton('observe'); callbacks.onModeChangeClicked('observe'); });
    modeTranslateButton.addEventListener('click', () => { setActiveModeButton('translate'); callbacks.onModeChangeClicked('translate'); });
    modeRotateButton.addEventListener('click', () => { setActiveModeButton('rotate'); callbacks.onModeChangeClicked('rotate'); });
    if(modeScaleButton) modeScaleButton.addEventListener('click', () => { setActiveModeButton('scale'); callbacks.onModeChangeClicked('scale'); });

    toggleWireframeButton.addEventListener('click', callbacks.onWireframeToggleClicked);
    toggleGridButton.addEventListener('click', callbacks.onGridToggleClicked);
    cameraModeOrbitButton.addEventListener('click', () => { setActiveCameraModeButton('orbit'); callbacks.onCameraModeChangeClicked('orbit');});
    cameraModeFlyButton.addEventListener('click', () => { setActiveCameraModeButton('fly'); callbacks.onCameraModeChangeClicked('fly');});
    
    toggleSnapToGridButton.addEventListener('click', () => {
        const isNowEnabled = callbacks.onSnapToggleClicked(); // Callback should return new state
        toggleSnapToGridButton.textContent = `Snap to Grid: ${isNowEnabled ? 'ON' : 'OFF'}`;
    });
    gridSnapSizeInput.addEventListener('change', () => callbacks.onSnapSettingsChanged(gridSnapSizeInput.value, undefined));
    angleSnapSizeInput.addEventListener('change', () => callbacks.onSnapSettingsChanged(undefined, angleSnapSizeInput.value));

    // Add listeners for add object buttons (call the solid editor)
    addButtons.forEach(button => {
        button.addEventListener('click', (event) => {
            const type = event.target.dataset.addType;
            if (type.startsWith('solid_')) {
                // Call the new solid editor instead of the old modal
                SolidEditor.show(); 
            } else {
                // For defines and materials, we can keep the old simple modal for now
                showAddObjectModal(type);
            }
        });
    });

    // Add Object Modal Listeners
    confirmAddObjectButton.addEventListener('click', collectAndConfirmAddObject);
    cancelAddObjectButton.addEventListener('click', hideAddObjectModal);
    modalBackdrop.addEventListener('click', hideAddObjectModal);
    newObjectTypeSelect.addEventListener('change', populateAddObjectModalParams); // Renamed for clarity

    // Tab Navigation
    const tabNavButtons = document.querySelectorAll('.tab_button');
    tabNavButtons.forEach(button => {
        button.addEventListener('click', () => {
            const targetTabId = button.dataset.tab;
            activateTab(targetTabId);
        });
    });
    activateTab('tab_structure'); // Default tab

    console.log("UIManager initialized.");
}

export function updateDefineInspectorValues(defineName, newValues, isRotation = false) {
    // Find the inspector panel for the define, but only if it's currently open
    const inspectorTitle = inspectorContentDiv.querySelector('h4');
    if (!inspectorTitle || !inspectorTitle.textContent.includes(`define: ${defineName}`)) {
        return; // Don't update if the define is not being inspected
    }

    for (const axis of ['x', 'y', 'z']) {
        const input = inspectorContentDiv.querySelector(`input[data-property-path="value.${axis}"]`);
        if (input) {
            let valueToShow = newValues[axis];
            if (isRotation) {
                valueToShow = THREE.MathUtils.radToDeg(valueToShow);
            }
            input.value = valueToShow.toFixed(3);
        }
    }
}

// --- Inspector Panel Management ---
export function populateInspector(itemContext) {
    if (!inspectorContentDiv) return;
    inspectorContentDiv.innerHTML = '';

    const { type, id, name, data } = itemContext;

    const title = document.createElement('h4');
    title.textContent = `${type}: ${name || id}`;
    inspectorContentDiv.appendChild(title);

    // Other properties (this loop now handles everything)
    for (const key in data) {
        if (key === 'id' || key === 'phys_children') continue;
        if (typeof data[key] === 'function') continue;

        const propertyDiv = document.createElement('div');
        propertyDiv.classList.add('property_item');
        const label = document.createElement('label');
        label.textContent = `${key}:`;
        propertyDiv.appendChild(label);

        const value = data[key];
        if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
            const subDiv = document.createElement('div');
            subDiv.style.paddingLeft = "10px";
            for (const subKey in value) {
                const subPropertyDiv = document.createElement('div');
                const subLabel = document.createElement('label');
                subLabel.textContent = `${subKey}:`;
                subLabel.style.width = "auto"; subLabel.style.marginRight = "5px";
                subPropertyDiv.appendChild(subLabel);
                
                // Special handling for rotation degrees
                if (key === 'value' && type === 'define' && data.type === 'rotation') {
                     const rotDeg = THREE.MathUtils.radToDeg(value[subKey] || 0);
                     const input = createEditableInputField(subPropertyDiv, {val: rotDeg.toFixed(3)}, 'val', `${key}.${subKey}`, type, id);
                     input.addEventListener('change', (e) => {
                        const radValue = THREE.MathUtils.degToRad(parseFloat(e.target.value));
                        callbacks.onInspectorPropertyChanged(type, id, `${key}.${subKey}`, radValue);
                     });
                } else {
                    createEditableInputField(subPropertyDiv, value, subKey, `${key}.${subKey}`, type, id);
                }

                subDiv.appendChild(subPropertyDiv);
            }
            propertyDiv.appendChild(subDiv);
        } else if (!Array.isArray(value)) {
            createEditableInputField(propertyDiv, data, key, key, type, id);
        } else {
            const valueSpan = document.createElement('span');
            valueSpan.textContent = `[Array of ${value.length}]`;
            propertyDiv.appendChild(valueSpan);
        }
        inspectorContentDiv.appendChild(propertyDiv);
    }
}

// CHANGED: This function now prevents adding a generic listener for rotation properties
function createEditableInputField(parentDiv, object, key, propertyPath, objectType, objectId) {
    const input = document.createElement('input');
    const currentValue = object[key];
    input.type = (typeof currentValue === 'number' || !isNaN(parseFloat(currentValue))) ? 'number' : 'text';
    if (input.type === 'number') input.step = 'any';
    input.value = (currentValue === null || currentValue === undefined) ? '' : currentValue;
    
    input.dataset.objectType = objectType;
    input.dataset.objectId = objectId;
    input.dataset.propertyPath = propertyPath;

    // Do NOT add a generic listener for rotation, as it needs special handling (deg->rad)
    if (!propertyPath.startsWith('rotation.')) {
        input.addEventListener('change', (e) => {
            callbacks.onInspectorPropertyChanged(
                e.target.dataset.objectType,
                e.target.dataset.objectId,
                e.target.dataset.propertyPath,
                e.target.value // Send as string, backend will try to convert
            );
        });
    }

    parentDiv.appendChild(input);
    return input;
}

// ADDED: This function provides the live link from the 3D transform to the UI
export function updateInspectorTransform(liveObject) {
    if (!inspectorContentDiv || !liveObject) return;

    // Only update if the inspector is showing numeric inputs (not a reference string)
    const posXInput = inspectorContentDiv.querySelector('input[data-live-update="position.x"]');
    if (!posXInput) return; 

    // Update Position Fields
    posXInput.value = liveObject.position.x.toFixed(3);
    const posYInput = inspectorContentDiv.querySelector('input[data-live-update="position.y"]');
    if (posYInput) posYInput.value = liveObject.position.y.toFixed(3);
    const posZInput = inspectorContentDiv.querySelector('input[data-live-update="position.z"]');
    if (posZInput) posZInput.value = liveObject.position.z.toFixed(3);

    // Update Rotation Fields (displaying in degrees)
    const euler = new THREE.Euler().setFromQuaternion(liveObject.quaternion, 'ZYX');
    const rotXInput = inspectorContentDiv.querySelector('input[data-live-update="rotation.x"]');
    if (rotXInput) rotXInput.value = THREE.MathUtils.radToDeg(euler.x).toFixed(3);
    const rotYInput = inspectorContentDiv.querySelector('input[data-live-update="rotation.y"]');
    if (rotYInput) rotYInput.value = THREE.MathUtils.radToDeg(euler.y).toFixed(3);
    const rotZInput = inspectorContentDiv.querySelector('input[data-live-update="rotation.z"]');
    if (rotZInput) rotZInput.value = THREE.MathUtils.radToDeg(euler.z).toFixed(3);
}

// --- The rest of the file is unchanged, but included for completeness ---
// --- UI Update Functions ---
function setActiveModeButton(mode) {
    if(modeObserveButton) modeObserveButton.classList.toggle('active_mode', mode === 'observe');
    if(modeTranslateButton) modeTranslateButton.classList.toggle('active_mode', mode === 'translate');
    if(modeRotateButton) modeRotateButton.classList.toggle('active_mode', mode === 'rotate');
    if(modeScaleButton) modeScaleButton.classList.toggle('active_mode', mode === 'scale');
    if(currentModeDisplay) currentModeDisplay.textContent = `Mode: ${mode.charAt(0).toUpperCase() + mode.slice(1)}`;
}

function setActiveCameraModeButton(mode) {
    if(cameraModeOrbitButton) cameraModeOrbitButton.classList.toggle('active_mode', mode === 'orbit');
    if(cameraModeFlyButton) cameraModeFlyButton.classList.toggle('active_mode', mode === 'fly');
}

export function triggerFileInput(inputId) {
    const inputElement = document.getElementById(inputId);
    if (inputElement) inputElement.click();
}

// --- Hierarchy Panel Management ---
export function updateHierarchy(projectState) {
    if (!projectState) {
        clearHierarchy();
        return;
    }
    if(structureTreeRoot) structureTreeRoot.innerHTML = '';
    if(definesListRoot) definesListRoot.innerHTML = '';
    if(materialsListRoot) materialsListRoot.innerHTML = '';
    if(solidsListRoot) solidsListRoot.innerHTML = '';

    for (const name in projectState.defines) {
        if(definesListRoot) definesListRoot.appendChild(createTreeItem(name, 'define', name, projectState.defines[name]));
    }
    for (const name in projectState.materials) {
        if(materialsListRoot) materialsListRoot.appendChild(createTreeItem(name, 'material', name, projectState.materials[name]));
    }
    for (const name in projectState.solids) {
        if(solidsListRoot) solidsListRoot.appendChild(createTreeItem(name, 'solid', name, projectState.solids[name]));
    }
    if (projectState.world_volume_ref && projectState.logical_volumes) {
        const worldLV = projectState.logical_volumes[projectState.world_volume_ref];
        if (worldLV && structureTreeRoot) {
            structureTreeRoot.appendChild(buildVolumeNode(worldLV, projectState.logical_volumes, projectState.solids, 0, worldLV.name));
        } else if (structureTreeRoot) {
            structureTreeRoot.innerHTML = '<li>World volume not found.</li>';
        }
    } else if (structureTreeRoot) {
         structureTreeRoot.innerHTML = '<li>No structure to display.</li>';
    }
}

function buildVolumeNode(lvData, allLVs, allSolids, depth, lvIdForBackend) {
    const lvItem = createTreeItem(lvData.name, 'logical_volume', lvIdForBackend, lvData);
    if (lvData.phys_children && lvData.phys_children.length > 0) {
        const toggle = document.createElement('span');
        toggle.classList.add('toggle');
        toggle.textContent = '[-] ';
        toggle.onclick = (e) => { e.stopPropagation();
            const childrenUl = lvItem.querySelector('ul');
            if (childrenUl) {
                childrenUl.style.display = childrenUl.style.display === 'none' ? 'block' : 'none';
                toggle.textContent = childrenUl.style.display === 'none' ? '[+] ' : '[-] ';
            }
        };
        if (lvItem.firstChild) lvItem.insertBefore(toggle, lvItem.firstChild); 
        else lvItem.appendChild(toggle);
    }

    const childrenUl = document.createElement('ul');
    (lvData.phys_children || []).forEach(pvData => {
        const childLVData = allLVs[pvData.volume_ref];
        let displayName = pvData.name || `pv_${pvData.id.substring(0,4)}`;
        if (childLVData) {
             displayName += ` (LV: ${childLVData.name})`;
             const pvItem = createTreeItem(displayName, 'physical_volume', pvData.id, pvData, { lvData: childLVData, solidData: allSolids[childLVData.solid_ref] });
             childrenUl.appendChild(pvItem);
        }
    });
    if (childrenUl.children.length > 0) lvItem.appendChild(childrenUl);
    return lvItem;
}

function createTreeItem(displayName, itemType, itemIdForBackend, fullItemData, additionalData = {}) {
    const item = document.createElement('li');
    item.innerHTML = `<span>${displayName}</span>`;
    item.dataset.type = itemType;
    item.dataset.id = itemIdForBackend;
    item.dataset.name = displayName;
    item.appData = {...fullItemData, ...additionalData};

    item.addEventListener('click', (event) => {
        event.stopPropagation();
        const selected = document.querySelector('#left_panel_container .selected_item');
        if(selected) selected.classList.remove('selected_item');
        item.classList.add('selected_item');
        callbacks.onHierarchyItemSelected({ type: itemType, id: itemIdForBackend, name: displayName, data: item.appData, element: item });
    });

    // For double-clicking of solids
    if (itemType === 'solid') {
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            // Pass the solid's data to the handler
            callbacks.onEditSolidClicked(item.appData);
        });
    }
    return item;
}

export function selectHierarchyItemByTypeAndId(itemType, itemId, projectState) {
    let itemElement = document.querySelector(`.tab_pane.active li[data-id="${itemId}"]`);
    if (itemElement) {
        if(projectState) {
            // This part is complex, let's assume itemElement.appData is up to date for now
        }
        itemElement.click(); // Simulate a click to run the selection logic
        itemElement.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
}

export function reselectHierarchyItem(itemType, itemId, projectState) {
    selectHierarchyItemByTypeAndId(itemType, itemId, projectState);
}


export function clearHierarchySelection() {
    const selected = document.querySelector('#left_panel_container .selected_item');
    if (selected) selected.classList.remove('selected_item');
}

export function clearHierarchy() {
    if(structureTreeRoot) structureTreeRoot.innerHTML = '';
    if(definesListRoot) definesListRoot.innerHTML = '';
    if(materialsListRoot) materialsListRoot.innerHTML = '';
    if(solidsListRoot) solidsListRoot.innerHTML = '';
}

export function clearInspector() {
    if(inspectorContentDiv) inspectorContentDiv.innerHTML = '<p>Select an item.</p>';
}

// --- Add Object Modal ---
export function showAddObjectModal(preselectedType = 'define_position') {
    if(newObjectNameInput) newObjectNameInput.value = '';
    
    // Set the dropdown to the correct value passed from the button
    if(newObjectTypeSelect) {
        newObjectTypeSelect.value = preselectedType;
    }

    // Populate the parameters for the pre-selected type
    populateAddObjectModalParams();

    // Show the modal
    if(addObjectModal) addObjectModal.style.display = 'block';
    if(modalBackdrop) modalBackdrop.style.display = 'block';
}

export function hideAddObjectModal() {
    if(addObjectModal) addObjectModal.style.display = 'none';
    if(modalBackdrop) modalBackdrop.style.display = 'none';
}

function populateAddObjectModalParams() {
    if(!newObjectParamsDiv || !newObjectTypeSelect) return;
    newObjectParamsDiv.innerHTML = '';
    const type = newObjectTypeSelect.value;
     if (type === 'define_position') {
        newObjectParamsDiv.innerHTML = `
            <label>X:</label><input type="number" id="add_define_pos_x" value="0"><br>
            <label>Y:</label><input type="number" id="add_define_pos_y" value="0"><br>
            <label>Z:</label><input type="number" id="add_define_pos_z" value="0"><br>
            <label>Unit:</label><input type="text" id="add_define_pos_unit" value="mm">`;
    } else if (type === 'material') {
        newObjectParamsDiv.innerHTML = `
            <label>Density (g/cm3):</label><input type="number" id="add_mat_density" value="1.0" step="any"><br>
            <label>State (optional):</label><input type="text" id="add_mat_state" placeholder="solid/liquid/gas">`;
    } else if (type === 'solid_box') {
        newObjectParamsDiv.innerHTML = `
            <label>X (mm):</label><input type="number" id="add_box_x" value="100" step="any"><br>
            <label>Y (mm):</label><input type="number" id="add_box_y" value="100" step="any"><br>
            <label>Z (mm):</label><input type="number" id="add_box_z" value="100" step="any">`;
    } else if (type === 'solid_tube') {
        newObjectParamsDiv.innerHTML = `
            <label>RMin (mm):</label><input type="number" id="add_tube_rmin" value="0" step="any"><br>
            <label>RMax (mm):</label><input type="number" id="add_tube_rmax" value="50" step="any"><br>
            <label>Full Length Z (mm):</label><input type="number" id="add_tube_z_fulllength" value="200" step="any"><br>
            <label>StartPhi (rad):</label><input type="number" step="any" id="add_tube_startphi" value="0"><br>
            <label>DeltaPhi (rad):</label><input type="number" step="any" id="add_tube_deltaphi" value="${(2 * Math.PI).toFixed(4)}">`;
    }
}

function collectAndConfirmAddObject() {
    const objectType = newObjectTypeSelect.value;
    const nameSuggestion = newObjectNameInput.value.trim();
    if (!nameSuggestion) {
        showError("Please enter a name for the new object.");
        return;
    }
    let params = {};
    if (objectType === 'define_position') {
        params = {
            x: document.getElementById('add_define_pos_x').value,
            y: document.getElementById('add_define_pos_y').value,
            z: document.getElementById('add_define_pos_z').value,
            unit: document.getElementById('add_define_pos_unit').value
        };
    } else if (objectType === 'material') {
        params = {
            density: parseFloat(document.getElementById('add_mat_density').value),
            state: document.getElementById('add_mat_state').value || null
        };
    } else if (objectType === 'solid_box') {
        params = {
            x: parseFloat(document.getElementById('add_box_x').value),
            y: parseFloat(document.getElementById('add_box_y').value),
            z: parseFloat(document.getElementById('add_box_z').value)
        };
    } else if (objectType === 'solid_tube') {
        params = {
            rmin: parseFloat(document.getElementById('add_tube_rmin').value),
            rmax: parseFloat(document.getElementById('add_tube_rmax').value),
            dz: parseFloat(document.getElementById('add_tube_z_fulllength').value), 
            startphi: parseFloat(document.getElementById('add_tube_startphi').value),
            deltaphi: parseFloat(document.getElementById('add_tube_deltaphi').value),
        };
    }
    callbacks.onConfirmAddObject(objectType, nameSuggestion, params);
}

// --- Tab Management ---
function activateTab(tabId) {
    const tabNavButtons = document.querySelectorAll('.tab_button');
    const tabContentPanes = document.querySelectorAll('.tab_pane');

    tabNavButtons.forEach(button => {
        button.classList.toggle('active', button.dataset.tab === tabId);
    });
    tabContentPanes.forEach(pane => {
        pane.classList.toggle('active', pane.id === tabId);
    });
}

// --- Utility/Notification Functions ---
export function showError(message) {
    console.error("[UI Error] " + message);
    alert("Error: " + message);
}
export function showNotification(message) {
    console.log("[UI Notification] " + message);
    alert(message);
}
export function showLoading(message = "Loading...") {
    console.log("[UI Loading] " + message);
}
export function hideLoading() {
    console.log("[UI Loading] Complete.");
}

/**
 * Displays a confirmation dialog to the user.
 * @param {string} message The question to ask the user.
 * @returns {boolean} True if the user clicked "OK", false otherwise.
 */
export function confirmAction(message) {
    return window.confirm(message);
}