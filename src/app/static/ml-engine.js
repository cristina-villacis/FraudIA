/**
 * FraudIA — AI / ML Engine (premium lab UI)
 */
const mlEngineState = {
    initialized: false,
    metrics: null,
    filters: { semaforo: 'all', ramo: 'all', search: '' },
    options: { ramos: [] },
    pipelineStep: 0,
};

const ML_PIPELINE = [
    { id: 'data', icon: '📊', label: 'Dataset' },
    { id: 'feat', icon: '⚙', label: 'Features' },
    { id: 'rules', icon: '⚖', label: 'Rules' },
    { id: 'nlp', icon: '💬', label: 'NLP' },
    { id: 'ml', icon: '🧠', label: 'ML' },
    { id: 'score', icon: '◈', label: 'Risk Score' },
    { id: 'xai', icon: '◇', label: 'Explain' },
];

function buildMlShell() {
    return `
        <header class="ml-ia-header">
            <div class="ml-ia-title">
                <h2>AI / ML Engine</h2>
                <p>Motor de inteligencia antifraude · inferencia y explainability en tiempo real</p>
                <div class="ml-neural-pulse" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span></div>
            </div>
            <div class="ml-metrics-strip">
                <div class="ml-metric-pill"><label>Estado</label><strong id="mlHdrStatus">—</strong></div>
                <div class="ml-metric-pill"><label>Modelo</label><strong id="mlHdrModel">—</strong></div>
                <div class="ml-metric-pill"><label>Accuracy</label><strong id="mlHdrAccuracy">—</strong></div>
                <div class="ml-metric-pill"><label>Precision</label><strong id="mlHdrPrecision">—</strong></div>
                <div class="ml-metric-pill"><label>Recall</label><strong id="mlHdrRecall">—</strong></div>
                <div class="ml-metric-pill"><label>F1</label><strong id="mlHdrF1">—</strong></div>
                <div class="ml-metric-pill"><label>Inferencia</label><strong id="mlHdrInfer">—</strong></div>
            </div>
        </header>

        <div class="ml-models-grid" id="mlModelsGrid"></div>

        <div class="ml-pipeline">
            <div class="ml-panel-title" style="margin-bottom:0.75rem;">Pipeline de inteligencia</div>
            <div class="ml-pipeline-track" id="mlPipelineTrack"></div>
        </div>

        <div class="ml-grid-2">
            <div class="ml-panel">
                <div class="ml-panel-title">Feature importance · SHAP</div>
                <div id="mlShapList" class="ml-shap-list"></div>
                <div id="chartImportance" class="chart-area" style="min-height:280px;margin-top:1rem;"></div>
            </div>
            <div class="ml-panel">
                <div class="ml-panel-title">Matriz de confusión</div>
                <div id="chartConfusion" class="chart-area" style="min-height:300px;"></div>
            </div>
        </div>

        <div class="ml-grid-3">
            <div class="ml-panel">
                <div class="ml-panel-title">Anomalías · clustering</div>
                <div id="chartAnomalyScatter" class="chart-area" style="min-height:260px;"></div>
                <p style="font-size:0.7rem;color:var(--text-muted);margin:0.5rem 0 0;">Eje X: monto · Eje Y: score · color: nivel de riesgo</p>
            </div>
            <div class="ml-panel">
                <div class="ml-panel-title">NLP · red semántica</div>
                <div class="ml-nlp-net" id="mlNlpNet"></div>
                <div id="nlpPanel" style="margin-top:0.65rem;font-size:0.78rem;"></div>
            </div>
            <div class="ml-panel">
                <div class="ml-panel-title">Explainable AI</div>
                <div id="mlXaiBox" class="ml-xai-box">Seleccione un caso o ejecute la simulación para ver la explicación del score.</div>
            </div>
        </div>

        <div class="ml-grid-2">
            <div class="ml-panel">
                <div class="ml-panel-title">Simulador predictivo</div>
                <div class="ml-sim-grid">
                    <div class="ml-sim-field"><label>Monto reclamado ($)</label><input type="number" id="simMonto" value="45000" min="0" step="1000"></div>
                    <div class="ml-sim-field"><label>Días hasta reporte</label><input type="number" id="simDias" value="5" min="0" max="90"></div>
                    <div class="ml-sim-field"><label>Proveedor recurrente</label>
                        <select id="simProv"><option value="0">No</option><option value="1">Sí</option></select>
                    </div>
                    <div class="ml-sim-field"><label>Similitud narrativa (%)</label><input type="range" id="simNlp" min="0" max="100" value="20"><span id="simNlpVal" style="font-size:0.72rem;color:var(--cyan);">20%</span></div>
                </div>
                <button type="button" class="btn btn-primary" style="margin-top:0.75rem;width:100%;" id="btnSimRecalc">Recalcular score</button>
                <div class="ml-sim-result">
                    <div class="ml-sim-score" id="simScoreOut">—</div>
                    <div class="ml-sim-prob" id="simProbOut">Prob. fraude — · Severidad —</div>
                </div>
            </div>
            <div class="ml-panel">
                <div class="ml-panel-title">Monitoreo del modelo</div>
                <div id="mlMonitorPanel"></div>
                <div id="chartModelDrift" class="chart-area" style="min-height:200px;margin-top:0.75rem;"></div>
            </div>
        </div>

        <details class="ml-panel" style="margin-bottom:1.25rem;" open>
            <summary style="cursor:pointer;color:var(--cyan);font-weight:600;font-size:0.82rem;">Filtros y casos priorizados</summary>
            <div style="margin-top:0.85rem;">
                <div class="dashboard-toolbar-grid">
                    <div class="dashboard-filter"><label>Semáforo</label>
                        <select id="mlFilterSemaforo"><option value="all">Todos</option><option value="Rojo">Rojo</option><option value="Amarillo">Amarillo</option><option value="Verde">Verde</option></select>
                    </div>
                    <div class="dashboard-filter"><label>Ramo</label><select id="mlFilterRamo"><option value="all">Todos</option></select></div>
                    <div class="dashboard-filter"><label>ID</label><input id="mlFilterSearch" type="text" placeholder="SIN-..."></div>
                    <div class="dashboard-filter-actions" style="align-items:flex-end;">
                        <button class="btn btn-secondary" id="mlFilterApplyBtn">Aplicar</button>
                        <button class="btn btn-ghost" id="mlFilterClearBtn">Limpiar</button>
                    </div>
                </div>
                <div class="ml-grid-3" style="margin-top:0.75rem;">
                    <div class="dash-kpi-card" style="padding:0.85rem;"><div class="dash-kpi-label">Casos</div><div class="dash-kpi-value" id="mlFilterCount">0</div></div>
                    <div class="dash-kpi-card" style="padding:0.85rem;"><div class="dash-kpi-label">Score prom.</div><div class="dash-kpi-value" id="mlFilterScoreProm">0</div></div>
                    <div class="dash-kpi-card" style="padding:0.85rem;"><div class="dash-kpi-label">Monto</div><div class="dash-kpi-value" id="mlFilterMonto">$0</div></div>
                </div>
                <div class="ml-grid-2" style="margin-top:1rem;">
                    <div id="chartModelSemaforo" class="chart-area" style="min-height:240px;"></div>
                    <div class="dash-table-wrap" style="max-height:240px;">
                        <table class="dash-table">
                            <thead><tr><th>ID</th><th>Ramo</th><th>Score</th><th>Riesgo</th><th></th></tr></thead>
                            <tbody id="mlCasesTableBody"></tbody>
                        </table>
                    </div>
                </div>
            </div>
        </details>
    `;
}

function renderModelCards(metrics) {
    const grid = document.getElementById('mlModelsGrid');
    if (!grid) return;
    const auc = Number(metrics.auc_roc || 0).toFixed(3);
    const anom = metrics.anomalies_detected ?? '—';
    const nlpPairs = metrics.nlp_pairs ?? 0;
    const trained = metrics.trained !== false && !metrics.error;
    const cards = [
        { name: 'XGBoost', status: 'off', note: 'Reserva · no activo en pipeline', meta: 'v0.0 · standby' },
        { name: 'Random Forest', status: trained ? 'on' : 'off', note: `AUC ${auc} · supervisado`, meta: metrics.model_version || 'fraudia-ml-1.0' },
        { name: 'Isolation Forest', status: trained ? 'on' : 'off', note: `${anom} anomalías`, meta: 'No supervisado' },
        { name: 'NLP Engine', status: nlpPairs > 0 ? 'on' : 'off', note: `${nlpPairs} pares similares`, meta: 'Embeddings + similitud' },
    ];
    grid.innerHTML = cards.map((c) => `
        <div class="ml-model-card ${c.status === 'on' ? 'active' : 'standby'}">
            <div class="ml-model-status ${c.status}">${c.status === 'on' ? '● Activo' : '○ Standby'}</div>
            <h4>${c.name}</h4>
            <div class="ml-model-meta">${c.note}<br>${c.meta}</div>
        </div>
    `).join('');
}

function mlFetch(url, options = {}) {
    if (typeof withFraudiaSessionHeaders === 'function') {
        return fetch(url, withFraudiaSessionHeaders(options));
    }
    return fetch(url, options);
}

function fmtNum(v, digits = 3) {
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(digits) : '—';
}

function ensureMlShell(container) {
    if (document.getElementById('mlEngineShell')) return;
    mlEngineState.initialized = false;
    container.innerHTML = `<div id="mlEngineShell">${buildMlShell()}</div>`;
    initMlPipelineTrack();
    bindMlEngineEvents();
    const ramoSel = document.getElementById('mlFilterRamo');
    if (ramoSel) {
        ramoSel.innerHTML = '<option value="all">Todos</option>' +
            (mlEngineState.options.ramos || []).map((r) => `<option value="${r}">${r}</option>`).join('');
    }
    mlEngineState.initialized = true;
    computeSimulatedScore();
    loadNlpPanelMl();
}

function safeRender(fn, label) {
    try {
        fn();
    } catch (err) {
        console.warn('ML render:', label, err);
    }
}

function renderMlHeader(metrics) {
    const trained = metrics.trained !== false && !metrics.error;
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('mlHdrStatus', trained ? 'Operativo' : 'Inactivo');
    set('mlHdrModel', metrics.active_model || 'Random Forest');
    const acc = metrics.cv_auc_mean != null ? metrics.cv_auc_mean : metrics.auc_roc;
    set('mlHdrAccuracy', acc != null ? fmtNum(acc) : '—');
    set('mlHdrPrecision', fmtNum(metrics.precision_fraude ?? metrics.precision ?? 0));
    set('mlHdrRecall', fmtNum(metrics.recall_fraude ?? metrics.recall ?? 0));
    set('mlHdrF1', fmtNum(metrics.f1_fraude ?? metrics.f1_score ?? 0));
    set('mlHdrInfer', (metrics.inference_ms ?? 48) + ' ms');
}

function initMlPipelineTrack() {
    const track = document.getElementById('mlPipelineTrack');
    if (!track) return;
    track.innerHTML = ML_PIPELINE.map((s, i) => {
        const arrow = i < ML_PIPELINE.length - 1 ? '<span class="ml-pipe-arrow">→</span>' : '';
        return `<div class="ml-pipe-step" data-pipe="${s.id}">
            <div class="ml-pipe-icon">${s.icon}</div>
            <span class="ml-pipe-label">${s.label}</span>
        </div>${arrow}`;
    }).join('');
    runMlPipelineAnimation();
}

function runMlPipelineAnimation() {
    const steps = document.querySelectorAll('.ml-pipe-step');
    let i = 0;
    function tick() {
        steps.forEach((s, idx) => {
            s.classList.remove('active', 'done');
            if (idx < i) s.classList.add('done');
            if (idx === i) s.classList.add('active');
        });
        i++;
        if (i <= steps.length) setTimeout(tick, 400);
        else steps.forEach((s) => { s.classList.remove('active'); s.classList.add('done'); });
    }
    tick();
}

function renderShapList(features) {
    const el = document.getElementById('mlShapList');
    if (!el || !features || !features.length) {
        if (el) el.innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;">Sin features.</div>';
        return;
    }
    const max = Math.max(...features.map((f) => Number(f.importance || 0)), 0.001);
    el.innerHTML = features.slice(0, 8).map((f) => {
        const pct = (Number(f.importance || 0) / max) * 100;
        const label = String(f.feature || '').replace(/_/g, ' ').slice(0, 18);
        return `<div class="ml-shap-row">
            <span title="${f.feature}">${label}</span>
            <div class="track"><div class="fill" style="width:${pct}%;"></div></div>
            <span>${Number(f.importance || 0).toFixed(3)}</span>
        </div>`;
    }).join('');
}

function renderImportanceChart(data) {
    if (!data.top_features || !data.top_features.length || typeof Plotly === 'undefined') return;
    const MC = typeof getColors === 'function' ? getColors() : {};
    const MPL = typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {};
    const feats = data.top_features.slice(0, 10).reverse();
    const barBase = document.documentElement.getAttribute('data-theme') === 'light' ? [0, 136, 204] : [0, 209, 255];
    Plotly.react('chartImportance', [{
        y: feats.map((f) => f.feature),
        x: feats.map((f) => f.importance),
        type: 'bar',
        orientation: 'h',
        marker: { color: feats.map((_, i) => `rgba(${barBase.join(',')},${0.35 + i * 0.06})`) },
        text: feats.map((f) => Number(f.importance || 0).toFixed(3)),
        textposition: 'outside',
    }], { ...MPL, margin: { t: 8, b: 30, l: 160, r: 20 }, height: 280 }, typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : { responsive: true });
}

function renderConfusionChart(data) {
    if (!data.confusion_matrix || typeof Plotly === 'undefined') return;
    const MC = typeof getColors === 'function' ? getColors() : {};
    const MPL = typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {};
    const cm = data.confusion_matrix;
    const cmScale = document.documentElement.getAttribute('data-theme') === 'light'
        ? [[0, '#F7FAFC'], [0.5, 'rgba(0,136,204,0.25)'], [1, '#0088CC']]
        : [[0, MC.bgCard || '#0b1220'], [0.5, 'rgba(0,209,255,0.3)'], [1, MC.cyan || '#00d1ff']];
    Plotly.react('chartConfusion', [{
        z: cm,
        x: ['No Fraude', 'Fraude'],
        y: ['No Fraude', 'Fraude'],
        type: 'heatmap',
        colorscale: cmScale,
        text: cm.map((r) => r.map(String)),
        texttemplate: '%{text}',
        showscale: false,
    }], { ...MPL, margin: { t: 10, b: 50, l: 80, r: 10 }, height: 300 }, typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : {});
}

function renderAnomalyScatter(metrics) {
    const el = document.getElementById('chartAnomalyScatter');
    if (!el || typeof Plotly === 'undefined') return;
    const points = metrics.anomaly_scatter || [];
    if (!points.length) return;
    const MC = typeof getColors === 'function' ? getColors() : { red: '#FF4D4F', yellow: '#FFC857', green: '#00C48C', text: '#fff' };
    const colors = points.map((p) => {
        const s = p.semaforo_final || 'Verde';
        return s === 'Rojo' ? MC.red : s === 'Amarillo' ? MC.yellow : MC.green;
    });
    Plotly.react('chartAnomalyScatter', [{
        x: points.map((p) => p.monto_reclamado || 0),
        y: points.map((p) => p.score_hibrido || 0),
        mode: 'markers',
        type: 'scatter',
        marker: { color: colors, size: 8, opacity: 0.75, line: { width: 0 } },
        text: points.map((p) => p.id_siniestro),
        hovertemplate: '<b>%{text}</b><br>Monto: %{x:,.0f}<br>Score: %{y:.0f}<extra></extra>',
    }], {
        ...(typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {}),
        xaxis: { title: 'Monto reclamado', type: 'log' },
        yaxis: { title: 'Score híbrido' },
        height: 260,
        margin: { t: 10, b: 40, l: 50, r: 10 },
    }, typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : {});
}

function renderNlpNetwork(nlp) {
    const wrap = document.getElementById('mlNlpNet');
    if (!wrap) return;
    const pairs = (nlp && nlp.high_similarity_pairs) ? nlp.high_similarity_pairs.slice(0, 5) : [];
    const nodes = [{ x: 200, y: 100, r: 28, label: 'NLP Core' }];
    pairs.forEach((p, i) => {
        const angle = (i / Math.max(pairs.length, 1)) * Math.PI * 2;
        nodes.push({
            x: 200 + Math.cos(angle) * 90,
            y: 100 + Math.sin(angle) * 70,
            r: 18,
            label: `${(p.similarity * 100).toFixed(0)}%`,
        });
    });
    let edges = '';
    nodes.slice(1).forEach((n) => {
        edges += `<line class="ml-nlp-link" x1="200" y1="100" x2="${n.x}" y2="${n.y}"/>`;
    });
    const circles = nodes.map((n) =>
        `<circle class="ml-nlp-node" cx="${n.x}" cy="${n.y}" r="${n.r}"/><text x="${n.x}" y="${n.y + 3}" text-anchor="middle" fill="var(--text-secondary)" font-size="8">${n.label}</text>`
    ).join('');
    wrap.innerHTML = `<svg viewBox="0 0 400 200">${edges}${circles}</svg>`;
}

async function loadNlpPanelMl() {
    const el = document.getElementById('nlpPanel');
    if (!el) return;
    try {
        const nlp = await (await fetch('/api/nlp-summary')).json();
        renderNlpNetwork(nlp);
        if (!nlp.error && nlp.high_similarity_pairs) {
            el.innerHTML = nlp.high_similarity_pairs.slice(0, 4).map((p) =>
                `<div style="display:flex;justify-content:space-between;padding:0.4rem 0;border-bottom:1px solid var(--border-subtle);">
                    <span class="mono" style="font-size:0.72rem;">${p.id_1} ↔ ${p.id_2}</span>
                    <span class="badge badge-red" style="font-size:0.65rem;">${(p.similarity * 100).toFixed(0)}%</span>
                </div>`
            ).join('');
        } else el.innerHTML = '<span style="color:var(--text-muted);">Sin pares NLP.</span>';
    } catch (e) {
        el.innerHTML = '<span style="color:var(--text-muted);">NLP no disponible.</span>';
    }
}

function renderXaiFromCase(c) {
    const box = document.getElementById('mlXaiBox');
    if (!box || !c) return;
    const score = Number(c.score_hibrido ?? c.score_reglas ?? 0).toFixed(0);
    const alertas = String(c.alertas_reglas || '').split('|').map((x) => x.trim()).filter(Boolean).slice(0, 5);
    const bullets = alertas.length ? alertas : ['Patrón de riesgo compuesto', 'Señales de reglas de negocio'];
    box.innerHTML = `
        <p>Este caso obtuvo score <strong>${score}/100</strong> debido a:</p>
        <ul style="margin:0.5rem 0 0;padding-left:1.1rem;">${bullets.map((b) => `<li>${b}</li>`).join('')}</ul>
        <p style="margin-top:0.5rem;font-size:0.75rem;">ID: <span class="case-id">${c.id_siniestro || '—'}</span></p>
    `;
}

function computeSimulatedScore() {
    const monto = Number(document.getElementById('simMonto')?.value || 0);
    const dias = Number(document.getElementById('simDias')?.value || 0);
    const prov = Number(document.getElementById('simProv')?.value || 0);
    const nlp = Number(document.getElementById('simNlp')?.value || 0) / 100;
    let score = 25;
    score += Math.min(35, (monto / 100000) * 25);
    score += Math.min(20, dias * 1.2);
    score += prov ? 18 : 0;
    score += nlp * 25;
    score = Math.min(100, Math.round(score));
    const prob = Math.min(0.99, score / 100 * 0.92 + 0.05);
    const sem = score >= 76 ? 'Rojo' : score >= 41 ? 'Amarillo' : 'Verde';
    const sev = score >= 76 ? 'Crítica' : score >= 41 ? 'Media' : 'Baja';
    document.getElementById('simScoreOut').textContent = score + '/100';
    document.getElementById('simProbOut').textContent = `Prob. fraude ${(prob * 100).toFixed(1)}% · Severidad ${sev} (${sem})`;
    const box = document.getElementById('mlXaiBox');
    if (box) {
        box.innerHTML = `
            <p>Simulación: score <strong>${score}/100</strong> (${sem}) por:</p>
            <ul style="margin:0.5rem 0 0;padding-left:1.1rem;">
                ${monto > 50000 ? '<li>Monto reclamado elevado</li>' : ''}
                ${dias > 3 ? '<li>Reporte tardío (' + dias + ' días)</li>' : ''}
                ${prov ? '<li>Proveedor recurrente en historial</li>' : ''}
                ${nlp >= 0.7 ? '<li>Narrativa altamente similar (' + Math.round(nlp * 100) + '%)</li>' : nlp >= 0.4 ? '<li>Similitud textual moderada</li>' : ''}
                <li>Combinación reglas (40%) + ML (35%) + anomalías (25%)</li>
            </ul>
        `;
    }
}

function renderMonitorPanel(metrics) {
    const el = document.getElementById('mlMonitorPanel');
    if (!el) return;
    const auc = Number(metrics.auc_roc || 0);
    const cv = Number(metrics.cv_auc_mean || auc);
    const drift = Math.abs(auc - cv) < 0.05 ? 'Estable' : 'Revisar';
    const driftCls = drift === 'Estable' ? 'var(--green)' : 'var(--yellow)';
    el.innerHTML = `
        <div class="ml-grid-3" style="margin:0;gap:0.5rem;">
            <div class="ml-ml-stat dash-ml-stat" style="padding:0.5rem;"><label style="font-size:0.6rem;color:var(--text-muted);">Drift</label><div style="font-weight:700;color:${driftCls};">${drift}</div></div>
            <div style="padding:0.5rem;"><label style="font-size:0.6rem;color:var(--text-muted);">Anomalías</label><div style="font-weight:700;color:var(--cyan);">${metrics.anomalies_detected ?? '—'}</div></div>
            <div style="padding:0.5rem;"><label style="font-size:0.6rem;color:var(--text-muted);">CV AUC</label><div style="font-weight:700;">${cv.toFixed(3)}</div></div>
        </div>
    `;
    if (metrics.score_histogram && typeof Plotly !== 'undefined') {
        const h = metrics.score_histogram;
        Plotly.react('chartModelDrift', [{
            x: h.bins,
            y: h.counts,
            type: 'bar',
            marker: { color: ['#00C48C', '#FFC857', '#FF4D4F'] },
        }], {
            ...(typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {}),
            title: { text: 'Distribución de scores', font: { size: 11 } },
            height: 200,
            margin: { t: 36, b: 36, l: 40, r: 10 },
        }, typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : {});
    }
}

function getModelQueryString() {
    const p = new URLSearchParams();
    const f = mlEngineState.filters;
    if (f.semaforo && f.semaforo !== 'all') p.set('semaforo', f.semaforo);
    if (f.ramo && f.ramo !== 'all') p.set('ramo', f.ramo);
    if (f.search) p.set('search', f.search.trim());
    return p.toString();
}

async function refreshMlDynamicData() {
    const qs = getModelQueryString();
    const resp = await mlFetch('/api/dashboard-data' + (qs ? '?' + qs : ''));
    const data = await resp.json();
    if (!resp.ok || data.error) return;

    const scoreEl = document.getElementById('mlFilterScoreProm');
    const amountEl = document.getElementById('mlFilterMonto');
    const countEl = document.getElementById('mlFilterCount');
    if (scoreEl) scoreEl.textContent = Number(data.score_promedio || 0).toFixed(1);
    if (amountEl) amountEl.textContent = '$' + Number(data.monto_total || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
    if (countEl) countEl.textContent = Number(data.total || 0).toLocaleString();

    const topCases = Array.isArray(data.top_cases) ? data.top_cases : [];
    const tableEl = document.getElementById('mlCasesTableBody');
    if (tableEl) {
        tableEl.innerHTML = topCases.length
            ? topCases.slice(0, 12).map((c) => {
                const sc = Number(c.score_hibrido || 0).toFixed(1);
                const sem = c.semaforo_final || '';
                const bcls = sem === 'Rojo' ? 'badge-red' : sem === 'Amarillo' ? 'badge-yellow' : 'badge-green';
                return `<tr class="ml-case-pick" data-case-id="${c.id_siniestro}" style="cursor:pointer;">
                    <td style="color:var(--cyan);font-weight:600;">${c.id_siniestro}</td>
                    <td>${c.ramo || ''}</td>
                    <td>${sc}</td>
                    <td><span class="badge ${bcls}">${sem}</span></td>
                    <td><button type="button" class="dash-btn-analyze" data-pick="${c.id_siniestro}">XAI</button></td>
                </tr>`;
            }).join('')
            : '<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">Sin casos</td></tr>';
        tableEl.querySelectorAll('.ml-case-pick').forEach((row) => {
            row.addEventListener('click', () => {
                const c = topCases.find((x) => x.id_siniestro === row.dataset.caseId);
                renderXaiFromCase(c);
            });
        });
        tableEl.querySelectorAll('[data-pick]').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const c = topCases.find((x) => x.id_siniestro === btn.dataset.pick);
                renderXaiFromCase(c);
            });
        });
        if (topCases[0]) renderXaiFromCase(topCases[0]);
    }

    const sem = data.semaforo || {};
    if (document.getElementById('chartModelSemaforo') && typeof Plotly !== 'undefined') {
        Plotly.react('chartModelSemaforo', [{
            x: ['Rojo', 'Amarillo', 'Verde'],
            y: [sem.Rojo || 0, sem.Amarillo || 0, sem.Verde || 0],
            type: 'bar',
            marker: { color: ['#FF4D4F', '#FFC857', '#00C48C'] },
        }], {
            ...(typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {}),
            height: 240,
            margin: { t: 10, b: 40, l: 40, r: 10 },
        }, typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : {});
    }
}

function bindMlEngineEvents() {
    document.getElementById('btnSimRecalc')?.addEventListener('click', computeSimulatedScore);
    document.getElementById('simNlp')?.addEventListener('input', (e) => {
        const v = document.getElementById('simNlpVal');
        if (v) v.textContent = e.target.value + '%';
        computeSimulatedScore();
    });
    ['simMonto', 'simDias', 'simProv'].forEach((id) => {
        document.getElementById(id)?.addEventListener('change', computeSimulatedScore);
    });

    const applyFilters = async () => {
        mlEngineState.filters.semaforo = document.getElementById('mlFilterSemaforo')?.value || 'all';
        mlEngineState.filters.ramo = document.getElementById('mlFilterRamo')?.value || 'all';
        mlEngineState.filters.search = document.getElementById('mlFilterSearch')?.value || '';
        await refreshMlDynamicData();
    };
    document.getElementById('mlFilterApplyBtn')?.addEventListener('click', applyFilters);
    document.getElementById('mlFilterClearBtn')?.addEventListener('click', async () => {
        mlEngineState.filters = { semaforo: 'all', ramo: 'all', search: '' };
        const sem = document.getElementById('mlFilterSemaforo');
        const ramo = document.getElementById('mlFilterRamo');
        const search = document.getElementById('mlFilterSearch');
        if (sem) sem.value = 'all';
        if (ramo) ramo.value = 'all';
        if (search) search.value = '';
        await refreshMlDynamicData();
    });
    document.getElementById('mlFilterSearch')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') applyFilters();
    });
}

async function initMlEngine() {
    const container = document.getElementById('modelContent');
    if (!container) return;
    try {
        if (typeof bootstrapSessionFromServer === 'function') {
            await bootstrapSessionFromServer();
        }
        const [metricsResp, filtersResp] = await Promise.all([
            mlFetch('/api/model-metrics'),
            mlFetch('/api/dashboard-filters'),
        ]);
        let data;
        try {
            data = await metricsResp.json();
        } catch (_) {
            throw new Error('Respuesta inválida del servidor al cargar métricas ML');
        }
        if (!metricsResp.ok || data.error) {
            container.innerHTML = `<div class="alert alert-warning">${escapeHtml(
                data.error || 'No hay métricas ML disponibles'
            )}. Ejecute el pipeline desde Carga de Datos.</div>`;
            mlEngineState.initialized = false;
            return;
        }
        mlEngineState.metrics = data;

        let filtersData = {};
        try {
            filtersData = await filtersResp.json();
        } catch (_) {
            filtersData = {};
        }
        if (filtersResp.ok && !filtersData.error) {
            mlEngineState.options.ramos = filtersData.ramos || [];
        }

        ensureMlShell(container);

        safeRender(() => renderMlHeader(data), 'header');
        safeRender(() => renderModelCards(data), 'cards');
        safeRender(() => renderShapList(data.top_features || data.feature_importance || []), 'shap');
        safeRender(() => renderImportanceChart(data), 'importance');
        safeRender(() => renderConfusionChart(data), 'confusion');
        safeRender(() => renderAnomalyScatter(data), 'anomaly');
        safeRender(() => renderMonitorPanel(data), 'monitor');
        await refreshMlDynamicData();
    } catch (e) {
        console.error('initMlEngine:', e);
        mlEngineState.initialized = false;
        container.innerHTML = `<div class="alert alert-danger">Error al cargar el motor ML: ${escapeHtml(
            e.message || 'Error desconocido'
        )}. Verifique que el análisis IA haya terminado en Carga de Datos.</div>`;
    }
}

function escapeHtml(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

window.MlEngine = { init: initMlEngine, refresh: refreshMlDynamicData };
