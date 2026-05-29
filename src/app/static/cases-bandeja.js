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
            <p class="bandeja-intro">Revise todos los siniestros analizados. Los casos de mayor prioridad aparecen primero; use los filtros para acotar la tabla.</p>
            <div class="dash-panel bandeja-filters-panel">
                <div class="dash-panel-head">
                    <h3 class="dash-panel-title">Filtros de búsqueda</h3>
                </div>
                <div class="bandeja-filters-body">
                    <div class="dashboard-toolbar-grid bandeja-toolbar-grid">
                        <div class="dashboard-filter">
                            <label for="filterRamoBandeja">Tipo de ramo</label>
                            <select id="filterRamoBandeja"><option value="">Todos</option></select>
                        </div>
                        <div class="dashboard-filter">
                            <label for="filterCoberturaBandeja">Cobertura</label>
                            <select id="filterCoberturaBandeja"><option value="">Todas</option></select>
                        </div>
                        <div class="dashboard-filter">
                            <label for="filterSemaforoBandeja">Semáforo</label>
                            <select id="filterSemaforoBandeja"><option value="">Todos</option></select>
                        </div>
                        <div class="dashboard-filter">
                            <label for="filterMontoMin">Monto mín.</label>
                            <input type="number" id="filterMontoMin" placeholder="0" min="0">
                        </div>
                        <div class="dashboard-filter">
                            <label for="filterMontoMax">Monto máx.</label>
                            <input type="number" id="filterMontoMax" placeholder="Sin límite" min="0">
                        </div>
                        <div class="dashboard-filter">
                            <label for="filterScoreMinBandeja">Score mín.</label>
                            <input type="number" id="filterScoreMinBandeja" min="0" max="100" placeholder="0">
                        </div>
                        <div class="dashboard-filter">
                            <label for="filterScoreMaxBandeja">Score máx.</label>
                            <input type="number" id="filterScoreMaxBandeja" min="0" max="100" placeholder="100">
                        </div>
                    </div>
                    <div class="dashboard-filter-actions bandeja-filter-actions">
                        <button type="button" class="btn btn-secondary" id="btnClearBandejaFilters">Limpiar filtros</button>
                    </div>
                    <p class="bandeja-count-label" id="bandejaCountLabel">—</p>
                </div>
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
        if (lbl) {
            lbl.innerHTML = `Mostrando <strong>${filtered.length.toLocaleString()}</strong> de <strong>${allCases.length.toLocaleString()}</strong> siniestros`;
        }
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
                <td class="bandeja-actions">
                    <button type="button" class="btn btn-ghost btn-sm" data-case-detail="${escapeAttr(id)}">Detalle</button>
                    <button type="button" class="btn btn-primary btn-sm" data-case-pdf="${escapeAttr(id)}">PDF</button>
                </td>
            </tr>`;
        }).join('');
        tbody.querySelectorAll('[data-case-detail]').forEach((btn) => {
            btn.addEventListener('click', () => {
                if (typeof viewCase === 'function') viewCase(btn.dataset.caseDetail);
            });
        });
        tbody.querySelectorAll('[data-case-pdf]').forEach((btn) => {
            btn.addEventListener('click', () => downloadCasePdf(btn.dataset.casePdf, btn));
        });
    }

    async function downloadCasePdf(caseId, btn) {
        if (!caseId) return;
        const headers = {};
        try {
            const sid = sessionStorage.getItem('fxecure_session_id') || sessionStorage.getItem('fraudia_session_id');
            if (sid) {
                headers['X-FXecure-Session'] = sid;
                headers['X-FraudIA-Session'] = sid;
            }
        } catch (e) { /* ignore */ }
        if (btn) { btn.disabled = true; btn.textContent = '…'; }
        try {
            const r = await fetch('/api/case/' + encodeURIComponent(caseId) + '/pdf', { headers });
            if (!r.ok) {
                const err = await r.json().catch(() => ({}));
                alert(err.error || 'No se pudo generar el PDF');
                return;
            }
            const blob = await r.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'reporte_antifraude_' + caseId + '.pdf';
            a.click();
            URL.revokeObjectURL(a.href);
        } catch (e) {
            alert('Error al descargar PDF: ' + e.message);
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'PDF'; }
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
        } catch (e) {
            container.innerHTML = `<div class="alert alert-danger">Error al cargar la bandeja: ${escapeHtml(e.message)}</div>`;
        }
    }

    return { init };
})();

window.CasesBandeja = CasesBandeja;
