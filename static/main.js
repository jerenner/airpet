// static/main.js
import * as THREE from 'three';

import * as APIService from './apiService.js';
import * as AssemblyEditor from './assemblyEditor.js';
import * as BorderSurfaceEditor from './borderSurfaceEditor.js';
import * as DefineEditor from './defineEditor.js';
import * as InteractionManager from './interactionManager.js';
import * as IsotopeEditor from './isotopeEditor.js';
import * as LVEditor from './logicalVolumeEditor.js';
import * as ElementEditor from './elementEditor.js';
import * as MaterialEditor from './materialEditor.js';
import * as OpticalSurfaceEditor from './opticalSurfaceEditor.js';
import * as PVEditor from './physicalVolumeEditor.js';
import * as SceneManager from './sceneManager.js';
import * as SkinSurfaceEditor from './skinSurfaceEditor.js';
import * as SolidEditor from './solidEditor.js';
import * as StepImportEditor from './stepImportEditor.js';
import * as UIManager from './uiManager.js';

// --- Global Application State (Keep this minimal) ---
const AppState = {
    currentProjectState: null,    // Full state dict from backend (defines, materials, solids, LVs, world_ref)
    currentProjectScene: null,    // Full scene dict from backend (THREE.js objects to be rendered)
    currentProjectName: "untitled",
    selectedHierarchyItems: [],   // array of { type, id, name, data (raw from projectState) }
    selectedThreeObjects: [],     // Managed by SceneManager, but AppState might need to know for coordination
    selectedPVContext: {
        pvId: null,
        positionDefineName: null,
        rotationDefineName: null,
    }
};

// --- Variables for auto-save ---
let isProjectChanged = false;
let autoSaveTimer = null;
const AUTO_SAVE_INTERVAL = 15000; // 15 seconds

// --- Initialization ---
document.addEventListener('DOMContentLoaded', initializeApp);

async function initializeApp() {
    console.log("Initializing GDML Editor Application...");

    // Initialize UI elements and pass callback handlers for UI-triggered actions
    UIManager.initUI({
        onNewProjectClicked: handleNewProject,
        // Open Project Handlers
        onOpenGdmlClicked: handleOpenGdmlProject,
        onOpenProjectClicked: handleOpenJsonProject,
        // Import Part Handlers
        onImportGdmlClicked: handleImportGdmlPart,
        onImportProjectClicked: handleImportJsonPart,
        onImportAiResponseClicked: handleImportAiResponse,
        onImportStepClicked: handleImportStep,
        // Other File Handlers
        onSaveProjectClicked: handleSaveProject,
        onExportGdmlClicked: handleExportGdml,
        onSetApiKeyClicked: handleSetApiKey,
        onSaveApiKeyClicked: handleSaveApiKey,
        // Project history and undo/redo
        onUndoClicked: handleUndo,
        onRedoClicked: handleRedo,
        onHistoryButtonClicked: handleShowHistory,
        onProjectRenamed: handleProjectRenamed,
        onLoadVersionClicked: handleLoadVersion,
        // Add/edit solids
        onAddSolidClicked: handleAddSolid,
        onEditSolidClicked: handleEditSolid,
        // Add/edit defines
        onAddDefineClicked: handleAddDefine,
        onEditDefineClicked: handleEditDefine,
        // Add/edit optical surfaces
        onAddOpticalSurfaceClicked: handleAddOpticalSurface,
        onEditOpticalSurfaceClicked: handleEditOpticalSurface,
        onAddSkinSurfaceClicked: handleAddSkinSurface,
        onEditSkinSurfaceClicked: handleEditSkinSurface,
        onAddBorderSurfaceClicked: handleAddBorderSurface,
        onEditBorderSurfaceClicked: handleEditBorderSurface,
        // Add/edit materials
        onAddMaterialClicked: handleAddMaterial,
        onEditMaterialClicked: handleEditMaterial,
        // Add/edit elements
        onAddElementClicked: handleAddElement,
        onEditElementClicked: handleEditElement,
        // Add/edit isotopes
        onAddIsotopeClicked: handleAddIsotope,
        onEditIsotopeClicked: handleEditIsotope,
        // Add/edit LVs
        onAddLVClicked: handleAddLV,
        onEditLVClicked: handleEditLV,
        // Add/edit PVs
        onAddPVClicked: handleAddPV,
        onEditPVClicked: handleEditPV,
        onGroupIntoAssemblyClicked: handleGroupIntoAssembly,
        // Add/edit assemblies
        onAddAssemblyClicked: handleAddAssembly,
        onEditAssemblyClicked: handleEditAssembly,

        onPVVisibilityToggle: handlePVVisibilityToggle,
        onDeleteSelectedClicked: handleDeleteSelected,
        onDeleteSpecificItemClicked: handleDeleteSpecificItem,
        onExportGdmlClicked: handleExportGdml,
        onConfirmAddObject: handleAddObject, // Data from modal comes to this handler
        onModeChangeClicked: handleModeChange, // Passes mode to InteractionManager
        onSnapToggleClicked: InteractionManager.toggleSnap, // Direct call if no complex logic
        onSnapSettingsChanged: InteractionManager.updateSnapSettings,
        onCameraModeChangeClicked: handleCameraModeChange,
        onWireframeToggleClicked: SceneManager.toggleGlobalWireframe,
        onGridToggleClicked: SceneManager.toggleGridVisibility,
        onAxesToggleClicked: SceneManager.toggleAxesVisibility,
        onHierarchySelectionChanged: handleHierarchySelection,
        onInspectorPropertyChanged: handleInspectorPropertyUpdate, // When a property in inspector is changed by user
        onAiGenerateClicked: handleAiGenerate,
        // Hierarchy organization
        onMovePvToAssembly: handleMovePvToAssembly,
        onMovePvToLv: handleMovePvToLv,
        // Group organization
        getProjectState: () => AppState.currentProjectState, // Give UI manager access to state
        onAddGroup: handleAddGroup,
        onRenameGroup: handleRenameGroup,
        onDeleteGroup: handleDeleteGroup,
        onMoveItemsToGroup: handleMoveItemsToGroup
    });

    // Initialize the 3D scene and its controls
    SceneManager.initScene({
        onObjectSelectedIn3D: handle3DSelection,          // Callback when object clicked in 3D scene
        onObjectTransformEnd: handleTransformEnd,          // Callback when TransformControls drag/rotate/scale ends
        //onObjectTransformLive: handleTransformLive,       // Live transformations
        onMultiObjectSelected: handle3DMultiSelection, // Selector box
        getInspectorSnapSettings: () => { // Provide snap settings to SceneManager/TransformControls
            return { 
                snapEnabled: InteractionManager.isSnapEnabled(), 
                translationSnap: InteractionManager.getTranslationSnapValue(),
                rotationSnap: InteractionManager.getRotationSnapValue() 
            };
        }
    });
    
    // Initialize interaction manager (modes, keyboard shortcuts for transforms)
    InteractionManager.initInteractionManager(
        SceneManager.getTransformControls(), // Pass the TransformControls instance
        SceneManager.getOrbitControls(),     // Pass the OrbitControls instance
    );

    // Initialize define editor
    DefineEditor.initDefineEditor({ 
        onConfirm: handleDefineEditorConfirm,
        getProjectState: () => AppState.currentProjectState // Provide access to state
    });

    // Initialize logical volume editor
    LVEditor.initLVEditor({
        onConfirm: handleLVEditorConfirm
    });

    // Initialize the assembly editor
    AssemblyEditor.initAssemblyEditor({
        onConfirm: handleAssemblyEditorConfirm
    });

    // Initialize the materials editor
    MaterialEditor.initMaterialEditor({
        onConfirm: handleMaterialEditorConfirm
    });

    // Initialize the elements editor
    ElementEditor.initElementEditor({
        onConfirm: handleElementEditorConfirm
    });

    // Initialize the isotopes editor
    IsotopeEditor.initIsotopeEditor({ 
        onConfirm: handleIsotopeEditorConfirm 
    });

    // Initialize physical volume editor
    PVEditor.initPVEditor({ 
        onConfirm: handlePVEditorConfirm 
    });

    // Initialize solid editor
    SolidEditor.initSolidEditor({
        onConfirm: handleSolidEditorConfirm,
        getSelectedParentContext: () => UIManager.getSelectedParentContext() 
    });

    // Initialize the optical surface editor
    OpticalSurfaceEditor.initOpticalSurfaceEditor({
        onConfirm: handleOpticalSurfaceEditorConfirm
    });

    // Initialize the skin surface editor
    SkinSurfaceEditor.initSkinSurfaceEditor({
        onConfirm: handleSkinSurfaceEditorConfirm
    });

    // Initialize the border surface editor
    BorderSurfaceEditor.initBorderSurfaceEditor({
        onConfirm: handleBorderSurfaceEditorConfirm
    });

    // Initialize the new editor
    StepImportEditor.initStepImportEditor({
        onConfirm: handleConfirmStepImport
    });

    // Add menu listeners
    document.getElementById('hideSelBtn').addEventListener('click', handleHideSelected);
    document.getElementById('showSelBtn').addEventListener('click', handleShowSelected);
    document.getElementById('hideAllBtn').addEventListener('click', handleHideAll);
    document.getElementById('showAllBtn').addEventListener('click', handleShowAll);

    // --- Check AI service status on startup ---
    checkAndSetAiStatus();

    // Restore session from backend on page load
    console.log("Fetching initial project state from backend...");
    const initialState = await APIService.getProjectState();
    // No try/catch needed, as the backend now guarantees a valid response
    if (initialState && initialState.project_state) {
        
        // Set the project name
        AppState.currentProjectName = initialState.project_name;
        UIManager.setProjectName(AppState.currentProjectName);

        // Save the project state and scene description
        AppState.currentProjectState = initialState.project_state;
        AppState.currentProjectScene = initialState.scene_update;

        // Update the UI and scene.
        UIManager.updateHierarchy(initialState.project_state,initialState.scene_update);
        SceneManager.renderObjects(initialState.scene_update || [], initialState.project_state);
        SceneManager.frameScene();

    } else {
        // This case should theoretically not be reached anymore, but is good for safety
        UIManager.showError("Failed to retrieve a valid project state from the server.");
    }

    // --- Global Keyboard Listener ---
    window.addEventListener('keydown', (event) => {

        // If the user is typing in ANY input field, textarea, or contenteditable element,
        // do not trigger any of the global shortcuts (except for Undo/Redo/Save which are universal).
        const isTyping = document.activeElement.tagName === 'INPUT' ||
                         document.activeElement.tagName === 'TEXTAREA' ||
                         document.activeElement.isContentEditable;
        
        // Undo
        if (event.ctrlKey && !event.shiftKey && event.key.toLowerCase() === 'z') {
            event.preventDefault();
            handleUndo();
        }
        // Redo
        if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'z') {
            event.preventDefault();
            handleRedo();
        }

        // Save version
        if (event.ctrlKey && event.key.toLowerCase() === 's') {
            event.preventDefault();
            handleSaveVersion();
        }

        // If we are typing in an input field, stop here for all other shortcuts.
        if (isTyping) {
            return;
        }

        // Focus camera on selected object
        if (event.key.toLowerCase() === 'f') {
            event.preventDefault();
            handleCameraModeChange('selected'); // Trigger the "focus selected" action
        }
        // Focus camera on origin
        if (event.key.toLowerCase() === 'o') {
            event.preventDefault();
            handleCameraModeChange('origin'); // Trigger the "focus selected" action
        }

        // Delete
        if (event.key === 'Delete' || event.key === 'Backspace') {
            event.preventDefault();
            handleDeleteSelected();
        }

        // Hide all
        if (event.shiftKey && event.key.toLowerCase() === 'h') {
            event.preventDefault();
            handleHideAll();
        }
        // Hide selected
        else if (event.key.toLowerCase() === 'h') {
            event.preventDefault();
            handleHideSelected();
        }
        // Show all
        if (event.shiftKey && event.key.toLowerCase() === 'j') {
            event.preventDefault();
            handleShowAll();
        }
        // Show selected
        else if (event.key.toLowerCase() === 'j') {
            event.preventDefault();
            handleShowSelected();
        }

        // --- Modes ---
        if (event.key.toLowerCase() === 'e') {
            event.preventDefault();
            handleModeChange('observe');
        }
        if (event.key.toLowerCase() === 't') {
            event.preventDefault();
            handleModeChange('translate');
        }
        if (event.key.toLowerCase() === 'r') {
            event.preventDefault();
            handleModeChange('rotate');
        }
        // if (event.key.toLowerCase() === 'e') {
        //     event.preventDefault();
        //     handleModeChange('scale');
        // }

    });

    console.log("Application Initialized.");
}

// --- State Synchronization and Selection Management ---

/**
 * Triggers a browser download for a given text content.
 * @param {string} filename - The name of the file to be downloaded.
 * @param {string} text - The content of the file.
 */
function downloadTextFile(filename, text) {
    const element = document.createElement('a');
    element.setAttribute('href', 'data:text/plain;charset=utf-8,' + encodeURIComponent(text));
    element.setAttribute('download', filename);

    element.style.display = 'none';
    document.body.appendChild(element);

    element.click();

    document.body.removeChild(element);
}
/**
 * Gets the context of the currently selected item(s).
 */
function getSelectionContext() {
    // Check the new array property
    if (!AppState.selectedHierarchyItems || AppState.selectedHierarchyItems.length === 0) {
        return null;
    }
    // Return the array of selected items.
    // Each item in the array is already a context object: {type, id, name, data}
    return AppState.selectedHierarchyItems;
}

/**
    The single function to update the entire UI from a new state object from the backend.
    This is the core of the unidirectional data flow pattern.
    @param {object} responseData The consistent success response object from the backend.
*/
function syncUIWithState(responseData, selectionToRestore = []) {
    if (!responseData || !responseData.success) {
        UIManager.showError(responseData.error || "An unknown error occurred during state sync.");
        return;
    }
    console.log("[Main] Syncing UI with new backend state. Message: " + responseData.message);

    // Set changed state for autosave
    markProjectAsChanged();

    // --- MERGE LOGIC for partial updates ---
    if (responseData.response_type === 'full_with_exclusions') {
        console.log("Merging with exclusions")
        // This is a partial state update. We need to merge it.
        // We can't just replace the whole state.
        const newSolids = responseData.project_state.solids || {};
        
        // Keep all existing solids that are NOT in the incoming update.
        // This preserves our large, static tessellated solids on the client.
        const preservedSolids = {};
        for (const solidName in AppState.currentProjectState.solids) {
            if (!newSolids.hasOwnProperty(solidName)) {
                preservedSolids[solidName] = AppState.currentProjectState.solids[solidName];
            }
        }
        
        // Combine the preserved solids with the newly received ones.
        const combinedSolids = { ...preservedSolids, ...newSolids };
        
        // Update the project state with the combined solids list.
        AppState.currentProjectState = responseData.project_state;
        AppState.currentProjectState.solids = combinedSolids;

    } else {
        // This is a full state update (e.g., from loading a file). Replace everything.
        AppState.currentProjectState = responseData.project_state;
    }

    // 1. Update the global AppState cache
    //AppState.currentProjectState updated in logic above
    AppState.currentProjectScene = responseData.scene_update;
    AppState.selectedHierarchyItems = []; // Clear old selections
    AppState.selectedThreeObjects = [];
    AppState.selectedPVContext.pvId = null;

    // 2. Re-render the 3D scene
    if (responseData.scene_update) {
        SceneManager.renderObjects(AppState.currentProjectScene, AppState.currentProjectState);
        
        // --- Frame the scene after a full update ---
        // We only do this for "full" loads, not for every small patch.
        // const responseType = responseData.response_type || "full";
        // if (responseType.startsWith("full")) { // Catches 'full' and 'full_with_exclusions'
        //      SceneManager.frameScene();
        // }

    } else {
        SceneManager.clearScene(); // Ensure scene is cleared if there's no update
    }

    // 3. Re-render the hierarchy panels
    UIManager.updateHierarchy(responseData.project_state,responseData.scene_update);

    // 4. Update Undo/Redo button states
    if (responseData.history_status) {
        UIManager.updateUndoRedoButtons(responseData.history_status);
    }

    // 5. Restore selection and repopulate inspector ---
    restoreSelection(selectionToRestore);

    // 6. Re-apply persistent visibility state ---
    restoreVisibility();
    
}

function restoreVisibility() {

    // Iterate through the list of hidden IDs and apply the visibility state.
    const hiddenPvIds = SceneManager.getHiddenPvIds();
    if (hiddenPvIds.size > 0) {
        console.log("Re-applying visibility state for", hiddenPvIds.size, "objects.");
        hiddenPvIds.forEach(pvId => {
            SceneManager.setPVVisibility(pvId, false);
            UIManager.setTreeItemVisibility(pvId, false);
        });
    }
}

function restoreSelection(selectionToRestore) {

    let validatedSelectionToRestore = [];
    if (selectionToRestore && selectionToRestore.length > 0) {

        // Filter the old selection, keeping only items that still exist in the new state.
        validatedSelectionToRestore = selectionToRestore.filter(item => {
                const itemId = item.id || item.canonical_id;
                return (findItemInScene(itemId) != null);
        });

        if (validatedSelectionToRestore.length > 0) {
            const idsToSelect = validatedSelectionToRestore.map(item => {
                const itemId = item.id || item.canonical_id;
                return itemId;
            });
            UIManager.setHierarchySelection(idsToSelect); // Visually select in the hierarchy
            handleHierarchySelection(validatedSelectionToRestore); // Update inspector, gizmo, etc.
        } else {
            // If no valid selection remains (or there was none to begin with), clear everything.
            UIManager.clearInspector();
            UIManager.clearHierarchySelection();
            SceneManager.unselectAllInScene();
        }  
    }
}

function syncUIWithState_shallow(responseData) {
    if (!responseData.success) {
        UIManager.showError(responseData.error || "A shallow update failed.");
        return;
    }

    // Set changed state for autosave
    markProjectAsChanged();
    
    const patch = responseData.patch;

    // Apply project state patch
    if (patch.project_state) {
        const projectPatch = patch.project_state;

        // Process deletions
        if (projectPatch.deleted) {
            for (const [category, idList] of Object.entries(projectPatch.deleted)) {
                if (!idList || idList.length === 0) continue;
                
                // Map the category to the correct AppState dictionary
                const targetDictName = category === 'physical_volumes' ? null : category;
                if (targetDictName && AppState.currentProjectState[targetDictName]) {
                    idList.forEach(id => {
                        delete AppState.currentProjectState[targetDictName][id];
                    });
                } else if (category === 'physical_volumes') {
                    // Need to find and remove PVs from their parents
                    idList.forEach(pvIdToDelete => {
                        for (const lv of Object.values(AppState.currentProjectState.logical_volumes)) {
                            if (lv.content_type === 'physvol') {
                                lv.content = lv.content.filter(pv => pv.id !== pvIdToDelete);
                            }
                        }
                        // Also check assemblies
                        for (const asm of Object.values(AppState.currentProjectState.assemblies)) {
                            asm.placements = asm.placements.filter(pv => pv.id !== pvIdToDelete);
                        }
                    });
                }
            }
        }

        // Process updates
        if (projectPatch.updated && projectPatch.updated.physical_volumes) {
            for (const [pvId, updatedPvData] of Object.entries(projectPatch.updated.physical_volumes)) {
                let found = false;
                
                // Search in Logical Volumes
                for (const lv of Object.values(AppState.currentProjectState.logical_volumes)) {
                    if (lv.content_type === 'physvol') {
                        const index = lv.content.findIndex(pv => pv.id === pvId);
                        if (index !== -1) {
                            // Found it! Replace the old object with the new one.
                            lv.content[index] = updatedPvData;
                            found = true;
                            break;
                        }
                    }
                }
                
                // If not found, search in Assemblies
                if (!found) {
                    for (const asm of Object.values(AppState.currentProjectState.assemblies)) {
                        const index = asm.placements.findIndex(pv => pv.id === pvId);
                        if (index !== -1) {
                            // Found it! Replace the old object with the new one.
                            asm.placements[index] = updatedPvData;
                            found = true;
                            break;
                        }
                    }
                }
                if (!found) console.warn(`Could not find PV with ID ${pvId} in AppState to apply update.`);
            }
        }
    }

    // Update the full scene if it exists.
    if (responseData.scene_update) {
        AppState.currentProjectScene = responseData.scene_update;
        SceneManager.renderObjects(responseData.scene_update, AppState.currentProjectState);
    }
    // Otherwise, apply scene patch (for transforms)
    else if (patch.scene_update && patch.scene_update.updated_transforms) {
        patch.scene_update.updated_transforms.forEach(update => {
            // Update the local AppState first
            const pv_obj = findItemInState(update.id)?.data;
            if (pv_obj) {
                pv_obj._evaluated_position = update.position;
                pv_obj._evaluated_rotation = update.rotation;
                pv_obj._evaluated_scale = update.scale;
            }
            // Tell SceneManager to visually update the object
            SceneManager.updateObjectTransformFromData(update.id, update.position, update.rotation, update.scale);
        });
    }

    //if (patch.project_state && patch.project_state.updated) {
        // ... logic to merge updated objects into AppState.currentProjectState ...
    //}

    // Re-render the hierarchy panels
    UIManager.updateHierarchy(AppState.currentProjectState, AppState.currentProjectScene);
    
    // Update the undo/redo buttons
    if (responseData.history_status) {
        UIManager.updateUndoRedoButtons(responseData.history_status);
    }
    
    // 5. Restore selection and repopulate inspector ---
    const selectionToRestore = AppState.selectedHierarchyItems;
    restoreSelection(selectionToRestore);

    // 6. Re-apply persistent visibility state ---
    restoreVisibility();
    
}

// --- Autosave functions
/**
 * Marks the project as having unsaved changes and schedules an autosave.
 */
function markProjectAsChanged() {
    isProjectChanged = true;
    
    // Reset any existing timer
    if (autoSaveTimer) {
        clearTimeout(autoSaveTimer);
    }
    
    // Set a new timer to trigger the autosave after the interval
    console.log(`[AutoSave] Project is in changed state. Scheduling autosave in ${AUTO_SAVE_INTERVAL / 1000}s.`);
    autoSaveTimer = setTimeout(triggerAutoSave, AUTO_SAVE_INTERVAL);
}

/**
 * The function that is called after the user has been idle.
 */
async function triggerAutoSave() {
    if (!isProjectChanged) {
        console.log("[AutoSave] Aborting: Project is not in changed state.");
        return;
    }
    
    console.log("[AutoSave] Idle timer expired. Triggering autosave...");
    
    try {
        const result = await APIService.autoSaveProject(); // A new API service function
        if (result.success && result.message !== "No changes to autosave.") {
            console.log("[AutoSave] Backend confirmed autosave.");
            isProjectChanged = false; // Reset the dirty flag ONLY on successful save
            UIManager.showTemporaryStatus("Auto-saved");
        }
    } catch (error) {
        console.error("Auto-save failed:", error.message);
        // We do NOT reset the dirty flag, so it will try again later.
    }
}

// --- Handler Functions (Act as Controllers/Mediators) ---

async function handleSetApiKey() {
    // Fetch the current key to pre-fill the input
    try {
        const response = await APIService.getGeminiApiKey();
        if (response.api_key) {
            UIManager.setApiKeyInputValue(response.api_key);
        } else {
            UIManager.setApiKeyInputValue("");
        }
        UIManager.showApiKeyModal();
    } catch (error) {
        UIManager.showError("Could not fetch current API key: " + error.message);
    }
}

async function handleSaveApiKey(apiKey) {
    UIManager.showLoading("Saving API Key...");
    try {
        const result = await APIService.setGeminiApiKey(apiKey);
        if (result.success) {
            UIManager.hideApiKeyModal();
            UIManager.showNotification(result.message);
            // After saving, refresh the AI status to get the new model list
            checkAndSetAiStatus();
        } else {
            UIManager.showError(result.error);
        }
    } catch (error) {
        UIManager.showError("Failed to save API key: " + error.message);
    } finally {
        UIManager.hideLoading();
    }
}

function handle3DMultiSelection(selectedMeshes, isCtrlHeld) {
    // --- Start with the current selection if Ctrl is held ---
    let currentSelection = isCtrlHeld ? [...AppState.selectedHierarchyItems] : [];
    
    // --- Use a Map to consolidate procedural volumes and track standard PVs ---
    // The key will be the canonical ID (either the PV's own ID or its owner's ID)
    const consolidatedSelectionMap = new Map();
    currentSelection.forEach(item => consolidatedSelectionMap.set(item.canonical_id, item));

    selectedMeshes.forEach(mesh => {
        // The ID is the parent ID for procedural slices, or its own ID for standard PVs.
        const selectedId = mesh.userData.id;
        
        // If we haven't processed this canonical object yet, add it to our map.
        if (!consolidatedSelectionMap.has(selectedId)) {
            const itemContext = findItemInScene(selectedId);
            if (itemContext) {
                // Select the parent for procedural instances
                if(itemContext.selData.is_procedural_instance) {
                    const parentId = itemContext.selData.parent_id;
                    const parentItem = findItemInScene(parentId);
                    if(parentItem) consolidatedSelectionMap.set(parentId, parentItem);
                }
                else {
                    consolidatedSelectionMap.set(selectedId, itemContext);
                }
            }
        }
    });

    // Convert the map back to an array
    const finalSelection = Array.from(consolidatedSelectionMap.values());

    // --- The rest of the process remains the same ---
    // This will now correctly select the procedural parent in the hierarchy
    // and update the inspector and gizmo state based on the consolidated list.
    handleHierarchySelection(finalSelection);
}

async function handleOpenGdmlProject(file) {
    if (!file) return;
    if (!UIManager.confirmAction("This will replace your current project. Are you sure?")) {
        document.getElementById('gdmlFile').value = null; // Reset input
        return;
    }
    UIManager.showLoading("Opening GDML Project...");
    try {
        const result = await APIService.openGdmlProject(file);
        syncUIWithState(result);
        //UIManager.showNotification("GDML project loaded successfully. Note: Any <file> or <!ENTITY> references were ignored.");
    } catch (error) { 
        // Show the specific error message from the backend
        UIManager.showError("Failed to open GDML Project: " + error.message);
    } finally {
        document.getElementById('gdmlFile').value = null;
        UIManager.hideLoading();
    }
}

async function handleOpenJsonProject(file) {
    if (!file) return;
    if (!UIManager.confirmAction("This will replace your current project. Are you sure?")) {
        document.getElementById('projectFile').value = null; // Reset input
        return;
    }
    UIManager.showLoading("Opening JSON Project...");
    try {
        const result = await APIService.openJsonProject(file);
        syncUIWithState(result);
    } catch (error) { 
        UIManager.showError("Failed to open JSON Project: " + (error.message || error));
    } finally {
        document.getElementById('projectFile').value = null;
        UIManager.hideLoading();
    }
}

async function handleImportGdmlPart(file) {
    if (!file) return;
    UIManager.showLoading("Importing GDML Part...");
    try {
        const result = await APIService.importGdmlPart(file);
        syncUIWithState(result); // The sync function handles the refresh perfectly
        //UIManager.showNotification("GDML part(s) imported. Note: Any <file> or <!ENTITY> references were ignored.");
    } catch (error) { 
        // Show the specific error from the backend
        UIManager.showError("Failed to import GDML Part: " + error.message);
    } finally {
        document.getElementById('gdmlPartFile').value = null;
        UIManager.hideLoading();
    }
}

async function handleImportJsonPart(file) {
    if (!file) return;
    UIManager.showLoading("Importing JSON Part...");
    try {
        const result = await APIService.importJsonPart(file);
        syncUIWithState(result);
    } catch (error) { 
        UIManager.showError("Failed to import JSON Part: " + (error.message || error));
    } finally {
        document.getElementById('jsonPartFile').value = null;
        UIManager.hideLoading();
    }
}

async function handleImportAiResponse(file) {
    if (!file) return;
    UIManager.showLoading("Importing AI Response...");
    try {
        const result = await APIService.importAiResponse(file);
        syncUIWithState(result); // The sync function handles the refresh
        UIManager.showNotification("AI Response imported successfully!");
    } catch (error) { 
        UIManager.showError("Failed to import AI Response: " + (error.message || error));
    } finally {
        // Reset the file input so the user can upload the same file again if they want
        document.getElementById('aiResponseFile').value = null;
        UIManager.hideLoading();
    }
}

// Handler for the "New Project" button
async function handleNewProject() {
    if (!UIManager.confirmAction("This will clear the current session. Are you sure?")) return;
    UIManager.showLoading("Creating new project...");
    try {
        const result = await APIService.newProject();
        syncUIWithState(result); // No selection to restore
    } catch (error) { UIManager.showError("Failed to create new project: " + error.message); }
    finally { UIManager.hideLoading(); }
}

async function handleSaveProject() {
    UIManager.showLoading("Saving project...");
    handleSaveVersion();
    try {
        await APIService.saveProject();
    } catch (error) { UIManager.showError("Failed to save project: " + (error.message || error)); }
    finally { UIManager.hideLoading(); }
}

async function handleExportGdml() {
    UIManager.showLoading("Exporting GDML...");
    try {
        await APIService.exportGdml(); // APIService handles the download
    } catch (error) { UIManager.showError("Failed to export GDML: " + (error.message || error)); }
    finally { UIManager.hideLoading(); }
}

async function handleUndo() {
    const selectionBeforeUndo = [...AppState.selectedHierarchyItems]; // Make a copy
    //UIManager.showLoading("Undoing...");
    try {
        const result = await APIService.undo();
        syncUIWithState(result, selectionBeforeUndo); // Restore selection after undo
    } catch (error) { UIManager.showError(error.message); }
    //finally { UIManager.hideLoading(); }
}

async function handleRedo() {
    const selectionBeforeRedo = [...AppState.selectedHierarchyItems]; // Make a copy
    //UIManager.showLoading("Redoing...");
    try {
        const result = await APIService.redo();
        syncUIWithState(result, selectionBeforeRedo); // Restore selection after redo
    } catch (error) { UIManager.showError(error.message); }
    //finally { UIManager.hideLoading(); }
}

async function handleShowHistory() {
    //UIManager.showLoading("Fetching history...");
    try {
        const result = await APIService.getProjectHistory(AppState.currentProjectName);
        if (result.success) {
            UIManager.populateHistoryPanel(result.history, AppState.currentProjectName);
            UIManager.showHistoryPanel();
        } else {
            UIManager.showError(result.error);
        }
    } catch (error) { UIManager.showError(error.message); }
    //finally { UIManager.hideLoading(); }
}

async function handleLoadVersion(projectName, versionId) {
    UIManager.showLoading(`Loading version ${versionId}...`);
    try {
        const result = await APIService.loadVersion(projectName, versionId);
        syncUIWithState(result); // This will update the whole app to the restored state
        UIManager.hideHistoryPanel();
    } catch (error) { UIManager.showError(error.message); }
    finally { UIManager.hideLoading(); }
}

async function handleSaveVersion() {
    UIManager.showLoading("Saving version...");
    try {
        const result = await APIService.saveVersion(AppState.currentProjectName);
        UIManager.showTemporaryStatus(result.message);
    } catch (error) { UIManager.showError("Failed to save version: " + error.message); }
    finally { UIManager.hideLoading(); }
}

async function handleAddObject(objectType, nameSuggestion, paramsFromModal) {
    UIManager.showLoading("Adding object...");
    try {
        const result = await APIService.addObject(objectType, nameSuggestion, paramsFromModal);
        syncUIWithState(result);
        UIManager.hideAddObjectModal();
    } catch (error) {
        UIManager.showError("Error adding object: " + (error.message || error));
    }
    finally { UIManager.hideLoading(); }
}

// --- Delete all selected items ---
async function handleDeleteSelected() {
    const selectionContexts = getSelectionContext();
    
    if (!selectionContexts) {
        UIManager.showNotification("Please select one or more items to delete.");
        return;
    }

    const itemsToDelete = selectionContexts.map(item => ({ type: item.type, id: item.canonical_id, name: item.name }));

    let confirmationMessage;
    if (selectionContexts.length === 1) {
        confirmationMessage = `Are you sure you want to delete ${selectionContexts[0].type}: ${selectionContexts[0].name}?`;
    } else {
        confirmationMessage = `Are you sure you want to delete ${selectionContexts.length} items?`;
    }

    if (!UIManager.confirmAction(confirmationMessage)) return;

    UIManager.showLoading(`Deleting ${selectionContexts.length} item(s)...`);
    try {
        const result = await APIService.deleteObjectsBatch(itemsToDelete);
        // A successful deletion requires a full state sync because many things could have changed.
        syncUIWithState_shallow(result);
    } catch (error) {
        if (error.type === 'dependency') {
            UIManager.showDependencyError(error.message);
        } else {
            UIManager.showError("An error occurred during deletion: " + error.message);
        }
    } finally {
        UIManager.hideLoading();
    }
}

async function handleDeleteSpecificItem(type, id, name) {
    // We can reuse the main handler's logic.
    // For simplicity, we'll make a direct API call here.
    const itemToDelete = [{ type: type, id: id, name: name }];
    
    UIManager.showLoading("Deleting object...");
    try {
        const result = await APIService.deleteObjectsBatch(itemToDelete);
        syncUIWithState_shallow(result);
    } catch (error) {
        if (error.type === 'dependency') {
            UIManager.showDependencyError(error.message);
        } else {
            UIManager.showError("Error deleting object: " + error.message);
        }
    } finally {
        UIManager.hideLoading();
    }
}

async function handleProjectRenamed(newName) {

    // Set the frontend current project name
    AppState.currentProjectName = newName;
 
    // Send the new name to the backend
    try {
        const result = await APIService.renameProject(newName);
    } catch (error) {
        UIManager.showError("Error renaming project: " + error.message);
    } 
}

function handleModeChange(newMode) {
    UIManager.setActiveModeButton(newMode);
    InteractionManager.setMode(newMode, AppState.selectedThreeObjects.length > 0 ? AppState.selectedThreeObjects[0] : null);
    
    if (newMode === 'observe' && SceneManager.getTransformControls().object) {
        SceneManager.getTransformControls().detach();
    } else if (newMode !== 'observe' && AppState.selectedThreeObjects.length > 0){
        // Pass the entire array of selected objects
        SceneManager.attachTransformControls(AppState.selectedThreeObjects);
    }
}

async function handleHierarchySelection(newSelection) {
    //console.log("Hierarchy selection changed. New selection count:", newSelection.length);
    AppState.selectedHierarchyItems = newSelection;
    
    // --- 1. Check selection type and manage UI state ---
    // let transformState = { translate: true, rotate: true, scale: false }; // Default for standard PVs
    // let reason = '';

    // if (newSelection.length === 1) {
    //     const item = newSelection[0];
    //     if (item.type === 'physical_volume') {
    //         const lv = AppState.currentProjectState.logical_volumes[item.selData.volume_ref];
    //         if (lv && lv.content_type !== 'physvol') {
    //             // It's a procedural volume, remove gizmo transformations.
    //             transformState = { translate: true, rotate: true, scale: false };
    //             reason = "Scaling is not supported for procedural volumes.";
    //         }
    //     }
    // // For multi-selection, disable scale if any item is procedural.
    // } else if (newSelection.length > 1) {
    //     const anyProcedural = newSelection.some(item => {
    //         if (item.type !== 'physical_volume') return false;
    //         const lv = AppState.currentProjectState.logical_volumes[item.selData.volume_ref];
    //         return lv && lv.content_type !== 'physvol';
    //     });
    //     if (anyProcedural) {
    //         transformState = { translate: true, rotate: true, scale: false };
    //         reason = "Scaling is not supported for procedural volumes.";
    //     }
    // }

    // UIManager.setTransformButtonsState(transformState, reason);

    // // If a disabled mode is currently active, switch to 'observe'
    // const currentMode = InteractionManager.getCurrentMode();
    // if (currentMode !== 'observe' && !transformState[currentMode]) {
    //     handleModeChange('observe');
    // }

    // --- 2. Build the list of meshes to highlight/transform ---
    const meshesToProcess = [];
    newSelection.forEach(item => {
        if (item.type === 'physical_volume') {
            let isProcedural = item.selData.is_procedural_instance;
            if (isProcedural) {
                // Procedural PV: get all its instances.
                meshesToProcess.push(...SceneManager.getMeshesForOwner(item.canonical_id));
            } else {
                // Simple PV: get its single mesh.
                const mesh = SceneManager.findObjectByPvId(item.id);
                if (mesh) meshesToProcess.push(mesh);
            }
        }
    });

    // --- 3. Update the 3D Scene (Visuals and Gizmo) ---
    SceneManager.updateSelectionState(meshesToProcess);
    AppState.selectedThreeObjects = meshesToProcess;
    
    // Consolidate the gizmo logic. Always detach first, then attach if needed.
    SceneManager.getTransformControls().detach();
    if (InteractionManager.getCurrentMode() !== 'observe' && meshesToProcess.length > 0) {
        SceneManager.attachTransformControls(meshesToProcess);
    }

    // --- 4. Update the UI (Hierarchy List and Inspector) ---
    const selectedIds = newSelection.map(item => {
        if(item.selData.is_procedural_instance) {
            return item.canonical_id;
        }
        return item.id;
    });
    UIManager.setHierarchySelection(selectedIds);

    if (newSelection.length === 1) {
        const singleItem = newSelection[0];

        // The getObjectDetails and populateInspector logic can now proceed
        const type = singleItem.type;
        const name = singleItem.name;
        const id = singleItem.canonical_id;
        
        const idForApi = (type === 'physical_volume') ? id : name;
        try {
            const details = await APIService.getObjectDetails(type, idForApi);
            if (details) {
                singleItem.data = details; // Ensure data is up-to-date

                // Hack-fix for procedurals
                if(singleItem.selData.is_procedural_instance) {
                    singleItem.id = singleItem.canonical_id;
                }
                UIManager.populateInspector(singleItem, AppState.currentProjectState);
            } else {
                UIManager.showError(`Could not fetch details for ${type} ${idForApi}`);
                UIManager.clearInspector();
            }
        } catch (error) {
            UIManager.showError(error.message);
            UIManager.clearInspector();
        }
    } else if (newSelection.length > 1) {
        UIManager.clearInspector();
        UIManager.setInspectorTitle(`${newSelection.length} items selected`);
    } else {
        UIManager.clearInspector();
    }
}

// Called by SceneManager when an object is clicked in 3D
function handle3DSelection(clickedMesh, isCtrlHeld, isShiftHeld) {
    if (isShiftHeld) return; // Shift-select is still deferred

    let currentSelection = isCtrlHeld ? [...AppState.selectedHierarchyItems] : [];
    let clickedItemInstanceId = null;
    
    if (clickedMesh) {
        const userData = clickedMesh.userData;
        clickedItemInstanceId = userData.id
    }

    if (clickedItemInstanceId) {
        const existingIndex = currentSelection.findIndex(item => item.id === clickedItemInstanceId);
        
        if (isCtrlHeld) {
            if (existingIndex > -1) {
                currentSelection.splice(existingIndex, 1);
            } else {
                const newItem = findItemInScene(clickedItemInstanceId);
                if(newItem) {
                    // For a procedural, always select the parent.
                    if(newItem.selData.is_procedural_instance) {
                        const parentItem = findItemInScene(newItem.selData.parent_id);
                        if(parentItem) currentSelection.push(parentItem);
                    }
                    else{
                        currentSelection.push(newItem);
                    }
                }
            }
        } else {
            const newItem = findItemInScene(clickedItemInstanceId);
            if(newItem) {
                // For a procedural, always select the parent.
                if(newItem.selData.is_procedural_instance) {
                    const parentItem = findItemInScene(newItem.selData.parent_id);
                    currentSelection = parentItem ? [parentItem] : [];
                }
                else{
                    currentSelection = [newItem];
                }
            }
        }
    } else if (!isCtrlHeld) {
        currentSelection = [];
    }
    
    // Now that we have the final list of selected items, trigger the main handler.
    // This becomes the single point of truth for updating the UI, inspector, and 3D scene.
    handleHierarchySelection(currentSelection);
}

function findItemInScene(itemId) {

    const pv = SceneManager.findObjectByPvId(itemId);
    if(pv){
        return {type: "physical_volume", id: pv.userData.id, name: pv.userData.name, selData: pv.userData, canonical_id: pv.userData.canonical_id};
    }
    return null;
}

// Helper function to find a PV by its ID anywhere in the project state
function findItemInState(itemCanonicalId) {

    if (!AppState.currentProjectState) return null;
    const state = AppState.currentProjectState;

    // --- If an instance ID was provided, find the item in the scene
    // let sceneItem = null;
    // if(itemInstanceId) {
    //    sceneItem = findItemInScene(itemInstanceId)
    // }
    
    // --- Find the item in the project state

    // Search standard PVs
    for (const lv of Object.values(state.logical_volumes)) {
        if (lv.content_type === 'physvol') {
            const found = lv.content.find(pv => pv.id === itemCanonicalId);
            if (found) {
                // Return the standard context object
                return { type: 'physical_volume', id: found.id, name: found.name, selData: found, canonical_id: found.id };
            }
        }
    }
    // Search PVs within Assemblies
    for (const asm of Object.values(state.assemblies)) {
        const found = asm.placements.find(pv => pv.id === itemCanonicalId);
        if (found) {
            return { type: 'physical_volume', id: found.id, name: found.name, data: found, canonical_id: found.id };
        }
    }

    // Add searches for other types if needed in the future...
    return null;
}

// function handleTransformLive(liveObject) {
//     // 1. Update the PV's own inspector (if it has inline values)
//     if (AppState.selectedHierarchyItem && AppState.selectedHierarchyItem.id === liveObject.userData.id) {
//         UIManager.updateInspectorTransform(liveObject);
//     }

//     // 2. If the transform is linked to a define, update THAT define's inspector
//     const euler = new THREE.Euler().setFromQuaternion(liveObject.quaternion, 'XYZ');
//     const newPosition = { x: liveObject.position.x, y: liveObject.position.y, z: liveObject.position.z };
//     const newRotation = { x: euler.x, y: euler.y, z: euler.z };

//     if (AppState.selectedPVContext.positionDefineName) {
//         UIManager.updateDefineInspectorValues(AppState.selectedPVContext.positionDefineName, newPosition);
//     }
//     if (AppState.selectedPVContext.rotationDefineName) {
//         UIManager.updateDefineInspectorValues(AppState.selectedPVContext.rotationDefineName, newRotation, true); // true for rotation
//     }
// }

// Called by SceneManager when TransformControls finishes a transformation
async function handleTransformEnd(transformedObject) {
    if (!transformedObject) {
        // If nothing was transformed, we should still end the transaction cleanly.
        try { await APIService.endTransaction("Empty transform"); } catch(e) { console.error(e); }
        return;
    }

    const selection = AppState.selectedHierarchyItems;
    const updates = [];

    // This function will now handle all cases: single, multi, and procedural,
    // by calculating the final local transform for every affected object.

    for (const item of selection) {
        if (item.type !== 'physical_volume') continue;

        const pvId = item.canonical_id;
        const pvInstanceId = item.id || pvId;
        
        // Find the THREE.Group for the PV being updated.
        const currentThreeJsObject = SceneManager.findObjectByPvId(pvInstanceId);
        if (!currentThreeJsObject) continue;

        // 1. Get the final world matrix of this instance after the user's drag.
        const newWorldMatrix = currentThreeJsObject.matrixWorld.clone();

        // 2. Get the world matrix of its DIRECT PARENT in the scene graph.
        const parentInverse = new THREE.Matrix4();
        const parentLvName = item.selData.parent_lv_name;
        if (parentLvName !== AppState.currentProjectState.world_volume_ref) {
            if (item.selData.parent_id) {
                const parentThreeJsGroup = SceneManager.findObjectByPvId(item.selData.parent_id);
                if (parentThreeJsGroup) {
                    parentInverse.copy(parentThreeJsGroup.matrixWorld).invert();
                }
            }
        }

        // 3. Calculate the new LOCAL matrix. This is the crucial step.
        // newLocalMatrix = parentWorldMatrix^-1 * newWorldMatrix
        const newLocalMatrix = new THREE.Matrix4().multiplyMatrices(parentInverse, newWorldMatrix);

        // 4. Decompose to get local position, rotation, scale for the backend.
        const pos = new THREE.Vector3();
        const rot = new THREE.Quaternion();
        const scl = new THREE.Vector3();
        newLocalMatrix.decompose(pos, rot, scl);
        const euler = new THREE.Euler().setFromQuaternion(rot, 'XYZ');
        
        updates.push({
            id: pvId, // Send the canonical ID to the backend
            name: null, // Name is not changed here
            position: { x: pos.x, y: pos.y, z: pos.z },
            rotation: { x: -euler.x, y: -euler.y, z: -euler.z },
            scale:    { x: scl.x, y: scl.y, z: scl.z }
        });
    }

    if (updates.length === 0) {
        UIManager.hideLoading();
        return;
    }
    
    //UIManager.showLoading(`Updating ${updates.length} transform(s)...`);
    try {
        const result = await APIService.updatePhysicalVolumeBatch(updates);
        //syncUIWithState(result, AppState.selectedHierarchyItems);
        syncUIWithState_shallow(result);
    } catch (error) {
        UIManager.showError("Error saving transform: " + error.message);
        // Optional: Revert frontend visuals to initialTransforms on error
    } 
    //finally { UIManager.hideLoading();}
}

// Keep this helper function, it's essential
function findPVThatPlacesLV(lvName, projectState) {
    // This helper needs to search ALL placements, including those inside assemblies
    const allPVs = [];
    for (const lv of Object.values(projectState.logical_volumes)) {
        if (lv.content_type === 'physvol') {
            allPVs.push(...lv.content);
        }
    }
    for (const asm of Object.values(projectState.assemblies)) {
        allPVs.push(...asm.placements);
    }
    
    return allPVs.find(pv => pv.volume_ref === lvName);
}

// Called by UIManager when a property is changed in the Inspector Panel
async function handleInspectorPropertyUpdate(objectType, objectId, propertyPath, newValue) {
    const selectionContext = getSelectionContext(); // Get selection BEFORE update
    UIManager.showLoading("Updating property...");
    try {
        const result = await APIService.updateProperty(objectType, objectId, propertyPath, newValue);
        syncUIWithState(result, selectionContext); // Restore selection
    } catch (error) { UIManager.showError("Error updating property: " + error.message); }
    finally { UIManager.hideLoading(); }
}

// Open solid editor to add a solid.
function handleAddSolid() {
    SolidEditor.show(null, AppState.currentProjectState);
}

// Open solid editor for editing.
function handleEditSolid(solidData) {
    // Pass the full project state so the editor knows about other solids
    SolidEditor.show(solidData, AppState.currentProjectState); 
}

async function handleSolidEditorConfirm(data) {
    
    if (data.isEdit) {
        // --- EDIT LOGIC ---
        if (data.isChainedBoolean) {
            UIManager.showLoading("Updating boolean solid...");
            try {
                const result = await APIService.updateBooleanSolid(data.id, data.recipe);
                syncUIWithState(result, [{ type: 'solid', id: data.id, name: data.name, data: data }]);
            } catch (error) {
                UIManager.showError("Error updating boolean solid: " + (error.message || error));
            } finally {
                UIManager.hideLoading();
            }
        } else { // It's a primitive solid
            UIManager.showLoading("Updating solid...");
            try {
                // ## UPDATED: Use the correct key for the API call
                const result = await APIService.updateSolid(data.id, data.params);
                syncUIWithState(result, [{ type: 'solid', id: data.id, name: data.name, data: data }]);
            } catch (error) {
                UIManager.showError("Error updating solid: " + (error.message || error));
            } finally {
                UIManager.hideLoading();
            }
        }

    } else {
        // --- CREATE LOGIC ---
        UIManager.showLoading("Adding object...");
        try {
            
            const solidParams = {
                name: data.name,
                type: data.type,
            };

            // Add either 'recipe' or 'params' based on the solid type
            if (data.isChainedBoolean) {
                solidParams.recipe = data.recipe;
            } else {
                solidParams.params = data.params;
            }

            const lvParams = data.createLV ? { material_ref: data.materialRef } : null;
            let pvParams = null;
            if (data.createLV && data.placePV) {
                // Use the parent name from the dropdown box in the solid editor
                 if (!data.parentLVName) {
                    UIManager.showError("A parent volume must be selected for placement.");
                    UIManager.hideLoading();
                    return;
                }
                pvParams = { parent_lv_name: data.parentLVName };
            }
            
            const result = await APIService.addSolidAndPlace(solidParams, lvParams, pvParams);
            
            // After creation, select the new solid in the hierarchy
            const newSolidName = result.project_state.solids[data.name] ? data.name : Object.keys(result.project_state.solids).find(k => k.startsWith(data.name));
            syncUIWithState(result, [{type: 'solid', id: newSolidName, name: newSolidName}]);

        } catch (error) { 
            UIManager.showError("Error adding solid: " + (error.message || error)); 
        } finally { 
            UIManager.hideLoading(); 
        }
    }
}

function handleAddLV() {
    LVEditor.show(null, AppState.currentProjectState);
}

function handleEditLV(lvData) {
    LVEditor.show(lvData, AppState.currentProjectState);
}

async function handleLVEditorConfirm(data) {
    const selectionContext = getSelectionContext();
    if (data.isEdit) {
        UIManager.showLoading("Updating Logical Volume...");
        try {
            const result = await APIService.updateLogicalVolume(data.id, data.solid_ref, data.material_ref, data.vis_attributes, data.content_type, data.content);
            syncUIWithState(result, selectionContext);
        } catch (error) {
            UIManager.showError("Error updating LV: " + (error.message || error));
        } finally {
            UIManager.hideLoading();
        }
    } else {
        UIManager.showLoading("Creating Logical Volume...");
        try {
            const result = await APIService.addLogicalVolume(data.name, data.solid_ref, data.material_ref, data.vis_attributes, data.content_type, data.content);
            syncUIWithState(result, [{ type: 'logical_volume', id: data.name, name: data.name, data: result.project_state.logical_volumes[data.name] }]);
        } catch (error) { UIManager.showError("Error creating LV: " + (error.message || error)); } 
        finally { UIManager.hideLoading(); }
    }
}

function handleAddPV() {
    let parentContext = UIManager.getSelectedParentContext();

    // If nothing is selected, default to the World volume
    if (!parentContext) {
        if (AppState.currentProjectState && AppState.currentProjectState.world_volume_ref) {
            parentContext = { name: AppState.currentProjectState.world_volume_ref };
            console.log("No parent selected, defaulting to World.");
        } else {
            UIManager.showError("No world volume found to place object into.");
            return;
        }
    }
    
    PVEditor.show(null, null, AppState.currentProjectState, parentContext);
}

function handleEditPV(pvData, lvData) {
    PVEditor.show(pvData, lvData, AppState.currentProjectState);
}

async function handlePVEditorConfirm(data) {
    const selectionContext = getSelectionContext();
    if (data.isEdit) {
        UIManager.showLoading("Updating Physical Volume...");
        try {
            const result = await APIService.updatePhysicalVolume(data.id, data.name, data.position, data.rotation, data.scale);
            syncUIWithState(result, selectionContext);
        } catch (error) { UIManager.showError("Error updating PV: " + (error.message || error)); } 
        finally { UIManager.hideLoading(); }
    } else {
        UIManager.showLoading("Placing Physical Volume...");
        try {
            const result = await APIService.addPhysicalVolume(data.parent_lv_name, data.name, data.volume_ref, data.position, data.rotation, data.scale);
            
            // After placement, we want the PARENT LV to remain selected
            syncUIWithState(result, [{ type: 'logical_volume', id: data.parent_lv_name, name: data.parent_lv_name }]);
        } catch (error) { UIManager.showError("Error placing PV: " + (error.message || error)); } 
        finally { UIManager.hideLoading(); }
    }
}

function handleAddDefine() {
    DefineEditor.show(null, AppState.currentProjectState);
}

function handleEditDefine(defineData) {
    DefineEditor.show(defineData, AppState.currentProjectState);
}

async function handleDefineEditorConfirm(data) {
    const selectionContext = getSelectionContext();
    if (data.isEdit) {
        UIManager.showLoading("Updating Define...");
        try {
            const result = await APIService.updateDefine(data.id, data.raw_expression, data.unit, data.category);
            syncUIWithState(result, selectionContext);
        } catch (error) {
            UIManager.showError("Error updating define: " + (error.message || error));
        } finally { UIManager.hideLoading(); }
    } else {
        UIManager.showLoading("Creating Define...");
        try {
            const result = await APIService.addDefine(data.name, data.type, data.raw_expression, data.unit, data.category);
            
            const newDefineName = result.project_state.defines[data.name] ? data.name : Object.keys(result.project_state.defines).find(k => k.startsWith(data.name));
            syncUIWithState(result, [{ type: 'define', id: newDefineName, name: newDefineName }]);
        } catch (error) {
            UIManager.showError("Error creating define: " + (error.message || error));
        } finally { UIManager.hideLoading(); }
    }
}

function handleAddMaterial() {
    MaterialEditor.show(null, AppState.currentProjectState);
}
function handleEditMaterial(matData) {
    MaterialEditor.show(matData, AppState.currentProjectState);
}

async function handleMaterialEditorConfirm(data) {

    if (data.isEdit) {
        UIManager.showLoading("Updating Material...");
        try {
            const result = await APIService.updateMaterial(data.id, data.params);
            syncUIWithState(result);
        } catch (error) { /* ... */ } 
        finally { UIManager.hideLoading(); }
    } else {
        UIManager.showLoading("Creating Material...");
        try {
            const result = await APIService.addMaterial(data.name, data.params);

            // After creating, set the selection to the newly created material
            syncUIWithState(result, [{ type: 'material', id: data.name, name: data.name }]);
        } catch (error) {
            UIManager.showError("Error creating material: " + (error.message || error));
        } finally {
            UIManager.hideLoading();
        }
    }
}

function handleAddIsotope() { 
    IsotopeEditor.show(null); 
}

function handleEditIsotope(isoData) { 
    IsotopeEditor.show(isoData); 
}

async function handleIsotopeEditorConfirm(data) {
    const selectionContext = getSelectionContext();
    const apiCall = data.isEdit 
        ? APIService.updateIsotope(data.id, data)
        : APIService.addIsotope(data.name, data);

    const loadingMessage = data.isEdit ? "Updating Isotope..." : "Creating Isotope...";
    UIManager.showLoading(loadingMessage);
    try {
        const result = await apiCall;
        
        // Find the final name in case the backend had to make it unique
        const newIsotopeName = Object.keys(result.project_state.isotopes).find(k => k.startsWith(data.name)) || data.name;
        
        const newSelection = [{ 
            type: 'isotope', 
            id: newIsotopeName, 
            name: newIsotopeName, 
            data: result.project_state.isotopes[newIsotopeName] 
        }];
        
        syncUIWithState(result, data.isEdit ? selectionContext : newSelection);
    } catch (error) {
        UIManager.showError("Error processing Isotope: " + (error.message || error));
    } finally {
        UIManager.hideLoading();
    }
}

function handlePVVisibilityToggle(pvId, isVisible, isRecursive = false) {
    // 1. Get the DOM element for the primary PV
    const pvElement = document.querySelector(`#structure_tree_root li[data-instance-id="${pvId}"]`);
    if (!pvElement) return;

    // 2. Toggle visibility for selected element
    SceneManager.setPVVisibility(pvId, isVisible);
    UIManager.setTreeItemVisibility(pvId, isVisible);

    // 3. Find all descendant PV IDs
    let descendantIds = UIManager.getDescendantPvIds(pvElement); // Use the new helper
    
    // 4. If recursive, toggle visibility of all descendants.
    const pvContext = findItemInScene(pvId);
    const isAssemblyContainer = pvContext.selData.is_assembly_container;
    const isProceduralContainer = pvContext.selData.is_procedural_container;
    if(isRecursive || isAssemblyContainer || isProceduralContainer) {
        descendantIds.forEach(id => {
            // Update the 3D scene
            SceneManager.setPVVisibility(id, isVisible);
            // Update the hierarchy UI (the eye icon and dimmed text)
            UIManager.setTreeItemVisibility(id, isVisible);
        });
    }
}

function handleHideSelected() {
    // This now works for multi-select as well
    const selection = AppState.selectedHierarchyItems;
    if (selection.length > 0) {
        selection.forEach(item => {
            if (item.type === 'physical_volume') {
                handlePVVisibilityToggle(item.id, false, false);
            }
        });
    } else {
        UIManager.showNotification("Please select one or more Physical Volumes to hide.");
    }
}

function handleShowSelected() {
    // This now works for multi-select as well
    const selection = AppState.selectedHierarchyItems;
    if (selection.length > 0) {
        selection.forEach(item => {
            if (item.type === 'physical_volume') {
                handlePVVisibilityToggle(item.id, true, false);
            }
        });
    } else {
        UIManager.showNotification("Please select one or more Physical Volumes to show.");
    }
}

function handleHideAll() {
    // 1. Tell the SceneManager to hide all 3D objects.
    SceneManager.setAllPVVisibility(false, AppState.currentProjectState);
    // 2. Tell the UIManager to update the visual state of all hierarchy items.
    UIManager.setAllTreeItemVisibility(false);
}

function handleShowAll() {
    // 1. Tell the SceneManager to show all 3D objects.
    SceneManager.setAllPVVisibility(true, AppState.currentProjectState);
    // 2. Tell the UIManager to update the visual state of all hierarchy items.
    UIManager.setAllTreeItemVisibility(true);
}

/**
 * Checks the AI service status and updates the UI accordingly.
 */
async function checkAndSetAiStatus() {
    // Disable the panel by default while checking
    UIManager.setAiPanelState('disabled', "Checking AI service connection...");
    console.log("Checking AI service status...");

    try {
        const status = await APIService.checkAiServiceStatus();
        if (status.success) {
            UIManager.populateAiModelSelector(status.models);
            UIManager.setAiPanelState('idle', "Generate with AI");
            console.log("AI service is online.");
        } else {
            UIManager.setAiPanelState('disabled', `AI service is offline: ${status.error}`);
            console.error("AI service check failed:", status.error);
        }
    } catch (error) {
        UIManager.setAiPanelState('disabled', `AI service is offline: ${error.message}`);
        console.error("Failed to check AI service status:", error.message);
    }
}

async function handleAiGenerate(promptText) {

    // Get selected model.
    const selectedModel = UIManager.getAiSelectedModel();
    if (!selectedModel || selectedModel === "No models found") {
        UIManager.showError("No AI model is selected or available.");
        return;
    }
    
    if (selectedModel === '--export--') {
        // --- NEW: Call backend to get the prompt ---
        UIManager.showLoading("Building prompt for export...");
        try {
            const fullPromptText = await APIService.getFullAiPrompt(promptText);
            downloadTextFile('ai_prompt.md', fullPromptText);
            UIManager.showNotification("Prompt exported to ai_prompt.md!");
        } catch (error) {
            UIManager.showError("Failed to build prompt: " + (error.message || error));
        } finally {
            UIManager.hideLoading();
        }
        return; // Stop execution here
    }

    // If not exporting, proceed with the API call
    UIManager.showLoading("Sending prompt to AI Assistant...");
    UIManager.setAiPanelState('loading'); // Set loading state
    
    try {
        const result = await APIService.processAiPrompt(promptText, selectedModel);
        syncUIWithState(result); 
        UIManager.clearAiPrompt();
        UIManager.showNotification("AI command processed successfully!");
    } catch (error) {
        UIManager.showError("AI Assistant Error: " + (error.message || error));
    } finally {
        UIManager.hideLoading();
        // Set state back to idle, regardless of success or failure
        UIManager.setAiPanelState('idle'); 
    }
}

// Handler for STEP file import
async function handleImportStep(file) {
    if (!file) return;
    StepImportEditor.show(file, AppState.currentProjectState);
}

// NEW Handlers for the Assembly Definition Editor
function handleAddAssembly() {
    AssemblyEditor.show(null, AppState.currentProjectState);
}

function handleEditAssembly(assemblyData) {
    AssemblyEditor.show(assemblyData, AppState.currentProjectState);
}

async function handleAssemblyEditorConfirm(data) {
    const selectionContext = getSelectionContext();
    if (data.isEdit) {
        UIManager.showLoading("Updating Assembly...");
        try {
            const result = await APIService.updateAssembly(data.id, data.placements);
            syncUIWithState(result, selectionContext);
        } catch (error) { UIManager.showError("Error updating assembly: " + error.message); }
        finally { UIManager.hideLoading(); }
    } else {
        UIManager.showLoading("Creating Assembly...");
        try {
            const result = await APIService.addAssembly(data.name, data.placements);
            const newSelection = [{ type: 'assembly', id: data.name, name: data.name }];
            syncUIWithState(result, newSelection);
        } catch (error) { UIManager.showError("Error creating assembly: " + error.message); }
        finally { UIManager.hideLoading(); }
    }
}

async function handleAddGroup(groupType, groupName) {
    UIManager.showLoading(`Creating group '${groupName}' of type '${groupType}'...`);
    try {
        const result = await APIService.createGroup(groupType, groupName);
        syncUIWithState(result); // This will now correctly redraw the hierarchy
    } catch (error) {
        UIManager.showError("Failed to create group: " + (error.message || error));
    } finally {
        UIManager.hideLoading();
    }
}

async function handleRenameGroup(groupType, oldName, newName) {
    UIManager.showLoading(`Renaming group...`);
    try {
        const result = await APIService.renameGroup(groupType, oldName, newName);
        syncUIWithState(result);
    } catch (error) {
        UIManager.showError("Failed to rename group: " + (error.message || error));
    } finally {
        UIManager.hideLoading();
    }
}

async function handleDeleteGroup(groupType, groupName) {
    UIManager.showLoading(`Deleting group '${groupName}'...`);
    try {
        const result = await APIService.deleteGroup(groupType, groupName);
        syncUIWithState(result);
    } catch (error) {
        UIManager.showError("Failed to delete group: " + (error.message || error));
    } finally {
        UIManager.hideLoading();
    }
}

async function handleMoveItemsToGroup(groupType, itemIds, targetGroupName) {
    const selectionContext = getSelectionContext();
    UIManager.showLoading(`Moving ${itemIds.length} item(s)...`);
    try {
        const result = await APIService.moveItemsToGroup(groupType, itemIds, targetGroupName);
        syncUIWithState(result, selectionContext); // Restore selection after move
    } catch (error) {
        UIManager.showError("Failed to move items: " + (error.message || error));
    } finally {
        UIManager.hideLoading();
    }
}

// Assembly functions
async function handleGroupIntoAssembly() {
    const selectionContexts = getSelectionContext();
    if (!selectionContexts || selectionContexts.length === 0) {
        UIManager.showError("Please select one or more Physical Volumes to group into an assembly.");
        return;
    }

    // Ensure all selected items are physical volumes
    const pvItems = selectionContexts.filter(item => item.type === 'physical_volume');
    if (pvItems.length !== selectionContexts.length) {
        UIManager.showError("You can only group Physical Volumes into an assembly. Please adjust your selection.");
        return;
    }

    const parentContext = UIManager.getSelectedParentContext();
    if (!parentContext) {
        UIManager.showError("Could not determine a parent volume for the new assembly. Please select the items from within a single parent volume.");
        return;
    }
    const parentLvName = parentContext.data.name || parentContext.name;
    
    const assemblyName = prompt("Enter a name for the new assembly:", "MyAssembly");
    if (!assemblyName || !assemblyName.trim()) {
        return; // User cancelled
    }

    const pvIds = pvItems.map(item => item.id);

    UIManager.showLoading("Creating assembly...");
    try {
        const result = await APIService.createAssemblyFromPVs(pvIds, assemblyName.trim(), parentLvName);
        // After creation, we want to select the new assembly's placement
        const newAssemblyPV = findPlacementOfVolume(result.project_state, assemblyName.trim());
        syncUIWithState(result, newAssemblyPV ? [newAssemblyPV] : []);
    } catch (error) {
        UIManager.showError("Failed to create assembly: " + (error.message || error));
    } finally {
        UIManager.hideLoading();
    }
}

// Helper to find the new assembly's PV after creation
function findPlacementOfVolume(projectState, volumeRefName) {
    for (const lv of Object.values(projectState.logical_volumes)) {
        if (lv.content_type === 'physvol') {
            for (const pv of lv.content) {
                if (pv.volume_ref === volumeRefName) {
                    return { type: 'physical_volume', id: pv.id, name: pv.name, data: pv };
                }
            }
        }
    }
    return null;
}

async function handleMovePvToAssembly(pvId, assemblyName) {
    UIManager.showLoading(`Moving PV to assembly '${assemblyName}'...`);
    try {
        const result = await APIService.movePvToAssembly(pvId, assemblyName);
        syncUIWithState(result); // This redraws everything
    } catch (error) {
        UIManager.showError("Failed to move PV: " + error.message);
    } finally {
        UIManager.hideLoading();
    }
}

async function handleMovePvToLv(pvId, lvName) {
    UIManager.showLoading(`Moving PV to volume '${lvName}'...`);
    try {
        const result = await APIService.movePvToLv(pvId, lvName);
        syncUIWithState(result);
    } catch (error) {
        UIManager.showError("Failed to move PV: " + error.message);
    } finally {
        UIManager.hideLoading();
    }
}

function handleAddOpticalSurface() {
    OpticalSurfaceEditor.show(null, AppState.currentProjectState);
}

function handleEditOpticalSurface(osData) {
    OpticalSurfaceEditor.show(osData, AppState.currentProjectState);
}

async function handleOpticalSurfaceEditorConfirm(data) {
    const selectionContext = getSelectionContext();
    // These API functions don't exist yet, but we are setting up the frontend for them
    const apiCall = data.isEdit 
        ? APIService.updateOpticalSurface(data.id, data)
        : APIService.addOpticalSurface(data.name, data);

    const loadingMessage = data.isEdit ? "Updating Optical Surface..." : "Creating Optical Surface...";
    UIManager.showLoading(loadingMessage);
    try {
        const result = await apiCall;
        const newSelection = [{ type: 'optical_surface', id: data.name, name: data.name, data: result.project_state.optical_surfaces[data.name] }];
        syncUIWithState(result, data.isEdit ? selectionContext : newSelection);
    } catch (error) {
        UIManager.showError("Error processing Optical Surface: " + (error.message || error));
    } finally {
        UIManager.hideLoading();
    }
}

function handleAddSkinSurface() {
    SkinSurfaceEditor.show(null, AppState.currentProjectState);
}

function handleEditSkinSurface(ssData) {
    SkinSurfaceEditor.show(ssData, AppState.currentProjectState);
}

async function handleSkinSurfaceEditorConfirm(data) {
    const selectionContext = getSelectionContext();
    // These API functions will be created in the next step
    const apiCall = data.isEdit 
        ? APIService.updateSkinSurface(data.id, data)
        : APIService.addSkinSurface(data.name, data);

    const loadingMessage = data.isEdit ? "Updating Skin Surface..." : "Creating Skin Surface...";
    UIManager.showLoading(loadingMessage);
    try {
        const result = await apiCall;
        const newSelection = [{ type: 'skin_surface', id: data.name, name: data.name, data: result.project_state.skin_surfaces[data.name] }];
        syncUIWithState(result, data.isEdit ? selectionContext : newSelection);
    } catch (error) {
        UIManager.showError("Error processing Skin Surface: " + (error.message || error));
    } finally {
        UIManager.hideLoading();
    }
}

function handleAddBorderSurface() {
    BorderSurfaceEditor.show(null, AppState.currentProjectState);
}

function handleEditBorderSurface(bsData) {
    BorderSurfaceEditor.show(bsData, AppState.currentProjectState);
}

async function handleBorderSurfaceEditorConfirm(data) {
    const selectionContext = getSelectionContext();
    // These API functions will be created in the next step
    const apiCall = data.isEdit 
        ? APIService.updateBorderSurface(data.id, data)
        : APIService.addBorderSurface(data.name, data);

    const loadingMessage = data.isEdit ? "Updating Border Surface..." : "Creating Border Surface...";
    UIManager.showLoading(loadingMessage);
    try {
        const result = await apiCall;
        const newSelection = [{ type: 'border_surface', id: data.name, name: data.name, data: result.project_state.border_surfaces[data.name] }];
        syncUIWithState(result, data.isEdit ? selectionContext : newSelection);
    } catch (error) {
        UIManager.showError("Error processing Border Surface: " + (error.message || error));
    } finally {
        UIManager.hideLoading();
    }
}

function handleAddElement() {
    ElementEditor.show(null, AppState.currentProjectState);
}

function handleEditElement(elData) {
    ElementEditor.show(elData, AppState.currentProjectState);
}

async function handleElementEditorConfirm(data) {
    const selectionContext = getSelectionContext();
    const apiCall = data.isEdit 
        ? APIService.updateElement(data.id, data)
        : APIService.addElement(data.name, data);

    const loadingMessage = data.isEdit ? "Updating Element..." : "Creating Element...";
    UIManager.showLoading(loadingMessage);
    try {
        const result = await apiCall;
        const newElementName = Object.keys(result.project_state.elements).find(k => k.startsWith(data.name)) || data.name;
        const newSelection = [{ type: 'element', id: newElementName, name: newElementName, data: result.project_state.elements[newElementName] }];
        syncUIWithState(result, data.isEdit ? selectionContext : newSelection);
    } catch (error) {
        UIManager.showError("Error processing Element: " + (error.message || error));
    } finally {
        UIManager.hideLoading();
    }
}

/**
 * Checks if a given item from a selection context still exists in a new project state.
 * @param {object} itemContext - The item to check { type, id, name, data }.
 * @param {object} newState - The full project state object to check against.
 * @returns {boolean} - True if the item exists, false otherwise.
 */
function doesItemExistInState(itemContext, newState) {
    const { type, id, name } = itemContext; // 'name' and 'id' are often the same
    if (!newState || !type || !id) return false;

    switch (type) {
        case 'physical_volume':
            // Must search all possible parents for the PV's ID
            for (const lv of Object.values(newState.logical_volumes || {})) {
                if (lv.content_type === 'physvol' && lv.content.some(pv => pv.id === id)) {
                    return true;
                }
            }
            for (const asm of Object.values(newState.assemblies || {})) {
                if (asm.placements.some(pv => pv.id === id)) {
                    return true;
                }
            }
            return false; // Not found in any LV or Assembly

        // For all other types, the ID is the name, so we can do a direct lookup.
        case 'logical_volume':
            return !!newState.logical_volumes?.[name];
        case 'assembly':
            return !!newState.assemblies?.[name];
        case 'solid':
            return !!newState.solids?.[name];
        case 'material':
            return !!newState.materials?.[name];
        case 'element':
            return !!newState.elements?.[name];
        case 'isotope':
            return !!newState.isotopes?.[name];
        case 'define':
            return !!newState.defines?.[name];
        case 'optical_surface':
            return !!newState.optical_surfaces?.[name];
        case 'skin_surface':
            return !!newState.skin_surfaces?.[name];
        case 'border_surface':
            return !!newState.border_surfaces?.[name];

        default:
            return false;
    }
}

function handleCameraModeChange(mode) {
    if (mode === 'origin') {
        // Center the camera on the world origin
        SceneManager.centerCameraOn(null); // Passing null resets to (0,0,0)
        UIManager.setActiveCameraModeButton('origin');
    } else if (mode === 'selected') {
        const selection = AppState.selectedThreeObjects;
        
        if (selection && selection.length > 0) {
            let target; // This will be either a single object or a Vector3 for the center

            if (selection.length === 1) {
                // If only one object is selected, target it directly.
                target = selection[0];
            } else {
                // --- NEW ROBUST LOGIC for MULTI-SELECT ---
                // If multiple objects are selected, calculate their collective center.
                // This works regardless of the current mode or if the gizmo is visible.
                const multiSelectBox = new THREE.Box3();
                
                selection.forEach(obj => {
                    // Important: Ensure the object's bounding box is up-to-date with its world matrix
                    const box = new THREE.Box3().setFromObject(obj);
                    multiSelectBox.union(box); // Expand the main box to include this object's box
                });
                
                // The target is now the center of this combined bounding box.
                target = new THREE.Vector3();
                multiSelectBox.getCenter(target);
            }

            // Set the new camera center.
            SceneManager.centerCameraOn(target);

            // Update the menu buttons.
            UIManager.setActiveCameraModeButton('selected');
        } else {
            UIManager.showNotification("Please select an object to center the camera on.");
        }
    }
}

async function handleConfirmStepImport(options) {
    if (!options || !options.file) return;

    UIManager.showLoading(`Importing ${options.file.name}... This may take a moment.`);
    
    try {
        const formData = new FormData();
        formData.append('stepFile', options.file);

        // We send the rest of the options, but remove the file object itself
        // as it's already been appended.
        const optionsForJson = { ...options };
        delete optionsForJson.file;
        formData.append('options', JSON.stringify(options));
        
        const result = await APIService.importStepWithOptions(formData); // This API call is still needed
        syncUIWithState(result);
        UIManager.hideLoading();
        //UIManager.showNotification("STEP file imported successfully.");
    } catch (error) {
        UIManager.hideLoading();
        UIManager.showError("Failed to import STEP file: " + error.message);
    } finally {
        document.getElementById('stepFile').value = null;
    }
}

