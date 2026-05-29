/**
 * FXecure — Bandeja de casos con tabla filtrable estilo Excel.
 */
const CasesBandeja = (function () {
    let allCases = [];
    let filtered = [];

    const FILTER_COLS = {
        tipo_ramo: 'filterRamoBandeja',
        cobertura: 'filterCoberturaBandeja',
        tipo_semaforo: 'filterSemaforoBandeja',
    };

    function sessionHeaders() {
        const h = { 'Content-Type': 'application/json' };
        try {
            const sid = sessionStorage.getItem('fxecure_session_id') || sessionStorage.getItem('fraudia_session_id');
            if (sid) {
                h['X-FXecure-Session'] = sid;
                h['X-FraudIA-Session'] = sid;
            }
        } catch (e) { /* ignore */ }
        return h;
    }

    function shellHtml() {
        return `
            <div class="section-header">
                <h2>Bandeja de casos</h2>
                <div class="section-line"></div>
            </div>
            <p class="bandeja-intro">Revise todos los siniestros analizados. Los casos de mayor prioridad aparecen primero; use los filtros como en Excel.</p>
            <details class="dash-panel bandeja-criticos-panel" open>
                <summary>▸ Casos críticos — factores y señales</summary>
                <div class="bandeja-criticos-grid">
                    <div class="bandeja-factores" id="bandejaFactoresPanel">
                        <h4>Factores principales (casos prioritarios)</h4>
                        <ul id="bandejaFactoresList"></ul>
                    </div>
                    <div class="bandeja-senales-wrap">
                        <h4>Señales detectadas</h4>
                        <div class="dash-table-wrap">
                            <table class="dash-table">
                                <thead><tr><th>Señal</th><th>Casos</th><th>Severidad</th></tr></thead>
                                <tbody id="bandejaSenalesTable"></tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </details>
            <div class="bandeja-filters card" style="margin:1rem 0;">
                <div class="bandeja-filter-row">
                    <label>Tipo de ramo <select id="filterRamoBandeja"><option value="">Todos</option></select></label>
                    <label>Cobertura <select id="filterCoberturaBandeja"><option value="">Todas</option></select></label>
                    <label>Tipo de semáforo <select id="filterSemaforoBandeja"><option value="">Todos</option></select></label>
                    <label>Monto mín. <input type="number" id="filterMontoMin" placeholder="0" min="0"></label>
                    <label>Monto máx. <input type="number" id="filterMontoMax" placeholder="Sin límite" min="0"></label>
                    <label>Score mín. <input type="number" id="filterScoreMinBandeja" min="0" max="100"></label>
                    <label>Score máx. <input type="number" id="filterScoreMaxBandeja" min="0" max="100"></label>
                    <button type="button" class="btn btn-secondary" id="btnClearBandejaFilters">Limpiar filtros</button>
                </div>
                <p class="dash-chart-help" id="bandejaCountLabel">—</p>
            </div>
            <div class="table-container bandeja-table-wrap">
                <table class="dash-table bandeja-data-table" id="bandejaMainTable">
                    <thead><tr>
                        <th>ID</th><th>Ramo</th><th>Cobertura</th><th>Monto</th><th>Score</th><th>Semáforo</th><th>Alertas</th><th></th>
                    </tr></thead>
                    <tbody id="bandejaTableBody"></tbody>
                </table>
            </div>
        `;
    }

    function uniqueValues(key) {
        const s = new Set();
        allCases.forEach((c) => {
            const v = c[key];
            if (v != null && String(v).trim() !== '') s.add(String(v));
        });
        return [...s].sort();
    }

    function fillSelect(id, values) {
        const sel = document.getElementById(id);
        if (!sel) return;
        const current = sel.value;
        sel.innerHTML = '<option value="">Todos</option>' + values.map((v) =>
            `<option value="${escapeAttr(v)}">${escapeHtml(v)}</option>`
        ).join('');
        if (values.includes(current)) sel.value = current;
    }

    function applyFilters() {
        const ramo = document.getElementById('filterRamoBandeja')?.value || '';
        const cob = document.getElementById('filterCoberturaBandeja')?.value || '';
        const sem = document.getElementById('filterSemaforoBandeja')?.value || '';
        const mMin = parseFloat(document.getElementById('filterMontoMin')?.value);
        const mMax = parseFloat(document.getElementById('filterMontoMax')?.value);
        const sMin = parseFloat(document.getElementById('filterScoreMinBandeja')?.value);
        const sMax = parseFloat(document.getElementById('filterScoreMaxBandeja')?.value);

        filtered = allCases.filter((c) => {
            const ramoKey = c.tipo_ramo ?? c.ramo;
            const semKey = c.tipo_semaforo ?? c.semaforo_final ?? c.semaforo_reglas;
            const score = Number(c.score ?? c.score_hibrido ?? 0);
            const monto = Number(c.monto_reclamado ?? 0);
            if (ramo && String(ramoKey) !== ramo) return false;
            if (cob && String(c.cobertura) !== cob) return false;
            if (sem && String(semKey) !== sem) return false;
            if (!Number.isNaN(mMin) && document.getElementById('filterMontoMin')?.value !== '' && monto < mMin) return false;
            if (!Number.isNaN(mMax) && document.getElementById('filterMontoMax')?.value !== '' && monto > mMax) return false;
            if (!Number.isNaN(sMin) && document.getElementById('filterScoreMinBandeja')?.value !== '' && score < sMin) return false;
            if (!Number.isNaN(sMax) && document.getElementById('filterScoreMaxBandeja')?.value !== '' && score > sMax) return false;
            return true;
        });
        renderTable();
    }

    function renderTable() {
        const tbody = document.getElementById('bandejaTableBody');
        const lbl = document.getElementById('bandejaCountLabel');
        if (!tbody) return;
        if (lbl) lbl.textContent = `Mostrando ${filtered.length.toLocaleString()} de ${allCases.length.toLocaleString()} siniestros`;
        if (!filtered.length) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:1.5rem;color:var(--text-muted);">Sin registros con los filtros actuales.</td></tr>';
            return;
        }
        const sorted = [...filtered].sort((a, b) =>
            Number(b.score ?? b.score_hibrido ?? 0) - Number(a.score ?? a.score_hibrido ?? 0)
        );
        tbody.innerHTML = sorted.map((c) => {
            const sem = c.tipo_semaforo ?? c.semaforo_final ?? 'Verde';
            const bcls = sem === 'Rojo' ? 'badge-red' : sem === 'Amarillo' ? 'badge-yellow' : 'badge-green';
            const sc = Number(c.score ?? c.score_hibrido ?? 0);
            const id = c.id_siniestro;
            return `<tr>
                <td style="color:var(--cyan);font-weight:600;">${escapeHtml(id)}</td>
                <td>${escapeHtml(c.tipo_ramo ?? c.ramo ?? '')}</td>
                <td>${escapeHtml(c.cobertura ?? '')}</td>
                <td>$${Number(c.monto_reclamado || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                <td><span class="badge ${bcls}">${sc.toFixed(1)}</span></td>
                <td><span class="badge ${bcls}">${escapeHtml(sem)}</span></td>
                <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeAttr(c.alertas_reglas || '')}">${escapeHtml((c.alertas_reglas || '—').slice(0, 60))}</td>
                <td><button type="button" class="btn btn-ghost btn-sm" data-case-detail="${escapeAttr(id)}">Detalle</button></td>
            </tr>`;
        }).join('');
        tbody.querySelectorAll('[data-case-detail]').forEach((btn) => {
            btn.addEventListener('click', () => {
                if (typeof viewCase === 'function') viewCase(btn.dataset.caseDetail);
            });
        });
    }

    async function loadCriticosMeta() {
        try {
            const resp = await fetch('/api/dashboard-data', { headers: sessionHeaders() });
            const data = await resp.json();
            if (data.error) return;
            const signals = data.signals_summary || [];
            const tbody = document.getElementById('bandejaSenalesTable');
            if (tbody) {
                tbody.innerHTML = signals.slice(0, 12).map((s) => `
                    <tr><td>${escapeHtml(s.signal || s.name || '—')}</td>
                    <td>${(s.count || 0).toLocaleString()}</td>
                    <td>${escapeHtml(s.severity || '—')}</td></tr>
                `).join('') || '<tr><td colspan="3">Sin señales</td></tr>';
            }
            const factList = document.getElementById('bandejaFactoresList');
            const top = (data.top_cases || []).slice(0, 8);
            if (factList) {
                factList.innerHTML = top.map((c) => {
                    const reglas = String(c.alertas_reglas || '').split('|').map((x) => x.trim()).filter(Boolean);
                    const factor = reglas[0] || 'Score elevado sin regla nominal';
                    return `<li><strong>${escapeHtml(c.id_siniestro)}</strong> — ${escapeHtml(factor)} (score ${Number(c.score_hibrido || 0).toFixed(0)})</li>`;
                }).join('') || '<li>No hay casos críticos en el filtro actual.</li>';
            }
        } catch (e) {
            console.warn('bandeja meta', e);
        }
    }

    function bindFilters() {
        ['filterRamoBandeja', 'filterCoberturaBandeja', 'filterSemaforoBandeja',
            'filterMontoMin', 'filterMontoMax', 'filterScoreMinBandeja', 'filterScoreMaxBandeja',
        ].forEach((id) => {
            document.getElementById(id)?.addEventListener('input', applyFilters);
            document.getElementById(id)?.addEventListener('change', applyFilters);
        });
        document.getElementById('btnClearBandejaFilters')?.addEventListener('click', () => {
            ['filterRamoBandeja', 'filterCoberturaBandeja', 'filterSemaforoBandeja'].forEach((id) => {
                const el = document.getElementById(id);
                if (el) el.value = '';
            });
            ['filterMontoMin', 'filterMontoMax', 'filterScoreMinBandeja', 'filterScoreMaxBandeja'].forEach((id) => {
                const el = document.getElementById(id);
                if (el) el.value = '';
            });
            applyFilters();
        });
    }

    function escapeHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
    function escapeAttr(s) {
        return escapeHtml(s).replace(/"/g, '&quot;');
    }

    async function init() {
        const container = document.getElementById('casesContent');
        if (!container) return;
        container.innerHTML = '<div class="alert alert-info"><span class="spinner"></span> Cargando bandeja…</div>';
        try {
            const resp = await fetch('/api/cases-all', { headers: sessionHeaders() });
            const data = await resp.json();
            if (data.error || !data.cases) {
                container.innerHTML = `<div class="alert alert-info">${escapeHtml(data.error || 'Ejecute el análisis desde Carga de datos.')}</div>`;
                return;
            }
            allCases = data.cases;
            filtered = [...allCases];
            container.innerHTML = shellHtml();
            fillSelect('filterRamoBandeja', uniqueValues('tipo_ramo').concat(uniqueValues('ramo')));
            fillSelect('filterCoberturaBandeja', uniqueValues('cobertura'));
            fillSelect('filterSemaforoBandeja', uniqueValues('tipo_semaforo'));
            bindFilters();
            renderTable();
            loadCriticosMeta();
        } catch (e) {
            container.innerHTML = `<div class="alert alert-danger">Error al cargar la bandeja: ${escapeHtml(e.message)}</div>`;
        }
    }

    return { init };
})();

window.CasesBandeja = CasesBandeja;
