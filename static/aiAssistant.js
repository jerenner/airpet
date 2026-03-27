// static/aiAssistant.js
import * as APIService from './apiService.js';
import * as UIManager from './uiManager.js';
import { formatBackendDiagnosticsError } from './backendDiagnosticsUi.js';
import {
    runtimeConfigToFormState,
    buildRuntimeConfigPayloadFromFormState,
    getLocalRuntimeBackendIds,
} from './aiRuntimeConfigUi.js';

let messageList, promptInput, generateButton, clearButton, modelSelect, contextStatsEl;
let isProcessing = false;
let onGeometryUpdateCallback = () => {};
let localUnsavedMessages = [];
let currentRecentTools = [];
let currentTurn = 1;
let currentTurnLimit = 10;

let runtimeConfigButton, runtimeConfigStatusEl;
let runtimeConfigModal, runtimeConfigErrorEl;
let runtimeConfigReloadBtn, runtimeConfigClearBtn, runtimeConfigCancelBtn, runtimeConfigSaveBtn;
let runtimeConfigFormEls = {};
let runtimeConfigLoaded = false;
let historyLoaded = false;

export function init(callbacks) {
    messageList = document.getElementById('ai_message_list');
    promptInput = document.getElementById('ai_prompt_input');
    generateButton = document.getElementById('ai_generate_button');
    clearButton = document.getElementById('clear_chat_btn');
    modelSelect = document.getElementById('ai_model_select');
    contextStatsEl = document.getElementById('ai_context_stats');

    initRuntimeConfigUi();

    if (callbacks && callbacks.onGeometryUpdate) {
        onGeometryUpdateCallback = callbacks.onGeometryUpdate;
    }

    generateButton.addEventListener('click', handleSend);
    promptInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    });

    if (clearButton) {
        clearButton.addEventListener('click', handleClear);
    }

    if (modelSelect) {
        modelSelect.addEventListener('change', () => {
            refreshContextStats();
            UIManager.updateAiBackendStatus?.();
        });
    }

    // Load existing history
    loadHistory();
    loadRuntimeConfigProfile({ quiet: true });
}

function initRuntimeConfigUi() {
    runtimeConfigButton = document.getElementById('ai_runtime_config_btn');
    runtimeConfigStatusEl = document.getElementById('ai_runtime_config_status');
    runtimeConfigModal = document.getElementById('aiRuntimeConfigModal');
    runtimeConfigErrorEl = document.getElementById('ai_runtime_config_error');
    runtimeConfigReloadBtn = document.getElementById('ai_runtime_config_reload_btn');
    runtimeConfigClearBtn = document.getElementById('ai_runtime_config_clear_btn');
    runtimeConfigCancelBtn = document.getElementById('ai_runtime_config_cancel_btn');
    runtimeConfigSaveBtn = document.getElementById('ai_runtime_config_save_btn');

    runtimeConfigFormEls = {};
    getLocalRuntimeBackendIds().forEach((backendId) => {
        runtimeConfigFormEls[backendId] = {
            enabled: document.getElementById(`ai_runtime_${backendId}_enabled`),
            base_url: document.getElementById(`ai_runtime_${backendId}_base_url`),
            endpoint_path: document.getElementById(`ai_runtime_${backendId}_endpoint_path`),
            model: document.getElementById(`ai_runtime_${backendId}_model`),
            timeout_seconds: document.getElementById(`ai_runtime_${backendId}_timeout_seconds`),
            max_retries: document.getElementById(`ai_runtime_${backendId}_max_retries`),
            retry_backoff_seconds: document.getElementById(`ai_runtime_${backendId}_retry_backoff_seconds`),
            verify_tls: document.getElementById(`ai_runtime_${backendId}_verify_tls`),
            headers_json: document.getElementById(`ai_runtime_${backendId}_headers_json`),
        };
    });

    setRuntimeConfigStatus('Runtime profile: loading…', 'info');

    if (runtimeConfigButton) {
        runtimeConfigButton.addEventListener('click', () => {
            if (!runtimeConfigModal) return;
            runtimeConfigModal.style.display = 'block';
            setRuntimeConfigError('', 'neutral');
            if (!runtimeConfigLoaded) {
                loadRuntimeConfigProfile({ quiet: true });
            }
        });
    }

    if (runtimeConfigCancelBtn) {
        runtimeConfigCancelBtn.addEventListener('click', () => {
            if (runtimeConfigModal) runtimeConfigModal.style.display = 'none';
        });
    }

    if (runtimeConfigReloadBtn) {
        runtimeConfigReloadBtn.addEventListener('click', () => {
            loadRuntimeConfigProfile({ quiet: false });
        });
    }

    if (runtimeConfigSaveBtn) {
        runtimeConfigSaveBtn.addEventListener('click', handleSaveRuntimeConfigProfile);
    }

    if (runtimeConfigClearBtn) {
        runtimeConfigClearBtn.addEventListener('click', handleClearRuntimeConfigProfile);
    }
}

function setRuntimeConfigStatus(message, kind = 'info') {
    if (!runtimeConfigStatusEl) return;

    runtimeConfigStatusEl.className = 'ai-model-info ai-runtime-config-status';
    runtimeConfigStatusEl.classList?.add(`status-${kind}`);
    runtimeConfigStatusEl.textContent = message;
}

function setRuntimeConfigError(message, kind = 'error') {
    if (!runtimeConfigErrorEl) return;

    runtimeConfigErrorEl.className = `ai-runtime-feedback ${kind}`;
    runtimeConfigErrorEl.textContent = message || '';
    runtimeConfigErrorEl.style.display = message ? 'block' : 'none';
}

function setRuntimeConfigFormBusy(isBusy) {
    const fieldGroups = Object.values(runtimeConfigFormEls || {});
    fieldGroups.forEach((fields) => {
        Object.values(fields || {}).forEach((el) => {
            if (el) el.disabled = isBusy;
        });
    });

    if (runtimeConfigSaveBtn) runtimeConfigSaveBtn.disabled = isBusy;
    if (runtimeConfigReloadBtn) runtimeConfigReloadBtn.disabled = isBusy;
    if (runtimeConfigClearBtn) runtimeConfigClearBtn.disabled = isBusy;
}

function collectRuntimeConfigFormState() {
    const backends = {};

    getLocalRuntimeBackendIds().forEach((backendId) => {
        const fields = runtimeConfigFormEls[backendId] || {};
        backends[backendId] = {
            enabled: !!fields.enabled?.checked,
            base_url: fields.base_url?.value ?? '',
            endpoint_path: fields.endpoint_path?.value ?? '',
            model: fields.model?.value ?? '',
            timeout_seconds: fields.timeout_seconds?.value ?? '',
            max_retries: fields.max_retries?.value ?? '',
            retry_backoff_seconds: fields.retry_backoff_seconds?.value ?? '',
            verify_tls: !!fields.verify_tls?.checked,
            headers_json: fields.headers_json?.value ?? '',
        };
    });

    return { backends };
}

function applyRuntimeConfigFormState(formState) {
    const backendForms = formState?.backends || {};

    getLocalRuntimeBackendIds().forEach((backendId) => {
        const fields = runtimeConfigFormEls[backendId] || {};
        const values = backendForms[backendId] || {};

        if (fields.enabled) fields.enabled.checked = !!values.enabled;
        if (fields.base_url) fields.base_url.value = values.base_url ?? '';
        if (fields.endpoint_path) fields.endpoint_path.value = values.endpoint_path ?? '';
        if (fields.model) fields.model.value = values.model ?? '';
        if (fields.timeout_seconds) fields.timeout_seconds.value = values.timeout_seconds ?? '';
        if (fields.max_retries) fields.max_retries.value = values.max_retries ?? '';
        if (fields.retry_backoff_seconds) fields.retry_backoff_seconds.value = values.retry_backoff_seconds ?? '';
        if (fields.verify_tls) fields.verify_tls.checked = !!values.verify_tls;
        if (fields.headers_json) fields.headers_json.value = values.headers_json ?? '{}';
    });
}

function hasSessionRuntimeOverrides(runtimeConfig) {
    if (!runtimeConfig || typeof runtimeConfig !== 'object') return false;
    const backendMap = runtimeConfig.backends && typeof runtimeConfig.backends === 'object'
        ? runtimeConfig.backends
        : runtimeConfig;

    return getLocalRuntimeBackendIds().some((backendId) => {
        const value = backendMap[backendId];
        return value && typeof value === 'object' && Object.keys(value).length > 0;
    });
}

async function refreshRuntimeConfigDiagnostics() {
    try {
        const diagResponse = await APIService.getAiBackendDiagnostics(['llama_cpp', 'lm_studio']);
        if (diagResponse?.success && Array.isArray(diagResponse.diagnostics)) {
            diagResponse.diagnostics.forEach(diagnostic => {
                UIManager.upsertAiBackendDiagnostic?.(diagnostic);
            });
        }
    } catch (_diagErr) {
    }
}

async function loadRuntimeConfigProfile({ quiet = false } = {}) {
    if (!quiet) {
        setRuntimeConfigError('', 'neutral');
    }

    setRuntimeConfigFormBusy(true);
    try {
        const response = await APIService.getAiBackendRuntimeConfig();
        const runtimeConfig = response?.runtime_config || {};
        applyRuntimeConfigFormState(runtimeConfigToFormState(runtimeConfig));
        runtimeConfigLoaded = true;

        if (hasSessionRuntimeOverrides(runtimeConfig)) {
            setRuntimeConfigStatus('Runtime profile: using saved profile (session-scoped; request overrides win).', 'ok');
        } else {
            setRuntimeConfigStatus('Runtime profile: using built-in defaults (no saved session profile).', 'info');
        }

        await refreshRuntimeConfigDiagnostics();

        if (!quiet) {
            setRuntimeConfigError('Runtime profile reloaded from this session. Saved defaults are session-scoped, and request overrides still take precedence.', 'ok');
        }
    } catch (err) {
        const message = `Failed to load runtime profile: ${err.message || err}`;
        setRuntimeConfigStatus('Runtime profile: load failed.', 'error');
        setRuntimeConfigError(message, 'error');
    } finally {
        setRuntimeConfigFormBusy(false);
    }
}

async function handleSaveRuntimeConfigProfile() {
    setRuntimeConfigError('', 'neutral');

    const payloadResult = buildRuntimeConfigPayloadFromFormState(collectRuntimeConfigFormState());
    if (!payloadResult.ok) {
        setRuntimeConfigStatus('Runtime profile: validation error.', 'error');
        setRuntimeConfigError(payloadResult.error, 'error');
        return;
    }

    setRuntimeConfigFormBusy(true);
    try {
        const response = await APIService.saveAiBackendRuntimeConfig(payloadResult.runtimeConfig);
        const runtimeConfig = response?.runtime_config || {};

        applyRuntimeConfigFormState(runtimeConfigToFormState(runtimeConfig));
        runtimeConfigLoaded = true;

        setRuntimeConfigStatus('Runtime profile: using saved profile (session-scoped; request overrides win).', 'ok');
        setRuntimeConfigError('Saved. These defaults now apply to diagnostics/chat for this session unless a request sends explicit runtime overrides.', 'ok');

        await refreshRuntimeConfigDiagnostics();
    } catch (err) {
        const message = `Failed to save runtime profile: ${err.message || err}`;
        setRuntimeConfigStatus('Runtime profile: save failed.', 'error');
        setRuntimeConfigError(message, 'error');
    } finally {
        setRuntimeConfigFormBusy(false);
    }
}

async function handleClearRuntimeConfigProfile() {
    const shouldClear = confirm('Clear the saved local runtime profile for this session and revert to defaults?');
    if (!shouldClear) return;

    setRuntimeConfigError('', 'neutral');
    setRuntimeConfigFormBusy(true);

    try {
        const response = await APIService.clearAiBackendRuntimeConfig();
        const runtimeConfig = response?.runtime_config || {};

        applyRuntimeConfigFormState(runtimeConfigToFormState(runtimeConfig));
        runtimeConfigLoaded = true;

        setRuntimeConfigStatus('Runtime profile: using built-in defaults (saved session profile cleared).', 'info');
        setRuntimeConfigError('Saved session profile cleared. Built-in backend defaults are now active for diagnostics/chat.', 'ok');

        await refreshRuntimeConfigDiagnostics();
    } catch (err) {
        const message = `Failed to clear runtime profile: ${err.message || err}`;
        setRuntimeConfigStatus('Runtime profile: clear failed.', 'error');
        setRuntimeConfigError(message, 'error');
    } finally {
        setRuntimeConfigFormBusy(false);
    }
}

async function loadHistory(force = false) {
    // Prevent duplicate loading on initial page load
    if (!force && historyLoaded) {
        console.log('loadHistory: skipped (already loaded)');
        return;
    }
    
    try {
        console.log('loadHistory: fetching history...', { force, historyLoaded });
        const res = await APIService.getAiChatHistory();
        console.log('loadHistory: received history with', res.history?.length || 0, 'messages');
        if (res.history) {
            renderHistory(res.history);
            historyLoaded = true;
        }
        
        // Only load unsaved messages from localStorage if history is empty (no server data)
        // Otherwise, messages are already in the server history and will be rendered below
        const savedMessages = localStorage.getItem('airpet_unsaved_messages');
        if (savedMessages && history.length === 0) {
            try {
                localUnsavedMessages = JSON.parse(savedMessages);
                localUnsavedMessages.forEach(msg => {
                    addMessageToUI(msg.role, msg.text);
                });
                localUnsavedMessages = [];
                localStorage.removeItem('airpet_unsaved_messages');
            } catch (e) {
                console.error('Failed to parse unsaved messages:', e);
            }
        } else if (savedMessages && history.length > 0) {
            // Clear localStorage since messages are now on the server
            localStorage.removeItem('airpet_unsaved_messages');
        }
    } catch (err) {
        console.error("Failed to load chat history:", err);
    } finally {
        refreshContextStats();
    }
}

export function reloadHistory() {
    loadHistory(true);
}

  function renderHistory(history) {
    console.log('renderHistory: called with', history.length, 'messages');
    messageList.innerHTML = '';
    // Skip the first two messages (system instructions)
    if (history.length <= 2) {
        addMessageToUI('system', "Welcome to AIRPET AI. How can I help you with your detector geometry today?", false);
        return;
    }
    
    // Group messages by turn: [user msg, intermediate msgs..., final msg]
    const turns = [];
    let currentTurn = [];
    
    history.slice(2).forEach(msg => {
        // Skip tool results and system messages
        if (msg.role === 'tool' || msg.role === 'system') return;
        
        const isUser = msg.role === 'user';
        const isIntermediate = (msg.role === 'assistant' || msg.role === 'model') && msg.metadata && msg.metadata._intermediate;
        const isFinal = (msg.role === 'assistant' || msg.role === 'model') && (!msg.metadata || !msg.metadata._intermediate);
        
        if (isUser) {
            // Start new turn with user message
            if (currentTurn.length > 0) {
                turns.push(currentTurn);
            }
            currentTurn = [{ type: 'user', msg }];
        } else if (isIntermediate) {
            // Add intermediate message to current turn
            currentTurn.push({ type: 'intermediate', msg });
        } else if (isFinal) {
            // Add final message and close turn
            currentTurn.push({ type: 'final', msg });
            turns.push(currentTurn);
            currentTurn = [];
        }
    });
    
    // Render each turn
    turns.forEach(turn => {
        turn.forEach(item => {
            let text = "";
            if (item.msg.role === 'user' && item.msg.metadata && item.msg.metadata.original_message) {
                text = item.msg.metadata.original_message;
            } else {
                text = item.msg.parts ? item.msg.parts.map(p => p.text || '').join('\n').trim() : (item.msg.content || '').trim();
            }
            
            if (text && !text.startsWith('[System Context Update]')) {
                if (item.type === 'user') {
                    addMessageToUI('user', text, false);
                } else if (item.type === 'final') {
                    addMessageToUI('model', text, false);
                    // Add thinking dropdown if there were intermediate steps
                    const intermediates = turn.filter(t => t.type === 'intermediate');
                    if (intermediates.length > 0) {
                        addThinkingDropdown(intermediates);
                    }
                }
            }
        });
    });

    // Ensure the model selector is synced if history was loaded
    if (history.length > 0) {
        // Trigger a tiny delay to ensure models are loaded
        setTimeout(() => {
            // Find the last message that has a model_id in its metadata
            const lastModelMsg = [...history].reverse().find(m => m.metadata && m.metadata.model_id);
            if (lastModelMsg && lastModelMsg.metadata.model_id) {
                const select = document.getElementById('ai_model_select');
                if (select) select.value = lastModelMsg.metadata.model_id;
            }
        }, 500);
    }
    scrollToBottom();
}

async function handleSend() {
    if (isProcessing) return;
    
    const message = promptInput.value.trim();
    if (!message) return;

    const model = UIManager.getAiSelectedModel();
    if (!model || model === '--export--') {
        UIManager.showError("Please select a valid AI model for chat.");
        return;
    }

    const turnLimitInput = document.getElementById('ai_turn_limit');
    const turnLimit = turnLimitInput ? parseInt(turnLimitInput.value, 10) : 10;

    setLoading(true);
    addMessageToUI('user', message);
    promptInput.value = '';
    scrollToBottom();

    currentRecentTools = [];
    currentTurn = 1;
    currentTurnLimit = turnLimit;

    const thinkingIndicator = createThinkingIndicator();
    
    try {
        const result = await APIService.streamAiChatMessage(message, model, turnLimit, (progress) => {
            updateThinkingIndicator(thinkingIndicator, progress);
        });
        removeThinkingIndicator(thinkingIndicator);
        addMessageToUI('model', result.message);
        
        if (onGeometryUpdateCallback) {
            onGeometryUpdateCallback(result);
        }
    } catch (err) {
        removeThinkingIndicator(thinkingIndicator);
        const backendError = formatBackendDiagnosticsError(err);

        if (backendError) {
            UIManager.showError("AI Error: " + backendError.alertMessage);
            addMessageToUI('system', backendError.chatMessage);
            UIManager.upsertAiBackendDiagnostic?.(backendError.readiness);

            try {
                const diagResponse = await APIService.getAiBackendDiagnostics(['llama_cpp', 'lm_studio']);
                if (diagResponse?.success && Array.isArray(diagResponse.diagnostics)) {
                    diagResponse.diagnostics.forEach(diagnostic => {
                        UIManager.upsertAiBackendDiagnostic?.(diagnostic);
                    });
                }
            } catch (_diagErr) {
            }
        } else {
            UIManager.showError("AI Error: " + err.message);
            addMessageToUI('system', "Error: " + err.message);
        }
    } finally {
        setLoading(false);
        scrollToBottom();
        refreshContextStats();
    }
}

async function handleClear() {
    if (!confirm("Clear AI chat history? This won't undo geometry changes.")) return;
    try {
        await APIService.clearAiChatHistory();
        messageList.innerHTML = '';
        addMessageToUI('system', "History cleared.");
        historyLoaded = false;
    } catch (err) {
        UIManager.showError("Failed to clear history: " + err.message);
    } finally {
        refreshContextStats();
    }
}

function addMessageToUI(role, text, skipSave = false) {
    const div = document.createElement('div');
    div.className = `chat-message ${role} markdown-content`;
    
    const formattedText = marked.marked(text);
    div.innerHTML = formattedText;
    messageList.appendChild(div);
    
    if (!skipSave && (role === 'user' || role === 'model')) {
        localUnsavedMessages.push({ role, text });
        try {
            localStorage.setItem('airpet_unsaved_messages', JSON.stringify(localUnsavedMessages));
        } catch (e) {
            console.warn('Failed to save unsaved messages to localStorage:', e);
        }
    }
}

async function refreshContextStats() {
    if (!contextStatsEl) return;
    const model = UIManager.getAiSelectedModel?.() || '';
    try {
        const stats = await APIService.getAiContextStats(model);
        if (!stats.success) throw new Error(stats.error || 'Could not read context stats');

        const sourceLabel = stats.context_source === 'gemini'
            ? 'Gemini'
            : (stats.context_source === 'ollama'
                ? 'Ollama'
                : (stats.context_source === 'llama_cpp'
                    ? 'llama.cpp'
                    : (stats.context_source === 'lm_studio' ? 'LM Studio' : 'Unknown')));

        if (stats.max_context_tokens) {
            contextStatsEl.textContent = `Context: ~${stats.estimated_tokens}/${stats.max_context_tokens} (${sourceLabel})`;
        } else {
            contextStatsEl.textContent = `Context: ~${stats.estimated_tokens} tokens (${sourceLabel})`;
        }
    } catch (err) {
        contextStatsEl.textContent = 'Context: n/a';
    }
}

function setLoading(loading) {
    isProcessing = loading;
    generateButton.classList.toggle('loading', loading);
    generateButton.disabled = loading;
    promptInput.disabled = loading;
}

function scrollToBottom() {
    messageList.scrollTop = messageList.scrollHeight;
}

function scrollToBottomSmooth() {
    messageList.scrollTo({
        top: messageList.scrollHeight,
        behavior: 'smooth'
    });
}

function createThinkingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'chat-message model thinking-indicator';
    indicator.id = 'ai-thinking-indicator';
    indicator.innerHTML = '<span class="thinking-text">Thinking...</span>';
    messageList.appendChild(indicator);
    scrollToBottom();
    return indicator;
}

function updateThinkingIndicator(indicator, progress) {
    if (!indicator || !indicator.isConnected) return;
    
    const thinkingText = indicator.querySelector('.thinking-text');
    
    if (progress.type === 'turn_start') {
        currentTurn = progress.turn;
        currentTurnLimit = progress.turnLimit;
        
        if (currentRecentTools.length > 0) {
            const turnBadge = `<span class="turn-badge">Turn ${currentTurn}/${currentTurnLimit}</span>`;
            const toolsHtml = currentRecentTools.map(tool => 
                `<div class="tool-entry">🛠️ ${tool}</div>`
            ).join('');
            thinkingText.innerHTML = `${turnBadge}<div class="tools-list">${toolsHtml}</div>`;
        } else {
            thinkingText.innerHTML = `<span class="turn-badge">Turn ${currentTurn}/${currentTurnLimit}</span> Processing...`;
        }
    } else if (progress.type === 'tool_calls' && progress.tools && progress.tools.length > 0) {
        currentTurn = progress.turn;
        
        if (progress.recentTools && progress.recentTools.length > 0) {
            currentRecentTools = progress.recentTools;
        } else {
            currentRecentTools = [...currentRecentTools, ...progress.tools].slice(-3);
        }
        
        const turnBadge = `<span class="turn-badge">Turn ${currentTurn}/${currentTurnLimit}</span>`;
        const toolsHtml = currentRecentTools.map(tool => 
            `<div class="tool-entry">🛠️ ${tool}</div>`
        ).join('');
        thinkingText.innerHTML = `${turnBadge}<div class="tools-list">${toolsHtml}</div>`;
    } else if (progress.type === 'paused') {
        thinkingText.innerHTML = `<span class="pause-badge">⏸️ Paused</span> ${progress.reason || 'tab hidden'}`;
    } else if (progress.type === 'resumed') {
        if (progress.recentTools && progress.recentTools.length > 0) {
            currentRecentTools = progress.recentTools;
        }
        
        const turnBadge = `<span class="turn-badge">Turn ${currentTurn}/${currentTurnLimit}</span>`;
        const toolsHtml = currentRecentTools.map(tool => 
            `<div class="tool-entry">🛠️ ${tool}</div>`
        ).join('');
        thinkingText.innerHTML = `${turnBadge}<div class="tools-list">${toolsHtml}</div>`;
    }
    
    scrollToBottom();
}

function removeThinkingIndicator(indicator) {
    if (indicator && indicator.isConnected) {
        indicator.remove();
    }
    currentRecentTools = [];
}

function addThinkingDropdown(intermediates) {
    const dropdown = document.createElement('div');
    dropdown.className = 'chat-message model thinking-dropdown';
    
    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'thinking-toggle';
    toggleBtn.innerHTML = `🤔 Thinking (${intermediates.length} step${intermediates.length > 1 ? 's' : ''}) ▼`;
    toggleBtn.onclick = () => toggleThinkingDropdown(dropdown);
    
    const content = document.createElement('div');
    content.className = 'thinking-content';
    content.style.display = 'none';
    
    intermediates.forEach((item, idx) => {
        const text = item.msg.parts ? item.msg.parts.map(p => p.text || '').join('\n').trim() : (item.msg.content || '').trim();
        if (text && !text.startsWith('[System Context Update]')) {
            const step = document.createElement('div');
            step.className = 'thinking-step';
            step.innerHTML = `<strong>Step ${idx + 1}:</strong> ${marked.marked.parse(text)}`;
            content.appendChild(step);
        }
        
        // Show tool calls if any
        if (item.msg.tool_calls && item.msg.tool_calls.length > 0) {
            const toolDiv = document.createElement('div');
            toolDiv.className = 'thinking-tools';
            toolDiv.innerHTML = `<strong>Tools called:</strong> ${item.msg.tool_calls.map(tc => tc.function?.name || tc.name).join(', ')}`;
            content.appendChild(toolDiv);
        }
    });
    
    dropdown.appendChild(toggleBtn);
    dropdown.appendChild(content);
    messageList.appendChild(dropdown);
}

function toggleThinkingDropdown(dropdown) {
    const content = dropdown.querySelector('.thinking-content');
    const toggleBtn = dropdown.querySelector('.thinking-toggle');
    
    if (content.style.display === 'none') {
        content.style.display = 'block';
        toggleBtn.innerHTML = toggleBtn.innerHTML.replace('▼', '▲');
    } else {
        content.style.display = 'none';
        toggleBtn.innerHTML = toggleBtn.innerHTML.replace('▲', '▼');
    }
}
