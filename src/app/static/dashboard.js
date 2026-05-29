/**
 * FraudIA — Dashboard antifraude enterprise (Plotly + API /api/dashboard-data)
 */
const fraudiaDash = {
    initialized: false,
    options: null,
    filters: {
        semaforo: 'all', ramo: 'all', cobertura: 'all', sucursal: 'all', estado: 'all',
        search: '', score_min: '', score_max: '', fecha_desde: '', fecha_hasta: '',
    },
    lastData: null,
    temporalFreq: 'month',
    tableSort: { key: 'score', dir: 'desc' },
    refreshTimer: null,
};

const FD_CHARTS = [
    'fdChartDonut', 'fdChartTemporal', 'fdChartRadar', 'fdChartGeo',
    'fdChartWaterfall', 'fdChartNetwork', 'fdChartGauge',
];

function fdColors() {
    return typeof getColors === 'function' ? getColors() : {
        cyan: '#22d3ee', blue: '#3b82f6', red: '#FF4D4F', yellow: '#F5B700',
        green: '#00C48C', purple: '#a78bfa', text: '#E8F0FF', muted: '#94A3B8',
        grid: 'rgba(148,163,184,0.12)', bgCard: '#0e1426',
    };
}

function fdLayout(extra = {}) {
    return { ...(typeof getPlotlyLayout === 'function' ? getPlotlyLayout() : {}), ...extra };
}

function fdCfg() {
    return typeof PLOTLY_CONFIG !== 'undefined' ? PLOTLY_CONFIG : { responsive: true, displayModeBar: false };
}

function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtKpi(item) {
    const v = Number(item.value);
    if (item.format === 'currency') {
        return v >= 1e6 ? '$' + (v / 1e6).toFixed(1) + 'M' : '$' + Number(v).toLocaleString('es-CO', { maximumFractionDigits: 0 });
    }
    if (item.format === 'percent') return v.toFixed(1) + '%';
    if (item.format === 'score') return v.toFixed(1);
    return Number(v).toLocaleString('es-CO');
}

function sparklineSvg(vals, color, w = 56, h = 22) {
    const pts = (vals || []).filter((n) => Number.isFinite(Number(n))).map(Number);
    if (pts.length < 2) return '';
    const min = Math.min(...pts);
    const max = Math.max(...pts);
    const range = max - min || 1;
    const coords = pts.map((v, i) => {
        const x = 2 + (i / (pts.length - 1)) * (w - 4);
        const y = h - 2 - ((v - min) / range) * (h - 4);
        return `${x},${y}`;
    });
    return `<svg width="${w}" height="${h}" class="fd-spark"><polyline fill="none" stroke="${color}" stroke-width="1.8" points="${coords.join(' ')}"/></svg>`;
}

function buildFraudiaShell() {
    return `
        <canvas id="fraudiaParticles" aria-hidden="true"></canvas>
        <div class="fraudia-dash" id="fraudiaDashRoot">
            <header class="fraudia-dash-header">
                <div>
                    <h2>FraudIA</h2>
                    <p>Centro de monitoreo antifraude · IA · ML · Anomalías</p>
                    <div class="fraudia-meta" style="margin-top:0.5rem;">
                        <span class="fraudia-live"><span class="fraudia-live-dot"></span> IA activa</span>
                        <span>Motor: <strong id="fdModelName">—</strong></span>
                        <span>Salud: <strong id="fdHealthScore">—</strong></span>
                        <span id="fdUpdated">—</span>
                    </div>
                </div>
            </header>

            <div id="fraudiaBanner" class="fraudia-banner"></div>

            <div class="fraudia-toolbar">
                <input type="text" id="fdSearch" class="fraudia-search" placeholder="Buscar ID siniestro…">
                <select id="fdFilterSem"><option value="all">Todos los semáforos</option><option value="Verde">Verde</option><option value="Amarillo">Amarillo</option><option value="Rojo">Rojo</option></select>
                <select id="fdFilterRamo"><option value="all">Todos los ramos</option></select>
                <button type="button" class="btn btn-primary" id="fdApplyFilters" style="padding:0.35rem 0.85rem;font-size:0.78rem;">Aplicar</button>
                <button type="button" class="btn btn-secondary" id="fdResetFilters" style="padding:0.35rem 0.85rem;font-size:0.78rem;">Limpiar</button>
            </div>

            <div id="fraudiaInsights" class="fraudia-insights"></div>
            <div id="fraudiaKpis" class="fraudia-kpi-row"></div>

            <div class="fraudia-ops-row" id="fraudiaOps"></div>

            <div class="fraudia-grid-2">
                <div class="fraudia-panel">
                    <div class="fraudia-panel-head"><span class="fraudia-panel-title">Distribución de riesgo</span></div>
                    <div id="fdChartDonut" class="fraudia-chart fraudia-chart-sm"></div>
                </div>
                <div class="fraudia-panel">
                    <div class="fraudia-panel-head">
                        <span class="fraudia-panel-title">Evolución temporal</span>
                        <div class="fraudia-temporal-tabs">
                            <button type="button" data-freq="day">Día</button>
                            <button type="button" data-freq="week">Semana</button>
                            <button type="button" data-freq="month" class="active">Mes</button>
                        </div>
                    </div>
                    <div id="fdChartTemporal" class="fraudia-chart"></div>
                </div>
            </div>

            <div class="fraudia-grid-2">
                <div class="fraudia-panel">
                    <div class="fraudia-panel-head"><span class="fraudia-panel-title">Radar IA — dimensiones de riesgo</span></div>
                    <div id="fdChartRadar" class="fraudia-chart fraudia-chart-sm"></div>
                </div>
                <div class="fraudia-panel">
                    <div class="fraudia-panel-head"><span class="fraudia-panel-title">Heatmap geográfico antifraude</span></div>
                    <div id="fdChartGeo" class="fraudia-chart"></div>
                </div>
            </div>

            <div class="fraudia-grid-2">
                <div class="fraudia-panel">
                    <div class="fraudia-panel-head"><span class="fraudia-panel-title">Waterfall — construcción del score</span></div>
                    <div id="fdChartWaterfall" class="fraudia-chart"></div>
                </div>
                <div class="fraudia-panel">
                    <div class="fraudia-panel-head"><span class="fraudia-panel-title">Red de fraude</span></div>
                    <div id="fdChartNetwork" class="fraudia-chart fraudia-chart-lg"></div>
                </div>
            </div>

            <div class="fraudia-panel" style="margin-bottom:1rem;">
                <div class="fraudia-panel-head">
                    <span class="fraudia-panel-title">Casos prioritarios — bandeja inteligente</span>
                    <span id="fdCaseCount" style="font-size:0.72rem;color:var(--text-muted);">0 casos</span>
                </div>
                <div class="fraudia-table-wrap">
                    <table class="fraudia-table" id="fraudiaCasesTable">
                        <thead><tr>
                            <th data-sort="id_siniestro">ID</th>
                            <th data-sort="score">Score</th>
                            <th data-sort="semaforo">Semáforo</th>
                            <th data-sort="prob_fraude">Prob. IA</th>
                            <th>Anomalía</th>
                            <th>Alertas</th>
                            <th data-sort="monto_reclamado">Monto</th>
                            <th>Ciudad</th>
                            <th>Proveedor</th>
                            <th>Estado</th>
                            <th>Acciones</th>
                        </tr></thead>
                        <tbody id="fraudiaCasesBody"></tbody>
                    </table>
                </div>
            </div>

            <div class="fraudia-panel">
                <div class="fraudia-panel-head"><span class="fraudia-panel-title">Explicabilidad — score híbrido</span></div>
                <div id="fdChartGauge" class="fraudia-chart fraudia-chart-sm"></div>
            </div>
        </div>

        <aside id="fraudiaDrawer" class="fraudia-drawer" aria-hidden="true">
            <button type="button" id="fraudiaDrawerClose" style="float:right;background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:1.2rem;">✕</button>
            <h4 id="fraudiaDrawerTitle">Explicabilidad IA</h4>
            <div id="fraudiaDrawerBody"></div>
        </aside>
    `;
}

function showSkeleton() {
    return `<div class="fraudia-kpi-row">${'<div class="fraudia-skeleton" style="min-height:96px;flex:1;"></div>'.repeat(4)}</div>
        <div class="fraudia-skeleton" style="min-height:280px;margin-bottom:1rem;"></div>
        <div class="fraudia-skeleton" style="min-height:280px;"></div>`;
}

function initParticles() {
    const canvas = document.getElementById('fraudiaParticles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const parent = canvas.parentElement;
    let w = 0, h = 0;
    const dots = Array.from({ length: 40 }, () => ({
        x: Math.random(), y: Math.random(),
        vx: (Math.random() - 0.5) * 0.00035, vy: (Math.random() - 0.5) * 0.00035,
        r: 0.5 + Math.random(),
    }));
    const resize = () => {
        if (!parent) return;
        w = canvas.width = parent.clientWidth;
        h = canvas.height = Math.max(parent.clientHeight, 500);
    };
    const tick = () => {
        if (!w) { requestAnimationFrame(tick); return; }
        ctx.clearRect(0, 0, w, h);
        dots.forEach((d) => {
            d.x += d.vx; d.y += d.vy;
            if (d.x < 0 || d.x > 1) d.vx *= -1;
            if (d.y < 0 || d.y > 1) d.vy *= -1;
            ctx.beginPath();
            ctx.arc(d.x * w, d.y * h, d.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(34, 211, 238, 0.3)';
            ctx.fill();
        });
        requestAnimationFrame(tick);
    };
    resize();
    window.addEventListener('resize', resize);
    tick();
}

function renderKpis(kpis) {
    const el = document.getElementById('fraudiaKpis');
    if (!el) return;
    el.innerHTML = (kpis || []).map((k, i) => {
        const trendCls = k.trend_dir || 'neutral';
        const sign = k.trend_pct > 0 ? '+' : '';
        const trendTxt = k.trend_pct ? `${sign}${k.trend_pct}%` : '';
        const glow = k.glow || 'cyan';
        const color = glow === 'red' ? 'var(--fd-red)' : glow === 'green' ? 'var(--fd-green)' : glow === 'amber' ? 'var(--fd-yellow)' : glow === 'purple' ? 'var(--fd-purple)' : '#fff';
        return `<article class="fraudia-kpi glow-${glow}" style="animation-delay:${i * 0.04}s">
            <div class="fraudia-kpi-label">${escapeHtml(k.label)}</div>
            <div class="fraudia-kpi-value" style="color:${color}">${fmtKpi(k)}</div>
            <div class="fraudia-kpi-foot">
                <span class="fraudia-kpi-trend ${trendCls}">${trendTxt}</span>
                ${sparklineSvg(k.spark, 'var(--fd-cyan)')}
            </div>
        </article>`;
    }).join('');
}

function renderInsights(insights) {
    const el = document.getElementById('fraudiaInsights');
    if (!el) return;
    el.innerHTML = (insights || []).map((ins, i) =>
        `<div class="fraudia-insight ${ins.type || 'info'}" style="animation-delay:${i * 0.05}s">${escapeHtml(ins.text)}</div>`
    ).join('');
}

function renderOps(ops) {
    const el = document.getElementById('fraudiaOps');
    if (!el || !ops) return;
    const items = [
        { label: 'AUC-ROC', val: ops.auc_roc != null ? ops.auc_roc : '—' },
        { label: 'Precisión IA', val: ops.precision_pct != null ? ops.precision_pct + '%' : '—' },
        { label: 'Anomalías', val: ops.total_anomalies != null ? ops.total_anomalies.toLocaleString() : '—' },
        { label: 'Inferencia', val: (ops.processing_ms || '—') + ' ms' },
        { label: 'Health score', val: ops.health_score != null ? ops.health_score + '/100' : '—' },
    ];
    el.innerHTML = items.map((o) =>
        `<div class="fraudia-ops-card"><label>${o.label}</label><strong>${o.val}</strong></div>`
    ).join('');
    const mn = document.getElementById('fdModelName');
    const hs = document.getElementById('fdHealthScore');
    if (mn) mn.textContent = ops.model_name || 'FraudIA';
    if (hs) hs.textContent = ops.health_score != null ? ops.health_score + '/100' : '—';
}

function plotDonut(donut) {
    const C = fdColors();
    if (!donut?.values?.length || typeof Plotly === 'undefined') return;
    Plotly.react('fdChartDonut', [{
        labels: donut.labels,
        values: donut.values,
        type: 'pie',
        hole: 0.62,
        marker: { colors: [C.green, C.yellow, C.red] },
        textinfo: 'label+percent',
        hovertemplate: '%{label}<br>%{value:,} casos<br>%{percent}<extra></extra>',
    }], fdLayout({ height: 260, margin: { t: 8, b: 8, l: 8, r: 8 }, showlegend: true }), fdCfg());
}

function plotTemporal(fd, freq) {
    const block = (fd?.temporal || {})[freq] || {};
    const C = fdColors();
    if (!block.labels?.length || typeof Plotly === 'undefined') return;
    Plotly.react('fdChartTemporal', [
        { x: block.labels, y: block.siniestros, name: 'Siniestros', type: 'scatter', mode: 'lines', fill: 'tozeroy', line: { color: C.cyan, width: 2 }, fillcolor: 'rgba(34,211,238,0.1)' },
        { x: block.labels, y: block.fraudes, name: 'Fraudes (rojo)', type: 'scatter', mode: 'lines', line: { color: C.red, width: 2 } },
        { x: block.labels, y: block.anomalias, name: 'Anomalías', type: 'scatter', mode: 'lines', line: { color: C.purple, width: 2, dash: 'dot' } },
    ], fdLayout({
        height: 280, margin: { t: 12, b: 48, l: 48, r: 16 },
        legend: { orientation: 'h', y: 1.1 }, xaxis: { tickangle: -30, gridcolor: C.grid },
        yaxis: { gridcolor: C.grid },
    }), fdCfg());
}

function plotRadar(radar) {
    const C = fdColors();
    if (!radar?.labels?.length || typeof Plotly === 'undefined') return;
    Plotly.react('fdChartRadar', [{
        type: 'scatterpolar',
        r: [...radar.values, radar.values[0]],
        theta: [...radar.labels, radar.labels[0]],
        fill: 'toself',
        fillcolor: 'rgba(167,139,250,0.2)',
        line: { color: C.purple, width: 2 },
    }], fdLayout({
        height: 260, polar: { radialaxis: { range: [0, 100], gridcolor: C.grid }, bgcolor: 'transparent' },
    }), fdCfg());
}

function plotGeo(geo) {
    const C = fdColors();
    if (!geo?.locations?.length || typeof Plotly === 'undefined') return;
    const colors = (geo.intensity || []).map((v) => {
        if (v >= 60) return '#B91C1C';
        if (v >= 40) return C.red;
        if (v >= 25) return C.yellow;
        return C.blue;
    });
    Plotly.react('fdChartGeo', [{
        type: 'bar', orientation: 'h',
        y: geo.locations.map((l) => String(l).slice(0, 36)),
        x: geo.intensity,
        marker: { color: colors, opacity: 0.9 },
        hovertemplate: '<b>%{y}</b><br>Intensidad: %{x:.1f}<extra></extra>',
    }], fdLayout({
        height: Math.max(280, geo.locations.length * 28),
        margin: { t: 12, b: 40, l: 8, r: 40 },
        xaxis: { title: 'Índice de riesgo', gridcolor: C.grid },
        yaxis: { automargin: true },
    }), fdCfg());
}

function plotWaterfall(wf) {
    const C = fdColors();
    if (!wf?.steps?.length || typeof Plotly === 'undefined') return;
    const labels = wf.steps.map((s) => s.label);
    const measures = wf.steps.map(() => 'relative');
    const values = wf.steps.map((s) => s.value);
    labels.push('Score final');
    measures.push('total');
    values.push(wf.final_score || 0);
    Plotly.react('fdChartWaterfall', [{
        type: 'waterfall', orientation: 'v',
        x: labels, y: values, measure: measures,
        connector: { line: { color: 'rgba(148,163,184,0.3)' } },
        increasing: { marker: { color: C.red } },
        decreasing: { marker: { color: C.green } },
        totals: { marker: { color: C.cyan } },
    }], fdLayout({ height: 300, margin: { t: 12, b: 80, l: 48, r: 16 }, xaxis: { tickangle: -25 } }), fdCfg());
}

function plotNetwork(net) {
    const C = fdColors();
    if (!net?.nodes?.length || typeof Plotly === 'undefined') return;
    const idIdx = {};
    net.nodes.forEach((n, i) => { idIdx[n.id] = i; });
    const n = net.nodes.length;
    const x = net.nodes.map((_, i) => Math.cos((i / n) * 2 * Math.PI));
    const y = net.nodes.map((_, i) => Math.sin((i / n) * 2 * Math.PI));
    if (net.nodes[0]?.id === 'hub') { x[0] = 0; y[0] = 0; }
    const edgeX = [], edgeY = [];
    (net.edges || []).forEach((e) => {
        const a = idIdx[e.source], b = idIdx[e.target];
        if (a == null || b == null) return;
        edgeX.push(x[a], x[b], null);
        edgeY.push(y[a], y[b], null);
    });
    const sizes = net.nodes.map((node) => 12 + (node.size || 10));
    const colors = net.nodes.map((node) =>
        node.type === 'hub' ? C.cyan : node.type === 'proveedor' ? C.red : C.blue);
    Plotly.react('fdChartNetwork', [
        { x: edgeX, y: edgeY, mode: 'lines', line: { color: 'rgba(34,211,238,0.25)', width: 1 }, hoverinfo: 'skip' },
        { x, y, mode: 'markers+text', text: net.nodes.map((nd) => nd.label), textposition: 'top center',
            textfont: { size: 8, color: C.muted }, marker: { size: sizes, color: colors, line: { width: 1, color: '#fff' } },
            hovertemplate: '%{text}<extra></extra>' },
    ], fdLayout({
        height: 320, margin: { t: 24, b: 24, l: 24, r: 24 },
        xaxis: { visible: false }, yaxis: { visible: false }, showlegend: false,
    }), fdCfg());
}

function plotGauge(tier, score) {
    const C = fdColors();
    const color = tier?.color || C.cyan;
    const val = Number(score) || 0;
    if (typeof Plotly === 'undefined') return;
    Plotly.react('fdChartGauge', [{
        type: 'indicator', mode: 'gauge+number',
        value: val,
        number: { suffix: '/100', font: { size: 28, color: C.text } },
        title: { text: tier?.label || 'Riesgo', font: { size: 12, color: C.muted } },
        gauge: {
            axis: { range: [0, 100] },
            bar: { color },
            steps: [
                { range: [0, 40], color: 'rgba(0,196,140,0.25)' },
                { range: [40, 75], color: 'rgba(245,183,0,0.25)' },
                { range: [75, 100], color: 'rgba(255,77,79,0.3)' },
            ],
        },
    }], fdLayout({ height: 220, margin: { t: 36, b: 16, l: 24, r: 24 } }), fdCfg());
}

function semBadge(sem) {
    const s = String(sem || '').toLowerCase();
    const cls = s.startsWith('roj') ? 'rojo' : s.startsWith('amar') ? 'amarillo' : 'verde';
    return `<span class="fraudia-badge ${cls}">${escapeHtml(sem)}</span>`;
}

function renderCasesTable(cases) {
    const body = document.getElementById('fraudiaCasesBody');
    const cnt = document.getElementById('fdCaseCount');
    if (!body) return;
    let rows = [...(cases || [])];
    const { key, dir } = fraudiaDash.tableSort;
    rows.sort((a, b) => {
        const av = a[key], bv = b[key];
        if (typeof av === 'number' && typeof bv === 'number') return dir === 'asc' ? av - bv : bv - av;
        return dir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
    if (cnt) cnt.textContent = rows.length.toLocaleString() + ' casos';
    body.innerHTML = rows.map((c) => `
        <tr data-id="${escapeHtml(c.id_siniestro)}">
            <td><strong style="color:var(--fd-cyan)">${escapeHtml(c.id_siniestro)}</strong></td>
            <td>${c.score}</td>
            <td>${semBadge(c.semaforo)}</td>
            <td>${c.prob_fraude != null ? c.prob_fraude + '%' : '—'}</td>
            <td>${c.anomaly_score != null ? c.anomaly_score + '%' : '—'}</td>
            <td title="${escapeHtml(c.alerta_resumen || '')}">${c.alertas_count || 0}</td>
            <td>$${Number(c.monto_reclamado || 0).toLocaleString('es-CO', { maximumFractionDigits: 0 })}</td>
            <td>${escapeHtml(c.ciudad || '—')}</td>
            <td>${escapeHtml(String(c.proveedor || '—').slice(0, 24))}</td>
            <td>${escapeHtml(c.estado || '—')}</td>
            <td>
                <button type="button" class="fraudia-btn-xs" data-action="view" data-id="${escapeHtml(c.id_siniestro)}">Análisis</button>
                <button type="button" class="fraudia-btn-xs" data-action="xai" data-id="${escapeHtml(c.id_siniestro)}">IA</button>
            </td>
        </tr>
    `).join('') || '<tr><td colspan="11" style="color:var(--text-muted);padding:1rem;">Sin casos en el filtro actual.</td></tr>';

    body.querySelectorAll('[data-action]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const id = btn.dataset.id;
            if (btn.dataset.action === 'view' && typeof viewCase === 'function') viewCase(id);
            else openExplainDrawer(id);
        });
    });
}

async function openExplainDrawer(caseId) {
    const drawer = document.getElementById('fraudiaDrawer');
    const title = document.getElementById('fraudiaDrawerTitle');
    const body = document.getElementById('fraudiaDrawerBody');
    if (!drawer || !body) return;
    if (title) title.textContent = caseId;
    body.innerHTML = '<p style="color:var(--text-muted);">Cargando explicabilidad…</p>';
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    try {
        const resp = await fetch(`/api/case/${encodeURIComponent(caseId)}`, typeof withFraudiaSessionHeaders === 'function' ? withFraudiaSessionHeaders() : {});
        const data = await resp.json();
        if (!resp.ok || data.error) throw new Error(data.error || 'Error');
        const rows = [
            ['Score híbrido', (data.score_hibrido || 0).toFixed(1)],
            ['Score reglas', (data.score_reglas || 0).toFixed(1)],
            ['Prob. IA fraude', data.ml_fraud_probability != null ? (data.ml_fraud_probability * 100).toFixed(1) + '%' : '—'],
            ['Anomaly score', data.anomaly_score != null ? (data.anomaly_score * 100).toFixed(1) + '%' : '—'],
            ['Semáforo', data.semaforo || '—'],
            ['Monto', '$' + Number(data.monto_reclamado || 0).toLocaleString()],
            ['Estado', data.estado || '—'],
        ];
        body.innerHTML = rows.map(([k, v]) =>
            `<div class="fraudia-xai-row"><span>${escapeHtml(k)}</span><strong>${escapeHtml(String(v))}</strong></div>`
        ).join('') + (data.alertas_reglas
            ? `<div style="margin-top:1rem;font-size:0.78rem;"><strong>Reglas:</strong><br>${escapeHtml(data.alertas_reglas)}</div>` : '');
    } catch (e) {
        body.innerHTML = `<p style="color:var(--fd-red);">${escapeHtml(e.message)}</p>`;
    }
}

function closeDrawer() {
    const drawer = document.getElementById('fraudiaDrawer');
    if (drawer) {
        drawer.classList.remove('open');
        drawer.setAttribute('aria-hidden', 'true');
    }
}

function renderFraudia(fd) {
    if (!fd) return;
    renderKpis(fd.kpis);
    renderInsights(fd.insights);
    renderOps(fd.ops);
    plotDonut(fd.donut);
    plotTemporal(fd, fraudiaDash.temporalFreq);
    plotRadar(fd.radar_ia);
    plotGeo(fd.geo);
    plotWaterfall(fd.waterfall);
    plotNetwork(fd.network);
    plotGauge(fd.global_tier, fd.formulas?.score_promedio);
    renderCasesTable(fd.cases);
}

function buildQuery() {
    const f = fraudiaDash.filters;
    const p = new URLSearchParams();
    Object.entries(f).forEach(([k, v]) => { if (v && v !== 'all') p.set(k, v); });
    return p.toString();
}

function syncFiltersFromUi() {
    fraudiaDash.filters.search = document.getElementById('fdSearch')?.value.trim() || '';
    fraudiaDash.filters.semaforo = document.getElementById('fdFilterSem')?.value || 'all';
    fraudiaDash.filters.ramo = document.getElementById('fdFilterRamo')?.value || 'all';
}

function populateFilters(opts) {
    const ramo = document.getElementById('fdFilterRamo');
    if (ramo && opts.ramos) {
        ramo.innerHTML = '<option value="all">Todos los ramos</option>' +
            opts.ramos.map((r) => `<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>`).join('');
    }
}

function renderBanner(data) {
    const el = document.getElementById('fraudiaBanner');
    if (!el) return;
    const total = data.total || 0;
    const src = data.source_total_siniestros || data.total_unfiltered || total;
    if (data.filtered) {
        el.innerHTML = `Mostrando <strong>${total.toLocaleString()}</strong> de ${(data.total_unfiltered || src).toLocaleString()} siniestros analizados.`;
    } else {
        el.innerHTML = `Universo analizado: <strong>${total.toLocaleString()}</strong> siniestros · FraudIA listo.`;
    }
}

async function refreshDashboard() {
    const headers = {};
    try {
        const sid = sessionStorage.getItem('fxecure_session_id') || sessionStorage.getItem('fraudia_session_id');
        if (sid) {
            headers['X-FXecure-Session'] = sid;
            headers['X-FraudIA-Session'] = sid;
        }
    } catch (e) { /* ignore */ }
    const qs = buildQuery();
    const resp = await fetch('/api/dashboard-data' + (qs ? '?' + qs : ''), typeof withFraudiaSessionHeaders === 'function' ? withFraudiaSessionHeaders({ headers }) : { headers });
    const data = await resp.json();
    if (!resp.ok || data.error) throw new Error(data.error || 'Error al cargar datos');
    fraudiaDash.lastData = data;
    const fd = data.fraudia || {};
    if (data.model_metrics && fd.ops) {
        const m = data.model_metrics;
        fd.ops.auc_roc = m.auc_roc || m.cv_auc_mean;
        fd.ops.precision_pct = m.precision_fraude;
    }
    renderBanner(data);
    renderFraudia(fd);
    const upd = document.getElementById('fdUpdated');
    if (upd) upd.textContent = new Date().toLocaleString('es-EC');
    scheduleResize();
}

function scheduleResize() {
    requestAnimationFrame(() => {
        [80, 400].forEach((ms) => setTimeout(resizeCharts, ms));
    });
}

function resizeCharts() {
    if (typeof Plotly === 'undefined') return;
    FD_CHARTS.forEach((id) => {
        const el = document.getElementById(id);
        if (el?.querySelector('.plotly')) try { Plotly.Plots.resize(el); } catch (e) { /* ignore */ }
    });
}

function bindEvents() {
    document.getElementById('fdApplyFilters')?.addEventListener('click', () => {
        syncFiltersFromUi();
        refreshDashboard().catch((e) => alert(e.message));
    });
    document.getElementById('fdResetFilters')?.addEventListener('click', () => {
        fraudiaDash.filters = { semaforo: 'all', ramo: 'all', cobertura: 'all', sucursal: 'all', estado: 'all', search: '', score_min: '', score_max: '', fecha_desde: '', fecha_hasta: '' };
        const s = document.getElementById('fdSearch');
        if (s) s.value = '';
        refreshDashboard().catch((e) => alert(e.message));
    });
    document.getElementById('fraudiaDrawerClose')?.addEventListener('click', closeDrawer);
    document.querySelectorAll('.fraudia-temporal-tabs button').forEach((btn) => {
        btn.addEventListener('click', () => {
            fraudiaDash.temporalFreq = btn.dataset.freq || 'month';
            document.querySelectorAll('.fraudia-temporal-tabs button').forEach((b) => b.classList.toggle('active', b === btn));
            if (fraudiaDash.lastData?.fraudia) plotTemporal(fraudiaDash.lastData.fraudia, fraudiaDash.temporalFreq);
        });
    });
    document.querySelectorAll('#fraudiaCasesTable th[data-sort]').forEach((th) => {
        th.style.cursor = 'pointer';
        th.addEventListener('click', () => {
            const key = th.dataset.sort;
            if (fraudiaDash.tableSort.key === key) {
                fraudiaDash.tableSort.dir = fraudiaDash.tableSort.dir === 'asc' ? 'desc' : 'asc';
            } else {
                fraudiaDash.tableSort = { key, dir: 'desc' };
            }
            if (fraudiaDash.lastData?.fraudia) renderCasesTable(fraudiaDash.lastData.fraudia.cases);
        });
    });
}

async function initDashboard() {
    const container = document.getElementById('dashboardContent');
    if (!container) return;
    container.innerHTML = showSkeleton();
    try {
        if (typeof bootstrapSessionFromServer === 'function') await bootstrapSessionFromServer();
        const headers = {};
        try {
            const sid = sessionStorage.getItem('fxecure_session_id') || sessionStorage.getItem('fraudia_session_id');
            if (sid) { headers['X-FXecure-Session'] = sid; headers['X-FraudIA-Session'] = sid; }
        } catch (e) { /* ignore */ }
        const optResp = await fetch('/api/dashboard-filters', typeof withFraudiaSessionHeaders === 'function' ? withFraudiaSessionHeaders({ headers }) : { headers });
        const opts = await optResp.json();
        if (!optResp.ok || opts.error) {
            container.innerHTML = `<div class="alert alert-warning">${escapeHtml(opts.error || 'Ejecute el análisis desde Carga de datos.')}</div>`;
            return;
        }
        fraudiaDash.options = opts;
        container.innerHTML = buildFraudiaShell();
        bindEvents();
        populateFilters(opts);
        initParticles();
        fraudiaDash.initialized = true;
        await refreshDashboard();
    } catch (e) {
        console.error('initDashboard:', e);
        container.innerHTML = `<div class="alert alert-danger">Error al cargar FraudIA: ${escapeHtml(e.message)}. Recargue con Ctrl+F5.</div>`;
    }
}

function loadDashboard() { return initDashboard(); }

if (typeof window !== 'undefined') {
    window.initDashboard = initDashboard;
    window.loadDashboard = loadDashboard;
    window.scheduleDashboardChartsResize = scheduleResize;
    window.resizeDashboardCharts = resizeCharts;
}
