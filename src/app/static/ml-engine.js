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
            <div class="ml-ia-header-main">
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
            </div>
            <aside class="ml-panel ml-sim-sidebar">
                <div class="ml-panel-title">Simulador predictivo</div>
                <p class="dash-chart-help">Ajuste los valores y pulse «Recalcular score».</p>
                <div class="ml-sim-grid">
                    <div class="ml-sim-field"><label>Monto reclamado ($)</label><input type="number" id="simMonto" value="45000" min="0" step="1000"></div>
                    <div class="ml-sim-field"><label>Días hasta reporte</label><input type="number" id="simDias" value="5" min="0" max="90"></div>
                    <div class="ml-sim-field"><label>Proveedor recurrente</label>
                        <select id="simProv"><option value="0">No</option><option value="1">Sí</option></select>
                    </div>
                    <div class="ml-sim-field"><label>Similitud narrativa (%)</label><input type="range" id="simNlp" min="0" max="100" value="20"><span id="simNlpVal" class="ml-sim-nlp-val">20%</span></div>
                </div>
                <button type="button" class="btn btn-primary ml-sim-btn" id="btnSimRecalc">Recalcular score</button>
                <div class="ml-sim-result">
                    <div class="ml-sim-score" id="simScoreOut">—</div>
                    <div class="ml-sim-prob" id="simProbOut">Prob. de revisión — · Severidad —</div>
                </div>
            </aside>
        </header>

        <div class="ml-models-grid" id="mlModelsGrid"></div>

        <div class="ml-panel" style="margin-bottom:1.25rem;">
            <div class="ml-panel-title">Matriz de confusión</div>
            <div id="chartConfusion" class="chart-area" style="min-height:300px;"></div>
        </div>

        <div class="ml-grid-2 ml-prob-charts-row">
            <div class="ml-panel">
                <div class="ml-panel-title">Prob. elevada sin alerta roja</div>
                <p class="dash-chart-help">Siniestros con probabilidad ML de fraude ≥50% pero semáforo final distinto de rojo (no acusados como críticos).</p>
                <div id="chartProbHidden" class="chart-area ml-chart-prob"></div>
            </div>
            <div class="ml-panel">
                <div class="ml-panel-title">Probabilidad ML por semáforo</div>
                <p class="dash-chart-help">Promedio de probabilidad del modelo y casos con prob. ≥70% según el semáforo operativo.</p>
                <div id="chartProbBySem" class="chart-area ml-chart-prob"></div>
            </div>
        </div>

        <div class="ml-grid-2 ml-monitor-row">
            <div class="ml-panel">
                <div class="ml-panel-title">Casos atípicos detectados</div>
                <div id="chartAnomalyScatter" class="chart-area ml-chart-anomaly"></div>
                <p class="dash-chart-help">Cada punto es un siniestro: monto vs. score de riesgo.</p>
            </div>
            <div class="ml-panel">
                <div class="ml-panel-title">Monitoreo del modelo</div>
                <div id="mlMonitorPanel"></div>
                <div id="chartModelDrift" class="chart-area ml-chart-drift"></div>
            </div>
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

function mlFmtCount(n) {
    const v = Number(n);
    if (!Number.isFinite(v) || v <= 0) return '';
    return v.toLocaleString('es-CO');
}

function renderProbHiddenChart(metrics) {
    const el = document.getElementById('chartProbHidden');
    if (!el || typeof Plotly === 'undefined') return;
    const block = metrics.prob_hidden_risk;
    const MC = typeof getColors === 'function' ? getColors() : {};
    const MPL = typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {};
    if (!block || !block.labels || !block.labels.length) {
        el.innerHTML = '<p style="color:var(--text-muted);font-size:0.8rem;padding:1rem 0;">Sin datos de probabilidad ML. Ejecute el análisis completo.</p>';
        return;
    }
    const counts = block.counts || [];
    const colors = counts.map((c, i) => {
        if (c <= 0) return 'rgba(100,116,139,0.35)';
        if (i >= 3) return MC.red || '#FF4D4F';
        if (i >= 2) return MC.yellow || '#FFC857';
        return MC.cyan || '#00D1FF';
    });
    Plotly.react('chartProbHidden', [{
        x: block.labels,
        y: counts,
        type: 'bar',
        marker: { color: colors, opacity: 0.92 },
        text: counts.map(mlFmtCount),
        textposition: 'outside',
        textfont: { size: 11, color: MC.text || '#E5F4FF' },
        hovertemplate: 'Rango %{x}<br>Casos: %{y:,}<extra></extra>',
    }], {
        ...MPL,
        margin: { t: 12, b: 56, l: 48, r: 16, autoexpand: true },
        height: 300,
        yaxis: { title: { text: 'Casos (semáforo ≠ rojo)', font: { size: 11 } }, gridcolor: MC.grid },
        xaxis: { title: { text: 'Probabilidad ML de fraude', font: { size: 11 } }, gridcolor: MC.grid },
    }, typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : { responsive: true });
}

function renderProbBySemaforoChart(metrics) {
    const el = document.getElementById('chartProbBySem');
    if (!el || typeof Plotly === 'undefined') return;
    const block = metrics.prob_by_semaforo;
    const MC = typeof getColors === 'function' ? getColors() : {};
    const MPL = typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {};
    if (!block || !block.semaforos || !block.semaforos.length) {
        el.innerHTML = '<p style="color:var(--text-muted);font-size:0.8rem;padding:1rem 0;">Sin datos de probabilidad ML.</p>';
        return;
    }
    const sems = block.semaforos;
    const avg = block.avg_prob_pct || [];
    const high = block.high_prob_counts || [];
    const semColors = [MC.green || '#00C48C', MC.yellow || '#FFC857', MC.red || '#FF4D4F'];
    Plotly.react('chartProbBySem', [
        {
            x: sems,
            y: avg,
            name: 'Prob. promedio (%)',
            type: 'bar',
            marker: { color: semColors, opacity: 0.85 },
            text: avg.map((v) => (v > 0 ? `${v}%` : '')),
            textposition: 'outside',
            textfont: { size: 11, color: MC.text || '#E5F4FF' },
            hovertemplate: '%{x}<br>Promedio: %{y:.1f}%<extra></extra>',
        },
        {
            x: sems,
            y: high,
            name: 'Casos prob. ≥70%',
            type: 'bar',
            marker: { color: semColors.map((c) => c + '99'), line: { color: c, width: 1 } },
            text: high.map(mlFmtCount),
            textposition: 'inside',
            textfont: { size: 10, color: '#fff' },
            hovertemplate: '%{x}<br>Alta prob.: %{y:,} casos<extra></extra>',
            yaxis: 'y2',
            opacity: 0.55,
        },
    ], {
        ...MPL,
        barmode: 'group',
        bargap: 0.22,
        bargroupgap: 0.12,
        margin: { t: 16, b: 48, l: 52, r: 52, autoexpand: true },
        height: 300,
        yaxis: {
            title: { text: 'Prob. promedio ML (%)', font: { size: 11 } },
            gridcolor: MC.grid,
            range: [0, Math.max(100, ...avg) * 1.15],
        },
        yaxis2: {
            title: { text: 'Casos ≥70%', font: { size: 10 } },
            overlaying: 'y',
            side: 'right',
            gridcolor: 'transparent',
            showgrid: false,
        },
        legend: { orientation: 'h', y: 1.12, x: 0, font: { size: 10 } },
    }, typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : { responsive: true });
}

function renderConfusionChart(data) {
    if (!data.confusion_matrix || typeof Plotly === 'undefined') return;
    const MC = typeof getColors === 'function' ? getColors() : {};
    const MPL = typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {};
    const cm = data.confusion_matrix;
    const labels = [['TN', 'FP'], ['FN', 'TP']];
    Plotly.react('chartConfusion', [{
        z: cm,
        x: ['Pred. sin alerta', 'Pred. revisión'],
        y: ['Real sin alerta', 'Real revisión'],
        type: 'heatmap',
        colorscale: [[0, MC.bgCard || '#0b1220'], [1, MC.cyan || '#00d1ff']],
        text: cm.map((row, i) => row.map((v, j) => `${labels[i][j]}: ${v}`)),
        texttemplate: '%{text}',
        textfont: { size: 13, color: '#ffffff', family: 'Inter, sans-serif' },
        hovertemplate: '%{y} / %{x}<br>Casos: %{z}<extra></extra>',
        showscale: true,
        colorbar: { title: 'Casos', thickness: 12, tickfont: { size: 9, color: MC.muted || '#9CB3CC' } },
    }], {
        ...MPL,
        margin: { t: 16, b: 56, l: 120, r: 40, autoexpand: true },
        height: 320,
        xaxis: { side: 'bottom', tickfont: { size: 10 } },
        yaxis: { automargin: true, tickfont: { size: 10 } },
    }, typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : { responsive: true });
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
    const top = [...points].sort((a, b) => (b.score_hibrido || 0) - (a.score_hibrido || 0)).slice(0, 8);
    Plotly.react('chartAnomalyScatter', [
        {
            x: points.map((p) => p.monto_reclamado || 0),
            y: points.map((p) => p.score_hibrido || 0),
            mode: 'markers',
            type: 'scatter',
            name: 'Siniestros',
            marker: { color: colors, size: 9, opacity: 0.78, line: { width: 0.5, color: 'rgba(255,255,255,0.25)' } },
            text: points.map((p) => p.id_siniestro),
            hovertemplate: '<b>%{text}</b><br>Monto: %{x:,.0f}<br>Score: %{y:.1f}<extra></extra>',
        },
        {
            x: top.map((p) => p.monto_reclamado || 0),
            y: top.map((p) => (p.score_hibrido || 0) + 1.5),
            mode: 'text',
            type: 'scatter',
            text: top.map((p) => p.id_siniestro),
            textposition: 'top center',
            textfont: { size: 9, color: MC.text || '#E5F4FF' },
            hoverinfo: 'skip',
            showlegend: false,
        },
    ], {
        ...(typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {}),
        margin: { t: 16, b: 48, l: 56, r: 16, autoexpand: true },
        xaxis: { title: { text: 'Monto reclamado ($)', font: { size: 11 } }, type: 'log', gridcolor: MC.grid },
        yaxis: { title: { text: 'Score de riesgo', font: { size: 11 } }, gridcolor: MC.grid },
        height: 300,
        showlegend: false,
    }, typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : { responsive: true });
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
        const MC = typeof getColors === 'function' ? getColors() : {};
        const counts = h.counts || [];
        Plotly.react('chartModelDrift', [{
            x: h.bins,
            y: counts,
            type: 'bar',
            marker: { color: [MC.green || '#00C48C', MC.yellow || '#FFC857', MC.red || '#FF4D4F'] },
            text: counts.map((c) => (c > 0 ? Number(c).toLocaleString('es-CO') : '')),
            textposition: 'outside',
            textfont: { size: 11, color: MC.text || '#E5F4FF' },
            hovertemplate: 'Rango: %{x}<br>Casos: %{y:,}<extra></extra>',
        }], {
            ...(typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {}),
            title: { text: 'Distribución de scores en cartera', font: { size: 11, color: MC.muted } },
            margin: { t: 36, b: 48, l: 48, r: 16, autoexpand: true },
            height: 240,
            yaxis: { title: 'Casos', gridcolor: MC.grid },
            xaxis: { title: 'Rango de score', gridcolor: MC.grid },
        }, typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : { responsive: true });
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
        safeRender(() => renderConfusionChart(data), 'confusion');
        safeRender(() => renderProbHiddenChart(data), 'prob-hidden');
        safeRender(() => renderProbBySemaforoChart(data), 'prob-sem');
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
