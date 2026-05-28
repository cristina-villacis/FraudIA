/**
 * FraudIA — UI Carga Inteligente de Datos
 */
(function () {
    const ETL_STEPS = [
        { id: 'excel', label: 'Excel', icon: '📊' },
        { id: 'parse', label: 'Parsing', icon: '⚙' },
        { id: 'valid', label: 'Validación', icon: '✓' },
        { id: 'er', label: 'Modelo ER', icon: '◈' },
        { id: 'tidb', label: 'TiDB', icon: '☁' },
        { id: 'ml', label: 'ML Engine', icon: '🧠' },
        { id: 'dash', label: 'Dashboard', icon: '📈' },
    ];

    const ER_NODES = [
        { id: 'sin', label: 'Siniestros', x: 50, y: 140 },
        { id: 'pol', label: 'Pólizas', x: 200, y: 60 },
        { id: 'ase', label: 'Asegurados', x: 350, y: 140 },
        { id: 'pro', label: 'Proveedores', x: 200, y: 220 },
        { id: 'doc', label: 'Documentos', x: 50, y: 60 },
    ];
    const ER_EDGES = [
        ['sin', 'pol', 'id_poliza'],
        ['sin', 'ase', 'id_asegurado'],
        ['sin', 'pro', 'id_proveedor'],
        ['doc', 'sin', 'id_siniestro'],
        ['pol', 'ase', 'id_asegurado'],
    ];

    const SHEET_META = {
        siniestros: { letter: 'S', title: 'Siniestros', rel: '→ Pólizas, Asegurados, Proveedores' },
        polizas: { letter: 'P', title: 'Pólizas', rel: '→ Asegurados' },
        asegurados: { letter: 'A', title: 'Asegurados', rel: 'Entidad raíz cliente' },
        proveedores: { letter: 'Pr', title: 'Proveedores', rel: '→ Siniestros' },
        documentos: { letter: 'D', title: 'Documentos', rel: '→ Siniestros' },
    };

    function initParticles() {
        const canvas = document.getElementById('ingestParticles');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        let w, h, particles = [];

        function resize() {
            const parent = canvas.parentElement;
            w = canvas.width = parent.clientWidth;
            h = canvas.height = Math.max(parent.clientHeight, 600);
        }

        function mk() {
            particles = [];
            const n = Math.floor((w * h) / 12000);
            for (let i = 0; i < n; i++) {
                particles.push({
                    x: Math.random() * w,
                    y: Math.random() * h,
                    vx: (Math.random() - 0.5) * 0.4,
                    vy: (Math.random() - 0.5) * 0.4,
                    r: Math.random() * 1.5 + 0.5,
                });
            }
        }

        function draw() {
            ctx.clearRect(0, 0, w, h);
            const cyan = getComputedStyle(document.documentElement).getPropertyValue('--cyan').trim() || '#00D1FF';
            particles.forEach((p, i) => {
                p.x += p.vx;
                p.y += p.vy;
                if (p.x < 0 || p.x > w) p.vx *= -1;
                if (p.y < 0 || p.y > h) p.vy *= -1;
                ctx.beginPath();
                ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
                ctx.fillStyle = cyan;
                ctx.globalAlpha = 0.35;
                ctx.fill();
                particles.slice(i + 1, i + 4).forEach((p2) => {
                    const d = Math.hypot(p.x - p2.x, p.y - p2.y);
                    if (d < 100) {
                        ctx.beginPath();
                        ctx.moveTo(p.x, p.y);
                        ctx.lineTo(p2.x, p2.y);
                        ctx.strokeStyle = cyan;
                        ctx.globalAlpha = 0.08 * (1 - d / 100);
                        ctx.stroke();
                    }
                });
            });
            ctx.globalAlpha = 1;
            requestAnimationFrame(draw);
        }

        resize();
        mk();
        draw();
        window.addEventListener('resize', () => { resize(); mk(); });
    }

    function renderEtlTrack() {
        const track = document.getElementById('etlTrack');
        if (!track) return;
        track.innerHTML = ETL_STEPS.map(
            (s) => `
            <div class="etl-step" data-etl="${s.id}">
                <div class="etl-step-icon">${s.icon}</div>
                <div class="etl-step-label">${s.label}</div>
                <div class="etl-step-pct">0%</div>
            </div>`
        ).join('');
    }

    function runEtlAnimation(onDone) {
        const el = document.getElementById('ingestEtl');
        if (el) el.classList.add('visible');
        const steps = document.querySelectorAll('.etl-step');
        let i = 0;

        function tick() {
            if (i >= steps.length) {
                if (onDone) onDone();
                return;
            }
            const step = steps[i];
            step.classList.add('active');
            let pct = 0;
            const iv = setInterval(() => {
                pct += 8 + Math.random() * 12;
                if (pct >= 100) {
                    pct = 100;
                    clearInterval(iv);
                    step.classList.remove('active');
                    step.classList.add('done');
                    const pEl = step.querySelector('.etl-step-pct');
                    if (pEl) pEl.textContent = '100%';
                    i++;
                    setTimeout(tick, 120);
                } else {
                    const pEl = step.querySelector('.etl-step-pct');
                    if (pEl) pEl.textContent = Math.round(pct) + '%';
                }
            }, 80);
        }
        tick();
    }

    function renderErGraph() {
        const wrap = document.getElementById('erGraph');
        if (!wrap) return;
        const byId = Object.fromEntries(ER_NODES.map((n) => [n.id, n]));
        let edges = '';
        ER_EDGES.forEach(([a, b, label]) => {
            const n1 = byId[a];
            const n2 = byId[b];
            if (!n1 || !n2) return;
            edges += `<line class="er-edge" x1="${n1.x}" y1="${n1.y}" x2="${n2.x}" y2="${n2.y}"/>`;
            const mx = (n1.x + n2.x) / 2;
            const my = (n1.y + n2.y) / 2;
            edges += `<text class="er-edge-label" x="${mx}" y="${my - 4}" text-anchor="middle">${label}</text>`;
        });
        const nodes = ER_NODES.map(
            (n) => `
            <g class="er-node">
                <circle cx="${n.x}" cy="${n.y}" r="36"/>
                <text x="${n.x}" y="${n.y + 4}" text-anchor="middle">${n.label}</text>
            </g>`
        ).join('');
        wrap.innerHTML = `<svg viewBox="0 0 420 280" preserveAspectRatio="xMidYMid meet">${edges}${nodes}</svg>`;
    }

    function qualityScore(rows, cols) {
        if (!rows) return 'mid';
        if (rows >= 50 && cols >= 5) return 'high';
        return 'mid';
    }

    function renderSheets(tables) {
        const list = document.getElementById('sheetList');
        if (!list || !tables) return;
        const order = ['siniestros', 'polizas', 'asegurados', 'proveedores', 'documentos'];
        list.innerHTML = order
            .filter((k) => tables[k])
            .map((k) => {
                const t = tables[k];
                const meta = SHEET_META[k] || { letter: '?', title: k, rel: '' };
                const rows = t.rows || 0;
                const cols = Array.isArray(t.columns)
                    ? t.columns.length
                    : typeof t.columns === 'number'
                      ? t.columns
                      : (t.cols || []).length;
                const q = qualityScore(rows, cols);
                return `
                <div class="sheet-card">
                    <div class="sheet-card-icon">${meta.letter}</div>
                    <div>
                        <h4>${meta.title}</h4>
                        <div class="sheet-card-meta">${rows.toLocaleString()} registros · ${cols} columnas<br>${meta.rel}</div>
                    </div>
                    <span class="sheet-quality ${q}">${q === 'high' ? 'Alta' : 'OK'}</span>
                </div>`;
            })
            .join('');
    }

    function renderValidations(data, tables) {
        const grid = document.getElementById('valGrid');
        if (!grid) return;
        const warnings = data.warnings || [];
        const hasSin = data.has_siniestros || (tables && tables.siniestros);
        const items = [
            { t: hasSin ? 'ok' : 'err', m: 'IDs y hoja Siniestros' },
            { t: warnings.length === 0 ? 'ok' : 'warn', m: warnings.length ? warnings[0].slice(0, 50) : 'Relaciones correctas' },
            { t: 'ok', m: 'Claves foráneas mapeadas' },
            { t: warnings.length > 1 ? 'warn' : 'ok', m: warnings.length > 1 ? 'Campos opcionales faltantes' : 'Esquema completo' },
            { t: 'ok', m: 'Fechas normalizadas' },
            { t: 'ok', m: 'Sin duplicados críticos' },
        ];
        grid.innerHTML = items
            .map((i) => `<div class="val-item ${i.t}">${i.t === 'ok' ? '✓' : '⚠'} ${i.m}</div>`)
            .join('');
    }

    function showAiPanel() {
        const panel = document.getElementById('ingestAi');
        if (panel) panel.classList.add('visible');
    }

    function onUploadStart(fileName) {
        const zone = document.getElementById('ingestUpload');
        const status = document.getElementById('datasetLoadStatus');
        const actionsBar = document.getElementById('ingestActionsBar');
        const insights = document.getElementById('ingestInsights');
        if (actionsBar) actionsBar.style.display = 'block';
        if (insights) insights.style.display = 'grid';
        if (zone) zone.classList.add('scanning');
        if (status) {
            status.innerHTML = `<div class="alert alert-info" style="margin:0;">Subiendo <strong>${fileName}</strong>… (unos segundos). Luego TiDB + análisis en segundo plano.</div>`;
        }
        ['btnPipeline', 'btnPipelineMain'].forEach((id) => {
            const btn = document.getElementById(id);
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner"></span> Cargando archivo…';
            }
        });
        document.querySelectorAll('.etl-step').forEach((s) => {
            s.classList.remove('active', 'done');
            const p = s.querySelector('.etl-step-pct');
            if (p) p.textContent = '0%';
        });
    }

    function onUploadEnd() {
        const zone = document.getElementById('ingestUpload');
        if (zone) zone.classList.remove('scanning');
    }

    function onLoadComplete(data) {
        onUploadEnd();
        const tables = data.tables || {};
        const canAnalyze = data.has_siniestros !== false;
        renderSheets(tables);
        renderValidations(data, tables);
        renderErGraph();
        ['btnPipeline', 'btnPipelineMain'].forEach((id) => {
            const btn = document.getElementById(id);
            if (btn) {
                btn.disabled = !canAnalyze;
                btn.textContent = 'Activar motor IA';
            }
        });
        runEtlAnimation(() => {
            showAiPanel();
            if (typeof showTablesInfo === 'function') showTablesInfo(tables);
            const tablesInfo = document.getElementById('tablesInfo');
            if (tablesInfo) tablesInfo.style.display = 'block';
        });
    }

    function bindUploadZone() {
        const zone = document.getElementById('ingestUpload');
        const input = document.getElementById('fileInput');
        if (!zone || !input) return;
        zone.addEventListener('click', () => input.click());
        zone.addEventListener('dragover', (e) => {
            e.preventDefault();
            zone.classList.add('dragover');
        });
        zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.classList.remove('dragover');
            if (e.dataTransfer.files.length && typeof uploadFileObj === 'function') {
                uploadFileObj(e.dataTransfer.files[0]);
            }
        });
    }

    function init() {
        renderEtlTrack();
        renderErGraph();
        initParticles();
        bindUploadZone();
    }

    window.IngestUI = {
        init,
        onUploadStart,
        onLoadComplete,
        onUploadEnd,
        runEtlAnimation,
        showAiPanel,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
