// static/uiManager.js
import * as THREE from 'three';
import * as SceneManager from './sceneManager.js';

// --- Module-level variables for DOM elements ---
let newProjectButton, saveProjectButton, exportGdmlButton,
    openGdmlButton, openProjectButton, importGdmlButton, importProjectButton,
    importAiResponseButton, importStepButton,
    gdmlFileInput, projectFileInput, gdmlPartFileInput, jsonPartFileInput,
    aiResponseFileInput, stepFileInput,
    deleteSelectedObjectButton,
    modeObserveButton, modeTranslateButton, modeRotateButton, //modeScaleButton,
    toggleWireframeButton, toggleGridButton, toggleAxesButton,
    cameraModeOrbitButton, cameraModeFlyButton,
    toggleSnapToGridButton, gridSnapSizeInput, angleSnapSizeInput,
    aiPromptInput, aiGenerateButton, aiModelSelect,
    setApiKeyButton, apiKeyModal, apiKeyInput, saveApiKeyButton, cancelApiKeyButton,
    currentModeDisplay;

// Hierarchy and Inspector
let structureTreeRoot, assembliesListRoot, lvolumesListRoot, definesListRoot, materialsListRoot, solidsListRoot;
let inspectorContentDiv;

// Buttons for adding LVs, PVs, and assemblies
let addAssemblyButton, addLVButton, addPVButton;

// Keep track of selected parent LV in structure hierarchy.
let selectedParentContext = null;

// Number of items per group for lists
const ITEMS_PER_GROUP = 100;

// Callbacks to main.js (controller logic)
let callbacks = {
    
    onOpenGdmlClicked: (file) => {},
    onOpenProjectClicked: (file) => {},
    onImportGdmlClicked: (file) => {},
    onImportProjectClicked: (file) => {},
    onImportAiResponseClicked: (file) => {},
    onImportStepClicked: (file) => {},
    onNewProjectClicked: () => {},
    onSaveProjectClicked: () => {},
    onExportGdmlClicked: () => {},
    onEditSolidClicked: (solidData) => {},
    onAddDefineClicked: () => {},
    onEditDefineClicked: (defineData) => {},
    onAddMaterialClicked: ()=>{}, 
    onEditMaterialClicked: (d)=>{},
    onAddLVClicked: () => {},
    onEditLVClicked: (lvData) => {},
    onAddObjectClicked: () => {}, // To show modal
    onConfirmAddObject: (type, name, params) => {},
    onDeleteSelectedClicked: () => {},
    onHierarchySelectionChanged: (selectedItems) => {},
    onModeChangeClicked: (mode) => {},
    onSnapToggleClicked: () => {},
    onSnapSettingsChanged: (transSnap, angleSnap) => {},
    onCameraModeChangeClicked: (mode) => {},
    onWireframeToggleClicked: () => {},
    onGridToggleClicked: () => {},
    onAxesToggleClicked: () => {},
    onHierarchyItemSelected: (itemContext) => {}, // {type, id, name, data}
    onInspectorPropertyChanged: (type, id, path, value) => {},
    onPVVisibilityToggle: (pvId, isVisible) => {},
    onAiGenerateClicked: (promptText) => {},
    onSetApiKeyClicked: () => {},
    onSaveApiKeyClicked: (apiKey) => {}
};

// --- Initialization ---
export function initUI(cb) {
    callbacks = {...callbacks, ...cb}; // Merge provided callbacks

    // Get Menu Buttons
    // Open Project
    openGdmlButton = document.getElementById('openGdmlButton')
    gdmlFileInput = document.getElementById('gdmlFile')
    
    openProjectButton = document.getElementById('openProjectButton')
    projectFileInput = document.getElementById('projectFile')

    // Import Parts
    importGdmlButton = document.getElementById('importGdmlButton')
    gdmlPartFileInput = document.getElementById('gdmlPartFile')

    importProjectButton = document.getElementById('importProjectButton')
    jsonPartFileInput = document.getElementById('jsonPartFile')

    importAiResponseButton = document.getElementById('importAiResponseButton');
    aiResponseFileInput = document.getElementById('aiResponseFile');

    importStepButton = document.getElementById('importStepButton');
    stepFileInput = document.getElementById('stepFile');

    // Other File menu options
    newProjectButton = document.getElementById('newProjectButton');
    saveProjectButton = document.getElementById('saveProjectButton');
    exportGdmlButton = document.getElementById('exportGdmlButton');
    setApiKeyButton = document.getElementById('setApiKeyButton');

    deleteSelectedObjectButton = document.getElementById('deleteSelectedObjectButton');

    // Add buttons
    const addButtons = document.querySelectorAll('.add_button');
    addAssemblyButton = document.getElementById('addAssemblyButton');
    addLVButton = document.getElementById('addLVButton');
    addPVButton = document.getElementById('addPVButton');

    // Mode Buttons
    modeObserveButton = document.getElementById('modeObserveButton');
    modeTranslateButton = document.getElementById('modeTranslateButton');
    modeRotateButton = document.getElementById('modeRotateButton');
    //modeScaleButton = document.getElementById('modeScaleButton'); // If you add it
    currentModeDisplay = document.getElementById('currentModeDisplay');

    // View Menu Buttons
    toggleWireframeButton = document.getElementById('toggleWireframeButton');
    toggleGridButton = document.getElementById('toggleGridButton');
    toggleAxesButton = document.getElementById('toggleAxesButton');
    cameraModeOrbitButton = document.getElementById('cameraModeOrbitButton');
    cameraModeFlyButton = document.getElementById('cameraModeFlyButton');

    // Edit Menu / Snap Buttons
    toggleSnapToGridButton = document.getElementById('toggleSnapToGridButton');
    gridSnapSizeInput = document.getElementById('gridSnapSizeInput');
    angleSnapSizeInput = document.getElementById('angleSnapSizeInput');

    // Hierarchy and Inspector Roots
    structureTreeRoot = document.getElementById('structure_tree_root');
    assembliesListRoot = document.getElementById('assemblies_list_root');
    lvolumesListRoot = document.getElementById('lvolumes_list_root');
    definesListRoot = document.getElementById('defines_list_root');
    materialsListRoot = document.getElementById('materials_list_root');
    solidsListRoot = document.getElementById('solids_list_root');
    inspectorContentDiv = document.getElementById('inspector_content');

    // AI Panel elements
    aiPromptInput = document.getElementById('ai_prompt_input');
    aiGenerateButton = document.getElementById('ai_generate_button');
    aiModelSelect = document.getElementById('ai_model_select');

    // API key modal elements
    apiKeyModal = document.getElementById('apiKeyModal');
    apiKeyInput = document.getElementById('apiKeyInput');
    saveApiKeyButton = document.getElementById('saveApiKey');
    cancelApiKeyButton = document.getElementById('cancelApiKey');

    // Add Object Modal Elements
    // addObjectModal = document.getElementById('addObjectModal');
    // modalBackdrop = document.getElementById('modalBackdrop');
    // newObjectTypeSelect = document.getElementById('newObjectType');
    // newObjectNameInput = document.getElementById('newObjectName');
    // newObjectParamsDiv = document.getElementById('newObjectParams');
    // confirmAddObjectButton = document.getElementById('confirmAddObject');
    // cancelAddObjectButton = document.getElementById('cancelAddObject');

    // --- Initialize snap settings from UI values on startup ---
    const initialTransSnap = document.getElementById('gridSnapSizeInput').value;
    const initialAngleSnap = document.getElementById('angleSnapSizeInput').value;
    callbacks.onSnapSettingsChanged(initialTransSnap, initialAngleSnap);

    // Attach Event Listeners
    openGdmlButton.addEventListener('click', () => triggerFileInput('gdmlFile'));
    openProjectButton.addEventListener('click', () => triggerFileInput('projectFile'));
    importGdmlButton.addEventListener('click', () => triggerFileInput('gdmlPartFile'));
    importProjectButton.addEventListener('click', () => triggerFileInput('jsonPartFile'));
    importAiResponseButton.addEventListener('click', () => triggerFileInput('aiResponseFile'));
    importStepButton.addEventListener('click', () => triggerFileInput('stepFile'));

    gdmlFileInput.addEventListener('change', (e) => callbacks.onOpenGdmlClicked(e.target.files[0]));
    projectFileInput.addEventListener('change', (e) => callbacks.onOpenProjectClicked(e.target.files[0]));
    gdmlPartFileInput.addEventListener('change', (e) => callbacks.onImportGdmlClicked(e.target.files[0]));
    jsonPartFileInput.addEventListener('change', (e) => callbacks.onImportProjectClicked(e.target.files[0]));
    aiResponseFileInput.addEventListener('change', (e) => callbacks.onImportAiResponseClicked(e.target.files[0]));
    stepFileInput.addEventListener('change', (e) => callbacks.onImportStepClicked(e.target.files[0]));

    newProjectButton.addEventListener('click', callbacks.onNewProjectClicked);
    saveProjectButton.addEventListener('click', callbacks.onSaveProjectClicked);
    exportGdmlButton.addEventListener('click', callbacks.onExportGdmlClicked);

    deleteSelectedObjectButton.addEventListener('click', callbacks.onDeleteSelectedClicked);

    modeObserveButton.addEventListener('click', () => { setActiveModeButton('observe'); callbacks.onModeChangeClicked('observe'); });
    modeTranslateButton.addEventListener('click', () => { setActiveModeButton('translate'); callbacks.onModeChangeClicked('translate'); });
    modeRotateButton.addEventListener('click', () => { setActiveModeButton('rotate'); callbacks.onModeChangeClicked('rotate'); });
    //if(modeScaleButton) modeScaleButton.addEventListener('click', () => { setActiveModeButton('scale'); callbacks.onModeChangeClicked('scale'); });

    toggleWireframeButton.addEventListener('click', callbacks.onWireframeToggleClicked);
    toggleGridButton.addEventListener('click', callbacks.onGridToggleClicked);
    toggleAxesButton.addEventListener('click', callbacks.onAxesToggleClicked);
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
            if(type.startsWith('define')) {
                callbacks.onAddDefineClicked();
            } else if (type.startsWith('solid')) {
                callbacks.onAddSolidClicked();
            } else if (type.startsWith('material')) {
                callbacks.onAddMaterialClicked();
            } else {
                console.log("ERROR: module does not exist")
            }
        });
    });

    // Add listeners for add logical and physical volume buttons
    addAssemblyButton.addEventListener('click', callbacks.onAddAssemblyClicked);
    addAssemblyButton.disabled = false;
    addLVButton.addEventListener('click', callbacks.onAddLVClicked);
    addLVButton.disabled = false;
    addPVButton.addEventListener('click', callbacks.onAddPVClicked);
    addPVButton.disabled = false;

    // AI Panel Listener
    aiGenerateButton.addEventListener('click', () => {
        const promptText = aiPromptInput.value.trim();
        if (promptText) {
            callbacks.onAiGenerateClicked(promptText);
        } else {
            showError("Please enter a prompt for the AI assistant.");
        }
    });

    // API key modal listeners
    setApiKeyButton.addEventListener('click', callbacks.onSetApiKeyClicked);
    saveApiKeyButton.addEventListener('click', () => {
        callbacks.onSaveApiKeyClicked(apiKeyInput.value);
    });
    cancelApiKeyButton.addEventListener('click', hideApiKeyModal);

    // Tab Navigation
    const tabNavButtons = document.querySelectorAll('.tab_button');
    tabNavButtons.forEach(button => {
        button.addEventListener('click', () => {
            const targetTabId = button.dataset.tab;
            activateTab(targetTabId);
        });
    });
    activateTab('tab_structure'); // Default tab

    // --- Global Keyboard Listener ---
    window.addEventListener('keydown', (event) => {
        if (event.key === 'Delete' || event.key === 'Backspace') {
            // Prevent the browser's default back navigation on Backspace
            if (document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
                event.preventDefault();
                callbacks.onDeleteSelectedClicked();
            }
        }
    });

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
export async function populateInspector(itemContext, projectState) {
    if (!inspectorContentDiv) return;
    inspectorContentDiv.innerHTML = '';

    const { type, id, name, data } = itemContext;

    const title = document.createElement('h4');
    title.textContent = `${type}: ${name || id}`;
    inspectorContentDiv.appendChild(title);

    // --- Special handling for Physical Volumes ---
    if (type === 'physical_volume') {
        // Create the smart transform editor for position and rotation
        await createPVTransformEditor(inspectorContentDiv, data, projectState);
        
        // Display other PV properties as read-only
        const otherPropsLabel = document.createElement('h5');
        otherPropsLabel.textContent = "Other Properties";
        otherPropsLabel.style.marginTop = '15px';
        otherPropsLabel.style.borderTop = '1px solid #ccc';
        otherPropsLabel.style.paddingTop = '10px';
        inspectorContentDiv.appendChild(otherPropsLabel);

        // Render other properties as read-only spans
        createReadOnlyProperty(inspectorContentDiv, "Volume Ref:", data.volume_ref);
        createReadOnlyProperty(inspectorContentDiv, "Copy Number:", data.copy_number);

    } else {
        // --- For all other object types, render all properties as read-only ---
        for (const key in data) {
            // Skip redundant or internal properties
            if (key === 'id' || key === 'name' || key === 'phys_children' || typeof data[key] === 'function') continue;

            const value = data[key];
            if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
                // Handle nested objects like 'parameters' or 'value'
                const subDiv = document.createElement('div');
                subDiv.style.paddingLeft = "10px";
                const label = document.createElement('label');
                label.textContent = `${key}:`;
                label.style.fontWeight = 'bold';
                subDiv.appendChild(label);
                
                for (const subKey in value) {
                    createReadOnlyProperty(subDiv, `${subKey}:`, value[subKey]);
                }
                inspectorContentDiv.appendChild(subDiv);
            } else {
                createReadOnlyProperty(inspectorContentDiv, `${key}:`, value);
            }
        }
    }
}

// NEW: Helper to create a simple read-only property line
function createReadOnlyProperty(parent, labelText, value) {
    const propDiv = document.createElement('div');
    propDiv.className = 'property_item readonly';
    const label = document.createElement('label');
    label.textContent = labelText;
    propDiv.appendChild(label);
    
    const valueSpan = document.createElement('span');
    valueSpan.textContent = Array.isArray(value) ? `[Array of ${value.length}]` : value;
    propDiv.appendChild(valueSpan);
    parent.appendChild(propDiv);
}


// NEW: The main function to build the interactive transform editor
async function createPVTransformEditor(parent, pvData, projectState) {
    const transformWrapper = document.createElement('div');
    
    // --- Get defines from the passed-in state, not a new API call ---
    const allDefines = projectState.defines || {};
    const posDefines = {};
    const rotDefines = {};
    for (const name in allDefines) {
        if (allDefines[name].type === 'position') posDefines[name] = allDefines[name];
        if (allDefines[name].type === 'rotation') rotDefines[name] = allDefines[name];
    }
    
    // --- Create Position Editor ---
    const posEditor = buildSingleTransformEditor('position', 'Position (mm)', 'pos', pvData, posDefines);
    transformWrapper.appendChild(posEditor);

    // --- Create Rotation Editor ---
    const rotEditor = buildSingleTransformEditor('rotation', 'Rotation (deg, ZYX)', 'rot', pvData, rotDefines);
    transformWrapper.appendChild(rotEditor);

    parent.appendChild(transformWrapper);
}

// Helper to build one transform block (e.g., for position or rotation)
function buildSingleTransformEditor(transformType, labelText, prefix, pvData, defines) {
    const group = document.createElement('div');
    group.className = 'transform-group';

    // --- 1. Create all DOM elements first ---
    const header = document.createElement('div');
    header.className = 'define-header';
    header.innerHTML = `<span>${labelText}</span>`;
    
    const select = document.createElement('select');
    select.className = 'define-select';
    
    header.appendChild(select);
    group.appendChild(header);

    const inputs = {};
    ['x', 'y', 'z'].forEach(axis => {
        const item = document.createElement('div');
        item.className = 'property_item';
        item.innerHTML = `<label>${axis.toUpperCase()}:</label>`;
        const input = document.createElement('input');
        input.type = 'number';
        input.step = 'any';
        item.appendChild(input);
        group.appendChild(item);
        inputs[axis] = input;
    });

    // --- 2. Create helper to populate inputs from a value object ---
    const updateInputUI = (valueObj) => {
        const val = valueObj || { x: 0, y: 0, z: 0 };
        console.log("Value is ", val)
        if (transformType === 'rotation') {
            inputs.x.value = THREE.MathUtils.radToDeg(val.x || 0).toFixed(3);
            inputs.y.value = THREE.MathUtils.radToDeg(val.y || 0).toFixed(3);
            inputs.z.value = THREE.MathUtils.radToDeg(val.z || 0).toFixed(3);
        } else {
            inputs.x.value = (val.x || 0).toFixed(3);
            inputs.y.value = (val.y || 0).toFixed(3);
            inputs.z.value = (val.z || 0).toFixed(3);
        }
    };
    
    // --- 3. Set the initial state of the component from pvData ---
    populateDefineSelect(select, defines); // Populate options first
    const initialTransformValue = pvData[transformType];

    if (typeof initialTransformValue === 'string' && defines[initialTransformValue]) {
        // State is a define reference
        select.value = initialTransformValue;
        updateInputUI(defines[initialTransformValue].value);
    } else {
        // State is an absolute value object (or null)
        select.value = '[Absolute]';
        updateInputUI(initialTransformValue);
    }

    // --- 4. Attach Event Listeners ---
    
    // Listener for when the user changes the dropdown (e.g., links to a new define)
    select.addEventListener('change', () => {
        const selectedValue = select.value;
        if (selectedValue === '[Absolute]') {
            // Switching TO Absolute. The value should be taken from the currently displayed inputs.
            const currentUiValues = {
                x: parseFloat(inputs.x.value),
                y: parseFloat(inputs.y.value),
                z: parseFloat(inputs.z.value),
            };
            const valuesForBackend = (transformType === 'rotation')
                ? { x: THREE.MathUtils.degToRad(currentUiValues.x), y: THREE.MathUtils.degToRad(currentUiValues.y), z: THREE.MathUtils.degToRad(currentUiValues.z) }
                : currentUiValues;
            callbacks.onInspectorPropertyChanged('physical_volume', pvData.id, transformType, valuesForBackend);
        } else {
            // Switching TO a define. Update the PV to link to this define name.
            // Also, update the input boxes to reflect this define's values.
            const define = defines[selectedValue];
            if (define) {
                updateInputUI(define.value);
                callbacks.onInspectorPropertyChanged('physical_volume', pvData.id, transformType, selectedValue);
            }
        }
    });

    // Listener for when the user types a new value in an input box
    Object.values(inputs).forEach(input => {
        input.addEventListener('change', () => {
            // Read all three boxes to form a complete object
            const newUiValues = {
                x: parseFloat(inputs.x.value),
                y: parseFloat(inputs.y.value),
                z: parseFloat(inputs.z.value),
            };
            const valuesForBackend = (transformType === 'rotation')
                ? { x: THREE.MathUtils.degToRad(newUiValues.x), y: THREE.MathUtils.degToRad(newUiValues.y), z: THREE.MathUtils.degToRad(newUiValues.z) }
                : newUiValues;

            const selectedDefineName = select.value;
            if (selectedDefineName === '[Absolute]') {
                // If absolute, update the PV's own transform property.
                callbacks.onInspectorPropertyChanged('physical_volume', pvData.id, transformType, valuesForBackend);
            } else {
                // If linked to a define, update the define's value property.
                callbacks.onInspectorPropertyChanged('define', selectedDefineName, 'value', valuesForBackend);
            }
        });
    });

    return group;
}

function populateDefineSelect(selectElement, defines) {
    selectElement.innerHTML = '<option value="[Absolute]">[Absolute Value]</option>';
    for (const name in defines) {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        selectElement.appendChild(option);
    }
}

// This function provides the live link from the 3D transform to the UI
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
export function setActiveModeButton(mode) {
    if(modeObserveButton) modeObserveButton.classList.toggle('active_mode', mode === 'observe');
    if(modeTranslateButton) modeTranslateButton.classList.toggle('active_mode', mode === 'translate');
    if(modeRotateButton) modeRotateButton.classList.toggle('active_mode', mode === 'rotate');
    //if(modeScaleButton) modeScaleButton.classList.toggle('active_mode', mode === 'scale');
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
    if(assembliesListRoot) assembliesListRoot.innerHTML = '';
    if(lvolumesListRoot) lvolumesListRoot.innerHTML = '';
    if(definesListRoot) definesListRoot.innerHTML = '';
    if(materialsListRoot) materialsListRoot.innerHTML = '';
    if(solidsListRoot) solidsListRoot.innerHTML = '';

    // --- Grouped Population ---
    populateListWithGrouping(assembliesListRoot, Object.values(projectState.assemblies), 'assembly');
    populateListWithGrouping(lvolumesListRoot, Object.values(projectState.logical_volumes), 'logical_volume');
    populateListWithGrouping(definesListRoot, Object.values(projectState.defines), 'define');
    populateListWithGrouping(materialsListRoot, Object.values(projectState.materials), 'material');
    populateListWithGrouping(solidsListRoot, Object.values(projectState.solids), 'solid');

    // for (const name in projectState.logical_volumes) {
    //     if(lvolumesListRoot) lvolumesListRoot.appendChild(createTreeItem(name, 'logical_volume', name, projectState.logical_volumes[name]));
    // }
    // for (const name in projectState.defines) {
    //     if(definesListRoot) definesListRoot.appendChild(createTreeItem(name, 'define', name, projectState.defines[name]));
    // }
    // for (const name in projectState.materials) {
    //     if(materialsListRoot) materialsListRoot.appendChild(createTreeItem(name, 'material', name, projectState.materials[name]));
    // }
    // for (const name in projectState.solids) {
    //     if(solidsListRoot) solidsListRoot.appendChild(createTreeItem(name, 'solid', name, projectState.solids[name]));
    // }

    // --- Build the physical placement tree (Structure tab) ---
    if (structureTreeRoot) { // Make sure the element exists
        if (projectState.world_volume_ref && projectState.logical_volumes) {
            const worldLV = projectState.logical_volumes[projectState.world_volume_ref];
            if (worldLV) {
                // Create the root of the tree representing the World LV
                const worldItem = createTreeItem(`(World) ${worldLV.name}`, 'logical_volume', worldLV.name, worldLV);
                worldItem.classList.add('world-volume-item'); // Add a class for special styling/selection

                // Now, recursively build the tree for all PVs placed *inside* the world
                if (worldLV.phys_children && worldLV.phys_children.length > 0) {
                    const childrenUl = document.createElement('ul');
                    worldLV.phys_children.forEach(pvData => {
                        const childNode = buildVolumeNode(pvData, projectState);
                        if (childNode) childrenUl.appendChild(childNode);
                    });
                    if (childrenUl.hasChildNodes()) {
                        worldItem.appendChild(childrenUl);
                    }
                }
                structureTreeRoot.appendChild(worldItem);

            } else {
                structureTreeRoot.innerHTML = '<li>World volume not found in logical volumes list.</li>';
            }
        } else {
             structureTreeRoot.innerHTML = '<li>No world volume defined in project.</li>';
        }
    }
}

function populateListWithGrouping(listElement, itemsArray, itemType) {
    if (!listElement) return;
    listElement.innerHTML = ''; // Clear previous content

    if (itemsArray.length <= ITEMS_PER_GROUP) {
        // If there are few enough items, just render them all directly
        itemsArray.forEach(itemData => {
            listElement.appendChild(createTreeItem(itemData.name, itemType, itemData.name, itemData));
        });
    } else {
        // Otherwise, create collapsable folders/groups
        for (let i = 0; i < itemsArray.length; i += ITEMS_PER_GROUP) {
            const group = itemsArray.slice(i, i + ITEMS_PER_GROUP);
            const groupName = `${itemType.charAt(0).toUpperCase() + itemType.slice(1)}s ${i + 1} - ${Math.min(i + ITEMS_PER_GROUP, itemsArray.length)}`;

            const folderLi = document.createElement('li');
            folderLi.classList.add('hierarchy-folder');
            
            const folderToggle = document.createElement('span');
            folderToggle.classList.add('toggle');
            folderToggle.textContent = '[+] ';
            
            const folderNameSpan = document.createElement('span');
            folderNameSpan.classList.add('item-name');
            folderNameSpan.textContent = groupName;

            const folderContentDiv = document.createElement('div');
            folderContentDiv.className = 'tree-item-content';
            folderContentDiv.appendChild(folderToggle);
            folderContentDiv.appendChild(folderNameSpan);
            
            const childrenUl = document.createElement('ul');
            childrenUl.style.display = 'none'; // Initially collapsed

            // Populate the group on-demand when the folder is first opened
            let isPopulated = false;
            folderToggle.addEventListener('click', (e) => {
                e.stopPropagation();
                const isCollapsed = childrenUl.style.display === 'none';
                childrenUl.style.display = isCollapsed ? 'block' : 'none';
                folderToggle.textContent = isCollapsed ? '[-] ' : '[+] ';

                // Lazy-load the content
                if (isCollapsed && !isPopulated) {
                    group.forEach(itemData => {
                        childrenUl.appendChild(createTreeItem(itemData.name, itemType, itemData.name, itemData));
                    });
                    isPopulated = true;
                }
            });
            
            folderLi.appendChild(folderContentDiv);
            folderLi.appendChild(childrenUl);
            listElement.appendChild(folderLi);
        }
    }
}

function buildVolumeNode(pvData, projectState) {
    const allLVs = projectState.logical_volumes;
    const childLVData = allLVs[pvData.volume_ref];
    if (!childLVData) return null; // Safety check

    let displayName = pvData.name || `pv_${pvData.id.substring(0,4)}`;
    displayName += ` (LV: ${childLVData.name})`;

    // The list item represents the Physical Volume
    const pvItem = createTreeItem(displayName, 'physical_volume', pvData.id, pvData, { lvData: childLVData });
    
    // Check if the placed LV has children of its own
    if (childLVData.phys_children && childLVData.phys_children.length > 0) {
        const toggle = document.createElement('span');
        toggle.classList.add('toggle');
        toggle.textContent = '[-] ';
        toggle.onclick = (e) => { e.stopPropagation();
            const childrenUl = pvItem.querySelector('ul');
            if (childrenUl) {
                childrenUl.style.display = childrenUl.style.display === 'none' ? 'block' : 'none';
                toggle.textContent = childrenUl.style.display === 'none' ? '[+] ' : '[-] ';
            }
        };
        // Insert toggle at the beginning of the li content
        const firstSpan = pvItem.querySelector('span');
        if (firstSpan) firstSpan.before(toggle);
        
        const childrenUl = document.createElement('ul');
        childLVData.phys_children.forEach(nestedPvData => {
            const nestedNode = buildVolumeNode(nestedPvData, projectState);
            if (nestedNode) childrenUl.appendChild(nestedNode);
        });
        if (childrenUl.hasChildNodes()) pvItem.appendChild(childrenUl);
    }

    return pvItem;
}

function createTreeItem(displayName, itemType, itemIdForBackend, fullItemData, additionalData = {}) {
    const item = document.createElement('li');
    // --- Add a container for the name and buttons ---
    item.innerHTML = `
        <div class="tree-item-content">
            <span class="item-name">${displayName}</span>
            <div class="item-controls">
                ${itemType === 'physical_volume' ? '<button class="visibility-btn" title="Toggle Visibility">👁️</button>' : ''}
                <button class="delete-item-btn" title="Delete Item">×</button>
            </div>
        </div>
    `;
    item.dataset.type = itemType;
    item.dataset.id = itemIdForBackend;
    item.dataset.name = displayName;
    item.appData = {...fullItemData, ...additionalData};

    // Main click listener for selection
    //const contentDiv = item.querySelector('.tree-item-content');
    item.addEventListener('click', (event) => {
        event.stopPropagation();
        
        const isCtrlHeld = event.ctrlKey;
        const isShiftHeld = event.shiftKey; // We'll handle shift-click later, for now just pass it.

        if (!isCtrlHeld) {
            // If Ctrl is not held, clear all other selections first.
            const allSelected = document.querySelectorAll('#left_panel_container .selected_item');
            allSelected.forEach(sel => {
                if (sel !== item) { // Don't deselect the item we are about to select
                    sel.classList.remove('selected_item');
                }
            });
        }
        
        // Toggle the selection state of the currently clicked item
        item.classList.toggle('selected_item');
        
        // Gather all currently selected items from the DOM
        const selectedItemContexts = [];
        document.querySelectorAll('#left_panel_container .selected_item').forEach(sel => {
            selectedItemContexts.push({
                type: sel.dataset.type,
                id: sel.dataset.id,
                name: sel.dataset.name,
                data: sel.appData // The full data object we stored earlier
            });
        });
        
        // Notify the main controller about the new selection state
        callbacks.onHierarchySelectionChanged(selectedItemContexts);
    });

    // Listener for the new delete button
    const deleteBtn = item.querySelector('.delete-item-btn');
    deleteBtn.addEventListener('click', (event) => {
        event.stopPropagation(); // Prevent the item from being selected
        // We manually call the main delete handler after confirming
        if (confirmAction(`Are you sure you want to delete ${itemType}: ${displayName}?`)) {
            // We need to tell main.js *what* to delete
            callbacks.onDeleteSpecificItemClicked(itemType, itemIdForBackend);
        }
    });

    // Add listener for the new visibility button
    if (itemType === 'physical_volume') {
        const visBtn = item.querySelector('.visibility-btn');

        // --- Set the initial state of the button ---
        const isHidden = SceneManager.isPvHidden(itemIdForBackend);
        item.classList.toggle('item-hidden', isHidden);
        visBtn.style.opacity = isHidden ? '0.4' : '1.0';

        visBtn.addEventListener('click', (event) => {
            event.stopPropagation();

            // Toggle the current state.
            const wasHidden = item.classList.contains('item-hidden');
            const isNowVisible = wasHidden; // If it was hidden, it is now visible.

            item.classList.toggle('item-hidden', !isNowVisible);
            visBtn.style.opacity = isNowVisible ? '1.0' : '0.4';
            callbacks.onPVVisibilityToggle(itemIdForBackend, isNowVisible);
        });
    }

    // For double-clicking of solids, volumes, etc.
    if (itemType === 'define') {
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            callbacks.onEditDefineClicked(item.appData);
        });
    } else if (itemType === 'material') {
        item.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            callbacks.onEditMaterialClicked(item.appData);
        });
    } else if (itemType === 'physical_volume') {
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            // We need to find the parent LV name. For a PV, the LV data is in additionalData.
            const parentLV = findParentLV(item);
            if (parentLV) {
                 callbacks.onEditPVClicked(item.appData, parentLV.dataset.name);
            }
        });
    } else if (itemType === 'solid') {
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            // Pass the solid's data to the handler
            callbacks.onEditSolidClicked(item.appData);
        });
    } else if (itemType === 'logical_volume') {
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            callbacks.onEditLVClicked(item.appData);
        });
    }
    return item;
}

// This function is called by main.js to sync 3D selection TO the hierarchy
export function setHierarchySelection(selectedIds = []) {
    const allItems = document.querySelectorAll('#left_panel_container li[data-id]');
    allItems.forEach(item => {
        // Check if the item's ID is in the array of IDs to select
        const shouldBeSelected = selectedIds.includes(item.dataset.id);
        item.classList.toggle('selected_item', shouldBeSelected);
        
        // Scroll the last selected item into view
        if (shouldBeSelected && item.dataset.id === selectedIds[selectedIds.length - 1]) {
            item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    });
}

// Helper to find the parent LV element in the DOM tree
function findParentLV(pvElement) {
    let current = pvElement.parentElement;
    while(current) {
        if (current.tagName === 'LI' && (current.dataset.type === 'logical_volume' || current.dataset.type === 'physical_volume')) {
            return current;
        }
        current = current.parentElement;
    }
    return null; // Should ideally find the world
}

export function setInspectorTitle(titleText) {
    const title = inspectorContentDiv.querySelector('h4');
    if (title) {
        title.textContent = titleText;
    } else {
        inspectorContentDiv.innerHTML = `<h4>${titleText}</h4>`;
    }
}

// Return the selected parent LV
export function getSelectedParentContext() {
    return selectedParentContext;
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

export function clearHierarchySelection() {
    const selected = document.querySelector('#left_panel_container .selected_item');
    if (selected) selected.classList.remove('selected_item');
    selectedParentContext = null; // Reset the context
}

export function clearHierarchy() {
    if(structureTreeRoot) structureTreeRoot.innerHTML = '';
    if(assembliesListRoot) assembliesListRoot.innerHTML = '';
    if(lvolumesListRoot) lvolumesListRoot.innerHTML = '';
    if(definesListRoot) definesListRoot.innerHTML = '';
    if(materialsListRoot) materialsListRoot.innerHTML = '';
    if(solidsListRoot) solidsListRoot.innerHTML = '';
}

export function clearInspector() {
    if(inspectorContentDiv) inspectorContentDiv.innerHTML = '<p>Select an item.</p>';
}

/**
 * Sets the enabled or disabled state of the AI generate button.
 * @param {boolean} isEnabled True to enable, false to disable.
 * @param {string|null} title Optional tooltip to set on the button.
 */
export function setAiButtonState(isEnabled, title = null) {
    if (aiGenerateButton) {
        aiGenerateButton.disabled = !isEnabled;
        if (title) {
            aiGenerateButton.title = title;
        }
    }
}

/**
 * Sets the state of the AI interaction elements.
 * @param {string} state Can be 'idle', 'loading', or 'disabled'.
 * @param {string|null} title Optional tooltip to set on the button.
 */
export function setAiPanelState(state, title = null) {
    if (!aiPromptInput || !aiGenerateButton) return;

    switch (state) {
        case 'loading':
            aiPromptInput.disabled = true;
            aiGenerateButton.disabled = true;
            aiModelSelect.disabled = true;
            aiGenerateButton.classList.add('loading');
            aiGenerateButton.title = "Processing...";
            break;
        case 'disabled':
            aiPromptInput.disabled = true;
            aiGenerateButton.disabled = true;
            aiModelSelect.disabled = true;
            aiGenerateButton.classList.remove('loading');
            aiGenerateButton.title = title || "AI service is unavailable.";
            break;
        case 'idle':
        default:
            aiPromptInput.disabled = false;
            aiGenerateButton.disabled = false;
            aiModelSelect.disabled = false;
            aiGenerateButton.classList.remove('loading');
            aiGenerateButton.title = title || "Generate with AI";
            break;
    }
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

export function setTreeItemVisibility(pvId, isVisible) {
    const item = document.querySelector(`li[data-id="${pvId}"]`);
    if (item) {
        const visBtn = item.querySelector('.visibility-btn');
        item.classList.toggle('item-hidden', !isVisible);
        if (visBtn) visBtn.style.opacity = isVisible ? '1.0' : '0.4';
    }
}
export function setAllTreeItemVisibility(isVisible) {
    document.querySelectorAll('#tab_structure li[data-type="physical_volume"]').forEach(item => {
        const visBtn = item.querySelector('.visibility-btn');
        item.classList.toggle('item-hidden', !isVisible);
        if (visBtn) visBtn.style.opacity = isVisible ? '1.0' : '0.4';
    });
}

/**
 * Clears the AI prompt input textarea.
 */
export function clearAiPrompt() {
    if (aiPromptInput) {
        aiPromptInput.value = '';
    }
}

/**
 * Populates the AI model selector dropdown with grouped options.
 * @param {object} models - An object like {ollama: [...], gemini: [...]}.
 */
export function populateAiModelSelector(models) {
    if (!aiModelSelect) return;
    
    // Remove all existing model groups before adding new ones.
    const existingGroups = aiModelSelect.querySelectorAll('.model-group, .no-models-option');
    existingGroups.forEach(group => group.remove());

    const createGroup = (label, modelList) => {
        if (modelList && modelList.length > 0) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = label;
            optgroup.classList.add('model-group'); // <-- Add a class for easy removal
            
            modelList.forEach(modelName => {
                const option = document.createElement('option');
                option.value = modelName;
                // Display a friendlier name for Gemini models
                option.textContent = modelName.startsWith('models/') ? `${modelName.split('/')[1]}` : modelName;
                optgroup.appendChild(option);
            });
            aiModelSelect.appendChild(optgroup);
        }
    };
    
    createGroup("Gemini Models", models.gemini);
    createGroup("Ollama Models", models.ollama);

    // If no models were added at all (check both lists)
    const hasGemini = models.gemini && models.gemini.length > 0;
    const hasOllama = models.ollama && models.ollama.length > 0;

    if (!hasGemini && !hasOllama) {
        const option = document.createElement('option');
        option.textContent = "No AI models found";
        option.disabled = true;
        option.classList.add('no-models-option'); // <-- Add class for removal
        aiModelSelect.appendChild(option);
    }
}

/**
 * Gets the currently selected AI model from the dropdown.
 * @returns {string|null}
 */
export function getAiSelectedModel() {
    return aiModelSelect ? aiModelSelect.value : null;
}

// --- Functions for API Key Modal ---
export function showApiKeyModal() {
    if (apiKeyModal) apiKeyModal.style.display = 'block';
}
export function hideApiKeyModal() {
    if (apiKeyModal) apiKeyModal.style.display = 'none';
}
export function setApiKeyInputValue(key) {
    if (apiKeyInput) apiKeyInput.value = key;
}