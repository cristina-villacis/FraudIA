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
                <h2>Centro de Inteligencia Antifraude</h2>
                <div class="dash-soc-meta">
                    <span>Motor IA: <strong id="dashIaStatus">Activo</strong></span>
                    <span>AUC-ROC: <strong id="kpiAuc">—</strong></span>
                    <span>Actualizado: <strong id="dashNow">—</strong></span>
                </div>
            </div>
            <span class="dash-panel-badge">SOC · Tiempo real</span>
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

        <details class="dash-panel dash-filters-panel" open>
            <summary>▸ Filtros inteligentes · clic en gráficos para explorar</summary>
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

        <div class="dash-layout-main">
            <section class="dash-panel">
                <div class="dash-panel-head">
                    <h3 class="dash-panel-title">Casos críticos · priorización IA</h3>
                    <span class="dash-panel-badge">Top riesgo</span>
                </div>
                <div class="dash-table-wrap">
                    <table class="dash-table">
                        <thead><tr>
                            <th></th><th>ID</th><th>Score IA</th><th>Riesgo</th><th>Proveedor</th><th>Asegurado</th><th>Monto</th><th>Reglas</th><th>Estado</th><th></th>
                        </tr></thead>
                        <tbody id="criticalCasesTable"></tbody>
                    </table>
                </div>
                <div id="topAnomaliesList" style="display:none;"></div>
            </section>
            <div class="dash-stack">
                <div class="dash-panel card-chart">
                    <div class="dash-panel-head">
                        <h3 class="dash-panel-title">Distribución score · ML</h3>
                        <button type="button" class="chart-reset-btn" data-reset-scope="score" title="Limpiar">✕</button>
                    </div>
                    <div id="chartScores" class="chart-area" style="min-height:240px;"></div>
                </div>
                <div class="dash-panel card-chart">
                    <div class="dash-panel-head">
                        <h3 class="dash-panel-title">Timeline antifraude</h3>
                        <button type="button" class="chart-reset-btn" data-reset-scope="fecha" title="Limpiar">✕</button>
                    </div>
                    <div id="chartTemporal" class="chart-area" style="min-height:220px;"></div>
                </div>
            </div>
        </div>

        <div class="dash-layout-triple">
            <div class="dash-panel card-chart">
                <div class="dash-panel-head">
                    <h3 class="dash-panel-title">Semáforo de riesgo</h3>
                    <button type="button" class="chart-reset-btn" data-reset-scope="semaforo" title="Limpiar">✕</button>
                </div>
                <div class="donut-chart-wrap"><div id="chartSemaforo" class="chart-area"></div></div>
            </div>
            <div class="dash-panel card-chart">
                <div class="dash-panel-head">
                    <h3 class="dash-panel-title">Mapa calor · sucursales</h3>
                    <button type="button" class="chart-reset-btn" data-reset-scope="all" title="Limpiar">✕</button>
                </div>
                <div id="chartGeoOperacion" class="chart-area" style="min-height:260px;"></div>
            </div>
            <div class="dash-panel">
                <div class="dash-panel-head">
                    <h3 class="dash-panel-title">Red de relaciones</h3>
                    <span class="dash-panel-badge">PK/FK</span>
                </div>
                <div class="dash-graph-wrap" id="dashRelationGraph"></div>
            </div>
        </div>

        <div class="dash-layout-duo">
            <div class="dash-panel">
                <div class="dash-panel-head"><h3 class="dash-panel-title">NLP · similitud narrativa</h3></div>
                <div id="nlpPanel"></div>
                <div class="dash-nlp-cluster" id="nlpKeywords"></div>
            </div>
            <div class="dash-panel">
                <div class="dash-panel-head"><h3 class="dash-panel-title">IA explicable · caso activo</h3></div>
                <div id="explainabilityPanel" class="dash-xai-hero">
                    Seleccione un caso crítico para ver la explicación automática del motor antifraude.
                </div>
            </div>
        </div>

        <div class="dash-layout-duo">
            <div class="dash-panel card-chart">
                <div class="dash-panel-head">
                    <h3 class="dash-panel-title">Heatmap ramo × riesgo</h3>
                    <button type="button" class="chart-reset-btn" data-reset-scope="all" title="Limpiar">✕</button>
                </div>
                <div id="chartHeatmapRamoRiesgo" class="chart-area" style="min-height:260px;"></div>
            </div>
            <div class="dash-panel card-chart">
                <div class="dash-panel-head">
                    <h3 class="dash-panel-title">Análisis por ramo</h3>
                    <button type="button" class="chart-reset-btn" data-reset-scope="ramo" title="Limpiar">✕</button>
                </div>
                <div id="chartRamo" class="chart-area chart-area-ramo" style="min-height:260px;"></div>
                <div class="chart-legend-below" id="ramoChartLegend" style="margin-top:0.5rem;">
                    <span><i style="background:var(--green);"></i> Bajo</span>
                    <span><i style="background:var(--yellow);"></i> Medio</span>
                    <span><i style="background:var(--red);"></i> Alto</span>
                </div>
            </div>
        </div>

        <div class="dash-layout-duo">
            <div class="dash-panel">
                <div class="dash-panel-head"><h3 class="dash-panel-title">Ranking proveedores sospechosos</h3></div>
                <div class="dash-table-wrap" style="max-height:300px;">
                    <table class="dash-table">
                        <thead><tr><th>Proveedor</th><th>Casos</th><th>Score prom.</th><th>Monto</th><th>Alertas</th></tr></thead>
                        <tbody id="providerRiskTable"></tbody>
                    </table>
                </div>
            </div>
            <div class="dash-panel">
                <div class="dash-panel-head"><h3 class="dash-panel-title">Panel ML · anomalías</h3></div>
                <div id="dashMlPanel"></div>
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

        <div class="dash-panel dash-chat-panel">
            <div class="dash-panel-head">
                <h3 class="dash-panel-title">Asistente IA antifraude</h3>
                <span class="dash-panel-badge">Datos en vivo</span>
            </div>
            <div class="dash-chat-suggestions">
                <button type="button" data-dash-q="¿Qué casos revisar primero?">¿Qué casos revisar primero?</button>
                <button type="button" data-dash-q="¿Qué ciudad tiene más fraude?">¿Qué sucursal concentra alertas?</button>
                <button type="button" data-dash-q="Resume los casos críticos del dashboard.">Resume casos críticos</button>
            </div>
            <div class="dash-chat-messages" id="dashChatMessages">
                <div class="chat-msg chat-agent">Soy FraudIA. Pregúntame sobre casos críticos, patrones, proveedores o riesgo geográfico usando los datos del dashboard.</div>
            </div>
            <div class="dash-chat-input">
                <input type="text" id="dashChatInput" placeholder="Ej: ¿Cuáles son los 5 casos de mayor riesgo?" onkeypress="if(event.key==='Enter')sendDashChatQuery()">
                <button type="button" class="btn btn-primary" id="btnDashChatSend" onclick="sendDashChatQuery()">Enviar</button>
            </div>
        </div>
    `;
}

const DASH_ER_NODES = [
    { id: 'sin', label: 'Siniestros', x: 200, y: 150 },
    { id: 'pol', label: 'Pólizas', x: 80, y: 70 },
    { id: 'ase', label: 'Asegurados', x: 320, y: 70 },
    { id: 'pro', label: 'Proveedores', x: 80, y: 230 },
    { id: 'doc', label: 'Documentos', x: 320, y: 230 },
];
const DASH_ER_EDGES = [
    ['sin', 'pol'], ['sin', 'ase'], ['sin', 'pro'], ['doc', 'sin'], ['pol', 'ase'],
];

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
            const id = row.dataset.caseId;
            const c = cases.find((x) => x.id_siniestro === id);
            renderExplainability(c);
        });
    });
    tbody.querySelectorAll('.dash-btn-analyze').forEach((btn) => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const id = btn.dataset.analyze;
            const c = cases.find((x) => x.id_siniestro === id);
            renderExplainability(c);
            if (typeof viewCase === 'function') viewCase(id);
        });
    });
}

function renderDashRelationGraph(data) {
    const wrap = document.getElementById('dashRelationGraph');
    if (!wrap) return;
    const provN = (data.provider_risk || []).length;
    const crit = data.rojos || 0;
    const byId = Object.fromEntries(DASH_ER_NODES.map((n) => [n.id, n]));
    let edges = '';
    DASH_ER_EDGES.forEach(([a, b]) => {
        const n1 = byId[a];
        const n2 = byId[b];
        if (!n1 || !n2) return;
        edges += `<line class="er-edge" x1="${n1.x}" y1="${n1.y}" x2="${n2.x}" y2="${n2.y}"/>`;
    });
    const nodes = DASH_ER_NODES.map((n) => {
        const pulse = n.id === 'sin' && crit > 0 ? ' filter="url(#glow)"' : '';
        return `<g class="er-node"${pulse}>
            <circle cx="${n.x}" cy="${n.y}" r="34"/>
            <text x="${n.x}" y="${n.y + 4}" text-anchor="middle">${n.label}</text>
        </g>`;
    }).join('');
    wrap.innerHTML = `<svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid meet">
        <defs><filter id="glow"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
        ${edges}${nodes}
        <text x="200" y="285" text-anchor="middle" fill="var(--text-muted)" font-size="8">${provN} proveedores · ${crit} casos críticos en vista</text>
    </svg>`;
}

async function renderDashMlPanel() {
    const el = document.getElementById('dashMlPanel');
    if (!el) return;
    try {
        const m = await (await fetch('/api/model-metrics')).json();
        if (m.error) {
            el.innerHTML = '<div style="color:var(--text-muted);font-size:0.82rem;">Ejecute el pipeline para activar métricas ML.</div>';
            return;
        }
        const auc = Number(m.auc_roc || 0).toFixed(2);
        const features = m.top_features || m.feature_importance || [];
        const featRows = (Array.isArray(features) ? features : []).slice(0, 6).map((f) => {
            const name = f.feature || f.name || 'feature';
            const imp = Number(f.importance ?? f.value ?? 0);
            const pct = Math.min(100, imp * (imp <= 1 ? 100 : 1));
            return `<div class="dash-shap-bar"><span style="min-width:90px;">${String(name).slice(0, 14)}</span><div class="track"><div class="fill" style="width:${pct}%;"></div></div></div>`;
        }).join('');
        el.innerHTML = `
            <div class="dash-ml-grid">
                <div class="dash-ml-stat"><label>AUC-ROC</label><span>${auc}</span></div>
                <div class="dash-ml-stat"><label>Predicción fraude</label><span>${m.trained ? 'Activa' : 'Reglas'}</span></div>
                <div class="dash-ml-stat"><label>Anomalías</label><span>${m.anomalies_detected ?? '—'}</span></div>
                <div class="dash-ml-stat"><label>Precisión</label><span>${m.precision != null ? (m.precision * 100).toFixed(0) + '%' : '—'}</span></div>
            </div>
            <div style="margin-top:0.85rem;font-size:0.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.06em;">Feature importance (SHAP)</div>
            ${featRows || '<div style="color:var(--text-muted);font-size:0.8rem;margin-top:0.5rem;">Sin importancias disponibles.</div>'}
        `;
        dashboardState.metricsAuc = auc;
        const aucEl = document.getElementById('kpiAuc');
        if (aucEl) aucEl.textContent = auc;
    } catch (e) {
        el.innerHTML = '<div style="color:var(--text-muted);font-size:0.82rem;">ML no disponible.</div>';
    }
}

function sendDashChatQuery(prefill) {
    const input = document.getElementById('dashChatInput');
    const q = typeof prefill === 'string' ? prefill : (input && input.value.trim());
    if (!q) return;
    if (input && typeof prefill !== 'string') input.value = '';
    if (typeof sendAgentQuery === 'function') sendAgentQuery(q, 'dashChatMessages', 'dashChat');
}

function bindDashboardEvents() {
    document.querySelectorAll('.dash-chat-suggestions button').forEach((btn) => {
        btn.addEventListener('click', () => sendDashChatQuery(btn.dataset.dashQ || ''));
    });
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
    const chartScores = document.getElementById('chartScores');
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
    if (chartScores && !chartScores._plotlyClickBound) {
        chartScores.on('plotly_click', (ev) => {
            const pt = ev.points[0];
            const ranges = (dashboardState.lastData && dashboardState.lastData.score_distribution && dashboardState.lastData.score_distribution.click_ranges) || [];
            const band = ranges[pt.pointNumber] || ranges.find(r => r.label === pt.x);
            if (band) {
                setDashboardFilter('score_min', String(band.min), false);
                setDashboardFilter('score_max', String(band.max), false);
                const smin = document.getElementById('filterScoreMin');
                const smax = document.getElementById('filterScoreMax');
                const rmin = document.getElementById('filterScoreMinRange');
                const rmax = document.getElementById('filterScoreMaxRange');
                if (smin) smin.value = band.min;
                if (smax) smax.value = band.max;
                if (rmin) rmin.value = band.min;
                if (rmax) rmax.value = band.max;
                updateFilterChips();
                refreshDashboard();
                return;
            }
            const parts = String(pt.x || '').split('-');
            if (parts.length >= 2) {
                const lo = Number(parts[0]);
                const hi = Number(parts[1]);
                setDashboardFilter('score_min', String(lo), false);
                setDashboardFilter('score_max', String(hi), false);
                document.getElementById('filterScoreMin').value = lo;
                document.getElementById('filterScoreMax').value = hi;
                document.getElementById('filterScoreMinRange').value = lo;
                document.getElementById('filterScoreMaxRange').value = hi;
                updateFilterChips();
                refreshDashboard();
            }
        });
        chartScores._plotlyClickBound = true;
    }
    if (chartRamo && !chartRamo._plotlyClickBound) {
        chartRamo.on('plotly_click', (ev) => {
            const ramo = ev.points[0].x;
            setDashboardFilter('ramo', ramo);
        });
        chartRamo._plotlyClickBound = true;
    }
    if (chartTemporal && !chartTemporal._plotlyClickBound && data.temporal_data) {
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
    const C = getColors(), PL = getPlotlyLayout();
    const rojo = data.semaforo.Rojo || 0, amarillo = data.semaforo.Amarillo || 0, verde = data.semaforo.Verde || 0;
    const totalSem = rojo + amarillo + verde || data.total || 1;

    Plotly.react('chartSemaforo', [{
        values: [rojo, amarillo, verde],
        labels: ['Rojo', 'Amarillo', 'Verde'],
        customdata: ['76-100 · Alto', '41-75 · Medio', '0-40 · Bajo'],
        type: 'pie', hole: 0.62, sort: false, direction: 'clockwise',
        marker: { colors: [C.red, C.yellow, C.green], line: { color: C.bgCard || C.bg, width: 3 } },
        textinfo: 'none',
        texttemplate: '%{label}<br>%{value:,} (%{percent})<br>%{customdata}',
        textposition: 'outside',
        textfont: { size: 10, color: C.text },
        hovertemplate: '<b>%{label}</b><br>%{value:,} casos<br>%{percent}<br>%{customdata}<extra></extra>',
        pull: rojo > 0 ? [0.04, 0, 0] : [0, 0, 0],
    }], {
        ...PL, showlegend: false, height: 220,
        margin: { t: 12, b: 12, l: 12, r: 12, autoexpand: true },
        annotations: [{
            text: '<b>' + totalSem.toLocaleString() + '</b><br>siniestros',
            showarrow: false, font: { size: 15, color: C.text, family: 'Inter, sans-serif' },
            x: 0.5, y: 0.5, xref: 'paper', yref: 'paper', align: 'center',
        }],
    }, PLOTLY_CONFIG);

    if (data.score_distribution && data.score_distribution.labels && data.score_distribution.labels.length) {
        const sd = data.score_distribution;
        Plotly.react('chartScores', [{
            x: sd.labels,
            y: sd.counts,
            type: 'bar',
            marker: {
                color: sd.colors || [],
                line: { width: 0 },
                opacity: 0.9,
            },
            text: sd.counts.map(String),
            textposition: 'outside',
            textfont: { size: 11, color: C.text },
            hovertemplate: '<b>%{x}</b><br>%{y:,} casos<extra></extra>',
        }], {
            ...PL,
            xaxis: {
                title: 'Nivel de riesgo (según score híbrido)',
                gridcolor: C.grid,
                tickfont: { size: 10 },
            },
            yaxis: { title: 'Cantidad de siniestros', gridcolor: C.grid },
            height: 280,
            margin: { t: 10, b: 50, l: 50, r: 20 },
            bargap: 0.35,
        }, PLOTLY_CONFIG);
    }

    if (data.ramo_data && data.ramo_data.length) {
        const ramos = data.ramo_data.map(r => r.ramo);
        const verdes = data.ramo_data.map(r => r.verdes ?? Math.max(0, (r.count || 0) - (r.rojos || 0) - (r.amarillos || 0)));
        const amarillos = data.ramo_data.map(r => r.amarillos ?? 0);
        const rojos = data.ramo_data.map(r => r.rojos ?? 0);
        Plotly.react('chartRamo', [
            {
                x: ramos, y: verdes, name: 'Verde', type: 'bar', marker: { color: C.green, opacity: 0.9 },
                text: verdes.map(v => v > 0 ? String(v) : ''), textposition: 'inside', textfont: { size: 10, color: C.text },
            },
            {
                x: ramos, y: amarillos, name: 'Amarillo', type: 'bar', marker: { color: C.yellow, opacity: 0.9 },
                text: amarillos.map(v => v > 0 ? String(v) : ''), textposition: 'inside', textfont: { size: 10, color: C.text },
            },
            {
                x: ramos, y: rojos, name: 'Rojo', type: 'bar', marker: { color: C.red, opacity: 0.9 },
                text: rojos.map(v => v > 0 ? String(v) : ''), textposition: 'inside', textfont: { size: 10, color: C.text },
            },
        ], {
            ...PL,
            barmode: 'stack',
            showlegend: false,
            bargap: 0.28,
            xaxis: {
                gridcolor: C.grid,
                tickfont: { size: 10, color: C.muted },
                tickangle: -35,
                automargin: true,
                type: 'category',
            },
            yaxis: {
                title: { text: 'Siniestros', font: { size: 11, color: C.muted } },
                gridcolor: C.grid,
                automargin: true,
                zeroline: false,
            },
            height: 300,
            margin: { t: 16, b: 70, l: 52, r: 16, autoexpand: true },
        }, { ...PLOTLY_CONFIG, responsive: true });
    }

    if (data.temporal_risk_data && data.temporal_risk_data.length) {
        const months = data.temporal_risk_data.map(t => t.mes);
        Plotly.react('chartTemporal', [
            {
                x: months,
                y: data.temporal_risk_data.map(t => t.Verde || 0),
                type: 'bar',
                name: 'Bajo (Verde)',
                marker: { color: C.green, opacity: 0.9 },
                text: data.temporal_risk_data.map(t => (t.Verde || 0) > 0 ? String(t.Verde || 0) : ''),
                textposition: 'inside',
                textfont: { size: 10, color: C.text },
            },
            {
                x: months,
                y: data.temporal_risk_data.map(t => t.Amarillo || 0),
                type: 'bar',
                name: 'Medio (Amarillo)',
                marker: { color: C.yellow, opacity: 0.9 },
                text: data.temporal_risk_data.map(t => (t.Amarillo || 0) > 0 ? String(t.Amarillo || 0) : ''),
                textposition: 'inside',
                textfont: { size: 10, color: C.text },
            },
            {
                x: months,
                y: data.temporal_risk_data.map(t => t.Rojo || 0),
                type: 'bar',
                name: 'Alto (Rojo)',
                marker: { color: C.red, opacity: 0.9 },
                text: data.temporal_risk_data.map(t => (t.Rojo || 0) > 0 ? String(t.Rojo || 0) : ''),
                textposition: 'inside',
                textfont: { size: 10, color: C.text },
            },
        ], {
            ...PL,
            barmode: 'stack',
            xaxis: { gridcolor: C.grid, title: 'Mes' },
            yaxis: { title: 'Casos por nivel de riesgo', gridcolor: C.grid, side: 'left' },
            height: 260,
            showlegend: true,
            legend: { orientation: 'h', y: -0.25, x: 0 },
        }, PLOTLY_CONFIG);
    }

    if (data.heatmap_ramo_riesgo && data.heatmap_ramo_riesgo.ramos && data.heatmap_ramo_riesgo.ramos.length) {
        Plotly.react('chartHeatmapRamoRiesgo', [{
            z: data.heatmap_ramo_riesgo.z,
            x: data.heatmap_ramo_riesgo.semaforos,
            y: data.heatmap_ramo_riesgo.ramos,
            type: 'heatmap',
            colorscale: currentTheme === 'light'
                ? [[0, '#f8fafc'], [0.5, 'rgba(3,105,161,0.35)'], [1, '#0369a1']]
                : [[0, '#0b1220'], [0.5, 'rgba(0,209,255,0.35)'], [1, '#00d1ff']],
            showscale: false,
            text: data.heatmap_ramo_riesgo.z,
            texttemplate: '%{text}',
            textfont: { size: 10, color: C.text },
        }], {
            ...PL,
            margin: { t: 10, b: 40, l: 90, r: 10 },
            xaxis: { title: 'Nivel de riesgo', gridcolor: C.grid },
            yaxis: { title: 'Ramo', gridcolor: C.grid },
            height: 280,
        }, PLOTLY_CONFIG);
    }

    if (data.geo_risk_data && data.geo_risk_data.length) {
        const suc = data.geo_risk_data.map(g => g.sucursal);
        Plotly.react('chartGeoOperacion', [
            {
                x: suc, y: data.geo_risk_data.map(g => g.Verde || 0), type: 'bar', name: 'Bajo',
                marker: { color: C.green, opacity: 0.88 },
                text: data.geo_risk_data.map(g => (g.Verde || 0) > 0 ? String(g.Verde || 0) : ''),
                textposition: 'inside',
                textfont: { size: 10, color: C.text },
            },
            {
                x: suc, y: data.geo_risk_data.map(g => g.Amarillo || 0), type: 'bar', name: 'Medio',
                marker: { color: C.yellow, opacity: 0.88 },
                text: data.geo_risk_data.map(g => (g.Amarillo || 0) > 0 ? String(g.Amarillo || 0) : ''),
                textposition: 'inside',
                textfont: { size: 10, color: C.text },
            },
            {
                x: suc, y: data.geo_risk_data.map(g => g.Rojo || 0), type: 'bar', name: 'Alto',
                marker: { color: C.red, opacity: 0.88 },
                text: data.geo_risk_data.map(g => (g.Rojo || 0) > 0 ? String(g.Rojo || 0) : ''),
                textposition: 'inside',
                textfont: { size: 10, color: C.text },
            },
        ], {
            ...PL,
            barmode: 'stack',
            margin: { t: 24, b: 40, l: 40, r: 10 },
            xaxis: { title: 'Sucursal', gridcolor: C.grid },
            yaxis: { title: 'Casos por nivel de riesgo', gridcolor: C.grid },
            height: 280,
            showlegend: true,
            legend: { orientation: 'h', y: -0.25, x: 0 },
        }, PLOTLY_CONFIG);
    }

    bindPlotlyDashboardCharts(data);
    resizeDashboardCharts();
}

function resizeDashboardCharts() {
    ['chartSemaforo', 'chartScores', 'chartRamo', 'chartTemporal', 'chartHeatmapRamoRiesgo', 'chartGeoOperacion'].forEach(id => {
        const el = document.getElementById(id);
        if (el && el.querySelector('.plotly')) {
            try { Plotly.Plots.resize(el); } catch (e) { /* ignore */ }
        }
    });
}
if (typeof window !== 'undefined') {
    window.addEventListener('resize', () => {
        if (document.getElementById('dashboardShell')) resizeDashboardCharts();
    });
}

async function loadNlpPanel() {
    const el = document.getElementById('nlpPanel');
    const kwEl = document.getElementById('nlpKeywords');
    if (!el) return;
    try {
        const nlp = await (await fetch('/api/nlp-summary')).json();
        if (!nlp.error && nlp.high_similarity_pairs) {
            const pairs = nlp.high_similarity_pairs.slice(0, 6);
            el.innerHTML = pairs.map((p) =>
                `<div style="display:flex;justify-content:space-between;align-items:center;padding:0.55rem 0;border-bottom:1px solid var(--border-subtle);">
                    <div>
                        <div class="mono" style="font-size:0.78rem;color:var(--cyan);">${p.id_1} ↔ ${p.id_2}</div>
                        <div style="font-size:0.68rem;color:var(--text-muted);">Reclamo clonado · embedding</div>
                    </div>
                    <span class="badge ${p.similarity >= 0.85 ? 'badge-red' : p.similarity >= 0.70 ? 'badge-yellow' : 'badge-green'}" style="font-size:0.7rem;">${(p.similarity * 100).toFixed(0)}% sim.</span>
                </div>`
            ).join('') || '<div style="color:var(--text-muted);font-size:0.82rem;">Sin pares similares.</div>';
            if (kwEl) {
                const tags = ['narrativa', 'similitud', 'embedding', 'cluster', 'fraude', 'clonado'];
                kwEl.innerHTML = tags.map((t) => `<span class="dash-nlp-tag">${t}</span>`).join('');
            }
        } else {
            el.innerHTML = '<div style="color:var(--text-muted);font-size:0.82rem;">Sin datos NLP. Ejecute el pipeline.</div>';
        }
    } catch (e) {
        el.innerHTML = '<div style="color:var(--text-muted);font-size:0.82rem;">NLP no disponible.</div>';
    }
}

function renderExplainability(caseItem) {
    const el = document.getElementById('explainabilityPanel');
    if (!el) return;
    if (!caseItem) {
        el.className = 'dash-xai-hero';
        el.innerHTML = 'Seleccione un caso crítico para ver la explicación automática del motor antifraude.';
        return;
    }
    const score = Number(caseItem.score_hibrido ?? caseItem.score_reglas ?? 0).toFixed(1);
    const sem = caseItem.semaforo_final || caseItem.semaforo_reglas || 'N/A';
    const nivel = sem === 'Rojo' ? 'ALTO' : sem === 'Amarillo' ? 'MEDIO' : 'BAJO';
    const alertas = String(caseItem.alertas_reglas || '').split('|').map((x) => x.trim()).filter(Boolean).slice(0, 6);
    const bullets = alertas.length
        ? alertas.map((a) => `<li>${a}</li>`).join('')
        : '<li>Score híbrido elevado según reglas de negocio</li><li>Patrón detectado por motor de anomalías</li>';
    el.className = 'dash-xai-hero';
    el.innerHTML = `
        <p>El caso <span class="xai-case-id">${caseItem.id_siniestro || 'N/A'}</span> fue clasificado como <strong>${nivel}</strong> riesgo (score ${score}/100) debido a:</p>
        <ul class="dash-xai-list">${bullets}</ul>
        <p style="margin-top:0.65rem;font-size:0.75rem;color:var(--text-muted);">Proveedor: ${caseItem.beneficiario || '—'} · Monto: $${Number(caseItem.monto_reclamado || 0).toLocaleString()} · Validación analista requerida.</p>
    `;
}

function renderDashboardData(data) {
    const rojo = data.semaforo.Rojo || 0, amarillo = data.semaforo.Amarillo || 0, verde = data.semaforo.Verde || 0;
    const totalSafe = data.total || (rojo + amarillo + verde) || 1;
    const pctOf = (n) => (n / totalSafe * 100).toFixed(1);

    const activeFilters = getActiveFiltersForUI();
    const isFiltered = activeFilters.length > 0;

    const banner = document.getElementById('dashboardBanner');
    if (isFiltered) {
        banner.innerHTML = `Mostrando <strong>${data.total.toLocaleString()}</strong> de <strong>${data.total_unfiltered.toLocaleString()}</strong> siniestros (${activeFilters.length} filtro${activeFilters.length > 1 ? 's' : ''} activo${activeFilters.length > 1 ? 's' : ''}).`;
    } else {
        banner.innerHTML = `Vista completa: <strong>${data.total.toLocaleString()}</strong> siniestros analizados. Use filtros o haga clic en los gráficos para explorar.`;
    }

    document.getElementById('kpiTotal').textContent = data.total.toLocaleString();
    document.getElementById('kpiTotalSub').textContent = isFiltered
        ? `de ${data.total_unfiltered.toLocaleString()} totales` : 'Analizados';
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
    renderCriticalCasesTable(topCases);
    renderAnomaliesList(topCases);
    renderDashRelationGraph(data);
    if (topCases[0]) renderExplainability(topCases[0]);
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
            const selected = (data.top_cases || []).find(x => x.id_siniestro === row.dataset.caseId);
            renderExplainability(selected);
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
    renderDashMlPanel();
}

async function refreshDashboard() {
    const shell = document.getElementById('dashboardShell');
    if (!shell) return;
    try {
        const qs = buildDashboardQuery();
        const dashHeaders = {};
        try {
            const sid = sessionStorage.getItem('fraudia_session_id');
            if (sid) dashHeaders['X-FraudIA-Session'] = sid;
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
            const sid = sessionStorage.getItem('fraudia_session_id');
            if (sid) dashHeaders['X-FraudIA-Session'] = sid;
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
            loadNlpPanel();
            try {
                const m = await (await fetch('/api/model-metrics')).json();
                if (!m.error) dashboardState.metricsAuc = (m.auc_roc || 0).toFixed(2);
            } catch (e) { /* ignore */ }
        }
        await refreshDashboard();
    } catch (e) {
        console.error('initDashboard:', e);
        container.innerHTML = '<div class="alert alert-danger">Error al cargar el dashboard.</div>';
    }
}

// Compatibilidad con llamadas anteriores
function loadDashboard() { initDashboard(); }
if (typeof window !== 'undefined') window.sendDashChatQuery = sendDashChatQuery;
