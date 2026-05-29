/**
 * FXecure — Previsualización del reporte de evaluación antifraude (modal estilo PDF).
 */
const CaseReportPreview = (function () {
    function sessionHeaders() {
        const h = {};
        try {
            const sid = sessionStorage.getItem('fxecure_session_id') || sessionStorage.getItem('fraudia_session_id');
            if (sid) {
                h['X-FXecure-Session'] = sid;
                h['X-FraudIA-Session'] = sid;
            }
        } catch (e) { /* ignore */ }
        if (typeof withFraudiaSessionHeaders === 'function') {
            return withFraudiaSessionHeaders({ headers: h }).headers;
        }
        return h;
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function sevClass(sev) {
        const s = String(sev || '').toUpperCase();
        if (s === 'ALTA') return 'cr-sev-alta';
        if (s === 'MEDIA') return 'cr-sev-media';
        return '';
    }

    function formatMoney(v) {
        const n = Number(v);
        if (!Number.isFinite(n)) return '—';
        return '$' + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function renderReportHtml(d) {
        const alertas = (d.alertas_tabla || []).map((a) => `
            <tr>
                <td>${a.num}</td>
                <td>${escapeHtml(a.descripcion)}</td>
                <td>${escapeHtml(a.umbral)}</td>
                <td>${a.puntos}</td>
                <td class="${sevClass(a.severidad)}">${escapeHtml(a.severidad)}</td>
            </tr>
        `).join('');

        const factores = (d.factores_evaluacion || []).map((f) =>
            `<li><strong>${escapeHtml(f.factor)}:</strong> ${escapeHtml(f.valor)}</li>`
        ).join('');

        const bars = (d.score_bars || []).map((b) =>
            `<span class="cr-bar-chip">${escapeHtml(b.label)} ${b.puntos} pts</span>`
        ).join('');

        const sem = String(d.semaforo || '').toUpperCase();
        const semColor = sem === 'ROJO' ? '#b91c1c' : sem === 'AMARILLO' ? '#b45309' : '#047857';

        return `
            <div class="cr-header-meta">
                <span><strong>FXecure</strong> · Agente IA Antifraude — Reporte de Evaluación</span>
                <span>${escapeHtml(d.id_siniestro)} · Generado: ${escapeHtml(d.generado)}</span>
            </div>
            <p class="cr-confidential">${escapeHtml(d.confidencial)}</p>
            <h2 class="cr-title">${escapeHtml(d.titulo)}</h2>
            <p class="cr-subtitle">${escapeHtml(d.subtitulo)}</p>
            <div class="cr-kpi-row">
                <div><div class="cr-kpi-head">SCORE DE RIESGO</div><div class="cr-kpi-val score">${Number(d.score_hibrido || 0).toFixed(1)}</div></div>
                <div><div class="cr-kpi-head">NIVEL DE RIESGO</div><div class="cr-kpi-val nivel" style="color:${semColor}">${escapeHtml(d.nivel_riesgo)}</div></div>
                <div><div class="cr-kpi-head">RANGO</div><div class="cr-kpi-val" style="font-size:0.85rem;">${escapeHtml(d.rango_score)}</div></div>
            </div>
            <div class="cr-accion">ACCIÓN SUGERIDA: ${escapeHtml(d.accion_destacada)}</div>

            <section class="cr-section">
                <h4>1. IDENTIFICACIÓN DEL SINIESTRO</h4>
                <dl class="cr-id-grid">
                    <dt>No. Siniestro</dt><dd>${escapeHtml(d.id_siniestro)}</dd>
                    <dt>Ramo</dt><dd>${escapeHtml(d.ramo || '—')}</dd>
                    <dt>Cobertura</dt><dd>${escapeHtml(d.cobertura || '—')}</dd>
                    <dt>Fecha de análisis</dt><dd>${escapeHtml(d.generado)}</dd>
                    <dt>Monto reclamado</dt><dd>${formatMoney(d.monto_reclamado)}</dd>
                    <dt>Asegurado</dt><dd>${escapeHtml(d.nombre_asegurado || '—')}</dd>
                    <dt>Póliza</dt><dd>${escapeHtml(d.id_poliza || '—')}</dd>
                    <dt>Reporte tardío</dt><dd>${escapeHtml(d.reporte_tardio || '—')}</dd>
                </dl>
            </section>

            <section class="cr-section">
                <h4>2. ALERTAS DETECTADAS (${d.num_alertas || 0} señales)</h4>
                <table class="cr-table">
                    <thead><tr><th>#</th><th>DESCRIPCIÓN</th><th>UMBRAL</th><th>PTS</th><th>SEVERIDAD</th></tr></thead>
                    <tbody>${alertas || '<tr><td colspan="5">Sin alertas registradas</td></tr>'}</tbody>
                </table>
            </section>

            <section class="cr-section">
                <h4>3. FACTORES PRINCIPALES DE EVALUACIÓN</h4>
                <ul class="cr-factores">${factores}</ul>
            </section>

            <section class="cr-section">
                <h4>4. DISTRIBUCIÓN DEL SCORE</h4>
                <div class="cr-bars">${bars || '—'}</div>
                <p style="font-size:0.72rem;color:#64748b;margin:0.35rem 0 0;">${escapeHtml(d.distribucion_nota || '')}</p>
            </section>

            <section class="cr-section">
                <h4>5. CONCLUSIÓN Y RECOMENDACIÓN</h4>
                <p class="cr-conclusion">${escapeHtml(d.conclusion || d.resumen || '')}</p>
            </section>

            <footer class="cr-footer">
                <div>${escapeHtml(d.pie)}</div>
                <div>${escapeHtml(d.pie_fecha || '')}</div>
            </footer>
        `;
    }

    async function show(caseId) {
        const existing = document.querySelector('.case-report-overlay');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.className = 'case-report-overlay';
        overlay.innerHTML = `
            <div class="case-report-modal" role="dialog" aria-labelledby="crTitle">
                <div class="case-report-toolbar">
                    <h3 id="crTitle">Reporte · ${escapeHtml(caseId)}</h3>
                    <div class="case-report-toolbar-actions">
                        <a class="btn btn-primary" id="crBtnPdf" href="/api/case/${encodeURIComponent(caseId)}/pdf" download="reporte_antifraude_${escapeHtml(caseId)}.pdf">Descargar PDF</a>
                        <button type="button" class="btn btn-secondary" id="crBtnClose">Cerrar</button>
                    </div>
                </div>
                <div class="case-report-body"><span class="spinner"></span> Cargando reporte…</div>
            </div>
        `;
        document.body.appendChild(overlay);

        const close = () => overlay.remove();
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
        overlay.querySelector('#crBtnClose').addEventListener('click', close);
        overlay.querySelector('#crBtnPdf').addEventListener('click', async (e) => {
            e.preventDefault();
            const btn = e.currentTarget;
            const url = '/api/case/' + encodeURIComponent(caseId) + '/pdf';
            const fname = 'reporte_antifraude_' + caseId + '.pdf';
            btn.disabled = true;
            const prev = btn.textContent;
            btn.textContent = 'Generando…';
            try {
                const r = await fetch(url, { headers: sessionHeaders() });
                if (!r.ok) {
                    const err = await r.json().catch(() => ({}));
                    alert(err.error || 'No se pudo generar el PDF');
                    return;
                }
                const blob = await r.blob();
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = fname;
                a.click();
                URL.revokeObjectURL(a.href);
            } catch (err) {
                alert('Error al descargar PDF: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.textContent = prev;
            }
        });

        try {
            const resp = await fetch('/api/case/' + encodeURIComponent(caseId), { headers: sessionHeaders() });
            const data = await resp.json();
            if (!resp.ok || data.error) {
                overlay.querySelector('.case-report-body').innerHTML =
                    `<div class="alert alert-danger">${escapeHtml(data.error || 'No se pudo cargar el caso')}</div>`;
                return;
            }
            overlay.querySelector('.case-report-body').innerHTML = renderReportHtml(data);
        } catch (e) {
            overlay.querySelector('.case-report-body').innerHTML =
                `<div class="alert alert-danger">Error: ${escapeHtml(e.message)}</div>`;
        }
    }

    return { show };
})();

window.CaseReportPreview = CaseReportPreview;
window.viewCase = function (caseId) {
    return CaseReportPreview.show(caseId);
};
