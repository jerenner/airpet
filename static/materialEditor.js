// FILE: virtual-pet/static/materialEditor.js

import * as ExpressionInput from './expressionInput.js';

let modalElement, titleElement, nameInput, confirmButton, cancelButton, paramsDiv;
let simpleRadio, mixtureRadio, compositeRadio, nistRadio;
let onConfirmCallback = null;
let isEditMode = false;
let editingMaterialId = null;
let currentProjectState = null;
let materialComponents = []; // For mixture mode

// Simple Materials (Elements)
const NIST_MATERIALS_SIMPLE = [
    "G4_H", "G4_He", "G4_Li", "G4_Be", "G4_B", "G4_C", "G4_N", "G4_O", "G4_F", "G4_Ne",
    "G4_Na", "G4_Mg", "G4_Al", "G4_Si", "G4_P", "G4_S", "G4_Cl", "G4_Ar", "G4_K", "G4_Ca",
    "G4_Sc", "G4_Ti", "G4_V", "G4_Cr", "G4_Mn", "G4_Fe", "G4_Co", "G4_Ni", "G4_Cu", "G4_Zn",
    "G4_Ga", "G4_Ge", "G4_As", "G4_Se", "G4_Br", "G4_Kr", "G4_Rb", "G4_Sr", "G4_Y", "G4_Zr",
    "G4_Nb", "G4_Mo", "G4_Tc", "G4_Ru", "G4_Rh", "G4_Pd", "G4_Ag", "G4_Cd", "G4_In", "G4_Sn",
    "G4_Sb", "G4_Te", "G4_I", "G4_Xe", "G4_Cs", "G4_Ba", "G4_La", "G4_Ce", "G4_Pr", "G4_Nd",
    "G4_Pm", "G4_Sm", "G4_Eu", "G4_Gd", "G4_Tb", "G4_Dy", "G4_Ho", "G4_Er", "G4_Tm", "G4_Yb",
    "G4_Lu", "G4_Hf", "G4_Ta", "G4_W", "G4_Re", "G4_Os", "G4_Ir", "G4_Pt", "G4_Au", "G4_Hg",
    "G4_Tl", "G4_Pb", "G4_Bi", "G4_Po", "G4_At", "G4_Rn", "G4_Fr", "G4_Ra", "G4_Ac", "G4_Th",
    "G4_Pa", "G4_U", "G4_Np", "G4_Pu", "G4_Am", "G4_Cm", "G4_Bk", "G4_Cf"
];

// NIST Compounds
const NIST_MATERIALS_COMPOUNDS = [
    "G4_A-150_TISSUE", "G4_ACETONE", "G4_ACETYLENE", "G4_ADENINE", "G4_ADIPOSE_TISSUE_ICRP",
    "G4_AIR", "G4_ALANINE", "G4_ALUMINUM_OXIDE", "G4_AMBER", "G4_AMMONIA", "G4_ANILINE",
    "G4_ANTHRACENE", "G4_B-100_BONE", "G4_BAKELITE", "G4_BARIUM_FLUORIDE", "G4_BARIUM_SULFATE",
    "G4_BENZENE", "G4_BERYLLIUM_OXIDE", "G4_BGO", "G4_BLOOD_ICRP", "G4_BONE_COMPACT_ICRU",
    "G4_BONE_CORTICAL_ICRP", "G4_BORON_CARBIDE", "G4_BORON_OXIDE", "G4_BRAIN_ICRP", "G4_BUTANE",
    "G4_N-BUTYL_ALCOHOL", "G4_C-552", "G4_CADMIUM_TELLURIDE", "G4_CADMIUM_TUNGSTATE",
    "G4_CALCIUM_CARBONATE", "G4_CALCIUM_FLUORIDE", "G4_CALCIUM_OXIDE", "G4_CALCIUM_SULFATE",
    "G4_CALCIUM_TUNGSTATE", "G4_CARBON_DIOXIDE", "G4_CARBON_TETRACHLORIDE",
    "G4_CELLULOSE_CELLOPHANE", "G4_CELLULOSE_BUTYRATE", "G4_CELLULOSE_NITRATE",
    "G4_CERIC_SULFATE", "G4_CESIUM_FLUORIDE", "G4_CESIUM_IODIDE", "G4_CHLOROBENZENE",
    "G4_CHLOROFORM", "G4_CONCRETE", "G4_CYCLOHEXANE", "G4_1,2-DICHLOROBENZENE",
    "G4_DICHLORODIETHYL_ETHER", "G4_1,2-DICHLOROETHANE", "G4_DIETHYL_ETHER",
    "G4_N,N-DIMETHYL_FORMAMIDE", "G4_DIMETHYL_SULFOXIDE", "G4_ETHANE", "G4_ETHYL_ALCOHOL",
    "G4_ETHYL_CELLULOSE", "G4_ETHYLENE", "G4_EYE_LENS_ICRP", "G4_FERRIC_OXIDE",
    "G4_FERROBORIDE", "G4_FERROUS_OXIDE", "G4_FERROUS_SULFATE", "G4_FREON-12",
    "G4_FREON-12B2", "G4_FREON-13", "G4_FREON-13B1", "G4_FREON-13I1",
    "G4_GADOLINIUM_OXYSULFIDE", "G4_GALLIUM_ARSENIDE", "G4_GEL_PHOTO_EMULSION",
    "G4_Pyrex_Glass", "G4_GLASS_LEAD", "G4_GLASS_PLATE", "G4_GLUTAMINE", "G4_GLYCEROL",
    "G4_GUANINE", "G4_GYPSUM", "G4_N-HEPTANE", "G4_N-HEXANE", "G4_KAPTON",
    "G4_LANTHANUM_OXYBROMIDE", "G4_LANTHANUM_OXYSULFIDE", "G4_LEAD_OXIDE",
    "G4_LITHIUM_AMIDE", "G4_LITHIUM_CARBONATE", "G4_LITHIUM_FLUORIDE", "G4_LITHIUM_HYDRIDE",
    "G4_LITHIUM_IODIDE", "G4_LITHIUM_OXIDE", "G4_LITHIUM_TETRABORATE", "G4_LUNG_ICRP",
    "G4_M3_WAX", "G4_MAGNESIUM_CARBONATE", "G4_MAGNESIUM_FLUORIDE", "G4_MAGNESIUM_OXIDE",
    "G4_MAGNESIUM_TETRABORATE", "G4_MERCURIC_IODIDE", "G4_METHANE", "G4_METHANOL",
    "G4_MIX_D_WAX", "G4_MS20_TISSUE", "G4_MUSCLE_SKELETAL_ICRP", "G4_MUSCLE_STRIATED_ICRU",
    "G4_MUSCLE_WITH_SUCROSE", "G4_MUSCLE_WITHOUT_SUCROSE", "G4_NAPHTHALENE",
    "G4_NITROBENZENE", "G4_NITROUS_OXIDE", "G4_NYLON-8062", "G4_NYLON-6-6",
    "G4_NYLON-6-10", "G4_NYLON-11_RILSAN", "G4_OCTANE", "G4_PARAFFIN", "G4_N-PENTANE",
    "G4_PHOTO_EMULSION", "G4_PLASTIC_SC_VINYLTOLUENE", "G4_PLUTONIUM_DIOXIDE",
    "G4_POLYACRYLONITRILE", "G4_POLYCARBONATE", "G4_POLYCHLOROSTYRENE", "G4_POLYETHYLENE",
    "G4_MYLAR", "G4_PLEXIGLASS", "G4_POLYOXYMETHYLENE", "G4_POLYPROPYLENE",
    "G4_POLYSTYRENE", "G4_TEFLON", "G4_POLYTRIFLUOROCHLOROETHYLENE",
    "G4_POLYVINYL_ACETATE", "G4_POLYVINYL_ALCOHOL", "G4_POLYVINYL_BUTYRAL",
    "G4_POLYVINYL_CHLORIDE", "G4_POLYVINYLIDENE_CHLORIDE", "G4_POLYVINYLIDENE_FLUORIDE",
    "G4_POLYVINYL_PYRROLIDONE", "G4_POTASSIUM_IODIDE", "G4_POTASSIUM_OXIDE",
    "G4_PROPANE", "G4_lPROPANE", "G4_N-PROPYL_ALCOHOL", "G4_PYRIDINE",
    "G4_RUBBER_BUTYL", "G4_RUBBER_NATURAL", "G4_RUBBER_NEOPRENE", "G4_SILICON_DIOXIDE",
    "G4_SILVER_BROMIDE", "G4_SILVER_CHLORIDE", "G4_SILVER_HALIDES", "G4_SILVER_IODIDE",
    "G4_SKIN_ICRP", "G4_SODIUM_CARBONATE", "G4_SODIUM_IODIDE", "G4_SODIUM_MONOXIDE",
    "G4_SODIUM_NITRATE", "G4_STILBENE", "G4_SUCROSE", "G4_TERPHENYL", "G4_TESTIS_ICRP",
    "G4_TETRACHLOROETHYLENE", "G4_THALLIUM_CHLORIDE", "G4_TISSUE_SOFT_ICRP",
    "G4_TISSUE_SOFT_ICRU-4", "G4_TISSUE-METHANE", "G4_TISSUE-PROPANE",
    "G4_TITANIUM_DIOXIDE", "G4_TOLUENE", "G4_TRICHLOROETHYLENE",
    "G4_TRIETHYL_PHOSPHATE", "G4_TUNGSTEN_HEXAFLUORIDE", "G4_URANIUM_DICARBIDE",
    "G4_URANIUM_MONOCARBIDE", "G4_URANIUM_OXIDE", "G4_UREA", "G4_VALINE", "G4_VITON",
    "G4_WATER", "G4_WATER_VAPOR", "G4_WOLFRAM_TUNGSTEN", "G4_XYLENE", "G4_YTTERBIUM",
    "G4_YTTRIUM", "G4_ZEOLITE", "G4_ZINC", "G4_ZIRCALOY", "G4_ZIRCONIUM"
];

// HEP and Nuclear Materials
const NIST_MATERIALS_HEP = [
    "G4_lH2", "G4_lN2", "G4_lO2", "G4_lAr", "G4_lBr", "G4_lKr", "G4_lXe", "G4_PbWO4",
    "G4_Galactic", "G4_GRAPHITE_POROUS", "G4_LUCITE", "G4_BRASS", "G4_BRONZE",
    "G4_STAINLESS-STEEL", "G4_CR39", "G4_OCTADECANOL"
];

// Space (ISS) Materials
const NIST_MATERIALS_ISS = [
    "G4_KEVLAR", "G4_DACRON", "G4_NEOPRENE"
];

// Bio-Chemical Materials
const NIST_MATERIALS_BIO = [
    "G4_CYTOSINE", "G4_THYMINE", "G4_URACIL", "G4_DNA_ADENINE", "G4_DNA_GUANINE",
    "G4_DNA_CYTOSINE", "G4_DNA_THYMINE", "G4_DNA_URACIL", "G4_DNA_ADENOSINE",
    "G4_DNA_GUANOSINE", "G4_DNA_CYTIDINE", "G4_DNA_URIDINE", "G4_DNA_METHYLURIDINE",
    "G4_DNA_MONOPHOSPHATE", "G4_DNA_A", "G4_DNA_G", "G4_DNA_C", "G4_DNA_U", "G4_DNA_MU"
];

export function initMaterialEditor(callbacks) {
    onConfirmCallback = callbacks.onConfirm;

    modalElement = document.getElementById('materialEditorModal');
    titleElement = document.getElementById('materialEditorTitle');
    nameInput = document.getElementById('materialEditorName');
    confirmButton = document.getElementById('materialEditorConfirm');
    cancelButton = document.getElementById('materialEditorCancel');
    paramsDiv = document.getElementById('material-editor-params');
    simpleRadio = document.getElementById('mat_type_simple');
    mixtureRadio = document.getElementById('mat_type_mixture');
    compositeRadio = document.getElementById('mat_type_composite');
    nistRadio = document.getElementById('mat_type_nist');

    cancelButton.addEventListener('click', hide);
    confirmButton.addEventListener('click', handleConfirm);
    simpleRadio.addEventListener('change', () => renderParamsUI());
    mixtureRadio.addEventListener('change', () => renderParamsUI());
    compositeRadio.addEventListener('change', () => renderParamsUI());
    nistRadio.addEventListener('change', () => renderParamsUI());

    console.log("Material Editor Initialized.");
}

export function show(materialData = null, projectState = null) {
    currentProjectState = projectState;
    materialComponents = []; // Reset components

    // Get the radio buttons
    const radios = [simpleRadio, mixtureRadio, compositeRadio, nistRadio];

    if (materialData && materialData.name) {
        // --- EDIT MODE ---
        isEditMode = true;
        editingMaterialId = materialData.name;
        titleElement.textContent = `Edit Material: ${materialData.name}`;
        nameInput.value = materialData.name;
        nameInput.disabled = true;
        confirmButton.textContent = "Update Material";

        // Disable the radio buttons in edit mode
        radios.forEach(radio => radio.disabled = true);

        // Check the correct radio button
        if (materialData.mat_type === 'nist') {
            nistRadio.checked = true;
        } else if (materialData.components && materialData.components.length > 0) {
            // Check if it's a composite (by natoms) or mixture (by fraction)
            if (materialData.components[0].natoms !== undefined) {
                compositeRadio.checked = true;
            } else {
                mixtureRadio.checked = true;
            }
            materialComponents = JSON.parse(JSON.stringify(materialData.components)); // Deep copy
        } else {
            simpleRadio.checked = true;
        }
        renderParamsUI(materialData);

    } else {
        // --- CREATE MODE ---
        isEditMode = false;
        editingMaterialId = null;
        titleElement.textContent = "Create New Material";
        nameInput.value = '';
        nameInput.disabled = false;

        // Ensure the radio buttons are enabled in create mode
        radios.forEach(radio => radio.disabled = false);

        simpleRadio.checked = true; // Default to simple
        confirmButton.textContent = "Create Material";
        renderParamsUI();
    }
    modalElement.style.display = 'block';
}

function hide() {
    modalElement.style.display = 'none';
}

function renderParamsUI(matData = null) {
    paramsDiv.innerHTML = '';
    const isSimple = simpleRadio.checked;
    const isComposite = compositeRadio.checked;
    const isNIST = nistRadio.checked;
    
    if (isNIST) {
        // --- UI for NIST ---
        
        // Define the structure for the dropdown
        const categories = {
            "Simple Elements": NIST_MATERIALS_SIMPLE,
            "Compounds": NIST_MATERIALS_COMPOUNDS,
            "HEP & Nuclear": NIST_MATERIALS_HEP,
            "Space Materials": NIST_MATERIALS_ISS,
            "Bio-Chemical": NIST_MATERIALS_BIO
        };

        // Build the select element with optgroups
        let selectHTML = '<option value="">-- Select a preset material --</option>';
        for (const [label, materialList] of Object.entries(categories)) {
            selectHTML += `<optgroup label="${label}">`;
            selectHTML += materialList.map(mat => `<option value="${mat}">${mat}</option>`).join('');
            selectHTML += `</optgroup>`;
        }

        const nistHtml = `
            <div class="property_item">
                <label for="nist_preset_select">NIST Presets:</label>
                <select id="nist_preset_select">${selectHTML}</select>
            </div>
            <p style="font-size: 12px; color: #666; margin-top: 5px; text-align: center;">
                Select a preset or type a NIST material name directly in the "Name" field above.
            </p>
        `;
        paramsDiv.innerHTML = nistHtml;
        
        // The name input at the top of the modal serves as the editable text field.
        const nistSelect = document.getElementById('nist_preset_select');
        nistSelect.addEventListener('change', () => {
            if (nistSelect.value) {
                nameInput.value = nistSelect.value;
            }
        });

        // Disable the selector if in edit mode
        if(isEditMode){
            nistSelect.disabled = true;
        }
    } else if (isSimple) {
        // Use the new component for each parameter
        paramsDiv.appendChild(ExpressionInput.create('mat_Z', 'Atomic Number (Z)', matData?.Z_expr || '1'));
        paramsDiv.appendChild(ExpressionInput.create('mat_A', 'Atomic Mass (g/mole)', matData?.A_expr || '1.008'));
        paramsDiv.appendChild(ExpressionInput.create('mat_density', 'Density (g/cm³)', matData?.density_expr || '1.0'));
    } else { // Mixture or Composite
        paramsDiv.appendChild(ExpressionInput.create('mat_density', 'Density (g/cm³)', matData?.density_expr || '1.0'));
        
        const hr = document.createElement('hr');

        // Dynamic title based on type
        const titleText = isComposite ? 'Elements (by # of Atoms)' : 'Components (by Mass Fraction)';

        const mixtureHtml = `
            <h6>${titleText}</h6>
            <div id="material-components-list"></div>
            <button id="add-mat-comp-btn" class="add_button" style="margin-top: 10px;">+ Add Component</button>`;
        const mixtureDiv = document.createElement('div');
        mixtureDiv.innerHTML = mixtureHtml;

        paramsDiv.appendChild(hr);
        paramsDiv.appendChild(mixtureDiv);
        
        document.getElementById('add-mat-comp-btn').addEventListener('click', addComponentRow);
        rebuildComponentsUI();
    }
}

function rebuildComponentsUI() {
    const listDiv = document.getElementById('material-components-list');
    if (!listDiv) return;
    listDiv.innerHTML = '';

    const isComposite = compositeRadio.checked; // Mixture by natoms
    const isMixture = mixtureRadio.checked;     // Mixture by fraction

    // --- Determine the correct set of available components ---
    let availableItems = {};
    if (isComposite) {
        availableItems['Elements'] = Object.keys(currentProjectState.elements || {});
    } else if (isMixture) {
        // For mixtures, we can add both Elements and other Materials
        availableItems['Elements'] = Object.keys(currentProjectState.elements || {});
        // Filter out the material being edited to prevent self-reference
        const availableMaterials = Object.keys(currentProjectState.materials || {})
            .filter(m => m !== editingMaterialId);
        availableItems['Materials'] = availableMaterials;
    }

    materialComponents.forEach((comp, index) => {
        const row = document.createElement('div');
        row.className = 'property_item';
        
        // --- Create the select dropdown for material reference ---
        const selectLabel = document.createElement('label');
        selectLabel.textContent = "Material:";
        
        const select = document.createElement('select');
        select.className = 'comp-ref';
        select.dataset.index = index;

        populateSelectWithOptions(select, availableItems);
        select.value = comp.ref;


        // --- Input for fraction or number of atoms ---
        const valueLabel = document.createElement('label');
        valueLabel.textContent = isComposite ? "# Atoms:" : "Fraction:";
        valueLabel.style.marginLeft = '10px';

        const valueKey = isComposite ? 'natoms' : 'fraction';
        const initialValue = comp[valueKey] || '0.0';

        const valueInputComponent = ExpressionInput.createInline(
            `mat_comp_val_${index}`,
            initialValue,
            (newValue) => {
                const component = materialComponents[index];
                if (isComposite) {
                    component.natoms = newValue;
                    delete component.fraction;
                } else {
                    component.fraction = newValue;
                    delete component.natoms;
                }
            }
        );

        // --- Create the remove button ---
        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-op-btn';
        removeBtn.dataset.index = index;
        removeBtn.textContent = '×';
        
        // --- Assemble the row ---
        row.appendChild(selectLabel);
        row.appendChild(select);
        row.appendChild(valueLabel);
        row.appendChild(valueInputComponent);
        row.appendChild(removeBtn);
        listDiv.appendChild(row);
    });

    // Attach listeners for select and remove buttons
    document.querySelectorAll('.comp-ref').forEach(el => el.addEventListener('change', updateComponentState));
    document.querySelectorAll('.remove-op-btn').forEach(btn => btn.addEventListener('click', removeComponentRow));
}

function addComponentRow() {
    const isComposite = compositeRadio.checked;
    const isMixture = mixtureRadio.checked;

    let availableRefs = [];
    if (isComposite) {
        availableRefs = Object.keys(currentProjectState.elements || {});
    } else if (isMixture) {
        const elements = Object.keys(currentProjectState.elements || {});
        const materials = Object.keys(currentProjectState.materials || {}).filter(m => m !== editingMaterialId);
        availableRefs = [...elements, ...materials];
    }

    if (availableRefs.length === 0) {
        alert(`No available ${isComposite ? 'elements' : 'components'} to add.`);
        return;
    }
    
    const newComponent = { ref: availableItems[0] };
    if (isComposite) {
        newComponent.natoms = '1'; // Default to 1 atom
    } else {
        newComponent.fraction = '0.0'; // Default to 0.0 fraction
    }
    materialComponents.push(newComponent);
    rebuildComponentsUI();
}

function removeComponentRow(event) {
    const index = parseInt(event.target.dataset.index, 10);
    materialComponents.splice(index, 1);
    rebuildComponentsUI();
}

function updateComponentState(event) {
    const index = parseInt(event.target.dataset.index, 10);
    // The fraction is updated live by the component's onChange callback.
    // We only need to handle the dropdown change here.
    if (event.target.classList.contains('comp-ref')) {
        materialComponents[index].ref = event.target.value;
    }
}

// A more advanced populateSelect function that handles optgroups
function populateSelectWithOptions(selectElement, optionsData) {
    selectElement.innerHTML = ''; // Clear existing options
    // Check if data is a simple array (for backward compatibility) or an object of groups
    if (Array.isArray(optionsData)) {
        optionsData.forEach(optionText => {
            const option = document.createElement('option');
            option.value = optionText;
            option.textContent = optionText;
            selectElement.appendChild(option);
        });
    } else { // It's an object of optgroups
        for (const groupLabel in optionsData) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = groupLabel;
            const items = optionsData[groupLabel];
            if (items.length === 0) {
                // Optionally add a disabled option to show the group is empty
                const disabledOption = document.createElement('option');
                disabledOption.textContent = `(No ${groupLabel} available)`;
                disabledOption.disabled = true;
                optgroup.appendChild(disabledOption);
            } else {
                items.forEach(itemText => {
                    const option = document.createElement('option');
                    option.value = itemText;
                    option.textContent = itemText;
                    optgroup.appendChild(option);
                });
            }
            selectElement.appendChild(optgroup);
        }
    }
}

function handleConfirm() {
    const name = nameInput.value.trim();
    if (!name && !isEditMode) { alert("Please provide a name."); return; }

    const isSimple = simpleRadio.checked;
    const isNIST = nistRadio.checked;

    let params = {};
    if (isSimple) {
        params = {
            mat_type: 'standard',
            Z_expr: document.getElementById('mat_Z').value,
            A_expr: document.getElementById('mat_A').value,
            density_expr: document.getElementById('mat_density').value,
            components: []
        };
    } else if (isNIST) {
        // Name only for NIST materials
        params = {
            mat_type: 'nist',
            components: [],
            Z_expr: null, // Let Geant4 calculate these
            A_expr: null,
            density_expr: null
        };
    } else if(!isNIST) {
        // For both Mixture and Composite
        params = {
            mat_type: 'standard',
            density_expr: document.getElementById('mat_density').value,
            components: materialComponents,
            Z_expr: null, // Let Geant4 calculate these
            A_expr: null
        };
    }
    
    onConfirmCallback({
        isEdit: isEditMode,
        id: isEditMode ? editingMaterialId : name,
        name: name,
        params: params
    });
    hide();
}