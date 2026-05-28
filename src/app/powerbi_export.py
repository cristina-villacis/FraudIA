"""
Módulo de exportación para Power BI.
Genera archivos Excel optimizados con múltiples hojas para consumo directo en Power BI.
"""
import os
from typing import Dict

import numpy as np
import pandas as pd


def export_to_powerbi(
    datasets: Dict[str, pd.DataFrame],
    df_scored: pd.DataFrame,
    output_path: str = "data/processed/powerbi_export.xlsx",
) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        _write_main_dashboard(writer, df_scored)
        _write_semaforo_summary(writer, df_scored)
        _write_ramo_analysis(writer, df_scored)
        _write_provider_analysis(writer, df_scored)
        _write_temporal_analysis(writer, df_scored)
        _write_alerts_detail(writer, df_scored)

        for name, df in datasets.items():
            if name != "siniestros":
                sheet_name = name[:31]
                df.to_excel(writer, sheet_name=sheet_name, index=False)

    return output_path


def _write_main_dashboard(writer, df: pd.DataFrame):
    cols_export = [
        "id_siniestro", "id_poliza", "id_asegurado", "ramo", "cobertura",
        "fecha_ocurrencia", "fecha_reporte", "monto_reclamado", "monto_estimado",
        "monto_pagado", "estado", "sucursal", "documentos_completos",
        "beneficiario", "dias_desde_inicio_poliza", "dias_entre_ocurrencia_reporte",
    ]

    score_cols = ["score_reglas", "ml_fraud_probability", "anomaly_score",
                  "score_hibrido", "semaforo_final", "num_alertas", "alertas_reglas"]
    cols_export.extend([c for c in score_cols if c in df.columns])

    available = [c for c in cols_export if c in df.columns]
    export_df = df[available].copy()

    for col in export_df.select_dtypes(include=["datetime64"]).columns:
        export_df[col] = export_df[col].dt.strftime("%Y-%m-%d")

    if "detalle_reglas" in export_df.columns:
        export_df = export_df.drop(columns=["detalle_reglas"], errors="ignore")

    export_df.to_excel(writer, sheet_name="Dashboard_Principal", index=False)

    workbook = writer.book
    worksheet = writer.sheets["Dashboard_Principal"]

    red_format = workbook.add_format({"bg_color": "#FF6B6B", "font_color": "#FFFFFF"})
    yellow_format = workbook.add_format({"bg_color": "#FFD93D", "font_color": "#333333"})
    green_format = workbook.add_format({"bg_color": "#6BCB77", "font_color": "#FFFFFF"})

    if "semaforo_final" in available:
        sem_col_idx = available.index("semaforo_final")
        for row_num in range(1, len(export_df) + 1):
            val = export_df.iloc[row_num - 1].get("semaforo_final", "")
            if val == "Rojo":
                worksheet.write(row_num, sem_col_idx, val, red_format)
            elif val == "Amarillo":
                worksheet.write(row_num, sem_col_idx, val, yellow_format)
            elif val == "Verde":
                worksheet.write(row_num, sem_col_idx, val, green_format)


def _write_semaforo_summary(writer, df: pd.DataFrame):
    semaforo_col = "semaforo_final" if "semaforo_final" in df.columns else "semaforo_reglas"
    score_col = "score_hibrido" if "score_hibrido" in df.columns else "score_reglas"

    if semaforo_col not in df.columns:
        return

    summary = df.groupby(semaforo_col).agg(
        Total_Siniestros=("id_siniestro", "count"),
        Monto_Total_Reclamado=("monto_reclamado", "sum"),
        Monto_Promedio=("monto_reclamado", "mean"),
        Score_Promedio=(score_col, "mean"),
        Score_Maximo=(score_col, "max"),
    ).reset_index()

    summary.columns = ["Semáforo", "Total Siniestros", "Monto Total", "Monto Promedio", "Score Promedio", "Score Máximo"]
    summary.to_excel(writer, sheet_name="Resumen_Semaforo", index=False)


def _write_ramo_analysis(writer, df: pd.DataFrame):
    if "ramo" not in df.columns:
        return

    score_col = "score_hibrido" if "score_hibrido" in df.columns else "score_reglas"
    semaforo_col = "semaforo_final" if "semaforo_final" in df.columns else "semaforo_reglas"

    ramo_stats = df.groupby("ramo").agg(
        Total_Siniestros=("id_siniestro", "count"),
        Monto_Total=("monto_reclamado", "sum"),
        Score_Promedio=(score_col, "mean"),
        Casos_Rojos=(semaforo_col, lambda x: (x == "Rojo").sum()),
        Casos_Amarillos=(semaforo_col, lambda x: (x == "Amarillo").sum()),
        Casos_Verdes=(semaforo_col, lambda x: (x == "Verde").sum()),
    ).reset_index().round(2)
    ramo_stats.to_excel(writer, sheet_name="Analisis_Ramo", index=False)


def _write_provider_analysis(writer, df: pd.DataFrame):
    if "id_proveedor" not in df.columns:
        return

    score_col = "score_hibrido" if "score_hibrido" in df.columns else "score_reglas"

    prov_stats = df.groupby(["id_proveedor", "beneficiario"]).agg(
        Siniestros=("id_siniestro", "count"),
        Monto_Total=("monto_reclamado", "sum"),
        Score_Promedio=(score_col, "mean"),
        Score_Maximo=(score_col, "max"),
    ).reset_index().sort_values("Score_Promedio", ascending=False).round(2)
    prov_stats.to_excel(writer, sheet_name="Analisis_Proveedores", index=False)


def _write_temporal_analysis(writer, df: pd.DataFrame):
    if "fecha_ocurrencia" not in df.columns:
        return

    df_temp = df.copy()
    fecha = pd.to_datetime(df_temp["fecha_ocurrencia"], errors="coerce")
    df_temp["mes_ocurrencia"] = fecha.dt.to_period("M").astype(str)

    score_col = "score_hibrido" if "score_hibrido" in df_temp.columns else "score_reglas"

    temporal = df_temp.groupby("mes_ocurrencia").agg(
        Siniestros=("id_siniestro", "count"),
        Monto_Total=("monto_reclamado", "sum"),
        Score_Promedio=(score_col, "mean"),
    ).reset_index().round(2)
    temporal.to_excel(writer, sheet_name="Analisis_Temporal", index=False)


def _write_alerts_detail(writer, df: pd.DataFrame):
    if "alertas_reglas" not in df.columns:
        return

    score_col = "score_hibrido" if "score_hibrido" in df.columns else "score_reglas"
    semaforo_col = "semaforo_final" if "semaforo_final" in df.columns else "semaforo_reglas"

    alerts_df = df[df["num_alertas"] > 0][
        ["id_siniestro", "ramo", "cobertura", "monto_reclamado",
         score_col, semaforo_col, "num_alertas", "alertas_reglas"]
    ].sort_values(score_col, ascending=False)

    alerts_df.to_excel(writer, sheet_name="Detalle_Alertas", index=False)


def export_csv_for_powerbi(df_scored: pd.DataFrame, output_dir: str = "data/processed/") -> Dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    files = {}

    main_path = os.path.join(output_dir, "siniestros_scored.csv")
    cols = [c for c in df_scored.columns if c != "detalle_reglas"]
    df_scored[cols].to_csv(main_path, index=False, encoding="utf-8-sig")
    files["siniestros_scored"] = main_path

    return files
