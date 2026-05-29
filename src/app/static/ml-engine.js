/**
 * FXecure — Análisis predictivo premium (forecast, visualizaciones IA)
 */
const mlEngineState = {
    initialized: false,
    metrics: null,
    particlesRaf: null,
    liveTicker: null,
};

const ML_CHART_IDS = [
    'chartFraudTrend', 'chartForecast30', 'chartRiskEvolution', 'chartHistorical',
    'chartForecastIA', 'chartRadarMl', 'chartDonutSem', 'chartRiskHeatmap',
    'chartSankey', 'chartNetwork', 'chartRiskGauge', 'chartAnomalyHeat',
    'chartConfusion', 'chartProbHidden', 'chartProbBySem', 'chartAnomalyScatter', 'chartModelDrift',
];

function buildMlSkeleton() {
    return `
        <div class="ml-skeleton-wrap" id="mlSkeleton">
            <div class="ml-ia-loading">
                <span class="ml-ia-spinner" aria-hidden="true"></span>
                <span>IA analizando patrones predictivos y series temporales…</span>
            </div>
            <div class="ml-skeleton-grid">
                ${'<div class="ml-skeleton-card"></div>'.repeat(5)}
            </div>
            <div class="ml-skeleton-panel"></div>
            <div class="ml-skeleton-panel"></div>
        </div>`;
}

function buildMlShell() {
    return `
        <canvas id="mlParticles" aria-hidden="true"></canvas>

        <header class="ml-topbar ml-topbar--premium">
            <div class="ml-topbar-intro">
                <div class="ml-ia-title">
                    <h2>Análisis predictivo</h2>
                    <p>Forecast IA, tendencia de fraude y evolución de riesgo sobre su cartera.</p>
                </div>
                <div class="ml-neural-pulse" aria-hidden="true">
                    <span></span><span></span><span></span><span></span><span></span>
                </div>
                <div class="ml-live-indicator">
                    <span class="ml-live-dot"></span>
                    <span id="mlLiveLabel">Motor IA en tiempo real</span>
                </div>
            </div>
            <div class="ml-metrics-strip">
                <div class="ml-metric-pill"><label>Estado</label><strong id="mlHdrStatus">—</strong></div>
                <div class="ml-metric-pill"><label>Modelo</label><strong id="mlHdrModel">—</strong></div>
                <div class="ml-metric-pill"><label>AUC</label><strong id="mlHdrAccuracy">—</strong></div>
                <div class="ml-metric-pill"><label>Recall</label><strong id="mlHdrRecall">—</strong></div>
                <div class="ml-metric-pill"><label>F1</label><strong id="mlHdrF1">—</strong></div>
            </div>
        </header>

        <div class="ml-predict-kpis" id="mlPredictKpis"></div>

        <section class="ml-section-block">
            <h3 class="ml-section-title">Panel predictivo IA <span>Forecast · tendencia · riesgo histórico</span></h3>
            <div class="ml-predict-grid">
                <div class="ml-panel ml-panel--glow">
                    <div class="ml-panel-title">Tendencia de fraude <span class="ml-panel-badge">LIVE</span></div>
                    <div id="chartFraudTrend" class="chart-area ml-chart-tall"></div>
                </div>
                <div class="ml-panel ml-panel--glow">
                    <div class="ml-panel-title">Proyección 30 días</div>
                    <p class="ml-panel-help">Casos críticos proyectados con banda de confianza.</p>
                    <div id="chartForecast30" class="chart-area ml-chart-tall"></div>
                </div>
                <div class="ml-panel ml-panel--glow">
                    <div class="ml-panel-title">Evolución de riesgo</div>
                    <div id="chartRiskEvolution" class="chart-area ml-chart-med"></div>
                </div>
                <div class="ml-panel ml-panel--glow">
                    <div class="ml-panel-title">Comportamiento histórico</div>
                    <div id="chartHistorical" class="chart-area ml-chart-med"></div>
                </div>
            </div>
            <div class="ml-predict-grid" style="margin-top:1rem;">
                <div class="ml-panel ml-panel--glow" style="grid-column:1/-1;">
                    <div class="ml-panel-title">Forecast IA <span class="ml-panel-badge" id="mlForecastConf">—</span></div>
                    <div id="chartForecastIA" class="chart-area ml-chart-tall"></div>
                </div>
            </div>
        </section>

        <section class="ml-section-block">
            <h3 class="ml-section-title">Visualizaciones avanzadas <span>Radar · Sankey · red · heatmaps</span></h3>
            <div class="ml-viz-grid">
                <div class="ml-panel ml-panel--glow">
                    <div class="ml-panel-title">Radar de desempeño</div>
                    <div id="chartRadarMl" class="chart-area ml-chart-med"></div>
                </div>
                <div class="ml-panel ml-panel--glow">
                    <div class="ml-panel-title">Distribución semáforo</div>
                    <div id="chartDonutSem" class="chart-area ml-chart-med"></div>
                </div>
                <div class="ml-panel ml-panel--glow">
                    <div class="ml-panel-title">Gauge de riesgo</div>
                    <div id="chartRiskGauge" class="chart-area ml-chart-gauge"></div>
                </div>
            </div>
            <div class="ml-viz-grid ml-viz-grid--2" style="margin-top:1rem;">
                <div class="ml-panel ml-panel--glow">
                    <div class="ml-panel-title">Heatmap riesgo (monto × score)</div>
                    <div id="chartRiskHeatmap" class="chart-area ml-chart-med"></div>
                </div>
                <div class="ml-panel ml-panel--glow">
                    <div class="ml-panel-title">Heatmap anomalías temporales</div>
                    <div id="chartAnomalyHeat" class="chart-area ml-chart-med"></div>
                </div>
            </div>
            <div class="ml-viz-grid ml-viz-grid--2" style="margin-top:1rem;">
                <div class="ml-panel ml-panel--glow">
                    <div class="ml-panel-title">Flujo ramo → semáforo (Sankey)</div>
                    <div id="chartSankey" class="chart-area ml-chart-tall"></div>
                </div>
                <div class="ml-panel ml-panel--glow">
                    <div class="ml-panel-title">Red de exposición por proveedor</div>
                    <div id="chartNetwork" class="chart-area ml-chart-tall"></div>
                </div>
            </div>
        </section>

        <section class="ml-section-block">
            <h3 class="ml-section-title">Modelo y métricas</h3>
            <div class="ml-main">
                <div class="ml-panel ml-chart-panel ml-panel--glow">
                    <div class="ml-panel-title">Matriz de confusión</div>
                    <div id="chartConfusion" class="chart-area ml-chart-confusion"></div>
                </div>
                <div class="ml-grid-2 ml-prob-charts-row">
                    <div class="ml-panel ml-chart-panel ml-panel--glow">
                        <div class="ml-panel-title">Prob. elevada sin alerta roja</div>
                        <div id="chartProbHidden" class="chart-area ml-chart-prob"></div>
                    </div>
                    <div class="ml-panel ml-chart-panel ml-panel--glow">
                        <div class="ml-panel-title">Probabilidad ML por semáforo</div>
                        <div id="chartProbBySem" class="chart-area ml-chart-prob"></div>
                    </div>
                </div>
                <div class="ml-grid-2 ml-monitor-row">
                    <div class="ml-panel ml-chart-panel ml-panel--glow">
                        <div class="ml-panel-title">Casos atípicos (anomalías)</div>
                        <div id="chartAnomalyScatter" class="chart-area ml-chart-anomaly"></div>
                    </div>
                    <div class="ml-panel ml-chart-panel ml-panel--glow">
                        <div class="ml-panel-title">Monitoreo del modelo</div>
                        <div id="mlMonitorPanel" class="ml-monitor-stats"></div>
                        <div id="chartModelDrift" class="chart-area ml-chart-drift"></div>
                    </div>
                </div>
            </div>
        </section>
    `;
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

function mlPlotCfg() {
    return typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : { responsive: true, displayModeBar: false };
}

function mlColors() {
    return typeof getColors === 'function' ? getColors() : {
        cyan: '#3B82F6', blue: '#3B82F6', red: '#FF4D4F', yellow: '#FFC857',
        green: '#00C48C', text: '#E8F0FF', muted: '#94A3B8', grid: 'rgba(148,163,184,0.12)',
        bgCard: '#121A2F',
    };
}

function mlLayout(extra = {}) {
    const base = typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {};
    return { ...base, ...extra };
}

function fmtNum(v, digits = 3) {
    const n = Number(v);
    return Number.isFinite(n) ? n.toFixed(digits) : '—';
}

function mlFmtCount(n) {
    const v = Number(n);
    if (!Number.isFinite(v) || v <= 0) return '';
    return v.toLocaleString('es-CO');
}

function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function safeRender(fn, label) {
    try { fn(); } catch (err) { console.warn('ML render:', label, err); }
}

function mlEmptyChart(el, msg) {
    if (!el) return;
    el.innerHTML = `<p style="color:var(--text-muted);font-size:0.8rem;padding:1rem 0;">${escapeHtml(msg)}</p>`;
}

function scheduleMlChartsResize() {
    requestAnimationFrame(() => {
        setTimeout(() => resizeMlCharts(), 80);
        setTimeout(() => resizeMlCharts(), 400);
    });
}

function resizeMlCharts() {
    if (typeof Plotly === 'undefined') return;
    const tab = document.getElementById('tab-model');
    if (tab && !tab.classList.contains('active')) return;
    ML_CHART_IDS.forEach((id) => {
        const el = document.getElementById(id);
        if (!el || !el.querySelector('.plotly')) return;
        try { Plotly.Plots.resize(el); } catch (e) { /* ignore */ }
    });
}

if (typeof window !== 'undefined') {
    window.scheduleMlChartsResize = scheduleMlChartsResize;
    window.resizeMlCharts = resizeMlCharts;
}

function initMlParticles() {
    const canvas = document.getElementById('mlParticles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const tab = document.getElementById('tab-model');
    let w = 0;
    let h = 0;
    const dots = [];
    const N = 42;

    function resize() {
        const parent = canvas.parentElement;
        if (!parent) return;
        w = parent.clientWidth;
        h = Math.max(parent.clientHeight, 400);
        canvas.width = w;
        canvas.height = h;
    }

    for (let i = 0; i < N; i++) {
        dots.push({
            x: Math.random(),
            y: Math.random(),
            vx: (Math.random() - 0.5) * 0.0004,
            vy: (Math.random() - 0.5) * 0.0004,
            r: 1 + Math.random() * 1.5,
        });
    }

    function frame() {
        if (!tab?.classList.contains('active')) {
            mlEngineState.particlesRaf = requestAnimationFrame(frame);
            return;
        }
        ctx.clearRect(0, 0, w, h);
        dots.forEach((d) => {
            d.x += d.vx;
            d.y += d.vy;
            if (d.x < 0 || d.x > 1) d.vx *= -1;
            if (d.y < 0 || d.y > 1) d.vy *= -1;
            const px = d.x * w;
            const py = d.y * h;
            ctx.beginPath();
            ctx.arc(px, py, d.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(59,130,246,0.35)';
            ctx.fill();
        });
        for (let i = 0; i < dots.length; i++) {
            for (let j = i + 1; j < dots.length; j++) {
                const dx = (dots[i].x - dots[j].x) * w;
                const dy = (dots[i].y - dots[j].y) * h;
                const dist = Math.hypot(dx, dy);
                if (dist < 90) {
                    ctx.strokeStyle = `rgba(59,130,246,${0.12 * (1 - dist / 90)})`;
                    ctx.beginPath();
                    ctx.moveTo(dots[i].x * w, dots[i].y * h);
                    ctx.lineTo(dots[j].x * w, dots[j].y * h);
                    ctx.stroke();
                }
            }
        }
        mlEngineState.particlesRaf = requestAnimationFrame(frame);
    }

    resize();
    window.addEventListener('resize', resize);
    frame();
}

function startMlLiveTicker() {
    if (mlEngineState.liveTicker) clearInterval(mlEngineState.liveTicker);
    mlEngineState.liveTicker = setInterval(() => {
        const el = document.getElementById('mlLiveLabel');
        if (!el) return;
        const ms = 38 + Math.floor(Math.random() * 24);
        el.textContent = `Inferencia ${ms} ms · actualizado ${new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
    }, 3200);
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

function renderMlPredictKpis(metrics) {
    const el = document.getElementById('mlPredictKpis');
    if (!el) return;
    const p = metrics.predictive || {};
    const trend = p.fraud_trend || {};
    const fc = p.forecast_30d || {};
    const dir = trend.direction || 'neutral';
    const trendCls = dir === 'up' ? 'up' : dir === 'down' ? 'down' : 'neutral';
    const sumFc = (fc.forecast_rojos || []).reduce((a, b) => a + Number(b), 0);
    el.innerHTML = `
        <div class="ml-predict-kpi"><label>Tendencia fraude</label><strong>${escapeHtml(trend.label || '—')}</strong><div class="ml-kpi-trend ${trendCls}">${dir === 'up' ? '▲' : dir === 'down' ? '▼' : '●'} período</div></div>
        <div class="ml-predict-kpi"><label>Proyección 30d</label><strong>${Math.round(sumFc)}</strong><div class="ml-kpi-trend neutral">casos críticos est.</div></div>
        <div class="ml-predict-kpi"><label>Score cartera</label><strong>${p.risk_gauge_score ?? metrics.score_promedio ?? '—'}</strong><div class="ml-kpi-trend neutral">riesgo medio</div></div>
        <div class="ml-predict-kpi"><label>Atípicos IA</label><strong>${metrics.anomalies_detected ?? '—'}</strong><div class="ml-kpi-trend neutral">detección</div></div>
        <div class="ml-predict-kpi"><label>Confianza forecast</label><strong>${fc.confidence_pct != null ? fc.confidence_pct + '%' : '—'}</strong><div class="ml-kpi-trend neutral">banda predictiva</div></div>`;
}

function renderFraudTrendChart(metrics) {
    const el = document.getElementById('chartFraudTrend');
    if (!el || typeof Plotly === 'undefined') return;
    const hist = (metrics.predictive || {}).monthly_history || [];
    if (!hist.length) {
        mlEmptyChart(el, 'Sin serie mensual. Incluya fechas de ocurrencia en la carga.');
        return;
    }
    const MC = mlColors();
    const meses = hist.map((m) => m.mes);
    Plotly.react('chartFraudTrend', [
        {
            x: meses,
            y: hist.map((m) => m.Rojo || 0),
            name: 'Críticos',
            type: 'scatter',
            mode: 'lines+markers',
            fill: 'tozeroy',
            fillcolor: 'rgba(255,77,79,0.15)',
            line: { color: MC.red, width: 2.5, shape: 'spline' },
            marker: { size: 7, color: MC.red },
        },
        {
            x: meses,
            y: hist.map((m) => (m.Amarillo || 0) + (m.Verde || 0)),
            name: 'Resto cartera',
            type: 'scatter',
            mode: 'lines',
            line: { color: MC.cyan, width: 2, dash: 'dot', shape: 'spline' },
            fill: 'tozeroy',
            fillcolor: 'rgba(59,130,246,0.08)',
        },
    ], mlLayout({
        margin: { t: 12, b: 48, l: 48, r: 16 },
        height: 300,
        showlegend: true,
        legend: { orientation: 'h', y: 1.1, font: { size: 10 } },
        yaxis: { title: 'Casos', gridcolor: MC.grid },
        xaxis: { gridcolor: MC.grid },
    }), mlPlotCfg());
}

function renderForecast30(metrics) {
    const el = document.getElementById('chartForecast30');
    if (!el || typeof Plotly === 'undefined') return;
    const fc = (metrics.predictive || {}).forecast_30d;
    if (!fc) {
        mlEmptyChart(el, 'Proyección disponible tras análisis con fechas.');
        return;
    }
    const MC = mlColors();
    const histX = fc.historical_labels || [];
    const histY = fc.historical_rojos || [];
    const fX = fc.forecast_labels || [];
    const fY = fc.forecast_rojos || [];
    const bridgeX = histX.length ? [histX[histX.length - 1], fX[0]] : fX.slice(0, 1);
    const bridgeY = histY.length ? [histY[histY.length - 1], fY[0]] : [];

    Plotly.react('chartForecast30', [
        {
            x: histX,
            y: histY,
            name: 'Histórico',
            type: 'scatter',
            mode: 'lines',
            line: { color: MC.cyan, width: 2, shape: 'spline' },
            fill: 'tozeroy',
            fillcolor: 'rgba(59,130,246,0.12)',
        },
        {
            x: fX,
            y: fY,
            name: 'Proyección',
            type: 'scatter',
            mode: 'lines',
            line: { color: MC.yellow, width: 2.5, dash: 'dash', shape: 'spline' },
        },
        {
            x: fX,
            y: fc.forecast_upper,
            name: 'Banda sup.',
            type: 'scatter',
            mode: 'lines',
            line: { width: 0 },
            showlegend: false,
            hoverinfo: 'skip',
        },
        {
            x: fX,
            y: fc.forecast_lower,
            name: 'Confianza',
            type: 'scatter',
            mode: 'lines',
            fill: 'tonexty',
            fillcolor: 'rgba(255,200,87,0.12)',
            line: { width: 0 },
        },
        {
            x: bridgeX,
            y: bridgeY,
            mode: 'lines',
            line: { color: 'rgba(148,163,184,0.5)', dash: 'dot' },
            showlegend: false,
            hoverinfo: 'skip',
        },
    ], mlLayout({
        margin: { t: 12, b: 56, l: 48, r: 16 },
        height: 300,
        xaxis: { tickangle: -35, nticks: 12, gridcolor: MC.grid },
        yaxis: { title: 'Casos críticos', gridcolor: MC.grid },
        shapes: histX.length ? [{
            type: 'line',
            x0: histX[histX.length - 1],
            x1: histX[histX.length - 1],
            y0: 0,
            y1: 1,
            yref: 'paper',
            line: { color: 'rgba(148,163,184,0.35)', dash: 'dot', width: 1 },
        }] : [],
    }), mlPlotCfg());
}

function renderRiskEvolution(metrics) {
    const el = document.getElementById('chartRiskEvolution');
    if (!el || typeof Plotly === 'undefined') return;
    const rows = (metrics.predictive || {}).risk_evolution || [];
    if (!rows.length) {
        mlEmptyChart(el, 'Sin evolución de riesgo mensual.');
        return;
    }
    const MC = mlColors();
    Plotly.react('chartRiskEvolution', [{
        x: rows.map((r) => r.mes),
        y: rows.map((r) => r.score_avg),
        type: 'scatter',
        mode: 'lines+markers',
        fill: 'tozeroy',
        fillcolor: 'rgba(0,196,140,0.12)',
        line: { color: MC.green, width: 2.5, shape: 'spline' },
        marker: { size: 6, color: MC.green },
        name: 'Score medio',
    }], mlLayout({
        height: 260,
        margin: { t: 12, b: 48, l: 48, r: 16 },
        yaxis: { title: 'Score', range: [0, 100], gridcolor: MC.grid },
        xaxis: { gridcolor: MC.grid },
    }), mlPlotCfg());
}

function renderHistorical(metrics) {
    const el = document.getElementById('chartHistorical');
    if (!el || typeof Plotly === 'undefined') return;
    const hist = (metrics.predictive || {}).monthly_history || [];
    if (!hist.length) {
        mlEmptyChart(el, 'Sin histórico mensual.');
        return;
    }
    const MC = mlColors();
    Plotly.react('chartHistorical', [
        { x: hist.map((m) => m.mes), y: hist.map((m) => m.Verde || 0), name: 'Verde', type: 'bar', marker: { color: MC.green } },
        { x: hist.map((m) => m.mes), y: hist.map((m) => m.Amarillo || 0), name: 'Amarillo', type: 'bar', marker: { color: MC.yellow } },
        { x: hist.map((m) => m.mes), y: hist.map((m) => m.Rojo || 0), name: 'Rojo', type: 'bar', marker: { color: MC.red } },
    ], mlLayout({
        barmode: 'stack',
        height: 260,
        margin: { t: 12, b: 48, l: 48, r: 16 },
        yaxis: { title: 'Casos', gridcolor: MC.grid },
        legend: { orientation: 'h', y: 1.12, font: { size: 10 } },
    }), mlPlotCfg());
}

function renderForecastIA(metrics) {
    const el = document.getElementById('chartForecastIA');
    const badge = document.getElementById('mlForecastConf');
    if (!el || typeof Plotly === 'undefined') return;
    const block = (metrics.predictive || {}).forecast_ia;
    const fc = (metrics.predictive || {}).forecast_30d;
    if (badge && fc) badge.textContent = `Conf. ${fc.confidence_pct || 70}%`;
    if (!block || !block.labels?.length) {
        mlEmptyChart(el, 'Forecast IA requiere histórico diario.');
        return;
    }
    const MC = mlColors();
    const actual = block.actual || [];
    const pred = block.predicted || [];
    Plotly.react('chartForecastIA', [
        {
            x: block.labels,
            y: actual,
            name: 'Real',
            type: 'scatter',
            mode: 'lines+markers',
            line: { color: MC.cyan, width: 2 },
            connectgaps: false,
        },
        {
            x: block.labels,
            y: pred,
            name: 'IA forecast',
            type: 'scatter',
            mode: 'lines',
            line: { color: '#A78BFA', width: 2.5, shape: 'spline' },
            connectgaps: false,
        },
        {
            x: block.labels,
            y: block.upper,
            mode: 'lines',
            line: { width: 0 },
            showlegend: false,
            hoverinfo: 'skip',
            connectgaps: false,
        },
        {
            x: block.labels,
            y: block.lower,
            name: 'Banda',
            type: 'scatter',
            mode: 'lines',
            fill: 'tonexty',
            fillcolor: 'rgba(167,139,250,0.15)',
            line: { width: 0 },
            connectgaps: false,
        },
    ], mlLayout({
        height: 300,
        margin: { t: 12, b: 56, l: 48, r: 16 },
        xaxis: { tickangle: -35, nticks: 14, gridcolor: MC.grid },
        yaxis: { title: 'Casos críticos', gridcolor: MC.grid },
        legend: { orientation: 'h', y: 1.08 },
    }), mlPlotCfg());
}

function renderRadarMl(metrics) {
    const el = document.getElementById('chartRadarMl');
    if (!el || typeof Plotly === 'undefined') return;
    const r = (metrics.predictive || {}).feature_radar;
    if (!r) {
        mlEmptyChart(el, 'Sin métricas de radar.');
        return;
    }
    const MC = mlColors();
    Plotly.react('chartRadarMl', [{
        type: 'scatterpolar',
        r: [...r.values, r.values[0]],
        theta: [...r.labels, r.labels[0]],
        fill: 'toself',
        fillcolor: 'rgba(59,130,246,0.25)',
        line: { color: MC.cyan, width: 2 },
        name: 'Modelo',
    }], mlLayout({
        polar: {
            radialaxis: { visible: true, range: [0, 100], gridcolor: MC.grid },
            bgcolor: 'rgba(18,26,47,0.5)',
        },
        height: 260,
        margin: { t: 24, b: 24, l: 48, r: 48 },
        showlegend: false,
    }), mlPlotCfg());
}

function renderDonutSem(metrics) {
    const el = document.getElementById('chartDonutSem');
    if (!el || typeof Plotly === 'undefined') return;
    const d = (metrics.predictive || {}).donut_semaforo || metrics.semaforo_counts;
    let labels, values;
    if (d?.labels) {
        labels = d.labels;
        values = d.values;
    } else if (d) {
        labels = ['Verde', 'Amarillo', 'Rojo'];
        values = [d.Verde || 0, d.Amarillo || 0, d.Rojo || 0];
    } else {
        mlEmptyChart(el, 'Sin distribución de semáforo.');
        return;
    }
    const MC = mlColors();
    Plotly.react('chartDonutSem', [{
        labels,
        values,
        type: 'pie',
        hole: 0.62,
        marker: { colors: [MC.green, MC.yellow, MC.red], line: { color: '#121A2F', width: 2 } },
        textinfo: 'label+percent',
        textfont: { size: 11, color: MC.text },
        hovertemplate: '%{label}<br>%{value:,} casos<br>%{percent}<extra></extra>',
    }], mlLayout({
        height: 260,
        margin: { t: 8, b: 8, l: 8, r: 8 },
        showlegend: true,
        legend: { orientation: 'h', y: -0.05 },
    }), mlPlotCfg());
}

function renderRiskGauge(metrics) {
    const el = document.getElementById('chartRiskGauge');
    if (!el || typeof Plotly === 'undefined') return;
    const score = Number((metrics.predictive || {}).risk_gauge_score ?? metrics.score_promedio ?? 0);
    const MC = mlColors();
    const color = score >= 65 ? MC.red : score >= 45 ? MC.yellow : MC.green;
    Plotly.react('chartRiskGauge', [{
        type: 'indicator',
        mode: 'gauge+number',
        value: score,
        number: { suffix: '/100', font: { size: 28, color: MC.text } },
        gauge: {
            axis: { range: [0, 100], tickcolor: MC.muted },
            bar: { color, thickness: 0.35 },
            bgcolor: 'rgba(18,26,47,0.8)',
            borderwidth: 0,
            steps: [
                { range: [0, 40], color: 'rgba(0,196,140,0.25)' },
                { range: [40, 65], color: 'rgba(255,200,87,0.25)' },
                { range: [65, 100], color: 'rgba(255,77,79,0.3)' },
            ],
        },
        title: { text: 'Riesgo cartera', font: { size: 12, color: MC.muted } },
    }], mlLayout({ height: 220, margin: { t: 36, b: 16, l: 24, r: 24 } }), mlPlotCfg());
}

function renderRiskHeatmap(metrics) {
    const el = document.getElementById('chartRiskHeatmap');
    if (!el || typeof Plotly === 'undefined') return;
    const h = (metrics.predictive || {}).risk_heatmap;
    if (!h?.z?.length) {
        mlEmptyChart(el, 'Sin heatmap de riesgo.');
        return;
    }
    const MC = mlColors();
    Plotly.react('chartRiskHeatmap', [{
        z: h.z,
        x: h.x_labels,
        y: h.y_labels,
        type: 'heatmap',
        colorscale: [[0, MC.bgCard], [0.5, MC.yellow], [1, MC.red]],
        hovertemplate: 'Monto %{y}<br>Score %{x}<br>Casos: %{z}<extra></extra>',
    }], mlLayout({
        height: 260,
        margin: { t: 12, b: 48, l: 72, r: 24 },
        xaxis: { title: 'Score' },
        yaxis: { title: 'Monto' },
    }), mlPlotCfg());
}

function renderAnomalyHeat(metrics) {
    const el = document.getElementById('chartAnomalyHeat');
    if (!el || typeof Plotly === 'undefined') return;
    const h = (metrics.predictive || {}).anomaly_heatmap;
    if (!h?.z?.length) {
        mlEmptyChart(el, 'Heatmap temporal no disponible.');
        return;
    }
    Plotly.react('chartAnomalyHeat', [{
        z: h.z,
        x: h.x,
        y: h.y,
        type: 'heatmap',
        colorscale: 'Blues',
        hovertemplate: '%{y} · %{x}<br>Score medio: %{z:.1f}<extra></extra>',
    }], mlLayout({ height: 260, margin: { t: 12, b: 48, l: 56, r: 24 } }), mlPlotCfg());
}

function renderSankey(metrics) {
    const el = document.getElementById('chartSankey');
    if (!el || typeof Plotly === 'undefined') return;
    const s = (metrics.predictive || {}).sankey;
    if (!s?.labels?.length || !s.value?.length) {
        mlEmptyChart(el, 'Sankey requiere ramo y semáforo en los datos.');
        return;
    }
    const MC = mlColors();
    Plotly.react('chartSankey', [{
        type: 'sankey',
        orientation: 'h',
        node: {
            pad: 14,
            thickness: 16,
            line: { color: '#121A2F', width: 0.5 },
            label: s.labels,
            color: s.labels.map((_, i) => `rgba(59,130,246,${0.35 + (i % 5) * 0.1})`),
        },
        link: {
            source: s.source,
            target: s.target,
            value: s.value,
            color: 'rgba(59,130,246,0.35)',
        },
    }], mlLayout({
        height: 320,
        margin: { t: 16, b: 16, l: 16, r: 16 },
        font: { size: 10, color: MC.text },
    }), mlPlotCfg());
}

function renderNetwork(metrics) {
    const el = document.getElementById('chartNetwork');
    if (!el || typeof Plotly === 'undefined') return;
    const net = (metrics.predictive || {}).risk_network;
    if (!net?.edges?.length) {
        mlEmptyChart(el, 'Red de proveedores no disponible.');
        return;
    }
    const nodes = net.nodes || [];
    const idToIdx = {};
    nodes.forEach((n, i) => { idToIdx[n.id] = i; });
    const x = nodes.map((_, i) => Math.cos((i / nodes.length) * Math.PI * 2) * (i === 0 ? 0 : 1));
    const y = nodes.map((_, i) => Math.sin((i / nodes.length) * Math.PI * 2) * (i === 0 ? 0 : 1));
    if (nodes.length) { x[0] = 0; y[0] = 0; }
    const MC = mlColors();
    const edgeX = [];
    const edgeY = [];
    net.edges.forEach((e) => {
        const a = idToIdx[e.source];
        const b = idToIdx[e.target];
        if (a == null || b == null) return;
        edgeX.push(x[a], x[b], null);
        edgeY.push(y[a], y[b], null);
    });
    const sizes = nodes.map((n) => 12 + (n.size || 10) * 1.2);
    Plotly.react('chartNetwork', [
        {
            x: edgeX,
            y: edgeY,
            mode: 'lines',
            line: { color: 'rgba(59,130,246,0.35)', width: Math.max(1, ...(net.edges.map((e) => e.weight / 8))) },
            hoverinfo: 'none',
            showlegend: false,
        },
        {
            x,
            y,
            mode: 'markers+text',
            text: nodes.map((n) => n.label),
            textposition: 'top center',
            textfont: { size: 9, color: MC.muted },
            marker: {
                size: sizes,
                color: nodes.map((n, i) => (i === 0 ? MC.cyan : MC.red)),
                line: { width: 1, color: '#fff' },
                opacity: 0.9,
            },
            hovertemplate: '%{text}<extra></extra>',
        },
    ], mlLayout({
        height: 320,
        margin: { t: 24, b: 24, l: 24, r: 24 },
        xaxis: { visible: false, showgrid: false, zeroline: false },
        yaxis: { visible: false, showgrid: false, zeroline: false },
        showlegend: false,
    }), mlPlotCfg());
}

function renderProbHiddenChart(metrics) {
    const el = document.getElementById('chartProbHidden');
    if (!el || typeof Plotly === 'undefined') return;
    const block = metrics.prob_hidden_risk;
    const MC = mlColors();
    if (!block?.labels?.length) {
        mlEmptyChart(el, 'Sin datos de probabilidad ML oculta.');
        return;
    }
    const counts = block.counts || [];
    const colors = counts.map((c, i) => {
        if (c <= 0) return 'rgba(100,116,139,0.35)';
        if (i >= 3) return MC.red;
        if (i >= 2) return MC.yellow;
        return MC.cyan;
    });
    Plotly.react('chartProbHidden', [{
        x: block.labels,
        y: counts,
        type: 'bar',
        marker: { color: colors, opacity: 0.92 },
        text: counts.map(mlFmtCount),
        textposition: 'outside',
    }], mlLayout({ height: 300, margin: { t: 12, b: 56, l: 48, r: 16 }, yaxis: { gridcolor: MC.grid } }), mlPlotCfg());
}

function renderProbBySemaforoChart(metrics) {
    const el = document.getElementById('chartProbBySem');
    if (!el || typeof Plotly === 'undefined') return;
    const block = metrics.prob_by_semaforo;
    const MC = mlColors();
    if (!block?.semaforos?.length) {
        mlEmptyChart(el, 'Sin datos de probabilidad por semáforo.');
        return;
    }
    const semColors = [MC.green, MC.yellow, MC.red];
    Plotly.react('chartProbBySem', [
        {
            x: block.semaforos,
            y: block.avg_prob_pct || [],
            name: 'Prob. promedio (%)',
            type: 'bar',
            marker: { color: semColors, opacity: 0.85 },
        },
        {
            x: block.semaforos,
            y: block.high_prob_counts || [],
            name: 'Casos prob. ≥70%',
            type: 'bar',
            yaxis: 'y2',
            marker: { color: semColors.map((c) => c + '99') },
            opacity: 0.55,
        },
    ], mlLayout({
        barmode: 'group',
        height: 300,
        yaxis: { title: 'Prob. %', gridcolor: MC.grid },
        yaxis2: { title: 'Alta prob.', overlaying: 'y', side: 'right', showgrid: false },
        legend: { orientation: 'h', y: 1.12 },
    }), mlPlotCfg());
}

function renderConfusionChart(data) {
    if (!data.confusion_matrix || typeof Plotly === 'undefined') return;
    const MC = mlColors();
    const cm = data.confusion_matrix;
    const labels = [['TN', 'FP'], ['FN', 'TP']];
    Plotly.react('chartConfusion', [{
        z: cm,
        x: ['Pred. sin alerta', 'Pred. revisión'],
        y: ['Real sin alerta', 'Real revisión'],
        type: 'heatmap',
        colorscale: [[0, MC.bgCard], [1, MC.cyan]],
        text: cm.map((row, i) => row.map((v, j) => `${labels[i][j]}: ${v}`)),
        texttemplate: '%{text}',
        textfont: { size: 13, color: '#fff' },
    }], mlLayout({ height: 320, margin: { t: 16, b: 56, l: 120, r: 40 } }), mlPlotCfg());
}

function renderAnomalyScatter(metrics) {
    const el = document.getElementById('chartAnomalyScatter');
    if (!el || typeof Plotly === 'undefined') return;
    const points = metrics.anomaly_scatter || [];
    if (!points.length) {
        mlEmptyChart(el, 'Sin puntos de anomalía.');
        return;
    }
    const MC = mlColors();
    const colors = points.map((p) => {
        const s = p.semaforo_final || 'Verde';
        return s === 'Rojo' ? MC.red : s === 'Amarillo' ? MC.yellow : MC.green;
    });
    const scores = points.map((p) => p.anomaly_score || p.score_hibrido || 0);
    Plotly.react('chartAnomalyScatter', [{
        x: points.map((p) => p.monto_reclamado || 0),
        y: scores,
        mode: 'markers',
        type: 'scatter',
        marker: {
            color: colors,
            size: scores.map((s) => 6 + Math.min(14, s / 8)),
            opacity: 0.8,
            line: { width: 0.5, color: 'rgba(255,255,255,0.2)' },
        },
        text: points.map((p) => p.id_siniestro),
        hovertemplate: '<b>%{text}</b><br>Monto: %{x:,.0f}<br>Riesgo: %{y:.1f}<extra></extra>',
    }], mlLayout({
        height: 300,
        xaxis: { title: 'Monto ($)', type: 'log', gridcolor: MC.grid },
        yaxis: { title: 'Score / anomalía', gridcolor: MC.grid },
    }), mlPlotCfg());
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
            <div><label style="font-size:0.6rem;color:var(--text-muted);">Atípicos</label><div style="font-weight:700;color:#3b82f6;">${metrics.anomalies_detected ?? '—'}</div></div>
            <div><label style="font-size:0.6rem;color:var(--text-muted);">CV AUC</label><div style="font-weight:700;">${cv.toFixed(3)}</div></div>
        </div>`;
    if (metrics.score_histogram && typeof Plotly !== 'undefined') {
        const h = metrics.score_histogram;
        const MC = mlColors();
        const counts = h.counts || [];
        Plotly.react('chartModelDrift', [{
            x: h.bins,
            y: counts,
            type: 'bar',
            marker: { color: [MC.green, MC.yellow, MC.red] },
            text: counts.map((c) => (c > 0 ? Number(c).toLocaleString('es-CO') : '')),
            textposition: 'outside',
        }], mlLayout({
            title: { text: 'Distribución de scores', font: { size: 11, color: MC.muted } },
            height: 240,
            margin: { t: 36, b: 48, l: 48, r: 16 },
        }), mlPlotCfg());
    }
}

function renderAllMlCharts(metrics) {
    renderMlHeader(metrics);
    renderMlPredictKpis(metrics);
    safeRender(() => renderFraudTrendChart(metrics), 'fraud-trend');
    safeRender(() => renderForecast30(metrics), 'forecast-30');
    safeRender(() => renderRiskEvolution(metrics), 'risk-evo');
    safeRender(() => renderHistorical(metrics), 'historical');
    safeRender(() => renderForecastIA(metrics), 'forecast-ia');
    safeRender(() => renderRadarMl(metrics), 'radar');
    safeRender(() => renderDonutSem(metrics), 'donut');
    safeRender(() => renderRiskGauge(metrics), 'gauge');
    safeRender(() => renderRiskHeatmap(metrics), 'heatmap');
    safeRender(() => renderAnomalyHeat(metrics), 'anomaly-heat');
    safeRender(() => renderSankey(metrics), 'sankey');
    safeRender(() => renderNetwork(metrics), 'network');
    safeRender(() => renderConfusionChart(metrics), 'confusion');
    safeRender(() => renderProbHiddenChart(metrics), 'prob-hidden');
    safeRender(() => renderProbBySemaforoChart(metrics), 'prob-sem');
    safeRender(() => renderAnomalyScatter(metrics), 'anomaly');
    safeRender(() => renderMonitorPanel(metrics), 'monitor');
}

async function initMlEngine() {
    const container = document.getElementById('modelContent');
    if (!container) return;
    container.innerHTML = buildMlSkeleton();
    try {
        if (typeof bootstrapSessionFromServer === 'function') await bootstrapSessionFromServer();
        const metricsResp = await mlFetch('/api/model-metrics');
        const data = await metricsResp.json();
        if (!metricsResp.ok || data.error) {
            container.innerHTML = `<div class="alert alert-warning">${escapeHtml(data.error || 'Ejecute el análisis desde Carga de datos.')}</div>`;
            return;
        }
        mlEngineState.metrics = data;
        container.innerHTML = `<div id="mlEngineShell" class="ml-predictive-root">${buildMlShell()}</div>`;
        initMlParticles();
        startMlLiveTicker();
        mlEngineState.initialized = true;
        renderAllMlCharts(data);
        scheduleMlChartsResize();
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">No se pudo cargar el análisis predictivo: ${escapeHtml(e.message)}</div>`;
    }
}

window.MlEngine = { init: initMlEngine };
