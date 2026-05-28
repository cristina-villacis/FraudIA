"""
Agente de IA explicativo para consultas en lenguaje natural.
Permite al analista hacer preguntas sobre casos, alertas, proveedores y patrones.
Con OPENAI_API_KEY en .env, enriquece respuestas vía ChatGPT usando solo datos del pipeline.
"""
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.ai_agent.llm_router import enhance_with_llm, get_llm_provider, llm_status


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

    def build_dataset_context(self, max_top: int = 8) -> str:
        """Contexto compacto para ChatGPT (estadísticas + top riesgo)."""
        total = len(self.df)
        lines = [f"Total siniestros: {total}"]

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

        if self.score_col in self.df.columns:
            top = self.df.nlargest(max_top, self.score_col)
            lines.append("Top casos por score:")
            for _, row in top.iterrows():
                sem = row.get(self.semaforo_col, "N/A")
                ml = ""
                if self.ml_col and not pd.isna(row.get(self.ml_col)):
                    ml = f", ML={float(row[self.ml_col])*100:.0f}%"
                lines.append(
                    f"  - {row['id_siniestro']}: score={row[self.score_col]:.1f}, "
                    f"{sem}{ml}, ramo={row.get('ramo', 'N/A')}"
                )

        dashboard_snapshot = self.extra_context.get("dashboard_snapshot")
        if isinstance(dashboard_snapshot, dict):
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
            lines.append(str(exec_sum)[:1200])

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

        return "\n".join(lines)

    def _use_external_llm(self) -> bool:
        return get_llm_provider() != "local"

    def _apply_response_style(self, text: str) -> str:
        """Aplica formato base consistente para respuestas del agente."""
        clean = (text or "").strip()
        if not clean:
            return "# 🤖 FraudIA Claims\n\nNo se encontró información para responder la consulta."
        if clean.startswith("#"):
            return clean
        return f"# 🤖 FraudIA Claims\n\n{clean}"

    def query(self, question: str) -> Dict:
        question_lower = question.lower().strip()

        handlers = [
            (self._is_case_query, self._handle_case_query),
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

        result = None
        for check, handler in handlers:
            if check(question_lower):
                result = handler(question_lower)
                break
        if result is None:
            result = self._handle_general_query(question_lower)

        result.setdefault("motor", "reglas-local")
        status = llm_status()
        result.update(status)
        result["openai_used"] = False
        result["gemini_used"] = False

        if self._use_external_llm() and result.get("tipo") not in ("ayuda",):
            factual = result.get("respuesta", "")
            context = self.build_dataset_context()
            if result.get("datos") and isinstance(result["datos"], dict):
                context += "\n\nDetalle caso:\n" + str(
                    {k: result["datos"].get(k) for k in (
                        "id_siniestro", "score_hibrido", "score_reglas",
                        "ml_fraud_probability", "anomaly_score",
                        "semaforo_final", "alertas_reglas", "reglas_criticas",
                        "ramo", "cobertura", "monto_reclamado",
                    ) if k in result["datos"]}
                )
            enhanced, motor = enhance_with_llm(question, factual, context)
            if enhanced:
                result["respuesta"] = enhanced
                result["motor"] = motor
                result["openai_used"] = motor.startswith("chatgpt")
                result["gemini_used"] = motor.startswith("gemini")
            else:
                result["motor"] = motor

        result["respuesta"] = self._apply_response_style(result.get("respuesta", ""))
        return result

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
        respuesta = (
            f"**Siniestro {case_id}**\n"
            f"- Score híbrido de riesgo: {score:.1f}/100 ({semaforo})\n"
            f"- Ramo: {row.get('ramo', 'N/A')} | Cobertura: {row.get('cobertura', 'N/A')}\n"
            f"- Monto reclamado: ${row.get('monto_reclamado', 0):,.2f}\n"
            f"- Asegurado: {row.get('id_asegurado', 'N/A')}\n"
            f"- Proveedor: {row.get('beneficiario', 'N/A')}\n"
            f"- Fecha ocurrencia: {row.get('fecha_ocurrencia', 'N/A')}\n"
            f"- Alertas: {alertas}\n"
        )
        if ai_block:
            respuesta += f"\n**Señales de IA:**\n{ai_block}\n"

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
        return {
            "respuesta": (
                "Puedo ayudarte con consultas sobre:\n"
                "- **Casos específicos**: 'Detalle del siniestro SIN-000001'\n"
                "- **Resumen general**: '¿Cuál es el panorama general?'\n"
                "- **Top riesgos**: '¿Cuáles son los 10 casos más riesgosos?'\n"
                "- **Proveedores**: '¿Qué proveedores tienen más riesgo?'\n"
                "- **Asegurados**: '¿Qué asegurados tienen más reclamos?'\n"
                "- **Ramos/Coberturas**: 'Análisis por ramo'\n"
                "- **Patrones**: '¿Qué patrones se detectaron?'\n"
                "- **Alertas**: '¿Cuántas alertas hay?'\n"
                "- **Montos**: '¿Cuál es el monto total reclamado?'\n"
                "- **Vehículos**: '¿Qué vehículos tienen más siniestros?'\n"
                "- **IA / ML**: '¿Cuál es la probabilidad de fraude del modelo?'\n"
            ),
            "tipo": "ayuda",
        }
