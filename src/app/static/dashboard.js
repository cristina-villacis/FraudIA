/**
 * Dashboard Ejecutivo de Riesgo — filtros dinámicos e interactividad Plotly.
 */
const dashboardState = {
    initialized: false,
    options: null,
    filterDefaults: null,
    lastData: null,
    metricsAuc: '--',
    refreshTimer: null,
    filters: {
        semaforo: 'all',
        ramo: 'all',
        cobertura: 'all',
        sucursal: 'all',
        estado: 'all',
        search: '',
        score_min: '',
        score_max: '',
        fecha_desde: '',
        fecha_hasta: '',
    },
};

function getAppTheme() {
    return document.documentElement.getAttribute('data-theme') || 'dark';
}

function fmtChartNum(n) {
    const v = Number(n);
    if (!Number.isFinite(v) || v <= 0) return '';
    return v.toLocaleString('es-CO');
}

function dashBarAxis(C) {
    return {
        gridcolor: C.grid,
        tickfont: { size: 10, color: C.muted },
        automargin: true,
        zeroline: false,
    };
}

/** Barras apiladas por semáforo con etiqueta en cada segmento y total arriba. */
function buildStackedRiskTraces(xLabels, verdes, amarillos, rojos, C, names) {
    const totals = xLabels.map((_, i) =>
        (Number(verdes[i]) || 0) + (Number(amarillos[i]) || 0) + (Number(rojos[i]) || 0)
    );
    const segFont = { size: 10, color: '#ffffff', family: 'Inter, sans-serif' };
    const totalFont = { size: 11, color: C.text, family: 'Inter, sans-serif' };
    return [
        {
            x: xLabels, y: verdes, name: names[0], type: 'bar',
            marker: { color: C.green, opacity: 0.92 },
            text: verdes.map(fmtChartNum), textposition: 'inside', textfont: segFont,
        },
        {
            x: xLabels, y: amarillos, name: names[1], type: 'bar',
            marker: { color: C.yellow, opacity: 0.92 },
            text: amarillos.map(fmtChartNum), textposition: 'inside', textfont: segFont,
        },
        {
            x: xLabels, y: rojos, name: names[2], type: 'bar',
            marker: { color: C.red, opacity: 0.92 },
            text: rojos.map((v, i) => fmtChartNum(v) || fmtChartNum(totals[i])),
            textposition: 'outside',
            textfont: totalFont,
            hovertemplate: '%{x}<br>Total: %{customdata}<extra></extra>',
            customdata: totals.map((t) => t.toLocaleString('es-CO')),
        },
    ];
}

function safePlotlyReact(targetId, data, layout, config) {
    if (typeof Plotly === 'undefined') {
        console.error('Plotly no está cargado; revise la conexión al CDN.');
        return false;
    }
    const el = document.getElementById(targetId);
    if (!el) return false;
    try {
        Plotly.react(targetId, data, layout, config);
        return true;
    } catch (err) {
        console.error('Plotly chart error:', targetId, err);
        return false;
    }
}

/** Plotly calcula mal el tamaño si el contenedor estaba oculto (display:none). */
function scheduleDashboardChartsResize() {
    requestAnimationFrame(() => {
        setTimeout(() => resizeDashboardCharts(), 80);
        setTimeout(() => resizeDashboardCharts(), 350);
    });
}

function dashStackedLayout(PL, C, opts = {}) {
    return {
        ...PL,
        barmode: 'stack',
        bargap: 0.28,
        height: opts.height || 300,
        margin: { t: 20, b: opts.bottom || 72, l: 56, r: 16, autoexpand: true },
        xaxis: {
            ...dashBarAxis(C),
            tickangle: opts.tickangle ?? -30,
            type: 'category',
            title: opts.xTitle ? { text: opts.xTitle, font: { size: 11, color: C.muted } } : undefined,
        },
        yaxis: {
            ...dashBarAxis(C),
            title: { text: opts.yTitle || 'Siniestros', font: { size: 11, color: C.muted } },
        },
        showlegend: opts.showlegend !== false,
        legend: opts.showlegend !== false ? {
            orientation: 'h',
            y: opts.legendY ?? -0.28,
            x: 0,
            font: { size: 10, color: C.muted },
        } : undefined,
    };
}

const FILTER_LABELS = {
    semaforo: 'Semáforo',
    ramo: 'Ramo',
    cobertura: 'Cobertura',
    sucursal: 'Sucursal',
    estado: 'Estado',
    search: 'Búsqueda',
    score_min: 'Score mín.',
    score_max: 'Score máx.',
    fecha_desde: 'Desde',
    fecha_hasta: 'Hasta',
};

function setFilterDefaultsFromOptions(opts) {
    dashboardState.filterDefaults = {
        score_min: String(opts?.score_min ?? 0),
        score_max: String(opts?.score_max ?? 100),
        fecha_desde: opts?.fecha_min || '',
        fecha_hasta: opts?.fecha_max || '',
    };
}

function emptyDashboardFilters() {
    return {
        semaforo: 'all',
        ramo: 'all',
        cobertura: 'all',
        sucursal: 'all',
        estado: 'all',
        search: '',
        score_min: '',
        score_max: '',
        fecha_desde: '',
        fecha_hasta: '',
    };
}

function isFilterActive(key, value) {
    const v = value == null ? '' : String(value).trim();
    const d = dashboardState.filterDefaults;
    if (['semaforo', 'ramo', 'cobertura', 'sucursal', 'estado'].includes(key)) {
        return v !== '' && v !== 'all';
    }
    if (key === 'search') return v !== '';
    if (key === 'score_min' && d) return v !== '' && v !== String(d.score_min);
    if (key === 'score_max' && d) return v !== '' && v !== String(d.score_max);
    if (key === 'fecha_desde' && d) return v !== '' && v !== String(d.fecha_desde);
    if (key === 'fecha_hasta' && d) return v !== '' && v !== String(d.fecha_hasta);
    return false;
}

function getActiveFiltersForUI() {
    const f = dashboardState.filters;
    const active = [];
    Object.keys(FILTER_LABELS).forEach(key => {
        if (isFilterActive(key, f[key])) {
            active.push({ key, label: FILTER_LABELS[key], value: String(f[key]) });
        }
    });
    return active;
}

function buildDashboardQuery() {
    const f = dashboardState.filters;
    const p = new URLSearchParams();
    Object.keys(FILTER_LABELS).forEach(key => {
        if (isFilterActive(key, f[key])) p.set(key, f[key]);
    });
    return p.toString();
}

function scheduleDashboardRefresh(delay = 280) {
    clearTimeout(dashboardState.refreshTimer);
    dashboardState.refreshTimer = setTimeout(refreshDashboard, delay);
}

function syncFiltersFromForm() {
    const g = (id) => document.getElementById(id);
    if (!g('filterRamo')) return;
    const d = dashboardState.filterDefaults;
    dashboardState.filters.ramo = g('filterRamo').value;
    dashboardState.filters.cobertura = g('filterCobertura').value;
    dashboardState.filters.sucursal = g('filterSucursal').value;
    dashboardState.filters.estado = g('filterEstado').value;
    dashboardState.filters.search = g('filterSearch').value.trim();
    dashboardState.filters.fecha_desde = g('filterFechaDesde').value;
    dashboardState.filters.fecha_hasta = g('filterFechaHasta').value;
    const smin = g('filterScoreMin').value;
    const smax = g('filterScoreMax').value;
    dashboardState.filters.score_min = (d && String(smin) === String(d.score_min)) ? '' : smin;
    dashboardState.filters.score_max = (d && String(smax) === String(d.score_max)) ? '' : smax;
}

function updateSemaforoPills() {
    const sem = dashboardState.filters.semaforo;
    document.querySelectorAll('.semaforo-pill').forEach(btn => {
        const v = btn.dataset.semaforo;
        btn.classList.toggle('active', sem === v || (sem === 'all' && v === 'all'));
    });
    document.querySelectorAll('.semaforo-legend-item.clickable').forEach(el => {
        const s = el.dataset.semaforo;
        el.classList.toggle('active-filter', sem === s);
    });
}

function resetFilterControlUI(key) {
    const d = dashboardState.filterDefaults || {};
    const elMap = {
        semaforo: 'filterSemaforo',
        ramo: 'filterRamo',
        cobertura: 'filterCobertura',
        sucursal: 'filterSucursal',
        estado: 'filterEstado',
        search: 'filterSearch',
        fecha_desde: 'filterFechaDesde',
        fecha_hasta: 'filterFechaHasta',
        score_min: 'filterScoreMin',
        score_max: 'filterScoreMax',
    };
    if (elMap[key]) {
        const el = document.getElementById(elMap[key]);
        if (el) {
            if (key === 'search') el.value = '';
            else if (['semaforo', 'ramo', 'cobertura', 'sucursal', 'estado'].includes(key)) el.value = 'all';
            else if (key === 'fecha_desde' || key === 'fecha_hasta') el.value = '';
        }
    }
    if (key === 'score_min') {
        const v = d.score_min ?? '0';
        ['filterScoreMin', 'filterScoreMinRange'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = v;
        });
        const lbl = document.getElementById('scoreMinLabel');
        if (lbl) lbl.textContent = v;
    }
    if (key === 'score_max') {
        const v = d.score_max ?? '100';
        ['filterScoreMax', 'filterScoreMaxRange'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = v;
        });
        const lbl = document.getElementById('scoreMaxLabel');
        if (lbl) lbl.textContent = v;
    }
}

function setDashboardFilter(key, value, refresh = true) {
    dashboardState.filters[key] = value;
    const elMap = {
        semaforo: 'filterSemaforo',
        ramo: 'filterRamo',
        cobertura: 'filterCobertura',
        sucursal: 'filterSucursal',
        estado: 'filterEstado',
        search: 'filterSearch',
        fecha_desde: 'filterFechaDesde',
        fecha_hasta: 'filterFechaHasta',
        score_min: 'filterScoreMin',
        score_max: 'filterScoreMax',
    };
    if (elMap[key]) {
        const el = document.getElementById(elMap[key]);
        if (el) el.value = (value === 'all' || value === '') ? (key === 'search' ? '' : 'all') : value;
    }
    if (key === 'score_min' || key === 'score_max') {
        const r = document.getElementById(key === 'score_min' ? 'filterScoreMinRange' : 'filterScoreMaxRange');
        const num = document.getElementById(key === 'score_min' ? 'filterScoreMin' : 'filterScoreMax');
        const lbl = document.getElementById(key === 'score_min' ? 'scoreMinLabel' : 'scoreMaxLabel');
        if (r) r.value = value;
        if (num) num.value = value;
        if (lbl) lbl.textContent = value;
    }
    updateSemaforoPills();
    updateFilterChips();
    if (refresh) scheduleDashboardRefresh(80);
}

function removeDashboardFilter(key) {
    if (['semaforo', 'ramo', 'cobertura', 'sucursal', 'estado'].includes(key)) {
        dashboardState.filters[key] = 'all';
    } else {
        dashboardState.filters[key] = '';
    }
    resetFilterControlUI(key);
    updateSemaforoPills();
    updateFilterChips();
    refreshDashboard();
}

function clearDashboardFilters() {
    dashboardState.filters = emptyDashboardFilters();
    populateFilterControls(dashboardState.options);
    updateSemaforoPills();
    updateFilterChips();
    refreshDashboard();
}

function populateFilterControls(opts) {
    const fill = (id, items, filterKey) => {
        const sel = document.getElementById(id);
        if (!sel) return;
        sel.innerHTML = '<option value="all">Todos</option>' +
            (items || []).map(v => `<option value="${v}">${v}</option>`).join('');
        const fv = dashboardState.filters[filterKey];
        sel.value = (fv && fv !== 'all') ? fv : 'all';
    };
    fill('filterRamo', opts.ramos, 'ramo');
    fill('filterCobertura', opts.coberturas, 'cobertura');
    fill('filterSucursal', opts.sucursales, 'sucursal');
    fill('filterEstado', opts.estados, 'estado');
    const fs = document.getElementById('filterSemaforo');
    if (fs) fs.value = dashboardState.filters.semaforo || 'all';

    const d = dashboardState.filterDefaults || {
        score_min: String(opts.score_min ?? 0),
        score_max: String(opts.score_max ?? 100),
        fecha_desde: opts.fecha_min || '',
        fecha_hasta: opts.fecha_max || '',
    };

    const fd = document.getElementById('filterFechaDesde');
    const fh = document.getElementById('filterFechaHasta');
    if (fd) {
        fd.min = opts.fecha_min || '';
        fd.max = opts.fecha_max || '';
        fd.value = isFilterActive('fecha_desde', dashboardState.filters.fecha_desde)
            ? dashboardState.filters.fecha_desde : '';
    }
    if (fh) {
        fh.min = opts.fecha_min || '';
        fh.max = opts.fecha_max || '';
        fh.value = isFilterActive('fecha_hasta', dashboardState.filters.fecha_hasta)
            ? dashboardState.filters.fecha_hasta : '';
    }

    const smin = document.getElementById('filterScoreMin');
    const smax = document.getElementById('filterScoreMax');
    const rmin = document.getElementById('filterScoreMinRange');
    const rmax = document.getElementById('filterScoreMaxRange');
    if (smin && smax) {
        const uiMin = isFilterActive('score_min', dashboardState.filters.score_min) ? dashboardState.filters.score_min : d.score_min;
        const uiMax = isFilterActive('score_max', dashboardState.filters.score_max) ? dashboardState.filters.score_max : d.score_max;
        smin.min = smax.min = rmin.min = rmax.min = opts.score_min;
        smin.max = smax.max = rmin.max = rmax.max = opts.score_max;
        smin.value = uiMin;
        smax.value = uiMax;
        if (rmin) rmin.value = uiMin;
        if (rmax) rmax.value = uiMax;
        const lblMin = document.getElementById('scoreMinLabel');
        const lblMax = document.getElementById('scoreMaxLabel');
        if (lblMin) lblMin.textContent = uiMin;
        if (lblMax) lblMax.textContent = uiMax;
    }
    const searchEl = document.getElementById('filterSearch');
    if (searchEl) searchEl.value = dashboardState.filters.search || '';
}

function buildDashboardShell() {
    return `
        <div class="dash-soc-title">
            <div>
                <h2>Panel de control de riesgo</h2>
                <div class="dash-soc-meta">
                    <span>Estado del análisis: <strong id="dashIaStatus">Activo</strong></span>
                    <span>Precisión del modelo: <strong id="kpiAuc">—</strong></span>
                    <span>Actualizado: <strong id="dashNow">—</strong></span>
                </div>
            </div>
            <span class="dash-panel-badge">Vista ejecutiva</span>
        </div>

        <div class="dash-soc-kpis">
            <div class="dash-kpi-card">
                <div class="dash-kpi-label">Total siniestros</div>
                <div class="dash-kpi-value" id="kpiTotal" style="color:var(--cyan);">—</div>
                <div class="dash-kpi-sub" id="kpiTotalSub">Analizados</div>
            </div>
            <div class="dash-kpi-card accent-red">
                <div class="dash-kpi-label">Casos críticos</div>
                <div class="dash-kpi-value" id="kpiRojo" style="color:var(--red);">—</div>
                <div class="dash-kpi-sub" id="kpiRojoPct">—</div>
                <span class="dash-kpi-trend up" id="kpiCriticalTrend">▲ Prioridad alta</span>
            </div>
            <div class="dash-kpi-card">
                <div class="dash-kpi-label">Riesgo promedio</div>
                <div class="dash-kpi-value" id="kpiScore">—</div>
                <div class="dash-kpi-sub">Score híbrido / 100</div>
            </div>
            <div class="dash-kpi-card accent-yellow">
                <div class="dash-kpi-label">Monto comprometido</div>
                <div class="dash-kpi-value" id="kpiMonto" style="color:var(--yellow);">—</div>
                <div class="dash-kpi-sub">Exposición en filtro</div>
            </div>
            <div class="dash-kpi-card accent-green">
                <div class="dash-kpi-label">Alertas activas</div>
                <div class="dash-kpi-value" id="kpiAlerts" style="color:var(--green);">—</div>
                <div class="dash-kpi-sub" id="kpiProbFraude">Prob. fraude —</div>
            </div>
        </div>

        <details class="dash-panel dash-filters-panel">
            <summary>▸ Filtros de exploración (también puede hacer clic en los gráficos)</summary>
            <div class="dash-filters-body">
                <div class="card dashboard-toolbar" style="margin:0;border:none;background:transparent;box-shadow:none;">
                    <div style="display:flex;justify-content:flex-end;gap:0.5rem;margin-bottom:0.75rem;">
                        <button type="button" class="btn btn-primary" id="btnApplyFilters" style="padding:0.4rem 1rem;font-size:0.8rem;">Aplicar</button>
                        <button type="button" class="btn btn-secondary" id="btnResetFilters" style="padding:0.4rem 1rem;font-size:0.8rem;">Limpiar</button>
                    </div>
                    <div class="dashboard-toolbar-grid">
                        <div class="dashboard-filter"><label>Semáforo</label>
                            <select id="filterSemaforo"><option value="all">Todos</option><option value="Verde">Verde (0-40)</option><option value="Amarillo">Amarillo (41-75)</option><option value="Rojo">Rojo (76-100)</option></select>
                        </div>
                        <div class="dashboard-filter"><label>Ramo</label><select id="filterRamo"></select></div>
                        <div class="dashboard-filter"><label>Cobertura</label><select id="filterCobertura"></select></div>
                        <div class="dashboard-filter"><label>Sucursal</label><select id="filterSucursal"></select></div>
                        <div class="dashboard-filter"><label>Estado</label><select id="filterEstado"></select></div>
                        <div class="dashboard-filter"><label>ID Siniestro</label><input type="text" id="filterSearch" placeholder="Buscar SIN-..."></div>
                        <div class="dashboard-filter"><label>Desde</label><input type="date" id="filterFechaDesde"></div>
                        <div class="dashboard-filter"><label>Hasta</label><input type="date" id="filterFechaHasta"></div>
                        <div class="dashboard-filter score-range-wrap"><label>Score mín. <span id="scoreMinLabel">0</span></label>
                            <input type="range" id="filterScoreMinRange"><input type="number" id="filterScoreMin" min="0" max="100" style="margin-top:0.35rem;">
                        </div>
                        <div class="dashboard-filter score-range-wrap"><label>Score máx. <span id="scoreMaxLabel">100</span></label>
                            <input type="range" id="filterScoreMaxRange"><input type="number" id="filterScoreMax" min="0" max="100" style="margin-top:0.35rem;">
                        </div>
                    </div>
                    <div class="dashboard-semaforo-pills">
                        <button type="button" class="semaforo-pill active" data-semaforo="all">Todos</button>
                        <button type="button" class="semaforo-pill pill-verde" data-semaforo="Verde">Verde</button>
                        <button type="button" class="semaforo-pill pill-amarillo" data-semaforo="Amarillo">Amarillo</button>
                        <button type="button" class="semaforo-pill pill-rojo" data-semaforo="Rojo">Rojo</button>
                    </div>
                </div>
            </div>
        </details>
        <div id="dashboardChips" class="dashboard-chips"></div>
        <div id="dashboardBanner" class="dashboard-filtered-banner"></div>
        <span id="kpiClasificacion" style="display:none;"></span>

        <section class="dash-charts-section">
            <h3 class="dash-section-title">Gráficos de análisis</h3>
            <p class="dash-chart-help">Puede hacer clic en las barras o sectores para filtrar. Use el botón ✕ en cada gráfico para limpiar el filtro aplicado.</p>
            <div class="dash-layout-duo">
                <div class="dash-panel card-chart">
                    <div class="dash-panel-head">
                        <h3 class="dash-panel-title">Semáforo de riesgo</h3>
                        <button type="button" class="chart-reset-btn" data-reset-scope="semaforo" title="Limpiar">✕</button>
                    </div>
                    <div class="donut-chart-wrap"><div id="chartSemaforo" class="chart-area chart-area-donut"></div></div>
                </div>
                <div class="dash-panel card-chart">
                    <div class="dash-panel-head">
                        <h3 class="dash-panel-title">Distribución del score</h3>
                        <button type="button" class="chart-reset-btn" data-reset-scope="score" title="Limpiar">✕</button>
                    </div>
                    <div id="chartScores" class="chart-area" style="min-height:240px;"></div>
                </div>
            </div>
            <div class="dash-panel card-chart">
                <div class="dash-panel-head">
                    <h3 class="dash-panel-title">Evolución en el tiempo</h3>
                    <button type="button" class="chart-reset-btn" data-reset-scope="fecha" title="Limpiar">✕</button>
                </div>
                <div id="chartTemporal" class="chart-area" style="min-height:220px;"></div>
            </div>
            <div class="dash-layout-duo">
                <div class="dash-panel card-chart">
                    <div class="dash-panel-head">
                        <h3 class="dash-panel-title">Concentración por sucursal</h3>
                        <button type="button" class="chart-reset-btn" data-reset-scope="all" title="Limpiar">✕</button>
                    </div>
                    <div id="chartGeoOperacion" class="chart-area" style="min-height:260px;"></div>
                </div>
                <div class="dash-panel card-chart">
                    <div class="dash-panel-head">
                        <h3 class="dash-panel-title">Riesgo por ramo y cobertura</h3>
                        <button type="button" class="chart-reset-btn" data-reset-scope="all" title="Limpiar">✕</button>
                    </div>
                    <div id="chartHeatmapRamoRiesgo" class="chart-area" style="min-height:260px;"></div>
                </div>
            </div>
            <div class="dash-panel card-chart">
                <div class="dash-panel-head">
                    <h3 class="dash-panel-title">Comparativo por ramo</h3>
                    <button type="button" class="chart-reset-btn" data-reset-scope="ramo" title="Limpiar">✕</button>
                </div>
                <div id="chartRamo" class="chart-area chart-area-ramo" style="min-height:260px;"></div>
                <div class="chart-legend-below" id="ramoChartLegend" style="margin-top:0.5rem;">
                    <span><i style="background:var(--green);"></i> Bajo</span>
                    <span><i style="background:var(--yellow);"></i> Medio</span>
                    <span><i style="background:var(--red);"></i> Alto</span>
                </div>
            </div>
        </section>

        <div class="dash-panel" style="margin-bottom:1.25rem;">
            <div class="dash-panel-head"><h3 class="dash-panel-title">Ranking proveedores sospechosos</h3></div>
            <div class="dash-table-wrap" style="max-height:300px;">
                <table class="dash-table">
                    <thead><tr><th>Proveedor</th><th>Casos</th><th>Score prom.</th><th>Monto</th><th>Alertas</th></tr></thead>
                    <tbody id="providerRiskTable"></tbody>
                </table>
            </div>
        </div>

        <div class="dash-layout-duo">
            <div class="dash-panel">
                <div class="dash-panel-head"><h3 class="dash-panel-title">Motor de señales</h3></div>
                <div class="dash-table-wrap" style="max-height:280px;">
                    <table class="dash-table">
                        <thead><tr><th>Señal</th><th>Casos</th><th>Severidad</th><th>Acción</th></tr></thead>
                        <tbody id="fraudSignalsTable"></tbody>
                    </table>
                </div>
                <div id="signalCasesPanel" style="margin-top:0.65rem;font-size:0.78rem;color:var(--text-secondary);">
                    Seleccione una señal para ver siniestros relacionados.
                </div>
            </div>
            <div class="dash-panel">
                <div class="dash-panel-head">
                    <h3 class="dash-panel-title">Reglas críticas RF-01..RF-07</h3>
                    <span class="dash-panel-badge" id="dashCriticalCount">0</span>
                </div>
                <div id="criticalRulesPanel"></div>
            </div>
        </div>

        <div class="dash-panel" style="margin-bottom:1.25rem;">
            <div class="dash-panel-head"><h3 class="dash-panel-title">Alertas automáticas · tiempo real</h3></div>
            <div id="alertsPanel" class="alerts-panel"></div>
        </div>
    `;
}

function renderCriticalCasesTable(cases) {
    const tbody = document.getElementById('criticalCasesTable');
    if (!tbody) return;
    if (!cases || !cases.length) {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--text-muted);padding:1.5rem;">Sin casos con los filtros actuales.</td></tr>';
        return;
    }
    tbody.innerHTML = cases.slice(0, 15).map((c) => {
        const sc = Number(c.score_hibrido ?? c.score_reglas ?? 0);
        const sem = c.semaforo_final || c.semaforo_reglas || 'Verde';
        const sevCls = sem === 'Rojo' ? 'rojo' : sem === 'Amarillo' ? 'amarillo' : 'verde';
        const bcls = sem === 'Rojo' ? 'badge-red' : sem === 'Amarillo' ? 'badge-yellow' : 'badge-green';
        const prov = String(c.beneficiario || c.ramo || '—').slice(0, 22);
        const aseg = String(c.id_asegurado || c.cobertura || '—').slice(0, 18);
        const reglas = String(c.alertas_reglas || '').split('|').map((x) => x.trim()).filter(Boolean);
        const reglaShort = reglas[0] ? reglas[0].slice(0, 28) + (reglas[0].length > 28 ? '…' : '') : '—';
        const estado = c.estado || 'En revisión';
        const monto = '$' + Number(c.monto_reclamado || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
        const fillW = Math.min(100, sc);
        const fillColor = sem === 'Rojo' ? 'var(--red)' : sem === 'Amarillo' ? 'var(--yellow)' : 'var(--green)';
        return `<tr class="dash-case-tr" data-case-id="${c.id_siniestro}">
            <td><div class="dash-sev ${sevCls}"></div></td>
            <td><strong style="color:var(--cyan);font-size:0.75rem;">${c.id_siniestro}</strong>
                <div class="dash-score-bar"><div class="dash-score-fill" style="width:${fillW}%;background:${fillColor};"></div></div></td>
            <td><span class="badge ${bcls}">${sc.toFixed(0)}</span></td>
            <td><span class="badge ${bcls}" style="font-size:0.65rem;">${sem}</span></td>
            <td title="${prov}">${prov}</td>
            <td>${aseg}</td>
            <td>${monto}</td>
            <td style="font-size:0.7rem;color:var(--text-muted);max-width:120px;" title="${reglas.join(' | ')}">${reglaShort}</td>
            <td style="font-size:0.7rem;">${estado}</td>
            <td><button type="button" class="dash-btn-analyze" data-analyze="${c.id_siniestro}">Analizar</button></td>
        </tr>`;
    }).join('');
    tbody.querySelectorAll('.dash-case-tr').forEach((row) => {
        row.addEventListener('click', (e) => {
            if (e.target.closest('.dash-btn-analyze')) return;
            if (typeof viewCase === 'function') viewCase(row.dataset.caseId);
        });
    });
    tbody.querySelectorAll('.dash-btn-analyze').forEach((btn) => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (typeof viewCase === 'function') viewCase(btn.dataset.analyze);
        });
    });
}

function bindDashboardEvents() {
    document.getElementById('btnApplyFilters').addEventListener('click', () => {
        syncFiltersFromForm();
        dashboardState.filters.semaforo = document.getElementById('filterSemaforo').value;
        updateSemaforoPills();
        updateFilterChips();
        refreshDashboard();
    });
    document.getElementById('btnResetFilters').addEventListener('click', clearDashboardFilters);

    ['filterRamo', 'filterCobertura', 'filterSucursal', 'filterEstado', 'filterSemaforo'].forEach(id => {
        document.getElementById(id).addEventListener('change', () => {
            syncFiltersFromForm();
            dashboardState.filters.semaforo = document.getElementById('filterSemaforo').value;
            updateSemaforoPills();
            updateFilterChips();
            scheduleDashboardRefresh();
        });
    });

    document.getElementById('filterSearch').addEventListener('input', (e) => {
        dashboardState.filters.search = e.target.value.trim();
        updateFilterChips();
        scheduleDashboardRefresh(450);
    });
    document.getElementById('filterFechaDesde').addEventListener('change', (e) => {
        dashboardState.filters.fecha_desde = e.target.value;
        updateFilterChips();
        scheduleDashboardRefresh();
    });
    document.getElementById('filterFechaHasta').addEventListener('change', (e) => {
        dashboardState.filters.fecha_hasta = e.target.value;
        updateFilterChips();
        scheduleDashboardRefresh();
    });

    const syncScore = (rangeId, numId, key, labelId) => {
        const range = document.getElementById(rangeId);
        const num = document.getElementById(numId);
        const applyScore = (val) => {
            const d = dashboardState.filterDefaults;
            num.value = val;
            range.value = val;
            document.getElementById(labelId).textContent = val;
            if (d && String(val) === String(d[key])) {
                dashboardState.filters[key] = '';
            } else {
                dashboardState.filters[key] = String(val);
            }
            updateFilterChips();
            scheduleDashboardRefresh();
        };
        range.addEventListener('input', () => applyScore(range.value));
        num.addEventListener('change', () => applyScore(num.value));
    };
    syncScore('filterScoreMinRange', 'filterScoreMin', 'score_min', 'scoreMinLabel');
    syncScore('filterScoreMaxRange', 'filterScoreMax', 'score_max', 'scoreMaxLabel');

    document.querySelectorAll('.semaforo-pill').forEach(btn => {
        btn.addEventListener('click', () => {
            const v = btn.dataset.semaforo;
            dashboardState.filters.semaforo = v;
            document.getElementById('filterSemaforo').value = v;
            updateSemaforoPills();
            updateFilterChips();
            scheduleDashboardRefresh(80);
        });
    });

    document.querySelectorAll('.chart-reset-btn').forEach(btn => {
        btn.addEventListener('click', (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            const scope = btn.dataset.resetScope || 'all';
            if (scope === 'all') {
                clearDashboardFilters();
                return;
            }
            if (scope === 'score') {
                removeDashboardFilter('score_min');
                removeDashboardFilter('score_max');
                return;
            }
            if (scope === 'fecha') {
                removeDashboardFilter('fecha_desde');
                removeDashboardFilter('fecha_hasta');
                return;
            }
            removeDashboardFilter(scope);
        });
    });
}

function updateFilterChips() {
    const chips = document.getElementById('dashboardChips');
    if (!chips) return;
    const active = getActiveFiltersForUI();
    if (!active.length) {
        chips.innerHTML = '';
        return;
    }
    chips.innerHTML = active.map(f =>
        `<span class="dashboard-chip" data-chip-key="${f.key}">
            ${f.label}: <strong>${f.value}</strong>
            <button type="button" class="chip-remove" data-chip-key="${f.key}" title="Quitar filtro" aria-label="Quitar filtro">&times;</button>
        </span>`
    ).join('');
    chips.querySelectorAll('.chip-remove').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            removeDashboardFilter(btn.dataset.chipKey);
        });
    });
}

function renderAnomaliesList(cases) {
    const el = document.getElementById('topAnomaliesList');
    if (!cases.length) {
        el.innerHTML = '<div style="color:var(--text-muted);font-size:0.82rem;padding:0.5rem;">Sin casos con los filtros actuales.</div>';
        return;
    }
    el.innerHTML = cases.slice(0, 6).map((c, i) => {
        const sc = c.score_hibrido || c.score_reglas || 0;
        const sem = c.semaforo_final || c.semaforo_reglas || 'Verde';
        const bcls = sem === 'Rojo' ? 'badge-red' : sem === 'Amarillo' ? 'badge-yellow' : 'badge-green';
        return `<div class="anomaly-row-clickable" data-case-id="${c.id_siniestro}" style="display:flex;align-items:center;gap:0.6rem;padding:0.5rem 0.4rem;border-radius:8px;${i % 2 === 0 ? 'background:rgba(0,209,255,0.02);' : ''}">
            <span class="mono" style="font-size:0.7rem;color:var(--text-muted);width:16px;">${i + 1}</span>
            <div style="flex:1;min-width:0;">
                <div style="font-size:0.8rem;font-weight:600;color:var(--text-primary);">${c.id_siniestro}</div>
                <div style="font-size:0.7rem;color:var(--text-muted);">${c.ramo || ''} · $${((c.monto_reclamado || 0) / 1000).toFixed(0)}K</div>
            </div>
            <span class="badge ${bcls}" style="font-size:0.68rem;">${Number(sc).toFixed(0)}</span>
        </div>`;
    }).join('');
    el.querySelectorAll('.anomaly-row-clickable').forEach(row => {
        row.addEventListener('click', () => {
            if (typeof viewCase === 'function') viewCase(row.dataset.caseId);
        });
    });
}

function renderSemaforoLegend(rojo, amarillo, verde, totalSafe, pctOf) {
    const legendEl = document.getElementById('semaforoLegend');
    if (legendEl) legendEl.innerHTML = '';
    updateSemaforoPills();
}

function bindPlotlyDashboardCharts(data) {
    const chartSemaforo = document.getElementById('chartSemaforo');
    const chartRamo = document.getElementById('chartRamo');
    const chartTemporal = document.getElementById('chartTemporal');

    if (chartSemaforo && !chartSemaforo._plotlyClickBound) {
        chartSemaforo.on('plotly_click', (ev) => {
            const label = ev.points[0].label;
            setDashboardFilter('semaforo', label);
            document.getElementById('filterSemaforo').value = label;
        });
        chartSemaforo._plotlyClickBound = true;
    }
    if (chartRamo && !chartRamo._plotlyClickBound) {
        chartRamo.on('plotly_click', (ev) => {
            const ramo = ev.points[0].x;
            setDashboardFilter('ramo', ramo);
        });
        chartRamo._plotlyClickBound = true;
    }
    if (chartTemporal && !chartTemporal._plotlyClickBound) {
        chartTemporal.on('plotly_click', (ev) => {
            const mes = ev.points[0].x;
            if (!mes) return;
            const [y, m] = mes.split('-');
            const lastDay = new Date(y, m, 0).getDate();
            setDashboardFilter('fecha_desde', `${mes}-01`, false);
            setDashboardFilter('fecha_hasta', `${mes}-${String(lastDay).padStart(2, '0')}`, false);
            document.getElementById('filterFechaDesde').value = dashboardState.filters.fecha_desde;
            document.getElementById('filterFechaHasta').value = dashboardState.filters.fecha_hasta;
            refreshDashboard();
        });
        chartTemporal._plotlyClickBound = true;
    }
}

function renderDashboardCharts(data) {
    if (typeof Plotly === 'undefined') {
        console.error('Plotly no está disponible.');
        return;
    }
    const C = getColors(), PL = getPlotlyLayout();
    const theme = getAppTheme();
    const sem = data.semaforo || {};
    const rojo = sem.Rojo || 0, amarillo = sem.Amarillo || 0, verde = sem.Verde || 0;
    const totalSem = rojo + amarillo + verde || data.total || 1;

    if (!document.getElementById('chartSemaforo')) return;

    safePlotlyReact('chartSemaforo', [{
        values: [rojo, amarillo, verde],
        labels: ['Rojo', 'Amarillo', 'Verde'],
        customdata: ['76-100 · Alto', '41-75 · Medio', '0-40 · Bajo'],
        type: 'pie',
        hole: 0.58,
        sort: false,
        direction: 'clockwise',
        marker: { colors: [C.red, C.yellow, C.green], line: { color: C.bgCard || C.bg, width: 3 } },
        textinfo: 'label+value+percent',
        texttemplate: '<b>%{label}</b><br>%{value:,}<br>%{percent}',
        textposition: 'outside',
        textfont: { size: 11, color: C.text, family: 'Inter, sans-serif' },
        hovertemplate: '<b>%{label}</b><br>%{value:,} casos<br>%{percent}<br>%{customdata}<extra></extra>',
        pull: rojo > 0 ? [0.04, 0, 0] : [0, 0, 0],
    }], {
        ...PL,
        showlegend: false,
        height: 300,
        margin: { t: 28, b: 28, l: 48, r: 48, autoexpand: true },
        uniformtext: { minsize: 9, mode: 'hide' },
        annotations: [{
            text: '<b>' + totalSem.toLocaleString() + '</b><br>siniestros',
            showarrow: false,
            font: { size: 14, color: C.text, family: 'Inter, sans-serif' },
            x: 0.5, y: 0.5, xref: 'paper', yref: 'paper', align: 'center',
        }],
    }, { ...PLOTLY_CONFIG, responsive: true });

    const sd = data.score_distribution || {};
    const sdLabels = sd.labels && sd.labels.length ? sd.labels : ['Verde (0-40)', 'Amarillo (41-75)', 'Rojo (76-100)'];
    const sdCounts = sd.counts && sd.counts.length ? sd.counts : [verde, amarillo, rojo];
    const sdColors = sd.colors && sd.colors.length ? sd.colors : [C.green, C.yellow, C.red];
    safePlotlyReact('chartScores', [{
        x: sdLabels,
        y: sdCounts,
        type: 'bar',
        marker: { color: sdColors, line: { width: 0 }, opacity: 0.9 },
        text: sdCounts.map((v) => fmtChartNum(v) || '0'),
        textposition: 'outside',
        textfont: { size: 11, color: C.text, family: 'Inter, sans-serif' },
        hovertemplate: '<b>%{x}</b><br>%{y:,} casos<extra></extra>',
    }], {
        ...PL,
        xaxis: {
            title: { text: 'Nivel de riesgo (score híbrido)', font: { size: 11, color: C.muted } },
            ...dashBarAxis(C),
            tickangle: -20,
        },
        yaxis: { title: { text: 'Cantidad de siniestros', font: { size: 11, color: C.muted } }, ...dashBarAxis(C) },
        height: 280,
        margin: { t: 16, b: 64, l: 52, r: 20, autoexpand: true },
        bargap: 0.35,
    }, { ...PLOTLY_CONFIG, responsive: true });

    const ramos = (data.ramo_data || []).map((r) => r.ramo);
    const ramoVerdes = (data.ramo_data || []).map((r) => r.verdes ?? Math.max(0, (r.count || 0) - (r.rojos || 0) - (r.amarillos || 0)));
    const ramoAmarillos = (data.ramo_data || []).map((r) => r.amarillos ?? 0);
    const ramoRojos = (data.ramo_data || []).map((r) => r.rojos ?? 0);
    safePlotlyReact('chartRamo',
        buildStackedRiskTraces(ramos.length ? ramos : ['Sin datos'], ramoVerdes.length ? ramoVerdes : [0], ramoAmarillos.length ? ramoAmarillos : [0], ramoRojos.length ? ramoRojos : [0], C, ['Bajo', 'Medio', 'Alto']),
        dashStackedLayout(PL, C, { height: 340, bottom: 88, tickangle: -35, showlegend: true, legendY: -0.32 }),
        { ...PLOTLY_CONFIG, responsive: true }
    );

    const months = (data.temporal_risk_data || []).map((t) => t.mes);
    const tVerdes = (data.temporal_risk_data || []).map((t) => t.Verde || 0);
    const tAmarillos = (data.temporal_risk_data || []).map((t) => t.Amarillo || 0);
    const tRojos = (data.temporal_risk_data || []).map((t) => t.Rojo || 0);
    safePlotlyReact('chartTemporal',
        buildStackedRiskTraces(months.length ? months : ['—'], tVerdes.length ? tVerdes : [0], tAmarillos.length ? tAmarillos : [0], tRojos.length ? tRojos : [0], C, ['Bajo (Verde)', 'Medio (Amarillo)', 'Alto (Rojo)']),
        dashStackedLayout(PL, C, {
            height: 300,
            bottom: 64,
            tickangle: -25,
            xTitle: 'Mes',
            yTitle: 'Casos por nivel de riesgo',
            legendY: -0.3,
        }),
        { ...PLOTLY_CONFIG, responsive: true }
    );

    const heat = data.heatmap_ramo_riesgo || {};
    const heatRamos = heat.ramos && heat.ramos.length ? heat.ramos : ['—'];
    const heatSemaforos = heat.semaforos && heat.semaforos.length ? heat.semaforos : ['Verde', 'Amarillo', 'Rojo'];
    const heatZ = heat.z && heat.z.length ? heat.z : [[0, 0, 0]];
    safePlotlyReact('chartHeatmapRamoRiesgo', [{
        z: heatZ,
        x: heatSemaforos,
        y: heatRamos,
        type: 'heatmap',
        colorscale: theme === 'light'
            ? [[0, '#f8fafc'], [0.5, 'rgba(3,105,161,0.35)'], [1, '#0369a1']]
            : [[0, '#0b1220'], [0.5, 'rgba(0,209,255,0.35)'], [1, '#00d1ff']],
        showscale: true,
        colorbar: { title: 'Casos', thickness: 12, len: 0.85, tickfont: { size: 9, color: C.muted } },
        text: heatZ.map((row) => row.map((v) => fmtChartNum(v) || '0')),
        texttemplate: '%{text}',
        textfont: { size: 12, color: '#ffffff', family: 'Inter, sans-serif' },
        hovertemplate: 'Ramo: %{y}<br>Nivel: %{x}<br>Casos: %{z}<extra></extra>',
    }], {
        ...PL,
        margin: { t: 16, b: 48, l: 110, r: 48, autoexpand: true },
        xaxis: { title: { text: 'Nivel de riesgo', font: { size: 11, color: C.muted } }, ...dashBarAxis(C) },
        yaxis: { title: { text: 'Ramo', font: { size: 11, color: C.muted } }, ...dashBarAxis(C), automargin: true },
        height: 300,
    }, { ...PLOTLY_CONFIG, responsive: true });

    const geo = data.geo_risk_data || [];
    const suc = geo.map((g) => g.sucursal);
    const gVerdes = geo.map((g) => g.Verde || 0);
    const gAmarillos = geo.map((g) => g.Amarillo || 0);
    const gRojos = geo.map((g) => g.Rojo || 0);
    safePlotlyReact('chartGeoOperacion',
        buildStackedRiskTraces(suc.length ? suc : ['—'], gVerdes.length ? gVerdes : [0], gAmarillos.length ? gAmarillos : [0], gRojos.length ? gRojos : [0], C, ['Bajo', 'Medio', 'Alto']),
        dashStackedLayout(PL, C, {
            height: 300,
            bottom: 72,
            tickangle: -30,
            xTitle: 'Sucursal',
            yTitle: 'Casos por nivel de riesgo',
            legendY: -0.3,
        }),
        { ...PLOTLY_CONFIG, responsive: true }
    );

    bindPlotlyDashboardCharts(data);
    scheduleDashboardChartsResize();
}

function resizeDashboardCharts() {
    if (typeof Plotly === 'undefined') return;
    const tab = document.getElementById('tab-dashboard');
    if (tab && !tab.classList.contains('active')) return;
    ['chartSemaforo', 'chartScores', 'chartRamo', 'chartTemporal', 'chartHeatmapRamoRiesgo', 'chartGeoOperacion'].forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        try {
            if (el.querySelector('.plotly')) Plotly.Plots.resize(el);
        } catch (e) { /* ignore */ }
    });
}
if (typeof window !== 'undefined') {
    window.scheduleDashboardChartsResize = scheduleDashboardChartsResize;
    window.resizeDashboardCharts = resizeDashboardCharts;
    window.addEventListener('resize', () => {
        if (document.getElementById('dashboardShell')) resizeDashboardCharts();
    });
}

async function loadDashboardMetricsAuc() {
    try {
        const m = await (await fetch('/api/model-metrics')).json();
        if (!m.error) {
            dashboardState.metricsAuc = (m.auc_roc || 0).toFixed(2);
            const aucEl = document.getElementById('kpiAuc');
            if (aucEl) aucEl.textContent = dashboardState.metricsAuc;
        }
    } catch (e) { /* ignore */ }
}

function renderDashboardData(data) {
    const rojo = data.semaforo.Rojo || 0, amarillo = data.semaforo.Amarillo || 0, verde = data.semaforo.Verde || 0;
    const totalSafe = data.total || (rojo + amarillo + verde) || 1;
    const pctOf = (n) => (n / totalSafe * 100).toFixed(1);

    const activeFilters = getActiveFiltersForUI();
    const isFiltered = activeFilters.length > 0;
    const sourceTotal = data.source_total_siniestros || data.total_unfiltered || data.total;
    const analyzedTotal = data.total_unfiltered ?? data.total;
    const countMismatch = sourceTotal > 0 && analyzedTotal < sourceTotal;

    const banner = document.getElementById('dashboardBanner');
    if (isFiltered) {
        banner.innerHTML = `Mostrando <strong>${data.total.toLocaleString()}</strong> de <strong>${analyzedTotal.toLocaleString()}</strong> siniestros analizados (${activeFilters.length} filtro${activeFilters.length > 1 ? 's' : ''} activo${activeFilters.length > 1 ? 's' : ''}).`;
    } else if (countMismatch) {
        banner.innerHTML = `Se cargaron <strong>${sourceTotal.toLocaleString()}</strong> siniestros en el dataset; el motor analizó <strong>${analyzedTotal.toLocaleString()}</strong>. Vuelva a cargar el Excel y ejecute el análisis, o revise advertencias en la pestaña Datos.`;
        banner.classList.add('dashboard-banner-warn');
    } else {
        banner.classList.remove('dashboard-banner-warn');
        banner.innerHTML = `Vista completa: <strong>${analyzedTotal.toLocaleString()}</strong> siniestros analizados (dataset cargado). Use filtros o haga clic en los gráficos para explorar.`;
    }

    const kpiTotalVal = isFiltered ? data.total : analyzedTotal;
    document.getElementById('kpiTotal').textContent = kpiTotalVal.toLocaleString();
    document.getElementById('kpiTotalSub').textContent = isFiltered
        ? `de ${analyzedTotal.toLocaleString()} analizados`
        : (sourceTotal > analyzedTotal ? `de ${sourceTotal.toLocaleString()} cargados` : 'Analizados');
    document.getElementById('kpiRojo').textContent = rojo.toLocaleString();
    document.getElementById('kpiRojoPct').textContent = `${pctOf(rojo)}% del filtro`;
    const ek = data.executive_kpis || {};
    const montoComp = ek.monto_potencial_riesgo ?? data.monto_rojo ?? 0;
    document.getElementById('kpiMonto').textContent = montoComp >= 1e6
        ? '$' + (montoComp / 1e6).toFixed(1) + 'M'
        : '$' + Number(montoComp).toLocaleString(undefined, { maximumFractionDigits: 0 });
    const aucEl = document.getElementById('kpiAuc');
    if (aucEl) aucEl.textContent = dashboardState.metricsAuc;
    document.getElementById('kpiScore').textContent = data.score_promedio;
    const alertCount = (data.signals_summary || []).reduce((a, s) => a + (s.count || 0), 0) || rojo + amarillo;
    const alertsEl = document.getElementById('kpiAlerts');
    if (alertsEl) alertsEl.textContent = alertCount.toLocaleString();
    const now = document.getElementById('dashNow');
    if (now) now.textContent = new Date().toLocaleString('es-EC');
    const iaStatus = document.getElementById('dashIaStatus');
    if (iaStatus) iaStatus.textContent = (dashboardState.metricsAuc !== '--' && Number(dashboardState.metricsAuc) > 0) ? 'Modelo supervisado activo' : 'Reglas + anomalías';

    const setText = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
    setText('kpiProbFraude', 'Prob. fraude ' + (ek.prob_fraude_promedio || 0).toFixed(1) + '%');
    setText(
        'kpiClasificacion',
        `🔴 ${(ek.riesgo_alto || 0).toLocaleString()} · 🟡 ${(ek.riesgo_medio || 0).toLocaleString()} · 🟢 ${(ek.riesgo_bajo || 0).toLocaleString()}`
    );

    updateFilterChips();
    const topCases = data.top_cases || [];
    renderAnomaliesList(topCases);
    renderSemaforoLegend(rojo, amarillo, verde, totalSafe, pctOf);

    const alerts = document.getElementById('alertsPanel');
    alerts.innerHTML = (data.top_cases || []).slice(0, 8).map(c => {
        const alertText = (c.alertas_reglas || '').split('|')[0].trim() || 'Caso de alto riesgo';
        const sem = c.semaforo_final || c.semaforo_reglas || 'Verde';
        const dotCls = sem === 'Rojo' ? 'pulse-dot-red' : sem === 'Amarillo' ? 'pulse-dot-yellow' : 'pulse-dot-green';
        const score = c.score_hibrido ?? c.score_reglas ?? '';
        return `<div class="alert-item anomaly-row-clickable" data-case-id="${c.id_siniestro}">
            <span class="pulse-dot ${dotCls}" style="margin-top:0.35rem;flex-shrink:0;"></span>
            <div class="alert-item-body">
                <div class="alert-item-text">${alertText}</div>
                <div class="alert-item-meta">${c.id_siniestro} · ${c.ramo || '—'}${score !== '' ? ' · Score ' + Number(score).toFixed(0) : ''}</div>
            </div>
        </div>`;
    }).join('') || '<div style="color:var(--text-muted);font-size:0.82rem;padding:0.5rem;">Sin alertas con los filtros actuales.</div>';
    alerts.querySelectorAll('.anomaly-row-clickable').forEach(row => {
        row.addEventListener('click', () => {
            if (typeof viewCase === 'function') viewCase(row.dataset.caseId);
        });
    });

    const signalsEl = document.getElementById('fraudSignalsTable');
    const signalCasesPanel = document.getElementById('signalCasesPanel');
    if (signalsEl) {
        const signalCasesMap = data.signal_cases_map || {};
        const renderSignalCases = (signalName) => {
            if (!signalCasesPanel) return;
            const cases = Array.isArray(signalCasesMap[signalName]) ? signalCasesMap[signalName] : [];
            if (!cases.length) {
                signalCasesPanel.innerHTML = `<div style="padding:0.4rem 0.2rem;color:var(--text-muted);">No hay siniestros para la señal <strong>${signalName}</strong> con los filtros actuales.</div>`;
                return;
            }
            const rows = cases.slice(0, 12).map(c => {
                const score = Number(c.score_hibrido ?? c.score_reglas ?? 0).toFixed(1);
                const sem = c.semaforo_final || c.semaforo_reglas || '—';
                return `<tr class="signal-case-row" data-case-id="${c.id_siniestro || ''}" style="cursor:pointer;">
                    <td style="color:var(--cyan);font-weight:600;">${c.id_siniestro || ''}</td>
                    <td>${c.ramo || ''}</td>
                    <td>${score}</td>
                    <td>${sem}</td>
                </tr>`;
            }).join('');
            signalCasesPanel.innerHTML = `
                <div style="margin-bottom:0.45rem;color:var(--text-primary);font-weight:600;">Siniestros relacionados: ${signalName}</div>
                <div class="table-container" style="max-height:180px;overflow:auto;">
                    <table>
                        <thead><tr><th>ID</th><th>Ramo</th><th>Score</th><th>Semáforo</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
                <div style="margin-top:0.35rem;color:var(--text-muted);font-size:0.72rem;">Mostrando ${Math.min(cases.length, 12)} de ${cases.length} siniestros.</div>
            `;
            signalCasesPanel.querySelectorAll('.signal-case-row').forEach(row => {
                row.addEventListener('click', () => {
                    if (typeof viewCase === 'function' && row.dataset.caseId) viewCase(row.dataset.caseId);
                });
            });
        };

        signalsEl.innerHTML = (data.signals_summary || []).sort((a, b) => (b.count || 0) - (a.count || 0)).map(s => {
            const sev = s.count > 50 ? 'Crítica' : s.count > 20 ? 'Alta' : s.count > 5 ? 'Media' : 'Baja';
            const action = s.count > 50 ? 'Escalar investigación' : s.count > 20 ? 'Revisión documental' : 'Monitoreo';
            const cls = sev === 'Crítica' ? 'badge-red' : sev === 'Alta' ? 'badge-yellow' : 'badge-green';
            return `<tr class="signal-row-clickable" data-signal="${s.signal}" style="cursor:pointer;"><td>${s.signal}</td><td>${(s.count || 0).toLocaleString()}</td><td><span class="badge ${cls}">${sev}</span></td><td>${action}</td></tr>`;
        }).join('');
        signalsEl.querySelectorAll('.signal-row-clickable').forEach(row => {
            row.addEventListener('click', () => renderSignalCases(row.dataset.signal || ''));
        });
    }

    const critical = data.critical_rules_summary || {};
    const critTotal = Object.values(critical).reduce((acc, n) => acc + Number(n || 0), 0);
    setText('dashCriticalCount', critTotal.toLocaleString());
    const criticalEl = document.getElementById('criticalRulesPanel');
    if (criticalEl) {
        const rulesCatalog = [
            {
                code: 'RF-01',
                label: 'Cobertura Pérdida Total por Robo (PTxRB)',
                risk: 'Rojo',
            },
            {
                code: 'RF-02',
                label: 'Evidencia de falsificación o adulteración documental evidente',
                risk: 'Rojo',
            },
            {
                code: 'RF-03',
                label: 'Asegurado/Beneficiario/APS con coincidencia exacta en lista restrictiva',
                risk: 'Rojo',
            },
            {
                code: 'RF-04',
                label: 'Dinámica del accidente físicamente imposible',
                risk: 'Rojo',
            },
            {
                code: 'RF-05',
                label: 'Siniestro extremo al borde de vigencia (< 48 hrs)',
                risk: 'Amarillo',
            },
            {
                code: 'RF-06',
                label: 'Demora atípica en denuncia de robo (> 4 días)',
                risk: 'Amarillo',
            },
            {
                code: 'RF-07',
                label: 'Narrativa idéntica (clonada)',
                risk: 'Amarillo',
            },
        ];
        criticalEl.innerHTML = rulesCatalog.map(rule => {
            const n = Number(critical[rule.code] || 0);
            const cls = rule.risk === 'Rojo' ? 'badge-red' : 'badge-yellow';
            return `<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:0.6rem;padding:0.45rem 0;border-bottom:1px solid var(--border);">
                <div style="min-width:0;">
                    <div style="font-weight:700;color:var(--text-primary);">${rule.code}</div>
                    <div style="font-size:0.75rem;color:var(--text-secondary);line-height:1.35;">${rule.label}</div>
                    <div style="font-size:0.72rem;color:var(--text-muted);margin-top:0.1rem;">Clasificación: ${rule.risk}</div>
                </div>
                <span class="badge ${cls}" style="white-space:nowrap;">${n} casos</span>
            </div>`;
        }).join('');
    }

    const providerEl = document.getElementById('providerRiskTable');
    if (providerEl) {
        providerEl.innerHTML = (data.provider_risk || []).map((p) => {
            const sc = Number(p.score_prom || 0);
            const alertCls = sc >= 70 ? 'badge-red' : sc >= 45 ? 'badge-yellow' : 'badge-green';
            return `<tr>
                <td title="${p.beneficiario || ''}"><strong>${String(p.beneficiario || '').slice(0, 28)}</strong></td>
                <td>${(p.casos || 0).toLocaleString()}</td>
                <td><span class="badge ${alertCls}">${sc.toFixed(1)}</span></td>
                <td>$${Number(p.monto || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                <td><span class="badge ${alertCls}" style="font-size:0.65rem;">${sc >= 70 ? 'Alta' : sc >= 45 ? 'Media' : 'Baja'}</span></td>
            </tr>`;
        }).join('') || '<tr><td colspan="5" style="color:var(--text-muted);">Sin datos de proveedores.</td></tr>';
    }

    renderDashboardCharts(data);
}

async function refreshDashboard() {
    const shell = document.getElementById('dashboardShell');
    if (!shell) return;
    try {
        const qs = buildDashboardQuery();
        const dashHeaders = {};
        try {
            const sid = sessionStorage.getItem('fxecure_session_id') || sessionStorage.getItem('fraudia_session_id');
            if (sid) {
                dashHeaders['X-FXecure-Session'] = sid;
                dashHeaders['X-FraudIA-Session'] = sid;
            }
        } catch (e) { /* ignore */ }
        const resp = await fetch('/api/dashboard-data' + (qs ? '?' + qs : ''), { headers: dashHeaders });
        const data = await resp.json();
        if (data.error) return;
        dashboardState.lastData = data;
        renderDashboardData(data);
    } catch (e) {
        console.error('Dashboard refresh:', e);
    }
}

async function initDashboard() {
    const container = document.getElementById('dashboardContent');
    try {
        const dashHeaders = {};
        try {
            const sid = sessionStorage.getItem('fxecure_session_id') || sessionStorage.getItem('fraudia_session_id');
            if (sid) {
                dashHeaders['X-FXecure-Session'] = sid;
                dashHeaders['X-FraudIA-Session'] = sid;
            }
        } catch (e) { /* ignore */ }
        const optResp = await fetch('/api/dashboard-filters', { headers: dashHeaders });
        const opts = await optResp.json();
        if (opts.error) {
            container.innerHTML = '<div class="alert alert-info">' + opts.error + '. Ejecute el pipeline desde Datos.</div>';
            return;
        }
        dashboardState.options = opts;
        setFilterDefaultsFromOptions(opts);
        if (!dashboardState.initialized) {
            dashboardState.filters = emptyDashboardFilters();
            container.innerHTML = '<div id="dashboardShell" class="dash-premium">' + buildDashboardShell() + '</div>';
            bindDashboardEvents();
            populateFilterControls(opts);
            updateSemaforoPills();
            dashboardState.initialized = true;
            await loadDashboardMetricsAuc();
        }
        await refreshDashboard();
        scheduleDashboardChartsResize();
    } catch (e) {
        console.error('initDashboard:', e);
        container.innerHTML = '<div class="alert alert-danger">Error al cargar el dashboard.</div>';
    }
}

// Compatibilidad con llamadas anteriores
function loadDashboard() { initDashboard(); }
