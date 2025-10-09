// static/apiService.js

// --- Configuration ---
// It's good practice to have the base URL configurable
const API_BASE_URL = ''; // Empty for same-origin, or e.g., 'http://localhost:5003' if different

// --- Helper Functions ---
async function handleResponse(response) {
    if (!response.ok) {
        // Try to parse error message from JSON response, else use status text
        let errorData;
        try {
            errorData = await response.json();
        } catch (e) {
            // Not a JSON response
            throw new Error(`Network error: ${response.status} ${response.statusText}`);
        }
        
        // --- Custom error object ---
        const error = new Error(errorData.error || `Request failed with status ${response.status}`);
        error.type = errorData.error_type || 'generic'; // Add the error type if it exists
        throw error;
    }
    return response.json(); // Assumes all successful responses are JSON
}

async function handleBlobResponse(response, defaultFilename) {
    if (!response.ok) {
        let errorData;
        try {
            errorData = await response.json();
        } catch (e) {
            throw new Error(`Network error: ${response.status} ${response.statusText}`);
        }
        throw new Error(errorData.error || `Request failed with status ${response.status}`);
    }
    
    // Create a link and trigger a download for the blob data
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = defaultFilename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

// --- API Functions ---

/**
 * Creates a new, empty project on the backend with a default world volume.
 * @returns {Promise<Object>} A promise that resolves to the new project state.
 */
export async function newProject() {
    const response = await fetch(`${API_BASE_URL}/new_project`, {
        method: 'POST',
    });
    return handleResponse(response);
}

export async function openGdmlProject(gdmlFile) {
    const formData = new FormData();
    formData.append('gdmlFile', gdmlFile);
    const response = await fetch(`${API_BASE_URL}/process_gdml`, {
        method: 'POST',
        body: formData,
    });
    return handleResponse(response);
}

export async function openJsonProject(projectFile) {
    const formData = new FormData();
    formData.append('projectFile', projectFile);
    const response = await fetch(`${API_BASE_URL}/load_project_json`, {
        method: 'POST',
        body: formData,
    });
    return handleResponse(response);
}

export async function importGdmlPart(partFile) {
    const formData = new FormData();
    formData.append('partFile', partFile);
    const response = await fetch(`${API_BASE_URL}/import_gdml_part`, {
        method: 'POST',
        body: formData,
    });
    return handleResponse(response);
}

export async function importJsonPart(partFile) {
    const formData = new FormData();
    formData.append('partFile', partFile);
    const response = await fetch(`${API_BASE_URL}/import_json_part`, {
        method: 'POST',
        body: formData,
    });
    return handleResponse(response);
}

/**
 * Requests the current project state from the backend and triggers a browser download.
 * @returns {Promise<void>}
 */
export async function saveProject() {
    const response = await fetch(`${API_BASE_URL}/save_project_json`);
    await handleBlobResponse(response, 'project.json');
}

export async function autoSaveProject() {
    const response = await fetch(`${API_BASE_URL}/autosave`, { method: 'POST' });
    return handleResponse(response);
}

export async function renameProject(projectName) {
    const response = await fetch(`${API_BASE_URL}/rename_project`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_name: projectName })
    });
    return handleResponse(response); // Returns simple success/error message
}

// --- History/Versioning Functions ---

export async function undo() {
    const response = await fetch(`${API_BASE_URL}/api/undo`, { method: 'POST' });
    return handleResponse(response);
}

export async function redo() {
    const response = await fetch(`${API_BASE_URL}/api/redo`, { method: 'POST' });
    return handleResponse(response);
}

/**
 * Tells the backend to start a transaction, suspending history captures.
 * @returns {Promise<Object>}
 */
export async function beginTransaction() {
    const response = await fetch(`${API_BASE_URL}/api/begin_transaction`, { method: 'POST' });
    return handleResponse(response);
}

/**
 * Tells the backend to end a transaction, capturing the final state.
 * @param {string} description - A description of the operation for the history log.
 * @returns {Promise<Object>} A promise resolving to the full, updated project state.
 */
export async function endTransaction(description = "Transform objects") {
    const response = await fetch(`${API_BASE_URL}/api/end_transaction`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: description })
    });
    return handleResponse(response); // Returns the full state for UI sync
}

export async function saveVersion(projectName) {
    const response = await fetch(`${API_BASE_URL}/api/save_version`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_name: projectName })
    });
    return handleResponse(response); // Returns simple success/error message
}

export async function getProjectHistory(projectName) {
    const response = await fetch(`${API_BASE_URL}/api/get_project_history?project_name=${projectName}`);
    return handleResponse(response);
}

export async function loadVersion(projectName, versionId) {
    const response = await fetch(`${API_BASE_URL}/api/load_version`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_name: projectName, version_id: versionId })
    });
    return handleResponse(response);
}

// --

/**
 * Requests the GDML representation of the current project state and triggers a download.
 * @returns {Promise<void>}
 */
export async function exportGdml() {
    const response = await fetch(`${API_BASE_URL}/export_gdml`);
    await handleBlobResponse(response, 'exported_geometry.gdml');
}

/**
 * Gets the entire current project state from the backend.
 * @returns {Promise<Object>} A promise that resolves to the full project state dictionary.
 */
export async function getProjectState() {
    const response = await fetch(`${API_BASE_URL}/get_project_state`);
    return handleResponse(response);
}

/**
 * Gets detailed information for a single object.
 * @param {string} objectType e.g., 'physical_volume', 'solid', 'define'
 * @param {string} objectId The unique ID (for PVs) or name (for others) of the object.
 * @returns {Promise<Object>} A promise that resolves to the object's data dictionary.
 */
export async function getObjectDetails(objectType, objectId) {
    const response = await fetch(`${API_BASE_URL}/get_object_details?type=${objectType}&id=${objectId}`);
    return handleResponse(response);
}

export async function addDefine(name, type, rawExpression, unit, category) {
    const response = await fetch(`${API_BASE_URL}/add_define`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, type, value: rawExpression, unit, category }) // Backend expects 'value' key
    });
    return handleResponse(response);
}

export async function updateDefine(id, rawExpression, unit, category) {
    const response = await fetch(`${API_BASE_URL}/update_define`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, value: rawExpression, unit, category }) // Backend expects 'value' key
    });
    return handleResponse(response);
}

export async function addMaterial(name, params) {
    const response = await fetch(`${API_BASE_URL}/add_material`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, params })
    });
    return handleResponse(response);
}

export async function updateMaterial(id, params) {
    const response = await fetch(`${API_BASE_URL}/update_material`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, params })
    });
    return handleResponse(response);
}

export async function addElement(name, params) {
    const payload = { name, ...params };
    const response = await fetch(`${API_BASE_URL}/add_element`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse(response);
}

export async function updateElement(id, params) {
    const payload = { id, ...params };
    const response = await fetch(`${API_BASE_URL}/update_element`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse(response);
}

export async function addIsotope(name, params) {
    const payload = { name, ...params };
    const response = await fetch(`${API_BASE_URL}/add_isotope`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse(response);
}

export async function updateIsotope(id, params) {
    const payload = { id, ...params };
    const response = await fetch(`${API_BASE_URL}/update_isotope`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse(response);
}

export async function addPrimitiveSolid(name, type, params) {
    const response = await fetch(`${API_BASE_URL}/add_primitive_solid`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, type, params })
    });
    return handleResponse(response);
}

export async function updateSolid(solidId, rawParameters) {
    const response = await fetch(`${API_BASE_URL}/update_solid`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: solidId, params: rawParameters })
    });
    return handleResponse(response);
}

/**
 * Deletes a batch of objects from the geometry in a single transaction.
 * @param {Array<Object>} objectsToDelete - Array of {type, id} objects.
 * @returns {Promise<Object>} A promise that resolves to the backend's response.
 */
export async function deleteObjectsBatch(objectsToDelete) {
    const response = await fetch(`${API_BASE_URL}/api/delete_objects_batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ objects: objectsToDelete })
    });
    return handleResponse(response);
}

/**
 * Updates the transformation (position, rotation) of a physical volume.
 * @param {string} objectId The unique ID (UUID) of the physical volume.
 * @param {Object} position The new position {x, y, z}.
 * @param {Object} rotation The new rotation (ZYX Euler in radians) {x, y, z}.
 * @returns {Promise<Object>} A promise that resolves to the backend's response.
 */
export async function updateObjectTransform(objectId, position, rotation) {
    const payload = { id: objectId };
    if (position) payload.position = position;
    if (rotation) payload.rotation = rotation;

    const response = await fetch(`${API_BASE_URL}/update_object_transform`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse(response);
}

/**
 * Updates a specific property of any object in the geometry.
 * @param {string} objectType The type of object.
 * @param {string} objectId The unique ID or name of the object.
 * @param {string} propertyPath The path to the property (e.g., 'parameters.x').
 * @param {any} newValue The new value for the property.
 * @returns {Promise<Object>} A promise that resolves to the backend's response, typically including success status and updated scene/project data.
 */
export async function updateProperty(objectType, objectId, propertyPath, newValue) {
    const response = await fetch(`${API_BASE_URL}/update_property`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            object_type: objectType,
            object_id: objectId,
            property_path: propertyPath,
            new_value: newValue
        })
    });
    return handleResponse(response);
}

export async function addSolidAndPlace(solidParams, lvParams, pvParams) {
    const response = await fetch(`${API_BASE_URL}/add_solid_and_place`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            solid_params: solidParams,
            lv_params: lvParams,
            pv_params: pvParams
        })
    });
    return handleResponse(response);
}

/**
 * Creates a new boolean solid by sending its recipe to the backend.
 * @param {string} nameSuggestion The user-suggested name for the new solid.
 * @param {Array} recipe The list of operations for the boolean solid.
 * @returns {Promise<Object>} A promise that resolves to the backend's response.
 */
export async function addBooleanSolid(nameSuggestion, recipe) {
    const response = await fetch(`${API_BASE_URL}/add_boolean_solid`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: nameSuggestion, recipe: recipe })
    });
    return handleResponse(response);
}

export async function updateBooleanSolid(solidId, recipe) {
    const response = await fetch(`${API_BASE_URL}/update_boolean_solid`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: solidId, recipe: recipe })
    });
    return handleResponse(response);
}

export async function addLogicalVolume(name, solid_ref, material_ref, vis_attributes, is_sensitive, content_type, content) {
    const response = await fetch(`${API_BASE_URL}/add_logical_volume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, solid_ref, material_ref, vis_attributes, is_sensitive, content_type, content })
    });
    return handleResponse(response);
}

export async function updateLogicalVolume(id, solid_ref, material_ref, vis_attributes, is_sensitive, content_type, content) {
    const response = await fetch(`${API_BASE_URL}/update_logical_volume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, solid_ref, material_ref, vis_attributes, is_sensitive, content_type, content })
    });
    return handleResponse(response);
}

export async function addPhysicalVolume(parent_lv_name, name, volume_ref, position, rotation, scale) {
    const response = await fetch(`${API_BASE_URL}/add_physical_volume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parent_lv_name, name, volume_ref, position, rotation, scale })
    });
    return handleResponse(response);
}

export async function updatePhysicalVolume(id, name, position, rotation, scale) {
    const response = await fetch(`${API_BASE_URL}/update_physical_volume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, name, position, rotation, scale })
    });
    return handleResponse(response);
}

/**
 * Sends a batch of physical volume transform updates to the backend.
 * This is treated as a single operation for the undo/redo history.
 * @param {Array<Object>} updates - An array of update objects, e.g., [{id, position, rotation, scale}, ...]
 * @returns {Promise<Object>} A promise resolving to the full, updated project state.
 */
export async function updatePhysicalVolumeBatch(updates) {
    const response = await fetch(`${API_BASE_URL}/api/update_physical_volume_batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates: updates })
    });
    return handleResponse(response);
}

export async function getDefinesByType(type) {
    const response = await fetch(`${API_BASE_URL}/get_defines_by_type?type=${type}`);
    return handleResponse(response);
}

/**
 * Checks if the backend AI service (Ollama) is reachable.
 * @returns {Promise<Object>} A promise that resolves to the health status.
 */
export async function checkAiServiceStatus() {
    const response = await fetch(`${API_BASE_URL}/ai_health_check`);
    // We don't use handleResponse here because we want to handle the 503 error gracefully
    if (!response.ok) {
        return { success: false, error: `Service unavailable (status: ${response.status})` };
    }
    return response.json();
}

/**
 * Sends a prompt to the AI assistant for processing.
 * @param {string} prompt The user's text prompt.
 * @param {string} model The name of the Ollama model to use.
 * @returns {Promise<Object>} A promise that resolves to the backend's response.
 */
export async function processAiPrompt(prompt, model) {
    const response = await fetch(`${API_BASE_URL}/ai_process_prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, model }) // <-- MODIFIED
    });
    return handleResponse(response);
}

/**
 * Sends a pre-generated AI response JSON file to the backend for processing.
 * @param {File} aiFile The JSON file to upload.
 * @returns {Promise<Object>} A promise that resolves to the backend's response.
 */
export async function importAiResponse(aiFile) {
    const formData = new FormData();
    formData.append('aiFile', aiFile);
    const response = await fetch(`${API_BASE_URL}/import_ai_json`, {
        method: 'POST',
        body: formData,
    });
    return handleResponse(response);
}

/**
 * Fetches the fully constructed prompt string from the backend for exporting.
 * @param {string} userPrompt The user's text prompt.
 * @returns {Promise<string>} A promise that resolves to the full prompt text.
 */
export async function getFullAiPrompt(userPrompt) {
    const response = await fetch(`${API_BASE_URL}/ai_get_full_prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: userPrompt })
    });
    
    // Handle text response instead of JSON
    if (!response.ok) {
        // Try to parse error from JSON, else use status text
        let errorData;
        try {
            errorData = await response.json();
        } catch (e) {
            throw new Error(`Network error: ${response.status} ${response.statusText}`);
        }
        throw new Error(errorData.error || `Request failed with status ${response.status}`);
    }
    
    return response.text(); // Return the response body as a string
}

/**
 * Fetches the currently configured Gemini API key from the server.
 * @returns {Promise<Object>}
 */
export async function getGeminiApiKey() {
    const response = await fetch(`${API_BASE_URL}/api/get_gemini_key`);
    return handleResponse(response);
}

/**
 * Sends a new Gemini API key to the server to be saved.
 * @param {string} apiKey The new API key.
 * @returns {Promise<Object>}
 */
export async function setGeminiApiKey(apiKey) {
    const response = await fetch(`${API_BASE_URL}/api/set_gemini_key`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey })
    });
    return handleResponse(response);
}

/**
 * Imports a STEP file along with user-defined options from the import modal.
 * @param {FormData} formData - The form data containing the STEP file and options JSON.
 * @returns {Promise<Object>} A promise that resolves to the backend's response.
 */
export async function importStepWithOptions(formData) {
    const response = await fetch(`${API_BASE_URL}/import_step_with_options`, {
        method: 'POST',
        body: formData, // FormData sets the correct Content-Type header automatically
    });
    return handleResponse(response);
}

/**
 * Creates a new assembly definition.
 * @param {string} name - The user-suggested name for the assembly.
 * @param {Array} placements - An array of placement objects defining the assembly's content.
 * @returns {Promise<Object>} A promise that resolves to the backend's response.
 */
export async function addAssembly(name, placements) {
    const response = await fetch(`${API_BASE_URL}/add_assembly`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, placements })
    });
    return handleResponse(response);
}

/**
 * Updates an existing assembly definition.
 * @param {string} id - The name of the assembly to update.
 * @param {Array} placements - The new array of placement objects for the assembly.
 * @returns {Promise<Object>} A promise that resolves to the backend's response.
 */
export async function updateAssembly(id, placements) {
    const response = await fetch(`${API_BASE_URL}/update_assembly`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, placements })
    });
    return handleResponse(response);
}

export async function createGroup(groupType, groupName) {
    const response = await fetch(`${API_BASE_URL}/create_group`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_type: groupType, group_name: groupName })
    });
    return handleResponse(response);
}

export async function renameGroup(groupType, oldName, newName) {
    const response = await fetch(`${API_BASE_URL}/rename_group`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_type: groupType, old_name: oldName, new_name: newName })
    });
    return handleResponse(response);
}

export async function deleteGroup(groupType, groupName) {
    const response = await fetch(`${API_BASE_URL}/delete_group`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_type: groupType, group_name: groupName })
    });
    return handleResponse(response);
}

export async function moveItemsToGroup(groupType, itemIds, targetGroupName) {
    const response = await fetch(`${API_BASE_URL}/move_items_to_group`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            group_type: groupType,
            item_ids: itemIds,
            target_group_name: targetGroupName
        })
    });
    return handleResponse(response);
}

/**
 * Sends an expression to the backend for safe evaluation.
 * @param {string} expression - The mathematical/variable expression string.
 * @param {Object} projectState - The current full project state to provide context.
 * @returns {Promise<Object>} A promise resolving to the backend's response {success, result} or {success, error}.
 */
export async function evaluateExpression(expression) {
    const response = await fetch(`${API_BASE_URL}/api/evaluate_expression`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            expression: expression
        })
    });
    // This uses handleResponse, which will throw an error on non-OK responses
    return handleResponse(response);
}

export async function movePvToLv(pvIds, targetLvName) { // Changed to pvIds
    const response = await fetch(`${API_BASE_URL}/move_pv_to_lv`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pv_ids: pvIds, target_lv_name: targetLvName }) // Changed to pv_ids
    });
    return handleResponse(response);
}

export async function addOpticalSurface(name, params) {
    // The params object already contains all necessary fields from the editor
    const payload = { name, ...params };
    const response = await fetch(`${API_BASE_URL}/add_optical_surface`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse(response);
}

export async function updateOpticalSurface(id, params) {
    // The params object already contains all necessary fields from the editor
    const payload = { id, ...params };
    const response = await fetch(`${API_BASE_URL}/update_optical_surface`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse(response);
}

export async function addSkinSurface(name, params) {
    // The params object from the editor contains volume_ref and surfaceproperty_ref
    const payload = { name, ...params };
    const response = await fetch(`${API_BASE_URL}/add_skin_surface`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse(response);
}

export async function updateSkinSurface(id, params) {
    const payload = { id, ...params };
    const response = await fetch(`${API_BASE_URL}/update_skin_surface`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse(response);
}

export async function addBorderSurface(name, params) {
    const payload = { name, ...params };
    const response = await fetch(`${API_BASE_URL}/add_border_surface`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse(response);
}

export async function updateBorderSurface(id, params) {
    const payload = { id, ...params };
    const response = await fetch(`${API_BASE_URL}/update_border_surface`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    return handleResponse(response);
}

export async function addParticleSource(name, gps_commands, position, rotation) {
    const response = await fetch(`${API_BASE_URL}/api/add_source`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, gps_commands, position, rotation })
    });
    return handleResponse(response);
}

export async function updateSourceTransform(sourceId, position, rotation) {
    const response = await fetch(`${API_BASE_URL}/api/update_source_transform`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: sourceId, position: position, rotation: rotation })
    });
    return handleResponse(response);
}

export async function updateParticleSource(sourceId, name, gps_commands, position, rotation) {
    const response = await fetch(`${API_BASE_URL}/api/update_source`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            id: sourceId, 
            name: name, 
            gps_commands: gps_commands,
            position: position,
            rotation: rotation
        })
    });
    return handleResponse(response);
}

export async function setActiveSource(sourceId) {
    const response = await fetch(`${API_BASE_URL}/api/set_active_source`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_id: sourceId })
    });
    return handleResponse(response);
}

/**
 * Sends a request to the backend to start a new simulation run.
 * @param {object} simParams - An object containing simulation parameters (e.g., {events: 1000}).
 * @returns {Promise<Object>} A promise resolving to the backend's response, including a job_id.
 */
export async function runSimulation(simParams) {
    const response = await fetch(`${API_BASE_URL}/api/simulation/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(simParams)
    });
    return handleResponse(response);
}

/**
 * Sends a request to the backend to get the status of a running simulation.
 * @param {string} jobId - The unique ID of the simulation job.
 * @returns {Promise<Object>} A promise resolving to the simulation status.
 */
export async function getSimulationStatus(jobId, sinceLine = 0) {
    const response = await fetch(`${API_BASE_URL}/api/simulation/status/${jobId}?since=${sinceLine}`);
    return handleResponse(response);
}

/**
 * Fetches the trajectory data for a specific event or all events as a text file.
 * @param {string} versionId - The ID of the project version.
 * @param {string} jobId - The ID of the simulation job.
 * @param {string|number} eventSpec - The event number or the string "all".
 * @returns {Promise<string>} A promise that resolves to the text content of the track file(s).
 */
export async function getEventTracks(versionId, jobId, eventSpec) {
    // Construct the URL, e.g., /api/simulation/tracks/2024-08.../uuid.../all
    const response = await fetch(`${API_BASE_URL}/api/simulation/tracks/${versionId}/${jobId}/${eventSpec}`);
    
    if (!response.ok) {
        // Try to get a structured error message from the body (which might be JSON)
        let errorData;
        try {
            errorData = await response.json();
            throw new Error(errorData.error || `Failed to fetch tracks: ${response.statusText}`);
        } catch(e) {
            // If the body is not JSON or another error occurs, use the status text
            throw new Error(`Failed to fetch tracks: ${response.statusText}`);
        }
    }
    // If the response is OK, return the raw text content
    return response.text();
}

/**
 * Sends a request to the backend to stop (terminate) a running simulation.
 * @param {string} jobId - The unique ID of the simulation job to stop.
 * @returns {Promise<Object>} A promise resolving to the backend's response.
 */
export async function stopSimulation(jobId) {
    const response = await fetch(`${API_BASE_URL}/api/simulation/stop/${jobId}`, { // We will create this endpoint next
        method: 'POST'
    });
    return handleResponse(response);
}

/**
 * Tells the backend to process a simulation's output to generate LORs.
 * @param {string} versionId - The ID of the project version.
 * @param {string} jobId - The ID of the simulation job.
 * @param {object} params - Coincidence processing parameters.
 * @returns {Promise<Object>}
 */
export async function processLors(versionId, jobId, params) {
    const response = await fetch(`${API_BASE_URL}/api/simulation/process_lors/${versionId}/${jobId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
    });
    return handleResponse(response);
}

/**
 * Starts the reconstruction process on the backend.
 * @param {string} versionId - The ID of the project version.
 * @param {string} jobId - The ID of the simulation job.
 * @param {object} reconParams - Reconstruction parameters (iterations, image size, etc.).
 * @returns {Promise<Object>}
 */
export async function runReconstruction(versionId, jobId, reconParams) {
    const response = await fetch(`${API_BASE_URL}/api/reconstruction/run/${versionId}/${jobId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reconParams)
    });
    return handleResponse(response);
}

/**
 * Gets the URL for a specific slice of the reconstructed image.
 * @param {string} versionId - The ID of the project version.
 * @param {string} jobId - The ID of the simulation job.
 * @param {string} axis - The slicing axis ('x', 'y', or 'z').
 * @param {number} sliceNum - The index of the slice.
 * @returns {string} The direct URL to the image slice.
 */
export function getReconstructionSliceUrl(versionId, jobId, axis, sliceNum) {
    // We add a timestamp to prevent the browser from caching the image
    return `${API_BASE_URL}/api/reconstruction/slice/${versionId}/${jobId}/${axis}/${sliceNum}?t=${new Date().getTime()}`;
}

/**
 * Fetches the metadata for a specific simulation run.
 * @param {string} versionId - The ID of the project version.
 * @param {string} jobId - The ID of the simulation job.
 * @returns {Promise<Object>} A promise resolving to the metadata.
 */
export async function getSimulationMetadata(versionId, jobId) {
    const response = await fetch(`${API_BASE_URL}/api/simulation/metadata/${versionId}/${jobId}`);
    return handleResponse(response);
}