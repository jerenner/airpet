// static/uiManager.js
import * as THREE from 'three';
import * as SceneManager from './sceneManager.js';
import * as ExpressionInput from './expressionInput.js';
import {
    normalizeAiBackendDiagnostics,
    getLocalBackendIdForModel,
    getReadinessLabel,
    buildLocalBackendTooltip,
    formatLocalModelOptionLabel,
    buildBackendStatusChip,
    applyBackendStatusChip,
} from './backendDiagnosticsUi.js';
import {
    getReplicaInspectorEditableFieldSpecs,
    buildReplicaInspectorPropertyUpdateArgs,
} from './replicaInspectorBindings.js';
import {
    getDivisionInspectorEditableFieldSpecs,
    buildDivisionInspectorPropertyUpdateArgs,
} from './divisionInspectorBindings.js';
import {
    buildScopedIssueFamilyBucketSummary,
    buildScopedIssueCodeChips,
    buildScopedIssueFilterContextCopyText,
    buildScopedIssueExcerptCopyText,
    buildScopedIssueExcerptCopyJson,
    filterScopedIssuesByBucket,
    getScopedIssueBucketDisplayLabel,
} from './preflightScopedDiagnosticsUi.js';
import {
    GLOBAL_UNIFORM_MAGNETIC_FIELD_OBJECT_ID,
    GLOBAL_UNIFORM_MAGNETIC_FIELD_OBJECT_TYPE,
    GLOBAL_UNIFORM_MAGNETIC_FIELD_VECTOR_AXES,
    GLOBAL_UNIFORM_ELECTRIC_FIELD_OBJECT_ID,
    GLOBAL_UNIFORM_ELECTRIC_FIELD_OBJECT_TYPE,
    GLOBAL_UNIFORM_ELECTRIC_FIELD_VECTOR_AXES,
    LOCAL_UNIFORM_MAGNETIC_FIELD_OBJECT_ID,
    LOCAL_UNIFORM_MAGNETIC_FIELD_OBJECT_TYPE,
    LOCAL_UNIFORM_MAGNETIC_FIELD_VECTOR_AXES,
    LOCAL_UNIFORM_ELECTRIC_FIELD_OBJECT_ID,
    LOCAL_UNIFORM_ELECTRIC_FIELD_OBJECT_TYPE,
    LOCAL_UNIFORM_ELECTRIC_FIELD_VECTOR_AXES,
    REGION_CUTS_AND_LIMITS_OBJECT_ID,
    REGION_CUTS_AND_LIMITS_OBJECT_TYPE,
    formatGlobalMagneticFieldSummary,
    formatGlobalElectricFieldSummary,
    formatLocalMagneticFieldSummary,
    formatLocalElectricFieldSummary,
    formatRegionCutsAndLimitsSummary,
    normalizeLocalMagneticFieldState,
    normalizeLocalElectricFieldState,
    normalizeGlobalMagneticFieldState,
    normalizeGlobalElectricFieldState,
    normalizeRegionCutsAndLimitsState,
    normalizeTargetVolumeNames,
} from './environmentFieldUi.js';
import { buildCadImportBatchContext, buildCadImportSelectionContext, describeCadImportRecord } from './cadImportUi.js';
import {
    describeDetectorFeatureGeneratorLaunchState,
    describeDetectorFeatureGeneratorPanelState,
    describeDetectorFeatureGenerator,
    buildDetectorFeatureGeneratorSelectionContext,
} from './detectorFeatureGeneratorsUi.js';
import {
    buildScoringStateWithUpdatedRunManifestDefaults,
    buildScoringResultSummary,
    SCORING_OBJECT_ID,
    SCORING_OBJECT_TYPE,
    SUPPORTED_SCORING_TALLY_QUANTITIES,
    RUNTIME_READY_SCORING_QUANTITIES,
    buildScoringStateWithAddedMesh,
    compareScoringResultSummaries,
    buildScoringStateWithRemovedMesh,
    describeScoringMesh,
    describeScoringPanelState,
    describeScoringRunControls,
    describeScoringResultComparison,
    describeScoringResultSummary,
    formatScoringQuantityLabel,
    isMeshTallyEnabled,
    normalizeScoringState,
    replaceScoringMesh,
    setMeshTallyEnabled,
} from './scoringUi.js';

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
    bottomPanel, bottomPanelResizeHandle, toggleBottomPanelBtn,
    aiPromptInput, aiGenerateButton, aiModelSelect, aiBackendStatusEl,
    setApiKeyButton, apiKeyModal, apiKeyInput, saveApiKeyButton, cancelApiKeyButton,
    currentModeDisplay;

// Hierarchy and Inspector
let structureTreeRoot, assembliesListRoot, lvolumesListRoot, definesListRoot, materialsListRoot,
    elementsListRoot, isotopesListRoot, solidsListRoot, opticalSurfacesListRoot, skinSurfacesListRoot,
    borderSurfacesListRoot;
let inspectorContentDiv, environmentPanelRoot, cadImportsPanelRoot, detectorFeatureGeneratorsPanelRoot, scoringPanelRoot;
let loadedScoringResultSummary = null;
let previousLoadedScoringResultSummary = null;

function setCadImportsAccordionVisibility(hasCadImports) {
    if (!cadImportsPanelRoot) return;
    const accordionItem = cadImportsPanelRoot.closest('.accordion-item');
    if (!accordionItem) return;

    accordionItem.hidden = !hasCadImports;

    if (!hasCadImports) {
        const content = accordionItem.querySelector('.accordion-content');
        const toggle = accordionItem.querySelector('.accordion-toggle');
        if (content) content.classList.remove('active');
        if (toggle) toggle.textContent = '[+]';
    }
}

// Project, history and undo/redo
let projectNameDisplay, historyButton, historyPanel, closeHistoryPanel, historyListContainer,
    historySelectModeButton, historySelectionBar, historySelectionSummary,
    historyDeleteSelectedButton, historyCancelSelectionButton,
    undoButton, redoButton, projectNameWrapper, projectListDropdown;

// Button for adding PVs
let addPVButton;

// Button for creating ring arrays
let createRingArrayButton;
let createDetectorFeatureGeneratorButton;

// Loading overlay
let loadingOverlay, loadingMessage;

// Status indicator for autosave
let statusIndicator;

// Keep track of last selected item
let lastSelectedItem = null; // Stores the DOM element of the last clicked item

// AI backend readiness diagnostics cache (keyed by backend id)
let aiBackendDiagnosticsById = {};

let historySelectionMode = false;
let historySelectedVersionIds = new Set();
let historySelectedRunKeys = new Set();
let historyExpandedVersionIds = new Set();
let historyLastEntries = [];
let historyLastProjectName = '';
let bottomPanelLastExpandedHeight = 260;
let bottomPanelResizeRefreshHandle = null;
const BOTTOM_PANEL_MIN_EXPANDED_HEIGHT = 120;
const BOTTOM_PANEL_COLLAPSE_THRESHOLD = 70;

// Number of items per group for lists
const ITEMS_PER_GROUP = 100;

// Simulation control variables
let simEventsInput, runSimButton, stopSimButton, preflightButton, simOptionsButton, simConsole,
    simStatusDisplay, simOptionsModal, saveSimOptionsButton, simThreadsInput, simSeed1Input, simSeed2Input,
    simSaveHitsCheckbox, simSaveHitMetadataCheckbox, simHitEnergyThresholdInput, simProductionCutInput, simSaveParticlesCheckbox, simSaveTracksRangeInput, simPrintProgressInput,
    drawTracksCheckbox, drawTracksRangeInput,
    simPhysicsListSelect, simOpticalPhysicsCheckbox,
    preflightPanel, preflightSummaryLine, preflightScopeLine, preflightDeltaLine, preflightScopeHintLine,
    preflightScopeBucketsLine, preflightScopeBucketFilterRow,
    preflightBucketAllBtn, preflightBucketScopeOnlyBtn, preflightBucketOutsideOnlyBtn, preflightBucketSharedBtn,
    preflightIssueCodeChipRow,
    preflightScopeContextRow, preflightCopyScopeContextBtn, preflightCopyScopeIssueExcerptBtn, preflightCopyScopeIssueExcerptJsonBtn, preflightScopeContextStatus,
    preflightIssueToggleRow, preflightShowScopeIssuesBtn, preflightShowGlobalIssuesBtn,
    preflightIssuesLabel, preflightIssuesList;

// Sticky preflight panel view state for scoped/global issue toggling
let preflightLastRenderState = null;
let preflightIssueDisplayMode = 'auto'; // auto | scoped | global
let preflightScopedBucketFilter = 'all'; // all | scope_only | outside_scope_only | shared
let preflightScopedIssueCodeFocus = ''; // active scoped issue-code focus chip
let preflightLastScopedContextCopyText = '';
let preflightLastScopedIssueExcerptCopyText = '';
let preflightLastScopedIssueExcerptJsonCopyText = '';

// Analysis control variables
let analysisModal, closeAnalysisModalBtn, analysisModalButton,
    energyBinsInput, spatialBinsInput, analysisSensitiveDetectorSelect, refreshAnalysisButton, analysisStatusDisplay;

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
    onLoadRunResults: () => { },
    onRenameVersion: (projectName, versionId, newDescription) => { },
    onDeleteVersion: (projectName, versionId, versionDescription, runCount) => { },
    onDeleteRun: (projectName, versionId, runId, versionDescription) => { },
    onDeleteHistorySelection: (projectName, selection) => { },
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
    onAddDetectorFeatureGeneratorClicked: () => { },
    onEditDetectorFeatureGeneratorClicked: (_generatorEntry) => { },
    onRealizeDetectorFeatureGeneratorClicked: (_generatorEntry) => { },
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
    onReimportStepClicked: (file, importRecord) => { },
    onCadImportBatchActionClicked: (action, importRecord) => { },
    onSetApiKeyClicked: () => { },
    onSaveApiKeyClicked: (apiKey) => { },
    onSourceActivationToggled: (sourceId) => { },
    onRunSimulationClicked: (simSettings) => { },
    onStopSimulationClicked: () => { },
    onRunPreflightClicked: () => { },
    onSimOptionsClicked: () => { },
    onSaveSimOptions: () => { },
    onDrawTracksToggle: () => { },
    onAnalysisModalOpen: () => { },
    onRefreshAnalysisClicked: (energyBins, spatialBins, sensitiveDetector) => { },
    onDownloadSimDataClicked: () => { },
    onSelectHierarchyItems: (selectedIds) => { },
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
    historySelectModeButton = document.getElementById('historySelectModeButton');
    historySelectionBar = document.getElementById('history_selection_bar');
    historySelectionSummary = document.getElementById('history_selection_summary');
    historyDeleteSelectedButton = document.getElementById('historyDeleteSelectedButton');
    historyCancelSelectionButton = document.getElementById('historyCancelSelectionButton');
    undoButton = document.getElementById('undoButton');
    redoButton = document.getElementById('redoButton');

    // Create ring array
    createRingArrayButton = document.getElementById('createRingArrayButton');
    createDetectorFeatureGeneratorButton = document.getElementById('createDetectorFeatureGeneratorButton');

    // Hierarchy and Inspector Roots
    structureTreeRoot = document.getElementById('structure_tree_root');
    assembliesListRoot = document.getElementById('assemblies_list_root');
    lvolumesListRoot = document.getElementById('lvolumes_list_root');
    definesListRoot = document.getElementById('defines_list_root');
    materialsListRoot = document.getElementById('materials_list_root');
    elementsListRoot = document.getElementById('elements_list_root');
    solidsListRoot = document.getElementById('solids_list_root');
    inspectorContentDiv = document.getElementById('inspector_content');
    environmentPanelRoot = document.getElementById('environment_panel_root');
    cadImportsPanelRoot = document.getElementById('cad_imports_panel_root');
    detectorFeatureGeneratorsPanelRoot = document.getElementById('detector_feature_generators_panel_root');
    scoringPanelRoot = document.getElementById('scoring_panel_root');


    // Bottom panel (AI and simulation)
    bottomPanel = document.getElementById('bottom_panel');
    bottomPanelResizeHandle = document.getElementById('bottomPanelResizeHandle');
    toggleBottomPanelBtn = document.getElementById('toggleBottomPanelBtn');

    // AI Panel elements
    aiPromptInput = document.getElementById('ai_prompt_input');
    aiGenerateButton = document.getElementById('ai_generate_button');
    aiModelSelect = document.getElementById('ai_model_select');
    aiBackendStatusEl = document.getElementById('ai_backend_status');

    if (aiModelSelect) {
        aiModelSelect.addEventListener('change', () => {
            updateAiBackendStatus();
        });
    }

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
    preflightButton = document.getElementById('preflightButton');
    simOptionsButton = document.getElementById('simOptionsButton');
    simConsole = document.getElementById('sim_console');
    simStatusDisplay = document.getElementById('sim_status_display');
    preflightPanel = document.getElementById('preflight_panel');
    preflightSummaryLine = document.getElementById('preflight_summary_line');
    preflightScopeLine = document.getElementById('preflight_scope_line');
    preflightDeltaLine = document.getElementById('preflight_delta_line');
    preflightScopeHintLine = document.getElementById('preflight_scope_hint_line');
    preflightScopeBucketsLine = document.getElementById('preflight_scope_buckets_line');
    preflightScopeBucketFilterRow = document.getElementById('preflight_scope_bucket_filter_row');
    preflightBucketAllBtn = document.getElementById('preflight_bucket_all_btn');
    preflightBucketScopeOnlyBtn = document.getElementById('preflight_bucket_scope_only_btn');
    preflightBucketOutsideOnlyBtn = document.getElementById('preflight_bucket_outside_only_btn');
    preflightBucketSharedBtn = document.getElementById('preflight_bucket_shared_btn');
    preflightIssueCodeChipRow = document.getElementById('preflight_issue_code_chip_row');
    preflightScopeContextRow = document.getElementById('preflight_scope_context_row');
    preflightCopyScopeContextBtn = document.getElementById('preflight_copy_scope_context_btn');
    preflightCopyScopeIssueExcerptBtn = document.getElementById('preflight_copy_scope_issue_excerpt_btn');
    preflightCopyScopeIssueExcerptJsonBtn = document.getElementById('preflight_copy_scope_issue_excerpt_json_btn');
    preflightScopeContextStatus = document.getElementById('preflight_scope_context_status');
    preflightIssueToggleRow = document.getElementById('preflight_issue_toggle_row');
    preflightShowScopeIssuesBtn = document.getElementById('preflight_show_scope_issues_btn');
    preflightShowGlobalIssuesBtn = document.getElementById('preflight_show_global_issues_btn');
    preflightIssuesLabel = document.getElementById('preflight_issues_label');
    preflightIssuesList = document.getElementById('preflight_issues_list');

    simOptionsModal = document.getElementById('simOptionsModal');
    saveSimOptionsButton = document.getElementById('saveSimOptions');

    clearPreflightReport();
    simSeed1Input = document.getElementById('simSeed1');
    simSeed2Input = document.getElementById('simSeed2');
    simSaveHitsCheckbox = document.getElementById('simSaveHits');
    simSaveHitMetadataCheckbox = document.getElementById('simSaveHitMetadata');
    simHitEnergyThresholdInput = document.getElementById('simHitEnergyThreshold');
    simProductionCutInput = document.getElementById('simProductionCut');
    simSaveParticlesCheckbox = document.getElementById('simSaveParticles');
    simSaveTracksRangeInput = document.getElementById('simSaveTracksRange');
    drawTracksCheckbox = document.getElementById('drawTracksCheckbox');
    drawTracksRangeInput = document.getElementById('drawTracksRange');
    simPrintProgressInput = document.getElementById('simPrintProgress');
    simPhysicsListSelect = document.getElementById('simPhysicsList');
    simOpticalPhysicsCheckbox = document.getElementById('simOpticalPhysics');

    // Analysis elements
    analysisModal = document.getElementById('analysisModal');
    closeAnalysisModalBtn = document.getElementById('closeAnalysisModal');
    analysisModalButton = document.getElementById('analysisModalButton');
    energyBinsInput = document.getElementById('energyBinsInput');
    spatialBinsInput = document.getElementById('spatialBinsInput');
    analysisSensitiveDetectorSelect = document.getElementById('analysisSensitiveDetectorSelect');
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

    // Tools dropdown toggle
    const toolsDropdownButton = document.getElementById('toolsDropdownButton');
    const toolsDropdownContent = document.getElementById('toolsDropdownContent');
    const closeToolsDropdown = () => {
        const dropdown = toolsDropdownButton?.parentElement;
        if (dropdown) {
            dropdown.classList.remove('show');
        }
    };

    if (createDetectorFeatureGeneratorButton) {
        createDetectorFeatureGeneratorButton.disabled = true;
        createDetectorFeatureGeneratorButton.title = 'Open or create a project with eligible geometry before launching a detector generator.';
        createDetectorFeatureGeneratorButton.addEventListener('click', () => {
            closeToolsDropdown();
            callbacks.onAddDetectorFeatureGeneratorClicked();
        });
    }

    if (createRingArrayButton) {
        createRingArrayButton.disabled = true;
        createRingArrayButton.title = 'Open or create a project before launching the ring-array tool.';
        createRingArrayButton.addEventListener('click', () => {
            closeToolsDropdown();
            callbacks.onAddRingArrayClicked();
        });
    }

    if (toolsDropdownButton && toolsDropdownContent) {
        toolsDropdownButton.addEventListener('click', (e) => {
            e.stopPropagation();
            const dropdown = toolsDropdownButton.parentElement;
            dropdown.classList.toggle('show');
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!toolsDropdownButton.contains(e.target) && !toolsDropdownContent.contains(e.target)) {
                const dropdown = toolsDropdownButton.parentElement;
                dropdown.classList.remove('show');
            }
        });
    }

    // Project history and undo/redo listeners
    historyButton.addEventListener('click', callbacks.onHistoryButtonClicked);
    closeHistoryPanel.addEventListener('click', hideHistoryPanel);
    if (historySelectModeButton) {
        historySelectModeButton.addEventListener('click', () => {
            setHistorySelectionMode(!historySelectionMode);
        });
    }
    if (historyDeleteSelectedButton) {
        historyDeleteSelectedButton.addEventListener('click', () => {
            callbacks.onDeleteHistorySelection(historyLastProjectName, getHistorySelectionPayload());
        });
    }
    if (historyCancelSelectionButton) {
        historyCancelSelectionButton.addEventListener('click', () => {
            setHistorySelectionMode(false);
        });
    }
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

    // Listener for the bottom panel collapse/restore button (single-click toggle)
    if (bottomPanel) {
        requestAnimationFrame(() => {
            const measuredHeight = Math.round(bottomPanel.getBoundingClientRect().height);
            if (measuredHeight > 0) {
                bottomPanelLastExpandedHeight = measuredHeight;
                bottomPanel.style.height = `${clampBottomPanelHeight(measuredHeight)}px`;
            }
            updateBottomPanelToggleButton();
        });
    }

    if (toggleBottomPanelBtn) {
        toggleBottomPanelBtn.addEventListener('click', () => {
            setBottomPanelMinimizedState(!bottomPanel.classList.contains('minimized'));
        });
    }

    if (bottomPanelResizeHandle) {
        bottomPanelResizeHandle.addEventListener('mousedown', (event) => {
            if (!bottomPanel || bottomPanel.classList.contains('minimized')) return;

            event.preventDefault();
            bottomPanel.classList.add('resizing');
            let collapsedByDrag = false;
            const previousUserSelect = document.body.style.userSelect;
            const previousCursor = document.body.style.cursor;
            document.body.style.userSelect = 'none';
            document.body.style.cursor = 'ns-resize';

            const handleMouseMove = (moveEvent) => {
                if (collapsedByDrag) return;

                const parentRect = bottomPanel.parentElement?.getBoundingClientRect();
                if (!parentRect) return;
                const desiredHeight = parentRect.bottom - moveEvent.clientY;
                if (desiredHeight <= BOTTOM_PANEL_COLLAPSE_THRESHOLD) {
                    collapsedByDrag = true;
                    setBottomPanelMinimizedState(true);
                    return;
                }

                if (bottomPanel.classList.contains('minimized')) {
                    bottomPanel.classList.remove('minimized');
                    updateBottomPanelToggleButton();
                }
                applyBottomPanelHeight(desiredHeight);
            };

            const handleMouseUp = () => {
                document.removeEventListener('mousemove', handleMouseMove);
                document.removeEventListener('mouseup', handleMouseUp);
                bottomPanel.classList.remove('resizing');
                document.body.style.userSelect = previousUserSelect;
                document.body.style.cursor = previousCursor;
                if (collapsedByDrag) {
                    setBottomPanelMinimizedState(true);
                }
                scheduleBottomPanelLayoutRefresh();
            };

            document.addEventListener('mousemove', handleMouseMove);
            document.addEventListener('mouseup', handleMouseUp);
        });
    }

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
    if (preflightButton) preflightButton.addEventListener('click', callbacks.onRunPreflightClicked);
    if (preflightShowScopeIssuesBtn) {
        preflightShowScopeIssuesBtn.addEventListener('click', () => {
            preflightIssueDisplayMode = 'scoped';
            if (preflightLastRenderState) {
                renderPreflightReport(preflightLastRenderState.report, preflightLastRenderState.details);
            }
        });
    }
    if (preflightShowGlobalIssuesBtn) {
        preflightShowGlobalIssuesBtn.addEventListener('click', () => {
            preflightIssueDisplayMode = 'global';
            if (preflightLastRenderState) {
                renderPreflightReport(preflightLastRenderState.report, preflightLastRenderState.details);
            }
        });
    }

    const preflightBucketButtons = [
        { button: preflightBucketAllBtn, value: 'all' },
        { button: preflightBucketScopeOnlyBtn, value: 'scope_only' },
        { button: preflightBucketOutsideOnlyBtn, value: 'outside_scope_only' },
        { button: preflightBucketSharedBtn, value: 'shared' },
    ];
    preflightBucketButtons.forEach(({ button, value }) => {
        if (!button) return;
        button.addEventListener('click', () => {
            preflightScopedBucketFilter = value;
            if (preflightLastRenderState) {
                renderPreflightReport(preflightLastRenderState.report, preflightLastRenderState.details);
            }
        });
    });

    if (preflightCopyScopeContextBtn) {
        preflightCopyScopeContextBtn.addEventListener('click', async () => {
            if (!preflightLastScopedContextCopyText) {
                setPreflightScopeContextStatus('Nothing to copy yet.', 'warning');
                return;
            }

            const copied = await copyTextToClipboard(preflightLastScopedContextCopyText);
            if (copied) {
                setPreflightScopeContextStatus('Copied filter context.', 'success');
            } else {
                setPreflightScopeContextStatus('Copy failed.', 'error');
            }
        });
    }

    if (preflightCopyScopeIssueExcerptBtn) {
        preflightCopyScopeIssueExcerptBtn.addEventListener('click', async () => {
            if (!preflightLastScopedIssueExcerptCopyText) {
                setPreflightScopeContextStatus('Nothing to copy yet.', 'warning');
                return;
            }

            const copied = await copyTextToClipboard(preflightLastScopedIssueExcerptCopyText);
            if (copied) {
                setPreflightScopeContextStatus('Copied issue excerpt.', 'success');
            } else {
                setPreflightScopeContextStatus('Copy failed.', 'error');
            }
        });
    }

    if (preflightCopyScopeIssueExcerptJsonBtn) {
        preflightCopyScopeIssueExcerptJsonBtn.addEventListener('click', async () => {
            if (!preflightLastScopedIssueExcerptJsonCopyText) {
                setPreflightScopeContextStatus('Nothing to copy yet.', 'warning');
                return;
            }

            const copied = await copyTextToClipboard(preflightLastScopedIssueExcerptJsonCopyText);
            if (copied) {
                setPreflightScopeContextStatus('Copied issue excerpt JSON.', 'success');
            } else {
                setPreflightScopeContextStatus('Copy failed.', 'error');
            }
        });
    }

    simOptionsButton.addEventListener('click', callbacks.onSimOptionsClicked);
    saveSimOptionsButton.addEventListener('click', callbacks.onSaveSimOptions);
    drawTracksCheckbox.addEventListener('change', callbacks.onDrawTracksToggle);
    drawTracksRangeInput.addEventListener('change', callbacks.onDrawTracksToggle); // Also trigger on range change

    if (analysisModalButton) {
        analysisModalButton.addEventListener('click', callbacks.onAnalysisModalOpen);
    }
    if (closeAnalysisModalBtn) {
        closeAnalysisModalBtn.addEventListener('click', hideAnalysisModal);
    }
    if (analysisSensitiveDetectorSelect) {
        analysisSensitiveDetectorSelect.addEventListener('change', () => {
            const energyBins = parseInt(energyBinsInput.value, 10);
            const spatialBins = parseInt(spatialBinsInput.value, 10);
            callbacks.onRefreshAnalysisClicked(energyBins, spatialBins, getSelectedSensitiveDetectorFilter());
        });
    }

    // Analysis listener
    if (refreshAnalysisButton) {
        refreshAnalysisButton.addEventListener('click', () => {
            const energyBins = parseInt(energyBinsInput.value, 10);
            const spatialBins = parseInt(spatialBinsInput.value, 10);
            callbacks.onRefreshAnalysisClicked(energyBins, spatialBins, getSelectedSensitiveDetectorFilter());
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
            // Reload AI chat history when switching to AI panel
            if (targetTabId === 'tab_ai_panel' && window.aiAssistant && window.aiAssistant.reloadHistory) {
                window.aiAssistant.reloadHistory();
            }
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

function clampBottomPanelHeight(heightPx) {
    if (!bottomPanel) return Math.max(Number(heightPx) || 0, 0);

    const requested = Number.isFinite(Number(heightPx)) ? Number(heightPx) : bottomPanelLastExpandedHeight;
    const parentHeight = bottomPanel.parentElement?.clientHeight || window.innerHeight;
    const minHeight = BOTTOM_PANEL_MIN_EXPANDED_HEIGHT;
    const maxHeight = Math.max(minHeight, parentHeight - 120);
    return Math.min(Math.max(requested, minHeight), maxHeight);
}

function applyBottomPanelHeight(heightPx) {
    if (!bottomPanel) return;
    const clamped = Math.round(clampBottomPanelHeight(heightPx));
    bottomPanel.style.height = `${clamped}px`;
    bottomPanelLastExpandedHeight = clamped;
    scheduleBottomPanelLayoutRefresh();
}

function scheduleBottomPanelLayoutRefresh() {
    if (bottomPanelResizeRefreshHandle !== null) return;
    bottomPanelResizeRefreshHandle = requestAnimationFrame(() => {
        bottomPanelResizeRefreshHandle = null;
        window.dispatchEvent(new Event('resize'));
    });
}

function updateBottomPanelToggleButton() {
    if (!toggleBottomPanelBtn || !bottomPanel) return;
    const isMinimized = bottomPanel.classList.contains('minimized');
    toggleBottomPanelBtn.textContent = isMinimized ? '↑' : '↓';
    toggleBottomPanelBtn.title = isMinimized ? 'Restore Panel' : 'Minimize Panel';
}

function setBottomPanelMinimizedState(isMinimized) {
    if (!bottomPanel) return;

    if (isMinimized) {
        const currentHeight = Math.round(bottomPanel.getBoundingClientRect().height);
        if (currentHeight > BOTTOM_PANEL_COLLAPSE_THRESHOLD) {
            bottomPanelLastExpandedHeight = currentHeight;
        }
        bottomPanel.classList.add('minimized');
        bottomPanel.style.removeProperty('height');
    } else {
        bottomPanel.classList.remove('minimized');
        applyBottomPanelHeight(bottomPanelLastExpandedHeight);
    }

    updateBottomPanelToggleButton();
    scheduleBottomPanelLayoutRefresh();
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
    refreshHistorySelectionUi();
}

export function hideHistoryPanel() {
    historyPanel.style.display = 'none';
    setHistorySelectionMode(false);
}

function makeHistoryRunSelectionKey(versionId, runId) {
    return `${encodeURIComponent(versionId)}::${encodeURIComponent(runId)}`;
}

function parseHistoryRunSelectionKey(key) {
    const [versionId = '', runId = ''] = String(key || '').split('::');
    return {
        versionId: decodeURIComponent(versionId),
        runId: decodeURIComponent(runId),
    };
}

function getHistoryRunSelectionKeysForVersion(version) {
    if (!version || !Array.isArray(version.runs)) return [];
    return version.runs.map(runId => makeHistoryRunSelectionKey(version.id, runId));
}

function renderCachedHistoryPanel() {
    populateHistoryPanel(historyLastEntries, historyLastProjectName);
}

function getHistorySelectionPayload() {
    return {
        versionIds: [...historySelectedVersionIds],
        runs: [...historySelectedRunKeys].map(parseHistoryRunSelectionKey),
    };
}

function summarizeHistorySelection() {
    const versionCount = historySelectedVersionIds.size;
    const runCount = historySelectedRunKeys.size;
    const parts = [];

    if (versionCount > 0) {
        parts.push(`${versionCount} version${versionCount === 1 ? '' : 's'}`);
    }
    if (runCount > 0) {
        parts.push(`${runCount} run${runCount === 1 ? '' : 's'}`);
    }

    return parts.length > 0 ? `${parts.join(', ')} selected` : 'No items selected';
}

function pruneHistorySelection(history) {
    const validAllVersionIds = new Set(
        (Array.isArray(history) ? history : [])
            .filter(version => version)
            .map(version => version.id)
    );
    const validVersionIds = new Set(
        (Array.isArray(history) ? history : [])
            .filter(version => version && !version.is_autosave)
            .map(version => version.id)
    );
    const validRunKeys = new Set();

    (Array.isArray(history) ? history : []).forEach(version => {
        if (!version || !Array.isArray(version.runs)) return;
        version.runs.forEach(runId => {
            validRunKeys.add(makeHistoryRunSelectionKey(version.id, runId));
        });
    });

    historySelectedVersionIds = new Set(
        [...historySelectedVersionIds].filter(versionId => validVersionIds.has(versionId))
    );
    historySelectedRunKeys = new Set(
        [...historySelectedRunKeys].filter(key => {
            const { versionId } = parseHistoryRunSelectionKey(key);
            return validRunKeys.has(key) && !historySelectedVersionIds.has(versionId);
        })
    );
    historyExpandedVersionIds = new Set(
        [...historyExpandedVersionIds].filter(versionId => validAllVersionIds.has(versionId))
    );
}

function refreshHistorySelectionUi() {
    const hasSelection = historySelectedVersionIds.size > 0 || historySelectedRunKeys.size > 0;

    if (historyPanel) {
        historyPanel.classList.toggle('history-selection-mode', historySelectionMode);
    }
    if (historySelectModeButton) {
        historySelectModeButton.textContent = historySelectionMode ? 'Done' : 'Select';
        historySelectModeButton.classList.toggle('active', historySelectionMode);
    }
    if (historySelectionBar) {
        historySelectionBar.style.display = historySelectionMode ? 'flex' : 'none';
    }
    if (historySelectionSummary) {
        historySelectionSummary.textContent = summarizeHistorySelection();
    }
    if (historyDeleteSelectedButton) {
        historyDeleteSelectedButton.disabled = !hasSelection;
    }
}

export function setHistorySelectionMode(enabled) {
    const nextMode = Boolean(enabled);
    historySelectionMode = nextMode;
    if (!nextMode) {
        historySelectedVersionIds = new Set();
        historySelectedRunKeys = new Set();
    }
    refreshHistorySelectionUi();
    if (historyLastProjectName) {
        renderCachedHistoryPanel();
    }
}

export function clearHistorySelection() {
    historySelectedVersionIds = new Set();
    historySelectedRunKeys = new Set();
    refreshHistorySelectionUi();
    if (historyLastProjectName) {
        renderCachedHistoryPanel();
    }
}

export function populateHistoryPanel(history, projectName) {
    historyLastEntries = Array.isArray(history) ? history : [];
    historyLastProjectName = projectName || '';
    pruneHistorySelection(historyLastEntries);
    refreshHistorySelectionUi();

    historyListContainer.innerHTML = '';
    if (historyLastEntries.length === 0) {
        historyListContainer.innerHTML = '<p>&nbsp;&nbsp;No saved versions.</p>';
        return;
    }

    historyLastEntries.forEach(version => {
        const versionItem = document.createElement('div');
        versionItem.className = 'accordion-item';
        versionItem.dataset.versionId = version.id;

        // --- Add a special class for the autosave item ---
        if (version.is_autosave) {
            versionItem.classList.add('autosave-history-item');
        }

        const header = document.createElement('div');
        header.className = 'accordion-header';

        if (historySelectionMode && !version.is_autosave) {
            const versionCheckbox = document.createElement('input');
            versionCheckbox.type = 'checkbox';
            versionCheckbox.className = 'history-select-checkbox version-select-checkbox';
            versionCheckbox.checked = historySelectedVersionIds.has(version.id);
            versionCheckbox.title = `Select version ${version.description || version.id}. Alt/Option-click to select all runs in this version.`;
            versionCheckbox.addEventListener('click', (e) => {
                e.stopPropagation();

                if (!e.altKey) return;

                e.preventDefault();
                historySelectedVersionIds.delete(version.id);

                const versionRunKeys = getHistoryRunSelectionKeysForVersion(version);
                const shouldSelectAllRuns = versionRunKeys.some(key => !historySelectedRunKeys.has(key));

                historySelectedRunKeys = new Set(
                    [...historySelectedRunKeys].filter((key) => parseHistoryRunSelectionKey(key).versionId !== version.id)
                );

                if (shouldSelectAllRuns) {
                    versionRunKeys.forEach((key) => historySelectedRunKeys.add(key));
                }

                refreshHistorySelectionUi();
                renderCachedHistoryPanel();
            });
            versionCheckbox.addEventListener('change', (e) => {
                if (e.target.checked) {
                    historySelectedVersionIds.add(version.id);
                    historySelectedRunKeys = new Set(
                        [...historySelectedRunKeys].filter((key) => parseHistoryRunSelectionKey(key).versionId !== version.id)
                    );
                } else {
                    historySelectedVersionIds.delete(version.id);
                }
                refreshHistorySelectionUi();
                renderCachedHistoryPanel();
            });
            header.appendChild(versionCheckbox);
        }

        const toggle = document.createElement('span');
        toggle.className = 'accordion-toggle';
        toggle.textContent = historyExpandedVersionIds.has(version.id) ? '[-]' : '[+]';

        const versionInfo = document.createElement('div');
        versionInfo.className = 'version-info';

        const versionDesc = document.createElement('span');
        versionDesc.className = 'version-desc';
        versionDesc.textContent = version.is_autosave
            ? `🕒 ${version.description}`
            : (version.description || 'Saved');

        const versionTs = document.createElement('span');
        versionTs.className = 'version-ts';
        const runCount = Array.isArray(version.runs) ? version.runs.length : 0;
        const runLabel = `${runCount} run${runCount === 1 ? '' : 's'}`;
        versionTs.textContent = `${formatTimestamp(version.timestamp)} · ${runLabel}`;

        versionInfo.appendChild(versionDesc);
        versionInfo.appendChild(versionTs);

        const headerActions = document.createElement('div');
        headerActions.className = 'history-actions';

        const loadBtn = document.createElement('button');
        loadBtn.className = 'history-action-btn load-version-btn';
        loadBtn.type = 'button';
        loadBtn.title = 'Load this project version';
        loadBtn.textContent = 'Load';
        headerActions.appendChild(loadBtn);
        headerActions.hidden = historySelectionMode;

        if (!version.is_autosave) {
            const deleteVersionBtn = document.createElement('button');
            deleteVersionBtn.className = 'history-action-btn history-delete-btn';
            deleteVersionBtn.type = 'button';
            deleteVersionBtn.title = 'Delete this version and all of its simulation runs';
            deleteVersionBtn.textContent = 'Delete';
            headerActions.appendChild(deleteVersionBtn);

            deleteVersionBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                callbacks.onDeleteVersion(projectName, version.id, version.description || 'Saved', runCount);
            });
        }

        header.appendChild(toggle);
        header.appendChild(versionInfo);
        header.appendChild(headerActions);

        const content = document.createElement('div');
        content.className = 'accordion-content';
        if (historyExpandedVersionIds.has(version.id)) {
            content.classList.add('active');
        }

        // --- Populate with simulation runs ---
        if (version.runs && version.runs.length > 0) {
            const runList = document.createElement('ul');
            version.runs.forEach(runId => {
                const runLi = document.createElement('li');
                runLi.className = 'run-item';
                runLi.dataset.versionId = version.id;
                runLi.dataset.runId = runId;

                const runSelectionKey = makeHistoryRunSelectionKey(version.id, runId);
                const versionSelected = historySelectedVersionIds.has(version.id);

                if (historySelectionMode) {
                    const runCheckbox = document.createElement('input');
                    runCheckbox.type = 'checkbox';
                    runCheckbox.className = 'history-select-checkbox run-select-checkbox';
                    runCheckbox.checked = historySelectedRunKeys.has(runSelectionKey);
                    runCheckbox.disabled = versionSelected;
                    runCheckbox.title = versionSelected
                        ? 'This run is already included because its version is selected.'
                        : `Select run ${runId}`;
                    runCheckbox.addEventListener('click', (e) => e.stopPropagation());
                    runCheckbox.addEventListener('change', (e) => {
                        if (e.target.checked) {
                            historySelectedRunKeys.add(runSelectionKey);
                        } else {
                            historySelectedRunKeys.delete(runSelectionKey);
                        }
                        refreshHistorySelectionUi();
                    });
                    runLi.appendChild(runCheckbox);
                }

                const runLabelEl = document.createElement('span');
                runLabelEl.className = 'run-item-label';
                runLabelEl.textContent = `Run: ${runId.substring(0, 8)}...`;
                runLi.appendChild(runLabelEl);

                const runActions = document.createElement('div');
                runActions.className = 'history-actions run-actions';

                const openRunBtn = document.createElement('button');
                openRunBtn.className = 'history-action-btn';
                openRunBtn.type = 'button';
                openRunBtn.textContent = 'Open';
                openRunBtn.title = `Load geometry and tracks for run ${runId}`;
                openRunBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    callbacks.onLoadRunResults(version.id, runId);
                });

                const deleteRunBtn = document.createElement('button');
                deleteRunBtn.className = 'history-action-btn history-delete-btn';
                deleteRunBtn.type = 'button';
                deleteRunBtn.textContent = 'Delete';
                deleteRunBtn.title = `Delete simulation run ${runId}`;
                deleteRunBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    callbacks.onDeleteRun(projectName, version.id, runId, version.description || 'Saved');
                });

                runActions.appendChild(openRunBtn);
                runActions.appendChild(deleteRunBtn);
                runLi.appendChild(runActions);
                runActions.hidden = historySelectionMode;

                runLi.title = `Show tracks for this run (${runId})`;
                runLi.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (historySelectionMode) {
                        const runCheckbox = runLi.querySelector('.run-select-checkbox');
                        if (runCheckbox && !runCheckbox.disabled) {
                            runCheckbox.checked = !runCheckbox.checked;
                            runCheckbox.dispatchEvent(new Event('change'));
                        }
                        return;
                    }
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
                ac.previousElementSibling.querySelector('.accordion-toggle').textContent = '[+]';
            });
            historyExpandedVersionIds = new Set();
            // Toggle current one
            if (!isActive) {
                content.classList.add('active');
                header.querySelector('.accordion-toggle').textContent = '[-]';
                historyExpandedVersionIds.add(version.id);
            }
        });

        header.querySelector('.load-version-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            callbacks.onLoadVersionClicked(projectName, version.id);
        });

        if (!version.is_autosave) {
            versionDesc.title = 'Click to rename this version';
            versionDesc.style.cursor = 'pointer';
            versionDesc.addEventListener('click', (e) => {
                e.stopPropagation();
                const currentDesc = version.description || 'Saved';
                const newDesc = prompt('Rename version description:', currentDesc);
                if (newDesc && newDesc.trim() && newDesc.trim() !== currentDesc) {
                    callbacks.onRenameVersion(projectName, version.id, newDesc.trim());
                }
            });
        }
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

function toDomSafeToken(value) {
    const raw = String(value ?? '').trim();
    if (!raw) return 'item';
    return raw.replace(/[^A-Za-z0-9_-]/g, '_');
}

function createEditableExpressionProperty(parent, { inputId, labelText, initialValue, propertyPath, onChange }) {
    const propDiv = document.createElement('div');
    propDiv.className = 'property_item editable';
    propDiv.dataset.propertyPath = propertyPath;

    const component = ExpressionInput.create(
        inputId,
        labelText,
        initialValue,
        (newValue) => onChange(newValue)
    );

    const inputEl = component.querySelector('.expression-input');
    if (inputEl) {
        inputEl.dataset.propertyPath = propertyPath;
    }

    propDiv.appendChild(component);
    parent.appendChild(propDiv);
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

            const editableReplicaFields = getReplicaInspectorEditableFieldSpecs(replica);
            const lvIdForUpdate = id || name;
            const inputIdPrefix = `inspector_replica_${toDomSafeToken(lvIdForUpdate)}`;

            editableReplicaFields.forEach((field) => {
                createEditableExpressionProperty(inspectorContentDiv, {
                    inputId: `${inputIdPrefix}_${field.key}`,
                    labelText: field.label,
                    initialValue: field.value,
                    propertyPath: field.propertyPath,
                    onChange: (newExpressionValue) => {
                        const update = buildReplicaInspectorPropertyUpdateArgs(
                            lvIdForUpdate,
                            field.propertyPath,
                            newExpressionValue
                        );
                        callbacks.onInspectorPropertyChanged(
                            update.objectType,
                            update.objectId,
                            update.propertyPath,
                            update.newValue
                        );
                    }
                });
            });

            const dir = replica.direction;
            createReadOnlyProperty(inspectorContentDiv, "Direction:", `(x: ${dir.x}, y: ${dir.y}, z: ${dir.z})`);
        } else if (data.content_type === 'division') {
            const division = data.content;
            createReadOnlyProperty(inspectorContentDiv, "Solid (Envelope):", data.solid_ref);
            createReadOnlyProperty(inspectorContentDiv, "Divided LV:", division.volume_ref);

            const editableDivisionFields = getDivisionInspectorEditableFieldSpecs(division);
            const lvIdForUpdate = id || name;
            const inputIdPrefix = `inspector_division_${toDomSafeToken(lvIdForUpdate)}`;

            editableDivisionFields.forEach((field) => {
                createEditableExpressionProperty(inspectorContentDiv, {
                    inputId: `${inputIdPrefix}_${field.key}`,
                    labelText: field.label,
                    initialValue: field.value,
                    propertyPath: field.propertyPath,
                    onChange: (newExpressionValue) => {
                        const update = buildDivisionInspectorPropertyUpdateArgs(
                            lvIdForUpdate,
                            field.propertyPath,
                            newExpressionValue
                        );
                        callbacks.onInspectorPropertyChanged(
                            update.objectType,
                            update.objectId,
                            update.propertyPath,
                            update.newValue
                        );
                    }
                });
            });

            createReadOnlyProperty(inspectorContentDiv, "Axis:", division.axis);
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
    if (value && typeof value === 'object' && !Array.isArray(value) && Object.prototype.hasOwnProperty.call(value, 'text')) {
        valueSpan.textContent = value.text;
        if (value.title) {
            valueSpan.title = value.title;
        }
    } else {
        valueSpan.textContent = Array.isArray(value) ? `[Array of ${value.length}]` : value;
    }
    valueSpan.style.wordBreak = 'break-word';
    propDiv.appendChild(valueSpan);
    parent.appendChild(propDiv);
}

function createEnvironmentFieldInput(parent, { labelText, id, value, onChange, fieldLabel }) {
    const fieldWrap = document.createElement('div');
    fieldWrap.className = 'environment-vector-field';

    const label = document.createElement('label');
    label.htmlFor = id;
    label.textContent = labelText;
    fieldWrap.appendChild(label);

    const input = document.createElement('input');
    input.type = 'number';
    input.step = 'any';
    input.id = id;
    input.value = String(value);
    input.addEventListener('change', () => {
        const nextValue = input.valueAsNumber;
        if (!Number.isFinite(nextValue)) {
            const axisLabel = labelText.replace(/\s*\([^)]+\)$/, '');
            showError(`${fieldLabel} ${axisLabel} must be a finite number.`);
            input.value = String(value);
            return;
        }

        onChange(nextValue);
    });
    fieldWrap.appendChild(input);

    parent.appendChild(fieldWrap);
}

function createEnvironmentTextInput(parent, { labelText, id, value, onChange, placeholder = '' }) {
    const fieldWrap = document.createElement('div');
    fieldWrap.className = 'environment-vector-field environment-targets-field';

    const label = document.createElement('label');
    label.htmlFor = id;
    label.textContent = labelText;
    fieldWrap.appendChild(label);

    const input = document.createElement('input');
    input.type = 'text';
    input.id = id;
    input.placeholder = placeholder;
    input.value = value;
    input.addEventListener('change', () => {
        onChange(normalizeTargetVolumeNames(input.value));
    });
    fieldWrap.appendChild(input);

    parent.appendChild(fieldWrap);
}

function createEnvironmentPlainTextInput(parent, { labelText, id, value, onChange, placeholder = '' }) {
    const fieldWrap = document.createElement('div');
    fieldWrap.className = 'environment-vector-field environment-targets-field';

    const label = document.createElement('label');
    label.htmlFor = id;
    label.textContent = labelText;
    fieldWrap.appendChild(label);

    const input = document.createElement('input');
    input.type = 'text';
    input.id = id;
    input.placeholder = placeholder;
    input.value = value;
    input.addEventListener('change', () => {
        const nextValue = input.value.trim();
        if (!nextValue) {
            showError(`${labelText} must be a non-empty string.`);
            input.value = value;
            return;
        }

        onChange(nextValue);
    });
    fieldWrap.appendChild(input);

    parent.appendChild(fieldWrap);
}

function createScoringIntegerInput(parent, { labelText, id, value, onChange, fieldLabel }) {
    const fieldWrap = document.createElement('div');
    fieldWrap.className = 'environment-vector-field';

    const label = document.createElement('label');
    label.htmlFor = id;
    label.textContent = labelText;
    fieldWrap.appendChild(label);

    const input = document.createElement('input');
    input.type = 'number';
    input.min = '1';
    input.step = '1';
    input.id = id;
    input.value = String(value);
    input.addEventListener('change', () => {
        const nextValue = Number.parseInt(input.value, 10);
        if (!Number.isInteger(nextValue) || nextValue <= 0) {
            const axisLabel = labelText.replace(/\s*\([^)]+\)$/, '');
            showError(`${fieldLabel} ${axisLabel} must be a positive integer.`);
            input.value = String(value);
            return;
        }

        onChange(nextValue);
    });
    fieldWrap.appendChild(input);

    parent.appendChild(fieldWrap);
}

function createScoringNonNegativeIntegerInput(parent, { labelText, id, value, onChange, fieldLabel }) {
    const fieldWrap = document.createElement('div');
    fieldWrap.className = 'environment-vector-field';

    const label = document.createElement('label');
    label.htmlFor = id;
    label.textContent = labelText;
    fieldWrap.appendChild(label);

    const input = document.createElement('input');
    input.type = 'number';
    input.min = '0';
    input.step = '1';
    input.id = id;
    input.value = String(value);
    input.addEventListener('change', () => {
        const nextValue = Number.parseInt(input.value, 10);
        if (!Number.isInteger(nextValue) || nextValue < 0) {
            const axisLabel = labelText.replace(/\s*\([^)]+\)$/, '');
            showError(`${fieldLabel} ${axisLabel} must be a non-negative integer.`);
            input.value = String(value);
            return;
        }

        onChange(nextValue);
    });
    fieldWrap.appendChild(input);

    parent.appendChild(fieldWrap);
}

function appendScoringResultCard(parent, described, quantityLinesKey = 'quantityLines') {
    if (!parent || !described) return;

    const card = document.createElement('div');
    card.className = 'scoring-run-card';

    const header = document.createElement('div');
    header.className = 'scoring-run-card-header';

    const titleWrap = document.createElement('div');

    const title = document.createElement('div');
    title.className = 'scoring-title';
    title.textContent = described.title;
    titleWrap.appendChild(title);

    if (described.meta) {
        const meta = document.createElement('div');
        meta.className = 'scoring-run-meta';
        meta.textContent = described.meta;
        titleWrap.appendChild(meta);
    }

    header.appendChild(titleWrap);

    if (described.statusBadge) {
        const badge = document.createElement('code');
        badge.className = 'scoring-status';
        badge.textContent = described.statusBadge;
        header.appendChild(badge);
    }

    card.appendChild(header);

    if (described.summary) {
        const summary = document.createElement('div');
        summary.className = 'scoring-summary';
        summary.textContent = described.summary;
        card.appendChild(summary);
    }

    if (Array.isArray(described.detailLines) && described.detailLines.length > 0) {
        const detailList = document.createElement('div');
        detailList.className = 'scoring-run-details';
        described.detailLines.forEach((line) => {
            const detail = document.createElement('div');
            detail.className = 'scoring-note';
            detail.textContent = line;
            detailList.appendChild(detail);
        });
        card.appendChild(detailList);
    }

    const quantityLines = Array.isArray(described[quantityLinesKey]) ? described[quantityLinesKey] : [];
    if (quantityLines.length > 0) {
        const quantityWrap = document.createElement('div');
        quantityWrap.className = 'scoring-run-quantities';
        quantityLines.forEach((line) => {
            const pill = document.createElement('div');
            pill.className = 'scoring-run-quantity';
            pill.textContent = line;
            quantityWrap.appendChild(pill);
        });
        card.appendChild(quantityWrap);
    }

    parent.appendChild(card);
}

export function clearLoadedScoringResultMetadata({ clearPrevious = true } = {}) {
    loadedScoringResultSummary = null;
    if (clearPrevious) {
        previousLoadedScoringResultSummary = null;
    }
    renderScoringPanel(callbacks.getProjectState ? callbacks.getProjectState() : null);
}

export function setLoadedScoringResultMetadata(versionId, jobId, metadata, { shiftPrevious = true } = {}) {
    const nextSummary = buildScoringResultSummary(metadata, { versionId, jobId });
    const currentRunKey = loadedScoringResultSummary?.runKey || '';
    if (shiftPrevious && loadedScoringResultSummary && currentRunKey && currentRunKey !== nextSummary.runKey) {
        previousLoadedScoringResultSummary = loadedScoringResultSummary;
    }
    loadedScoringResultSummary = nextSummary;
    renderScoringPanel(callbacks.getProjectState ? callbacks.getProjectState() : null);
}

function renderScoringPanel(projectState) {
    if (!scoringPanelRoot) return;

    scoringPanelRoot.innerHTML = '';

    if (!projectState) {
        const empty = document.createElement('p');
        empty.textContent = 'No project loaded.';
        scoringPanelRoot.appendChild(empty);
        return;
    }

    const scoringState = normalizeScoringState(projectState?.scoring);
    const panelState = describeScoringPanelState(projectState);
    const persistScoringState = (nextScoringState) => {
        if (callbacks.onInspectorPropertyChanged) {
            callbacks.onInspectorPropertyChanged(
                SCORING_OBJECT_TYPE,
                SCORING_OBJECT_ID,
                'state',
                nextScoringState,
            );
        }
    };

    const intro = document.createElement('p');
    intro.className = 'scoring-intro';
    intro.textContent = panelState.intro;
    scoringPanelRoot.appendChild(intro);

    if (panelState.hint) {
        const hint = document.createElement('p');
        hint.className = 'scoring-note';
        hint.textContent = panelState.hint;
        scoringPanelRoot.appendChild(hint);
    }

    const describedLoadedResult = describeScoringResultSummary(loadedScoringResultSummary);
    if (describedLoadedResult) {
        appendScoringResultCard(scoringPanelRoot, describedLoadedResult);
    }

    const describedComparison = describeScoringResultComparison(
        compareScoringResultSummaries(previousLoadedScoringResultSummary, loadedScoringResultSummary),
    );
    if (describedComparison) {
        appendScoringResultCard(scoringPanelRoot, describedComparison, 'deltaLines');
    }

    const describedRunControls = describeScoringRunControls(scoringState);
    const runControlsCard = document.createElement('details');
    runControlsCard.className = 'scoring-card';
    runControlsCard.open = true;

    const runControlsSummary = document.createElement('summary');
    runControlsSummary.className = 'scoring-card-summary';
    runControlsSummary.title = 'Inspect and revise the saved scoring-focused run defaults.';

    const runControlsSummaryLayout = document.createElement('div');
    runControlsSummaryLayout.className = 'scoring-card-summary-layout';

    const runControlsSummaryText = document.createElement('div');
    runControlsSummaryText.className = 'scoring-card-summary-text';

    const runControlsTitle = document.createElement('div');
    runControlsTitle.className = 'scoring-title';
    runControlsTitle.textContent = describedRunControls.title;
    runControlsSummaryText.appendChild(runControlsTitle);

    const runControlsSummaryLine = document.createElement('div');
    runControlsSummaryLine.className = 'scoring-summary';
    runControlsSummaryLine.textContent = describedRunControls.summary;
    runControlsSummaryText.appendChild(runControlsSummaryLine);

    const runControlsSummaryMeta = document.createElement('div');
    runControlsSummaryMeta.className = 'scoring-summary-meta';

    const runControlsStatus = document.createElement('code');
    runControlsStatus.className = 'scoring-status';
    runControlsStatus.textContent = describedRunControls.statusBadge;
    runControlsSummaryMeta.appendChild(runControlsStatus);

    runControlsSummaryLayout.appendChild(runControlsSummaryText);
    runControlsSummaryLayout.appendChild(runControlsSummaryMeta);
    runControlsSummary.appendChild(runControlsSummaryLayout);
    runControlsCard.appendChild(runControlsSummary);

    const runControlsBody = document.createElement('div');
    runControlsBody.className = 'scoring-card-body';

    const persistRunManifestDefaults = (updates) => {
        persistScoringState(buildScoringStateWithUpdatedRunManifestDefaults(scoringState, updates));
    };

    const executionRow = document.createElement('div');
    executionRow.className = 'environment-vector-row';
    createScoringIntegerInput(executionRow, {
        labelText: 'Threads',
        id: 'scoring_run_defaults_threads',
        value: scoringState.run_manifest_defaults.threads,
        fieldLabel: 'Run controls',
        onChange: (nextValue) => {
            persistRunManifestDefaults({ threads: nextValue });
        },
    });
    createScoringNonNegativeIntegerInput(executionRow, {
        labelText: 'Print Progress',
        id: 'scoring_run_defaults_print_progress',
        value: scoringState.run_manifest_defaults.print_progress,
        fieldLabel: 'Run controls',
        onChange: (nextValue) => {
            persistRunManifestDefaults({ print_progress: nextValue });
        },
    });
    runControlsBody.appendChild(executionRow);

    const seedRow = document.createElement('div');
    seedRow.className = 'environment-vector-row';
    createScoringNonNegativeIntegerInput(seedRow, {
        labelText: 'Seed 1',
        id: 'scoring_run_defaults_seed1',
        value: scoringState.run_manifest_defaults.seed1,
        fieldLabel: 'Run controls',
        onChange: (nextValue) => {
            persistRunManifestDefaults({ seed1: nextValue });
        },
    });
    createScoringNonNegativeIntegerInput(seedRow, {
        labelText: 'Seed 2',
        id: 'scoring_run_defaults_seed2',
        value: scoringState.run_manifest_defaults.seed2,
        fieldLabel: 'Run controls',
        onChange: (nextValue) => {
            persistRunManifestDefaults({ seed2: nextValue });
        },
    });
    runControlsBody.appendChild(seedRow);

    const thresholdRow = document.createElement('div');
    thresholdRow.className = 'environment-vector-row';
    createEnvironmentPlainTextInput(thresholdRow, {
        labelText: 'Production Cut',
        id: 'scoring_run_defaults_production_cut',
        value: scoringState.run_manifest_defaults.production_cut,
        placeholder: '1.0 mm',
        onChange: (nextValue) => {
            persistRunManifestDefaults({ production_cut: nextValue });
        },
    });
    createEnvironmentPlainTextInput(thresholdRow, {
        labelText: 'Hit Threshold',
        id: 'scoring_run_defaults_hit_threshold',
        value: scoringState.run_manifest_defaults.hit_energy_threshold,
        placeholder: '1 eV',
        onChange: (nextValue) => {
            persistRunManifestDefaults({ hit_energy_threshold: nextValue });
        },
    });
    runControlsBody.appendChild(thresholdRow);

    const outputToggleSpecs = [
        {
            key: 'save_hits',
            label: 'Save Hits',
        },
        {
            key: 'save_hit_metadata',
            label: 'Save Hit Metadata',
        },
        {
            key: 'save_particles',
            label: 'Save Particles',
        },
    ];
    outputToggleSpecs.forEach(({ key, label }) => {
        const toggleRow = document.createElement('div');
        toggleRow.className = 'environment-toggle-row';

        const input = document.createElement('input');
        input.type = 'checkbox';
        input.id = `scoring_run_defaults_${key}`;
        input.checked = Boolean(scoringState.run_manifest_defaults[key]);
        input.addEventListener('change', () => {
            persistRunManifestDefaults({ [key]: input.checked });
        });
        toggleRow.appendChild(input);

        const labelEl = document.createElement('label');
        labelEl.htmlFor = input.id;
        labelEl.textContent = label;
        toggleRow.appendChild(labelEl);

        runControlsBody.appendChild(toggleRow);
    });

    (describedRunControls.detailLines || []).forEach((line) => {
        const note = document.createElement('p');
        note.className = 'scoring-note';
        note.textContent = line;
        runControlsBody.appendChild(note);
    });

    const runControlsEventsNote = document.createElement('p');
    runControlsEventsNote.className = 'scoring-note';
    runControlsEventsNote.textContent = 'Event count stays on the main run bar; these saved controls set the scoring-friendly defaults for the rest of the run manifest.';
    runControlsBody.appendChild(runControlsEventsNote);

    runControlsCard.appendChild(runControlsBody);
    scoringPanelRoot.appendChild(runControlsCard);

    const toolbar = document.createElement('div');
    toolbar.className = 'scoring-toolbar';

    const addMeshButton = document.createElement('button');
    addMeshButton.type = 'button';
    addMeshButton.className = 'history-action-btn';
    addMeshButton.textContent = 'Add Scoring Mesh';
    addMeshButton.title = 'Create a new saved world-space box scoring mesh with a default energy_deposit tally.';
    addMeshButton.addEventListener('click', () => {
        if (callbacks.onInspectorPropertyChanged) {
            callbacks.onInspectorPropertyChanged(
                SCORING_OBJECT_TYPE,
                SCORING_OBJECT_ID,
                'state',
                buildScoringStateWithAddedMesh(scoringState),
            );
        }
    });
    toolbar.appendChild(addMeshButton);
    scoringPanelRoot.appendChild(toolbar);

    if (scoringState.scoring_meshes.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'scoring-empty';
        empty.textContent = panelState.empty;
        scoringPanelRoot.appendChild(empty);
        return;
    }

    scoringState.scoring_meshes.forEach((mesh, index) => {
        const described = describeScoringMesh(mesh, scoringState);
        const card = document.createElement('details');
        card.className = 'scoring-card';
        card.open = panelState.defaultExpandedIndex === index;

        const summary = document.createElement('summary');
        summary.className = 'scoring-card-summary';
        summary.title = 'Inspect and revise this saved scoring mesh.';

        const summaryLayout = document.createElement('div');
        summaryLayout.className = 'scoring-card-summary-layout';

        const summaryText = document.createElement('div');
        summaryText.className = 'scoring-card-summary-text';

        const title = document.createElement('div');
        title.className = 'scoring-title';
        title.textContent = described.title;
        summaryText.appendChild(title);

        const summaryLine = document.createElement('div');
        summaryLine.className = 'scoring-summary';
        summaryLine.textContent = described.summary;
        summaryText.appendChild(summaryLine);

        const summaryMeta = document.createElement('div');
        summaryMeta.className = 'scoring-summary-meta';

        const statusBadge = document.createElement('code');
        statusBadge.className = 'scoring-status';
        statusBadge.textContent = described.statusBadge;
        summaryMeta.appendChild(statusBadge);

        const summaryActions = document.createElement('div');
        summaryActions.className = 'scoring-summary-actions';

        const deleteButton = document.createElement('button');
        deleteButton.type = 'button';
        deleteButton.className = 'history-action-btn';
        deleteButton.textContent = 'Delete';
        deleteButton.title = 'Remove this scoring mesh and any tally requests that target it.';
        deleteButton.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            if (!confirmAction(`Delete scoring mesh '${mesh.name}' and its saved tally requests?`)) {
                return;
            }
            persistScoringState(buildScoringStateWithRemovedMesh(scoringState, mesh.mesh_id));
        });
        summaryActions.appendChild(deleteButton);

        summaryMeta.appendChild(summaryActions);
        summaryLayout.appendChild(summaryText);
        summaryLayout.appendChild(summaryMeta);
        summary.appendChild(summaryLayout);
        card.appendChild(summary);

        const body = document.createElement('div');
        body.className = 'scoring-card-body';

        const enabledRow = document.createElement('div');
        enabledRow.className = 'environment-toggle-row';

        const enabledInput = document.createElement('input');
        enabledInput.type = 'checkbox';
        enabledInput.id = `scoring_mesh_enabled_${mesh.mesh_id}`;
        enabledInput.checked = Boolean(mesh.enabled);
        enabledInput.addEventListener('change', () => {
            persistScoringState(replaceScoringMesh(scoringState, mesh.mesh_id, {
                ...mesh,
                enabled: enabledInput.checked,
            }));
        });
        enabledRow.appendChild(enabledInput);

        const enabledLabel = document.createElement('label');
        enabledLabel.htmlFor = enabledInput.id;
        enabledLabel.textContent = 'Mesh Enabled';
        enabledRow.appendChild(enabledLabel);

        body.appendChild(enabledRow);

        const nameRow = document.createElement('div');
        nameRow.className = 'environment-vector-row';
        createEnvironmentPlainTextInput(nameRow, {
            labelText: 'Mesh Name',
            id: `scoring_mesh_name_${mesh.mesh_id}`,
            value: mesh.name,
            placeholder: 'study_mesh',
            onChange: (nextValue) => {
                persistScoringState(replaceScoringMesh(scoringState, mesh.mesh_id, {
                    ...mesh,
                    name: nextValue,
                }));
            },
        });
        body.appendChild(nameRow);

        const centerRow = document.createElement('div');
        centerRow.className = 'environment-vector-row';
        ['x', 'y', 'z'].forEach((axis) => {
            createEnvironmentFieldInput(centerRow, {
                labelText: `Center ${axis.toUpperCase()} (mm)`,
                id: `scoring_mesh_center_${mesh.mesh_id}_${axis}`,
                value: mesh.geometry.center_mm[axis],
                fieldLabel: 'Scoring mesh center',
                onChange: (nextValue) => {
                    persistScoringState(replaceScoringMesh(scoringState, mesh.mesh_id, {
                        ...mesh,
                        geometry: {
                            ...mesh.geometry,
                            center_mm: {
                                ...mesh.geometry.center_mm,
                                [axis]: nextValue,
                            },
                        },
                    }));
                },
            });
        });
        body.appendChild(centerRow);

        const sizeRow = document.createElement('div');
        sizeRow.className = 'environment-vector-row';
        ['x', 'y', 'z'].forEach((axis) => {
            createEnvironmentFieldInput(sizeRow, {
                labelText: `Size ${axis.toUpperCase()} (mm)`,
                id: `scoring_mesh_size_${mesh.mesh_id}_${axis}`,
                value: mesh.geometry.size_mm[axis],
                fieldLabel: 'Scoring mesh size',
                onChange: (nextValue) => {
                    if (nextValue <= 0) {
                        showError(`Scoring mesh size ${axis.toUpperCase()} must be greater than zero.`);
                        return;
                    }
                    persistScoringState(replaceScoringMesh(scoringState, mesh.mesh_id, {
                        ...mesh,
                        geometry: {
                            ...mesh.geometry,
                            size_mm: {
                                ...mesh.geometry.size_mm,
                                [axis]: nextValue,
                            },
                        },
                    }));
                },
            });
        });
        body.appendChild(sizeRow);

        const binsRow = document.createElement('div');
        binsRow.className = 'environment-vector-row';
        ['x', 'y', 'z'].forEach((axis) => {
            createScoringIntegerInput(binsRow, {
                labelText: `Bins ${axis.toUpperCase()}`,
                id: `scoring_mesh_bins_${mesh.mesh_id}_${axis}`,
                value: mesh.bins[axis],
                fieldLabel: 'Scoring mesh bins',
                onChange: (nextValue) => {
                    persistScoringState(replaceScoringMesh(scoringState, mesh.mesh_id, {
                        ...mesh,
                        bins: {
                            ...mesh.bins,
                            [axis]: nextValue,
                        },
                    }));
                },
            });
        });
        body.appendChild(binsRow);

        const tallyLabel = document.createElement('div');
        tallyLabel.className = 'scoring-field-label';
        tallyLabel.textContent = 'Tallies';
        body.appendChild(tallyLabel);

        const quantityGrid = document.createElement('div');
        quantityGrid.className = 'scoring-quantity-grid';

        SUPPORTED_SCORING_TALLY_QUANTITIES.forEach((quantity) => {
            const quantityWrap = document.createElement('label');
            quantityWrap.className = 'scoring-quantity-option';
            quantityWrap.title = RUNTIME_READY_SCORING_QUANTITIES.includes(quantity)
                ? 'Saved in project state and supported by the current scoring-mesh runtime slice.'
                : 'Saved in project state now; runtime artifact generation for this quantity is planned for a later tally task.';

            const quantityInput = document.createElement('input');
            quantityInput.type = 'checkbox';
            quantityInput.checked = isMeshTallyEnabled(scoringState, mesh.mesh_id, quantity);
            quantityInput.addEventListener('change', () => {
                persistScoringState(setMeshTallyEnabled(scoringState, mesh, quantity, quantityInput.checked));
            });
            quantityWrap.appendChild(quantityInput);

            const quantityText = document.createElement('span');
            quantityText.textContent = formatScoringQuantityLabel(quantity);
            quantityWrap.appendChild(quantityText);

            if (RUNTIME_READY_SCORING_QUANTITIES.includes(quantity)) {
                const runtimeBadge = document.createElement('code');
                runtimeBadge.className = 'scoring-runtime-badge';
                runtimeBadge.textContent = 'runtime';
                quantityWrap.appendChild(runtimeBadge);
            }

            quantityGrid.appendChild(quantityWrap);
        });
        body.appendChild(quantityGrid);

        const note = document.createElement('p');
        note.className = 'scoring-note';
        note.textContent = 'Scoring meshes are fixed to world-space box meshes in this first UI slice. energy_deposit and n_of_step tallies now emit runtime artifacts; other saved tallies remain inspectable here until later runtime slices land.';
        body.appendChild(note);

        card.appendChild(body);
        scoringPanelRoot.appendChild(card);
    });
}

function renderEnvironmentFieldCard(parent, {
    title,
    summary,
    enabledInputId,
    enabled,
    onEnabledChange,
    fieldLabel,
    targetInputId = null,
    targetValue = null,
    targetPlaceholder = '',
    onTargetChange = null,
    vectorInputPrefix,
    vectorValues,
    vectorAxes,
    vectorPropertyBase,
    vectorUnitLabel,
    objectType,
    objectId,
    noteText = '',
}) {
    const card = document.createElement('div');
    card.className = 'environment-field-card';

    const titleEl = document.createElement('div');
    titleEl.className = 'environment-field-title';
    titleEl.textContent = title;
    card.appendChild(titleEl);

    const summaryEl = document.createElement('p');
    summaryEl.className = 'environment-summary';
    summaryEl.textContent = summary;
    card.appendChild(summaryEl);

    const toggleRow = document.createElement('div');
    toggleRow.className = 'environment-toggle-row';

    const enabledInput = document.createElement('input');
    enabledInput.type = 'checkbox';
    enabledInput.id = enabledInputId;
    enabledInput.checked = Boolean(enabled);
    enabledInput.addEventListener('change', () => {
        onEnabledChange(enabledInput.checked);
    });

    const enabledLabel = document.createElement('label');
    enabledLabel.htmlFor = enabledInput.id;
    enabledLabel.textContent = 'Enabled';

    toggleRow.appendChild(enabledInput);
    toggleRow.appendChild(enabledLabel);
    card.appendChild(toggleRow);

    if (targetInputId) {
        const targetRow = document.createElement('div');
        targetRow.className = 'environment-vector-row';
        createEnvironmentTextInput(targetRow, {
            labelText: 'Target Volumes',
            id: targetInputId,
            value: targetValue,
            placeholder: targetPlaceholder,
            onChange: onTargetChange,
        });
        card.appendChild(targetRow);
    }

    const vectorRow = document.createElement('div');
    vectorRow.className = 'environment-vector-row';
    vectorAxes.forEach((axis) => {
        createEnvironmentFieldInput(vectorRow, {
            labelText: `${axis.toUpperCase()} (${vectorUnitLabel})`,
            id: `${vectorInputPrefix}_${axis}`,
            value: vectorValues[axis],
            fieldLabel,
            onChange: (nextValue) => {
                callbacks.onInspectorPropertyChanged(
                    objectType,
                    objectId,
                    `${vectorPropertyBase}.${axis}`,
                    nextValue
                );
            },
        });
    });
    card.appendChild(vectorRow);

    const note = document.createElement('p');
    note.className = 'environment-note';
    note.textContent = noteText;
    card.appendChild(note);

    parent.appendChild(card);
}

function renderEnvironmentRegionCard(parent, {
    title,
    summary,
    enabledInputId,
    enabled,
    onEnabledChange,
    fieldLabel,
    regionNameInputId,
    regionNameValue,
    onRegionNameChange,
    targetInputId,
    targetValue,
    targetPlaceholder = '',
    onTargetChange,
    numericFields = [],
    objectType,
    objectId,
    noteText = '',
}) {
    const card = document.createElement('div');
    card.className = 'environment-field-card';

    const titleEl = document.createElement('div');
    titleEl.className = 'environment-field-title';
    titleEl.textContent = title;
    card.appendChild(titleEl);

    const summaryEl = document.createElement('p');
    summaryEl.className = 'environment-summary';
    summaryEl.textContent = summary;
    card.appendChild(summaryEl);

    const toggleRow = document.createElement('div');
    toggleRow.className = 'environment-toggle-row';

    const enabledInput = document.createElement('input');
    enabledInput.type = 'checkbox';
    enabledInput.id = enabledInputId;
    enabledInput.checked = Boolean(enabled);
    enabledInput.addEventListener('change', () => {
        onEnabledChange(enabledInput.checked);
    });

    const enabledLabel = document.createElement('label');
    enabledLabel.htmlFor = enabledInput.id;
    enabledLabel.textContent = 'Enabled';

    toggleRow.appendChild(enabledInput);
    toggleRow.appendChild(enabledLabel);
    card.appendChild(toggleRow);

    const regionRow = document.createElement('div');
    regionRow.className = 'environment-vector-row';
    createEnvironmentPlainTextInput(regionRow, {
        labelText: 'Region Name',
        id: regionNameInputId,
        value: regionNameValue,
        placeholder: 'airpet_region',
        onChange: onRegionNameChange,
    });
    card.appendChild(regionRow);

    const targetRow = document.createElement('div');
    targetRow.className = 'environment-vector-row';
    createEnvironmentTextInput(targetRow, {
        labelText: 'Target Volumes',
        id: targetInputId,
        value: targetValue,
        placeholder: targetPlaceholder,
        onChange: onTargetChange,
    });
    card.appendChild(targetRow);

    const numericRow = document.createElement('div');
    numericRow.className = 'environment-vector-row';
    numericFields.forEach((field) => {
        createEnvironmentFieldInput(numericRow, {
            labelText: `${field.labelText} (${field.unitLabel})`,
            id: field.id,
            value: field.value,
            fieldLabel,
            onChange: (nextValue) => {
                callbacks.onInspectorPropertyChanged(
                    objectType,
                    objectId,
                    field.propertyPath,
                    nextValue
                );
            },
        });
    });
    card.appendChild(numericRow);

    const note = document.createElement('p');
    note.className = 'environment-note';
    note.textContent = noteText;
    card.appendChild(note);

    parent.appendChild(card);
}

function renderEnvironmentPanel(projectState) {
    if (!environmentPanelRoot) return;

    environmentPanelRoot.innerHTML = '';

    if (!projectState) {
        const empty = document.createElement('p');
        empty.textContent = 'No project loaded.';
        environmentPanelRoot.appendChild(empty);
        return;
    }

    const globalMagneticField = normalizeGlobalMagneticFieldState(
        projectState?.environment?.global_uniform_magnetic_field
    );
    renderEnvironmentFieldCard(environmentPanelRoot, {
        title: 'Global Magnetic Field',
        summary: formatGlobalMagneticFieldSummary(globalMagneticField),
        enabledInputId: 'global_magnetic_field_enabled',
        enabled: globalMagneticField.enabled,
        fieldLabel: 'Global magnetic field',
        objectType: GLOBAL_UNIFORM_MAGNETIC_FIELD_OBJECT_TYPE,
        objectId: GLOBAL_UNIFORM_MAGNETIC_FIELD_OBJECT_ID,
        vectorInputPrefix: 'global_magnetic_field',
        vectorValues: globalMagneticField.field_vector_tesla,
        vectorAxes: GLOBAL_UNIFORM_MAGNETIC_FIELD_VECTOR_AXES,
        vectorPropertyBase: 'field_vector_tesla',
        vectorUnitLabel: 'T',
        onEnabledChange: (nextValue) => {
            callbacks.onInspectorPropertyChanged(
                GLOBAL_UNIFORM_MAGNETIC_FIELD_OBJECT_TYPE,
                GLOBAL_UNIFORM_MAGNETIC_FIELD_OBJECT_ID,
                'enabled',
                nextValue
            );
        },
        noteText: 'Saved in project state and passed to Geant4 runtime initialization.',
    });

    const globalElectricField = normalizeGlobalElectricFieldState(
        projectState?.environment?.global_uniform_electric_field
    );
    renderEnvironmentFieldCard(environmentPanelRoot, {
        title: 'Global Electric Field',
        summary: formatGlobalElectricFieldSummary(globalElectricField),
        enabledInputId: 'global_electric_field_enabled',
        enabled: globalElectricField.enabled,
        fieldLabel: 'Global electric field',
        objectType: GLOBAL_UNIFORM_ELECTRIC_FIELD_OBJECT_TYPE,
        objectId: GLOBAL_UNIFORM_ELECTRIC_FIELD_OBJECT_ID,
        vectorInputPrefix: 'global_electric_field',
        vectorValues: globalElectricField.field_vector_volt_per_meter,
        vectorAxes: GLOBAL_UNIFORM_ELECTRIC_FIELD_VECTOR_AXES,
        vectorPropertyBase: 'field_vector_volt_per_meter',
        vectorUnitLabel: 'V/m',
        onEnabledChange: (nextValue) => {
            callbacks.onInspectorPropertyChanged(
                GLOBAL_UNIFORM_ELECTRIC_FIELD_OBJECT_TYPE,
                GLOBAL_UNIFORM_ELECTRIC_FIELD_OBJECT_ID,
                'enabled',
                nextValue
            );
        },
        noteText: 'Saved in project state and passed to Geant4 runtime initialization.',
    });

    const localMagneticField = normalizeLocalMagneticFieldState(
        projectState?.environment?.local_uniform_magnetic_field
    );
    renderEnvironmentFieldCard(environmentPanelRoot, {
        title: 'Local Magnetic Field',
        summary: formatLocalMagneticFieldSummary(localMagneticField),
        enabledInputId: 'local_magnetic_field_enabled',
        enabled: localMagneticField.enabled,
        fieldLabel: 'Local magnetic field',
        objectType: LOCAL_UNIFORM_MAGNETIC_FIELD_OBJECT_TYPE,
        objectId: LOCAL_UNIFORM_MAGNETIC_FIELD_OBJECT_ID,
        targetInputId: 'local_magnetic_field_target_volumes',
        targetValue: localMagneticField.target_volume_names.join(', '),
        targetPlaceholder: 'box_LV, detector_LV',
        vectorInputPrefix: 'local_magnetic_field',
        vectorValues: localMagneticField.field_vector_tesla,
        vectorAxes: LOCAL_UNIFORM_MAGNETIC_FIELD_VECTOR_AXES,
        vectorPropertyBase: 'field_vector_tesla',
        vectorUnitLabel: 'T',
        onEnabledChange: (nextValue) => {
            callbacks.onInspectorPropertyChanged(
                LOCAL_UNIFORM_MAGNETIC_FIELD_OBJECT_TYPE,
                LOCAL_UNIFORM_MAGNETIC_FIELD_OBJECT_ID,
                'enabled',
                nextValue
            );
        },
        onTargetChange: (nextValue) => {
            callbacks.onInspectorPropertyChanged(
                LOCAL_UNIFORM_MAGNETIC_FIELD_OBJECT_TYPE,
                LOCAL_UNIFORM_MAGNETIC_FIELD_OBJECT_ID,
                'target_volume_names',
                nextValue
            );
        },
        noteText: 'Targets are comma-separated logical volume names.',
    });

    const localElectricField = normalizeLocalElectricFieldState(
        projectState?.environment?.local_uniform_electric_field
    );
    renderEnvironmentFieldCard(environmentPanelRoot, {
        title: 'Local Electric Field',
        summary: formatLocalElectricFieldSummary(localElectricField),
        enabledInputId: 'local_electric_field_enabled',
        enabled: localElectricField.enabled,
        fieldLabel: 'Local electric field',
        objectType: LOCAL_UNIFORM_ELECTRIC_FIELD_OBJECT_TYPE,
        objectId: LOCAL_UNIFORM_ELECTRIC_FIELD_OBJECT_ID,
        targetInputId: 'local_electric_field_target_volumes',
        targetValue: localElectricField.target_volume_names.join(', '),
        targetPlaceholder: 'box_LV, detector_LV',
        vectorInputPrefix: 'local_electric_field',
        vectorValues: localElectricField.field_vector_volt_per_meter,
        vectorAxes: LOCAL_UNIFORM_ELECTRIC_FIELD_VECTOR_AXES,
        vectorPropertyBase: 'field_vector_volt_per_meter',
        vectorUnitLabel: 'V/m',
        onEnabledChange: (nextValue) => {
            callbacks.onInspectorPropertyChanged(
                LOCAL_UNIFORM_ELECTRIC_FIELD_OBJECT_TYPE,
                LOCAL_UNIFORM_ELECTRIC_FIELD_OBJECT_ID,
                'enabled',
                nextValue
            );
        },
        onTargetChange: (nextValue) => {
            callbacks.onInspectorPropertyChanged(
                LOCAL_UNIFORM_ELECTRIC_FIELD_OBJECT_TYPE,
                LOCAL_UNIFORM_ELECTRIC_FIELD_OBJECT_ID,
                'target_volume_names',
                nextValue
            );
        },
        noteText: 'Targets are comma-separated logical volume names.',
    });

    const regionCutsAndLimits = normalizeRegionCutsAndLimitsState(
        projectState?.environment?.region_cuts_and_limits
    );
    renderEnvironmentRegionCard(environmentPanelRoot, {
        title: 'Region Cuts and Limits',
        summary: formatRegionCutsAndLimitsSummary(regionCutsAndLimits),
        enabledInputId: 'region_cuts_and_limits_enabled',
        enabled: regionCutsAndLimits.enabled,
        fieldLabel: 'Region cuts and limits',
        regionNameInputId: 'region_cuts_and_limits_region_name',
        regionNameValue: regionCutsAndLimits.region_name,
        onRegionNameChange: (nextValue) => {
            callbacks.onInspectorPropertyChanged(
                REGION_CUTS_AND_LIMITS_OBJECT_TYPE,
                REGION_CUTS_AND_LIMITS_OBJECT_ID,
                'region_name',
                nextValue
            );
        },
        targetInputId: 'region_cuts_and_limits_target_volumes',
        targetValue: regionCutsAndLimits.target_volume_names.join(', '),
        targetPlaceholder: 'tracker_region_LV, absorber_LV',
        onTargetChange: (nextValue) => {
            callbacks.onInspectorPropertyChanged(
                REGION_CUTS_AND_LIMITS_OBJECT_TYPE,
                REGION_CUTS_AND_LIMITS_OBJECT_ID,
                'target_volume_names',
                nextValue
            );
        },
        numericFields: [
            {
                labelText: 'Production Cut',
                id: 'region_cuts_and_limits_production_cut_mm',
                value: regionCutsAndLimits.production_cut_mm,
                propertyPath: 'production_cut_mm',
                unitLabel: 'mm',
            },
            {
                labelText: 'Max Step',
                id: 'region_cuts_and_limits_max_step_mm',
                value: regionCutsAndLimits.max_step_mm,
                propertyPath: 'max_step_mm',
                unitLabel: 'mm',
            },
            {
                labelText: 'Max Track Length',
                id: 'region_cuts_and_limits_max_track_length_mm',
                value: regionCutsAndLimits.max_track_length_mm,
                propertyPath: 'max_track_length_mm',
                unitLabel: 'mm',
            },
            {
                labelText: 'Max Time',
                id: 'region_cuts_and_limits_max_time_ns',
                value: regionCutsAndLimits.max_time_ns,
                propertyPath: 'max_time_ns',
                unitLabel: 'ns',
            },
            {
                labelText: 'Min Kinetic Energy',
                id: 'region_cuts_and_limits_min_kinetic_energy_mev',
                value: regionCutsAndLimits.min_kinetic_energy_mev,
                propertyPath: 'min_kinetic_energy_mev',
                unitLabel: 'MeV',
            },
            {
                labelText: 'Min Range',
                id: 'region_cuts_and_limits_min_range_mm',
                value: regionCutsAndLimits.min_range_mm,
                propertyPath: 'min_range_mm',
                unitLabel: 'mm',
            },
        ],
        objectType: REGION_CUTS_AND_LIMITS_OBJECT_TYPE,
        objectId: REGION_CUTS_AND_LIMITS_OBJECT_ID,
        noteText: 'Production cuts use mm; user limits use mm, ns, and MeV internal units.',
    });
}

function renderCadImportsPanel(projectState) {
    if (!cadImportsPanelRoot) return;

    cadImportsPanelRoot.innerHTML = '';

    const cadImports = Array.isArray(projectState?.cad_imports)
        ? projectState.cad_imports.filter((entry) => entry && typeof entry === 'object')
        : [];

    setCadImportsAccordionVisibility(cadImports.length > 0);

    if (cadImports.length === 0) {
        return;
    }

    const intro = document.createElement('p');
    intro.className = 'cad-imports-intro';
    intro.textContent = 'Saved provenance records for imported STEP subsystems. Reimport from a revised STEP file to replace the matching import in place.';
    cadImportsPanelRoot.appendChild(intro);

    cadImports.forEach((rawRecord, index) => {
        const described = describeCadImportRecord(rawRecord);
        const selectionContext = described.selectionContext || buildCadImportSelectionContext(rawRecord);
        const batchContext = described.batchContext || buildCadImportBatchContext(rawRecord);
        const card = document.createElement('details');
        card.className = 'cad-import-card';
        card.open = cadImports.length === 1 || index === cadImports.length - 1;

        const summary = document.createElement('summary');
        summary.className = 'cad-import-card-summary';
        summary.title = 'Inspect this imported CAD provenance record.';

        const summaryText = document.createElement('div');
        summaryText.className = 'cad-import-card-summary-text';

        const title = document.createElement('div');
        title.className = 'cad-import-title';
        title.textContent = described.title;
        summaryText.appendChild(title);

        const summaryLine = document.createElement('div');
        summaryLine.className = 'cad-import-summary';
        summaryLine.textContent = described.summary;
        summaryText.appendChild(summaryLine);

        const idBadge = document.createElement('code');
        idBadge.className = 'cad-import-id';
        idBadge.textContent = described.reimportContext.reimportTargetImportId;

        summary.appendChild(summaryText);
        summary.appendChild(idBadge);
        card.appendChild(summary);

        const body = document.createElement('div');
        body.className = 'cad-import-card-body';

        described.detailRows.forEach((row) => {
            createReadOnlyProperty(body, `${row.label}:`, row.value);
        });

        const actions = document.createElement('div');
        actions.className = 'cad-import-actions';

        if (selectionContext.selectionIds.length > 0) {
            const selectButton = document.createElement('button');
            selectButton.type = 'button';
            selectButton.className = 'history-action-btn';
            selectButton.textContent = 'Select Top-Level';
            selectButton.title = 'Select the top-level imported placement(s) in the hierarchy.';
            selectButton.addEventListener('click', (event) => {
                event.stopPropagation();
                if (callbacks.onSelectHierarchyItems) {
                    callbacks.onSelectHierarchyItems(selectionContext.selectionIds);
                }
            });
            actions.appendChild(selectButton);
        }

        if (batchContext.hasLogicalVolumes) {
            const materialButton = document.createElement('button');
            materialButton.type = 'button';
            materialButton.className = 'history-action-btn';
            materialButton.textContent = 'Set Material...';
            materialButton.title = 'Apply one material to all imported logical volumes in this STEP record.';
            materialButton.addEventListener('click', (event) => {
                event.stopPropagation();
                if (callbacks.onCadImportBatchActionClicked) {
                    callbacks.onCadImportBatchActionClicked('material', rawRecord);
                }
            });
            actions.appendChild(materialButton);

            const sensitiveButton = document.createElement('button');
            sensitiveButton.type = 'button';
            sensitiveButton.className = 'history-action-btn';
            sensitiveButton.textContent = 'Mark Sensitive';
            sensitiveButton.title = 'Mark all imported logical volumes in this STEP record as sensitive.';
            sensitiveButton.addEventListener('click', (event) => {
                event.stopPropagation();
                if (callbacks.onCadImportBatchActionClicked) {
                    callbacks.onCadImportBatchActionClicked('sensitive', rawRecord);
                }
            });
            actions.appendChild(sensitiveButton);
        }

        const reimportButton = document.createElement('button');
        reimportButton.type = 'button';
        reimportButton.className = 'history-action-btn';
        reimportButton.textContent = 'Reimport STEP...';
        reimportButton.title = 'Choose a replacement STEP file and open the supported reimport flow.';

        const reimportFileInput = document.createElement('input');
        reimportFileInput.type = 'file';
        reimportFileInput.accept = '.step,.stp';
        reimportFileInput.style.display = 'none';
        reimportFileInput.addEventListener('change', (event) => {
            const file = event.target.files?.[0];
            event.target.value = '';
            if (file && callbacks.onReimportStepClicked) {
                callbacks.onReimportStepClicked(file, rawRecord);
            }
        });

        reimportButton.addEventListener('click', (event) => {
            event.stopPropagation();
            reimportFileInput.click();
        });

        actions.appendChild(reimportButton);
        actions.appendChild(reimportFileInput);
        body.appendChild(actions);

        if (batchContext.hasLogicalVolumes) {
            const batchNote = document.createElement('p');
            batchNote.className = 'cad-import-note';
            batchNote.textContent = `Batch helpers apply to ${batchContext.logicalVolumeSummary}.`;
            body.appendChild(batchNote);
        }

        const note = document.createElement('p');
        note.className = 'cad-import-note';
        note.textContent = 'The reimport modal will inherit the saved grouping and placement options for this import.';
        body.appendChild(note);

        card.appendChild(body);
        cadImportsPanelRoot.appendChild(card);
    });
}

function renderDetectorFeatureGeneratorsPanel(projectState) {
    if (!detectorFeatureGeneratorsPanelRoot) return;

    detectorFeatureGeneratorsPanelRoot.innerHTML = '';

    const panelState = describeDetectorFeatureGeneratorPanelState(projectState);
    const generators = Array.isArray(projectState?.detector_feature_generators)
        ? projectState.detector_feature_generators.filter((entry) => entry && typeof entry === 'object')
        : [];

    const intro = document.createElement('p');
    intro.className = 'detector-feature-generators-intro';
    intro.textContent = panelState.intro;
    detectorFeatureGeneratorsPanelRoot.appendChild(intro);

    if (panelState.hint) {
        const launchHint = document.createElement('p');
        launchHint.className = 'detector-feature-note';
        launchHint.textContent = panelState.hint;
        detectorFeatureGeneratorsPanelRoot.appendChild(launchHint);
    }

    if (generators.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'detector-feature-generators-empty';
        empty.textContent = panelState.empty;
        detectorFeatureGeneratorsPanelRoot.appendChild(empty);
        return;
    }

    generators.forEach((rawEntry, index) => {
        const described = describeDetectorFeatureGenerator(rawEntry, projectState);
        const selectionContext = buildDetectorFeatureGeneratorSelectionContext(rawEntry, projectState);
        const card = document.createElement('details');
        card.className = 'detector-feature-card';
        card.open = panelState.defaultExpandedIndex === index;

        const summary = document.createElement('summary');
        summary.className = 'detector-feature-card-summary';
        summary.title = 'Inspect this detector-feature-generator contract.';

        const summaryLayout = document.createElement('div');
        summaryLayout.className = 'detector-feature-card-summary-layout';

        const summaryText = document.createElement('div');
        summaryText.className = 'detector-feature-card-summary-text';

        const title = document.createElement('div');
        title.className = 'detector-feature-title';
        title.textContent = described.title;
        summaryText.appendChild(title);

        const summaryLine = document.createElement('div');
        summaryLine.className = 'detector-feature-summary';
        summaryLine.textContent = described.summary;
        summaryText.appendChild(summaryLine);

        const statusBadge = document.createElement('code');
        statusBadge.className = 'detector-feature-status';
        statusBadge.textContent = described.statusBadge;

        const summaryMeta = document.createElement('div');
        summaryMeta.className = 'detector-feature-summary-meta';
        summaryMeta.appendChild(statusBadge);

        const summaryActions = document.createElement('div');
        summaryActions.className = 'detector-feature-summary-actions';

        if (selectionContext.selectionIds.length > 0) {
            const selectButton = document.createElement('button');
            selectButton.type = 'button';
            selectButton.className = 'history-action-btn';
            selectButton.textContent = selectionContext.buttonLabel;
            selectButton.title = selectionContext.buttonTitle;
            selectButton.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                if (callbacks.onSelectHierarchyItems) {
                    callbacks.onSelectHierarchyItems(selectionContext.selectionIds);
                }
            });
            summaryActions.appendChild(selectButton);
        }

        const editButton = document.createElement('button');
        editButton.type = 'button';
        editButton.className = 'history-action-btn';
        editButton.textContent = 'Edit...';
        editButton.title = 'Revise the saved detector-feature-generator parameters.';
        editButton.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            if (callbacks.onEditDetectorFeatureGeneratorClicked) {
                callbacks.onEditDetectorFeatureGeneratorClicked(rawEntry);
            }
        });
        summaryActions.appendChild(editButton);

        const regenerateButton = document.createElement('button');
        regenerateButton.type = 'button';
        regenerateButton.className = 'history-action-btn';
        regenerateButton.textContent = 'Regenerate';
        regenerateButton.title = 'Re-run the saved generator contract against the current target geometry.';
        regenerateButton.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            if (callbacks.onRealizeDetectorFeatureGeneratorClicked) {
                callbacks.onRealizeDetectorFeatureGeneratorClicked(rawEntry);
            }
        });
        summaryActions.appendChild(regenerateButton);

        summaryMeta.appendChild(summaryActions);
        summaryLayout.appendChild(summaryText);
        summaryLayout.appendChild(summaryMeta);
        summary.appendChild(summaryLayout);
        card.appendChild(summary);

        const body = document.createElement('div');
        body.className = 'detector-feature-card-body';

        described.detailRows.forEach((row) => {
            createReadOnlyProperty(body, `${row.label}:`, row.value);
        });

        card.appendChild(body);
        detectorFeatureGeneratorsPanelRoot.appendChild(card);
    });
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
        updateHierarchyToolButtons(null);
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
    cadImportsPanelRoot = document.getElementById('cad_imports_panel_root');
    detectorFeatureGeneratorsPanelRoot = document.getElementById('detector_feature_generators_panel_root');
    scoringPanelRoot = document.getElementById('scoring_panel_root');

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
    renderEnvironmentPanel(projectState);
    renderCadImportsPanel(projectState);
    renderDetectorFeatureGeneratorsPanel(projectState);
    renderScoringPanel(projectState);
    updateHierarchyToolButtons(projectState);

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

function updateHierarchyToolButtons(projectState) {
    const launchState = describeDetectorFeatureGeneratorLaunchState(projectState);
    if (createDetectorFeatureGeneratorButton) {
        createDetectorFeatureGeneratorButton.disabled = !launchState.canLaunch;
        createDetectorFeatureGeneratorButton.title = launchState.title;
    }

    if (createRingArrayButton) {
        const hasProjectState = Boolean(projectState);
        createRingArrayButton.disabled = !hasProjectState;
        createRingArrayButton.title = hasProjectState
            ? 'Create a detector ring array from Hierarchy > + Tools.'
            : 'Open or create a project before launching the ring-array tool.';
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
    renderEnvironmentPanel(null);
    renderCadImportsPanel(null);
    renderDetectorFeatureGeneratorsPanel(null);
    renderScoringPanel(null);
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


export function getAiBackendDiagnosticForModel(modelValue = null) {
    const selectedModel = modelValue || getAiSelectedModel();
    const backendId = getLocalBackendIdForModel(selectedModel);
    if (!backendId) return null;
    return aiBackendDiagnosticsById[backendId] || null;
}

export function upsertAiBackendDiagnostic(diagnostic) {
    if (!diagnostic || typeof diagnostic !== 'object' || !diagnostic.backend_id) return;

    const backendId = diagnostic.backend_id;
    aiBackendDiagnosticsById[backendId] = diagnostic;

    if (aiModelSelect) {
        const options = aiModelSelect.querySelectorAll(`option[data-backend-id="${backendId}"]`);
        options.forEach(option => {
            const rawModelName = String(option.value || '').split('::').slice(1).join('::') || option.textContent;
            option.textContent = formatLocalModelOptionLabel(rawModelName, diagnostic);
            option.title = buildLocalBackendTooltip(backendId, diagnostic);
            option.dataset.readinessStatus = getReadinessLabel(diagnostic.status);
        });
    }

    updateAiBackendStatus();
}

export function updateAiBackendStatus(modelValue = null) {
    if (!aiBackendStatusEl) return;

    const selectedModel = modelValue || getAiSelectedModel();
    const chip = buildBackendStatusChip(selectedModel, aiBackendDiagnosticsById);

    applyBackendStatusChip(aiBackendStatusEl, chip);
}

/**
 * Populates the AI model selector dropdown with grouped options.
 * @param {object} models - An object like {ollama: [...], gemini: [...]}.
 * @param {object|Array<object>|null} localBackendDiagnostics - Local backend readiness diagnostics.
 */
export function populateAiModelSelector(models, localBackendDiagnostics = null) {
    if (!aiModelSelect) return;

    if (localBackendDiagnostics !== null) {
        aiBackendDiagnosticsById = normalizeAiBackendDiagnostics(localBackendDiagnostics);
    }

    // Remove all existing model groups before adding new ones.
    const existingGroups = aiModelSelect.querySelectorAll('.model-group, .no-models-option');
    existingGroups.forEach(group => group.remove());

    const createGroup = (label, modelList, valuePrefix = null, backendId = null) => {
        if (modelList && modelList.length > 0) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = label;
            optgroup.classList.add('model-group'); // <-- Add a class for easy removal

            modelList.forEach(modelName => {
                const option = document.createElement('option');
                option.value = valuePrefix ? `${valuePrefix}::${modelName}` : modelName;

                const prettyName = modelName.startsWith('models/') ? `${modelName.split('/')[1]}` : modelName;

                if (backendId) {
                    const diagnostic = aiBackendDiagnosticsById[backendId] || null;
                    option.textContent = formatLocalModelOptionLabel(prettyName, diagnostic);
                    option.title = buildLocalBackendTooltip(backendId, diagnostic);
                    option.dataset.backendId = backendId;
                    option.dataset.readinessStatus = getReadinessLabel(diagnostic?.status);
                } else {
                    option.textContent = prettyName;
                }

                optgroup.appendChild(option);
            });
            aiModelSelect.appendChild(optgroup);
        }
    };

    createGroup("Gemini Models", models.gemini);
    createGroup("Ollama Models", models.ollama);
    createGroup("llama.cpp Models", models.llama_cpp, "llama_cpp", "llama_cpp");
    createGroup("LM Studio Models", models.lm_studio, "lm_studio", "lm_studio");

    // If no models were added at all
    const hasGemini = models.gemini && models.gemini.length > 0;
    const hasOllama = models.ollama && models.ollama.length > 0;
    const hasLlamaCpp = models.llama_cpp && models.llama_cpp.length > 0;
    const hasLMStudio = models.lm_studio && models.lm_studio.length > 0;

    if (!hasGemini && !hasOllama && !hasLlamaCpp && !hasLMStudio) {
        const option = document.createElement('option');
        option.textContent = "No AI models found";
        option.disabled = true;
        option.classList.add('no-models-option'); // <-- Add class for removal
        aiModelSelect.appendChild(option);
    } else {
        // --- Set Default Model Preference ---
        // Prioritize user request, then gemini-3-flash-preview, then gemini-2.5-pro, then gemini-2.5-flash
        const preferredModels = ['gemini-3-flash-preview', 'gemini-2.5-pro', 'gemini-2.5-flash'];

        for (const pref of preferredModels) {
            // Check if any option value contains the preferred model name
            const options = Array.from(aiModelSelect.options);
            const found = options.find(opt => opt.value.includes(pref));
            if (found) {
                aiModelSelect.value = found.value;
                break;
            }
        }

        // Notify listeners (e.g., AI context stats widget) that model list/selection changed.
        aiModelSelect.dispatchEvent(new Event('change'));
    }

    updateAiBackendStatus();
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
    if (preflightButton) preflightButton.disabled = isRunning;
    simEventsInput.disabled = isRunning;
    simOptionsButton.disabled = isRunning;
}

export function setPreflightState(state) {
    if (!preflightButton) return;
    const isRunning = state === 'running';
    preflightButton.disabled = isRunning;
    preflightButton.textContent = isRunning ? '🧪 Preflight...' : '🧪 Preflight';
}

function formatPreflightScopeLabel(scope) {
    if (!scope || !scope.type || !scope.name) return '';
    if (scope.type === 'logical_volume') return `LV "${scope.name}"`;
    if (scope.type === 'assembly') return `Assembly "${scope.name}"`;
    return `${scope.type} "${scope.name}"`;
}

function resolveScopedPreflightFallbackHint(details = {}) {
    if (!details?.preferScopedSelection || details?.usedScopedPreflight) return '';

    if (details?.scopedFallbackError) {
        return 'Scoped preflight route failed; showing full-geometry diagnostics instead.';
    }

    const reason = details?.scopedSelectionReason;
    if (reason === 'no_selection') {
        return 'No geometry selection detected; showing full-geometry diagnostics.';
    }
    if (reason === 'selection_not_scopeable') {
        return 'Current selection is not scopeable (choose an LV, assembly, or PV linked to one).';
    }
    if (reason === 'ambiguous_selection') {
        const count = Number(details?.scopedSelectionCandidateCount || 0);
        if (count > 1) {
            return `Selection resolves to ${count} scope targets; showing full-geometry diagnostics.`;
        }
        return 'Selection resolves to multiple scope targets; showing full-geometry diagnostics.';
    }

    return 'Scoped preflight was not applied; showing full-geometry diagnostics.';
}

function updatePreflightIssueToggleState({ showToggle = false, activeMode = 'global' } = {}) {
    if (preflightIssueToggleRow) {
        preflightIssueToggleRow.style.display = showToggle ? 'flex' : 'none';
    }
    if (preflightShowScopeIssuesBtn) {
        preflightShowScopeIssuesBtn.classList.toggle('active', showToggle && activeMode === 'scoped');
        preflightShowScopeIssuesBtn.disabled = !showToggle;
    }
    if (preflightShowGlobalIssuesBtn) {
        preflightShowGlobalIssuesBtn.classList.toggle('active', activeMode === 'global');
    }
}

function updatePreflightBucketFilterState({ showRow = false, activeBucket = 'all' } = {}) {
    if (preflightScopeBucketFilterRow) {
        preflightScopeBucketFilterRow.style.display = showRow ? 'flex' : 'none';
    }

    const bucketButtons = [
        { button: preflightBucketAllBtn, value: 'all' },
        { button: preflightBucketScopeOnlyBtn, value: 'scope_only' },
        { button: preflightBucketOutsideOnlyBtn, value: 'outside_scope_only' },
        { button: preflightBucketSharedBtn, value: 'shared' },
    ];

    bucketButtons.forEach(({ button, value }) => {
        if (!button) return;
        button.classList.toggle('active', showRow && activeBucket === value);
        button.disabled = !showRow;
    });
}

function normalizePreflightIssueCode(value) {
    return String(value || '').trim();
}

function renderPreflightIssueCodeChips({ showRow = false, chips = [], activeCode = '' } = {}) {
    if (!preflightIssueCodeChipRow) return;

    preflightIssueCodeChipRow.innerHTML = '';
    preflightIssueCodeChipRow.style.display = showRow ? 'flex' : 'none';

    if (!showRow || chips.length === 0) {
        return;
    }

    const label = document.createElement('span');
    label.className = 'preflight_issue_code_chip_label';
    label.textContent = 'Issue codes:';
    preflightIssueCodeChipRow.appendChild(label);

    chips.forEach((chip) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'preflight_toggle_btn preflight_issue_code_chip';
        button.classList.toggle('active', activeCode === chip.code);
        button.textContent = `${chip.code} (${chip.count})`;

        if (chip.bucketLabel) {
            button.title = `${chip.bucketLabel} (${chip.count})`;
        }

        button.addEventListener('click', () => {
            preflightScopedIssueCodeFocus = preflightScopedIssueCodeFocus === chip.code ? '' : chip.code;
            if (preflightLastRenderState) {
                renderPreflightReport(preflightLastRenderState.report, preflightLastRenderState.details);
            }
        });

        preflightIssueCodeChipRow.appendChild(button);
    });

    if (activeCode) {
        const clearBtn = document.createElement('button');
        clearBtn.type = 'button';
        clearBtn.className = 'preflight_toggle_btn preflight_issue_code_chip_clear';
        clearBtn.textContent = 'Clear focus';
        clearBtn.addEventListener('click', () => {
            preflightScopedIssueCodeFocus = '';
            if (preflightLastRenderState) {
                renderPreflightReport(preflightLastRenderState.report, preflightLastRenderState.details);
            }
        });
        preflightIssueCodeChipRow.appendChild(clearBtn);
    }
}

async function copyTextToClipboard(value) {
    const text = String(value ?? '');
    if (!text) return false;

    try {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
            return true;
        }

        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const copied = document.execCommand('copy');
        document.body.removeChild(ta);
        return !!copied;
    } catch (_error) {
        return false;
    }
}

function setPreflightScopeContextStatus(message = '', type = 'info') {
    if (!preflightScopeContextStatus) return;

    const text = String(message || '').trim();
    if (!text) {
        preflightScopeContextStatus.textContent = '';
        preflightScopeContextStatus.style.display = 'none';
        return;
    }

    const colors = {
        info: '#64748b',
        success: '#166534',
        warning: '#92400e',
        error: '#b91c1c',
    };

    preflightScopeContextStatus.textContent = text;
    preflightScopeContextStatus.style.display = 'inline';
    preflightScopeContextStatus.style.color = colors[type] || colors.info;
}

function updatePreflightScopeContextCopyState({
    showRow = false,
    scopeLabel = '',
    hasBucketMetadata = false,
    bucketSelection = 'all',
    issueCodeFocus = '',
    visibleIssueCount = null,
    totalScopedIssueCount = null,
    visibleIssues = [],
} = {}) {
    const copyContextText = showRow
        ? buildScopedIssueFilterContextCopyText({
            scopeLabel,
            hasBucketMetadata,
            bucketSelection,
            issueCodeFocus,
            visibleIssueCount,
            totalScopedIssueCount,
        })
        : '';

    const copyExcerptText = showRow
        ? buildScopedIssueExcerptCopyText({
            scopeLabel,
            hasBucketMetadata,
            bucketSelection,
            issueCodeFocus,
            visibleIssueCount,
            totalScopedIssueCount,
            visibleIssues,
        })
        : '';

    const copyExcerptJsonText = showRow
        ? buildScopedIssueExcerptCopyJson({
            scopeLabel,
            hasBucketMetadata,
            bucketSelection,
            issueCodeFocus,
            visibleIssueCount,
            totalScopedIssueCount,
            visibleIssues,
        })
        : '';

    preflightLastScopedContextCopyText = copyContextText;
    preflightLastScopedIssueExcerptCopyText = copyExcerptText;
    preflightLastScopedIssueExcerptJsonCopyText = copyExcerptJsonText;

    const hasCopyActions = !!(copyContextText || copyExcerptText || copyExcerptJsonText);
    if (preflightScopeContextRow) {
        preflightScopeContextRow.style.display = hasCopyActions ? 'flex' : 'none';
    }
    if (preflightCopyScopeContextBtn) {
        preflightCopyScopeContextBtn.disabled = !copyContextText;
        preflightCopyScopeContextBtn.title = copyContextText
            ? 'Copy active scoped preflight filters for bug-report handoff.'
            : 'Run scoped preflight and pick filters to enable copy.';
    }
    if (preflightCopyScopeIssueExcerptBtn) {
        preflightCopyScopeIssueExcerptBtn.disabled = !copyExcerptText;
        preflightCopyScopeIssueExcerptBtn.title = copyExcerptText
            ? 'Copy active scoped filters plus currently visible issue lines.'
            : 'Run scoped preflight and pick filters to enable copy.';
    }
    if (preflightCopyScopeIssueExcerptJsonBtn) {
        preflightCopyScopeIssueExcerptJsonBtn.disabled = !copyExcerptJsonText;
        preflightCopyScopeIssueExcerptJsonBtn.title = copyExcerptJsonText
            ? 'Copy active scoped filters plus currently visible issue lines as structured JSON.'
            : 'Run scoped preflight and pick filters to enable copy.';
    }

    setPreflightScopeContextStatus('');
}

export function clearPreflightReport() {
    preflightLastRenderState = null;
    preflightIssueDisplayMode = 'auto';
    preflightScopedBucketFilter = 'all';
    preflightScopedIssueCodeFocus = '';
    preflightLastScopedContextCopyText = '';
    preflightLastScopedIssueExcerptCopyText = '';
    preflightLastScopedIssueExcerptJsonCopyText = '';

    if (preflightSummaryLine) {
        preflightSummaryLine.textContent = 'Preflight: not run yet.';
        preflightSummaryLine.style.color = '#334155';
    }
    if (preflightScopeLine) {
        preflightScopeLine.textContent = '';
        preflightScopeLine.style.display = 'none';
    }
    if (preflightDeltaLine) {
        preflightDeltaLine.textContent = '';
        preflightDeltaLine.style.display = 'none';
    }
    if (preflightScopeHintLine) {
        preflightScopeHintLine.textContent = '';
        preflightScopeHintLine.style.display = 'none';
    }
    if (preflightScopeBucketsLine) {
        preflightScopeBucketsLine.textContent = '';
        preflightScopeBucketsLine.style.display = 'none';
    }
    updatePreflightIssueToggleState({ showToggle: false, activeMode: 'global' });
    updatePreflightBucketFilterState({ showRow: false, activeBucket: 'all' });
    renderPreflightIssueCodeChips({ showRow: false });
    updatePreflightScopeContextCopyState({ showRow: false });

    if (preflightIssuesLabel) {
        preflightIssuesLabel.textContent = 'Issues';
    }
    if (preflightIssuesList) {
        preflightIssuesList.innerHTML = '';
        const empty = document.createElement('div');
        empty.id = 'preflight_empty_line';
        empty.style.color = '#64748b';
        empty.textContent = 'Run preflight to see geometry checks and diagnostics.';
        preflightIssuesList.appendChild(empty);
    }
}

export function renderPreflightReport(report, details = {}) {
    if (!preflightSummaryLine || !preflightIssuesList) return;

    preflightLastRenderState = { report, details };

    const scope = details?.scope || null;
    const scopedReport = details?.scopedReport || null;
    const summaryDelta = details?.summaryDelta || null;
    const issueFamilyCorrelations = details?.issueFamilyCorrelations || null;
    const usedScopedPreflight = !!details?.usedScopedPreflight;

    const summary = report?.summary || {};
    const errors = summary.errors || 0;
    const warnings = summary.warnings || 0;
    const infos = summary.infos || 0;
    const canRun = !!summary.can_run;

    const summaryPrefix = usedScopedPreflight ? 'Preflight (full geometry)' : 'Preflight';
    preflightSummaryLine.textContent = `${summaryPrefix}: ${errors} error(s), ${warnings} warning(s), ${infos} info. ` +
        (canRun ? 'Simulation can run.' : 'Simulation blocked.');
    preflightSummaryLine.style.color = canRun ? '#166534' : '#b91c1c';

    const scopeLabel = formatPreflightScopeLabel(scope);

    if (preflightScopeLine) {
        if (usedScopedPreflight && scope && scopedReport?.summary) {
            const scopedSummary = scopedReport.summary || {};
            const scopeErrors = scopedSummary.errors || 0;
            const scopeWarnings = scopedSummary.warnings || 0;
            const scopeInfos = scopedSummary.infos || 0;
            const scopeCanRun = !!scopedSummary.can_run;
            preflightScopeLine.style.display = 'block';
            preflightScopeLine.textContent = `Scope (${scopeLabel}): ${scopeErrors} error(s), ${scopeWarnings} warning(s), ${scopeInfos} info. ` +
                (scopeCanRun ? 'Scoped checks pass.' : 'Scoped checks blocked.');
        } else {
            preflightScopeLine.textContent = '';
            preflightScopeLine.style.display = 'none';
        }
    }

    if (preflightDeltaLine) {
        const outsideScope = summaryDelta?.outside_scope;
        if (usedScopedPreflight && outsideScope) {
            const outErrors = outsideScope.errors || 0;
            const outWarnings = outsideScope.warnings || 0;
            const outInfos = outsideScope.infos || 0;
            const outIssueCount = outsideScope.issue_count || 0;
            preflightDeltaLine.style.display = 'block';
            preflightDeltaLine.textContent = `Outside selected scope: ${outErrors} error(s), ${outWarnings} warning(s), ${outInfos} info (${outIssueCount} issue(s)).`;
        } else {
            preflightDeltaLine.textContent = '';
            preflightDeltaLine.style.display = 'none';
        }
    }

    if (preflightScopeHintLine) {
        const fallbackHint = resolveScopedPreflightFallbackHint(details);
        if (usedScopedPreflight) {
            preflightScopeHintLine.style.display = 'block';
            preflightScopeHintLine.textContent = 'Run safety still uses full-geometry preflight before simulation start.';
        } else if (fallbackHint) {
            preflightScopeHintLine.style.display = 'block';
            preflightScopeHintLine.textContent = fallbackHint;
        } else {
            preflightScopeHintLine.textContent = '';
            preflightScopeHintLine.style.display = 'none';
        }
    }

    if (preflightScopeBucketsLine) {
        const bucketSummary = usedScopedPreflight
            ? buildScopedIssueFamilyBucketSummary(issueFamilyCorrelations)
            : '';
        if (bucketSummary) {
            preflightScopeBucketsLine.style.display = 'block';
            preflightScopeBucketsLine.textContent = bucketSummary;
        } else {
            preflightScopeBucketsLine.textContent = '';
            preflightScopeBucketsLine.style.display = 'none';
        }
    }

    const hasScopedIssueSet = usedScopedPreflight && Array.isArray(scopedReport?.issues);
    const activeIssueMode = hasScopedIssueSet
        ? (preflightIssueDisplayMode === 'global' ? 'global' : 'scoped')
        : 'global';
    if (!hasScopedIssueSet && preflightIssueDisplayMode === 'scoped') {
        preflightIssueDisplayMode = 'auto';
    }

    updatePreflightIssueToggleState({
        showToggle: hasScopedIssueSet,
        activeMode: activeIssueMode,
    });

    let scopedBucketView = null;
    if (hasScopedIssueSet && activeIssueMode === 'scoped') {
        scopedBucketView = filterScopedIssuesByBucket(
            scopedReport.issues,
            issueFamilyCorrelations,
            preflightScopedBucketFilter,
        );
        preflightScopedBucketFilter = scopedBucketView.effectiveBucket;
    } else if (!hasScopedIssueSet) {
        preflightScopedBucketFilter = 'all';
    }

    const showBucketFilterRow = !!(scopedBucketView?.hasBucketMetadata);
    updatePreflightBucketFilterState({
        showRow: showBucketFilterRow,
        activeBucket: preflightScopedBucketFilter,
    });

    const scopedIssueCodeView = (hasScopedIssueSet && activeIssueMode === 'scoped')
        ? buildScopedIssueCodeChips(scopedReport.issues, issueFamilyCorrelations, preflightScopedBucketFilter)
        : null;
    const scopedIssueCodeSet = new Set((scopedIssueCodeView?.chips || []).map((chip) => chip.code));
    if (preflightScopedIssueCodeFocus && !scopedIssueCodeSet.has(preflightScopedIssueCodeFocus)) {
        preflightScopedIssueCodeFocus = '';
    }

    renderPreflightIssueCodeChips({
        showRow: !!(scopedIssueCodeView?.hasBucketMetadata && scopedIssueCodeView?.chips?.length),
        chips: scopedIssueCodeView?.chips || [],
        activeCode: preflightScopedIssueCodeFocus,
    });

    const activeScopedIssueCodeFocus = normalizePreflightIssueCode(preflightScopedIssueCodeFocus);
    const scopedBucketLabel = getScopedIssueBucketDisplayLabel(preflightScopedBucketFilter);

    if (preflightIssuesLabel) {
        if (hasScopedIssueSet && activeIssueMode === 'scoped') {
            const scopedLabelParts = [];
            if (scopeLabel) scopedLabelParts.push(scopeLabel);
            if (showBucketFilterRow && preflightScopedBucketFilter !== 'all') scopedLabelParts.push(scopedBucketLabel);
            if (activeScopedIssueCodeFocus) scopedLabelParts.push(`code: ${activeScopedIssueCodeFocus}`);

            if (scopedLabelParts.length > 0) {
                preflightIssuesLabel.textContent = `Scoped issues (${scopedLabelParts.join(' · ')})`;
            } else {
                preflightIssuesLabel.textContent = 'Scoped issues';
            }
        } else if (hasScopedIssueSet && activeIssueMode === 'global') {
            preflightIssuesLabel.textContent = 'Full-geometry issues';
        } else {
            preflightIssuesLabel.textContent = 'Issues';
        }
    }

    preflightIssuesList.innerHTML = '';
    const baseIssues = (hasScopedIssueSet && activeIssueMode === 'scoped')
        ? scopedReport.issues
        : (report?.issues || []);
    const issues = (scopedBucketView && scopedBucketView.hasBucketMetadata)
        ? scopedBucketView.filteredIssues
        : baseIssues;
    const focusedIssues = activeScopedIssueCodeFocus
        ? issues.filter((issue) => normalizePreflightIssueCode(issue?.code) === activeScopedIssueCodeFocus)
        : issues;

    updatePreflightScopeContextCopyState({
        showRow: hasScopedIssueSet && activeIssueMode === 'scoped',
        scopeLabel,
        hasBucketMetadata: showBucketFilterRow,
        bucketSelection: preflightScopedBucketFilter,
        issueCodeFocus: activeScopedIssueCodeFocus,
        visibleIssueCount: focusedIssues.length,
        totalScopedIssueCount: Array.isArray(scopedReport?.issues) ? scopedReport.issues.length : null,
        visibleIssues: focusedIssues,
    });

    if (focusedIssues.length === 0) {
        const empty = document.createElement('div');
        empty.style.color = '#64748b';
        if (activeScopedIssueCodeFocus) {
            empty.textContent = `No scoped issues with code "${activeScopedIssueCodeFocus}" for the current bucket view.`;
        } else if (scopedBucketView && scopedBucketView.hasBucketMetadata && scopedBucketView.emptyMessage) {
            empty.textContent = scopedBucketView.emptyMessage;
        } else if (hasScopedIssueSet && activeIssueMode === 'scoped') {
            empty.textContent = 'No issues detected in the selected scope.';
        } else if (hasScopedIssueSet && activeIssueMode === 'global') {
            empty.textContent = 'No full-geometry issues detected.';
        } else {
            empty.textContent = 'No issues detected.';
        }
        preflightIssuesList.appendChild(empty);
        return;
    }

    focusedIssues.forEach(issue => {
        const row = document.createElement('div');
        row.className = 'preflight_issue';

        const badge = document.createElement('span');
        const sev = (issue.severity || 'info').toLowerCase();
        badge.className = `preflight_badge ${sev}`;
        badge.textContent = sev;

        const textWrap = document.createElement('div');
        const message = document.createElement('div');
        message.textContent = issue.message || issue.code || 'Unknown preflight issue';
        textWrap.appendChild(message);

        if (issue.hint) {
            const hint = document.createElement('div');
            hint.style.color = '#64748b';
            hint.style.fontSize = '11px';
            hint.textContent = `Hint: ${issue.hint}`;
            textWrap.appendChild(hint);
        }

        row.appendChild(badge);
        row.appendChild(textWrap);
        preflightIssuesList.appendChild(row);
    });
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

export function showAnalysisModal() {
    if (analysisModal) {
        analysisModal.style.display = 'block';
        setTimeout(() => resizeAnalysisCharts(), 0);
    }
}

export function hideAnalysisModal() {
    if (analysisModal) analysisModal.style.display = 'none';
}

export function setAnalysisModalButtonEnabled(isEnabled) {
    if (analysisModalButton) analysisModalButton.disabled = !isEnabled;
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
    if (simSaveHitMetadataCheckbox) {
        simSaveHitMetadataCheckbox.checked = options.save_hit_metadata !== false;
    }
    simHitEnergyThresholdInput.value = options.hit_energy_threshold || '1 eV';
    if (simProductionCutInput) {
        simProductionCutInput.value = options.production_cut || '1.0 mm';
    }
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
        save_hit_metadata: simSaveHitMetadataCheckbox ? simSaveHitMetadataCheckbox.checked : true,
        hit_energy_threshold: (simHitEnergyThresholdInput.value || '1 eV').trim(),
        production_cut: (simProductionCutInput && simProductionCutInput.value ? simProductionCutInput.value : '1.0 mm').trim(),
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
    const filtering = analysis.filtering || {};

    updateAnalysisSensitiveDetectorOptions(
        filtering.available_sensitive_detectors || [],
        filtering.selected_sensitive_detector || '',
        filtering.sensitive_detector_supported !== false
    );

    ['energy_spectrum_chart', 'particle_breakdown_chart', 'xy_heatmap_chart', 'xz_heatmap_chart', 'yz_heatmap_chart'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '';
    });

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

    const selectedDetector = filtering.selected_sensitive_detector || '';
    if (selectedDetector) {
        setAnalysisStatus(`Loaded analysis for ${analysis.total_hits} hits in ${selectedDetector}.`);
    } else {
        setAnalysisStatus(`Loaded analysis for ${analysis.total_hits} hits.`);
    }
    resizeAnalysisCharts();
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
    updateAnalysisSensitiveDetectorOptions([], '', false);
    setAnalysisStatus('No analysis data loaded.');
}

export function getAnalysisOptions() {
    return {
        energyBins: parseInt(energyBinsInput?.value || '100', 10),
        spatialBins: parseInt(spatialBinsInput?.value || '50', 10),
        sensitiveDetector: getSelectedSensitiveDetectorFilter()
    };
}

function getSelectedSensitiveDetectorFilter() {
    return (analysisSensitiveDetectorSelect?.value || '').trim();
}

function updateAnalysisSensitiveDetectorOptions(detectorNames, selectedDetector, isSupported) {
    if (!analysisSensitiveDetectorSelect) return;

    const normalizedNames = Array.isArray(detectorNames)
        ? detectorNames.filter(name => typeof name === 'string' && name.trim()).map(name => name.trim())
        : [];
    const currentSelected = typeof selectedDetector === 'string' ? selectedDetector.trim() : '';

    analysisSensitiveDetectorSelect.innerHTML = '';

    const allOption = document.createElement('option');
    allOption.value = '';
    allOption.textContent = 'All hits';
    analysisSensitiveDetectorSelect.appendChild(allOption);

    normalizedNames.forEach(name => {
        const option = document.createElement('option');
        option.value = name;
        option.textContent = name;
        analysisSensitiveDetectorSelect.appendChild(option);
    });

    analysisSensitiveDetectorSelect.value = normalizedNames.includes(currentSelected) ? currentSelected : '';
    analysisSensitiveDetectorSelect.disabled = !isSupported;
    analysisSensitiveDetectorSelect.title = isSupported
        ? 'Filter analysis plots by sensitive detector.'
        : 'Sensitive-detector filtering is unavailable because this run was saved without hit metadata.';
}

function resizeAnalysisCharts() {
    if (typeof Plotly === 'undefined' || !Plotly.Plots || typeof Plotly.Plots.resize !== 'function') return;
    ['energy_spectrum_chart', 'particle_breakdown_chart', 'xy_heatmap_chart', 'xz_heatmap_chart', 'yz_heatmap_chart'].forEach(id => {
        const el = document.getElementById(id);
        if (el && el.data) {
            Plotly.Plots.resize(el);
        }
    });
}

export function setDownloadButtonEnabled(isEnabled) {
    const btn = document.getElementById('downloadSimDataButton');
    if (btn) btn.disabled = !isEnabled;
}
