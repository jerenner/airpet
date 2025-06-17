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
    selectedHierarchyItem: null,  // { type, id, name, data (raw from projectState) }
    selectedThreeObjects: [],      // Managed by SceneManager, but AppState might need to know for coordination
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
        onLoadGdmlClicked: () => UIManager.triggerFileInput('gdmlFile'), // UIManager handles its own file input now
        onLoadProjectClicked: () => UIManager.triggerFileInput('projectFile'),
        onGdmlFileSelected: handleLoadGdml, // Files are passed to handlers
        onAddSolidClicked: handleAddSolid,
        onEditSolidClicked: handleEditSolid,
        onAddDefineClicked: handleAddDefine,
        onEditDefineClicked: handleEditDefine,
        onAddMaterialClicked: handleAddMaterial,
        onEditMaterialClicked: handleEditMaterial,
        onAddLVClicked: handleAddLV,
        onEditLVClicked: handleEditLV,
        onAddPVClicked: handleAddPV,
        onEditPVClicked: handleEditPV,
        onProjectFileSelected: handleLoadProject,
        onSaveProjectClicked: handleSaveProject,
        onExportGdmlClicked: handleExportGdml,
        onConfirmAddObject: handleAddObject, // Data from modal comes to this handler
        onDeleteSelectedClicked: handleDeleteSelected,
        onModeChangeClicked: handleModeChange, // Passes mode to InteractionManager
        onSnapToggleClicked: InteractionManager.toggleSnap, // Direct call if no complex logic
        onSnapSettingsChanged: InteractionManager.updateSnapSettings,
        onCameraModeChangeClicked: SceneManager.setCameraMode,
        onWireframeToggleClicked: SceneManager.toggleGlobalWireframe,
        onGridToggleClicked: SceneManager.toggleGridVisibility,
        onHierarchyItemSelected: handleHierarchySelection, // When an item in hierarchy panel is clicked
        onInspectorPropertyChanged: handleInspectorPropertyUpdate, // When a property in inspector is changed by user
    });

    // Initialize the 3D scene and its controls
    SceneManager.initScene({
        onObjectSelectedIn3D: handle3DSelection,          // Callback when object clicked in 3D scene
        onObjectTransformEnd: handleTransformEnd,          // Callback when TransformControls drag/rotate/scale ends
        onObjectTransformLive: handleTransformLive,       // Live transformations
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
        onConfirm: handleDefineEditorConfirm 
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
 * Gets the context of the currently selected item.
 * @returns {object|null} An object with {type, id} or null.
 */
function getSelectionContext() {
    if (!AppState.selectedHierarchyItem) return null;
    return {
        type: AppState.selectedHierarchyItem.type,
        id: AppState.selectedHierarchyItem.id
    };
}

/**
    The single function to update the entire UI from a new state object from the backend.
    This is the core of the unidirectional data flow pattern.
    @param {object} responseData The consistent success response object from the backend.
*/
function syncUIWithState(responseData, selectionToRestore = null) {
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
    if (selectionToRestore) {
        // This UIManager function will find the new DOM element and "click" it
        UIManager.reselectHierarchyItem(selectionToRestore.type, selectionToRestore.id, responseData.project_state);
    } else {
        // If no selection to restore, just clear everything
        UIManager.clearInspector();
        UIManager.clearHierarchySelection();
        SceneManager.unselectAllInScene();
    }
}

// --- Handler Functions (Act as Controllers/Mediators) ---

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

async function handleLoadGdml(file) {
    if (!file) return;
    UIManager.showLoading("Processing GDML...");
    try {
        const result = await APIService.loadGdmlFile(file);
        syncUIWithState(result); // No selection to restore
    } catch (error) { UIManager.showError("Failed to load GDML: " + error.message); }
    finally { UIManager.hideLoading(); }
}

async function handleLoadProject(file) {
    if (!file) return;
    UIManager.showLoading("Loading project...");
    try {
        const result = await APIService.loadProjectFile(file);
        syncUIWithState(result); // No selection to restore
    } catch (error) { UIManager.showError("Failed to load project: " + error.message); }
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

async function handleDeleteSelected() {
    const selectionContext = getSelectionContext();
    if (!selectionContext) {
        UIManager.showNotification("Please select an item from the hierarchy to delete.");
        return;
    }
    if (!UIManager.confirmAction(`Are you sure you want to delete ${selectionContext.type}: ${selectionContext.id}?`)) return;

    UIManager.showLoading("Deleting object...");
    try {
        const result = await APIService.deleteObject(selectionContext.type, selectionContext.id);
        syncUIWithState(result); // No selection to restore after delete
    } catch (error) { UIManager.showError("Error deleting object: " + error.message); }
    finally { UIManager.hideLoading(); }
}

function handleModeChange(newMode) {
    const currentSelectedIn3D = SceneManager.getSelectedObjects();
    InteractionManager.setMode(newMode, currentSelectedIn3D.length === 1 ? currentSelectedIn3D[0] : null);
    if (newMode === 'observe' && SceneManager.getTransformControls().object) {
        SceneManager.getTransformControls().detach();
    } else if (newMode !== 'observe' && AppState.selectedThreeObjects.length === 1){
        SceneManager.attachTransformControls(AppState.selectedThreeObjects[0]);
    }
}

async function handleHierarchySelection(itemContext) {
    AppState.selectedHierarchyItem = itemContext;
    const { type, id } = itemContext;

    // Fetch fresh details for the inspector
    const details = await APIService.getObjectDetails(type, id);
    if (!details) {
        UIManager.showError(`Could not fetch details for ${type} ${id}`);
        return;
    }

    itemContext.data = details;
    
    // --- Pass the full project state to the inspector ---
    // The inspector can now get the defines list directly from here,
    // avoiding another async API call during a critical redraw.
    UIManager.populateInspector(itemContext, AppState.currentProjectState);

    // If a physical volume is selected, cache its define references for live updates and select in 3D
    if (type === 'physical_volume') {
        SceneManager.selectObjectInSceneByPvId(id);
        AppState.selectedThreeObjects = SceneManager.getSelectedObjects();
        AppState.selectedPVContext.pvId = id;
        AppState.selectedPVContext.positionDefineName = typeof details.position === 'string' ? details.position : null;
        AppState.selectedPVContext.rotationDefineName = typeof details.rotation === 'string' ? details.rotation : null;
        
        if (InteractionManager.getCurrentMode() !== 'observe') {
            const selectedMesh = AppState.selectedThreeObjects[0];
            if(selectedMesh) SceneManager.attachTransformControls(selectedMesh);
        }
    } else {
        // Clear PV context and 3D selection if something else is selected
        AppState.selectedPVContext.pvId = null;
        AppState.selectedPVContext.positionDefineName = null;
        AppState.selectedPVContext.rotationDefineName = null;
        SceneManager.unselectAllInScene();
        AppState.selectedThreeObjects = [];
    }
}

// Called by SceneManager when an object is clicked in 3D
function handle3DSelection(selectedThreeObject) {
    if (selectedThreeObject) {
        const pvId = selectedThreeObject.userData.id;
        // This will now trigger the async data fetch and context update via the hierarchy
        UIManager.selectHierarchyItemByTypeAndId('physical_volume', pvId, AppState.currentProjectState);
    } else {
        UIManager.clearHierarchySelection();
        AppState.selectedHierarchyItem = null;
        AppState.selectedThreeObjects = [];
        AppState.selectedPVContext.pvId = null;
    }
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
async function handleTransformEnd(transformedObject) {
    if (!transformedObject || !transformedObject.userData) return;
    const selectionContext = getSelectionContext(); // Get selection BEFORE update
    UIManager.showLoading("Updating transform...");
    try {
        const objData = transformedObject.userData;
        const newPosition = { x: transformedObject.position.x, y: transformedObject.position.y, z: transformedObject.position.z };
        const euler = new THREE.Euler().setFromQuaternion(transformedObject.quaternion, 'ZYX');
        const newRotation = { x: euler.x, y: euler.y, z: euler.z };
        const result = await APIService.updateObjectTransform(objData.id, newPosition, newRotation);
        syncUIWithState(result, selectionContext); // Restore selection
    } catch (error) { UIManager.showError("Error saving transform: " + error.message); }
    finally { UIManager.hideLoading(); }
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
    const selectionContext = getSelectionContext();

    // --- The data object from solidEditor.js now looks like one of these:
    // For creating a primitive: { isEdit: false, name, type, params, ... }
    // For creating a boolean:  { isChainedBoolean: true, name, recipe }
    // For editing a primitive: { isEdit: true, id, type, params }
    // For editing a boolean:  { isEdit: true, isChainedBoolean: true, id, recipe }
    
    if (data.isEdit) {
        // --- HANDLE ALL UPDATES (EDIT MODE) ---
        if (data.isChainedBoolean) {
            // --- Update an existing Boolean Solid ---
            UIManager.showLoading("Updating boolean solid...");
            try {
                const result = await APIService.updateBooleanSolid(data.id, data.recipe);
                syncUIWithState(result, { type: 'solid', id: data.id });
            } catch (error) {
                UIManager.showError("Error updating boolean solid: " + (error.message || error));
            } finally {
                UIManager.hideLoading();
            }
        } else {
            // --- Update an existing Primitive Solid ---
            UIManager.showLoading("Updating solid...");
            try {
                // The loop is still the best approach with our current API
                let lastResult;
                for (const key in data.params) {
                    const value = data.params[key];
                    // The backend expects radians for angles and full length for dz,
                    // which getParamsFromUI now correctly provides.
                    lastResult = await APIService.updateProperty('solid', data.id, `parameters.${key}`, value);
                    
                    if (!lastResult.success) {
                        UIManager.showError(`Failed to update property ${key}: ${lastResult.error}`);
                        const freshState = await APIService.getProjectState();
                        syncUIWithState({ ...freshState, success: true, message: "Update failed, state restored." });
                        return;
                    }
                }
                syncUIWithState(lastResult);
            } catch (error) {
                UIManager.showError("Error updating solid: " + (error.message || error));
            } finally {
                UIManager.hideLoading();
            }
        }

    } else {
        // --- HANDLE ALL CREATIONS (CREATE MODE) ---
        if (data.isChainedBoolean) {
            // --- Create a new Boolean Solid ---
            UIManager.showLoading("Creating boolean solid...");
            try {
                // We now call the correct new API function
                const result = await APIService.addBooleanSolid(data.name, data.recipe);
                syncUIWithState(result);
            } catch (error) {
                UIManager.showError("Error creating boolean solid: " + (error.message || error));
            } finally {
                UIManager.hideLoading();
            }
        } else {
            // --- Create a new Primitive Solid (with optional LV/PV) ---
            const objectType = `solid_${data.type}`;
            UIManager.showLoading("Adding solid...");
            try {
                // If either quick-add checkbox is checked, use the new powerful endpoint
                if (data.createLV) {
                    const solidParams = { name: data.name, type: data.type, params: data.params };
                    
                    const lvParams = { material_ref: data.materialRef };
                    // Let the backend generate the LV name, or use a convention
                    // lvParams.name = `${data.name}_lv`; 

                    let pvParams = null;
                    if (data.placePV) {
                        // Default to placing in the World if nothing else is selected
                        const parentContext = UIManager.getSelectedParentContext();
                        const parentName = (parentContext && parentContext.name) 
                                           ? parentContext.name 
                                           : AppState.currentProjectState.world_volume_ref;
                        pvParams = { parent_lv_name: parentName };
                    }
                    
                    const result = await APIService.addSolidAndPlace(solidParams, lvParams, pvParams);
                    syncUIWithState(result);

                } else {
                    // Otherwise, use the original simple "add solid" endpoint
                    const objectType = `solid_${data.type}`;
                    const result = await APIService.addPrimitiveSolid(data.name, data.type, data.params);

                    // After creation, we want to select the new solid
                    const newSolidName = result.project_state.solids[data.name] ? data.name : Object.keys(result.project_state.solids).pop();
                    syncUIWithState(result, { type: 'solid', id: newSolidName });
                }
            } catch (error) { 
                UIManager.showError("Error adding solid: " + (error.message || error)); 
            } finally { 
                UIManager.hideLoading(); 
            }
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
            const result = await APIService.updateLogicalVolume(data.id, data.solid_ref, data.material_ref);
            syncUIWithState(result, selectionContext);
        } catch (error) {
            UIManager.showError("Error updating LV: " + (error.message || error));
        } finally {
            UIManager.hideLoading();
        }
    } else {
        UIManager.showLoading("Creating Logical Volume...");
        try {
            const result = await APIService.addLogicalVolume(data.name, data.solid_ref, data.material_ref);
            syncUIWithState(result, { type: 'logical_volume', id: data.name });
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
            syncUIWithState(result, { type: 'logical_volume', id: data.parent_lv_name });
        } catch (error) { UIManager.showError("Error placing PV: " + (error.message || error)); } 
        finally { UIManager.hideLoading(); }
    }
}

function handleAddDefine() {
    DefineEditor.show();
}

function handleEditDefine(defineData) {
    DefineEditor.show(defineData);
}

async function handleDefineEditorConfirm(data) {
    const selectionContext = getSelectionContext();
    if (data.isEdit) {
        UIManager.showLoading("Updating Define...");
        try {
            const result = await APIService.updateDefine(data.id, data.value, data.unit, data.category);
            syncUIWithState(result, selectionContext);
        } catch (error) {
            UIManager.showError("Error updating define: " + (error.message || error));
        } finally { UIManager.hideLoading(); }
    } else {
        UIManager.showLoading("Creating Define...");
        try {
            const result = await APIService.addDefine(data.name, data.type, data.value, data.unit, data.category);
            
            // After creating, set the selection to the newly created define
            syncUIWithState(result, { type: 'define', id: data.name });
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
            syncUIWithState(result, { type: 'material', id: data.name });
        } catch (error) {
            UIManager.showError("Error creating material: " + (error.message || error));
        } finally {
            UIManager.hideLoading();
        }
    }
}