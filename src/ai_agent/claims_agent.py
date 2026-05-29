"""
Agente de IA explicativo para consultas en lenguaje natural.
Con GEMINI_API_KEY (Vercel) responde como asistente conversacional sobre el análisis cargado.
Sin LLM externo, usa motor de reglas como respaldo.
"""
import json
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.ai_agent.llm_router import (
    chat_with_llm,
    enhance_with_llm,
    get_llm_provider,
    llm_status,
)


class ClaimsAgent:
    """Agente que responde consultas en lenguaje natural sobre los datos de siniestros."""

    def __init__(self, df: pd.DataFrame, extra_context: Optional[Dict[str, Any]] = None):
        self.df = df.copy()
        self.extra_context = extra_context or {}
        self._build_index()

    def set_extra_context(self, extra_context: Optional[Dict[str, Any]]) -> None:
        """Actualiza contexto adicional persistente (dashboard + métricas ML)."""
        self.extra_context = extra_context or {}

    def _build_index(self):
        self.score_col = "score_hibrido" if "score_hibrido" in self.df.columns else "score_reglas"
        self.semaforo_col = "semaforo_final" if "semaforo_final" in self.df.columns else "semaforo_reglas"
        self.ml_col = "ml_fraud_probability" if "ml_fraud_probability" in self.df.columns else None
        self.anomaly_col = "anomaly_score" if "anomaly_score" in self.df.columns else None

    def _format_ai_signals(self, row: pd.Series) -> str:
        """Resumen de señales IA (ML supervisado, anomalías, reglas críticas) para el agente."""
        lines = []
        if self.ml_col and not pd.isna(row.get(self.ml_col)):
            prob = float(row[self.ml_col]) * 100
            lines.append(f"- Probabilidad ML de fraude: {prob:.1f}% (modelo supervisado, etiqueta simulada)")
        if self.anomaly_col and not pd.isna(row.get(self.anomaly_col)):
            anom = float(row[self.anomaly_col]) * 100
            lines.append(f"- Score de anomalía: {anom:.1f}% (Isolation Forest — comportamiento atípico)")
        if "score_reglas" in row.index and not pd.isna(row.get("score_reglas")):
            lines.append(f"- Score reglas de negocio: {float(row['score_reglas']):.1f}/100")
        reglas_crit = row.get("reglas_criticas", "")
        if isinstance(reglas_crit, str) and reglas_crit.strip():
            lines.append(f"- Reglas críticas activas: {reglas_crit}")
        return "\n".join(lines) if lines else ""

    def _format_dashboard_last_payload(self, payload: Dict[str, Any]) -> List[str]:
        """Serializa el payload completo del dashboard para el LLM."""
        lines: List[str] = []
        if not isinstance(payload, dict):
            return lines

        lines.append("=== DASHBOARD EJECUTIVO (análisis agregado, mismo que ve el usuario) ===")
        total = payload.get("total", payload.get("total_unfiltered"))
        lines.append(f"Registros en vista: {total} (universo analizado: {payload.get('total_unfiltered', total)})")
        if payload.get("source_total_siniestros"):
            lines.append(f"Siniestros cargados en archivo: {payload['source_total_siniestros']}")
        lines.append(f"Score híbrido promedio: {payload.get('score_promedio', 'N/A')}")
        lines.append(
            f"Montos: total=${payload.get('monto_total', 0):,.2f}, "
            f"en rojo=${payload.get('monto_rojo', 0):,.2f}"
        )

        sem = payload.get("semaforo") or {}
        if sem:
            lines.append(
                f"Semáforos: Rojo={sem.get('Rojo', 0)}, "
                f"Amarillo={sem.get('Amarillo', 0)}, Verde={sem.get('Verde', 0)}"
            )

        ek = payload.get("executive_kpis") or {}
        if ek:
            lines.append("KPIs ejecutivos del dashboard:")
            for key, val in ek.items():
                lines.append(f"  · {key}: {val}")

        for sig in (payload.get("signals_summary") or [])[:22]:
            lines.append(f"  Señal «{sig.get('signal', '?')}»: {sig.get('count', 0)} casos")

        crit = payload.get("critical_rules_summary") or {}
        if crit:
            lines.append("Conteo reglas críticas RF:")
            for code, n in sorted(crit.items(), key=lambda x: -int(x[1] or 0))[:12]:
                lines.append(f"  · {code}: {n} casos")

        for r in (payload.get("ramo_data") or [])[:18]:
            lines.append(
                f"  Ramo {r.get('ramo')}: {r.get('count')} casos, score_avg={r.get('score_avg')}, "
                f"R={r.get('rojos', 0)} A={r.get('amarillos', 0)} V={r.get('verdes', 0)}, "
                f"monto=${float(r.get('monto_total') or 0):,.0f}"
            )

        for p in (payload.get("provider_risk") or [])[:15]:
            ben = str(p.get("beneficiario") or "")[:50]
            lines.append(
                f"  Proveedor {ben}: {p.get('casos')} casos, score_prom={p.get('score_prom')}, "
                f"monto=${float(p.get('monto') or 0):,.0f}"
            )

        sd = payload.get("score_distribution") or {}
        labels = sd.get("labels") or []
        counts = sd.get("counts") or []
        if labels:
            lines.append("Distribución por banda de score:")
            for lab, cnt in zip(labels, counts):
                lines.append(f"  · {lab}: {cnt} siniestros")

        for t in (payload.get("temporal_risk_data") or [])[-14:]:
            lines.append(
                f"  Mes {t.get('mes')}: Verde={t.get('Verde', 0)}, "
                f"Amarillo={t.get('Amarillo', 0)}, Rojo={t.get('Rojo', 0)}"
            )

        for g in (payload.get("geo_risk_data") or [])[:14]:
            lines.append(
                f"  Sucursal {g.get('sucursal')}: V={g.get('Verde', 0)}, "
                f"A={g.get('Amarillo', 0)}, R={g.get('Rojo', 0)}"
            )

        heat = payload.get("heatmap_ramo_riesgo") or {}
        ramos_h = heat.get("ramos") or []
        sem_h = heat.get("semaforos") or []
        z = heat.get("z") or []
        if ramos_h and sem_h:
            lines.append(f"Heatmap ramo×semáforo (columnas: {', '.join(map(str, sem_h))}):")
            for i, ramo in enumerate(ramos_h[:14]):
                row = z[i] if i < len(z) else []
                lines.append(f"  {ramo}: {row}")

        lines.append("Top casos del dashboard (ID | ramo | score | semáforo | monto):")
        for c in (payload.get("top_cases") or [])[:25]:
            sc = c.get("score_hibrido", c.get("score_reglas", ""))
            sem_c = c.get("semaforo_final", c.get("semaforo_reglas", ""))
            monto = c.get("monto_reclamado", 0)
            alert = str(c.get("alertas_reglas") or "")[:80]
            lines.append(
                f"  | {c.get('id_siniestro')} | {c.get('ramo', '')} | {sc} | {sem_c} | "
                f"${float(monto or 0):,.0f} | {alert}"
            )
        return lines

    def _format_ml_analysis_context(self) -> List[str]:
        """Métricas ML, anomalías y NLP del pipeline."""
        lines: List[str] = []
        snapshot = self.extra_context.get("model_snapshot")
        results = self.extra_context.get("model_results")
        merged: Dict[str, Any] = {}
        if isinstance(results, dict):
            merged.update(results)
        if isinstance(snapshot, dict):
            merged.update(snapshot)

        if merged:
            lines.append("=== MOTOR MACHINE LEARNING (entrenamiento y métricas) ===")
            for key in (
                "trained", "auc_roc", "cv_auc_mean", "cv_auc_std",
                "precision_fraude", "recall_fraude", "f1_fraude",
                "accuracy", "precision", "recall", "f1_score",
                "ml_prob_promedio", "casos_alta_prob_ml", "anomalies_detected",
            ):
                val = merged.get(key)
                if val is not None and val != "":
                    if isinstance(val, float):
                        lines.append(f"  · {key}: {val:.4f}")
                    else:
                        lines.append(f"  · {key}: {val}")

            cm = merged.get("confusion_matrix")
            if cm is not None:
                lines.append(f"  · confusion_matrix: {cm}")

            top_feat = merged.get("top_features") or merged.get("feature_importance")
            if isinstance(top_feat, list) and top_feat:
                lines.append("  Variables más importantes del modelo:")
                for item in top_feat[:12]:
                    if isinstance(item, dict):
                        fname = item.get("feature", item.get("name", "?"))
                        imp = item.get("importance", item.get("score", ""))
                        lines.append(f"    - {fname}: {imp}")
                    else:
                        lines.append(f"    - {item}")

            if merged.get("error"):
                lines.append(f"  Aviso modelo: {merged['error']}")
            if merged.get("warning"):
                lines.append(f"  Aviso: {merged['warning']}")

        if self.ml_col and self.ml_col in self.df.columns:
            prob = pd.to_numeric(self.df[self.ml_col], errors="coerce").dropna()
            if len(prob):
                lines.append("Probabilidad ML en cartera (df_scored):")
                lines.append(f"  · Promedio: {prob.mean()*100:.2f}%")
                lines.append(f"  · Casos prob ≥ 70%: {int((prob >= 0.7).sum())}")
                lines.append(f"  · Casos prob ≥ 50%: {int((prob >= 0.5).sum())}")

        if self.anomaly_col and self.anomaly_col in self.df.columns:
            anom = pd.to_numeric(self.df[self.anomaly_col], errors="coerce").dropna()
            if len(anom):
                lines.append("Anomalías (Isolation Forest) en cartera:")
                lines.append(f"  · Score promedio: {anom.mean()*100:.2f}%")
                lines.append(f"  · Casos score ≥ 75%: {int((anom >= 0.75).sum())}")

        anom_res = self.extra_context.get("anomaly_results")
        if isinstance(anom_res, dict) and anom_res:
            lines.append(f"Resumen detección anomalías: {json.dumps(anom_res, default=str, ensure_ascii=False)[:2000]}")

        nlp = self.extra_context.get("nlp_results")
        if isinstance(nlp, dict) and nlp:
            lines.append(f"Análisis NLP narrativas: {json.dumps(nlp, default=str, ensure_ascii=False)[:1500]}")

        return lines

    def build_dataset_context(self, max_top: int = 15) -> str:
        """Contexto global de la sesión (todos los niveles de riesgo, no solo críticos)."""
        total = len(self.df)
        lines = [f"Total siniestros en sesión: {total}"]

        if self.semaforo_col in self.df.columns:
            for sem in ("Rojo", "Amarillo", "Verde"):
                n = int((self.df[self.semaforo_col] == sem).sum())
                lines.append(f"Semáforo {sem}: {n}")

        if self.score_col in self.df.columns:
            lines.append(f"Score híbrido promedio: {self.df[self.score_col].mean():.1f}")

        if self.ml_col:
            lines.append(
                f"Probabilidad ML promedio: {self.df[self.ml_col].mean()*100:.1f}%"
            )

        if self.anomaly_col:
            lines.append(
                f"Score anomalía promedio: {self.df[self.anomaly_col].mean()*100:.1f}%"
            )

        if "ramo" in self.df.columns and self.semaforo_col in self.df.columns:
            ramo_risk = (
                self.df.groupby("ramo")[self.semaforo_col]
                .apply(lambda s: f"R={int((s=='Rojo').sum())} A={int((s=='Amarillo').sum())} V={int((s=='Verde').sum())}")
            )
            lines.append("Distribución por ramo (R/A/V):")
            for ramo, dist in ramo_risk.head(12).items():
                lines.append(f"  - {ramo}: {dist}")

        if self.score_col in self.df.columns:
            top = self.df.nlargest(max_top, self.score_col)
            lines.append(f"Top {max_top} por score (referencia):")
            for _, row in top.iterrows():
                sem = row.get(self.semaforo_col, "N/A")
                ml = ""
                if self.ml_col and not pd.isna(row.get(self.ml_col)):
                    ml = f", ML={float(row[self.ml_col])*100:.0f}%"
                lines.append(
                    f"  - {row['id_siniestro']}: score={row[self.score_col]:.1f}, "
                    f"{sem}{ml}, ramo={row.get('ramo', 'N/A')}"
                )
            mid = self.df[
                (self.df[self.score_col] >= 41) & (self.df[self.score_col] <= 75)
            ].head(5) if self.score_col in self.df.columns else pd.DataFrame()
            if len(mid):
                lines.append("Muestra riesgo medio (amarillo):")
                for _, row in mid.iterrows():
                    lines.append(
                        f"  - {row['id_siniestro']}: score={row[self.score_col]:.1f}, "
                        f"{row.get(self.semaforo_col, 'N/A')}"
                    )

        src_counts = self.extra_context.get("source_row_counts")
        if isinstance(src_counts, dict) and src_counts:
            lines.append("Filas cargadas por tabla:")
            for name, cnt in src_counts.items():
                lines.append(f"  · {name}: {cnt}")

        dash_full = self.extra_context.get("dashboard_last_payload")
        if isinstance(dash_full, dict) and dash_full:
            lines.extend(self._format_dashboard_last_payload(dash_full))
        lines.extend(self._format_ml_analysis_context())

        dashboard_snapshot = self.extra_context.get("dashboard_snapshot")
        if isinstance(dashboard_snapshot, dict) and not dash_full:
            lines.append("Dashboard (snapshot guardado):")
            lines.append(
                f"- Registros considerados: {dashboard_snapshot.get('records_considered', total)} "
                f"(sin filtros activos: {dashboard_snapshot.get('active_filters_count', 0)})"
            )
            if dashboard_snapshot.get("score_promedio") is not None:
                lines.append(f"- Score promedio dashboard: {dashboard_snapshot.get('score_promedio'):.1f}")
            if dashboard_snapshot.get("monto_total") is not None:
                lines.append(f"- Monto total dashboard: ${dashboard_snapshot.get('monto_total'):,.2f}")
            semaforo_counts = dashboard_snapshot.get("semaforo_counts", {})
            if isinstance(semaforo_counts, dict) and semaforo_counts:
                lines.append(
                    "- Distribución semáforo dashboard: "
                    f"Rojo={semaforo_counts.get('Rojo', 0)}, "
                    f"Amarillo={semaforo_counts.get('Amarillo', 0)}, "
                    f"Verde={semaforo_counts.get('Verde', 0)}"
                )

        model_snapshot = self.extra_context.get("model_snapshot")
        if isinstance(model_snapshot, dict):
            lines.append("Modelo ML (entrenado en pipeline):")
            for key in (
                "auc_roc", "cv_auc_mean", "precision_fraude", "recall_fraude",
                "f1_fraude", "accuracy", "precision", "recall", "f1_score",
            ):
                val = model_snapshot.get(key)
                if val is not None:
                    if isinstance(val, (float, int)):
                        lines.append(f"- {key}: {float(val):.4f}")
                    else:
                        lines.append(f"- {key}: {val}")
            top_feat = model_snapshot.get("top_features") or model_snapshot.get("feature_importance")
            if isinstance(top_feat, list) and top_feat:
                lines.append("- Top variables del modelo:")
                for item in top_feat[:5]:
                    if isinstance(item, dict):
                        lines.append(f"  · {item.get('feature', item.get('name', '?'))}: {item.get('importance', item.get('score', ''))}")

        exec_sum = self.extra_context.get("executive_summary")
        if exec_sum:
            lines.append("Resumen ejecutivo del análisis:")
            lines.append(str(exec_sum)[:2500])

        manifest = self.extra_context.get("manifest")
        if isinstance(manifest, dict) and manifest.get("steps"):
            lines.append("Pasos del pipeline ejecutado:")
            for step in manifest["steps"]:
                lines.append(f"  · {step.get('step', '?')}: {step.get('status', '')}")

        doc_ctx = self.extra_context.get("documentos_subidos")
        if isinstance(doc_ctx, dict) and doc_ctx.get("total", 0) > 0:
            lines.append(f"Documentos PDF analizados: {doc_ctx['total']}")
            por = doc_ctx.get("por_semaforo") or {}
            if por:
                lines.append(
                    f"  Semáforos PDF: Rojo={por.get('Rojo', 0)}, "
                    f"Amarillo={por.get('Amarillo', 0)}, Verde={por.get('Verde', 0)}"
                )
            for item in (doc_ctx.get("items") or [])[:6]:
                lines.append(
                    f"  · {item.get('archivo')} ({item.get('tipo')}) → "
                    f"{item.get('siniestro')} {item.get('semaforo')} score={item.get('score')}"
                )

        if "num_alertas" in self.df.columns:
            with_alerts = int((self.df["num_alertas"] > 0).sum())
            lines.append(f"Siniestros con al menos una alerta: {with_alerts}")

        if self.semaforo_col in self.df.columns and "alertas_reglas" in self.df.columns:
            rojos = self.df[self.df[self.semaforo_col] == "Rojo"]
            if len(rojos) > 0 and self.score_col in rojos.columns:
                lines.append("Muestra casos rojos (ID | score | alertas):")
                for _, row in rojos.nlargest(8, self.score_col).iterrows():
                    al = str(row.get("alertas_reglas", ""))[:120]
                    lines.append(
                        f"  - {row['id_siniestro']}: {float(row[self.score_col]):.1f} | {al}"
                    )

        return "\n".join(lines)

    def _gather_factual_hints(self, question: str) -> str:
        """Hechos del motor de reglas para el LLM (no se muestran tal cual al usuario)."""
        rule_result = self._run_rule_handlers(question.lower().strip())
        parts: List[str] = []
        respuesta = rule_result.get("respuesta")
        if isinstance(respuesta, str) and respuesta.strip():
            parts.append("EXTRACTO MOTOR DE REGLAS:\n" + respuesta.strip()[:3500])
        datos = rule_result.get("datos")
        if datos is not None:
            try:
                if isinstance(datos, list):
                    slim = []
                    for item in datos[:12]:
                        if isinstance(item, dict):
                            slim.append({k: item.get(k) for k in list(item.keys())[:14]})
                    parts.append(
                        "REGISTROS RELACIONADOS (JSON):\n"
                        + json.dumps(slim, default=str, ensure_ascii=False)[:4500]
                    )
                elif isinstance(datos, dict):
                    slim = {k: datos.get(k) for k in list(datos.keys())[:22]}
                    parts.append(
                        "REGISTRO RELACIONADO (JSON):\n"
                        + json.dumps(slim, default=str, ensure_ascii=False)[:3000]
                    )
            except Exception:
                pass
        return "\n\n".join(parts)

    def _run_rule_handlers(self, question_lower: str) -> Dict[str, Any]:
        """Motor de reglas (respaldo cuando no hay LLM o falla la API)."""
        handlers = [
            (self._is_case_query, self._handle_case_query),
            (self._is_explainability_query, self._handle_explainability_query),
            (self._is_ml_query, self._handle_ml_query),
            (self._is_summary_query, self._handle_summary_query),
            (self._is_top_risk_query, self._handle_top_risk_query),
            (self._is_provider_query, self._handle_provider_query),
            (self._is_insured_query, self._handle_insured_query),
            (self._is_branch_query, self._handle_branch_query),
            (self._is_vehicle_query, self._handle_vehicle_query),
            (self._is_coverage_query, self._handle_coverage_query),
            (self._is_pattern_query, self._handle_pattern_query),
            (self._is_alert_query, self._handle_alert_query),
            (self._is_count_query, self._handle_count_query),
            (self._is_amount_query, self._handle_amount_query),
        ]
        for check, handler in handlers:
            if check(question_lower):
                return handler(question_lower)
        return self._handle_general_query(question_lower)

    def _use_external_llm(self) -> bool:
        return get_llm_provider() != "local"

    def _apply_response_style(self, text: str) -> str:
        """Formato base para respuestas del agente (sin saludos genéricos)."""
        clean = (text or "").strip()
        if not clean:
            return (
                "## Clasificación de riesgo\n"
                "No hay datos suficientes en el dataset procesado.\n\n"
                "## Recomendación de auditoría\n"
                "Cargue un Excel en «Carga Inteligente de Datos» y active el motor IA."
            )
        if clean.startswith("#"):
            return clean
        return clean

    def query(
        self,
        question: str,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict:
        question = (question or "").strip()
        status = llm_status()
        result: Dict[str, Any] = {
            **status,
            "openai_used": False,
            "gemini_used": False,
            "llm_primary": False,
        }

        if not question:
            result["respuesta"] = (
                "Escriba su consulta sobre la cartera analizada: casos, alertas, "
                "proveedores, montos o cualquier duda del análisis."
            )
            result["motor"] = "local"
            result["tipo"] = "ayuda"
            return result

        if len(self.df) == 0:
            result["respuesta"] = (
                "No hay siniestros analizados en esta sesión. Cargue un Excel en "
                "«Carga de datos» y active el motor IA antes de consultar."
            )
            result["motor"] = "local"
            result["tipo"] = "ayuda"
            return result

        # --- Modo principal: asistente conversacional (Gemini / OpenAI) ---
        if self._use_external_llm():
            context = self.build_dataset_context(max_top=30)
            hints = self._gather_factual_hints(question)
            text, motor, llm_error = chat_with_llm(
                question,
                context,
                history=history,
                factual_hints=hints or None,
            )
            if text:
                result["respuesta"] = self._apply_response_style(text)
                result["motor"] = motor
                result["llm_primary"] = True
                result["gemini_used"] = motor.startswith("gemini")
                result["openai_used"] = motor.startswith("chatgpt")
                result["tipo"] = "conversacion"
                rule_result = self._run_rule_handlers(question.lower())
                if rule_result.get("datos") is not None:
                    result["datos"] = rule_result.get("datos")
                return result
            result["llm_error"] = llm_error

        # --- Respaldo: motor de reglas (+ enriquecimiento LLM si aplica) ---
        rule_result = self._run_rule_handlers(question.lower())
        rule_result.update(status)
        rule_result.setdefault("motor", "reglas-local")
        rule_result["openai_used"] = False
        rule_result["gemini_used"] = False
        rule_result["llm_primary"] = False

        if self._use_external_llm() and rule_result.get("tipo") not in ("ayuda",):
            factual = rule_result.get("respuesta", "")
            context = self.build_dataset_context(max_top=30)
            enhanced, motor, llm_error = enhance_with_llm(question, factual, context)
            if enhanced:
                rule_result["respuesta"] = enhanced
                rule_result["motor"] = motor
                rule_result["gemini_used"] = motor.startswith("gemini")
                rule_result["openai_used"] = motor.startswith("chatgpt")
            elif llm_error:
                rule_result["llm_error"] = llm_error
                note = f"*No pude conectar con el asistente IA ({llm_error}). Respuesta del motor local:*\n\n"
                rule_result["respuesta"] = note + str(rule_result.get("respuesta", ""))
        elif result.get("llm_error"):
            note = f"*Asistente IA no disponible ({result['llm_error']}). Respuesta del motor local:*\n\n"
            rule_result["respuesta"] = note + str(rule_result.get("respuesta", ""))
            rule_result["llm_error"] = result["llm_error"]

        rule_result["respuesta"] = self._apply_response_style(rule_result.get("respuesta", ""))
        return rule_result

    def _is_explainability_query(self, q: str) -> bool:
        return any(w in q for w in [
            "por qué", "porque", "justifica", "justificación", "justificacion",
            "explica", "explicabilidad", "catalogado", "catalogados", "clasificado",
            "clasificados", "riesgo alto", "riesgo medio", "riesgo bajo",
            "semáforo", "semaforo", "rojo", "amarillo", "verde",
        ])

    def _risk_level_label(self, semaforo: str, score: float) -> str:
        sem = str(semaforo or "")
        if sem == "Rojo" or score >= 56:
            return "Alto (Rojo)"
        if sem == "Amarillo" or score >= 26:
            return "Medio (Amarillo)"
        return "Bajo (Verde)"

    def _handle_explainability_query(self, q: str) -> Dict:
        """Justificación estructurada de clasificación de riesgo desde el dataset procesado."""
        if self.score_col not in self.df.columns:
            return {"respuesta": "No hay scores en el dataset procesado. Active el motor IA tras cargar el Excel.", "datos": None}

        case_match = re.search(r"(sin-?\d+|\d{4,})", q)
        if case_match:
            return self._handle_case_query(q)

        sem_filter = None
        if any(w in q for w in ["riesgo alto", "alto", "rojo", "crítico", "critico"]):
            sem_filter = "Rojo"
        elif any(w in q for w in ["riesgo medio", "medio", "amarillo"]):
            sem_filter = "Amarillo"
        elif any(w in q for w in ["riesgo bajo", "bajo", "verde"]):
            sem_filter = "Verde"

        subset = self.df
        if sem_filter and self.semaforo_col in self.df.columns:
            subset = self.df[self.df[self.semaforo_col] == sem_filter]

        if subset.empty:
            subset = self.df.nlargest(5, self.score_col)

        lines = ["**Justificación de clasificación de riesgo (dataset cargado):**\n"]
        records = []
        for _, row in subset.nlargest(8, self.score_col).iterrows():
            score = float(row.get(self.score_col, 0) or 0)
            sem = row.get(self.semaforo_col, "N/A")
            nivel = self._risk_level_label(str(sem), score)
            alertas = row.get("alertas_reglas", "Sin alertas")
            reglas = row.get("reglas_criticas", "")
            ai_block = self._format_ai_signals(row)
            lines.append(f"**{row['id_siniestro']}** → {nivel} | Score: {score:.1f}/100")
            lines.append(f"- Alertas: {alertas}")
            if isinstance(reglas, str) and reglas.strip():
                lines.append(f"- Reglas críticas: {reglas}")
            if ai_block:
                lines.append(ai_block)
            lines.append("")
            records.append(row.to_dict())

        return {"respuesta": "\n".join(lines).strip(), "datos": records, "tipo": "explicabilidad"}

    def _is_case_query(self, q: str) -> bool:
        return bool(re.search(r"sin-?\d+|siniestro\s+\d+|caso\s+\d+|id\s+\d+", q))

    def _handle_case_query(self, q: str) -> Dict:
        match = re.search(r"(sin-?\d+|\d{4,})", q)
        if not match:
            return {"respuesta": "No pude identificar el número de siniestro.", "datos": None}

        case_id = match.group(1).upper()
        if not case_id.startswith("SIN-"):
            case_id = f"SIN-{case_id.zfill(6)}"

        mask = self.df["id_siniestro"].str.upper() == case_id
        if mask.sum() == 0:
            return {"respuesta": f"No se encontró el siniestro {case_id}.", "datos": None}

        row = self.df[mask].iloc[0]
        score = row.get(self.score_col, 0)
        semaforo = row.get(self.semaforo_col, "N/A")
        alertas = row.get("alertas_reglas", "Sin alertas")

        ai_block = self._format_ai_signals(row)
        nivel = self._risk_level_label(str(semaforo), float(score or 0))
        respuesta = (
            f"**Siniestro {case_id}**\n"
            f"## Clasificación de riesgo\n"
            f"- Nivel: **{nivel}** | Score híbrido: {score:.1f}/100\n"
            f"- Ramo: {row.get('ramo', 'N/A')} | Cobertura: {row.get('cobertura', 'N/A')}\n"
            f"- Monto reclamado: ${row.get('monto_reclamado', 0):,.2f}\n"
            f"- Asegurado: {row.get('id_asegurado', 'N/A')}\n"
            f"## Evidencia del archivo cargado\n"
            f"- Alertas detectadas: {alertas}\n"
        )
        reglas_crit = row.get("reglas_criticas", "")
        if isinstance(reglas_crit, str) and reglas_crit.strip():
            respuesta += f"- Reglas críticas activas: {reglas_crit}\n"
        if ai_block:
            respuesta += f"{ai_block}\n"
        respuesta += (
            f"- Proveedor: {row.get('beneficiario', 'N/A')}\n"
            f"- Fecha ocurrencia: {row.get('fecha_ocurrencia', 'N/A')}\n"
        )

        if row.get("score_documentos_max") and float(row.get("score_documentos_max") or 0) > 0:
            respuesta += (
                f"\n**Documentos PDF vinculados:**\n"
                f"- Score documental: {float(row['score_documentos_max']):.1f} "
                f"({row.get('semaforo_documento_peor', 'N/A')})\n"
                f"- PDFs analizados: {int(row.get('num_pdfs_cargados', 0) or 0)}\n"
            )
        doc_ctx = self.extra_context.get("documentos_subidos") or {}
        pdf_lines = []
        for item in (doc_ctx.get("items") or []):
            if str(item.get("siniestro", "")).upper() == case_id:
                pdf_lines.append(
                    f"  · {item.get('archivo')} ({item.get('tipo')}): "
                    f"{item.get('semaforo')} — {', '.join(item.get('alertas') or [])[:2]}"
                )
        if pdf_lines:
            respuesta += "\n".join(["", "**Detalle PDFs:**"] + pdf_lines) + "\n"

        return {"respuesta": respuesta, "datos": row.to_dict(), "tipo": "caso"}

    def _is_ml_query(self, q: str) -> bool:
        return any(w in q for w in [
            "probabilidad", "machine learning", "modelo ml", "modelo supervisado",
            "fraude ml", "predicción", "prediccion", "random forest", "anomalía",
            "anomalia", "isolation forest", "etiqueta simulada",
        ])

    def _handle_ml_query(self, q: str) -> Dict:
        if not self.ml_col and not self.anomaly_col:
            return {
                "respuesta": "El modelo supervisado o la detección de anomalías no se ejecutaron. "
                "Corra el pipeline completo desde la pestaña Datos.",
                "datos": None,
            }

        lines = ["**Análisis con Inteligencia Artificial**\n"]

        if self.ml_col:
            probs = self.df[self.ml_col].dropna()
            high = self.df[self.df[self.ml_col] >= 0.7]
            lines.append(
                f"- Modelo supervisado (Random Forest, etiqueta `etiqueta_fraude_simulada`):\n"
                f"  · Probabilidad promedio de fraude: {probs.mean()*100:.1f}%\n"
                f"  · Casos con probabilidad ≥ 70%: {len(high)} de {len(self.df)}\n"
                f"  · Máxima probabilidad: {probs.max()*100:.1f}%"
            )

        if self.anomaly_col:
            anom = self.df[self.anomaly_col].dropna()
            top_anom = self.df[self.df[self.anomaly_col] >= 0.75]
            lines.append(
                f"\n- Detección de anomalías (Isolation Forest):\n"
                f"  · Score de anomalía promedio: {anom.mean()*100:.1f}%\n"
                f"  · Casos con anomalía alta (≥75%): {len(top_anom)}\n"
                f"  · El score híbrido integra reglas (40%), ML (35%) y anomalías (25%)"
            )

        if self.score_col in self.df.columns:
            lines.append(
                f"\n- Score híbrido promedio: {self.df[self.score_col].mean():.1f}/100"
            )

        return {"respuesta": "\n".join(lines), "tipo": "ml_analisis"}

    def _is_summary_query(self, q: str) -> bool:
        return any(w in q for w in ["resumen", "general", "panorama", "overview", "estadísticas", "estadisticas"])

    def _handle_summary_query(self, q: str) -> Dict:
        total = len(self.df)
        if self.semaforo_col in self.df.columns:
            counts = self.df[self.semaforo_col].value_counts()
        else:
            counts = pd.Series(dtype=int)

        rojo = counts.get("Rojo", 0)
        amarillo = counts.get("Amarillo", 0)
        verde = counts.get("Verde", 0)
        score_prom = self.df[self.score_col].mean() if self.score_col in self.df.columns else 0

        respuesta = (
            f"**Resumen General del Análisis**\n"
            f"- Total de siniestros analizados: {total}\n"
            f"- Rojo (alto riesgo): {rojo} ({rojo/total*100:.1f}%)\n"
            f"- Amarillo (medio): {amarillo} ({amarillo/total*100:.1f}%)\n"
            f"- Verde (bajo): {verde} ({verde/total*100:.1f}%)\n"
            f"- Score promedio: {score_prom:.1f}/100\n"
        )

        if "monto_reclamado" in self.df.columns:
            monto_total = self.df["monto_reclamado"].sum()
            monto_rojo = self.df[self.df[self.semaforo_col] == "Rojo"]["monto_reclamado"].sum() if self.semaforo_col in self.df.columns else 0
            respuesta += f"- Monto total reclamado: ${monto_total:,.2f}\n"
            respuesta += f"- Monto en casos rojos: ${monto_rojo:,.2f}\n"

        return {"respuesta": respuesta, "tipo": "resumen"}

    def _is_top_risk_query(self, q: str) -> bool:
        return any(w in q for w in [
            "mayor riesgo", "más riesgo", "top", "peores", "críticos",
            "rojo", "sospechosos", "peligrosos", "prioritarios"
        ])

    def _handle_top_risk_query(self, q: str) -> Dict:
        n = 10
        match = re.search(r"(\d+)", q)
        if match:
            n = min(int(match.group(1)), 50)

        if self.score_col not in self.df.columns:
            return {"respuesta": "No hay scores calculados.", "datos": None}

        top = self.df.nlargest(n, self.score_col)
        lines = [f"**Top {n} casos de mayor riesgo:**\n"]
        for _, row in top.iterrows():
            semaforo = row.get(self.semaforo_col, "N/A")
            emoji = {"Rojo": "🔴", "Amarillo": "🟡", "Verde": "🟢"}.get(semaforo, "⚪")
            ml_txt = ""
            if self.ml_col and not pd.isna(row.get(self.ml_col)):
                ml_txt = f" | ML: {float(row[self.ml_col])*100:.0f}%"
            lines.append(
                f"{emoji} {row['id_siniestro']} | Score: {row[self.score_col]:.1f}{ml_txt} | "
                f"{row.get('ramo', 'N/A')} | ${row.get('monto_reclamado', 0):,.0f}"
            )

        return {"respuesta": "\n".join(lines), "datos": top.to_dict("records"), "tipo": "top_riesgo"}

    def _is_provider_query(self, q: str) -> bool:
        return any(w in q for w in ["proveedor", "taller", "clínica", "hospital", "beneficiario", "perito"])

    def _handle_provider_query(self, q: str) -> Dict:
        if "id_proveedor" not in self.df.columns:
            return {"respuesta": "No hay datos de proveedores disponibles.", "datos": None}

        prov_stats = self.df.groupby(["id_proveedor", "beneficiario"]).agg(
            siniestros=("id_siniestro", "count"),
            monto_total=("monto_reclamado", "sum"),
            score_promedio=(self.score_col, "mean") if self.score_col in self.df.columns else ("monto_reclamado", "mean"),
        ).reset_index().sort_values("score_promedio", ascending=False).head(10)

        lines = ["**Proveedores con mayor riesgo asociado:**\n"]
        for _, row in prov_stats.iterrows():
            lines.append(
                f"- {row['beneficiario']} | {int(row['siniestros'])} siniestros | "
                f"${row['monto_total']:,.0f} | Score prom: {row['score_promedio']:.1f}"
            )

        return {"respuesta": "\n".join(lines), "datos": prov_stats.to_dict("records"), "tipo": "proveedores"}

    def _is_insured_query(self, q: str) -> bool:
        return any(w in q for w in ["asegurado", "cliente", "persona"])

    def _handle_insured_query(self, q: str) -> Dict:
        match = re.search(r"(asg-?\d+)", q)
        if match:
            aseg_id = match.group(1).upper()
            if not aseg_id.startswith("ASG-"):
                aseg_id = f"ASG-{aseg_id}"
            mask = self.df["id_asegurado"].str.upper() == aseg_id
            if mask.sum() > 0:
                subset = self.df[mask]
                n_sin = len(subset)
                monto = subset["monto_reclamado"].sum() if "monto_reclamado" in subset.columns else 0
                score_max = subset[self.score_col].max() if self.score_col in subset.columns else 0
                respuesta = (
                    f"**Asegurado {aseg_id}:**\n"
                    f"- Siniestros: {n_sin}\n"
                    f"- Monto total reclamado: ${monto:,.2f}\n"
                    f"- Score máximo: {score_max:.1f}\n"
                )
                return {"respuesta": respuesta, "datos": subset.to_dict("records"), "tipo": "asegurado"}

        top_aseg = self.df.groupby("id_asegurado").agg(
            siniestros=("id_siniestro", "count"),
            monto_total=("monto_reclamado", "sum"),
            score_max=(self.score_col, "max") if self.score_col in self.df.columns else ("monto_reclamado", "max"),
        ).reset_index().sort_values("score_max", ascending=False).head(10)

        lines = ["**Asegurados con mayor riesgo:**\n"]
        for _, row in top_aseg.iterrows():
            lines.append(
                f"- {row['id_asegurado']} | {int(row['siniestros'])} siniestros | "
                f"${row['monto_total']:,.0f} | Score máx: {row['score_max']:.1f}"
            )
        return {"respuesta": "\n".join(lines), "datos": top_aseg.to_dict("records"), "tipo": "asegurados"}

    def _is_branch_query(self, q: str) -> bool:
        return any(w in q for w in ["ramo", "línea", "tipo de seguro"])

    def _handle_branch_query(self, q: str) -> Dict:
        if "ramo" not in self.df.columns:
            return {"respuesta": "No hay datos de ramo disponibles.", "datos": None}

        ramo_stats = self.df.groupby("ramo").agg(
            siniestros=("id_siniestro", "count"),
            monto_total=("monto_reclamado", "sum"),
            score_promedio=(self.score_col, "mean") if self.score_col in self.df.columns else ("monto_reclamado", "mean"),
            rojos=(self.semaforo_col, lambda x: (x == "Rojo").sum()) if self.semaforo_col in self.df.columns else ("id_siniestro", "count"),
        ).reset_index().sort_values("score_promedio", ascending=False)

        lines = ["**Análisis por ramo:**\n"]
        for _, row in ramo_stats.iterrows():
            lines.append(
                f"- {row['ramo']} | {int(row['siniestros'])} siniestros | "
                f"${row['monto_total']:,.0f} | Score prom: {row['score_promedio']:.1f} | "
                f"Rojos: {int(row['rojos'])}"
            )
        return {"respuesta": "\n".join(lines), "datos": ramo_stats.to_dict("records"), "tipo": "ramos"}

    def _is_vehicle_query(self, q: str) -> bool:
        return any(w in q for w in ["vehículo", "vehiculo", "placa", "auto", "carro", "marca"])

    def _handle_vehicle_query(self, q: str) -> Dict:
        if "id_vehiculo" not in self.df.columns:
            return {"respuesta": "No hay datos de vehículos.", "datos": None}

        veh_stats = self.df.groupby("id_vehiculo").agg(
            siniestros=("id_siniestro", "count"),
            score_max=(self.score_col, "max") if self.score_col in self.df.columns else ("monto_reclamado", "max"),
        ).reset_index().sort_values("score_max", ascending=False).head(10)

        lines = ["**Vehículos con mayor riesgo:**\n"]
        for _, row in veh_stats.iterrows():
            lines.append(f"- {row['id_vehiculo']} | {int(row['siniestros'])} siniestros | Score máx: {row['score_max']:.1f}")
        return {"respuesta": "\n".join(lines), "datos": veh_stats.to_dict("records"), "tipo": "vehiculos"}

    def _is_coverage_query(self, q: str) -> bool:
        return any(w in q for w in ["cobertura", "choque", "robo", "incendio", "pérdida total"])

    def _handle_coverage_query(self, q: str) -> Dict:
        if "cobertura" not in self.df.columns:
            return {"respuesta": "No hay datos de cobertura.", "datos": None}

        cob_stats = self.df.groupby("cobertura").agg(
            siniestros=("id_siniestro", "count"),
            monto_total=("monto_reclamado", "sum"),
            score_promedio=(self.score_col, "mean") if self.score_col in self.df.columns else ("monto_reclamado", "mean"),
        ).reset_index().sort_values("score_promedio", ascending=False)

        lines = ["**Análisis por cobertura:**\n"]
        for _, row in cob_stats.iterrows():
            lines.append(
                f"- {row['cobertura']} | {int(row['siniestros'])} siniestros | "
                f"${row['monto_total']:,.0f} | Score prom: {row['score_promedio']:.1f}"
            )
        return {"respuesta": "\n".join(lines), "datos": cob_stats.to_dict("records"), "tipo": "coberturas"}

    def _is_pattern_query(self, q: str) -> bool:
        return any(w in q for w in ["patrón", "patron", "tendencia", "anomalía", "anomalia"])

    def _handle_pattern_query(self, q: str) -> Dict:
        patterns = []

        if "frecuencia_siniestros_asegurado" in self.df.columns:
            high_freq = self.df[self.df["frecuencia_siniestros_asegurado"] >= 3]
            if len(high_freq) > 0:
                patterns.append(f"- {len(high_freq)} siniestros de asegurados con alta frecuencia (≥3 reclamos)")

        if self.semaforo_col in self.df.columns and "ramo" in self.df.columns:
            ramo_risk = self.df[self.df[self.semaforo_col] == "Rojo"].groupby("ramo").size()
            if len(ramo_risk) > 0:
                top_ramo = ramo_risk.idxmax()
                patterns.append(f"- Ramo con más casos rojos: {top_ramo} ({ramo_risk.max()} casos)")

        if "prov_en_lista_restrictiva" in self.df.columns:
            lista_rest = self.df[self.df["prov_en_lista_restrictiva"] == 1]
            if len(lista_rest) > 0:
                patterns.append(f"- {len(lista_rest)} siniestros vinculados a proveedores en lista restrictiva")

        if "borde_inicio_vigencia" in self.df.columns:
            borde = self.df[self.df["borde_inicio_vigencia"] == 1]
            if len(borde) > 0:
                patterns.append(f"- {len(borde)} siniestros cercanos al inicio de vigencia de la póliza")

        if self.anomaly_col:
            high_anom = self.df[self.df[self.anomaly_col] >= 0.75]
            if len(high_anom) > 0:
                patterns.append(
                    f"- {len(high_anom)} siniestros con comportamiento atípico (anomalía ≥ 75%)"
                )

        if self.ml_col:
            high_ml = self.df[self.df[self.ml_col] >= 0.7]
            if len(high_ml) > 0:
                patterns.append(
                    f"- {len(high_ml)} siniestros con alta probabilidad ML de fraude (≥ 70%)"
                )

        if not patterns:
            patterns.append("- No se detectaron patrones significativos con los datos actuales.")

        respuesta = "**Patrones y anomalías detectados:**\n\n" + "\n".join(patterns)
        return {"respuesta": respuesta, "tipo": "patrones"}

    def _is_alert_query(self, q: str) -> bool:
        return any(w in q for w in ["alerta", "señal", "regla"])

    def _handle_alert_query(self, q: str) -> Dict:
        if "num_alertas" in self.df.columns:
            with_alerts = self.df[self.df["num_alertas"] > 0]
            total_alerts = self.df["num_alertas"].sum()
            respuesta = (
                f"**Resumen de alertas:**\n"
                f"- Total de alertas generadas: {int(total_alerts)}\n"
                f"- Siniestros con al menos una alerta: {len(with_alerts)}\n"
                f"- Promedio de alertas por siniestro: {self.df['num_alertas'].mean():.1f}\n"
            )
        else:
            respuesta = "No hay alertas calculadas aún."
        return {"respuesta": respuesta, "tipo": "alertas"}

    def _is_count_query(self, q: str) -> bool:
        return any(w in q for w in ["cuántos", "cuantos", "cantidad", "número", "total de"])

    def _handle_count_query(self, q: str) -> Dict:
        total = len(self.df)
        respuesta = f"Total de siniestros en el dataset: {total}"
        if self.semaforo_col in self.df.columns:
            counts = self.df[self.semaforo_col].value_counts()
            respuesta += f"\n- Rojos: {counts.get('Rojo', 0)} | Amarillos: {counts.get('Amarillo', 0)} | Verdes: {counts.get('Verde', 0)}"
        return {"respuesta": respuesta, "tipo": "conteo"}

    def _is_amount_query(self, q: str) -> bool:
        return any(w in q for w in ["monto", "valor", "dinero", "costo", "facturado", "pagado"])

    def _handle_amount_query(self, q: str) -> Dict:
        if "monto_reclamado" not in self.df.columns:
            return {"respuesta": "No hay datos de montos.", "datos": None}

        total = self.df["monto_reclamado"].sum()
        promedio = self.df["monto_reclamado"].mean()
        maximo = self.df["monto_reclamado"].max()
        respuesta = (
            f"**Análisis de montos:**\n"
            f"- Monto total reclamado: ${total:,.2f}\n"
            f"- Monto promedio: ${promedio:,.2f}\n"
            f"- Monto máximo: ${maximo:,.2f}\n"
        )
        if self.semaforo_col in self.df.columns:
            for sem in ["Rojo", "Amarillo", "Verde"]:
                subset = self.df[self.df[self.semaforo_col] == sem]
                if len(subset) > 0:
                    respuesta += f"- Monto total {sem}: ${subset['monto_reclamado'].sum():,.2f}\n"
        return {"respuesta": respuesta, "tipo": "montos"}

    def _handle_general_query(self, q: str) -> Dict:
        if self.score_col in self.df.columns and len(self.df) > 0:
            return self._handle_explainability_query(
                "explica las alertas y justifica la clasificación de riesgo del archivo cargado"
            )
        return {
            "respuesta": (
                "No hay dataset procesado. Cargue un Excel en «Carga Inteligente de Datos» "
                "y pulse «Activar motor IA». Luego consulte aquí por alertas, semáforos o casos específicos."
            ),
            "tipo": "ayuda",
        }
