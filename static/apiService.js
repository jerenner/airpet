// static/apiService.js

// --- Configuration ---
// It's good practice to have the base URL configurable
const API_BASE_URL = 'http://localhost:5003'; // Empty for same-origin, or e.g., 'http://localhost:5003' if different

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
        throw new Error(errorData.error || `Request failed with status ${response.status}`);
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

export async function addDefine(name, type, value, unit, category) {
    const response = await fetch(`${API_BASE_URL}/add_define`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, type, value, unit, category })
    });
    return handleResponse(response);
}

export async function updateDefine(id, value, unit, category) {
    const response = await fetch(`${API_BASE_URL}/update_define`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, value, unit, category })
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

export async function addPrimitiveSolid(name, type, params) {
    const response = await fetch(`${API_BASE_URL}/add_primitive_solid`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, type, params })
    });
    return handleResponse(response);
}

/**
 * Deletes an object from the geometry.
 * @param {string} objectType The type of the object to delete.
 * @param {string} objectId The unique ID or name of the object to delete.
 * @returns {Promise<Object>} A promise that resolves to the backend's response.
 */
export async function deleteObject(objectType, objectId) {
    const response = await fetch(`${API_BASE_URL}/delete_object`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ object_type: objectType, object_id: objectId })
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

export async function addLogicalVolume(name, solid_ref, material_ref, vis_attributes) {
    const response = await fetch(`${API_BASE_URL}/add_logical_volume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, solid_ref, material_ref, vis_attributes })
    });
    return handleResponse(response);
}

export async function updateLogicalVolume(id, solid_ref, material_ref, vis_attributes) {
    const response = await fetch(`${API_BASE_URL}/update_logical_volume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, solid_ref, material_ref, vis_attributes })
    });
    return handleResponse(response);
}

export async function addPhysicalVolume(parent_lv_name, name, volume_ref, position, rotation) {
    const response = await fetch(`${API_BASE_URL}/add_physical_volume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parent_lv_name, name, volume_ref, position, rotation })
    });
    return handleResponse(response);
}

export async function updatePhysicalVolume(id, name, position, rotation) {
    const response = await fetch(`${API_BASE_URL}/update_physical_volume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, name, position, rotation })
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