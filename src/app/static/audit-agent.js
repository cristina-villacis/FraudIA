/**
 * Asistente de IA conversacional — chat conectado al análisis completo (dataset, ML, dashboard).
 */
const AuditAgent = (function () {
    const SUGGESTIONS = [
        '¿Cuántos casos rojos hay y cuál es el monto total expuesto?',
        'Explícame el siniestro con mayor score y por qué está en rojo.',
        '¿Qué proveedores concentran más alertas?',
        'Compara el riesgo entre ramos de la cartera.',
    ];

    let initialized = false;
    const chatHistory = [];

    function shell() {
        return document.getElementById('auditAgentContent');
    }

    function messagesEl() {
        return document.getElementById('auditChatMessages');
    }

    function inputEl() {
        return document.getElementById('auditChatInput');
    }

    function renderShell() {
        const root = shell();
        if (!root || root.dataset.rendered === '1') return;
        root.dataset.rendered = '1';
        root.innerHTML = `
            <div class="audit-header">
                <h2>Asistente de IA conversacional</h2>
                <p>Pregunte en lenguaje natural sobre su cartera completa. Le explico por qué un caso está en
                <strong>alto</strong>, <strong>medio</strong> o <strong>bajo</strong> riesgo — siempre como alerta de revisión, no como veredicto.</p>
            </div>
            <div class="audit-status-bar" id="auditStatusBar">
                <span class="audit-status-pill warn" id="auditDatasetPill">Cartera: verificando…</span>
            </div>
            <div class="audit-suggestions" id="auditSuggestions"></div>
            <div class="audit-chat-shell">
                <div class="audit-chat-messages" id="auditChatMessages" aria-live="polite"></div>
                <div class="audit-input-row">
                    <textarea id="auditChatInput" rows="1" placeholder="Ej: ¿Por qué SIN-000042 está en rojo?"></textarea>
                    <button type="button" class="audit-send-btn" id="auditChatSend">Consultar</button>
                </div>
            </div>
        `;

        const sug = document.getElementById('auditSuggestions');
        if (sug) {
            sug.innerHTML = SUGGESTIONS.map((q) =>
                `<button type="button" data-audit-q="${escapeAttr(q)}">${escapeHtml(q)}</button>`
            ).join('');
            sug.querySelectorAll('button').forEach((btn) => {
                btn.addEventListener('click', () => send(btn.dataset.auditQ || ''));
            });
        }

        const sendBtn = document.getElementById('auditChatSend');
        const input = inputEl();
        if (sendBtn) sendBtn.addEventListener('click', () => send());
        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    send();
                }
            });
        }

        appendWelcome();
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function escapeAttr(s) {
        return escapeHtml(s).replace(/'/g, '&#39;');
    }

    function appendWelcome() {
        const msgs = messagesEl();
        if (!msgs || msgs.dataset.welcome === '1') return;
        msgs.dataset.welcome = '1';
        appendAgentMessage(
            'Hola, soy su Asistente de IA conversacional en FXecure. Tras cargar y analizar su cartera, '
            + 'puede preguntarme lo que necesite en lenguaje natural: un caso concreto, comparaciones, '
            + 'proveedores, montos o el porqué de un semáforo. Respondo con los datos de su análisis actual.',
            null
        );
    }

    function appendUserMessage(text) {
        const msgs = messagesEl();
        if (!msgs) return;
        const div = document.createElement('div');
        div.className = 'audit-msg user';
        div.textContent = text;
        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;
    }

    function appendAgentMessage(html, meta) {
        const msgs = messagesEl();
        if (!msgs) return;
        const div = document.createElement('div');
        div.className = 'audit-msg agent';
        div.innerHTML = html + (meta ? `<div class="audit-msg-meta">${meta}</div>` : '');
        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;
    }

    function appendError(text) {
        const msgs = messagesEl();
        if (!msgs) return;
        const div = document.createElement('div');
        div.className = 'audit-msg agent error';
        div.textContent = text;
        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;
    }

    async function refreshStatus() {
        const dsPill = document.getElementById('auditDatasetPill');
        try {
            const opts = typeof withFraudiaSessionHeaders === 'function'
                ? withFraudiaSessionHeaders({})
                : {};
            const resp = await fetch('/api/agent-status', opts);
            const data = await resp.json();
            if (dsPill) {
                const n = data.siniestros_count;
                if (data.pipeline_ready && n != null) {
                    dsPill.textContent = `Dataset procesado: ${Number(n).toLocaleString()} siniestros`;
                    dsPill.className = 'audit-status-pill ready';
                } else {
                    dsPill.textContent = 'Dataset: sin análisis — cargue Excel y active motor IA';
                    dsPill.className = 'audit-status-pill warn';
                }
            }
        } catch (_) {
            if (dsPill) dsPill.textContent = 'Estado: no disponible';
        }
    }

    async function send(prefill) {
        const input = inputEl();
        const q = (typeof prefill === 'string' ? prefill : (input && input.value.trim())) || '';
        if (!q) return;
        if (input && typeof prefill !== 'string') input.value = '';

        appendUserMessage(q);

        const sendBtn = document.getElementById('auditChatSend');
        if (sendBtn) sendBtn.disabled = true;

        const loadId = 'auditLoading_' + Date.now();
        const msgs = messagesEl();
        if (msgs) {
            const loader = document.createElement('div');
            loader.className = 'audit-msg agent';
            loader.id = loadId;
            loader.innerHTML = '<span class="spinner"></span> Analizando alertas del dataset…';
            msgs.appendChild(loader);
            msgs.scrollTop = msgs.scrollHeight;
        }

        try {
            const headers = { 'Content-Type': 'application/json' };
            if (typeof withFraudiaSessionHeaders === 'function') {
                const wrapped = withFraudiaSessionHeaders({ method: 'POST', headers, body: JSON.stringify({ question: q }) });
                Object.assign(headers, wrapped.headers || {});
            }
            const resp = await fetch('/api/agent-query', {
                method: 'POST',
                headers,
                body: JSON.stringify({ question: q, history: chatHistory.slice(-10) }),
            });
            const data = await resp.json();
            const loader = document.getElementById(loadId);
            if (loader) loader.remove();

            if (!resp.ok) {
                appendError(data.error || `Error ${resp.status}`);
                return;
            }

            const answer = data.respuesta || data.error || 'Sin respuesta';
            chatHistory.push({ role: 'user', content: q });
            chatHistory.push({ role: 'model', content: answer });
            if (chatHistory.length > 20) chatHistory.splice(0, chatHistory.length - 20);

            const extra = typeof renderAgentDataBlock === 'function'
                ? renderAgentDataBlock(data.datos, q)
                : '';
            const html = typeof renderAgentText === 'function'
                ? renderAgentText(answer)
                : escapeHtml(answer).replace(/\n/g, '<br>');
            appendAgentMessage(html + extra, null);
            refreshStatus();
        } catch (e) {
            const loader = document.getElementById(loadId);
            if (loader) loader.remove();
            appendError('Error de conexión con el agente. Verifique que el análisis esté completo.');
        } finally {
            if (sendBtn) sendBtn.disabled = false;
            if (input) input.focus();
        }
    }

    async function init() {
        renderShell();
        if (typeof bootstrapSessionFromServer === 'function') {
            await bootstrapSessionFromServer();
        }
        await refreshStatus();
        initialized = true;
    }

    function clearHistory() {
        chatHistory.length = 0;
    }

    return { init, send, refreshStatus, clearHistory, initialized: () => initialized };
})();

window.AuditAgent = AuditAgent;
