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
    cameraModeOriginButton, cameraModeSelectedButton,
    toggleSnapToGridButton, gridSnapSizeInput, angleSnapSizeInput,
    bottomPanel, toggleBottomPanelBtn,
    aiPromptInput, aiGenerateButton, aiModelSelect,
    setApiKeyButton, apiKeyModal, apiKeyInput, saveApiKeyButton, cancelApiKeyButton,
    currentModeDisplay;

// Hierarchy and Inspector
let structureTreeRoot, assembliesListRoot, lvolumesListRoot, definesListRoot, materialsListRoot,
    elementsListRoot, isotopesListRoot, solidsListRoot, opticalSurfacesListRoot, skinSurfacesListRoot,
    borderSurfacesListRoot;
let inspectorContentDiv;

// Project, history and undo/redo
let projectNameDisplay, historyButton, historyPanel, closeHistoryPanel, historyListContainer,
    undoButton, redoButton, projectNameWrapper, projectListDropdown;

// Button for adding PVs
let addPVButton;

// Button for creating ring arrays
let createRingArrayButton;

// Loading overlay
let loadingOverlay, loadingMessage;

// Status indicator for autosave
let statusIndicator;

// Keep track of last selected item
let lastSelectedItem = null; // Stores the DOM element of the last clicked item

// Number of items per group for lists
const ITEMS_PER_GROUP = 100;

// Simulation control variables
let simEventsInput, runSimButton, stopSimButton, simOptionsButton, simConsole,
    simStatusDisplay, simOptionsModal, saveSimOptionsButton, simThreadsInput, simSeed1Input, simSeed2Input,
    simSaveHitsCheckbox, simSaveParticlesCheckbox, simSaveTracksRangeInput, simPrintProgressInput,
    drawTracksCheckbox, drawTracksRangeInput,
    simPhysicsListSelect, simOpticalPhysicsCheckbox;

// Analysis control variables
let energyBinsInput, spatialBinsInput, refreshAnalysisButton, analysisStatusDisplay;

// Reconstruction
let reconModal, closeReconModalBtn, cancelReconBtn, runReconstructionBtn,
    reconImageView, reconViewerPanel, sliceSlider, sliceIndicator, reconAxisSelect, reconModalButton,
    processLorsBtn, reconStatusP, coincidenceWindowInput, energyCutInput, energyResolutionInput, posResXInput, posResYInput, posResZInput,
    reconNormalizationCheckbox,
    acEnabledCheckbox, acParamsDiv, numRandomLorsInput, generateSensitivityBtn, sensStatusDisplay,
    acRadiusInput, acLengthInput, acMuInput;


// Callbacks to main.js (controller logic)
let callbacks = {

    onOpenGdmlClicked: (file) => { },
    onOpenProjectClicked: (file) => { },
    onImportGdmlClicked: (file) => { },
    onImportProjectClicked: (file) => { },
    onImportAiResponseClicked: (file) => { },
    onImportStepClicked: (file) => { },
    onNewProjectClicked: () => { },
    onSaveProjectClicked: () => { },
    onExportGdmlClicked: () => { },
    onUndoClicked: () => { },
    onRedoClicked: () => { },
    onHistoryButtonClicked: () => { },
    onProjectRenamed: (newName) => { },
    onLoadVersionClicked: () => { },
    onEditSolidClicked: (solidData) => { },
    onAddDefineClicked: () => { },
    onEditDefineClicked: (defineData) => { },
    onAddMaterialClicked: () => { },
    onEditMaterialClicked: (d) => { },
    onAddElementClicked: () => { },
    onEditElementClicked: (d) => { },
    onAddOpticalSurfaceClicked: () => { },
    onEditOpticalSurfaceClicked: (surfaceData) => { },
    onAddSkinSurfaceClicked: () => { },
    onEditSkinSurfaceClicked: (surfaceData) => { },
    onAddLVClicked: () => { },
    onEditLVClicked: (lvData) => { },
    onAddObjectClicked: () => { }, // To show modal
    onAddRingArrayClicked: () => { },
    onConfirmAddObject: (type, name, params) => { },
    onDeleteSelectedClicked: () => { },
    onHierarchySelectionChanged: (selectedItems) => { },
    onModeChangeClicked: (mode) => { },
    onSnapToggleClicked: () => { },
    onSnapSettingsChanged: (transSnap, angleSnap) => { },
    onCameraModeChangeClicked: (mode) => { },
    onWireframeToggleClicked: () => { },
    onGridToggleClicked: () => { },
    onAxesToggleClicked: () => { },
    onInspectorPropertyChanged: (type, id, path, value) => { },
    onPVVisibilityToggle: (pvId, isVisible) => { },
    onAiGenerateClicked: (promptText) => { },
    onSetApiKeyClicked: () => { },
    onSaveApiKeyClicked: (apiKey) => { },
    onSourceActivationToggled: (sourceId) => { },
    onRefreshAnalysisClicked: (energyBins, spatialBins) => { },
    onDownloadSimDataClicked: () => { }
};

// --- Initialization ---
export function initUI(cb) {
    callbacks = { ...callbacks, ...cb }; // Merge provided callbacks

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
    addPVButton = document.getElementById('addPVButton');

    // Mode Buttons
    modeObserveButton = document.getElementById('modeObserveButton');
    modeTranslateButton = document.getElementById('modeTranslateButton');
    modeRotateButton = document.getElementById('modeRotateButton');
    //modeScaleButton = document.getElementById('modeScaleButton');
    currentModeDisplay = document.getElementById('currentModeDisplay');

    // View Menu Buttons
    toggleWireframeButton = document.getElementById('toggleWireframeButton');
    toggleGridButton = document.getElementById('toggleGridButton');
    toggleAxesButton = document.getElementById('toggleAxesButton');
    cameraModeOriginButton = document.getElementById('cameraModeOriginButton');
    cameraModeSelectedButton = document.getElementById('cameraModeSelectedButton');

    // Edit Menu / Snap Buttons
    toggleSnapToGridButton = document.getElementById('toggleSnapToGridButton');
    gridSnapSizeInput = document.getElementById('gridSnapSizeInput');
    angleSnapSizeInput = document.getElementById('angleSnapSizeInput');

    // History and undo/redo buttons
    projectNameDisplay = document.getElementById('projectNameDisplay');
    projectNameWrapper = document.getElementById('project-name-wrapper');
    projectListDropdown = document.getElementById('project-list-dropdown');
    historyButton = document.getElementById('historyButton');
    historyPanel = document.getElementById('history_panel');
    closeHistoryPanel = document.getElementById('closeHistoryPanel');
    historyListContainer = document.getElementById('history_list_container');
    undoButton = document.getElementById('undoButton');
    redoButton = document.getElementById('redoButton');

    // Create ring array
    createRingArrayButton = document.getElementById('createRingArrayButton');

    // Hierarchy and Inspector Roots
    structureTreeRoot = document.getElementById('structure_tree_root');
    assembliesListRoot = document.getElementById('assemblies_list_root');
    lvolumesListRoot = document.getElementById('lvolumes_list_root');
    definesListRoot = document.getElementById('defines_list_root');
    materialsListRoot = document.getElementById('materials_list_root');
    elementsListRoot = document.getElementById('elements_list_root');
    solidsListRoot = document.getElementById('solids_list_root');
    inspectorContentDiv = document.getElementById('inspector_content');


    // Bottom panel (AI and simulation)
    bottomPanel = document.getElementById('bottom_panel');
    toggleBottomPanelBtn = document.getElementById('toggleBottomPanelBtn');

    // AI Panel elements
    aiPromptInput = document.getElementById('ai_prompt_input');
    aiGenerateButton = document.getElementById('ai_generate_button');
    aiModelSelect = document.getElementById('ai_model_select');

    // API key modal elements
    apiKeyModal = document.getElementById('apiKeyModal');
    apiKeyInput = document.getElementById('apiKeyInput');
    saveApiKeyButton = document.getElementById('saveApiKey');
    cancelApiKeyButton = document.getElementById('cancelApiKey');

    // Loading overlay
    loadingOverlay = document.getElementById('loading-overlay');
    loadingMessage = document.getElementById('loading-message');

    // --- Initialize snap settings from UI values on startup ---
    const initialTransSnap = document.getElementById('gridSnapSizeInput').value;
    const initialAngleSnap = document.getElementById('angleSnapSizeInput').value;
    callbacks.onSnapSettingsChanged(initialTransSnap, initialAngleSnap);

    // Simulation control elements
    simThreadsInput = document.getElementById('simThreads');
    simEventsInput = document.getElementById('simEventsInput');
    runSimButton = document.getElementById('runSimButton');
    stopSimButton = document.getElementById('stopSimButton');
    simOptionsButton = document.getElementById('simOptionsButton');
    simConsole = document.getElementById('sim_console');
    simStatusDisplay = document.getElementById('sim_status_display');

    simOptionsModal = document.getElementById('simOptionsModal');
    saveSimOptionsButton = document.getElementById('saveSimOptions');
    simSeed1Input = document.getElementById('simSeed1');
    simSeed2Input = document.getElementById('simSeed2');
    simSaveHitsCheckbox = document.getElementById('simSaveHits');
    simSaveParticlesCheckbox = document.getElementById('simSaveParticles');
    simSaveTracksRangeInput = document.getElementById('simSaveTracksRange');
    drawTracksCheckbox = document.getElementById('drawTracksCheckbox');
    drawTracksRangeInput = document.getElementById('drawTracksRange');
    simPrintProgressInput = document.getElementById('simPrintProgress');
    simPhysicsListSelect = document.getElementById('simPhysicsList');
    simOpticalPhysicsCheckbox = document.getElementById('simOpticalPhysics');

    // Analysis elements
    energyBinsInput = document.getElementById('energyBinsInput');
    spatialBinsInput = document.getElementById('spatialBinsInput');
    refreshAnalysisButton = document.getElementById('refreshAnalysisButton');
    analysisStatusDisplay = document.getElementById('analysis_status');

    // Reconstruction elements
    reconModal = document.getElementById('reconModal');
    reconViewerPanel = document.getElementById('recon-viewer-panel');
    closeReconModalBtn = document.getElementById('closeReconModal');
    cancelReconBtn = document.getElementById('cancelRecon');
    runReconstructionBtn = document.getElementById('runReconstructionBtn');
    reconImageView = document.getElementById('reconImageView');
    sliceSlider = document.getElementById('sliceSlider');
    sliceIndicator = document.getElementById('sliceIndicator');
    reconAxisSelect = document.getElementById('reconAxis');
    reconModalButton = document.getElementById('reconModalButton');
    processLorsBtn = document.getElementById('processLorsBtn');
    reconStatusP = document.getElementById('lorStatus');
    coincidenceWindowInput = document.getElementById('coincidenceWindow');
    energyCutInput = document.getElementById('energyCut');
    energyResolutionInput = document.getElementById('energyResolution');
    posResXInput = document.getElementById('posResX');
    posResYInput = document.getElementById('posResY');
    posResZInput = document.getElementById('posResZ');
    reconNormalizationCheckbox = document.getElementById('reconNormalization');
    // AC controls
    acEnabledCheckbox = document.getElementById('acEnabled');
    acParamsDiv = document.getElementById('acParams');
    numRandomLorsInput = document.getElementById('numRandomLors');
    generateSensitivityBtn = document.getElementById('generateSensitivityBtn');
    sensStatusDisplay = document.getElementById('sensStatus');
    acRadiusInput = document.getElementById('acRadius');
    acLengthInput = document.getElementById('acLength');
    acMuInput = document.getElementById('acMu');

    // AC Toggle logic
    if (acEnabledCheckbox && acParamsDiv) {
        acEnabledCheckbox.addEventListener('change', () => {
            acParamsDiv.style.display = acEnabledCheckbox.checked ? 'block' : 'none';
        });
        // Init state
        acParamsDiv.style.display = acEnabledCheckbox.checked ? 'block' : 'none';
    }

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
    const downloadSimDataButton = document.getElementById('downloadSimDataButton');
    if (downloadSimDataButton) {
        downloadSimDataButton.addEventListener('click', callbacks.onDownloadSimDataClicked);
    }

    deleteSelectedObjectButton.addEventListener('click', callbacks.onDeleteSelectedClicked);

    modeObserveButton.addEventListener('click', () => { setActiveModeButton('observe'); callbacks.onModeChangeClicked('observe'); });
    modeTranslateButton.addEventListener('click', () => { setActiveModeButton('translate'); callbacks.onModeChangeClicked('translate'); });
    modeRotateButton.addEventListener('click', () => { setActiveModeButton('rotate'); callbacks.onModeChangeClicked('rotate'); });
    //modeScaleButton.addEventListener('click', () => { setActiveModeButton('scale'); callbacks.onModeChangeClicked('scale'); });

    toggleWireframeButton.addEventListener('click', callbacks.onWireframeToggleClicked);
    toggleGridButton.addEventListener('click', callbacks.onGridToggleClicked);
    toggleAxesButton.addEventListener('click', callbacks.onAxesToggleClicked);
    cameraModeOriginButton.addEventListener('click', () => {
        setActiveCameraModeButton('origin');
        callbacks.onCameraModeChangeClicked('origin');
    });
    cameraModeSelectedButton.addEventListener('click', () => {
        // We don't change the active button here, because it's a one-shot action.
        // The mode is still "Orbit", we are just changing its target.
        callbacks.onCameraModeChangeClicked('selected');
    });

    toggleSnapToGridButton.addEventListener('click', () => {
        const isNowEnabled = callbacks.onSnapToggleClicked(); // Callback should return new state
        toggleSnapToGridButton.textContent = `Snap to Grid: ${isNowEnabled ? 'ON' : 'OFF'}`;
    });
    gridSnapSizeInput.addEventListener('change', () => callbacks.onSnapSettingsChanged(gridSnapSizeInput.value, undefined));
    angleSnapSizeInput.addEventListener('change', () => callbacks.onSnapSettingsChanged(undefined, angleSnapSizeInput.value));

    // --- Active Source Checkbox Listener (Delegation) ---
    structureTreeRoot.addEventListener('change', (event) => {
        if (event.target.classList.contains('active-source-checkbox')) {
            const sourceId = event.target.value;
            callbacks.onSourceActivationToggled(sourceId);
        }
    });

    // Add listeners for add object buttons
    addButtons.forEach(button => {
        button.addEventListener('click', (event) => {
            const type = event.target.dataset.addType;
            if (type.startsWith('define')) {
                callbacks.onAddDefineClicked();
            } else if (type.startsWith('solid')) {
                callbacks.onAddSolidClicked();
            } else if (type.startsWith('material')) {
                callbacks.onAddMaterialClicked();
            } else if (type.startsWith('logical_volume')) {
                callbacks.onAddLVClicked();
            } else if (type.startsWith('assembly')) {
                callbacks.onAddAssemblyClicked();
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
            } else if (type.startsWith('particle_source')) {
                callbacks.onAddGpsClicked();
            } else {
                console.log("ERROR: module does not exist")
            }
        });
    });

    // Add listener for physical volume button
    addPVButton.addEventListener('click', callbacks.onAddPVClicked);
    addPVButton.disabled = false;

    // Create ring array button
    createRingArrayButton.addEventListener('click', () => callbacks.onAddRingArrayClicked());

    // Project history and undo/redo listeners
    historyButton.addEventListener('click', callbacks.onHistoryButtonClicked);
    closeHistoryPanel.addEventListener('click', hideHistoryPanel);
    undoButton.addEventListener('click', callbacks.onUndoClicked);
    redoButton.addEventListener('click', callbacks.onRedoClicked);
    projectNameDisplay.addEventListener('keydown', (event) => {
        // Check if the Enter key was pressed
        if (event.key === 'Enter') {
            event.preventDefault();    // This stops it from creating a new line
            projectNameDisplay.blur(); // Trigger the blur event, which saves the name
        }
    });
    projectNameDisplay.addEventListener('blur', () => {
        // Remove any potential HTML tags from pasting
        const cleanName = projectNameDisplay.textContent.trim();
        if (cleanName === "") {
            projectNameDisplay.textContent = "untitled"; // Revert if empty
        } else {
            projectNameDisplay.textContent = cleanName;
        }
        callbacks.onProjectRenamed(projectNameDisplay.textContent);
    });
    projectNameWrapper.addEventListener('click', async (event) => {
        // Stop propagation to prevent the global 'click-off' from closing it immediately
        event.stopPropagation();

        // If the dropdown is already visible, do nothing
        if (projectListDropdown.style.display === 'block') return;

        try {
            const result = await callbacks.onProjectListRequested();
            if (result.success) {
                populateProjectListDropdown(result.projects);
                projectListDropdown.style.display = 'block';
            }
        } catch (error) {
            console.error("Could not fetch project list:", error);
        }
    });

    // --- Add a global listener to close the dropdown ---
    document.addEventListener('click', () => {
        if (projectListDropdown.style.display === 'block') {
            projectListDropdown.style.display = 'none';
        }
    });

    // Listener for the bottom panel expand/collapse button
    toggleBottomPanelBtn.addEventListener('click', () => {
        if (bottomPanel.classList.contains('expanded')) {
            bottomPanel.classList.remove('expanded');
            bottomPanel.classList.add('minimized');
            toggleBottomPanelBtn.textContent = '↑';
            toggleBottomPanelBtn.title = 'Restore Panel';
        } else if (bottomPanel.classList.contains('minimized')) {
            bottomPanel.classList.remove('minimized');
            toggleBottomPanelBtn.textContent = '↑';
            toggleBottomPanelBtn.title = 'Expand Panel';
        } else {
            bottomPanel.classList.add('expanded');
            toggleBottomPanelBtn.textContent = '↓';
            toggleBottomPanelBtn.title = 'Minimize Panel';
        }
    });

    // AI Panel Listener (removed, handled by aiAssistant.js)
    /*
    aiGenerateButton.addEventListener('click', () => {
        const promptText = aiPromptInput.value.trim();
        if (promptText) {
            callbacks.onAiGenerateClicked(promptText);
        } else {
            showError("Please enter a prompt for the AI assistant.");
        }
    });
    */

    // API key modal listeners
    setApiKeyButton.addEventListener('click', callbacks.onSetApiKeyClicked);
    saveApiKeyButton.addEventListener('click', () => {
        callbacks.onSaveApiKeyClicked(apiKeyInput.value);
    });
    cancelApiKeyButton.addEventListener('click', hideApiKeyModal);

    // Add listeners for sim buttons
    runSimButton.addEventListener('click', () => {
        const numEvents = parseInt(simEventsInput.value, 10);
        if (numEvents > 0) {
            callbacks.onRunSimulationClicked({ events: numEvents });
        } else {
            showError("Please enter a valid number of events.");
        }
    });
    stopSimButton.addEventListener('click', callbacks.onStopSimulationClicked);
    simOptionsButton.addEventListener('click', callbacks.onSimOptionsClicked);
    saveSimOptionsButton.addEventListener('click', callbacks.onSaveSimOptions);
    drawTracksCheckbox.addEventListener('change', callbacks.onDrawTracksToggle);
    drawTracksRangeInput.addEventListener('change', callbacks.onDrawTracksToggle); // Also trigger on range change

    // Analysis listener
    if (refreshAnalysisButton) {
        refreshAnalysisButton.addEventListener('click', () => {
            const energyBins = parseInt(energyBinsInput.value, 10);
            const spatialBins = parseInt(spatialBinsInput.value, 10);
            callbacks.onRefreshAnalysisClicked(energyBins, spatialBins);
        });
    }

    // Reconstruction listeners
    reconModalButton.addEventListener('click', () => callbacks.onReconModalOpen());
    closeReconModalBtn.addEventListener('click', hideReconstructionModal);
    cancelReconBtn.addEventListener('click', hideReconstructionModal);
    runReconstructionBtn.addEventListener('click', () => {
        // Gather params from the UI and pass them to the main controller
        const params = {
            algorithm: document.getElementById('reconAlgorithm').value,
            iterations: parseInt(document.getElementById('reconIterations').value, 10),
            image_size: document.getElementById('reconImageSize').value.split(',').map(Number),
            voxel_size: document.getElementById('reconVoxelSize').value.split(',').map(Number),
            normalization: document.getElementById('reconNormalization').checked,
            // Add AC params
            ac_enabled: document.getElementById('acEnabled').checked,
            ac_shape: 'cylinder',
            ac_radius: parseFloat(document.getElementById('acRadius').value),
            ac_length: parseFloat(document.getElementById('acLength').value),
            ac_mu: parseFloat(document.getElementById('acMu').value)
        };
        callbacks.onRunReconstruction(params);
    });
    processLorsBtn.addEventListener('click', () => {
        const params = {
            coincidence_window_ns: parseFloat(coincidenceWindowInput.value),
            energy_cut: parseFloat(energyCutInput.value),
            energy_resolution: parseFloat(energyResolutionInput.value),
            position_resolution: {
                x: parseFloat(posResXInput.value),
                y: parseFloat(posResYInput.value),
                z: parseFloat(posResZInput.value)
            }
        };
        callbacks.onProcessLorsClicked(params);
    });

    // Sensitivity Matrix
    if (generateSensitivityBtn) {
        generateSensitivityBtn.addEventListener('click', () => {
            // Disable button and change text to indicate work
            generateSensitivityBtn.disabled = true;
            generateSensitivityBtn.textContent = "Requesting...";
            const params = getSensitivityParams();
            callbacks.onGenerateSensitivityClicked(params);
        });
    }

    // Listener for the slider
    sliceSlider.addEventListener('input', () => {
        const axis = reconAxisSelect.value;
        callbacks.onSliceChanged(axis, sliceSlider.value);
    });
    // Also update when the axis changes
    reconAxisSelect.addEventListener('change', () => {
        const axis = reconAxisSelect.value;
        callbacks.onSliceAxisChanged(axis);
    });

    // --- Tab Navigation for LEFT SIDE PANEL ---
    const leftTabButtons = document.querySelectorAll('#left_panel_tabs .tab_button');
    const leftTabPanes = document.querySelectorAll('#left_panel_content .tab_pane');
    leftTabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const targetTabId = button.dataset.tab;
            // Activate button in the left panel only
            leftTabButtons.forEach(btn => btn.classList.toggle('active', btn === button));
            // Show content in the left panel only
            leftTabPanes.forEach(pane => {
                pane.classList.toggle('active', pane.id === targetTabId);
            });
        });
    });

    // --- Tab Navigation for BOTTOM PANEL ---
    const bottomTabButtons = document.querySelectorAll('#bottom_panel_tabs .tab_button');
    const bottomTabPanes = document.querySelectorAll('#bottom_panel_content .tab_pane');
    bottomTabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const targetTabId = button.dataset.tab;
            // Set active tab attribute for CSS styling
            bottomPanel.dataset.activeTab = targetTabId;
            // Activate button in the bottom panel only
            bottomTabButtons.forEach(btn => btn.classList.toggle('active', btn === button));
            // Show content in the bottom panel only
            bottomTabPanes.forEach(pane => {
                pane.classList.toggle('active', pane.id === targetTabId);
            });
        });
    });

    // Set initial active tab attribute
    bottomPanel.dataset.activeTab = 'tab_ai_panel';

    // Set default active tabs for both panels
    document.querySelector('#left_panel_tabs .tab_button[data-tab="tab_structure"]').classList.add('active');
    document.querySelector('#left_panel_content #tab_structure').classList.add('active');

    document.querySelector('#bottom_panel_tabs .tab_button[data-tab="tab_ai_panel"]').classList.add('active');
    document.querySelector('#bottom_panel_content #tab_ai_panel').classList.add('active');

    // Add listeners for the new "+ Group" buttons
    document.querySelectorAll('.add-group-btn').forEach(button => {
        button.addEventListener('click', (event) => {
            const type = event.target.dataset.groupType;
            const groupName = prompt(`Enter a name for the new ${type.replace('_', ' ')} group:`);
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

    // Autosave status indicator
    statusIndicator = document.createElement('div');
    statusIndicator.id = 'status-indicator';
    statusIndicator.style.position = 'absolute';
    statusIndicator.style.top = '10px';
    statusIndicator.style.right = '10px';
    statusIndicator.style.backgroundColor = 'rgba(0, 0, 0, 0.6)';
    statusIndicator.style.color = 'white';
    statusIndicator.style.padding = '5px 10px';
    statusIndicator.style.borderRadius = '5px';
    statusIndicator.style.zIndex = '2000';
    statusIndicator.style.opacity = '0';
    statusIndicator.style.transition = 'opacity 0.5s ease-in-out';
    document.getElementById('viewer_container').appendChild(statusIndicator);


    console.log("UIManager initialized.");
}

export function showTemporaryStatus(message, duration = 2000) {
    if (!statusIndicator) return;

    statusIndicator.textContent = message;
    statusIndicator.style.opacity = '1';

    setTimeout(() => {
        statusIndicator.style.opacity = '0';
    }, duration);
}

export function updateUndoRedoButtons(historyStatus) {
    if (!historyStatus) return;
    undoButton.disabled = !historyStatus.can_undo;
    redoButton.disabled = !historyStatus.can_redo;
}

export function showHistoryPanel() {
    historyPanel.style.display = 'flex';
}

export function hideHistoryPanel() {
    historyPanel.style.display = 'none';
}

export function populateHistoryPanel(history, projectName) {
    historyListContainer.innerHTML = '';
    if (history.length === 0) {
        historyListContainer.innerHTML = '<p>&nbsp;&nbsp;No saved versions.</p>';
        return;
    }

    history.forEach(version => {
        const versionItem = document.createElement('div');
        versionItem.className = 'accordion-item';

        // --- Add a special class for the autosave item ---
        if (version.is_autosave) {
            versionItem.classList.add('autosave-history-item');
        }

        const header = document.createElement('div');
        header.className = 'accordion-header';

        const descriptionText = version.is_autosave
            ? `🕒 ${version.description}` // Add an icon for autosave
            : version.description;
        header.innerHTML = `
            <span class="accordion-toggle">[+]</span>
            <div class="version-info">
                <span class="version-desc">&nbsp;&nbsp;${descriptionText}</span>
                <span class="version-ts">&nbsp;&nbsp;${formatTimestamp(version.timestamp)}</span>
            </div>
            <button class="load-version-btn" title="Load this project version">Load</button>
        `;

        const content = document.createElement('div');
        content.className = 'accordion-content';

        // --- Populate with simulation runs ---
        if (version.runs && version.runs.length > 0) {
            const runList = document.createElement('ul');
            version.runs.forEach(runId => {
                const runLi = document.createElement('li');
                runLi.className = 'run-item';
                runLi.textContent = `Run: ${runId.substring(0, 8)}...`;
                runLi.title = `Show tracks for this run (${runId})`;
                runLi.addEventListener('click', (e) => {
                    e.stopPropagation();
                    // Callback to main.js to load the geometry AND the tracks
                    callbacks.onLoadRunResults(version.id, runId);
                });
                runList.appendChild(runLi);
            });
            content.appendChild(runList);
        } else {
            content.innerHTML = '<p class="no-runs-text">(No simulation runs for this version)</p>';
        }

        versionItem.appendChild(header);
        versionItem.appendChild(content);
        historyListContainer.appendChild(versionItem);

        // --- Add Event Listeners ---
        header.addEventListener('click', () => {
            const isActive = content.classList.contains('active');
            // Close all other accordions
            historyListContainer.querySelectorAll('.accordion-content.active').forEach(ac => {
                ac.classList.remove('active');
                ac.previousElementSibling.querySelector('.accordion-toggle').textContent = '[+]  ';
            });
            // Toggle current one
            if (!isActive) {
                content.classList.add('active');
                header.querySelector('.accordion-toggle').textContent = '[-]  ';
            }
        });

        header.querySelector('.load-version-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            callbacks.onLoadVersionClicked(projectName, version.id);
        });
    });
}

function populateProjectListDropdown(projectNames) {
    projectListDropdown.innerHTML = ''; // Clear previous list

    if (projectNames.length === 0) {
        const noProjectsItem = document.createElement('div');
        noProjectsItem.textContent = "No other projects found.";
        noProjectsItem.style.padding = '10px';
        noProjectsItem.style.fontStyle = 'italic';
        noProjectsItem.style.color = '#888';
        projectListDropdown.appendChild(noProjectsItem);
        return;
    }

    projectNames.forEach(name => {
        const item = document.createElement('div');
        item.className = 'project-list-item';
        item.textContent = name;
        item.dataset.projectName = name; // Store the name in a data attribute

        item.addEventListener('click', (event) => {
            event.stopPropagation(); // Prevent the global click-off
            const selectedProject = event.target.dataset.projectName;
            callbacks.onSwitchProject(selectedProject);
            projectListDropdown.style.display = 'none'; // Hide dropdown after selection
        });

        projectListDropdown.appendChild(item);
    });
}

function formatTimestamp(ts) {
    // 2024-07-15T10-30-00 -> 2024-07-15 10:30:00
    return ts.replace('T', ' ').replace(/-/g, ':').replace(/(\d{4}):(\d{2}):(\d{2})/, '$1-$2-$3');
}

export function getProjectName() {
    return projectNameDisplay.textContent.trim();
}

export function setProjectName(name) {
    projectNameDisplay.textContent = name;
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

    // Set a warning for scale |values| != 1
    if (type === 'scale') {
        const warning = document.createElement('p');
        warning.style.fontSize = '11px';
        warning.style.color = '#AA0000';
        warning.style.margin = '5px 0 10px 0';
        warning.innerHTML = `<b>Note:</b> Only the sign of the numbers placed here are taken into account when rendering the object. Inputs with absolute value not equal to 1 may not give the same behavior as in Geant4.`;
        group.appendChild(warning); // Add the warning text to the scale group
    }

    const inputsContainer = document.createElement('div');
    inputsContainer.className = 'inline-inputs-container';
    group.appendChild(inputsContainer);

    populateDefineSelect(select, Object.keys(defines));

    // --- Set default values and determine if units are needed ---
    let displayValues = { x: '0', y: '0', z: '0' };
    //let wrapInUnit = false;
    if (type === 'scale') {
        displayValues = { x: '1', y: '1', z: '1' }; // Scale defaults to 1
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

    // Handle multi-selection case
    if (Array.isArray(itemContext)) {
        const title = document.createElement('h4');
        title.textContent = `${itemContext.length} items selected`;
        inspectorContentDiv.appendChild(title);
        // ... (optional: show common properties)
        return;
    }

    const { type, id, name, data } = itemContext;

    const title = document.createElement('h4');
    title.textContent = `${type}: ${name || id}`;
    inspectorContentDiv.appendChild(title);

    if (type === 'particle_source') {
        createReadOnlyProperty(inspectorContentDiv, "Source Type:", data.type.toUpperCase());

        const commands = data.gps_commands || {};
        for (const [key, value] of Object.entries(commands)) {
            createReadOnlyProperty(inspectorContentDiv, `/gps/${key}:`, value);
        }

    } else if (type === 'physical_volume') {
        const allDefines = projectState.defines || {};
        const posDefines = {};
        const rotDefines = {};
        const sclDefines = {};
        for (const defName in allDefines) {
            if (allDefines[defName].type === 'position') posDefines[defName] = allDefines[defName];
            if (allDefines[defName].type === 'rotation') rotDefines[defName] = allDefines[defName];
            if (allDefines[defName].type === 'scale') sclDefines[defName] = allDefines[defName];
        }

        // Check if the placed LV is procedural
        const lvData = projectState.logical_volumes[data.volume_ref];
        const isProcedural = lvData && lvData.content_type !== 'physvol';

        buildInspectorTransformEditor(inspectorContentDiv, 'position', 'Position (mm)', data, posDefines, projectState, { isDisabled: false });
        buildInspectorTransformEditor(inspectorContentDiv, 'rotation', 'Rotation (rad)', data, rotDefines, projectState, { isDisabled: false });
        // buildInspectorTransformEditor(inspectorContentDiv, 'scale', 'Scale', data, sclDefines, projectState, { isDisabled: isProcedural });

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
    if (modeObserveButton) modeObserveButton.classList.toggle('active_mode', mode === 'observe');
    if (modeTranslateButton) modeTranslateButton.classList.toggle('active_mode', mode === 'translate');
    if (modeRotateButton) modeRotateButton.classList.toggle('active_mode', mode === 'rotate');
    if (modeScaleButton) modeScaleButton.classList.toggle('active_mode', mode === 'scale');
    if (currentModeDisplay) currentModeDisplay.textContent = `${mode.charAt(0).toUpperCase() + mode.slice(1)}`;
}

export function setActiveCameraModeButton(mode) {
    // This function visually updates which "centering" mode is conceptually active.
    if (cameraModeOriginButton) cameraModeOriginButton.classList.toggle('active_mode', mode === 'origin');
}

export function triggerFileInput(inputId) {
    const inputElement = document.getElementById(inputId);
    if (inputElement) inputElement.click();
}

// --- Hierarchy Panel Management ---
export function updateHierarchy(projectState, sceneUpdate) {
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
    if (structureTreeRoot) structureTreeRoot.innerHTML = '';
    if (assembliesListRoot) assembliesListRoot.innerHTML = '';
    if (lvolumesListRoot) lvolumesListRoot.innerHTML = '';
    if (definesListRoot) definesListRoot.innerHTML = '';
    if (materialsListRoot) materialsListRoot.innerHTML = '';
    if (elementsListRoot) elementsListRoot.innerHTML = '';
    if (isotopesListRoot) isotopesListRoot.innerHTML = '';
    if (solidsListRoot) solidsListRoot.innerHTML = '';
    if (opticalSurfacesListRoot) opticalSurfacesListRoot.innerHTML = '';
    if (skinSurfacesListRoot) skinSurfacesListRoot.innerHTML = '';
    if (borderSurfacesListRoot) borderSurfacesListRoot.innerHTML = '';

    // --- Grouped Population ---
    populateListWithGrouping(assembliesListRoot, Object.values(projectState.assemblies || {}), 'assembly');
    populateListWithGrouping(lvolumesListRoot, Object.values(projectState.logical_volumes || {}), 'logical_volume');
    populateListWithGrouping(definesListRoot, Object.values(projectState.defines || {}), 'define');
    populateListWithGrouping(materialsListRoot, Object.values(projectState.materials || {}), 'material');
    populateListWithGrouping(elementsListRoot, Object.values(projectState.elements || {}), 'element');
    populateListWithGrouping(isotopesListRoot, Object.values(projectState.isotopes || {}), 'isotope');
    populateListWithGrouping(solidsListRoot, Object.values(projectState.solids || {}), 'solid');
    populateListWithGrouping(opticalSurfacesListRoot, Object.values(projectState.optical_surfaces || {}), 'optical_surface');
    populateListWithGrouping(skinSurfacesListRoot, Object.values(projectState.skin_surfaces || {}), 'skin_surface');
    populateListWithGrouping(borderSurfacesListRoot, Object.values(projectState.border_surfaces || {}), 'border_surface');

    // --- Build the physical placement tree (Structure tab) ---
    if (structureTreeRoot && sceneUpdate) {
        structureTreeRoot.innerHTML = '';

        // 1. Create a map of parentId -> [childData, childData, ...] from the scene description
        const sceneGraph = new Map();
        let worldPvId = null;

        // Separate geometry from sources
        const geometryItems = sceneUpdate.filter(item => !item.is_source);
        const sourceItems = sceneUpdate.filter(item => item.is_source);

        geometryItems.forEach(pvData => {
            if (!pvData.parent_id) {
                worldPvId = pvData.id; // This is the root PV of our scene
                sceneGraph.set(pvData.id, []);
            } else {
                if (!sceneGraph.has(pvData.parent_id)) {
                    sceneGraph.set(pvData.parent_id, []);
                }
                sceneGraph.get(pvData.parent_id).push(pvData);
            }
        });

        // 2. Find the World LV to display as the top-level item
        const worldLV = projectState.logical_volumes[projectState.world_volume_ref];
        if (worldLV && worldPvId) {
            const worldItem = createTreeItem(
                worldLV.name,
                'logical_volume',
                worldLV.name, // The ID for a logical volume is its name
                worldLV,
                { instanceId: worldPvId, hideDeleteButton: true, hideVisibilityButton: true } // Pass instanceId and a special flag
            );

            // 3. Start the recursive build from the world's direct children
            const childrenUl = document.createElement('ul');
            const worldChildren = sceneGraph.get(worldPvId) || [];
            worldChildren.forEach(childPvData => {
                const childNode = buildVolumeNodeRecursive(childPvData, projectState, sceneGraph);
                if (childNode) childrenUl.appendChild(childNode);
            });

            // --- Add sources to the world's children ---
            sourceItems.forEach(sourceData => {
                // The source data comes directly from the scene update
                const sourceNode = createTreeItem(
                    `${sourceData.name}`, // Add an icon
                    'particle_source',       // A new type for our hierarchy items
                    sourceData.id,           // Use the unique ID for selection
                    sourceData,
                    { instanceId: sourceData.id }
                );
                childrenUl.appendChild(sourceNode);
            });

            if (childrenUl.hasChildNodes()) {
                worldItem.appendChild(childrenUl);
            }
            structureTreeRoot.appendChild(worldItem);
        } else {
            structureTreeRoot.innerHTML = '<li>World volume data is missing or invalid.</li>';
        }
    }
}

/**
 * Recursive function to build the structure tree from the scene graph map.
 * @param {object} pvData - The scene description data for the current physical volume.
 * @param {object} projectState - The full project state for lookups.
 * @param {Map} sceneGraph - The pre-built map of parentId -> children.
 * @returns {HTMLLIElement | null}
 */
function buildVolumeNodeRecursive(pvData, projectState, sceneGraph) {
    const allLVs = projectState.logical_volumes || {};
    const allAssemblies = projectState.assemblies || {};

    const isAssemblyPlacement = allAssemblies[pvData.volume_ref];
    const childLVData = allLVs[pvData.volume_ref];

    let displayName = pvData.name || `pv_${pvData.id.substring(0, 4)}`;
    if (isAssemblyPlacement) {
        displayName = `⚙️ ` + displayName + ` (Assembly: ${pvData.volume_ref})`;
    } else if (childLVData) {
        displayName += ` (LV: ${pvData.volume_ref})`;
    } else {
        displayName += ` (Broken Ref: ${pvData.volume_ref})`;
    }

    const itemElement = createTreeItem(
        displayName,
        'physical_volume',
        pvData.canonical_id, // The ID for editing/deleting is the canonical ID
        pvData,              // The appData is the full pvDescription
        {
            instanceId: pvData.id,
            lvData: childLVData,
            hideDeleteButton: pvData.is_procedural_instance,
            hideVisibilityButton: false
        } // The unique ID for this specific instance in the scene
    );

    if (isAssemblyPlacement || childLVData) {
        const childrenOfThisNode = sceneGraph.get(pvData.id) || [];
        if (childrenOfThisNode.length > 0) {
            const childrenUl = document.createElement('ul');
            childrenOfThisNode.forEach(nestedPvData => {
                const nestedNode = buildVolumeNodeRecursive(nestedPvData, projectState, sceneGraph);
                if (nestedNode) childrenUl.appendChild(nestedNode);
            });
            if (childrenUl.hasChildNodes()) {
                addToggle(itemElement, childrenUl);
                itemElement.appendChild(childrenUl);
            }
        }
    }

    return itemElement;
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

    const { instanceId = null, lvData = null, hideDeleteButton = false, hideVisibilityButton = false } = additionalData;
    const item = document.createElement('li');

    // --- DRAG LOGIC ---
    // Define types that should be draggable in the Properties/Solids/Volumes tabs
    const draggableInLists = [
        'logical_volume', 'assembly', // Added for the Volumes tab
        'solid', 'define', 'material', 'element', 'isotope',
        'optical_surface', 'skin_surface', 'border_surface'
    ];

    // Only make the item draggable if its type is in our list.
    // This automatically excludes 'physical_volume' from the Structure tab.
    if (draggableInLists.includes(itemType)) {
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
                    if (el.dataset.type === itemType) el.classList.add('dragging');
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

    // Conditionally create the buttons based on the flags
    const controlsHTML = `
        <div class="item-controls">
            ${(itemType === 'physical_volume' && !hideVisibilityButton) ? '<button class="visibility-btn" title="Toggle Visibility">👁️</button>' : ''}
            ${!hideDeleteButton ? '<button class="delete-item-btn" title="Delete Item">×</button>' : ''}
        </div>
    `;

    let finalDisplayName = displayName; // Start with the passed name
    let leadingContent = ''; // Content before the name

    // Add an icon for procedural volumes in the main hierarchy view
    if (itemType === 'logical_volume' && fullItemData.content_type && fullItemData.content_type !== 'physvol') {
        const icon = `<span class="procedural-icon" title="Type: ${fullItemData.content_type}">⚙️</span>`;
        finalDisplayName = icon + ' ' + displayName;
    }

    // --- SOURCE CHECKBOX ---
    if (itemType === 'particle_source') {
        finalDisplayName = `&nbsp;&nbsp;${displayName}&nbsp;&nbsp;⚛️`;
        const activeSourceIds = callbacks.getActiveSourceIds?.() || [];
        const isChecked = activeSourceIds.includes(itemIdForBackend) ? 'checked' : '';
        // Create a checkbox. 
        leadingContent = `<input type="checkbox" class="active-source-checkbox" value="${itemIdForBackend}" ${isChecked} title="Toggle active status for this source">`;
    }

    item.innerHTML = `
        <div class="tree-item-content">
            ${leadingContent}
            <span class="item-name">${finalDisplayName}</span>
            ${controlsHTML}
        </div>
    `;
    item.dataset.type = itemType;
    item.dataset.id = itemIdForBackend;  // note: this will be an "ID" for physical volumes and a name for everything else
    if (instanceId) {  // UNIQUE ID for scene interaction
        item.dataset.instanceId = instanceId;
    }
    else {
        item.dataset.instanceId = itemIdForBackend;
    }
    item.dataset.name = displayName;
    item.appData = { ...fullItemData, ...lvData };

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
                    canonical_id: sel.dataset.id,
                    id: sel.dataset.instanceId,
                    name: sel.dataset.name,
                    selData: sel.appData
                });
            }
        });
        callbacks.onHierarchySelectionChanged(selectedItemContexts);
    });

    // --- Context Menu (Right-Click & Ctrl+Click) Handler ---
    item.addEventListener('contextmenu', (event) => {

        // Stop the event immediately to prevent it bubbling to parent items' context handlers.
        event.stopPropagation();

        // Prevent the default browser right-click menu from appearing.
        event.preventDefault();

        // We want Ctrl+Click to behave EXACTLY like a normal click with the Ctrl key held.
        //    So, we can simply dispatch a new 'click' event on the same element,
        //    making sure to pass along the modifier key states.

        // This is a more robust way than duplicating the selection logic.
        const clickEvent = new MouseEvent('click', {
            bubbles: true,
            cancelable: true,
            view: window,
            ctrlKey: true, // We know Ctrl was held for this to fire
            metaKey: event.metaKey, // Pass along metaKey state
            shiftKey: event.shiftKey // Pass along shiftKey state
        });

        // Dispatch the synthetic click event on the item.
        item.dispatchEvent(clickEvent);
    });

    // Listener for the new delete button
    const deleteBtn = item.querySelector('.delete-item-btn');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', (event) => {
            event.stopPropagation(); // Prevent the item from being selected
            // We manually call the main delete handler after confirming
            if (confirmAction(`Are you sure you want to delete ${itemType}: ${displayName}?`)) {
                // We need to tell main.js *what* to delete
                callbacks.onDeleteSpecificItemClicked(itemType, itemIdForBackend, displayName);
            }
        });
    }

    // Hierarchy interaction logic for physical volumes.
    if (itemType === 'physical_volume') {

        // Add visibility button
        const visBtn = item.querySelector('.visibility-btn');
        if (visBtn) {

            const idForVisibility = instanceId || itemIdForBackend; // Use instanceId if available
            const isHidden = SceneManager.isPvHidden(itemIdForBackend);
            item.classList.toggle('item-hidden', isHidden);
            //visBtn.style.opacity = isHidden ? '0.4' : '1.0';

            visBtn.addEventListener('click', (event) => {
                event.stopPropagation();

                // Toggle the current state.
                const wasHidden = item.classList.contains('item-hidden');
                const isNowVisible = wasHidden; // If it was hidden, it is now visible.

                // Call the main handler from main.js (handles object and GUI visibility).
                // The third argument (isRecursive) is false by default if not provided.
                // If the user holds Alt, we can do a recursive toggle.
                const isRecursiveToggle = event.altKey;
                callbacks.onPVVisibilityToggle(idForVisibility, isNowVisible, isRecursiveToggle);
            });
        }

        // Add double-click listener if we have a physvol we can delete
        if (!hideDeleteButton) {
            item.addEventListener('dblclick', (event) => {
                event.stopPropagation();
                callbacks.onEditPVClicked(item.dataset, item.appData);
            });
        }
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
    } else if (itemType === 'assembly') {
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            callbacks.onEditAssemblyClicked(item.appData);
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
    } else if (itemType === 'particle_source') {
        item.addEventListener('dblclick', (event) => {
            event.stopPropagation();
            // We need a callback to main.js to show the editor
            callbacks.onEditGpsClicked(fullItemData);
        });
    }

    // Add a specific listener for the particle source radio button, if we added one
    const radio = item.querySelector('.active-source-radio');
    if (radio) {
        radio.addEventListener('click', (event) => {
            event.stopPropagation(); // Don't trigger the item selection click
            callbacks.onSourceActivationChanged(event.target.value);
        });
    }

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
        const shouldBeSelected = selectedIds.includes(item.dataset.instanceId);
        item.classList.toggle('selected_item', shouldBeSelected);

        // Scroll the last selected item into view
        if (shouldBeSelected && item.dataset.instanceId === selectedIds[selectedIds.length - 1]) {
            item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    });
}

// Helper to find the parent LV element in the DOM tree
function findParentLV(pvElement) {
    let current = pvElement.parentElement;
    while (current) {
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
        if (li.dataset.instanceId) {
            ids.push(li.dataset.instanceId);
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

export function clearHierarchySelection() {
    const selected = document.querySelector('#left_panel_container .selected_item');
    if (selected) selected.classList.remove('selected_item');
}

export function clearHierarchy() {
    if (structureTreeRoot) structureTreeRoot.innerHTML = '';
    if (assembliesListRoot) assembliesListRoot.innerHTML = '';
    if (lvolumesListRoot) lvolumesListRoot.innerHTML = '';
    if (definesListRoot) definesListRoot.innerHTML = '';
    if (materialsListRoot) materialsListRoot.innerHTML = '';
    if (elementsListRoot) elementsListRoot.innerHTML = '';
    if (isotopesListRoot) isotopesListRoot.innerHTML = '';
    if (solidsListRoot) solidsListRoot.innerHTML = '';
    if (opticalSurfacesListRoot) opticalSurfacesListRoot.innerHTML = '';
    if (skinSurfacesListRoot) skinSurfacesListRoot.innerHTML = '';
    if (borderSurfacesListRoot) borderSurfacesListRoot.innerHTML = '';
}

export function clearInspector() {
    if (inspectorContentDiv) inspectorContentDiv.innerHTML = '<p>Select an item.</p>';
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

// --- Utility/Notification Functions ---
export function showError(message) {
    console.error("[UI Error] " + message);
    alert("Error: " + message);
}
export function showDependencyError(message) {
    console.warn("[UI Dependency Error] " + message);
    // Replace the "- " with a newline and proper indentation for readability in an alert box.
    const formattedMessage = message.replace(/:\n - /g, ':\n\n • ').replace(/\n - /g, '\n • ');
    alert(formattedMessage);
}
export function showNotification(message) {
    console.log("[UI Notification] " + message);
    alert(message);
}
export function showLoading(message = "Loading...") {
    console.log("[UI Loading] " + message);
    loadingMessage.textContent = message;
    loadingOverlay.style.display = 'flex';
}

export function hideLoading() {
    console.log("[UI Loading] Complete.");
    loadingOverlay.style.display = 'none';
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

    // Use querySelectorAll to find ALL items that match the pvId.
    // This correctly handles cases where an assembly is placed multiple times.
    const items = document.querySelectorAll(`#structure_tree_root li[data-instance-id="${pvId}"]`);

    if (items.length > 0) {
        items.forEach(item => {
            // The CSS handles styling the inner content based on this class on the <li>
            item.classList.toggle('item-hidden', !isVisible);
        });
    }
}
export function setAllTreeItemVisibility(isVisible) {
    document.querySelectorAll('#tab_structure li[data-type="physical_volume"]').forEach(item => {
        item.classList.toggle('item-hidden', !isVisible);
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
    } else {
        // --- Set Default Model Preference ---
        // Prioritize user request, then gemini-3-flash-preview, then gemini-2.5-pro, then gemini-2.5-flash
        const preferredModels = ['gemini-3-flash-preview', 'gemini-2.5-pro', 'gemini-2.5-flash'];
        let matched = false;

        for (const pref of preferredModels) {
            // Check if any option value contains the preferred model name
            const options = Array.from(aiModelSelect.options);
            const found = options.find(opt => opt.value.includes(pref));
            if (found) {
                aiModelSelect.value = found.value;
                matched = true;
                break;
            }
        }
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

export function setApiKeyInputPlaceholder(text) {
    if (apiKeyInput) apiKeyInput.placeholder = text;
}

// --- Functions for simulation ---
export function setSimulationState(state) {
    // state can be 'idle', 'running'
    const isRunning = state === 'running';
    runSimButton.disabled = isRunning;
    stopSimButton.disabled = !isRunning;
    simEventsInput.disabled = isRunning;
    simOptionsButton.disabled = isRunning;
}

export function clearSimConsole() {
    if (simConsole) simConsole.textContent = '';
}

export function appendToSimConsole(text) {
    if (simConsole) {
        simConsole.textContent += text + '\n';
        // Auto-scroll to the bottom
        simConsole.parentElement.scrollTop = simConsole.parentElement.scrollHeight;
    }
}

export function showReconstructionModal() {
    if (reconModal) reconModal.style.display = 'block';
}

export function hideReconstructionModal() {
    if (reconModal) reconModal.style.display = 'none';
}

export function setReconModalButtonEnabled(isEnabled) {
    if (reconModalButton) reconModalButton.disabled = !isEnabled;
}

export function updateReconstructionSlice(imageUrl, sliceNum, maxSlices) {
    if (reconImageView) reconImageView.src = imageUrl;
    if (sliceIndicator) sliceIndicator.textContent = `${sliceNum} / ${maxSlices - 1}`;
}

export function setupSliceSlider(axis, imageShape) {
    let maxSlices = 0;
    if (axis === 'x') maxSlices = imageShape[0];
    else if (axis === 'y') maxSlices = imageShape[1];
    else maxSlices = imageShape[2];

    if (sliceSlider) {
        sliceSlider.max = maxSlices - 1;
        const middleSlice = Math.floor((maxSlices - 1) / 2);
        sliceSlider.value = middleSlice;
        // Trigger the input event to load the middle slice
        sliceSlider.dispatchEvent(new Event('input'));
    }
}

export function showSimOptionsModal() {
    if (simOptionsModal) simOptionsModal.style.display = 'block';
}

export function hideSimOptionsModal() {
    if (simOptionsModal) simOptionsModal.style.display = 'none';
}

export function setSimOptions(options) {
    if (!options) return;
    simThreadsInput.value = options.threads || 4;
    simSeed1Input.value = options.seed1 || 0;
    simSeed2Input.value = options.seed2 || 0;
    simSaveHitsCheckbox.checked = options.save_hits || false;
    simSaveParticlesCheckbox.checked = options.save_particles || false;
    simSaveTracksRangeInput.value = options.save_tracks_range || '';
    simPrintProgressInput.value = options.print_progress || 1000;
}

export function getSimOptions() {
    return {
        threads: parseInt(simThreadsInput.value || 1, 10),
        seed1: parseInt(simSeed1Input.value, 10),
        seed2: parseInt(simSeed2Input.value, 10),
        print_progress: parseInt(simPrintProgressInput.value, 10),
        save_hits: simSaveHitsCheckbox.checked,
        save_particles: simSaveParticlesCheckbox.checked,
        save_tracks_range: simSaveTracksRangeInput.value,
        physics_list: simPhysicsListSelect ? simPhysicsListSelect.value : 'FTFP_BERT',
        optical_physics: simOpticalPhysicsCheckbox ? simOpticalPhysicsCheckbox.checked : false
    };
}

export function getDrawTracksOptions() {
    return {
        draw: drawTracksCheckbox.checked,
        range: drawTracksRangeInput.value
    };
}

export function setReconstructionButtonEnabled(isEnabled) {
    if (runReconstructionBtn) runReconstructionBtn.disabled = !isEnabled;
}

export function setLorStatus(message, isError = false) {
    if (reconStatusP) {
        reconStatusP.textContent = `Status: ${message}`;
        reconStatusP.style.color = isError ? '#c53030' : '#2f855a'; // Red for error, green for success
    }
}

export function updateSimStatusDisplay(jobId, totalEvents) {
    if (simStatusDisplay) {
        if (jobId && totalEvents) {
            simStatusDisplay.innerHTML = `
                <span>Loaded Run: <strong>${jobId.substring(0, 8)}...</strong></span>
                <span style="margin-left: 10px;">Events: <strong>${totalEvents}</strong></span>
            `;
        } else {
            simStatusDisplay.innerHTML = '<span>No simulation run loaded.</span>';
        }
    }
}

export function clearSimStatusDisplay() {
    if (simStatusDisplay) {
        simStatusDisplay.innerHTML = '<span>No simulation run loaded.</span>';
    }
}

/**
 * Sets the aspect ratio of the reconstruction image viewer panel.
 * @param {number} ratio - The desired width / height ratio.
 */
export function setReconViewerAspectRatio(ratio) {
    if (reconViewerPanel) {
        reconViewerPanel.style.aspectRatio = ratio;
    }
}

// --- Sensitivity Logic ---
export function setSensitivityStatus(exists, info, isError = false) {
    if (!sensStatusDisplay) return;

    if (isError) {
        sensStatusDisplay.textContent = `Status: Error checking sensitivity matrix.`;
        sensStatusDisplay.style.color = '#c53030';
        // Allow retry
        if (generateSensitivityBtn) generateSensitivityBtn.disabled = false;
        return;
    }

    if (exists) {
        let msg = "Status: Sensitivity Matrix Available";
        if (info) {
            msg += ` (R=${Math.round(info.scanner_radius)}mm)`;
            if (info.ac_enabled) msg += ", AC: Yes";
            else msg += ", AC: No";
        }
        sensStatusDisplay.textContent = msg;
        sensStatusDisplay.style.color = '#2f855a'; // Green
        if (generateSensitivityBtn) generateSensitivityBtn.disabled = false;
        // We could disable it if we don't want re-generation, but user might want to update params.
        generateSensitivityBtn.textContent = "Re-generate Sensitivity Matrix";
    } else {
        sensStatusDisplay.textContent = "Status: No sensitivity matrix generated.";
        sensStatusDisplay.style.color = '#dc3545'; // Red
        if (generateSensitivityBtn) generateSensitivityBtn.disabled = false;
        generateSensitivityBtn.textContent = "Generate Sensitivity Matrix";
    }
}

export function setupSensitivityButton(callback) {
    if (generateSensitivityBtn) {
        generateSensitivityBtn.addEventListener('click', () => {
            // Disable button while running
            generateSensitivityBtn.disabled = true;
            generateSensitivityBtn.textContent = "Generating... (this may take a minute)";
            callback();
        });
    }
}

export function getSensitivityParams() {
    return {
        num_random_lors: parseInt(numRandomLorsInput ? numRandomLorsInput.value : 20000000),
        // We also need reuse of AC params, which are already used for recon
        ac_enabled: document.getElementById('acEnabled').checked,
        ac_radius: parseFloat(document.getElementById('acRadius').value),
        ac_mu: parseFloat(document.getElementById('acMu').value),
        // Grid params
        voxel_size: parseFloat(document.getElementById('reconVoxelSize').value.split(',')[0]), // assuming isotropic for simplicity in UI, but backend handles tuple
        matrix_size: parseInt(document.getElementById('reconImageSize').value.split(',')[0]) // assuming isotropic
    };
}
// --- Analysis Visualization ---

/**
 * Updates the analysis charts with the provided data.
 * @param {Object} data - The analysis data object from the backend.
 */
export function updateAnalysisCharts(data) {
    if (!data || !data.success) return;
    const analysis = data.analysis;

    // 1. Energy Spectrum
    const spectrum = analysis.energy_spectrum;
    if (spectrum && spectrum.counts.length > 0) {
        const binCenters = spectrum.bin_edges.slice(0, -1).map((edge, i) => (edge + spectrum.bin_edges[i+1]) / 2);
        const trace = {
            x: binCenters,
            y: spectrum.counts,
            type: 'bar',
            marker: { color: 'rgb(55, 83, 109)' }
        };
        const layout = {
            title: 'Energy Deposition Spectrum',
            xaxis: { title: 'Energy (MeV)' },
            yaxis: { title: 'Hits' },
            margin: { t: 40, b: 40, l: 50, r: 10 }
        };
        Plotly.newPlot('energy_spectrum_chart', [trace], layout);
    }

    // 2. Particle Breakdown
    const breakdown = analysis.particle_breakdown;
    if (breakdown && breakdown.names.length > 0) {
        const trace = {
            labels: breakdown.names,
            values: breakdown.counts,
            type: 'pie',
            textinfo: 'label+percent',
            hole: 0.4
        };
        const layout = {
            title: 'Particle Species Breakdown',
            margin: { t: 40, b: 10, l: 10, r: 10 }
        };
        Plotly.newPlot('particle_breakdown_chart', [trace], layout);
    }

    // 3. Heatmaps
    const renderHeatmap = (divId, title, heatmapData) => {
        if (!heatmapData || heatmapData.z.length === 0) return;
        const trace = {
            z: heatmapData.z,
            x: heatmapData.x_edges,
            y: heatmapData.y_edges,
            type: 'heatmap',
            colorscale: 'Viridis'
        };
        const layout = {
            title: title,
            xaxis: { title: 'mm' },
            yaxis: { title: 'mm' },
            margin: { t: 40, b: 40, l: 50, r: 10 }
        };
        Plotly.newPlot(divId, [trace], layout);
    };

    renderHeatmap('xy_heatmap_chart', 'Hit Distribution (XY)', analysis.heatmaps.xy);
    renderHeatmap('xz_heatmap_chart', 'Hit Distribution (XZ)', analysis.heatmaps.xz);
    renderHeatmap('yz_heatmap_chart', 'Hit Distribution (YZ)', analysis.heatmaps.yz);
    
    setAnalysisStatus(`Loaded analysis for ${analysis.total_hits} hits.`);
}

export function setAnalysisStatus(message) {
    if (analysisStatusDisplay) {
        analysisStatusDisplay.textContent = message;
    }
}

export function clearAnalysisCharts() {
    ['energy_spectrum_chart', 'particle_breakdown_chart', 'xy_heatmap_chart', 'xz_heatmap_chart', 'yz_heatmap_chart'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '';
    });
    setAnalysisStatus('No analysis data loaded.');
}

export function setDownloadButtonEnabled(isEnabled) {
    const btn = document.getElementById('downloadSimDataButton');
    if (btn) btn.disabled = !isEnabled;
}
