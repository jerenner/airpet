// static/uiManager.js
import * as THREE from 'three'; // Needed for THREE.MathUtils

// --- Module-level variables for DOM elements ---
let gdmlFileInput, loadGdmlButton, exportGdmlButton,
    saveProjectButton, loadProjectButton, projectFileInput,
    addObjectButton, deleteSelectedObjectButton,
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
    onLoadGdmlClicked: () => {},
    onLoadProjectClicked: () => {},
    onGdmlFileSelected: (file) => {},
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
    loadGdmlButton = document.getElementById('loadGdmlButton');
    gdmlFileInput = document.getElementById('gdmlFile');
    exportGdmlButton = document.getElementById('exportGdmlButton');
    saveProjectButton = document.getElementById('saveProjectButton');
    loadProjectButton = document.getElementById('loadProjectButton');
    projectFileInput = document.getElementById('projectFile');
    addObjectButton = document.getElementById('addObjectButton');
    deleteSelectedObjectButton = document.getElementById('deleteSelectedObjectButton');

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
    loadGdmlButton.addEventListener('click', callbacks.onLoadGdmlClicked);
    gdmlFileInput.addEventListener('change', (event) => callbacks.onGdmlFileSelected(event.target.files[0]));
    exportGdmlButton.addEventListener('click', callbacks.onExportGdmlClicked);
    saveProjectButton.addEventListener('click', callbacks.onSaveProjectClicked);
    loadProjectButton.addEventListener('click', callbacks.onLoadProjectClicked);
    projectFileInput.addEventListener('change', (event) => callbacks.onProjectFileSelected(event.target.files[0]));

    addObjectButton.addEventListener('click', callbacks.onAddObjectClicked); // This now calls UIManager.showAddObjectModal
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
        console.warn("[UIManager] updateHierarchy called with no projectState.");
        clearHierarchy();
        return;
    }
    // Clear existing content in all tabs
    if(structureTreeRoot) structureTreeRoot.innerHTML = '';
    if(definesListRoot) definesListRoot.innerHTML = '';
    if(materialsListRoot) materialsListRoot.innerHTML = '';
    if(solidsListRoot) solidsListRoot.innerHTML = '';

    // Populate Defines Tab
    for (const name in projectState.defines) {
        if(definesListRoot) definesListRoot.appendChild(createTreeItem(name, 'define', name, projectState.defines[name]));
    }
    // Populate Materials Tab
    for (const name in projectState.materials) {
        if(materialsListRoot) materialsListRoot.appendChild(createTreeItem(name, 'material', name, projectState.materials[name]));
    }
    // Populate Solids Tab
    for (const name in projectState.solids) {
        if(solidsListRoot) solidsListRoot.appendChild(createTreeItem(name, 'solid', name, projectState.solids[name]));
    }
    // Populate Structure (Volumes) Tab
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
        toggle.onclick = (e) => { /* ... expand/collapse logic ... */ e.stopPropagation();
            const childrenUl = lvItem.querySelector('ul');
            if (childrenUl) {
                childrenUl.style.display = childrenUl.style.display === 'none' ? 'block' : 'none';
                toggle.textContent = childrenUl.style.display === 'none' ? '[+] ' : '[-] ';
            }
        };
        // Insert toggle carefully, e.g., before the first text node of the item's direct child (nameSpan)
        if (lvItem.firstChild) lvItem.insertBefore(toggle, lvItem.firstChild); 
        else lvItem.appendChild(toggle);
    }

    const childrenUl = document.createElement('ul');
    (lvData.phys_children || []).forEach(pvData => {
        const childLVData = allLVs[pvData.volume_ref];
        let displayName = pvData.name;
        if (childLVData) {
             displayName += ` (LV: ${childLVData.name})`;
             const pvItem = createTreeItem(displayName, 'physical_volume', pvData.id, pvData, { lvData: childLVData, solidData: allSolids[childLVData.solid_ref] });
             childrenUl.appendChild(pvItem);
        } else {
            // ... error item ...
        }
    });
    if (childrenUl.children.length > 0) lvItem.appendChild(childrenUl);
    return lvItem;
}

function createTreeItem(displayName, itemType, itemIdForBackend, fullItemData, additionalData = {}) {
    const item = document.createElement('li');
    const nameSpan = document.createElement('span');
    nameSpan.textContent = displayName;
    item.appendChild(nameSpan);

    item.dataset.type = itemType;
    item.dataset.id = itemIdForBackend;
    item.dataset.name = displayName; // For display, could be different from ID for PVs
    item.appData = {...fullItemData, ...additionalData}; // Store the full data object

    item.addEventListener('click', (event) => {
        event.stopPropagation();
        callbacks.onHierarchyItemSelected({ type: itemType, id: itemIdForBackend, name: displayName, data: item.appData, element: item });
    });
    return item;
}

export function selectHierarchyItemByTypeAndId(itemType, itemId, projectState) {
    // Find the DOM element
    let itemElement;
    if (itemType === 'physical_volume') {
        itemElement = document.querySelector(`.tab_pane.active li[data-type="physical_volume"][data-id="${itemId}"]`);
    } else { // For define, material, solid, lv - id is name
        itemElement = document.querySelector(`.tab_pane.active li[data-type="${itemType}"][data-id="${itemId}"]`);
    }
    
    if (itemElement) {
        // Update appData on the element if projectState is provided (after backend update)
        if(projectState) {
            let newData;
            if(itemType === 'define') newData = projectState.defines[itemId];
            else if(itemType === 'material') newData = projectState.materials[itemId];
            else if(itemType === 'solid') newData = projectState.solids[itemId];
            else if(itemType === 'logical_volume') newData = projectState.logical_volumes[itemId];
            else if(itemType === 'physical_volume'){
                // Find PV data again
                for (const lvName in projectState.logical_volumes) {
                    const lv = projectState.logical_volumes[lvName];
                    const pv = (lv.phys_children || []).find(p => p.id === itemId);
                    if (pv) { newData = pv; break; }
                }
            }
            if(newData) itemElement.appData = newData;
        }
        callbacks.onHierarchyItemSelected({ type: itemType, id: itemId, name: itemElement.dataset.name, data: itemElement.appData, element: itemElement });
        itemElement.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } else {
        console.warn(`[UIManager] Could not find hierarchy item to select: ${itemType} - ${itemId}`);
    }
}

export function reselectHierarchyItem(itemType, itemId, projectState) {
    // This is called after a property update to refresh the inspector with new data
    // The hierarchy itself might have been rebuilt, so find the new DOM element
    selectHierarchyItemByTypeAndId(itemType, itemId, projectState);
}


export function clearHierarchySelection() {
    const selected = document.querySelector('#left_panel_container .selected_item');
    if (selected) selected.classList.remove('selected_item');
    // currentlyInspectedUIItem is managed by main.js via AppState
}

export function clearHierarchy() {
    if(structureTreeRoot) structureTreeRoot.innerHTML = '';
    if(definesListRoot) definesListRoot.innerHTML = '';
    if(materialsListRoot) materialsListRoot.innerHTML = '';
    if(solidsListRoot) solidsListRoot.innerHTML = '';
}

// --- Inspector Panel Management ---
export function populateInspector(itemContext) { // objectId is UUID for PV, name for others
    if (!inspectorContentDiv) return;
    inspectorContentDiv.innerHTML = ''; // Clear

    const { type, id, name, data } = itemContext;

    const title = document.createElement('h4');
    title.textContent = `${type}: ${name || id}`; // Use objectId as fallback name
    inspectorContentDiv.appendChild(title);

    // --- Special handling for PV to show position/rotation ---
    if (type === 'physical_volume') {
        const pvData = data; // For clarity

        // Position
        const posDiv = document.createElement('div');
        posDiv.classList.add('property_item');
        const posLabel = document.createElement('label');
        posLabel.textContent = `Position:`;
        posDiv.appendChild(posLabel);

        if (typeof pvData.position === 'string') {
            // Display the reference name
            const refInput = createEditableInputField(posDiv, pvData, 'position', 'position', type, id);
            refInput.value = pvData.position;
            // TODO: Add a "Resolve/Break Ref" button next to it
        } else {
            // Display x, y, z inputs for inline values
            const posSubDiv = document.createElement('div');
            posSubDiv.style.paddingLeft = "10px";
            const pos = pvData.position || {x:0, y:0, z:0};
            for (const axis of ['x', 'y', 'z']) {
                const subPropertyDiv = document.createElement('div');
                const subLabel = document.createElement('label');
                subLabel.textContent = `${axis}:`;
                subPropertyDiv.appendChild(subLabel);
                const input = createEditableInputField(subPropertyDiv, pos, axis, `position.${axis}`, type, id);
                input.dataset.liveUpdate = `position.${axis}`; // Tag for live update
                posSubDiv.appendChild(subPropertyDiv);
            }
            posDiv.appendChild(posSubDiv);
        }
        inspectorContentDiv.appendChild(posDiv);
        
        // Rotation (similar logic)
        const rotDiv = document.createElement('div');
        rotDiv.classList.add('property_item');
        const rotLabel = document.createElement('label');
        rotLabel.textContent = `Rotation:`;
        rotDiv.appendChild(rotLabel);
        
        if (typeof pvData.rotation === 'string') {
            const refInput = createEditableInputField(rotDiv, pvData, 'rotation', 'rotation', type, id);
            refInput.value = pvData.rotation;
        } else {
            const rotSubDiv = document.createElement('div');
            rotSubDiv.style.paddingLeft = "10px";
            const rot = pvData.rotation || {x:0, y:0, z:0}; // Radians from backend
            for (const axis of ['x', 'y', 'z']) {
                const subPropertyDiv = document.createElement('div');
                const subLabel = document.createElement('label');
                subLabel.textContent = `${axis} (deg):`;
                subPropertyDiv.appendChild(subLabel);
                
                const rotDeg = THREE.MathUtils.radToDeg(rot[axis] || 0);
                const input = createEditableInputField(subPropertyDiv, {val: rotDeg}, 'val', `rotation.${axis}`, type, id);
                input.dataset.liveUpdate = `rotation.${axis}`;
                input.addEventListener('change', (e) => {
                    const radValue = THREE.MathUtils.degToRad(parseFloat(e.target.value));
                    callbacks.onInspectorPropertyChanged(type, id, `rotation.${axis}`, radValue);
                });
            }
            rotDiv.appendChild(rotSubDiv);
        }
        inspectorContentDiv.appendChild(rotDiv);
    }

    // Other properties
    for (const key in data) {
        // Skip internal/complex fields not directly editable as simple inputs
        if (key === 'id' || key === 'phys_children' || key === 'element' || key === 'appData' || key === 'components' || key === 'facets' || key === 'zplanes' || key === 'rzpoints' || key === 'vertices') continue;
        if (typeof data[key] === 'function') continue;

        const propertyDiv = document.createElement('div');
        propertyDiv.classList.add('property_item');
        const label = document.createElement('label');
        label.textContent = `${key}:`;
        propertyDiv.appendChild(label);

        const value = data[key];
        if (typeof value === 'object' && value !== null && !Array.isArray(value)) { // Nested object (e.g., position, parameters)
            const subDiv = document.createElement('div');
            subDiv.style.paddingLeft = "10px";
            for (const subKey in value) {
                const subPropertyDiv = document.createElement('div');
                const subLabel = document.createElement('label');
                subLabel.textContent = `${subKey}:`;
                subLabel.style.width = "auto"; subLabel.style.marginRight = "5px";
                subPropertyDiv.appendChild(subLabel);
                createEditableInputField(subPropertyDiv, value, subKey, `${key}.${subKey}`, type, id);
                subDiv.appendChild(subPropertyDiv);
            }
            propertyDiv.appendChild(subDiv);
        } else if (!Array.isArray(value)) { // Simple property
            createEditableInputField(propertyDiv, data, key, key, type, id);
        } else { // Array - display as read-only for now
            const valueSpan = document.createElement('span');
            valueSpan.textContent = `[Array of ${value.length}]`; // Simple representation
            propertyDiv.appendChild(valueSpan);
        }
        inspectorContentDiv.appendChild(propertyDiv);
    }

     // Add Hide/Delete buttons
    if (['physical_volume', 'logical_volume', 'solid', 'define', 'material'].includes(type)) {
        addInspectorActions(type, id, name);
    }
}

function createEditableInputField(parentDiv, object, key, propertyPath, objectType, objectId) {
    const input = document.createElement('input');
    const currentValue = object[key];
    input.type = (typeof currentValue === 'number') ? 'number' : 'text';
    if (input.type === 'number') input.step = 'any';
    input.value = (currentValue === null || currentValue === undefined) ? '' : currentValue;
    
    // Store necessary info for backend update
    input.dataset.objectType = objectType;
    input.dataset.objectId = objectId;
    input.dataset.propertyPath = propertyPath;

    // Remove the generic 'change' listener from here if it's handled specifically (like for rotation)
    // The generic one is still good for most cases
    if (propertyPath.startsWith('rotation.')) {
        // The specific listener is added in populateInspector
    } else {
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
    return input; // Return the input element
}

export function updateInspectorTransform(liveObject) {
    if (!inspectorContentDiv || !liveObject) return;

    // Check if the current inspector is showing ref strings. If so, don't update the numbers.
    // We only update if the number input fields already exist.
    const posXInput = inspectorContentDiv.querySelector('input[data-live-update="position.x"]');
    if (!posXInput) return; // The inspector is in "ref" mode, do nothing.

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

function addInspectorActions(objectType, objectId, objectName){
    const actionsDiv = document.createElement('div');
    actionsDiv.style.marginTop = '10px';

    if (objectType === 'physical_volume') { // Hide/Show only makes sense for PVs
        const hideButton = document.createElement('button');
        // Check visibility from SceneManager or via a callback if needed
        // For now, just a placeholder text. SceneManager must handle actual visibility.
        hideButton.textContent = "Toggle Visibility"; // SceneManager will know current state
        hideButton.onclick = () => {
            if(callbacks.onTogglePVVisibility) callbacks.onTogglePVVisibility(objectId); // Requires main.js to pass this
            else console.warn("onTogglePVVisibility callback not set for UIManager");
        };
        actionsDiv.appendChild(hideButton);
    }

    const deleteButton = document.createElement('button');
    deleteButton.textContent = "Delete";
    deleteButton.style.marginLeft = (objectType === 'physical_volume') ? "5px" : "0";
    deleteButton.onclick = () => {
        // Use callbacks.onDeleteSelectedClicked, but it relies on currentlyInspectedItem.
        // It's better if this directly calls a more specific delete action.
        if(callbacks.onDeleteSelectedItem) callbacks.onDeleteSelectedItem({type: objectType, id: objectId, name: objectName });
        else console.warn("onDeleteSelectedItem callback not set for UIManager")
    };
    actionsDiv.appendChild(deleteButton);
    inspectorContentDiv.appendChild(actionsDiv);
}


export function clearInspector() {
    if(inspectorContentDiv) inspectorContentDiv.innerHTML = '<p>Select an item.</p>';
}

// --- Add Object Modal ---
export function showAddObjectModal() {
    if(newObjectNameInput) newObjectNameInput.value = '';
    if(newObjectTypeSelect) populateAddObjectModalParams(); // Populate for default selection
    if(addObjectModal) addObjectModal.style.display = 'block';
    if(modalBackdrop) modalBackdrop.style.display = 'block';
}

export function hideAddObjectModal() {
    if(addObjectModal) addObjectModal.style.display = 'none';
    if(modalBackdrop) modalBackdrop.style.display = 'none';
}

function populateAddObjectModalParams() { // Renamed from populateAddObjectParams
    if(!newObjectParamsDiv || !newObjectTypeSelect) return;
    newObjectParamsDiv.innerHTML = '';
    const type = newObjectTypeSelect.value;
    // Same logic as before for populating parameters based on selected type
    // ... (box, tube, define_position, material params) ...
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
        showError("Please enter a name for the new object."); // Use new showError
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
        }; // Assumed these are in internal units (mm) as per UI label
    } else if (objectType === 'solid_tube') {
        params = {
            rmin: parseFloat(document.getElementById('add_tube_rmin').value),
            rmax: parseFloat(document.getElementById('add_tube_rmax').value),
            // Backend expects dz (half-length) for tube, but UI takes full length
            dz: parseFloat(document.getElementById('add_tube_z_fulllength').value) / 2.0, 
            startphi: parseFloat(document.getElementById('add_tube_startphi').value),
            deltaphi: parseFloat(document.getElementById('add_tube_deltaphi').value),
        }; // Assumed these are in internal units (mm, rad)
    }
    callbacks.onConfirmAddObject(objectType, nameSuggestion, params);
}


// --- Tab Management ---
function activateTab(tabId) {
    const tabNavButtons = document.querySelectorAll('.tab_button'); // Query inside function if not global
    const tabContentPanes = document.querySelectorAll('.tab_pane'); // Query inside function

    tabNavButtons.forEach(button => {
        button.classList.toggle('active', button.dataset.tab === tabId);
    });
    tabContentPanes.forEach(pane => {
        pane.classList.toggle('active', pane.id === tabId);
    });
}

// --- Utility/Notification Functions ---
export function showError(message) {
    // Replace with a more sophisticated notification system later
    console.error("[UI Error] " + message);
    alert("Error: " + message);
}
export function showNotification(message) {
    console.log("[UI Notification] " + message);
    alert(message); // Simple alert for now
}
export function showLoading(message = "Loading...") {
    console.log("[UI Loading] " + message);
    // TODO: Implement a proper loading indicator (e.g., spinner overlay)
}
export function hideLoading() {
    console.log("[UI Loading] Complete.");
    // TODO: Hide loading indicator
}