/**
 * FraudIA — AI Floating Copilot (ML / Dashboard)
 */
const MlCopilot = (function () {
    const PLACEHOLDERS = [
        'Analiza patrones sospechosos en el portfolio…',
        '¿Qué casos debo revisar primero?',
        'Explica por qué un siniestro es crítico…',
        'Detecta anomalías y clusters de fraude…',
        '¿Qué proveedores concentran más alertas?',
        'Genera un resumen ejecutivo antifraude…',
    ];
    const INVESTIGATIONS = [
        { id: 'crit', icon: '🔴', title: 'Casos Críticos', risk: 'Alto', prompt: '¿Cuáles son los 10 casos más riesgosos y por qué debo revisarlos primero?' },
        { id: 'prov', icon: '🟡', title: 'Proveedores Sospechosos', risk: 'Medio', prompt: '¿Qué proveedores tienen más alertas y mayor score promedio?' },
        { id: 'exec', icon: '🟢', title: 'Resumen Ejecutivo', risk: 'Info', prompt: 'Genera un resumen ejecutivo del panorama de fraude actual.' },
        { id: 'anom', icon: '🔵', title: 'Anomalías Detectadas', risk: 'IA', prompt: '¿Qué anomalías y patrones atípicos detectó el modelo?' },
        { id: 'nlp', icon: '💬', title: 'Narrativas Similares', risk: 'NLP', prompt: '¿Hay reclamos con narrativas clonadas o similitud textual alta?' },
        { id: 'geo', icon: '🗺', title: 'Riesgo Geográfico', risk: 'Mapa', prompt: '¿Qué sucursales concentran más casos de alto riesgo?' },
    ];
    const QUICK_ACTIONS = [
        { label: 'Casos Críticos', q: 'Lista los casos críticos con score y alertas' },
        { label: 'Detectar Fraude', q: '¿Qué señales de fraude son más frecuentes?' },
        { label: 'Analizar Narrativas', q: 'Analiza similitud narrativa y reclamos clonados' },
        { label: 'Heatmap Riesgo', q: 'Resume el riesgo por ramo y sucursal' },
        { label: 'Explicar Score', q: '¿Cómo se calcula el score híbrido antifraude?' },
        { label: 'Proveedores', q: 'Ranking de proveedores con mayor riesgo' },
        { label: 'Simular Escenario', q: '¿Qué pasa si aumentan reportes tardíos?' },
        { label: 'Generar Reporte', q: 'Informe ejecutivo de fraude para comité' },
    ];

    let placeholderIdx = 0;
    let placeholderTimer = null;
    let activeInvestigation = 'crit';
    let selectedCaseId = null;
    let dragState = null;

    const FAB_ICON_BOT = '<path d="M12 2a7 7 0 0 0-7 7v4a7 7 0 0 0 7 7c.9 0 1.76-.12 2.55-.35L20 24l-1.15-3.45C21.2 19.2 22 17.1 22 15V9a7 7 0 0 0-7-7zm-2.5 9.5a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zm5 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3z"/>';
    const FAB_ICON_CLOSE = '<path d="M18.3 5.71a1 1 0 0 0-1.41 0L12 10.59 7.11 5.7A1 1 0 0 0 5.7 7.11L10.59 12 5.7 16.89a1 1 0 1 0 1.41 1.41L12 13.41l4.89 4.89a1 1 0 0 0 1.41-1.41L13.41 12l4.89-4.89a1 1 0 0 0 0-1.41z"/>';

    function $(id) { return document.getElementById(id); }

    function escapeHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function messagesEl() { return $('mlCopilotMessages'); }

    function scrollMessages() {
        const el = messagesEl();
        if (el) el.scrollTop = el.scrollHeight;
    }

    function renderWelcome() {
        return `
            <div class="copilot-msg agent">
                <div class="copilot-msg-body">
                    <strong style="color:var(--cyan);">FraudIA Intelligence Engine</strong> conectado a TiDB, motor ML, NLP y reglas antifraude.
                    <div class="copilot-kpi-row" style="margin-top:0.75rem;">
                        <div class="copilot-kpi"><label>Modo</label><span>Copiloto</span></div>
                        <div class="copilot-kpi"><label>ML</label><span>RF + ISO</span></div>
                        <div class="copilot-kpi"><label>NLP</label><span>Activo</span></div>
                    </div>
                    <p style="margin:0.65rem 0 0;font-size:0.78rem;color:var(--text-muted);">Use la barra lateral o acciones rápidas para iniciar una investigación.</p>
                </div>
            </div>`;
    }

    function renderSidebar() {
        const side = $('copilotSidebar');
        if (!side) return;
        side.innerHTML = INVESTIGATIONS.map((inv) => `
            <div class="copilot-inv-card ${inv.id === activeInvestigation ? 'active' : ''}" data-inv="${inv.id}" data-prompt="${escapeHtml(inv.prompt)}">
                <div class="inv-title">${inv.icon} ${inv.title}</div>
                <div class="inv-meta">${inv.risk} · Investigación IA</div>
            </div>
        `).join('');
        side.querySelectorAll('.copilot-inv-card').forEach((card) => {
            card.addEventListener('click', () => {
                activeInvestigation = card.dataset.inv;
                renderSidebar();
                send(card.dataset.prompt);
            });
        });
    }

    function renderQuickActions() {
        const row = $('copilotQuickActions');
        if (!row) return;
        row.innerHTML = QUICK_ACTIONS.map((a) =>
            `<button type="button" class="copilot-qa-btn" data-q="${escapeHtml(a.q)}">${a.label}</button>`
        ).join('');
        row.querySelectorAll('.copilot-qa-btn').forEach((btn) => {
            btn.addEventListener('click', () => send(btn.dataset.q));
        });
    }

    function startPlaceholderRotation() {
        const input = $('mlCopilotInput');
        if (!input) return;
        stopPlaceholderRotation();
        placeholderTimer = setInterval(() => {
            if (document.activeElement === input) return;
            placeholderIdx = (placeholderIdx + 1) % PLACEHOLDERS.length;
            input.placeholder = PLACEHOLDERS[placeholderIdx];
        }, 4500);
    }

    function stopPlaceholderRotation() {
        if (placeholderTimer) clearInterval(placeholderTimer);
    }

    function appendUser(text) {
        const el = messagesEl();
        if (!el) return;
        el.insertAdjacentHTML('beforeend', `<div class="copilot-msg user">${escapeHtml(text)}</div>`);
        scrollMessages();
    }

    function appendLoading() {
        const el = messagesEl();
        if (!el) return 'copilotLoad';
        el.insertAdjacentHTML('beforeend', `<div class="copilot-msg agent" id="copilotLoad"><div class="copilot-typing"><span></span><span></span><span></span></div></div>`);
        scrollMessages();
        return 'copilotLoad';
    }

    function removeLoading() {
        const l = $('copilotLoad');
        if (l) l.remove();
    }

    function plainAgentText(text) {
        if (!text) return '';
        const plain = String(text)
            .replace(/```[\s\S]*?```/g, (m) => m.replace(/```/g, ''))
            .replace(/`([^`]+)`/g, '$1')
            .replace(/\*\*([^*]+)\*\*/g, '$1')
            .replace(/\n{3,}/g, '\n\n')
            .trim();
        const bullets = plain.split('\n').filter((l) => /^[•✓✔\-*]/.test(l.trim()));
        if (bullets.length >= 2) {
            return `<div class="copilot-xai"><strong>Explicación IA</strong><ul>${bullets.map((b) =>
                `<li>${escapeHtml(b.replace(/^[\s•✓✔\-*]+/, ''))}</li>`
            ).join('')}</ul></div>`;
        }
        return escapeHtml(plain).replace(/\n/g, '<br>');
    }

    function renderCaseCard(row) {
        const id = row.id_siniestro || '—';
        const score = Number(row.score_hibrido ?? row.score_reglas ?? 0).toFixed(0);
        const sem = row.semaforo_final || row.semaforo_reglas || '—';
        const prob = row.ml_fraud_probability != null ? (Number(row.ml_fraud_probability) * 100).toFixed(0) + '%' : '—';
        const monto = row.monto_reclamado != null ? '$' + Number(row.monto_reclamado).toLocaleString() : '—';
        const prov = row.beneficiario || row.id_proveedor || '—';
        const semColor = sem === 'Rojo' ? 'var(--red)' : sem === 'Amarillo' ? 'var(--yellow)' : 'var(--green)';
        return `
            <div class="copilot-case-card" data-case-id="${escapeHtml(id)}" style="cursor:pointer;">
                <div class="cc-id">${escapeHtml(id)}</div>
                <div class="copilot-kpi-row">
                    <div class="copilot-kpi"><label>Score</label><span style="color:${semColor}">${score}</span></div>
                    <div class="copilot-kpi"><label>Riesgo</label><span>${escapeHtml(sem)}</span></div>
                    <div class="copilot-kpi"><label>Prob. ML</label><span>${prob}</span></div>
                    <div class="copilot-kpi"><label>Monto</label><span>${monto}</span></div>
                </div>
                <div style="font-size:0.7rem;color:var(--text-muted);margin-top:0.35rem;">Proveedor: ${escapeHtml(String(prov).slice(0, 28))}</div>
            </div>`;
    }

    function renderDataBlock(datos, question) {
        if (!datos) return '';
        const rows = Array.isArray(datos) ? datos : [datos];
        if (!rows.length || typeof rows[0] !== 'object') return '';

        if (rows[0].id_siniestro && rows.length <= 6) {
            return rows.map((r) => renderCaseCard(r)).join('');
        }

        if (typeof window.renderAgentDataBlock === 'function') {
            const html = window.renderAgentDataBlock(datos, question);
            return html
                .replace(/chat-data-table/g, 'copilot-data-table')
                .replace(/chat-mini-chart/g, 'copilot-mini-chart');
        }

        const headers = Object.keys(rows[0]).slice(0, 6);
        const thead = headers.map((h) => `<th>${escapeHtml(h)}</th>`).join('');
        const tbody = rows.slice(0, 10).map((r) =>
            `<tr>${headers.map((h) => `<td>${escapeHtml(String(r[h] ?? '-').slice(0, 40))}</td>`).join('')}</tr>`
        ).join('');
        return `<div class="copilot-data-table-wrap"><table class="copilot-data-table"><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table></div>`;
    }

    function appendAgent(data, question) {
        removeLoading();
        const el = messagesEl();
        if (!el) return;
        const answer = data.respuesta || data.error || 'Sin respuesta';
        const motor = data.motor
            ? `<div style="font-size:0.68rem;color:var(--text-muted);margin-top:0.5rem;">Motor: ${escapeHtml(data.motor)} · auditable</div>`
            : '';
        const extra = renderDataBlock(data.datos, question);
        el.insertAdjacentHTML('beforeend', `
            <div class="copilot-msg agent">
                <div class="copilot-msg-body">
                    ${plainAgentText(answer)}
                    ${extra}
                    ${motor}
                </div>
            </div>`);
        el.querySelectorAll('.copilot-case-card[data-case-id]').forEach((card) => {
            card.addEventListener('click', () => openDossier(card.dataset.caseId));
        });
        const sinMatch = String(answer).match(/SIN-[\w-]+/i);
        if (sinMatch) openDossier(sinMatch[0], false);
        scrollMessages();
    }

    async function openDossier(caseId, expandPanel = true) {
        if (!caseId) return;
        selectedCaseId = caseId;
        const ctx = $('copilotContextBar');
        if (ctx) {
            ctx.classList.add('visible');
            ctx.innerHTML = `Analizando: <strong>${escapeHtml(caseId)}</strong> · modo investigación`;
        }
        const dossier = $('copilotDossier');
        if (!dossier) return;
        dossier.classList.add('open');
        dossier.innerHTML = '<div class="copilot-typing"><span></span><span></span><span></span></div>';
        if (expandPanel) {
            const panel = $('mlCopilotPanel');
            if (panel) panel.classList.add('expanded');
        }
        try {
            const data = await (await fetch('/api/case/' + encodeURIComponent(caseId))).json();
            if (data.error) {
                dossier.innerHTML = `<p style="color:var(--red);">${escapeHtml(data.error)}</p>`;
                return;
            }
            const score = Number(data.score_hibrido ?? data.score_reglas ?? 0).toFixed(1);
            const alertList = Array.isArray(data.alertas) ? data.alertas.slice(0, 6) : [];
            const factores = Array.isArray(data.factores_principales) ? data.factores_principales : [];
            const factorLines = factores.map((f) =>
                typeof f === 'string' ? f : `${f.factor || ''}: ${f.contribucion || ''}`
            ).filter(Boolean);
            dossier.innerHTML = `
                <h4>📁 Dossier · ${escapeHtml(caseId)}</h4>
                <div class="copilot-kpi-row">
                    <div class="copilot-kpi"><label>Score</label><span>${score}</span></div>
                    <div class="copilot-kpi"><label>Riesgo</label><span>${escapeHtml(data.semaforo_final || data.semaforo_reglas || '—')}</span></div>
                    <div class="copilot-kpi"><label>Acción</label><span style="font-size:0.7rem;">${escapeHtml((data.accion_sugerida || 'Revisar').slice(0, 24))}</span></div>
                </div>
                <div class="copilot-xai" style="margin-top:0.65rem;">
                    <strong>Factores de riesgo</strong>
                    <ul>${(alertList.length ? alertList : factorLines.length ? factorLines : ['Score compuesto reglas + ML + anomalías']).map((a) => `<li>${escapeHtml(String(a))}</li>`).join('')}</ul>
                </div>
                <p style="font-size:0.72rem;color:var(--text-muted);margin-top:0.5rem;">${escapeHtml((data.resumen || '').slice(0, 280))}</p>
                <button type="button" class="btn btn-secondary" style="margin-top:0.5rem;font-size:0.75rem;" onclick="typeof viewCase==='function'&&viewCase('${escapeHtml(caseId)}')">Abrir ficha completa</button>
            `;
        } catch (e) {
            dossier.innerHTML = '<p style="color:var(--red);">Error al cargar dossier.</p>';
        }
    }

    async function refreshHeaderMetrics() {
        const metricsEl = $('copilotHeaderMetrics');
        const chipsEl = $('copilotStatusChips');
        try {
            const [status, dash, ml] = await Promise.all([
                fetch('/api/agent-status').then((r) => r.json()).catch(() => ({})),
                fetch('/api/dashboard-data').then((r) => r.json()).catch(() => ({})),
                fetch('/api/model-metrics').then((r) => r.json()).catch(() => ({})),
            ]);
            const rojos = dash.semaforo?.Rojo ?? dash.executive_kpis?.riesgo_alto ?? 0;
            const alerts = (dash.signals_summary || []).reduce((a, s) => a + (s.count || 0), 0) || rojos;
            const inferMs = ml.inference_ms ?? 48;
            const modelName = ml.active_model || 'Random Forest';

            if (metricsEl) {
                metricsEl.innerHTML = `
                    <span class="copilot-metric-pill">🔴<strong>${Number(rojos).toLocaleString()}</strong> críticos</span>
                    <span class="copilot-metric-pill">🟡<strong>${Number(alerts).toLocaleString()}</strong> alertas</span>
                    <span class="copilot-metric-pill">🟢<strong>${escapeHtml(modelName)}</strong></span>
                    <span class="copilot-metric-pill">⚡<strong>${inferMs}ms</strong></span>
                `;
            }
            if (chipsEl) {
                const online = status.pipeline_ready ? 'on' : 'warn';
                chipsEl.innerHTML = `
                    <span class="copilot-chip ${online}">● Online</span>
                    <span class="copilot-chip on">TiDB</span>
                    <span class="copilot-chip ${ml.trained !== false ? 'on' : ''}">ML</span>
                    <span class="copilot-chip on">NLP</span>
                `;
            }
        } catch (e) { /* ignore */ }
    }

    async function send(question) {
        const q = (question || '').trim();
        if (!q) return;
        const input = $('mlCopilotInput');
        if (input) input.value = '';
        appendUser(q);
        appendLoading();
        const t0 = performance.now();
        try {
            const resp = await fetch('/api/agent-query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: q }),
            });
            const data = await resp.json();
            const ms = Math.round(performance.now() - t0);
            const inferEl = $('copilotInferLive');
            if (inferEl) inferEl.textContent = ms + 'ms';
            appendAgent(data, q);
        } catch (e) {
            removeLoading();
            const el = messagesEl();
            if (el) {
                el.insertAdjacentHTML('beforeend', `<div class="copilot-msg agent"><div class="copilot-msg-body" style="border-color:var(--red);">Error de conexión con el motor IA.</div></div>`);
            }
        }
        scrollMessages();
    }

    function toggle(forceOpen) {
        const panel = $('mlCopilotPanel');
        const fab = $('mlChatFab');
        const icon = $('mlChatFabIcon');
        if (!panel || !fab) return;
        const open = forceOpen === true ? true : forceOpen === false ? false : !panel.classList.contains('open');
        panel.classList.toggle('open', open);
        fab.classList.toggle('open', open);
        if (icon) icon.innerHTML = open ? FAB_ICON_CLOSE : FAB_ICON_BOT;
        if (open) {
            refreshHeaderMetrics();
            const inp = $('mlCopilotInput');
            if (inp) setTimeout(() => inp.focus(), 150);
        }
    }

    function setVisible(show) {
        const w = $('mlChatWidget');
        if (!w) return;
        w.classList.toggle('visible', !!show);
        w.setAttribute('aria-hidden', show ? 'false' : 'true');
        if (show) refreshHeaderMetrics();
        else toggle(false);
    }

    function bindDrag() {
        const panel = $('mlCopilotPanel');
        const header = $('copilotDragHandle');
        const widget = $('mlChatWidget');
        if (!panel || !header || !widget) return;

        header.addEventListener('mousedown', (e) => {
            if (e.target.closest('.copilot-icon-btn')) return;
            dragState = {
                startX: e.clientX,
                startY: e.clientY,
                right: parseInt(widget.style.right, 10) || 20,
                bottom: parseInt(widget.style.bottom, 10) || 20,
            };
            e.preventDefault();
        });
        window.addEventListener('mousemove', (e) => {
            if (!dragState) return;
            const dx = dragState.startX - e.clientX;
            const dy = dragState.startY - e.clientY;
            widget.style.right = Math.max(8, dragState.right + dx) + 'px';
            widget.style.bottom = Math.max(8, dragState.bottom + dy) + 'px';
        });
        window.addEventListener('mouseup', () => { dragState = null; });
    }

    function bindResize() {
        const panel = $('mlCopilotPanel');
        const handle = $('copilotResizeHandle');
        if (!panel || !handle) return;
        let resizing = false;
        let sx, sy, sw, sh;
        handle.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            e.preventDefault();
            resizing = true;
            sx = e.clientX;
            sy = e.clientY;
            sw = panel.offsetWidth;
            sh = panel.offsetHeight;
            document.body.style.userSelect = 'none';
        });
        window.addEventListener('mousemove', (e) => {
            if (!resizing) return;
            panel.style.width = Math.max(340, Math.min(window.innerWidth - 16, sw - (e.clientX - sx))) + 'px';
            panel.style.height = Math.max(420, Math.min(window.innerHeight - 16, sh - (e.clientY - sy))) + 'px';
        });
        window.addEventListener('mouseup', () => {
            resizing = false;
            document.body.style.userSelect = '';
        });
    }

    function bindControls() {
        $('copilotBtnMin')?.addEventListener('click', () => toggle(false));
        $('copilotBtnExpand')?.addEventListener('click', () => {
            $('mlCopilotPanel')?.classList.toggle('expanded');
        });
        $('copilotBtnClose')?.addEventListener('click', () => toggle(false));
        $('mlChatFab')?.addEventListener('click', () => toggle());
        $('mlCopilotSend')?.addEventListener('click', () => sendFromInput());
        const input = $('mlCopilotInput');
        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendFromInput();
                }
            });
            input.addEventListener('focus', stopPlaceholderRotation);
            input.addEventListener('blur', startPlaceholderRotation);
        }
        $('copilotDossierClose')?.addEventListener('click', () => {
            $('copilotDossier')?.classList.remove('open');
            $('copilotContextBar')?.classList.remove('visible');
        });
    }

    function sendFromInput() {
        const input = $('mlCopilotInput');
        if (!input) return;
        send(input.value);
    }

    function init() {
        if (!$('mlCopilotMessages')) return;
        renderSidebar();
        renderQuickActions();
        bindDrag();
        bindResize();
        bindControls();
        startPlaceholderRotation();
        const msg = messagesEl();
        if (msg && !msg.dataset.inited) {
            msg.innerHTML = renderWelcome();
            msg.dataset.inited = '1';
        }
    }

    return {
        init,
        send,
        toggle,
        setVisible,
        openDossier,
        refreshHeaderMetrics,
    };
})();

window.MlCopilot = MlCopilot;

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => MlCopilot.init());
} else {
    MlCopilot.init();
}
