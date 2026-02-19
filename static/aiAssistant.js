// static/aiAssistant.js
import * as APIService from './apiService.js';
import * as UIManager from './uiManager.js';

let messageList, promptInput, generateButton, clearButton, modelSelect, contextStatsEl;
let isProcessing = false;
let onGeometryUpdateCallback = () => {};

export function init(callbacks) {
    messageList = document.getElementById('ai_message_list');
    promptInput = document.getElementById('ai_prompt_input');
    generateButton = document.getElementById('ai_generate_button');
    clearButton = document.getElementById('clear_chat_btn');
    modelSelect = document.getElementById('ai_model_select');
    contextStatsEl = document.getElementById('ai_context_stats');
    
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
        modelSelect.addEventListener('change', refreshContextStats);
    }

    // Load existing history
    loadHistory();
}

async function loadHistory() {
    try {
        const res = await APIService.getAiChatHistory();
        if (res.history) {
            renderHistory(res.history);
        }
    } catch (err) {
        console.error("Failed to load chat history:", err);
    } finally {
        refreshContextStats();
    }
}

export function reloadHistory() {
    loadHistory();
}

function renderHistory(history) {
    messageList.innerHTML = '';
    // Skip the first two messages (system instructions)
    if (history.length <= 2) {
        addMessageToUI('system', "Welcome to AIRPET AI. How can I help you with your detector geometry today?");
        return;
    }
    history.slice(2).forEach(msg => {
        // Gemini API uses 'parts' with 'text', Ollama uses 'content'
        // Skip tool results and system updates
        if (msg.role === 'tool' || msg.role === 'system') return;
        
        // --- NEW: Use original_message from metadata if available ---
        let text = "";
        if (msg.role === 'user' && msg.metadata && msg.metadata.original_message) {
            text = msg.metadata.original_message;
        } else {
            text = msg.parts ? msg.parts.map(p => p.text || '').join('\n').trim() : (msg.content || '').trim();
        }
        
        if (text && !text.startsWith('[System Context Update]')) {
            addMessageToUI(msg.role === 'user' ? 'user' : 'model', text);
        }
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

    try {
        const result = await APIService.sendAiChatMessage(message, model, turnLimit);
        addMessageToUI('model', result.message);
        
        // Notify main.js that geometry might have changed
        if (onGeometryUpdateCallback) {
            onGeometryUpdateCallback(result);
        }
    } catch (err) {
        UIManager.showError("AI Error: " + err.message);
        addMessageToUI('system', "Error: " + err.message);
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
    } catch (err) {
        UIManager.showError("Failed to clear history: " + err.message);
    } finally {
        refreshContextStats();
    }
}

function addMessageToUI(role, text) {
    const div = document.createElement('div');
    div.className = `chat-message ${role}`;
    
    // Simple markdown-ish rendering for code blocks or tool calls
    // In the future, we could use a proper library like marked.js
    let formattedText = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\n/g, "<br>");
    
    // Highlight bracketed tool calls if present in the text (often added by AI explanation)
    formattedText = formattedText.replace(/\[Tool: (.*?)\]/g, '<span class="tool-call">🛠️ $1</span>');

    div.innerHTML = formattedText;
    messageList.appendChild(div);
}

async function refreshContextStats() {
    if (!contextStatsEl) return;
    const model = UIManager.getAiSelectedModel?.() || '';
    try {
        const stats = await APIService.getAiContextStats(model);
        if (!stats.success) throw new Error(stats.error || 'Could not read context stats');

        if (stats.max_context_tokens) {
            contextStatsEl.textContent = `Context: ~${stats.estimated_tokens}/${stats.max_context_tokens} (${stats.utilization_pct || 0}%)`;
        } else {
            contextStatsEl.textContent = `Context: ~${stats.estimated_tokens} tokens`;
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
