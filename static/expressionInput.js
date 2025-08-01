// static/expressionInput.js

import * as APIService from './apiService.js';

/**
 * Creates a complete expression input component with a label, input field, and result display.
 * @param {string} id - A unique base ID for the component's elements.
 * @param {string} label - The text label for the input.
 * @param {string} initialValue - The initial expression string.
 * @param {object} projectState - The current project state for evaluation context.
 * @param {function} onChange - A callback function to be fired when the value changes.
 * @returns {HTMLElement} The fully constructed component element.
 */
export function create(id, label, initialValue = '0', projectState, onChange = () => {}) {
    // Main container for the component
    const container = document.createElement('div');
    container.className = 'expression-component';

    // Label
    const labelEl = document.createElement('label');
    labelEl.htmlFor = id;
    labelEl.textContent = label;
    container.appendChild(labelEl);

    // Wrapper for the input and result fields
    const inputWrapper = document.createElement('div');
    inputWrapper.className = 'input-wrapper';
    
    // The expression input field
    const inputEl = document.createElement('input');
    inputEl.type = 'text';
    inputEl.id = id;
    inputEl.className = 'expression-input';
    inputEl.value = initialValue;
    inputWrapper.appendChild(inputEl);

    // The result display field
    const resultEl = document.createElement('input');
    resultEl.type = 'text';
    resultEl.id = `${id}-result`;
    resultEl.className = 'expression-result';
    resultEl.readOnly = true;
    resultEl.disabled = true;
    resultEl.tabIndex = -1; // Remove from tab order
    inputWrapper.appendChild(resultEl);
    
    container.appendChild(inputWrapper);

    // --- Evaluation Logic ---
    let debounceTimer;
    const evaluate = async () => {
        const expression = inputEl.value;
        if (!expression.trim()) {
            resultEl.value = '';
            resultEl.title = '';
            inputEl.style.borderColor = '';
            resultEl.style.borderColor = '';
            return;
        }
        try {
            // Use the provided projectState for context
            const response = await APIService.evaluateExpression(expression, projectState);
            if (response.success) {
                resultEl.value = response.result.toPrecision(4);
                resultEl.style.borderColor = '';
                inputEl.style.borderColor = '#8f8'; // Greenish for valid
            } else {
                resultEl.value = 'ERR';
                resultEl.style.borderColor = 'red';
                inputEl.style.borderColor = 'red';
                resultEl.title = response.error;
            }
        } catch (error) {
            resultEl.value = 'ERR';
            resultEl.style.borderColor = 'red';
            inputEl.style.borderColor = 'red';
            resultEl.title = error.message;
        }
    };

    // Attach event listeners
    inputEl.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(evaluate, 300); // Debounce to avoid API spam
    });
    
    // When the input loses focus (change event) or on creation,
    // call the provided onChange handler.
    inputEl.addEventListener('change', () => onChange(inputEl.value));
    
    // Initial evaluation on creation
    evaluate();

    return container;
}

/**
 * Creates a compact, inline expression input component without a top label.
 * Ideal for lists or tables where the label is separate.
 * @param {string} id - A unique base ID for the component's elements.
 * @param {string} initialValue - The initial expression string.
 * @param {object} projectState - The current project state for evaluation context.
 * @param {function} onChange - A callback function to be fired when the value changes.
 * @returns {HTMLElement} The fully constructed component wrapper element.
 */
export function createInline(id, initialValue = '0', projectState, onChange = () => {}) {
    const wrapper = document.createElement('div');
    wrapper.className = 'input-wrapper'; // Use the same class for consistent styling
    
    const inputEl = document.createElement('input');
    inputEl.type = 'text';
    inputEl.id = id;
    inputEl.className = 'expression-input';
    inputEl.value = initialValue;
    wrapper.appendChild(inputEl);

    const resultEl = document.createElement('input');
    resultEl.type = 'text';
    resultEl.id = `${id}-result`;
    resultEl.className = 'expression-result';
    resultEl.readOnly = true;
    resultEl.disabled = true;
    resultEl.tabIndex = -1;
    wrapper.appendChild(resultEl);
    
    // --- Evaluation Logic (Identical to the main component) ---
    let debounceTimer;
    const evaluate = async () => {
        const expression = inputEl.value;
        if (!expression.trim()) {
            resultEl.value = '';
            resultEl.title = '';
            inputEl.style.borderColor = '';
            resultEl.style.borderColor = '';
            return;
        }
        try {
            const response = await APIService.evaluateExpression(expression, projectState);
            if (response.success) {
                resultEl.value = response.result.toPrecision(4);
                resultEl.style.borderColor = '';
                inputEl.style.borderColor = '#8f8';
            } else {
                resultEl.value = 'ERR';
                resultEl.style.borderColor = 'red';
                inputEl.style.borderColor = 'red';
                resultEl.title = response.error;
            }
        } catch (error) {
            resultEl.value = 'ERR';
            resultEl.style.borderColor = 'red';
            inputEl.style.borderColor = 'red';
            resultEl.title = error.message;
        }
    };

    inputEl.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(evaluate, 300);
        // We call the onChange immediately on input for live updates in the material editor state
        onChange(inputEl.value); 
    });
    
    inputEl.addEventListener('change', () => onChange(inputEl.value));
    
    // Initial evaluation
    evaluate();

    return wrapper;
}