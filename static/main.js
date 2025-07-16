// static/main.js
import * as THREE from 'three';

import * as APIService from './apiService.js';
import * as DefineEditor from './defineEditor.js';
import * as InteractionManager from './interactionManager.js';
import * as LVEditor from './logicalVolumeEditor.js';
import * as MaterialEditor from './materialEditor.js';
import * as PVEditor from './physicalVolumeEditor.js';
import * as SceneManager from './sceneManager.js';
import * as SolidEditor from './solidEditor.js';
import * as UIManager from './uiManager.js';

// --- Global Application State (Keep this minimal) ---
const AppState = {
    currentProjectState: null,    // Full state dict from backend (defines, materials, solids, LVs, world_ref)
    selectedHierarchyItems: [],   // array of { type, id, name, data (raw from projectState) }
    selectedThreeObjects: [],     // Managed by SceneManager, but AppState might need to know for coordination
    selectedPVContext: {
        pvId: null,
        positionDefineName: null,
        rotationDefineName: null,
    }
};

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
        // Add/edit solids
        onAddSolidClicked: handleAddSolid,
        onEditSolidClicked: handleEditSolid,
        // Add/edit defines
        onAddDefineClicked: handleAddDefine,
        onEditDefineClicked: handleEditDefine,
        // Add/edit materials
        onAddMaterialClicked: handleAddMaterial,
        onEditMaterialClicked: handleEditMaterial,
        // Add/edit LVs
        onAddLVClicked: handleAddLV,
        onEditLVClicked: handleEditLV,
        // Add/edit PVs
        onAddPVClicked: handleAddPV,
        onEditPVClicked: handleEditPV,
        // Add assembly
        onAddAssemblyClicked: handleAddAssembly,
        onPVVisibilityToggle: handlePVVisibilityToggle,
        onDeleteSelectedClicked: handleDeleteSelected,
        onDeleteSpecificItemClicked: handleDeleteSpecificItem,
        onExportGdmlClicked: handleExportGdml,
        onConfirmAddObject: handleAddObject, // Data from modal comes to this handler
        onDeleteSelectedClicked: handleDeleteSelected,
        onModeChangeClicked: handleModeChange, // Passes mode to InteractionManager
        onSnapToggleClicked: InteractionManager.toggleSnap, // Direct call if no complex logic
        onSnapSettingsChanged: InteractionManager.updateSnapSettings,
        onCameraModeChangeClicked: SceneManager.setCameraMode,
        onWireframeToggleClicked: SceneManager.toggleGlobalWireframe,
        onGridToggleClicked: SceneManager.toggleGridVisibility,
        onAxesToggleClicked: SceneManager.toggleAxesVisibility,
        onHierarchySelectionChanged: handleHierarchySelection,
        onHierarchyItemSelected: handleHierarchySelection, // When an item in hierarchy panel is clicked
        onInspectorPropertyChanged: handleInspectorPropertyUpdate, // When a property in inspector is changed by user
        onAiGenerateClicked: handleAiGenerate,
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
        onObjectTransformLive: handleTransformLive,       // Live transformations
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
        SceneManager.getFlyControls()        // Pass the FlyControls instance
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

    // Initialize the materials editor
    MaterialEditor.initMaterialEditor({
        onConfirm: handleMaterialEditorConfirm
    });

    // Initialize physical volume editor
    PVEditor.initPVEditor({ 
        onConfirm: handlePVEditorConfirm 
    });

    // Initialize solid editor
    SolidEditor.initSolidEditor({
        onConfirm: handleSolidEditorConfirm
    });

    // Add menu listeners
    document.getElementById('hideSelectedBtn').addEventListener('click', handleHideSelected);
    document.getElementById('showAllBtn').addEventListener('click', handleShowAll);

    // --- Check AI service status on startup ---
    checkAndSetAiStatus();

    // Restore session from backend on page load
    console.log("Fetching initial project state from backend...");
    const initialState = await APIService.getProjectState();
    // No try/catch needed, as the backend now guarantees a valid response
    if (initialState && initialState.project_state) {
        console.log("Initializing UI with project state.");
        // We use a simplified sync function here as the structure is slightly different
        AppState.currentProjectState = initialState.project_state;
        UIManager.updateHierarchy(initialState.project_state);
        SceneManager.renderObjects(initialState.scene_update || [], initialState.project_state);
    } else {
        // This case should theoretically not be reached anymore, but is good for safety
        UIManager.showError("Failed to retrieve a valid project state from the server.");
    }

    console.log("Application Initialized.");
    
    // Example: Fetch initial empty state or last saved state if implemented
    // try {
    //     const initialState = await APIService.getProjectState();
    //     if (initialState && Object.keys(initialState).length > 0 && initialState.world_volume_ref) {
    //         AppState.currentProjectState = initialState;
    //         UIManager.updateHierarchy(initialState);
    //         const threeJSDesc = APIService.extractThreeJSDescription(initialState); // Helper might be needed
    //         SceneManager.renderObjects(threeJSDesc || []);
    //     }
    // } catch (error) {
    //     console.warn("No initial project state found or error loading:", error);
    // }
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

    // 1. Update the global AppState cache
    AppState.currentProjectState = responseData.project_state;
    AppState.selectedHierarchyItem = null; // Clear old selections
    AppState.selectedThreeObjects = [];
    AppState.selectedPVContext.pvId = null;

    // 2. Re-render the 3D scene
    if (responseData.scene_update) {
        SceneManager.renderObjects(responseData.scene_update, responseData.project_state);
    } else {
        SceneManager.clearScene(); // Ensure scene is cleared if there's no update
    }

    // 3. Re-render the hierarchy panels
    UIManager.updateHierarchy(responseData.project_state);

    // 4. Restore selection and repopulate inspector ---
    if (selectionToRestore && selectionToRestore.length > 0) {
        // Extract just the IDs to pass to the UI manager
        const idsToSelect = selectionToRestore.map(item => item.id);
        UIManager.setHierarchySelection(idsToSelect); // Use the existing function!

        // After setting the visual selection, we still need to trigger the main
        // handler to update the inspector, gizmo, etc.
        // We'll pass the full context array to it.
        handleHierarchySelection(selectionToRestore);
        
    } else {
        // If no selection to restore, clear everything
        UIManager.clearInspector();
        UIManager.clearHierarchySelection();
        SceneManager.unselectAllInScene();
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
    let currentSelection = isCtrlHeld ? [...AppState.selectedHierarchyItems] : [];
    const currentIds = new Set(currentSelection.map(item => item.id));

    // Add new items from the box selection, avoiding duplicates
    selectedMeshes.forEach(mesh => {
        if (!currentIds.has(mesh.userData.id)) {
            currentSelection.push({
                type: 'physical_volume',
                id: mesh.userData.id,
                name: mesh.userData.name,
                data: mesh.userData
            });
        }
    });

    // Sync the hierarchy list UI
    const newSelectedIds = currentSelection.map(item => item.id);
    UIManager.setHierarchySelection(newSelectedIds);

    // Call the main handler to update the rest of the app state
    handleHierarchySelection(currentSelection);
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
    } catch (error) { 
        UIManager.showError("Failed to open GDML Project: " + (error.message || error));
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
    } catch (error) { 
        UIManager.showError("Failed to import GDML Part: " + (error.message || error));
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

    // Create a confirmation message
    let confirmationMessage;
    if (selectionContexts.length === 1) {
        confirmationMessage = `Are you sure you want to delete ${selectionContexts[0].type}: ${selectionContexts[0].name}?`;
    } else {
        confirmationMessage = `Are you sure you want to delete ${selectionContexts.length} items?`;
    }

    if (!UIManager.confirmAction(confirmationMessage)) return;

    UIManager.showLoading(`Deleting ${selectionContexts.length} item(s)...`);
    try {
        let lastResult;
        // Loop through all selected items and delete them one by one.
        for (const context of selectionContexts) {
            lastResult = await APIService.deleteObject(context.type, context.id);
            // If any deletion fails, we can stop and report it.
            if (!lastResult.success) {
                UIManager.showError(`Failed to delete ${context.type} ${context.id}: ${lastResult.error}`);
                break; // Stop the loop on the first error
            }
        }
        
        // After all deletions are done (or on the first failure),
        // sync the UI with the state from the last successful operation.
        if (lastResult) {
            syncUIWithState(lastResult); // No selection to restore after deletion
        } else {
            // This case might happen if the loop doesn't run, though unlikely
             UIManager.hideLoading();
        }

    } catch (error) { 
        UIManager.showError("An error occurred during deletion: " + error.message); 
        UIManager.hideLoading();
    }
}

// NEW handler for specific deletions from button clicks
async function handleDeleteSpecificItem(type, id) {
    UIManager.showLoading("Deleting object...");
    try {
        const result = await APIService.deleteObject(type, id);
        syncUIWithState(result);
    } catch (error) { UIManager.showError("Error deleting object: " + error.message); }
    finally { UIManager.hideLoading(); }
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

// Replace the handleHierarchySelection function
async function handleHierarchySelection(newSelection) {
    console.log("Hierarchy selection changed. New selection count:", newSelection.length);
    AppState.selectedHierarchyItems = newSelection;

    // --- 1. Build the list of meshes to highlight/transform ---
    const meshesToProcess = [];
    newSelection.forEach(item => {
        if (item.type === 'physical_volume') {
            const lv = AppState.currentProjectState.logical_volumes[item.data.volume_ref];
            if (lv && lv.content_type !== 'physvol') {
                // Procedural PV: get all its instances.
                meshesToProcess.push(...SceneManager.getMeshesForOwner(item.id));
            } else {
                // Simple PV: get its single mesh.
                const mesh = SceneManager.findMeshByPvId(item.id);
                if (mesh) meshesToProcess.push(mesh);
            }
        }
    });

    // --- 2. Update the 3D Scene (Visuals and Gizmo) ---
    SceneManager.updateSelectionState(meshesToProcess);
    AppState.selectedThreeObjects = meshesToProcess;
    
    // Consolidate the gizmo logic. Always detach first, then attach if needed.
    SceneManager.getTransformControls().detach();
    if (InteractionManager.getCurrentMode() !== 'observe' && meshesToProcess.length > 0) {
        SceneManager.attachTransformControls(meshesToProcess);
    }

    // --- 3. Update the UI (Hierarchy List and Inspector) ---
    const selectedIds = newSelection.map(item => item.id);
    UIManager.setHierarchySelection(selectedIds);

    if (newSelection.length === 1) {
        const singleItem = newSelection[0];
        const { type, id, name } = singleItem;
        const idForApi = (type === 'physical_volume') ? id : name;

        // The getObjectDetails and populateInspector logic can now proceed
        try {
            const details = await APIService.getObjectDetails(type, idForApi);
            if (details) {
                singleItem.data = details; // Ensure data is up-to-date
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
    
    let clickedItemCanonicalId = null;
    if (clickedMesh) {
        const userData = clickedMesh.userData;
        clickedItemCanonicalId = (userData.owner_pv_id && userData.owner_pv_id !== userData.id) 
                                 ? userData.owner_pv_id 
                                 : userData.id;
    }

    if (clickedItemCanonicalId) {
        const existingIndex = currentSelection.findIndex(item => item.id === clickedItemCanonicalId);

        if (isCtrlHeld) {
            if (existingIndex > -1) {
                currentSelection.splice(existingIndex, 1);
            } else {
                const newItem = findItemInState(clickedItemCanonicalId);
                if (newItem) currentSelection.push(newItem);
            }
        } else {
            const newItem = findItemInState(clickedItemCanonicalId);
            currentSelection = newItem ? [newItem] : [];
        }
    } else if (!isCtrlHeld) {
        currentSelection = [];
    }
    
    // Now that we have the final list of selected items, trigger the main handler.
    // This becomes the single point of truth for updating the UI, inspector, and 3D scene.
    handleHierarchySelection(currentSelection);
}

// Helper function to find a PV by its ID anywhere in the project state
function findItemInState(itemId) {
    // Search PVs
    for (const lv of Object.values(AppState.currentProjectState.logical_volumes)) {
        if (lv.content_type === 'physvol') {
            const found = lv.content.find(pv => pv.id === itemId);
            if (found) return { type: 'physical_volume', id: found.id, name: found.name, data: found };
        }
    }
    // Add searches for other types if needed in the future...
    return null;
}

function handleTransformLive(liveObject) {
    // 1. Update the PV's own inspector (if it has inline values)
    if (AppState.selectedHierarchyItem && AppState.selectedHierarchyItem.id === liveObject.userData.id) {
        UIManager.updateInspectorTransform(liveObject);
    }

    // 2. If the transform is linked to a define, update THAT define's inspector
    const euler = new THREE.Euler().setFromQuaternion(liveObject.quaternion, 'ZYX');
    const newPosition = { x: liveObject.position.x, y: liveObject.position.y, z: liveObject.position.z };
    const newRotation = { x: euler.x, y: euler.y, z: euler.z };

    if (AppState.selectedPVContext.positionDefineName) {
        UIManager.updateDefineInspectorValues(AppState.selectedPVContext.positionDefineName, newPosition);
    }
    if (AppState.selectedPVContext.rotationDefineName) {
        UIManager.updateDefineInspectorValues(AppState.selectedPVContext.rotationDefineName, newRotation, true); // true for rotation
    }
}

// Called by SceneManager when TransformControls finishes a transformation
async function handleTransformEnd(transformedObject, initialTransforms, wasHelperTransformed) {
    if (!transformedObject) return;

    const updates = [];
    const selection = AppState.selectedHierarchyItems;

    if (wasHelperTransformed) {
        // --- This was the GIZMO HELPER (multi-select or procedural group) ---

        if (selection.length === 1 && selection[0].type === 'physical_volume') {
            // --- CASE 1: A SINGLE PROCEDURAL GROUP (like a replica) WAS MOVED ---
            // The helper's final world position IS the new world position for the owning PV.
            const pvId = selection[0].id;
            const pos = transformedObject.position;
            const euler = new THREE.Euler().setFromQuaternion(transformedObject.quaternion, 'ZYX');
            updates.push({
                pvId: pvId,
                position: { x: pos.x, y: pos.y, z: pos.z },
                rotation: { x: euler.x, y: euler.y, z: euler.z }
            });

        } else {
            // --- CASE 2: A STANDARD MULTI-SELECTION OF SIMPLE PVs WAS MOVED ---
            const helperStart = initialTransforms.get('helper');
            if (!helperStart) return;

            const helperEndMatrix = transformedObject.matrixWorld;
            const helperStartMatrixInv = new THREE.Matrix4().copy(helperStart.matrixWorld).invert();
            const deltaMatrix = new THREE.Matrix4().multiplyMatrices(helperEndMatrix, helperStartMatrixInv);

            for (const item of selection) {
                if (item.type === 'physical_volume') {
                    const initialMesh = initialTransforms.get(item.id);
                    if (initialMesh) {
                        const finalMatrix = new THREE.Matrix4().multiplyMatrices(deltaMatrix, initialMesh.matrixWorld);
                        const pos = new THREE.Vector3();
                        const rot = new THREE.Quaternion();
                        const scl = new THREE.Vector3();
                        finalMatrix.decompose(pos, rot, scl);
                        const euler = new THREE.Euler().setFromQuaternion(rot, 'ZYX');

                        updates.push({
                            pvId: item.id,
                            position: { x: pos.x, y: pos.y, z: pos.z },
                            rotation: { x: euler.x, y: euler.y, z: euler.z }
                        });
                    }
                }
            }
        }
    } else if (transformedObject.userData.id) {
        // --- CASE 3: A SINGLE standard physical volume was moved directly ---
        const pvId = transformedObject.userData.id;
        const pos = transformedObject.position;
        const euler = new THREE.Euler().setFromQuaternion(transformedObject.quaternion, 'ZYX');
        updates.push({
            pvId: pvId,
            position: { x: pos.x, y: pos.y, z: pos.z },
            rotation: { x: euler.x, y: euler.y, z: euler.z }
        });
    }

    if (updates.length === 0) return;

    UIManager.showLoading(`Updating ${updates.length} transform(s)...`);
    try {
        let lastResult;
        for (const update of updates) {
            // This loop now correctly handles all cases: single, multi-select, and procedural group.
            lastResult = await APIService.updatePhysicalVolume(update.pvId, null, update.position, update.rotation);
            if (!lastResult.success) {
                UIManager.showError(`Failed to update ${update.pvId}: ${lastResult.error}`);
                break;
            }
        }
        if (lastResult) {
            syncUIWithState(lastResult, AppState.selectedHierarchyItems);
        }
    } catch (error) {
        UIManager.showError("Error saving transform: " + error.message);
    } finally {
        UIManager.hideLoading();
    }
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
    console.log("Editing solid:", solidData);
    // Pass the full project state so the editor knows about other solids
    SolidEditor.show(solidData, AppState.currentProjectState); 
}

async function handleSolidEditorConfirm(data) {
    console.log("Solid Editor confirmed. Data:", data);
    
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
                const parentContext = UIManager.getSelectedParentContext();
                const parentName = (parentContext && parentContext.name) 
                                   ? parentContext.name 
                                   : AppState.currentProjectState.world_volume_ref;
                pvParams = { parent_lv_name: parentName };
            }
            
            const result = await APIService.addSolidAndPlace(solidParams, lvParams, pvParams);
            
            // After creation, select the new solid in the hierarchy
            const newSolidName = result.project_state.solids[data.name] ? data.name : Object.keys(result.project_state.solids).find(k => k.startsWith(data.name));
            syncUIWithState(result, [{type: 'solid', id: newSolidName}]);

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
            const result = await APIService.updateLogicalVolume(data.id, data.solid_ref, data.material_ref, data.vis_attributes);
            syncUIWithState(result, selectionContext);
        } catch (error) {
            UIManager.showError("Error updating LV: " + (error.message || error));
        } finally {
            UIManager.hideLoading();
        }
    } else {
        UIManager.showLoading("Creating Logical Volume...");
        try {
            const result = await APIService.addLogicalVolume(data.name, data.solid_ref, data.material_ref, data.vis_attributes);
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
    
    PVEditor.show(null, AppState.currentProjectState, parentContext);
}

function handleEditPV(pvData, parentLVName) {
    PVEditor.show(pvData, AppState.currentProjectState, { name: parentLVName });
}

async function handlePVEditorConfirm(data) {
    const selectionContext = getSelectionContext();
    if (data.isEdit) {
        UIManager.showLoading("Updating Physical Volume...");
        try {
            const result = await APIService.updatePhysicalVolume(data.id, data.name, data.position, data.rotation);
            syncUIWithState(result, selectionContext);
        } catch (error) { UIManager.showError("Error updating PV: " + (error.message || error)); } 
        finally { UIManager.hideLoading(); }
    } else {
        UIManager.showLoading("Placing Physical Volume...");
        try {
            const result = await APIService.addPhysicalVolume(data.parent_lv_name, data.name, data.volume_ref, data.position, data.rotation);
            
            // After placement, we want the PARENT LV to remain selected
            syncUIWithState(result, [{ type: 'logical_volume', id: data.parent_lv_name }]);
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
    const selectionContext = getSelectionContext();

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
            syncUIWithState(result, [{ type: 'material', id: data.name }]);
        } catch (error) {
            UIManager.showError("Error creating material: " + (error.message || error));
        } finally {
            UIManager.hideLoading();
        }
    }
}

function handlePVVisibilityToggle(pvId, isVisible) {
    // Update the visibility in the 3D scene
    SceneManager.setPVVisibility(pvId, isVisible);

    // --- Check if the hidden object has the gizmo attached ---
    if (!isVisible) {
        const selectedObjects = SceneManager.getSelectedObjects();
        if (selectedObjects.length === 1 && selectedObjects[0].userData.id === pvId) {
            // The object we just hid is the selected one. Detach the gizmo.
            console.log("Hiding selected object, detaching transform controls.");
            handleModeChange('observe');
        }
    }
}

function handleHideSelected() {
    if (AppState.selectedHierarchyItem && AppState.selectedHierarchyItem.type === 'physical_volume') {
        const pvId = AppState.selectedHierarchyItem.id;
        // This function now automatically handles detaching the gizmo
        handlePVVisibilityToggle(pvId, false);
        UIManager.setTreeItemVisibility(pvId, false);
    } else {
        UIManager.showNotification("Please select a Physical Volume to hide.");
    }
}

function handleShowAll() {
    SceneManager.setAllPVVisibility(true);
    // Update all UI elements
    UIManager.setAllTreeItemVisibility(true); // Need to add this helper to uiManager
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
    UIManager.showLoading("Importing and Tessellating STEP file... This may take some time for large files. Please do not navigate away from this tab.");
    try {
        const result = await APIService.importStepFile(file);
        // The backend returns a full state update, so we can just sync
        syncUIWithState(result);
        UIManager.showNotification("STEP geometry imported successfully as new solids and logical volumes. You can now place them in the world.");
    } catch (error) {
        UIManager.showError("Failed to import STEP file: " + (error.message || error));
    } finally {
        // Reset the file input so the user can upload the same file again if they want
        document.getElementById('stepFile').value = null;
        UIManager.hideLoading();
    }
}

async function handleAddAssembly() {
    const selectionContexts = getSelectionContext();
    if (!selectionContexts || selectionContexts.length !== 1 || selectionContexts[0].type !== 'assembly') {
        UIManager.showError("Please select a single Assembly to place.");
        return;
    }
    const assemblyName = selectionContexts[0].name;

    let parentContext = UIManager.getSelectedParentContext();
    if (!parentContext) {
        parentContext = { name: AppState.currentProjectState.world_volume_ref };
    }
    const parentLVName = parentContext.name;

    const placementName = prompt(`Enter a base name for this placement of '${assemblyName}':`, `${assemblyName}_placement`);
    if (!placementName) return;

    UIManager.showLoading(`Placing assembly '${assemblyName}' into '${parentLVName}'...`);
    try {
        const result = await APIService.addAssemblyPlacement(
            parentLVName,
            assemblyName,
            placementName,
            { x: 0, y: 0, z: 0 }, // Default placement at origin
            { x: 0, y: 0, z: 0 }
        );
        syncUIWithState(result, [{ type: 'logical_volume', id: parentLVName }]); // Reselect parent
    } catch (error) {
        UIManager.showError("Failed to place assembly: " + error.message);
    } finally {
        UIManager.hideLoading();
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