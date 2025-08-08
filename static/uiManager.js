// static/uiManager.js
import * as THREE from 'three';
import * as SceneManager from './sceneManager.js';
import * as ExpressionInput from './expressionInput.js';

// --- Module-level variables for DOM elements ---
let newProjectButton, saveProjectButton, exportGdmlButton,
    openGdmlButton, openProjectButton, importGdmlButton, importProjectButton,
    importAiResponseButton, importStepButton,
    gdmlFileInput, projectFileInput, gdmlPartFileInput, jsonPartFileInput,
    aiResponseFileInput, stepFileInput,
    deleteSelectedObjectButton,
    modeObserveButton, modeTranslateButton, modeRotateButton, modeScaleButton,
    toggleWireframeButton, toggleGridButton, toggleAxesButton,
    cameraModeOrbitButton, cameraModeFlyButton,
    toggleSnapToGridButton, gridSnapSizeInput, angleSnapSizeInput,
    aiPromptInput, aiGenerateButton, aiModelSelect,
    setApiKeyButton, apiKeyModal, apiKeyInput, saveApiKeyButton, cancelApiKeyButton,
    currentModeDisplay;

// Hierarchy and Inspector
let structureTreeRoot, assembliesListRoot, lvolumesListRoot, definesListRoot, materialsListRoot, 
    elementsListRoot, isotopesListRoot, solidsListRoot, opticalSurfacesListRoot, skinSurfacesListRoot, 
    borderSurfacesListRoot, replicasListRoot;
let inspectorContentDiv;

// Buttons for adding LVs, PVs, and assemblies
let addLVButton, addPVButton, addAssemblyButton;

// Keep track of selected parent LV in structure hierarchy and last selected item
let selectedParentContext = null;
let lastSelectedItem = null; // Stores the DOM element of the last clicked item

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
    onAddElementClicked: ()=>{}, 
    onEditElementClicked: (d)=>{},
    onAddOpticalSurfaceClicked: ()=>{}, 
    onEditOpticalSurfaceClicked: (surfaceData)=>{},
    onAddSkinSurfaceClicked: ()=>{}, 
    onEditSkinSurfaceClicked: (surfaceData)=>{},
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
    addLVButton = document.getElementById('addLVButton');
    addPVButton = document.getElementById('addPVButton');
    addAssemblyButton = document.getElementById('addAssemblyButton');

    // Mode Buttons
    modeObserveButton = document.getElementById('modeObserveButton');
    modeTranslateButton = document.getElementById('modeTranslateButton');
    modeRotateButton = document.getElementById('modeRotateButton');
    modeScaleButton = document.getElementById('modeScaleButton');
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
    elementsListRoot = document.getElementById('elements_list_root');
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
    modeScaleButton.addEventListener('click', () => { setActiveModeButton('scale'); callbacks.onModeChangeClicked('scale'); });

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

    // Add listeners for add object buttons
    addButtons.forEach(button => {
        button.addEventListener('click', (event) => {
            const type = event.target.dataset.addType;
            if(type.startsWith('define')) {
                callbacks.onAddDefineClicked();
            } else if (type.startsWith('solid')) {
                callbacks.onAddSolidClicked();
            } else if (type.startsWith('material')) {
                callbacks.onAddMaterialClicked();
            } else if (type.startsWith('element')) {
                callbacks.onAddElementClicked();
            } else if (type.startsWith('isotope')) {
                callbacks.onAddIsotopeClicked();
            } else if (type.startsWith('optical_surface')) {
                callbacks.onAddOpticalSurfaceClicked();
            } else if (type.startsWith('skin_surface')) {
                callbacks.onAddSkinSurfaceClicked();
            } else if (type.startsWith('border_surface')) {
                callbacks.onAddBorderSurfaceClicked();
            } else {
                console.log("ERROR: module does not exist")
            }
        });
    });

    // Add listeners for add logical and physical volume buttons
    addLVButton.addEventListener('click', callbacks.onAddLVClicked);
    addLVButton.disabled = false;
    addPVButton.addEventListener('click', callbacks.onAddPVClicked);
    addPVButton.disabled = false;
    addAssemblyButton.addEventListener('click', callbacks.onGroupIntoAssemblyClicked);

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

    // Add listeners for the new "+ Group" buttons
    document.querySelectorAll('.add-group-btn').forEach(button => {
        button.addEventListener('click', (event) => {
            const type = event.target.dataset.groupType;
            const groupName = prompt(`Enter a name for the new ${type.replace('_',' ')} group:`);
            if (groupName && groupName.trim()) {
                callbacks.onAddGroup(type, groupName.trim()); 
            }
        });
    });

    // Accordion functionality for Properties tab
    const accordions = document.querySelectorAll('.accordion-header');
    accordions.forEach(accordion => {
        accordion.addEventListener('click', () => {
            const content = accordion.nextElementSibling;
            const toggle = accordion.querySelector('.accordion-toggle');
            
            // Toggle the 'active' class on the content
            content.classList.toggle('active');

            // Update the toggle text based on whether the content is now active
            if (content.classList.contains('active')) {
                toggle.textContent = '[-]';
            } else {
                toggle.textContent = '[+]';
            }
        });
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

// Helper for building transform UI inside the Inspector
function buildInspectorTransformEditor(parent, type, label, pvData, defines, projectState, options = {}) {
    const { isDisabled = false } = options; 

    const group = document.createElement('div');
    group.className = 'transform-group';
    if (isDisabled) {
        group.style.opacity = '0.5';
        group.title = `Scaling is not supported for placements of procedural volumes (${pvData.volume_ref})`;
    }
    
    const header = document.createElement('div');
    header.className = 'define-header';
    header.innerHTML = `<span>${label}</span>`;
    const select = document.createElement('select');
    select.className = 'define-select';
    header.appendChild(select);
    group.appendChild(header);

    const inputsContainer = document.createElement('div');
    inputsContainer.className = 'inline-inputs-container';
    group.appendChild(inputsContainer);

    populateDefineSelect(select, Object.keys(defines));

    // --- Set default values and determine if units are needed ---
    let displayValues = {x: '0', y: '0', z: '0'};
    //let wrapInUnit = false;
    if (type === 'scale') {
        displayValues = {x: '1', y: '1', z: '1'}; // Scale defaults to 1
    }//} else if (type === 'rotation') {
    //    wrapInUnit = true; // Rotations are sent to backend with *deg
    //}

    const data = pvData[type];
    const isAbsolute = typeof data !== 'string' || !defines[data];
    select.value = isAbsolute ? '[Absolute]' : data;
    
    // Determine the initial values to display
    if (isAbsolute) {
        // If it's absolute, the data itself is the dictionary of raw expressions
        displayValues = data || displayValues;
    } else {
        // If it's a define, get the raw expressions from the define object
        const define = defines[data];
        if (define) displayValues = define.raw_expression || displayValues;
    }

    ['x', 'y', 'z'].forEach(axis => {
        // ## Create the component using ExpressionInput.create() ##
        const comp = ExpressionInput.create(
            `inspector_pv_${type}_${axis}`, // Unique ID
            axis.toUpperCase(), // Label
            displayValues[axis] || ((type === 'scale') ? '1' : '0'), // Initial value, default to 1 for scale, 0 for others
            projectState,
            (newValue) => { // onChange callback
                if (select.value === '[Absolute]') {
                    // Read all three values to send a complete object
                    const newAbsValues = {
                        x: document.getElementById(`inspector_pv_${type}_x`).value,
                        y: document.getElementById(`inspector_pv_${type}_y`).value,
                        z: document.getElementById(`inspector_pv_${type}_z`).value,
                    };
                    // if (wrapInUnit) {
                    //     newAbsValues.x = `(${newAbsValues.x}) * deg`;
                    //     newAbsValues.y = `(${newAbsValues.y}) * deg`;
                    //     newAbsValues.z = `(${newAbsValues.z}) * deg`;
                    // }
                    callbacks.onInspectorPropertyChanged('physical_volume', pvData.id, type, newAbsValues);
                }
            }
        );
        inputsContainer.appendChild(comp);
        
        // Disable inputs if a define is selected
        const inputEl = comp.querySelector('.expression-input');
        if (inputEl) inputEl.disabled = !isAbsolute || isDisabled;
    });

    select.addEventListener('change', (e) => {

        // Prevent changes if disabled
        if (isDisabled) { 
            e.target.value = isAbsolute ? '[Absolute]' : data; // Revert selection
            return;
        }

        const defaultValue = (type === 'scale') ? { x: '1', y: '1', z: '1' } : { x: '0', y: '0', z: '0' };
        const newValue = e.target.value === '[Absolute]' ? defaultValue : e.target.value;
        callbacks.onInspectorPropertyChanged('physical_volume', pvData.id, type, newValue);
    });

    parent.appendChild(group);
}

// --- Inspector Panel Management ---
export async function populateInspector(itemContext, projectState) {
    if (!inspectorContentDiv) return;
    inspectorContentDiv.innerHTML = '';

    const { type, id, name, data } = itemContext;

    const title = document.createElement('h4');
    title.textContent = `${type}: ${name || id}`;
    inspectorContentDiv.appendChild(title);

    if (type === 'physical_volume') {
        const allDefines = projectState.defines || {};
        const posDefines = {};
        const rotDefines = {};
        const sclDefines = {};
        for (const defName in allDefines) {
            if (allDefines[defName].type === 'position') posDefines[defName] = allDefines[defName];
            if (allDefines[defName].type === 'rotation') rotDefines[defName] = allDefines[defName];
            if (allDefines[defName].type === 'scale')    sclDefines[defName] = allDefines[defName];
        }

        // Check if the placed LV is procedural
        const lvData = projectState.logical_volumes[data.volume_ref];
        const isProcedural = lvData && lvData.content_type !== 'physvol';

        buildInspectorTransformEditor(inspectorContentDiv, 'position', 'Position (mm)',  data, posDefines, projectState, { isDisabled: isProcedural });
        buildInspectorTransformEditor(inspectorContentDiv, 'rotation', 'Rotation (rad)', data, rotDefines, projectState, { isDisabled: isProcedural });
        buildInspectorTransformEditor(inspectorContentDiv, 'scale', 'Scale', data, sclDefines, projectState, { isDisabled: isProcedural });
        
        const otherPropsLabel = document.createElement('h5');
        otherPropsLabel.textContent = "Other Properties";
        otherPropsLabel.style.marginTop = '15px';
        otherPropsLabel.style.borderTop = '1px solid #ccc';
        otherPropsLabel.style.paddingTop = '10px';
        inspectorContentDiv.appendChild(otherPropsLabel);

        createReadOnlyProperty(inspectorContentDiv, "Volume Ref:", data.volume_ref);
        createReadOnlyProperty(inspectorContentDiv, "Copy Number:", data.copy_number);

    } else if (type === 'logical_volume') {
        
        // Check its content type to decide what to show
        if (data.content_type === 'replica') {
            // Show the Replica editor UI
            const replica = data.content;
            createReadOnlyProperty(inspectorContentDiv, "Solid (Envelope):", data.solid_ref);
            createReadOnlyProperty(inspectorContentDiv, "Replicated LV:", replica.volume_ref);
            // TODO: Create editable expression inputs for these
            createReadOnlyProperty(inspectorContentDiv, "Number:", replica.number);
            createReadOnlyProperty(inspectorContentDiv, "Width:", replica.width);
            createReadOnlyProperty(inspectorContentDiv, "Offset:", replica.offset);
            const dir = replica.direction;
            createReadOnlyProperty(inspectorContentDiv, "Direction:", `(x: ${dir.x}, y: ${dir.y}, z: ${dir.z})`);
        }
        else { // It's a standard LV (or another procedural type for later)
             createReadOnlyProperty(inspectorContentDiv, "Solid Ref:", data.solid_ref);
             createReadOnlyProperty(inspectorContentDiv, "Material Ref:", data.material_ref);
             // Could add a list of its physvol children here if desired
        }
    } else if (type === 'replica') {
        createReadOnlyProperty(inspectorContentDiv, "Volume Ref:", data.volume_ref);
        createReadOnlyProperty(inspectorContentDiv, "Number:", data.number);
        createReadOnlyProperty(inspectorContentDiv, "Width:", data.width);
        createReadOnlyProperty(inspectorContentDiv, "Offset:", data.offset);
        const dir = data.direction;
        createReadOnlyProperty(inspectorContentDiv, "Direction:", `(x: ${dir.x}, y: ${dir.y}, z: ${dir.z})`);
    } else {
        for (const key in data) {
            if (key === 'id' || key === 'name' || key === 'phys_children' || typeof data[key] === 'function') continue;
            const value = data[key];
            if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
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

// Helper to create a simple read-only property line
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


// The main function to build the interactive transform editor
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
    const posEditor = buildSingleTransformEditor('position', 'Position (mm)', pvData, posDefines);
    transformWrapper.appendChild(posEditor);

    // --- Create Rotation Editor ---
    const rotEditor = buildSingleTransformEditor('rotation', 'Rotation (deg, ZYX)', pvData, rotDefines);
    transformWrapper.appendChild(rotEditor);

    parent.appendChild(transformWrapper);
}

// Helper to build one transform block (e.g., for position or rotation)
function buildSingleTransformEditor(transformType, labelText, pvData, defines) {
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
        // Default to a safe object if valueObj is null/undefined
        const val = valueObj || { x: 0, y: 0, z: 0 };
        
        if (transformType === 'rotation') {
            // Use parseFloat to handle both numbers and string representations of numbers
            inputs.x.value = THREE.MathUtils.radToDeg(parseFloat(val.x || 0)).toFixed(3);
            inputs.y.value = THREE.MathUtils.radToDeg(parseFloat(val.y || 0)).toFixed(3);
            inputs.z.value = THREE.MathUtils.radToDeg(parseFloat(val.z || 0)).toFixed(3);
        } else {
            inputs.x.value = parseFloat(val.x || 0).toFixed(3);
            inputs.y.value = parseFloat(val.y || 0).toFixed(3);
            inputs.z.value = parseFloat(val.z || 0).toFixed(3);
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

/**
 * Enables or disables transformation mode buttons based on provided state.
 * @param {object} state - An object with keys 'translate', 'rotate', 'scale' and boolean values.
 * @param {string} [reason=''] - An optional tooltip to show when disabled.
 */
export function setTransformButtonsState(state, reason = '') {
    const buttons = {
        translate: modeTranslateButton,
        rotate: modeRotateButton,
        scale: modeScaleButton
    };

    for (const mode in buttons) {
        if (buttons[mode]) {
            const isEnabled = state[mode] === true; // Explicitly check for true
            buttons[mode].disabled = !isEnabled;
            buttons[mode].title = isEnabled ? `Activate ${mode.charAt(0).toUpperCase() + mode.slice(1)} Mode` : reason;
        }
    }
}

function populateDefineSelect(selectElement, definesArray) {
    selectElement.innerHTML = '<option value="[Absolute]">[Absolute Value]</option>';
    definesArray.forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        selectElement.appendChild(option);
    });
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

    // --- Get all the list root elements ---
    structureTreeRoot = document.getElementById('structure_tree_root');
    assembliesListRoot = document.getElementById('assemblies_list_root');
    lvolumesListRoot = document.getElementById('lvolumes_list_root');
    definesListRoot = document.getElementById('defines_list_root');
    materialsListRoot = document.getElementById('materials_list_root');
    elementsListRoot = document.getElementById('elements_list_root');
    isotopesListRoot = document.getElementById('isotopes_list_root');
    solidsListRoot = document.getElementById('solids_list_root');
    opticalSurfacesListRoot = document.getElementById('optical_surfaces_list_root');
    skinSurfacesListRoot = document.getElementById('skin_surfaces_list_root');
    borderSurfacesListRoot = document.getElementById('border_surfaces_list_root');

    // Clear all lists
    if(structureTreeRoot) structureTreeRoot.innerHTML = '';
    if(assembliesListRoot) assembliesListRoot.innerHTML = '';
    if(lvolumesListRoot) lvolumesListRoot.innerHTML = '';
    if(definesListRoot) definesListRoot.innerHTML = '';
    if(materialsListRoot) materialsListRoot.innerHTML = '';
    if(elementsListRoot) elementsListRoot.innerHTML = '';
    if(isotopesListRoot) isotopesListRoot.innerHTML = '';
    if(solidsListRoot) solidsListRoot.innerHTML = '';
    if(opticalSurfacesListRoot) opticalSurfacesListRoot.innerHTML = '';
    if(skinSurfacesListRoot) skinSurfacesListRoot.innerHTML = '';
    if(borderSurfacesListRoot) borderSurfacesListRoot.innerHTML = '';

    // --- Grouped Population ---
    populateListWithGrouping(assembliesListRoot, Object.values(projectState.assemblies), 'assembly');
    populateListWithGrouping(lvolumesListRoot, Object.values(projectState.logical_volumes), 'logical_volume');
    populateListWithGrouping(definesListRoot, Object.values(projectState.defines), 'define');
    populateListWithGrouping(materialsListRoot, Object.values(projectState.materials), 'material');
    populateListWithGrouping(elementsListRoot, Object.values(projectState.elements || {}), 'element');
    populateListWithGrouping(isotopesListRoot, Object.values(projectState.isotopes || {}), 'isotope');
    populateListWithGrouping(solidsListRoot, Object.values(projectState.solids), 'solid');
    populateListWithGrouping(opticalSurfacesListRoot, Object.values(projectState.optical_surfaces || {}), 'optical_surface');
    populateListWithGrouping(skinSurfacesListRoot, Object.values(projectState.skin_surfaces || {}), 'skin_surface');
    populateListWithGrouping(borderSurfacesListRoot, Object.values(projectState.border_surfaces || {}), 'border_surface');

    // --- Build the physical placement tree (Structure tab) ---
    if (structureTreeRoot) { // Make sure the element exists
        if (projectState.world_volume_ref && projectState.logical_volumes) {
            const worldLV = projectState.logical_volumes[projectState.world_volume_ref];
            if (worldLV) {

                // Create the root of the tree representing the World LV
                const worldItem = createTreeItem(worldLV.name, 'logical_volume', worldLV.id, worldLV);
                worldItem.classList.add('world-volume-item'); // Add a class for special styling/selection
                // Prepend the "(World)" text visually after the item is created
                const nameSpan = worldItem.querySelector('.item-name');
                if (nameSpan) {
                    nameSpan.innerHTML = `<span style="font-weight:normal; color:#555;">(World) </span>` + nameSpan.innerHTML;
                }

                // Now, recursively build the tree for all PVs placed *inside* the world
                const world_children_to_process = (worldLV.content_type === 'physvol') ? worldLV.content : [];
                if (world_children_to_process && world_children_to_process.length > 0) {
                    const childrenUl = document.createElement('ul');
                    world_children_to_process.forEach(pvData => {
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

    // --- Get the most current state using the new callback ---
    const projectState = callbacks.getProjectState?.();
    const groups = (projectState?.ui_groups?.[itemType]) || [];
    const groupedItemIds = new Set();

    // 1. Render all the folders first
    groups.forEach(group => {
        const folderLi = createFolderElement(group.name, itemType, true);
        listElement.appendChild(folderLi);

        const childrenUl = folderLi.querySelector('ul');
        group.members.forEach(memberId => {
            const itemData = itemsArray.find(item => item.name === memberId);
            if (itemData) {
                childrenUl.appendChild(createTreeItem(itemData.name, itemType, itemData.name, itemData));
                groupedItemIds.add(memberId);
            }
        });
        // If a folder is empty, add a placeholder
        if (childrenUl.children.length === 0) {
            const placeholder = document.createElement('li');
            placeholder.className = 'empty-folder-placeholder';
            placeholder.textContent = '(empty)';
            childrenUl.appendChild(placeholder);
        }
    });

    // 2. Add a drop target for "ungrouped" items
    const ungroupedDropTarget = document.createElement('div');
    ungroupedDropTarget.className = 'ungrouped-drop-target';
    addDropHandling(ungroupedDropTarget, itemType, null); // null target group name means ungroup
    listElement.appendChild(ungroupedDropTarget);

    // 3. Render all ungrouped items
    itemsArray.forEach(itemData => {
        if (!groupedItemIds.has(itemData.name)) {
            listElement.appendChild(createTreeItem(itemData.name, itemType, itemData.name, itemData));
        }
    });
}

// --- Helper for creating folder elements ---
function createFolderElement(name, itemType, isDroppable) {
    const folderLi = document.createElement('li');
    folderLi.className = 'hierarchy-folder';
    folderLi.dataset.groupName = name;
    folderLi.dataset.groupType = itemType;

    const folderContent = document.createElement('div');
    folderContent.className = 'tree-item-content';
    
    const toggle = document.createElement('span');
    toggle.className = 'toggle';
    toggle.textContent = '[-] ';
    
    const nameSpan = document.createElement('span');
    nameSpan.className = 'item-name';
    nameSpan.textContent = name;

    const controlsDiv = document.createElement('div');
    controlsDiv.className = 'folder-controls';
    controlsDiv.innerHTML = `
        <button class="rename-group-btn" title="Rename Group">✏️</button>
        <button class="delete-group-btn" title="Delete Group">🗑️</button>
    `;
    
    folderContent.appendChild(toggle);
    folderContent.appendChild(nameSpan);
    folderContent.appendChild(controlsDiv);
    
    const childrenUl = document.createElement('ul');
    folderLi.appendChild(folderContent);
    folderLi.appendChild(childrenUl);

    toggle.addEventListener('click', (e) => {
        e.stopPropagation();
        const isHidden = childrenUl.style.display === 'none';
        childrenUl.style.display = isHidden ? '' : 'none';
        toggle.textContent = isHidden ? '[-] ' : '[+] ';
    });

    controlsDiv.querySelector('.rename-group-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        const newName = prompt(`Rename group "${name}" to:`, name);
        if (newName && newName.trim() && newName.trim() !== name) {
            callbacks.onRenameGroup(itemType, name, newName.trim());
        }
    });

    controlsDiv.querySelector('.delete-group-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        if (confirmAction(`Are you sure you want to delete the group "${name}"? Items inside will become ungrouped.`)) {
            callbacks.onDeleteGroup(itemType, name);
        }
    });

    if (isDroppable) {
        addDropHandling(folderContent, itemType, name);
    }
    
    return folderLi;
}

function buildVolumeNode(pvData, projectState) {
        if (!pvData) return null;

        const allLVs = projectState.logical_volumes || {};
        const allAssemblies = projectState.assemblies || {};

        // Determine if this PV is placing an Assembly or a Logical Volume
        const isAssemblyPlacement = allAssemblies[pvData.volume_ref];
        const childLVData = allLVs[pvData.volume_ref];

        let displayName = pvData.name || `pv_${pvData.id.substring(0, 4)}`;
        let itemElement;

        if (isAssemblyPlacement) {
            // --- This PV is an Assembly Placement ---
            const assembly = isAssemblyPlacement;
            displayName = `<span class="assembly-icon" title="Assembly">📁</span> ` + displayName;
            displayName += ` (Assembly: ${pvData.volume_ref})`;

            // The main item represents the PV that places the assembly
            itemElement = createTreeItem(displayName, 'physical_volume', pvData.id, pvData);
            
            // Its children are the PVs inside the assembly
            if (assembly.placements && assembly.placements.length > 0) {
                const childrenUl = document.createElement('ul');
                assembly.placements.forEach(nestedPvData => {
                    // Recursively build nodes for each PV inside the assembly
                    const nestedNode = buildVolumeNode(nestedPvData, projectState);
                    if (nestedNode) childrenUl.appendChild(nestedNode);
                });
                if (childrenUl.hasChildNodes()) {
                    addToggle(itemElement, childrenUl);
                    itemElement.appendChild(childrenUl);
                }
            }
        } else if (childLVData) {
            // --- This PV is a standard Logical Volume Placement ---
            displayName += ` (LV: ${pvData.volume_ref})`;

            itemElement = createTreeItem(displayName, 'physical_volume', pvData.id, pvData, { lvData: childLVData });

            // Its children are the PVs inside the placed LV
            const children_to_process = (childLVData.content_type === 'physvol') ? childLVData.content : [];
            if (children_to_process && children_to_process.length > 0) {
                const childrenUl = document.createElement('ul');
                children_to_process.forEach(nestedPvData => {
                    const nestedNode = buildVolumeNode(nestedPvData, projectState);
                    if (nestedNode) childrenUl.appendChild(nestedNode);
                });
                if (childrenUl.hasChildNodes()) {
                    addToggle(itemElement, childrenUl);
                    itemElement.appendChild(childrenUl);
                }
            }
        } else {
            // This is a broken reference, but we can still show the placement
            displayName += ` (Broken Ref: ${pvData.volume_ref})`;
            itemElement = createTreeItem(displayName, 'physical_volume', pvData.id, pvData);
            itemElement.style.color = 'red';
        }

        return itemElement;
    }

function addToggle(parentLi, childrenUl) {
    const toggle = document.createElement('span');
    toggle.classList.add('toggle');
    toggle.textContent = '[-] ';
    toggle.onclick = (e) => {
        e.stopPropagation();
        const isHidden = childrenUl.style.display === 'none';
        childrenUl.style.display = isHidden ? 'block' : 'none';
        toggle.textContent = isHidden ? '[-] ' : '[+] ';
    };
    const firstSpan = parentLi.querySelector('.item-name');
    if (firstSpan) firstSpan.before(toggle);
}

function createTreeItem(displayName, itemType, itemIdForBackend, fullItemData, additionalData = {}) {
    const item = document.createElement('li');

    // --- DRAG LOGIC ---
    const draggableTypes = ['physical_volume', 'solid', 'material', 'element', 'define', 
                            'optical_surface', 'skin_surface', 'border_surface'];

    // Make the item draggable if it's a type that can be moved or grouped
    if (draggableTypes.includes(itemType)) {
        item.draggable = true; // Make the item draggable!
        
        // --- Add dragstart listener ---
        item.addEventListener('dragstart', (event) => {
            event.stopPropagation();
            
            const selectedItems = document.querySelectorAll('#left_panel_container .selected_item');
            let dragData;

            // Check if the item being dragged is part of the current selection
            const isDraggingSelectedItem = Array.from(selectedItems).some(el => el.dataset.id === itemIdForBackend);
            const isMultiDrag = selectedItems.length > 1 && isDraggingSelectedItem;

            if (isMultiDrag) {
                // Dragging a part of a multi-selection
                const itemsToDrag = Array.from(selectedItems)
                    // IMPORTANT: Only drag items of the same type!
                    .filter(el => el.dataset.type === itemType) 
                    .map(el => ({ id: el.dataset.id, type: el.dataset.type }));
                
                dragData = { type: 'multi-selection', items: itemsToDrag };

                // --- CUSTOM DRAG IMAGE LOGIC ---
                if (itemsToDrag.length > 0) {
                    const dragHelper = document.getElementById('drag-image-helper');
                    // Create a simple but effective visual: a stack icon and a count
                    dragHelper.innerHTML = `
                        <span style="font-size: 18px;">📋</span>
                        <span>${itemsToDrag.length} ${itemType}(s)</span>
                    `;
                    // Use setDragImage to replace the default browser ghost image.
                    // The (0, 0) coordinates mean the cursor will be at the top-left of our custom image.
                    // You can adjust these to center it, e.g., (dragHelper.offsetWidth / 2, dragHelper.offsetHeight / 2)
                    event.dataTransfer.setDragImage(dragHelper, 10, 10);
                }
            } else {
                // Dragging a single item (even if others are selected)
                dragData = { type: 'single-item', id: itemIdForBackend, itemType: itemType };
            }
            
            event.dataTransfer.setData('application/json', JSON.stringify(dragData));
            event.dataTransfer.effectAllowed = 'move';
            
            // Add a class to all dragged items for styling
            if (isMultiDrag) {
                selectedItems.forEach(el => {
                    if(el.dataset.type === itemType) el.classList.add('dragging');
                });
            } else {
                item.classList.add('dragging');
            }
        });

        item.addEventListener('dragend', (event) => {
            event.stopPropagation();
            item.classList.remove('dragging');
        });
    }

    // --- Add a container for the name and buttons ---
    let finalDisplayName = displayName; // Start with the passed name
    // Add an icon for procedural volumes in the main hierarchy view
    if (itemType === 'logical_volume' && fullItemData.content_type && fullItemData.content_type !== 'physvol') {
        const icon = `<span class="procedural-icon" title="Type: ${fullItemData.content_type}">⚙️</span>`;
        finalDisplayName = icon + ' ' + displayName;
    }

    item.innerHTML = `
        <div class="tree-item-content">
            <span class="item-name">${finalDisplayName}</span>
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

    // --- DROP LOGIC (NEW) ---
    // An item can be a drop target if it's an LV that can contain PVs, or a PV that represents an Assembly.
    const isStandardLV = itemType === 'logical_volume' && fullItemData.content_type === 'physvol';
    const isAssemblyPlacement = itemType === 'physical_volume' && (callbacks.getProjectState()?.assemblies || {})[fullItemData.volume_ref];

    if (isStandardLV || isAssemblyPlacement) {
        item.addEventListener('dragover', e => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            item.classList.add('drop-target-hover');
        });
        item.addEventListener('dragleave', () => item.classList.remove('drop-target-hover'));
        item.addEventListener('drop', (event) => {
            event.preventDefault();
            event.stopPropagation(); // Prevent event bubbling up to parent drop targets
            item.classList.remove('drop-target-hover');
            const data = JSON.parse(event.dataTransfer.getData('application/json'));

            // We only handle dropping physical volumes for now
            if (data.itemType !== 'physical_volume') return;

            const pvIds = (data.type === 'multi-selection') ? data.items.map(i => i.id) : [data.id];

            if (isAssemblyPlacement) {
                const assemblyName = fullItemData.volume_ref;
                callbacks.onMovePvToAssembly(pvIds, assemblyName);
            } else { // isStandardLV
                const lvName = fullItemData.name;
                callbacks.onMovePvToLv(pvIds, lvName);
            }
        });
    }

    // Main click listener for selection
    item.addEventListener('click', (event) => {
        event.stopPropagation();

        const parentList = item.closest('ul');
        if (!parentList) return;
        
        const isCtrlHeld = event.ctrlKey;
        const isShiftHeld = event.shiftKey; // We'll handle shift-click later, for now just pass it.

        if (isShiftHeld && lastSelectedItem && lastSelectedItem.parentElement === parentList) {
            // --- SHIFT-CLICK LOGIC ---
            // Don't deselect others. Find the range between lastSelectedItem and current item.
            const allItems = Array.from(parentList.children);
            const startIndex = allItems.indexOf(lastSelectedItem);
            const endIndex = allItems.indexOf(item);
            
            // Clear previous selections IN THIS LIST ONLY before applying the new range
            allItems.forEach(li => li.classList.remove('selected_item'));

            const minIndex = Math.min(startIndex, endIndex);
            const maxIndex = Math.max(startIndex, endIndex);

            for (let i = minIndex; i <= maxIndex; i++) {
                allItems[i].classList.add('selected_item');
            }
            // Do not update lastSelectedItem on shift-click, so the anchor remains the same.
        } else if (isCtrlHeld) {
            // --- CTRL-CLICK LOGIC ---
            // Toggle the current item's selection state
            item.classList.toggle('selected_item');
            lastSelectedItem = item; // A ctrl-click also sets the anchor
        } else {
            // --- NORMAL CLICK LOGIC ---
            // Deselect everything in all lists first
            document.querySelectorAll('#left_panel_container .selected_item').forEach(sel => {
                sel.classList.remove('selected_item');
            });
            // Select only the current item
            item.classList.add('selected_item');
            lastSelectedItem = item; // This is the new anchor for future shift-clicks
        }
        
        // --- UNIFIED NOTIFICATION ---
        // After any selection change, gather all selected items across all lists and notify main.js
        const selectedItemContexts = [];
        document.querySelectorAll('#left_panel_container .selected_item').forEach(sel => {
            // We need to ensure we don't select the folder 'li' itself, only item 'li's
            if (sel.dataset.id) { 
                selectedItemContexts.push({
                    type: sel.dataset.type,
                    id: sel.dataset.id,
                    name: sel.dataset.name,
                    data: sel.appData
                });
            }
        });
        
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

    // For double-clicking physical volumes
    if (itemType === 'physical_volume') {

        // Add visibility button
        const visBtn = item.querySelector('.visibility-btn');
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

            // Call the main handler from main.js.
            // The third argument (isRecursive) is true by default if not provided.
            // If the user holds Alt, we can do a non-recursive toggle.
            const isRecursiveToggle = !event.altKey;
            callbacks.onPVVisibilityToggle(itemIdForBackend, isNowVisible, isRecursiveToggle);
        });

        // Add double-click listener
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            // We need to find the parent LV name. For a PV, the LV data is in additionalData.
            const parentLV = findParentLV(item);
            if (parentLV) {
                 callbacks.onEditPVClicked(item.appData, parentLV.dataset.name);
            }
        });
    }
    // For double-clicking of solids, volumes, etc.
    else if (itemType === 'define') {
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            callbacks.onEditDefineClicked(item.appData);
        });
    } else if (itemType === 'material') {
        item.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            callbacks.onEditMaterialClicked(item.appData);
        });
    } else if (itemType === 'element') {
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            callbacks.onEditElementClicked(item.appData);
        });
    } else if (itemType === 'isotope') {
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            callbacks.onEditIsotopeClicked(item.appData);
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
    } else if (itemType === 'optical_surface') {
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            callbacks.onEditOpticalSurfaceClicked(item.appData);
        });
    } else if (itemType === 'skin_surface') {
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            callbacks.onEditSkinSurfaceClicked(item.appData);
        });
    } else if (itemType === 'border_surface') {
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            callbacks.onEditBorderSurfaceClicked(item.appData);
        });
    }
    return item;
}

/**
 * Creates a list item for a procedural placement (Replica, Division, etc.).
 * @param {object} itemData - The data object for the procedural placement.
 * @param {string} parentLVName - The name of the logical volume this placement belongs to.
 * @returns {HTMLElement} The created <li> element.
 */
function createProceduralItem(itemData, parentLVName) {
    const item = document.createElement('li');
    let displayName = `Replica of '${itemData.volume_ref}' in '${parentLVName}'`;
    
    // You can add more display logic for other types here later
    // if (itemData.type === 'division') { ... }

    // Use the same consistent layout as other tree items
    item.innerHTML = `
        <div class="tree-item-content">
            <span class="item-name">${displayName}</span>
            <div class="item-controls">
                <button class="delete-item-btn" title="Delete Item">×</button>
            </div>
        </div>
    `;

    // Store data on the element for later access (for the inspector, editing, etc.)
    item.dataset.type = itemData.type; // 'replica', 'division', etc.
    item.dataset.id = itemData.id;
    item.dataset.name = displayName;
    item.appData = itemData; // Store the full object

    // Add a click listener for selection
    item.addEventListener('click', (event) => {
        event.stopPropagation();
        // Simple selection: deselect all others and select this one
        document.querySelectorAll('#left_panel_container .selected_item').forEach(sel => {
            sel.classList.remove('selected_item');
        });
        item.classList.add('selected_item');
        
        // Notify main.js of the selection
        // We package it in an array to be consistent with multi-select logic
        callbacks.onHierarchySelectionChanged([{
            type: item.dataset.type,
            id: item.dataset.id,
            name: item.dataset.name,
            data: item.appData
        }]);
    });

    // Add delete button listener
    const deleteBtn = item.querySelector('.delete-item-btn');
    deleteBtn.addEventListener('click', (event) => {
        event.stopPropagation();
        if (confirmAction(`Are you sure you want to delete this ${itemData.type} placement?`)) {
            // Note: Deleting procedural placements is more complex than other objects.
            // This will require a new API endpoint. For now, we can log it.
            console.log(`TODO: Implement deletion for procedural child with ID ${itemData.id} from parent ${parentLVName}`);
            showError("Deletion for procedural placements is not yet implemented.");
            // callbacks.onDeleteSpecificItemClicked(itemData.type, itemData.id, { parent: parentLVName });
        }
    });

    // Add double-click listener for editing
    item.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        console.log(`TODO: Open editor for ${itemData.type} with ID ${itemData.id}`);
        showError(`Editing for ${itemData.type} placements is not yet implemented.`);
    });


    return item;
}

// --- Centralized Drag & Drop Logic ---
function addDropHandling(element, itemType, targetGroupName) {
    element.addEventListener('dragover', (event) => {
        event.preventDefault(); // Necessary to allow a drop
        element.classList.add('drop-target-hover');
    });
    element.addEventListener('dragleave', () => {
        element.classList.remove('drop-target-hover');
    });
    element.addEventListener('drop', (event) => {
        event.preventDefault();
        element.classList.remove('drop-target-hover');
        
        const data = JSON.parse(event.dataTransfer.getData('application/json'));
        let itemIdsToMove;
        let dragItemType;

        if (data.type === 'multi-selection') {
            if (data.items.length === 0) return;
            // All items in a multi-drag must be of the same type for this to work
            dragItemType = data.items[0].type;
            if (dragItemType !== itemType) {
                showError(`Cannot move items of type '${dragItemType}' into a '${itemType}' group.`);
                return;
            }
            itemIdsToMove = data.items.map(item => item.id);
        } else if (data.type === 'single-item') {
            dragItemType = data.itemType;
            if (dragItemType !== itemType) {
                showError(`Cannot move a '${dragItemType}' into a '${itemType}' group.`);
                return;
            }
            itemIdsToMove = [data.id];
        }

        if (itemIdsToMove && itemIdsToMove.length > 0) {
            callbacks.onMoveItemsToGroup(itemType, itemIdsToMove, targetGroupName);
        }
    });
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

// Helper function to find all descendant PVs in the hierarchy view
export function getDescendantPvIds(startElement) {
    const ids = [];
    // The `querySelectorAll` will find all `<li>` elements at any level of nesting inside the startElement
    const descendants = startElement.querySelectorAll('li[data-type="physical_volume"]');
    descendants.forEach(li => {
        if (li.dataset.id) {
            ids.push(li.dataset.id);
        }
    });
    return ids;
}

/**
 * Gets the common parent context for all currently selected items in the hierarchy.
 * Returns null if items have different parents or if no valid parent is found.
 * @returns {object | null} The parent context { type, id, name, data } or null.
 */
export function getSelectedParentContext() {
    const selectedItems = document.querySelectorAll('#structure_tree_root .selected_item');
    if (selectedItems.length === 0) {
        return null;
    }

    let firstParent = null;

    for (let i = 0; i < selectedItems.length; i++) {
        const item = selectedItems[i];
        const currentParentEl = findParentInHierarchy(item);

        if (!currentParentEl) {
            // This item has no valid parent in the hierarchy (should not happen for PVs)
            return null;
        }

        if (i === 0) {
            // This is the first item, establish its parent as the reference parent
            firstParent = currentParentEl;
        } else if (currentParentEl !== firstParent) {
            // A subsequent item has a different parent. The selection is not unified.
            return null;
        }
    }

    // If we get here, all items share the same parent. Return its context.
    if (firstParent) {
        return {
            type: firstParent.dataset.type,
            id: firstParent.dataset.id,
            name: firstParent.dataset.name,
            data: firstParent.appData
        };
    }
    
    return null;
}

/**
 * Helper function to traverse up the DOM from a hierarchy item to find its parent item (LV or PV).
 * @param {HTMLElement} element - The starting list item.
 * @returns {HTMLElement | null} The parent list item element or null.
 */
function findParentInHierarchy(element) {
    if (!element) return null;
    // Go up two levels (from <li> to <ul> to parent <li>)
    let parent = element.parentElement?.parentElement; 
    if (parent && parent.tagName === 'LI' && parent.dataset.id) {
        return parent;
    }
    return null; // Reached the top of the tree
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
    if(elementsListRoot) elementsListRoot.innerHTML = '';
    if(isotopesListRoot) isotopesListRoot.innerHTML = '';
    if(solidsListRoot) solidsListRoot.innerHTML = '';
    if(opticalSurfacesListRoot) opticalSurfacesListRoot.innerHTML = '';
    if(skinSurfacesListRoot) skinSurfacesListRoot.innerHTML = '';
    if(borderSurfacesListRoot) borderSurfacesListRoot.innerHTML = '';
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