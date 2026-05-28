"""Script para ejecutar el pipeline completo y exportar datasets."""
import sys
import os

sys.path.insert(0, ".")

from src.ingestion.load_data import load_all_from_directory
from src.features.build_features import build_all_features, get_feature_columns
from src.rules.fraud_rules import apply_rules, get_rules_summary
from src.nlp.text_analysis import get_similarity_scores_by_id
from src.models.fraud_model import (
    train_supervised_model,
    train_anomaly_model,
    compute_hybrid_score,
    predict_fraud_probability,
)
from src.app.powerbi_export import export_to_powerbi, export_csv_for_powerbi
import pandas as pd

print("1. Cargando datos...")
datasets = load_all_from_directory("data/synthetic")
for n, d in datasets.items():
    print(f"   {n}: {d.shape}")

print("2. Feature engineering...")
df = build_all_features(datasets)

print("3. NLP similitud textual...")
sim = get_similarity_scores_by_id(df)

print("4. Reglas de negocio...")
df = apply_rules(df, sim)
s = get_rules_summary(df)
print(f"   Rojo: {s['rojo']} | Amarillo: {s['amarillo']} | Verde: {s['verde']}")

print("5. Modelo supervisado (Random Forest)...")
fcols = get_feature_columns(df)
ml = train_supervised_model(df, fcols)
print(f"   AUC-ROC: {ml['auc_roc']}")
df["ml_fraud_probability"] = predict_fraud_probability(
    df, ml["model"], ml["scaler"], ml["feature_cols"]
)

print("6. Deteccion de anomalias (Isolation Forest)...")
anom = train_anomaly_model(df, fcols)
df["anomaly_score"] = anom["anomaly_scores"]
print(f"   Anomalias: {anom['n_anomalies']}")

print("7. Score hibrido...")
df = compute_hybrid_score(df)
counts = df["semaforo_final"].value_counts().to_dict()
print(f"   Rojo: {counts.get('Rojo', 0)} | Amarillo: {counts.get('Amarillo', 0)} | Verde: {counts.get('Verde', 0)}")

print("8. Exportando datasets...")
os.makedirs("data/processed", exist_ok=True)

cols_drop = [c for c in df.columns if c == "detalle_reglas"]
df_export = df.drop(columns=cols_drop, errors="ignore")

out = "data/processed/dataset_completo_scored.xlsx"
with pd.ExcelWriter(out, engine="xlsxwriter") as w:
    df_export.to_excel(w, sheet_name="siniestros_scored", index=False)
    for name, d in datasets.items():
        if name != "siniestros":
            d.to_excel(w, sheet_name=name, index=False)

df_export.to_csv("data/processed/siniestros_scored.csv", index=False, encoding="utf-8-sig")
export_to_powerbi(datasets, df, "data/processed/powerbi_export.xlsx")

print("")
print("=" * 55)
print("  EXPORTACION COMPLETA")
print("=" * 55)
print(f"  data/synthetic/dataset_completo.xlsx   (datos crudos)")
print(f"  data/processed/dataset_completo_scored.xlsx (con scores)")
print(f"  data/processed/powerbi_export.xlsx     (para Power BI)")
print(f"  data/processed/siniestros_scored.csv   (CSV plano)")
print(f"")
print(f"  Total registros: {len(df_export)}")
print(f"  Columnas: {len(df_export.columns)}")
print(f"  Score promedio: {df_export['score_hibrido'].mean():.1f}")
print("=" * 55)
