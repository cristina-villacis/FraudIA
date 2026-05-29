/**
 * FXecure — Análisis predictivo y simulación
 */
const mlEngineState = {
    initialized: false,
    metrics: null,
};

function buildMlShell() {
    return `
        <header class="ml-ia-header">
            <div class="ml-ia-title">
                <h2>Análisis predictivo</h2>
                <p>Simule escenarios y revise el desempeño del modelo sobre su cartera cargada.</p>
            </div>
            <div class="ml-metrics-strip">
                <div class="ml-metric-pill"><label>Estado</label><strong id="mlHdrStatus">—</strong></div>
                <div class="ml-metric-pill"><label>Modelo</label><strong id="mlHdrModel">—</strong></div>
                <div class="ml-metric-pill"><label>Precisión</label><strong id="mlHdrAccuracy">—</strong></div>
                <div class="ml-metric-pill"><label>Recall</label><strong id="mlHdrRecall">—</strong></div>
                <div class="ml-metric-pill"><label>F1</label><strong id="mlHdrF1">—</strong></div>
            </div>
        </header>

        <div class="ml-panel ml-sim-top" style="margin-bottom:1.25rem;">
            <div class="ml-panel-title">Simulador predictivo</div>
            <p class="dash-chart-help">Ajuste los valores y pulse «Recalcular score» para ver el impacto al instante en esta sesión.</p>
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
                <div class="ml-sim-prob" id="simProbOut">Prob. de revisión — · Severidad —</div>
            </div>
        </div>

        <div class="ml-models-grid" id="mlModelsGrid"></div>

        <div class="ml-grid-2">
            <div class="ml-panel">
                <div class="ml-panel-title">Variables más influyentes</div>
                <div id="mlShapList" class="ml-shap-list"></div>
                <div id="chartImportance" class="chart-area" style="min-height:280px;margin-top:1rem;"></div>
            </div>
            <div class="ml-panel">
                <div class="ml-panel-title">Matriz de confusión</div>
                <div id="chartConfusion" class="chart-area" style="min-height:300px;"></div>
            </div>
        </div>

        <div class="ml-panel" style="margin-bottom:1.25rem;">
            <div class="ml-panel-title">Casos atípicos detectados</div>
            <div id="chartAnomalyScatter" class="chart-area" style="min-height:260px;"></div>
            <p class="dash-chart-help">Cada punto es un siniestro: monto vs. score de riesgo.</p>
        </div>

        <div class="ml-panel">
            <div class="ml-panel-title">Monitoreo del modelo</div>
            <div id="mlMonitorPanel"></div>
            <div id="chartModelDrift" class="chart-area" style="min-height:200px;margin-top:0.75rem;"></div>
        </div>
    `;
}

function renderModelCards(metrics) {
    const grid = document.getElementById('mlModelsGrid');
    if (!grid) return;
    const auc = Number(metrics.auc_roc || 0).toFixed(3);
    const anom = metrics.anomalies_detected ?? '—';
    const trained = metrics.trained !== false && !metrics.error;
    const cards = [
        { name: 'Modelo supervisado', status: trained ? 'on' : 'off', note: `AUC ${auc}`, meta: metrics.model_version || 'fxecure-ml-1.0' },
        { name: 'Detección de anomalías', status: trained ? 'on' : 'off', note: `${anom} atípicos`, meta: 'Comportamiento inusual' },
    ];
    grid.innerHTML = cards.map((c) => `
        <div class="ml-model-card ${c.status === 'on' ? 'active' : 'standby'}">
            <div class="ml-model-status ${c.status}">${c.status === 'on' ? '● Activo' : '○ En espera'}</div>
            <h4>${c.name}</h4>
            <div class="ml-model-meta">${c.note}<br>${c.meta}</div>
        </div>
    `).join('');
}

function mlFetch(url, options = {}) {
    const headers = { ...(options.headers || {}) };
    try {
        const sid = sessionStorage.getItem('fxecure_session_id') || sessionStorage.getItem('fraudia_session_id');
        if (sid) {
            headers['X-FXecure-Session'] = sid;
            headers['X-FraudIA-Session'] = sid;
        }
    } catch (e) { /* ignore */ }
    if (typeof withFraudiaSessionHeaders === 'function') {
        return fetch(url, withFraudiaSessionHeaders({ ...options, headers }));
    }
    return fetch(url, { ...options, headers });
}

function fmtNum(v, digits = 3) {
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(digits) : '—';
}

function ensureMlShell(container) {
    if (document.getElementById('mlEngineShell')) return;
    mlEngineState.initialized = false;
    container.innerHTML = `<div id="mlEngineShell">${buildMlShell()}</div>`;
    bindMlEngineEvents();
    mlEngineState.initialized = true;
    computeSimulatedScore();
}

function safeRender(fn, label) {
    try { fn(); } catch (err) { console.warn('ML render:', label, err); }
}

function renderMlHeader(metrics) {
    const trained = metrics.trained !== false && !metrics.error;
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('mlHdrStatus', trained ? 'Operativo' : 'En espera');
    set('mlHdrModel', metrics.active_model || 'Modelo de riesgo');
    const acc = metrics.cv_auc_mean != null ? metrics.cv_auc_mean : metrics.auc_roc;
    set('mlHdrAccuracy', acc != null ? fmtNum(acc) : '—');
    set('mlHdrRecall', fmtNum(metrics.recall_fraude ?? metrics.recall ?? 0));
    set('mlHdrF1', fmtNum(metrics.f1_fraude ?? metrics.f1_score ?? 0));
}

function renderShapList(features) {
    const el = document.getElementById('mlShapList');
    if (!el || !features || !features.length) {
        if (el) el.innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;">Sin variables.</div>';
        return;
    }
    const max = Math.max(...features.map((f) => Number(f.importance || 0)), 0.001);
    el.innerHTML = features.slice(0, 8).map((f) => {
        const pct = (Number(f.importance || 0) / max) * 100;
        const label = String(f.feature || '').replace(/_/g, ' ').slice(0, 18);
        return `<div class="ml-shap-row"><span title="${f.feature}">${label}</span>
            <div class="track"><div class="fill" style="width:${pct}%;"></div></div>
            <span>${Number(f.importance || 0).toFixed(3)}</span></div>`;
    }).join('');
}

function renderImportanceChart(data) {
    if (!data.top_features || !data.top_features.length || typeof Plotly === 'undefined') return;
    const MPL = typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {};
    const feats = data.top_features.slice(0, 10).reverse();
    const barBase = document.documentElement.getAttribute('data-theme') === 'light' ? [0, 136, 204] : [0, 209, 255];
    Plotly.react('chartImportance', [{
        y: feats.map((f) => f.feature),
        x: feats.map((f) => f.importance),
        type: 'bar',
        orientation: 'h',
        marker: { color: feats.map((_, i) => `rgba(${barBase.join(',')},${0.35 + i * 0.06})`) },
    }], { ...MPL, margin: { t: 8, b: 30, l: 160, r: 20 }, height: 280 }, typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : { responsive: true });
}

function renderConfusionChart(data) {
    if (!data.confusion_matrix || typeof Plotly === 'undefined') return;
    const MC = typeof getColors === 'function' ? getColors() : {};
    const MPL = typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {};
    const cm = data.confusion_matrix;
    Plotly.react('chartConfusion', [{
        z: cm,
        x: ['Sin alerta', 'Requiere revisión'],
        y: ['Sin alerta', 'Requiere revisión'],
        type: 'heatmap',
        colorscale: [[0, MC.bgCard || '#0b1220'], [1, MC.cyan || '#00d1ff']],
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
    const MC = typeof getColors === 'function' ? getColors() : { red: '#FF4D4F', yellow: '#FFC857', green: '#00C48C' };
    const colors = points.map((p) => {
        const s = p.semaforo_final || 'Verde';
        return s === 'Rojo' ? MC.red : s === 'Amarillo' ? MC.yellow : MC.green;
    });
    Plotly.react('chartAnomalyScatter', [{
        x: points.map((p) => p.monto_reclamado || 0),
        y: points.map((p) => p.score_hibrido || 0),
        mode: 'markers',
        type: 'scatter',
        marker: { color: colors, size: 8, opacity: 0.75 },
        text: points.map((p) => p.id_siniestro),
    }], {
        ...(typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {}),
        xaxis: { title: 'Monto reclamado', type: 'log' },
        yaxis: { title: 'Score de riesgo' },
        height: 260,
    }, typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : {});
}

function bindMlEngineEvents() {
    document.getElementById('btnSimRecalc')?.addEventListener('click', computeSimulatedScore);
    document.getElementById('simNlp')?.addEventListener('input', (e) => {
        const v = document.getElementById('simNlpVal');
        if (v) v.textContent = e.target.value + '%';
    });
}

async function computeSimulatedScore() {
    const monto = Number(document.getElementById('simMonto')?.value || 0);
    const dias = Number(document.getElementById('simDias')?.value || 0);
    const prov = Number(document.getElementById('simProv')?.value || 0);
    const nlp = Number(document.getElementById('simNlp')?.value || 0);
    try {
        const resp = await mlFetch('/api/ml-simulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ monto, dias, prov, nlp }),
        });
        const data = await resp.json();
        if (!resp.ok || data.error) throw new Error(data.error || 'Error en simulación');
        document.getElementById('simScoreOut').textContent = data.score + '/100';
        document.getElementById('simProbOut').textContent =
            `Prob. de revisión ${data.prob_fraude}% · ${data.severidad} (${data.semaforo})`;
        if (mlEngineState.metrics) {
            mlEngineState.metrics.last_simulation = data;
            safeRender(() => renderMlHeader(mlEngineState.metrics), 'header-post-sim');
        }
    } catch (e) {
        document.getElementById('simScoreOut').textContent = '—';
        document.getElementById('simProbOut').textContent = 'Error: ' + (e.message || 'simulación');
    }
}

function renderMonitorPanel(metrics) {
    const el = document.getElementById('mlMonitorPanel');
    if (!el) return;
    const auc = Number(metrics.auc_roc || 0);
    const cv = Number(metrics.cv_auc_mean || auc);
    const drift = Math.abs(auc - cv) < 0.05 ? 'Estable' : 'Revisar';
    el.innerHTML = `
        <div class="ml-grid-3" style="gap:0.5rem;">
            <div><label style="font-size:0.6rem;color:var(--text-muted);">Estabilidad</label><div style="font-weight:700;">${drift}</div></div>
            <div><label style="font-size:0.6rem;color:var(--text-muted);">Atípicos</label><div style="font-weight:700;color:var(--cyan);">${metrics.anomalies_detected ?? '—'}</div></div>
            <div><label style="font-size:0.6rem;color:var(--text-muted);">CV AUC</label><div style="font-weight:700;">${cv.toFixed(3)}</div></div>
        </div>`;
    if (metrics.score_histogram && typeof Plotly !== 'undefined') {
        const h = metrics.score_histogram;
        Plotly.react('chartModelDrift', [{
            x: h.bins,
            y: h.counts,
            type: 'bar',
            marker: { color: ['#00C48C', '#FFC857', '#FF4D4F'] },
        }], {
            ...(typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {}),
            title: { text: 'Distribución de scores en cartera', font: { size: 11 } },
            height: 200,
        }, typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : {});
    }
}

async function initMlEngine() {
    const container = document.getElementById('modelContent');
    if (!container) return;
    try {
        if (typeof bootstrapSessionFromServer === 'function') await bootstrapSessionFromServer();
        const metricsResp = await mlFetch('/api/model-metrics');
        const data = await metricsResp.json();
        if (!metricsResp.ok || data.error) {
            container.innerHTML = `<div class="alert alert-warning">${escapeHtml(data.error || 'Ejecute el análisis desde Carga de datos.')}</div>`;
            return;
        }
        mlEngineState.metrics = data;
        ensureMlShell(container);
        safeRender(() => renderMlHeader(data), 'header');
        safeRender(() => renderModelCards(data), 'cards');
        safeRender(() => renderShapList(data.top_features || data.feature_importance || []), 'shap');
        safeRender(() => renderImportanceChart(data), 'importance');
        safeRender(() => renderConfusionChart(data), 'confusion');
        safeRender(() => renderAnomalyScatter(data), 'anomaly');
        safeRender(() => renderMonitorPanel(data), 'monitor');
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">No se pudo cargar el análisis predictivo: ${escapeHtml(e.message)}}</div>`;
    }
}

function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

window.MlEngine = { init: initMlEngine };
