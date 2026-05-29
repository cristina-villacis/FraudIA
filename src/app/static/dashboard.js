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
    viewMode: 'executive',
    segmentTab: 'sucursal',
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

function normalizeSemaforoCounts(sem) {
    const out = { Rojo: 0, Amarillo: 0, Verde: 0 };
    if (!sem || typeof sem !== 'object') return out;
    Object.entries(sem).forEach(([k, v]) => {
        const key = String(k).trim().toLowerCase();
        const n = Number(v) || 0;
        if (key.startsWith('roj') || key === 'alto') out.Rojo += n;
        else if (key.startsWith('amar') || key === 'medio') out.Amarillo += n;
        else if (key.startsWith('ver') || key === 'bajo') out.Verde += n;
    });
    return out;
}

function safePlotlyReact(targetId, data, layout, config) {
    if (typeof Plotly === 'undefined') {
        console.error('Plotly no está cargado.');
        return false;
    }
    const el = document.getElementById(targetId);
    if (!el) return false;
    const cfg = { displayModeBar: false, responsive: true, ...(config || {}) };
    const lay = { ...layout, autosize: true };
    try {
        if (el.querySelector('.plotly-graph-div') || el.querySelector('.js-plotly-plot')) {
            Plotly.react(el, data, lay, cfg);
        } else {
            Plotly.newPlot(el, data, lay, cfg);
        }
        return true;
    } catch (err) {
        console.error('Plotly chart error:', targetId, err);
        try {
            Plotly.newPlot(el, data, lay, cfg);
            return true;
        } catch (err2) {
            console.error('Plotly newPlot error:', targetId, err2);
            return false;
        }
    }
}

/** Plotly calcula mal el tamaño si el contenedor estaba oculto (display:none). */
function scheduleDashboardChartsResize() {
    requestAnimationFrame(() => {
        [80, 350, 800, 1500].forEach((ms) => setTimeout(() => resizeDashboardCharts(), ms));
    });
}

function ensurePlotlyThenRenderCharts(data) {
    if (typeof Plotly !== 'undefined') {
        renderDashboardCharts(data);
        return;
    }
    let tries = 0;
    const t = setInterval(() => {
        tries += 1;
        if (typeof Plotly !== 'undefined') {
            clearInterval(t);
            renderDashboardCharts(data);
        } else if (tries > 40) {
            clearInterval(t);
            console.error('Plotly no cargó tras varios intentos.');
        }
    }, 150);
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

const DASH_SVG_ICONS = {
    layers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>',
    alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    money: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>',
    brain: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9.5 2A5.5 5.5 0 004 7.5c0 1.38.56 2.63 1.47 3.54A4.5 4.5 0 002 15.5 4.5 4.5 0 006.5 20H17a5 5 0 100-10 5.5 5.5 0 00-2.47-10.46A5.5 5.5 0 009.5 2z"/></svg>',
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
};

function fmtExecValue(item) {
    const v = Number(item.value);
    if (item.format === 'currency') {
        if (v >= 1e6) return '$' + (v / 1e6).toFixed(1) + 'M';
        return '$' + v.toLocaleString('es-CO', { maximumFractionDigits: 0 });
    }
    if (item.format === 'percent') return v.toFixed(1) + '%';
    if (item.format === 'hours') return v.toFixed(1) + ' h';
    if (item.format === 'score') return v.toFixed(1);
    return (item.value ?? 0).toLocaleString('es-CO');
}

function initDashParticles() {
    const canvas = document.getElementById('dashParticles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const parent = canvas.parentElement;
    let w = 0;
    let h = 0;
    const dots = [];
    const N = 48;
    for (let i = 0; i < N; i++) {
        dots.push({
            x: Math.random(),
            y: Math.random(),
            r: 0.5 + Math.random() * 1.5,
            vx: (Math.random() - 0.5) * 0.0004,
            vy: (Math.random() - 0.5) * 0.0004,
            a: 0.15 + Math.random() * 0.35,
        });
    }
    function resize() {
        if (!parent) return;
        w = parent.clientWidth;
        h = parent.clientHeight;
        canvas.width = w;
        canvas.height = h;
    }
    function tick() {
        if (!w || !h) { requestAnimationFrame(tick); return; }
        ctx.clearRect(0, 0, w, h);
        dots.forEach((d) => {
            d.x += d.vx;
            d.y += d.vy;
            if (d.x < 0 || d.x > 1) d.vx *= -1;
            if (d.y < 0 || d.y > 1) d.vy *= -1;
            ctx.beginPath();
            ctx.arc(d.x * w, d.y * h, d.r, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(59, 130, 246, ${d.a})`;
            ctx.fill();
        });
        requestAnimationFrame(tick);
    }
    resize();
    window.addEventListener('resize', resize);
    tick();
}

function renderHeroKpis(highlights) {
    const el = document.getElementById('heroKpisContainer');
    if (!el) return;
    const items = highlights && highlights.length ? highlights : [];
    el.innerHTML = items.map((h) => {
        const glow = h.glow ? `glow-${h.glow}` : 'glow-blue';
        const deltaCls = h.delta_dir || 'neutral';
        const deltaHtml = h.delta ? `<span class="dash-hero-delta ${deltaCls}">${h.delta}</span>` : '';
        const color = h.key === 'critical' ? 'var(--red)' : h.key === 'financial' ? 'var(--yellow)' : h.key === 'prevented' ? 'var(--green)' : '#fff';
        return `<article class="dash-hero-card ${glow}">
            <div class="dash-hero-label">${h.label}</div>
            <div class="dash-hero-value" style="color:${color}">${fmtExecValue(h)}</div>
            ${deltaHtml}
        </article>`;
    }).join('') || '<p style="color:var(--text-muted);grid-column:1/-1;">Sin datos — ejecute el análisis.</p>';
}

function renderExecGrid(extended, sparklines) {
    const el = document.getElementById('execKpisContainer');
    if (!el) return;
    const sp = sparklines || {};
    el.innerHTML = (extended || []).map((item, i) => {
        const spark = item.spark_key && sp[item.spark_key]
            ? renderSparklineSvg(sp[item.spark_key], 'var(--ai-blue, #3B82F6)', 56, 22)
            : '';
        return `<div class="dash-exec-card" style="animation-delay:${i * 0.04}s">
            <div class="dash-exec-card-label">${item.label}</div>
            <div class="dash-exec-card-value">${fmtExecValue(item)}</div>
            <div class="dash-exec-card-foot">
                <span>${item.delta || ''}</span>
                <span>${spark}</span>
            </div>
        </div>`;
    }).join('');
}

function renderRiskBands(bands) {
    const el = document.getElementById('riskBandsContainer');
    if (!el) return;
    el.innerHTML = (bands || []).map((b) => `
        <div class="dash-risk-band">
            <span class="dash-risk-band-label" style="color:${b.color}">${b.label}</span>
            <div class="dash-risk-band-track">
                <div class="dash-risk-band-fill" style="width:${b.pct}%;background:${b.color};"></div>
            </div>
            <span class="dash-risk-band-pct">${b.pct}%</span>
        </div>
    `).join('');
}

function renderRiskRecommendation(rp) {
    const el = document.getElementById('riskRecommendation');
    if (!el || !rp) return;
    const tier = rp.tier || {};
    el.innerHTML = `<strong>Recomendación · ${tier.label || '—'} (P${tier.priority || '—'})</strong>
        ${rp.recommendation || '—'}`;
}

function renderCriticalAlertFeed(feed) {
    const el = document.getElementById('criticalAlertFeed');
    if (!el) return;
    if (!feed || !feed.length) {
        el.innerHTML = '<p style="color:var(--text-muted);padding:1rem;">Sin alertas críticas en el filtro actual.</p>';
        return;
    }
    el.innerHTML = feed.map((a, i) => {
        const monto = '$' + Number(a.monto || 0).toLocaleString('es-CO', { maximumFractionDigits: 0 });
        const prob = a.prob_fraude != null ? `<span class="dash-crit-badge score">IA ${a.prob_fraude}%</span>` : '';
        return `<article class="dash-crit-alert tier-${a.risk_tier}" data-case-id="${a.id_siniestro}" style="animation-delay:${i * 0.05}s">
            <div class="dash-crit-alert-head">
                <span class="dash-crit-id">${a.id_siniestro}</span>
                <div class="dash-crit-badges">
                    <span class="dash-crit-badge risk">${a.risk_label}</span>
                    <span class="dash-crit-badge score">${a.score}</span>
                    ${prob}
                </div>
            </div>
            <div class="dash-crit-meta">
                <span>Monto: <strong>${monto}</strong></span>
                <span>Fecha: ${a.fecha}</span>
            </div>
            <div class="dash-crit-anomaly">${a.anomaly}</div>
            <div class="dash-crit-action">→ ${a.action}</div>
        </article>`;
    }).join('');
    el.querySelectorAll('.dash-crit-alert').forEach((card) => {
        card.addEventListener('click', () => {
            if (typeof viewCase === 'function') viewCase(card.dataset.caseId);
        });
    });
}

function renderSocTimeline(events) {
    const el = document.getElementById('socTimeline');
    if (!el) return;
    if (!events || !events.length) {
        el.innerHTML = '<p style="color:var(--text-muted);">Sin eventos temporales.</p>';
        return;
    }
    el.innerHTML = events.map((ev, i) => `
        <div class="dash-tl-item type-${ev.type || 'info'}" style="animation-delay:${i * 0.06}s">
            <span class="dash-tl-dot"></span>
            <div class="dash-tl-time">${ev.time}</div>
            <div class="dash-tl-title">${ev.title}</div>
            <div class="dash-tl-detail">${ev.detail}</div>
        </div>
    `).join('');
}

function renderSparklineSvg(values, color, w = 72, h = 28) {
    const pts = (values || []).map(Number).filter((n) => Number.isFinite(n));
    if (pts.length < 2) {
        return `<svg class="dash-spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><line x1="4" y1="${h / 2}" x2="${w - 4}" y2="${h / 2}" stroke="${color}" stroke-opacity="0.25"/></svg>`;
    }
    const min = Math.min(...pts);
    const max = Math.max(...pts);
    const range = max - min || 1;
    const coords = pts.map((v, i) => {
        const x = 4 + (i / (pts.length - 1)) * (w - 8);
        const y = h - 4 - ((v - min) / range) * (h - 8);
        return `${x},${y}`;
    });
    return `<svg class="dash-spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
        <polyline fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" points="${coords.join(' ')}"/>
    </svg>`;
}

const DASH_ICON_SVG = {
    layers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>',
    alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    money: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
    brain: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9.5 2A5.5 5.5 0 0 0 4 7.5c0 .88.23 1.71.64 2.43L2 14h4l1 4h10l1-4h2.36A5.5 5.5 0 0 0 14.5 2"/></svg>',
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
};

function fmtKpiDisplay(item) {
    const v = item.value;
    if (item.format === 'currency') {
        return v >= 1e6 ? '$' + (v / 1e6).toFixed(1) + 'M' : '$' + Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
    }
    if (item.format === 'percent') return Number(v).toFixed(1) + '%';
    if (item.format === 'hours') return Number(v).toFixed(1) + 'h';
    if (item.format === 'score') return Number(v).toFixed(1);
    return Number(v || 0).toLocaleString('es-CO');
}

function initDashParticles() {
    const canvas = document.getElementById('dashParticles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let w = 0;
    let h = 0;
    const dots = [];
    const resize = () => {
        const parent = canvas.parentElement;
        if (!parent) return;
        w = canvas.width = parent.clientWidth;
        h = canvas.height = parent.clientHeight;
    };
    for (let i = 0; i < 48; i++) {
        dots.push({ x: Math.random(), y: Math.random(), r: Math.random() * 1.5 + 0.3, vx: (Math.random() - 0.5) * 0.0004, vy: (Math.random() - 0.5) * 0.0004 });
    }
    function frame() {
        if (!ctx || !w) { requestAnimationFrame(frame); return; }
        ctx.clearRect(0, 0, w, h);
        dots.forEach((d) => {
            d.x += d.vx;
            d.y += d.vy;
            if (d.x < 0 || d.x > 1) d.vx *= -1;
            if (d.y < 0 || d.y > 1) d.vy *= -1;
            ctx.beginPath();
            ctx.arc(d.x * w, d.y * h, d.r, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(59, 130, 246, 0.35)';
            ctx.fill();
        });
        requestAnimationFrame(frame);
    }
    resize();
    window.addEventListener('resize', resize);
    frame();
}

function renderHeroKpis(highlights) {
    const el = document.getElementById('dashHeroKpis');
    if (!el) return;
    const items = highlights && highlights.length ? highlights : [];
    el.innerHTML = items.map((h) => `
        <article class="dash-hero-card glow-${h.glow || 'blue'}">
            <div class="dash-hero-top">
                <span class="dash-hero-icon">${DASH_ICON_SVG[h.icon] || DASH_ICON_SVG.layers}</span>
                <span class="dash-hero-check">✔</span>
            </div>
            <div class="dash-hero-label">${h.label}</div>
            <div class="dash-hero-value">${fmtKpiDisplay(h)}</div>
            ${h.delta ? `<span class="dash-hero-delta ${h.delta_dir || 'neutral'}">${h.delta}</span>` : ''}
        </article>
    `).join('') || '<p style="color:var(--text-muted);grid-column:1/-1;">Ejecute el análisis para ver KPIs.</p>';
}

function renderExecGrid(extended, sparklines) {
    const el = document.getElementById('dashExecGrid');
    if (!el) return;
    const sp = sparklines || {};
    el.innerHTML = (extended || []).map((k) => {
        const spark = k.spark_key && sp[k.spark_key] ? renderSparklineSvg(sp[k.spark_key], 'var(--ai-blue, #3B82F6)', 56, 22) : '';
        return `<div class="dash-exec-card">
            <div class="dash-exec-card-label">${k.label}</div>
            <div style="display:flex;justify-content:space-between;align-items:flex-end;">
                <div class="dash-exec-card-value">${fmtKpiDisplay(k)}</div>
                ${spark}
            </div>
            <div class="dash-exec-card-foot"><span>${k.delta || ''}</span></div>
        </div>`;
    }).join('');
}

function renderRiskBands(bands) {
    const el = document.getElementById('dashRiskBands');
    if (!el) return;
    el.innerHTML = (bands || []).map((b) => `
        <div class="dash-risk-band">
            <span class="dash-risk-band-label">${b.label}</span>
            <div class="dash-risk-band-track"><div class="dash-risk-band-fill" style="width:${b.pct}%;background:${b.color};"></div></div>
            <span class="dash-risk-band-pct">${b.pct}%</span>
        </div>
    `).join('');
}

function renderCriticalAlertFeed(feed) {
    const el = document.getElementById('dashCriticalFeed');
    if (!el) return;
    if (!feed || !feed.length) {
        el.innerHTML = '<p style="color:var(--text-muted);padding:1rem;">Sin alertas críticas en el filtro actual.</p>';
        return;
    }
    el.innerHTML = feed.map((a, i) => `
        <article class="dash-crit-alert tier-${a.risk_tier}" style="animation-delay:${i * 0.05}s" data-case-id="${a.id_siniestro || ''}">
            <div class="dash-crit-alert-head">
                <span class="dash-crit-id">${a.id_siniestro}</span>
                <div class="dash-crit-badges">
                    <span class="dash-crit-badge risk">${a.risk_label}</span>
                    <span class="dash-crit-badge score">Score ${a.score}</span>
                </div>
            </div>
            <div class="dash-crit-meta">
                <span>Monto: $${Number(a.monto || 0).toLocaleString()}</span>
                <span>Fecha: ${a.fecha}</span>
                ${a.prob_fraude != null ? `<span>Prob. IA: ${a.prob_fraude}%</span>` : '<span></span>'}
                <span>${a.semaforo}</span>
            </div>
            <div class="dash-crit-anomaly">${a.anomaly}</div>
            <div class="dash-crit-action">→ ${a.action}</div>
        </article>
    `).join('');
    el.querySelectorAll('.dash-crit-alert').forEach((card) => {
        card.addEventListener('click', () => {
            if (typeof viewCase === 'function' && card.dataset.caseId) viewCase(card.dataset.caseId);
        });
    });
}

function renderSocTimeline(events) {
    const el = document.getElementById('dashSocTimeline');
    if (!el) return;
    if (!events || !events.length) {
        el.innerHTML = '<p style="color:var(--text-muted);">Sin eventos temporales.</p>';
        return;
    }
    el.innerHTML = events.map((e, i) => `
        <div class="dash-tl-item type-${e.type || 'info'}" style="animation-delay:${i * 0.06}s">
            <span class="dash-tl-dot"></span>
            <div class="dash-tl-time">${e.time}</div>
            <div class="dash-tl-title">${e.title}</div>
            <div class="dash-tl-detail">${e.detail}</div>
        </div>
    `).join('');
}

function renderRiskProfileUI(rp) {
    if (!rp) return;
    const rec = document.getElementById('dashRiskRecommendation');
    const tierEl = document.getElementById('dashRiskTierLabel');
    if (rec) rec.textContent = rp.recommendation || '—';
    if (tierEl && rp.tier) {
        tierEl.textContent = `${rp.tier.label} · Prioridad ${rp.tier.priority}`;
        tierEl.style.color = rp.tier.color;
    }
    renderRiskBands(rp.bands);
}

function buildDashboardShell() {
    return `
        <canvas id="dashParticles" aria-hidden="true"></canvas>
        <header class="dash-exec-header">
            <div class="dash-exec-header-main">
                <div class="dash-exec-title-row">
                    <h2>Centro de inteligencia de riesgo</h2>
                    <span class="dash-live-pill"><span class="dash-live-dot"></span> Tiempo real</span>
                </div>
                <div class="dash-soc-meta">
                    <span>IA: <strong id="dashIaStatus">Activo</strong></span>
                    <span>AUC: <strong id="kpiAuc">—</strong></span>
                    <span>Actualizado: <strong id="dashNow">—</strong></span>
                    <span id="fraudTrendLabel" class="dash-trend-chip neutral">—</span>
                </div>
                <div class="dash-health-bar-wrap">
                    <div class="dash-health-label"><span>Salud del motor</span><span id="modelStabilityPct">—</span></div>
                    <div class="dash-health-track"><div class="dash-health-fill" id="modelHealthBar" style="width:72%;"></div></div>
                </div>
            </div>
            <div class="dash-global-risk-gauge" id="globalRiskGauge">
                <div class="dash-gauge-ring" id="globalRiskRing"></div>
                <div class="dash-gauge-center">
                    <span class="dash-gauge-level" id="globalRiskLevel">—</span>
                    <span class="dash-gauge-sub" id="globalRiskSub">Riesgo global</span>
                </div>
            </div>
        </header>

        <section class="dash-ai-strip" id="aiInsightsStrip" aria-live="polite"></section>

        <div class="dash-section-tag">Indicadores ejecutivos</div>
        <div class="dash-hero-kpis dash-kpi-single-row" id="heroKpisContainer"></div>

        <section class="dash-risk-command">
            <div class="dash-section-tag">Sistema de score de riesgo · IA explicable</div>
            <div class="dash-risk-command-grid dash-risk-command-grid--2">
                <div class="dash-gauge-panel">
                    <h4>Score híbrido</h4>
                    <div id="chartScoreGauge" style="min-height:200px;"></div>
                    <div id="riskRecommendation" class="dash-rec-box"></div>
                </div>
                <div class="dash-gauge-panel">
                    <h4>Distribución por nivel</h4>
                    <div id="riskBandsContainer" class="dash-risk-bands"></div>
                    <div id="chartRadar" style="min-height:220px;margin-top:0.75rem;"></div>
                </div>
            </div>
        </section>

        <div class="dash-layout-duo" style="margin-bottom:1.25rem;">
            <div class="dash-panel">
                <div class="dash-panel-head">
                    <h3 class="dash-panel-title">Alertas críticas inteligentes</h3>
                    <span class="dash-panel-badge" id="critAlertCount">0</span>
                </div>
                <div id="criticalAlertFeed" class="dash-critical-feed"></div>
            </div>
            <div class="dash-panel">
                <div class="dash-panel-head"><h3 class="dash-panel-title">Timeline SOC · eventos</h3></div>
                <div id="socTimeline" class="dash-soc-timeline"></div>
            </div>
        </div>

        <section class="dash-geo-panel dash-panel card-chart">
            <div class="dash-panel-head">
                <h3 class="dash-panel-title">Mapa de calor antifraude</h3>
                <span class="dash-panel-badge" id="geoHeatmapLabel">Por zona</span>
            </div>
            <p class="dash-chart-help">Intensidad de fraude por ubicación (ciudad, sucursal o provincia según datos).</p>
            <div id="chartGeoFraud" class="chart-area"></div>
        </section>

        <span id="kpiTotal" style="display:none;"></span>
        <span id="kpiRojo" style="display:none;"></span>
        <span id="kpiMonto" style="display:none;"></span>
        <span id="kpiScore" style="display:none;"></span>
        <span id="kpiAlerts" style="display:none;"></span>
        <span id="kpiProbValue" style="display:none;"></span>
        <span id="kpiTotalSub" style="display:none;"></span>
        <span id="kpiRojoPct" style="display:none;"></span>
        <span id="kpiProbFraude" style="display:none;"></span>
        <span id="kpiCriticalTrend" style="display:none;"></span>
        <span id="sparkTotal" style="display:none;"></span>
        <span id="sparkCritical" style="display:none;"></span>
        <span id="sparkScore" style="display:none;"></span>
        <span id="sparkAlerts" style="display:none;"></span>

        <details class="dash-panel dash-filters-panel">
            <summary>Filtros de exploración (clic en gráficos para filtrar)</summary>
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

        <details class="dash-analyst-depth" style="display:none;" aria-hidden="true">
        <summary>Análisis profundo · gráficos avanzados</summary>

        <section class="dash-risk-hub">
            <h3 class="dash-section-title">Mapa central de riesgo</h3>
            <p class="dash-chart-help">Concentración, clusters y matriz score × monto. Clic para filtrar el universo.</p>
            <div class="dash-layout-main">
                <div class="dash-stack">
                    <div class="dash-panel card-chart dash-hub-primary">
                        <div class="dash-panel-head">
                            <h3 class="dash-panel-title">Treemap · exposición por ramo</h3>
                            <button type="button" class="chart-reset-btn" data-reset-scope="ramo" title="Limpiar">✕</button>
                        </div>
                        <div id="chartTreemap" class="chart-area" style="min-height:320px;"></div>
                    </div>
                    <div class="dash-panel card-chart">
                        <div class="dash-panel-head">
                            <h3 class="dash-panel-title">Matriz de riesgo (monto × score)</h3>
                        </div>
                        <div id="chartRiskMatrix" class="chart-area" style="min-height:280px;"></div>
                    </div>
                </div>
                <div class="dash-stack">
                    <div class="dash-panel card-chart">
                        <div class="dash-panel-head">
                            <h3 class="dash-panel-title">Semáforo de riesgo</h3>
                            <button type="button" class="chart-reset-btn" data-reset-scope="semaforo" title="Limpiar">✕</button>
                        </div>
                        <div class="donut-chart-wrap"><div id="chartSemaforo" class="chart-area chart-area-donut"></div></div>
                    </div>
                    <div class="dash-panel card-chart">
                        <div class="dash-panel-head">
                            <h3 class="dash-panel-title">Heatmap ramo × nivel</h3>
                            <button type="button" class="chart-reset-btn" data-reset-scope="all" title="Limpiar">✕</button>
                        </div>
                        <div id="chartHeatmapRamoRiesgo" class="chart-area" style="min-height:260px;"></div>
                    </div>
                    <div class="dash-panel card-chart dash-analyst-only">
                        <div class="dash-panel-head">
                            <h3 class="dash-panel-title">Distribución del score</h3>
                            <button type="button" class="chart-reset-btn" data-reset-scope="score" title="Limpiar">✕</button>
                        </div>
                        <div id="chartScores" class="chart-area" style="min-height:220px;"></div>
                    </div>
                </div>
            </div>
            <div class="dash-panel card-chart" style="margin-top:1rem;">
                <div class="dash-panel-head">
                    <h3 class="dash-panel-title">Mapa de burbujas · intensidad de fraude</h3>
                </div>
                <div id="chartBubble" class="chart-area" style="min-height:280px;"></div>
            </div>
        </section>

        <section class="dash-temporal-section">
            <h3 class="dash-section-title">Evolución temporal</h3>
            <div class="dash-layout-duo">
                <div class="dash-panel card-chart">
                    <div class="dash-panel-head">
                        <h3 class="dash-panel-title">Tendencia de fraude por mes</h3>
                        <button type="button" class="chart-reset-btn" data-reset-scope="fecha" title="Limpiar">✕</button>
                    </div>
                    <div id="chartTemporal" class="chart-area" style="min-height:260px;"></div>
                </div>
                <div class="dash-panel card-chart">
                    <div class="dash-panel-head">
                        <h3 class="dash-panel-title">Índice de alertas en el tiempo</h3>
                    </div>
                    <div id="chartTemporalAlerts" class="chart-area" style="min-height:260px;"></div>
                </div>
            </div>
        </section>

        <section class="dash-segments-section">
            <div class="dash-segment-head">
                <h3 class="dash-section-title">Análisis por segmentos</h3>
                <div class="dash-segment-tabs" id="segmentTabs">
                    <button type="button" class="dash-seg-tab active" data-segment="sucursal">Sucursal</button>
                    <button type="button" class="dash-seg-tab" data-segment="ramo">Ramo</button>
                    <button type="button" class="dash-seg-tab" data-segment="cobertura">Cobertura</button>
                    <button type="button" class="dash-seg-tab" data-segment="proveedor">Proveedor</button>
                </div>
            </div>
            <div class="dash-layout-duo">
                <div class="dash-panel card-chart">
                    <div class="dash-panel-head">
                        <h3 class="dash-panel-title" id="segmentChartTitle">Riesgo por sucursal</h3>
                        <button type="button" class="chart-reset-btn" data-reset-scope="sucursal" title="Limpiar">✕</button>
                    </div>
                    <div id="chartSegment" class="chart-area" style="min-height:300px;"></div>
                </div>
                <div class="dash-panel card-chart">
                    <div class="dash-panel-head">
                        <h3 class="dash-panel-title">Comparativo por ramo</h3>
                        <button type="button" class="chart-reset-btn" data-reset-scope="ramo" title="Limpiar">✕</button>
                    </div>
                    <div id="chartRamo" class="chart-area chart-area-ramo" style="min-height:300px;"></div>
                </div>
            </div>
            <div class="dash-panel card-chart dash-analyst-only" style="margin-top:1rem;">
                <div class="dash-panel-head">
                    <h3 class="dash-panel-title">Concentración geográfica (sucursal)</h3>
                </div>
                <div id="chartGeoOperacion" class="chart-area" style="min-height:260px;"></div>
            </div>
        </section>

        <section class="dash-alerts-console">
            <h3 class="dash-section-title">Motor de alertas inteligentes</h3>
            <div id="enrichedAlertsGrid" class="dash-alerts-grid"></div>
            <div class="dash-layout-duo" style="margin-top:1rem;">
                <div class="dash-panel">
                    <div class="dash-panel-head"><h3 class="dash-panel-title">Detalle de señales</h3></div>
                    <div class="dash-table-wrap" style="max-height:240px;">
                        <table class="dash-table">
                            <thead><tr><th>Señal</th><th>Casos</th><th>Severidad</th><th>Acción</th></tr></thead>
                            <tbody id="fraudSignalsTable"></tbody>
                        </table>
                    </div>
                    <div id="signalCasesPanel" class="dash-signal-panel">Seleccione una señal para ver casos vinculados.</div>
                </div>
                <div class="dash-panel">
                    <div class="dash-panel-head">
                        <h3 class="dash-panel-title">Reglas críticas RF-01..RF-07</h3>
                        <span class="dash-panel-badge" id="dashCriticalCount">0</span>
                    </div>
                    <div id="criticalRulesPanel"></div>
                </div>
            </div>
        </section>

        <section class="dash-smart-table-section">
            <div class="dash-panel-head" style="margin-bottom:0.75rem;">
                <h3 class="dash-section-title" style="margin:0;">Tabla inteligente de siniestros prioritarios</h3>
                <span class="dash-panel-badge">Top riesgo</span>
            </div>
            <div class="dash-table-wrap dash-smart-table-wrap">
                <table class="dash-table dash-smart-table">
                    <thead><tr>
                        <th></th><th>Siniestro</th><th>Score</th><th>Riesgo</th><th>Prioridad</th>
                        <th>Monto</th><th>Segmento</th><th>Alertas</th><th>Explicación IA</th><th></th>
                    </tr></thead>
                    <tbody id="criticalCasesTable"></tbody>
                </table>
            </div>
        </section>

        <div class="dash-layout-duo" style="margin-top:1.25rem;">
            <div class="dash-panel">
                <div class="dash-panel-head"><h3 class="dash-panel-title">Proveedores de alto riesgo</h3></div>
                <div class="dash-table-wrap" style="max-height:280px;">
                    <table class="dash-table">
                        <thead><tr><th>Proveedor</th><th>Casos</th><th>Score</th><th>Monto</th><th>Nivel</th></tr></thead>
                        <tbody id="providerRiskTable"></tbody>
                    </table>
                </div>
            </div>
            <div class="dash-panel">
                <div class="dash-panel-head"><h3 class="dash-panel-title">Stream de alertas</h3></div>
                <div id="alertsPanel" class="alerts-panel dash-alerts-stream"></div>
                <div id="topAnomaliesList" class="dash-anomalies-list" style="display:none;"></div>
            </div>
        </div>

        </details>

        <aside id="dashDetailDrawer" class="dash-detail-drawer" aria-hidden="true">
            <div class="dash-drawer-head">
                <h4 id="dashDrawerTitle">Detalle</h4>
                <button type="button" id="dashDrawerClose" aria-label="Cerrar">✕</button>
            </div>
            <div id="dashDrawerBody" class="dash-drawer-body"></div>
        </aside>
    `;
}

function setDashboardViewMode(mode) {
    dashboardState.viewMode = mode;
    const shell = document.getElementById('dashboardShell');
    if (shell) {
        shell.classList.toggle('dash-mode-analyst', mode === 'analyst');
        shell.classList.toggle('dash-mode-executive', mode === 'executive');
    }
    document.querySelectorAll('.dash-view-btn').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.view === mode);
    });
    scheduleDashboardChartsResize();
}

function openDashDrawer(caseId, summaryHtml) {
    const drawer = document.getElementById('dashDetailDrawer');
    const title = document.getElementById('dashDrawerTitle');
    const body = document.getElementById('dashDrawerBody');
    if (!drawer || !body) return;
    if (title) title.textContent = caseId || 'Detalle';
    body.innerHTML = summaryHtml || '<p style="color:var(--text-muted);">Cargando…</p>';
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
}

function closeDashDrawer() {
    const drawer = document.getElementById('dashDetailDrawer');
    if (drawer) {
        drawer.classList.remove('open');
        drawer.setAttribute('aria-hidden', 'true');
    }
}

function renderAiInsights(insights) {
    const strip = document.getElementById('aiInsightsStrip');
    if (!strip) return;
    const items = insights && insights.length ? insights : [{ type: 'info', text: 'Motor de riesgo listo. Ejecute el análisis para generar insights.' }];
    strip.innerHTML = items.map((ins) => `
        <div class="dash-ai-card dash-ai-${ins.type || 'info'}">
            <p>${ins.text}</p>
        </div>
    `).join('');
}

function renderGlobalRiskGauge(globalRisk) {
    const gr = globalRisk || {};
    const levelEl = document.getElementById('globalRiskLevel');
    const subEl = document.getElementById('globalRiskSub');
    const ring = document.getElementById('globalRiskRing');
    if (levelEl) levelEl.textContent = gr.level === 'alto' ? 'ALTO' : gr.level === 'medio' ? 'MEDIO' : 'BAJO';
    if (subEl) subEl.textContent = gr.label || 'Riesgo global';
    if (ring) {
        const color = gr.color || 'var(--cyan)';
        ring.style.background = `conic-gradient(${color} ${Math.min(100, gr.pct_critical || 30) * 3.6}deg, rgba(255,255,255,0.06) 0deg)`;
        ring.style.boxShadow = `0 0 24px ${color}44`;
    }
}

function renderEnrichedAlerts(alerts) {
    const grid = document.getElementById('enrichedAlertsGrid');
    if (!grid) return;
    if (!alerts || !alerts.length) {
        grid.innerHTML = '<div class="dash-alert-empty">Sin señales activas en el universo filtrado.</div>';
        return;
    }
    grid.innerHTML = alerts.slice(0, 8).map((a) => {
        const pCls = a.priority === 'critica' ? 'critica' : a.priority === 'alta' ? 'alta' : 'media';
        const impact = a.economic_impact >= 1e6
            ? '$' + (a.economic_impact / 1e6).toFixed(1) + 'M'
            : '$' + Number(a.economic_impact || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
        return `<article class="dash-alert-card dash-alert-${pCls}" data-signal="${a.signal}">
            <div class="dash-alert-card-top">
                <span class="dash-alert-priority">${a.severity || 'Media'}</span>
                <span class="dash-alert-score">Score ${a.score}</span>
            </div>
            <h4>${a.signal}</h4>
            <p class="dash-alert-explain">${a.explanation}</p>
            <div class="dash-alert-meta">
                <span>${(a.count || 0).toLocaleString()} casos</span>
                <span>Impacto ${impact}</span>
            </div>
            <div class="dash-alert-action">→ ${a.action}</div>
        </article>`;
    }).join('');
    grid.querySelectorAll('.dash-alert-card').forEach((card) => {
        card.addEventListener('click', () => {
            const sig = card.dataset.signal || '';
            const rows = document.querySelectorAll('#fraudSignalsTable tr[data-signal]');
            rows.forEach((row) => { if (row.dataset.signal === sig) row.click(); });
        });
    });
}

function renderCriticalCasesTable(cases) {
    const tbody = document.getElementById('criticalCasesTable');
    if (!tbody) return;
    const rows = cases && cases.length ? cases : [];
    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--text-muted);padding:1.5rem;">Sin casos con los filtros actuales.</td></tr>';
        return;
    }
    tbody.innerHTML = rows.slice(0, 40).map((c) => {
        const sc = Number(c.score ?? c.score_hibrido ?? c.score_reglas ?? 0);
        const sem = c.semaforo || c.semaforo_final || c.semaforo_reglas || 'Verde';
        const sevCls = sem === 'Rojo' ? 'rojo' : sem === 'Amarillo' ? 'amarillo' : 'verde';
        const bcls = sem === 'Rojo' ? 'badge-red' : sem === 'Amarillo' ? 'badge-yellow' : 'badge-green';
        const monto = '$' + Number(c.monto_reclamado || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
        const seg = [c.ramo, c.sucursal].filter(Boolean).join(' · ') || '—';
        const explain = c.alerta_resumen || (String(c.alertas_reglas || '').split('|')[0] || 'Sin alertas');
        const prio = c.prioridad || (sc >= 76 ? 'P1' : sc >= 41 ? 'P2' : 'P3');
        const prioCls = prio === 'P1' ? 'badge-red' : prio === 'P2' ? 'badge-yellow' : 'badge-green';
        const fillW = Math.min(100, sc);
        const fillColor = sem === 'Rojo' ? 'var(--red)' : sem === 'Amarillo' ? 'var(--yellow)' : 'var(--green)';
        const alertBadge = c.alertas_count > 0 ? `<span class="dash-alert-count">${c.alertas_count}</span>` : '—';
        return `<tr class="dash-case-tr" data-case-id="${c.id_siniestro}">
            <td><div class="dash-sev ${sevCls}"></div></td>
            <td><strong class="dash-case-id">${c.id_siniestro}</strong>
                <div class="dash-score-bar"><div class="dash-score-fill" style="width:${fillW}%;background:${fillColor};"></div></div></td>
            <td><span class="badge ${bcls}">${sc.toFixed(0)}</span></td>
            <td><span class="badge ${bcls}" style="font-size:0.65rem;">${sem}</span></td>
            <td><span class="badge ${prioCls}">${prio}</span></td>
            <td>${monto}</td>
            <td style="font-size:0.72rem;">${seg}</td>
            <td>${alertBadge}</td>
            <td class="dash-explain-cell" title="${explain}">${explain.slice(0, 48)}${explain.length > 48 ? '…' : ''}</td>
            <td><button type="button" class="dash-btn-analyze" data-analyze="${c.id_siniestro}">Ver</button></td>
        </tr>`;
    }).join('');
    tbody.querySelectorAll('.dash-case-tr').forEach((row) => {
        row.addEventListener('click', (e) => {
            if (e.target.closest('.dash-btn-analyze')) return;
            const id = row.dataset.caseId;
            const c = rows.find((x) => x.id_siniestro === id);
            if (c) {
                openDashDrawer(id, `<p><strong>Score:</strong> ${c.score}</p><p><strong>Semáforo:</strong> ${c.semaforo}</p><p><strong>Resumen:</strong> ${c.alerta_resumen || '—'}</p><button class="btn btn-primary btn-sm" style="margin-top:0.75rem;" type="button" id="drawerOpenCase">Abrir expediente</button>`);
                const btn = document.getElementById('drawerOpenCase');
                if (btn) btn.onclick = () => { if (typeof viewCase === 'function') viewCase(id); closeDashDrawer(); };
            }
        });
    });
    tbody.querySelectorAll('.dash-btn-analyze').forEach((btn) => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (typeof viewCase === 'function') viewCase(btn.dataset.analyze);
        });
    });
}

function renderSegmentChart(data, segmentKey) {
    const segments = (data.segment_data || {})[segmentKey] || [];
    const C = getColors();
    const PL = getPlotlyLayout();
    const labels = segments.map((s) => String(s.label || '').slice(0, 28));
    const rojos = segments.map((s) => s.rojos || 0);
    const amarillos = segments.map((s) => s.amarillos || 0);
    const verdes = segments.map((s) => s.verdes || Math.max(0, (s.casos || 0) - (s.rojos || 0) - (s.amarillos || 0)));
    const titles = { sucursal: 'Sucursal', ramo: 'Ramo', cobertura: 'Cobertura', proveedor: 'Proveedor' };
    const titleEl = document.getElementById('segmentChartTitle');
    if (titleEl) titleEl.textContent = `Riesgo por ${titles[segmentKey] || segmentKey}`;
    safePlotlyReact('chartSegment',
        buildStackedRiskTraces(labels.length ? labels : ['—'], verdes, amarillos, rojos, C, ['Bajo', 'Medio', 'Alto']),
        dashStackedLayout(PL, C, { height: 320, bottom: 80, tickangle: -28, legendY: -0.28 }),
        { ...PLOTLY_CONFIG, responsive: true }
    );
    const chartEl = document.getElementById('chartSegment');
    if (chartEl && !chartEl._plotlyClickBound) {
        chartEl.on('plotly_click', (ev) => {
            const label = ev.points[0].x;
            const filterKey = segmentKey === 'proveedor' ? null : segmentKey;
            if (filterKey && label) setDashboardFilter(filterKey, label);
        });
        chartEl._plotlyClickBound = true;
    }
}

function bindDashboardEvents() {
    document.querySelectorAll('.dash-seg-tab').forEach((tab) => {
        tab.addEventListener('click', () => {
            dashboardState.segmentTab = tab.dataset.segment || 'sucursal';
            document.querySelectorAll('.dash-seg-tab').forEach((t) => t.classList.toggle('active', t === tab));
            if (dashboardState.lastData) renderSegmentChart(dashboardState.lastData, dashboardState.segmentTab);
        });
    });

    const closeDrawer = document.getElementById('dashDrawerClose');
    if (closeDrawer) closeDrawer.addEventListener('click', closeDashDrawer);

    document.getElementById('btnApplyFilters')?.addEventListener('click', () => {
        syncFiltersFromForm();
        dashboardState.filters.semaforo = document.getElementById('filterSemaforo').value;
        updateSemaforoPills();
        updateFilterChips();
        refreshDashboard();
    });
    document.getElementById('btnResetFilters')?.addEventListener('click', clearDashboardFilters);

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

    const bindClick = (el, handler) => {
        if (!el || el._plotlyClickBound) return;
        if (!el.querySelector('.plotly-graph-div') && !el.querySelector('.js-plotly-plot')) return;
        try {
            el.on('plotly_click', handler);
            el._plotlyClickBound = true;
        } catch (e) { /* ignore */ }
    };

    bindClick(chartScores, (ev) => {
        const pt = ev.points[0];
        const ranges = (dashboardState.lastData && dashboardState.lastData.score_distribution
            && dashboardState.lastData.score_distribution.click_ranges) || [];
        const band = ranges[pt.pointNumber] || ranges.find((r) => r.label === pt.x);
        if (band) {
            setDashboardFilter('score_min', String(band.min), false);
            setDashboardFilter('score_max', String(band.max), false);
            const smin = document.getElementById('filterScoreMin');
            const smax = document.getElementById('filterScoreMax');
            const rmin = document.getElementById('filterScoreMinRange');
            const rmax = document.getElementById('filterScoreMaxRange');
            if (smin) smin.value = dashboardState.filters.score_min;
            if (smax) smax.value = dashboardState.filters.score_max;
            if (rmin) rmin.value = dashboardState.filters.score_min;
            if (rmax) rmax.value = dashboardState.filters.score_max;
            refreshDashboard();
        }
    });

    bindClick(chartSemaforo, (ev) => {
        const label = ev.points[0].label;
        setDashboardFilter('semaforo', label);
        document.getElementById('filterSemaforo').value = label;
    });

    bindClick(chartRamo, (ev) => {
        const ramo = ev.points[0].x;
        setDashboardFilter('ramo', ramo);
    });

    bindClick(chartTemporal, (ev) => {
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
}

function renderDashboardCharts(data) {
    if (typeof Plotly === 'undefined') {
        console.error('Plotly no está disponible.');
        return;
    }
    const C = getColors(), PL = getPlotlyLayout();
    const theme = getAppTheme();
    const sem = normalizeSemaforoCounts(data.semaforo || {});
    const rojo = sem.Rojo, amarillo = sem.Amarillo, verde = sem.Verde;
    const totalSem = rojo + amarillo + verde || Number(data.total) || 1;

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

    const treemap = data.treemap_data || [];
    if (treemap.length) {
        safePlotlyReact('chartTreemap', [{
            type: 'treemap',
            labels: treemap.map((t) => t.label),
            parents: treemap.map(() => ''),
            values: treemap.map((t) => t.value),
            text: treemap.map((t) => `${t.label}<br>${t.casos} casos · score ${t.score_avg}`),
            textinfo: 'label+text',
            marker: {
                colors: treemap.map((t) => {
                    const s = t.score_avg || 0;
                    return s >= 76 ? C.red : s >= 41 ? C.yellow : C.green;
                }),
                line: { width: 1, color: C.bgCard || '#0b1120' },
            },
            hovertemplate: '<b>%{label}</b><br>Monto: %{value:,.0f}<extra></extra>',
        }], {
            ...PL,
            height: 340,
            margin: { t: 8, b: 8, l: 8, r: 8 },
        }, { ...PLOTLY_CONFIG, responsive: true });
        const treemapEl = document.getElementById('chartTreemap');
        if (treemapEl && !treemapEl._plotlyClickBound) {
            treemapEl.on('plotly_click', (ev) => {
                const label = ev.points[0].label;
                if (label) setDashboardFilter('ramo', label.split('<')[0].trim());
            });
            treemapEl._plotlyClickBound = true;
        }
    }

    const matrix = data.risk_matrix || {};
    if (matrix.z && matrix.z.length) {
        safePlotlyReact('chartRiskMatrix', [{
            z: matrix.z,
            x: matrix.x_labels || [],
            y: matrix.y_labels || [],
            type: 'heatmap',
            colorscale: [[0, '#0b1220'], [0.35, 'rgba(255,77,79,0.35)'], [1, '#FF4D4F']],
            showscale: true,
            text: matrix.z.map((row) => row.map((v) => fmtChartNum(v) || '0')),
            texttemplate: '%{text}',
            textfont: { size: 11, color: '#fff' },
            hovertemplate: 'Monto: %{y}<br>Score: %{x}<br>Casos: %{z}<extra></extra>',
        }], {
            ...PL,
            height: 300,
            margin: { t: 16, b: 56, l: 88, r: 40 },
            xaxis: { title: { text: 'Banda de score', font: { size: 11, color: C.muted } }, ...dashBarAxis(C) },
            yaxis: { title: { text: 'Banda de monto', font: { size: 11, color: C.muted } }, ...dashBarAxis(C) },
        }, { ...PLOTLY_CONFIG, responsive: true });
    }

    const topForBubble = (data.top_cases || []).slice(0, 120);
    if (topForBubble.length) {
        const scores = topForBubble.map((c) => Number(c.score_hibrido ?? c.score_reglas ?? 0));
        const montos = topForBubble.map((c) => Number(c.monto_reclamado || 0));
        const colors = topForBubble.map((c) => {
            const sem = c.semaforo_final || c.semaforo_reglas || 'Verde';
            return sem === 'Rojo' ? C.red : sem === 'Amarillo' ? C.yellow : C.green;
        });
        const sizes = montos.map((m) => Math.max(8, Math.min(36, Math.sqrt(m / 5000))));
        safePlotlyReact('chartBubble', [{
            x: scores,
            y: montos,
            mode: 'markers',
            type: 'scatter',
            marker: { size: sizes, color: colors, opacity: 0.75, line: { width: 1, color: '#fff' } },
            text: topForBubble.map((c) => c.id_siniestro),
            hovertemplate: '<b>%{text}</b><br>Score: %{x}<br>Monto: %{y:,.0f}<extra></extra>',
        }], {
            ...PL,
            height: 300,
            margin: { t: 16, b: 48, l: 64, r: 16 },
            xaxis: { title: { text: 'Score de riesgo', font: { size: 11, color: C.muted } }, ...dashBarAxis(C) },
            yaxis: { title: { text: 'Monto reclamado', font: { size: 11, color: C.muted } }, ...dashBarAxis(C) },
        }, { ...PLOTLY_CONFIG, responsive: true });
    }

    const sparkAlert = (data.sparklines || {}).alert_trend || [];
    const monthsA = (data.temporal_risk_data || []).map((t) => t.mes);
    safePlotlyReact('chartTemporalAlerts', [{
        x: monthsA.length ? monthsA : ['—'],
        y: sparkAlert.length ? sparkAlert : monthsA.map(() => 0),
        type: 'scatter',
        mode: 'lines+markers',
        fill: 'tozeroy',
        fillcolor: 'rgba(255,77,79,0.12)',
        line: { color: C.red, width: 2 },
        marker: { size: 6, color: C.red },
        name: 'Índice de alertas',
    }], {
        ...PL,
        height: 280,
        margin: { t: 16, b: 56, l: 48, r: 16 },
        xaxis: { ...dashBarAxis(C), tickangle: -25 },
        yaxis: { title: { text: 'Intensidad', font: { size: 11, color: C.muted } }, ...dashBarAxis(C) },
        showlegend: false,
    }, { ...PLOTLY_CONFIG, responsive: true });

    renderSegmentChart(data, dashboardState.segmentTab || 'sucursal');

    const rp = data.risk_profile || {};
    if (rp.score != null) {
        const tierColor = (rp.tier && rp.tier.color) || C.red;
        const gaugeLayout = { ...PL, height: 200, margin: { t: 36, b: 8, l: 24, r: 24 } };
        const steps = [
            { range: [0, 40], color: 'rgba(0,200,83,0.28)' },
            { range: [40, 75], color: 'rgba(245,183,0,0.32)' },
            { range: [75, 100], color: 'rgba(255,77,79,0.38)' },
        ];
        safePlotlyReact('chartScoreGauge', [{
            type: 'indicator',
            mode: 'gauge+number',
            value: rp.score,
            number: { suffix: '/100', font: { size: 26, color: C.text } },
            gauge: {
                axis: { range: [0, 100], tickcolor: C.muted, tickwidth: 1 },
                bar: { color: tierColor, thickness: 0.72 },
                bgcolor: 'rgba(255,255,255,0.04)',
                borderwidth: 0,
                steps,
            },
        }], gaugeLayout, { ...PLOTLY_CONFIG, responsive: true });

        if (rp.radar && rp.radar.labels && rp.radar.labels.length) {
            safePlotlyReact('chartRadar', [{
                type: 'scatterpolar',
                r: rp.radar.values,
                theta: rp.radar.labels,
                fill: 'toself',
                fillcolor: 'rgba(59,130,246,0.18)',
                line: { color: C.cyan, width: 2 },
            }], {
                ...PL,
                height: 220,
                margin: { t: 24, b: 24, l: 48, r: 48 },
                showlegend: false,
                polar: {
                    bgcolor: 'transparent',
                    radialaxis: { visible: true, range: [0, 100], gridcolor: C.grid, tickfont: { size: 9, color: C.muted } },
                    angularaxis: { gridcolor: C.grid, tickfont: { size: 9, color: C.muted } },
                },
            }, { ...PLOTLY_CONFIG, responsive: true });
        }
    }

    const geoHeatmap = data.geo_fraud_heatmap || {};
    if (geoHeatmap.locations && geoHeatmap.locations.length) {
        const colors = geoHeatmap.intensity.map((v) => {
            if (v >= 60) return '#B91C1C';
            if (v >= 40) return '#FF4D4F';
            if (v >= 25) return '#F5B700';
            return '#3B82F6';
        });
        safePlotlyReact('chartGeoFraud', [{
            type: 'bar',
            orientation: 'h',
            y: geoHeatmap.locations.map((l) => String(l).slice(0, 32)),
            x: geoHeatmap.intensity,
            marker: { color: colors, opacity: 0.92 },
            text: (geoHeatmap.casos || []).map((c, i) => `${c} · ${(geoHeatmap.rojos || [])[i] || 0} crít.`),
            textposition: 'outside',
            textfont: { size: 10, color: C.muted },
            hovertemplate: '<b>%{y}</b><br>Intensidad: %{x:.1f}<extra></extra>',
        }], {
            ...PL,
            height: Math.max(300, geoHeatmap.locations.length * 32),
            margin: { t: 12, b: 40, l: 8, r: 56 },
            xaxis: { title: { text: 'Índice de intensidad antifraude', font: { size: 11, color: C.muted } }, ...dashBarAxis(C) },
            yaxis: { ...dashBarAxis(C), automargin: true },
        }, { ...PLOTLY_CONFIG, responsive: true });
    }

    bindPlotlyDashboardCharts(data);
    scheduleDashboardChartsResize();
}

function resizeDashboardCharts() {
    if (typeof Plotly === 'undefined') return;
    ['chartSemaforo', 'chartScores', 'chartRamo', 'chartTemporal', 'chartHeatmapRamoRiesgo', 'chartGeoOperacion',
        'chartTreemap', 'chartRiskMatrix', 'chartBubble', 'chartTemporalAlerts', 'chartSegment',
        'chartScoreGauge', 'chartRadar', 'chartGeoFraud'].forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        try {
            if (el.querySelector('.plotly-graph-div') || el.querySelector('.js-plotly-plot')) {
                Plotly.Plots.resize(el);
            }
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
            if (dashboardState.lastData && dashboardState.lastData.executive_dashboard) {
                const prec = Math.min(99, Math.round((m.auc_roc || 0.85) * 100));
                const h = dashboardState.lastData.executive_dashboard.highlights;
                const pItem = h && h.find((x) => x.key === 'precision');
                if (pItem) {
                    pItem.value = prec;
                    renderHeroKpis(h);
                }
            }
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

    const setText = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
    const ed = data.executive_dashboard || {};
    renderHeroKpis(ed.highlights);
    const rp = data.risk_profile || {};
    renderRiskBands(rp.bands);
    renderRiskRecommendation(rp);
    renderCriticalAlertFeed(data.critical_alert_feed);
    renderSocTimeline(data.soc_timeline);
    const critCnt = document.getElementById('critAlertCount');
    if (critCnt) critCnt.textContent = String((data.critical_alert_feed || []).length);
    const geoLbl = document.getElementById('geoHeatmapLabel');
    if (geoLbl && data.geo_fraud_heatmap) {
        geoLbl.textContent = 'Por ' + (data.geo_fraud_heatmap.column || 'zona');
    }
    if (rp.tier && document.getElementById('globalRiskLevel')) {
        document.getElementById('globalRiskLevel').textContent = rp.tier.label.toUpperCase();
    }

    const kpiTotalVal = isFiltered ? data.total : analyzedTotal;
    const kpiTotalEl = document.getElementById('kpiTotal');
    if (kpiTotalEl) kpiTotalEl.textContent = kpiTotalVal.toLocaleString();
    const kpiSub = document.getElementById('kpiTotalSub');
    if (kpiSub) kpiSub.textContent = isFiltered
        ? `de ${analyzedTotal.toLocaleString()} analizados`
        : (sourceTotal > analyzedTotal ? `de ${sourceTotal.toLocaleString()} cargados` : 'Analizados');
    const ek = data.executive_kpis || {};
    setText('kpiRojo', rojo.toLocaleString());
    setText('kpiRojoPct', `${pctOf(rojo)}% del filtro`);
    const montoComp = ek.monto_potencial_riesgo ?? data.monto_rojo ?? 0;
    const montoEl = document.getElementById('kpiMonto');
    if (montoEl) {
        montoEl.textContent = montoComp >= 1e6
            ? '$' + (montoComp / 1e6).toFixed(1) + 'M'
            : '$' + Number(montoComp).toLocaleString(undefined, { maximumFractionDigits: 0 });
    }
    const aucEl = document.getElementById('kpiAuc');
    if (aucEl) aucEl.textContent = dashboardState.metricsAuc;
    setText('kpiScore', String(data.score_promedio));
    const alertCount = (data.signals_summary || []).reduce((a, s) => a + (s.count || 0), 0) || rojo + amarillo;
    const alertsEl = document.getElementById('kpiAlerts');
    if (alertsEl) alertsEl.textContent = alertCount.toLocaleString();
    const now = document.getElementById('dashNow');
    if (now) now.textContent = new Date().toLocaleString('es-EC');
    const iaStatus = document.getElementById('dashIaStatus');
    if (iaStatus) iaStatus.textContent = (dashboardState.metricsAuc !== '--' && Number(dashboardState.metricsAuc) > 0) ? 'Modelo supervisado activo' : 'Reglas + anomalías';

    setText('kpiProbFraude', 'Señales ' + (data.enriched_alerts || []).length);
    setText(
        'kpiClasificacion',
        `Rojo ${(ek.riesgo_alto || 0).toLocaleString()} · Amarillo ${(ek.riesgo_medio || 0).toLocaleString()} · Verde ${(ek.riesgo_bajo || 0).toLocaleString()}`
    );

    updateFilterChips();
    const topCases = data.top_cases || [];
    const casesTable = (data.cases_analytics && data.cases_analytics.length) ? data.cases_analytics : topCases;
    renderCriticalCasesTable(casesTable);
    renderAnomaliesList(topCases);
    renderSemaforoLegend(rojo, amarillo, verde, totalSafe, pctOf);

    const alerts = document.getElementById('alertsPanel');
    if (!alerts) { ensurePlotlyThenRenderCharts(data); return; }
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
            const sigEsc = String(s.signal || '').replace(/"/g, '&quot;');
            return `<tr class="signal-row-clickable" data-signal="${sigEsc}" style="cursor:pointer;"><td>${s.signal}</td><td>${(s.count || 0).toLocaleString()}</td><td><span class="badge ${cls}">${sev}</span></td><td>${action}</td></tr>`;
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

    ensurePlotlyThenRenderCharts(data);
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
        const optResp = await fetch(
            '/api/dashboard-filters',
            typeof withFraudiaSessionHeaders === 'function'
                ? withFraudiaSessionHeaders({ headers: dashHeaders })
                : { headers: dashHeaders },
        );
        const opts = await optResp.json();
        if (!optResp.ok || opts.error) {
            container.innerHTML = '<div class="alert alert-warning">' + (opts.error || 'No hay datos analizados') +
                '. Vuelva a <strong>Carga de Datos</strong> y pulse <strong>Iniciar análisis de riesgo</strong>.</div>';
            return;
        }
        dashboardState.options = opts;
        setFilterDefaultsFromOptions(opts);
        if (!dashboardState.initialized) {
            dashboardState.filters = emptyDashboardFilters();
            container.innerHTML = '<div id="dashboardShell" class="dash-premium dash-mode-executive">' + buildDashboardShell() + '</div>';
            bindDashboardEvents();
            populateFilterControls(opts);
            updateSemaforoPills();
            dashboardState.initialized = true;
            initDashParticles();
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
function loadDashboard() { return initDashboard(); }

if (typeof window !== 'undefined') {
    window.initDashboard = initDashboard;
    window.loadDashboard = loadDashboard;
}
