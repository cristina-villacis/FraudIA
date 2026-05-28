"""
Módulo de Machine Learning para detección de fraude.
- Modelo supervisado: Random Forest (predicción de probabilidad de fraude)
- Detección de anomalías: Isolation Forest
- Enfoque híbrido: Combinación de score de reglas, ML y anomalías
"""
import os
import warnings
from typing import Dict, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    precision_recall_curve,
    f1_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

MODEL_DIR = os.path.join("src", "models", "saved")


def _is_vercel_runtime() -> bool:
    return bool(
        os.getenv("VERCEL")
        or os.getenv("VERCEL_DEPLOYMENT_ID")
        or os.getenv("VERCEL_ENV")
    )


def _resolve_model_dir() -> str:
    # En runtimes serverless (Vercel) solo /tmp es escribible.
    if _is_vercel_runtime():
        return "/tmp/fraudia_models"
    return MODEL_DIR


def _safe_dump(obj, filename: str) -> None:
    """
    Persistencia best-effort: no rompe el pipeline si el filesystem es read-only.
    """
    model_dir = _resolve_model_dir()
    try:
        os.makedirs(model_dir, exist_ok=True)
        joblib.dump(obj, os.path.join(model_dir, filename))
    except Exception as exc:
        warnings.warn(f"No se pudo guardar '{filename}' en disco: {exc}")


def prepare_features(df: pd.DataFrame, feature_cols: list) -> Tuple[pd.DataFrame, list]:
    from src.utils.dataframe_columns import ensure_str_columns

    df = ensure_str_columns(df)
    feature_cols = [str(c) for c in feature_cols if str(c) in df.columns]

    X = df[feature_cols].copy()
    X.columns = [str(c) for c in X.columns]

    for col in X.select_dtypes(include=["object", "category"]).columns:
        X[col] = pd.Categorical(X[col]).codes

    X = X.fillna(0)
    X = X.replace([np.inf, -np.inf], 0)

    valid_cols = [str(c) for c in X.columns if X[c].std() > 0]
    X = X[valid_cols]
    X.columns = [str(c) for c in X.columns]

    return X, valid_cols


def train_supervised_model(
    df: pd.DataFrame,
    feature_cols: list,
    target_col: str = "etiqueta_fraude_simulada",
) -> Dict:
    if target_col not in df.columns:
        return {"error": f"Columna objetivo '{target_col}' no encontrada"}

    X, valid_cols = prepare_features(df, feature_cols)
    if not valid_cols:
        return {"error": "No hay variables numéricas válidas para entrenar el modelo supervisado."}

    y = df[target_col].fillna(0).astype(int)
    if y.nunique() < 2:
        return {
            "error": (
                "La columna 'etiqueta_fraude_simulada' debe contener al menos dos clases (0 y 1) "
                "para entrenar el modelo supervisado."
            )
        }

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train.values)
    X_test_scaled = scaler.transform(X_test.values)

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train_scaled, y_train)

    y_pred = model.predict(X_test_scaled)
    y_proba = model.predict_proba(X_test_scaled)[:, 1]

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    X_arr = scaler.transform(X.values)
    cv_scores = cross_val_score(model, X_arr, y, cv=cv, scoring="roc_auc")

    importances = pd.DataFrame({
        "feature": valid_cols,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)

    _safe_dump(model, "rf_fraud_model.joblib")
    _safe_dump(scaler, "scaler.joblib")
    _safe_dump(valid_cols, "feature_cols.joblib")

    auc = roc_auc_score(y_test, y_proba)
    report = classification_report(y_test, y_pred, output_dict=True)
    cm = confusion_matrix(y_test, y_pred)

    return {
        "model": model,
        "scaler": scaler,
        "feature_cols": valid_cols,
        "auc_roc": round(auc, 4),
        "cv_auc_mean": round(cv_scores.mean(), 4),
        "cv_auc_std": round(cv_scores.std(), 4),
        "classification_report": report,
        "confusion_matrix": cm.tolist(),
        "feature_importance": importances.to_dict("records"),
        "n_train": len(X_train),
        "n_test": len(X_test),
    }


def train_anomaly_model(
    df: pd.DataFrame,
    feature_cols: list,
    contamination: float = 0.10,
) -> Dict:
    X, valid_cols = prepare_features(df, feature_cols)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    iso_forest = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        max_samples="auto",
        random_state=42,
        n_jobs=-1,
    )
    iso_forest.fit(X_scaled)

    anomaly_labels = iso_forest.predict(X_scaled)
    anomaly_scores = iso_forest.decision_function(X_scaled)

    anomaly_scores_norm = 1 - (anomaly_scores - anomaly_scores.min()) / (
        anomaly_scores.max() - anomaly_scores.min() + 1e-8
    )

    _safe_dump(iso_forest, "isolation_forest.joblib")
    _safe_dump(scaler, "anomaly_scaler.joblib")

    n_anomalies = (anomaly_labels == -1).sum()

    return {
        "model": iso_forest,
        "scaler": scaler,
        "feature_cols": valid_cols,
        "anomaly_labels": anomaly_labels,
        "anomaly_scores": anomaly_scores_norm,
        "n_anomalies": int(n_anomalies),
        "n_total": len(X),
        "contamination": contamination,
    }


def predict_fraud_probability(
    df: pd.DataFrame,
    model=None,
    scaler=None,
    feature_cols: list = None,
) -> np.ndarray:
    if model is None:
        model_dir = _resolve_model_dir()
        model = joblib.load(os.path.join(model_dir, "rf_fraud_model.joblib"))
        scaler = joblib.load(os.path.join(model_dir, "scaler.joblib"))
        feature_cols = joblib.load(os.path.join(model_dir, "feature_cols.joblib"))

    feature_cols = [str(c) for c in feature_cols]
    X, _ = prepare_features(df, feature_cols)
    for col in feature_cols:
        if col not in X.columns:
            X[col] = 0
    X = X[feature_cols]
    X.columns = X.columns.astype(str)
    X_scaled = scaler.transform(X.values)
    return model.predict_proba(X_scaled)[:, 1]


def compute_hybrid_score(
    df: pd.DataFrame,
    rule_score_col: str = "score_reglas",
    ml_proba_col: str = "ml_fraud_probability",
    anomaly_score_col: str = "anomaly_score",
    weights: Dict[str, float] = None,
) -> pd.DataFrame:
    """
    Score híbrido: combinación ponderada de reglas, ML supervisado y anomalías.
    """
    if weights is None:
        weights = {"rules": 0.40, "ml": 0.35, "anomaly": 0.25}

    from src.utils.dataframe_columns import ensure_str_columns

    df = ensure_str_columns(df.copy())

    rule_norm = df[rule_score_col].fillna(0) / 100 if rule_score_col in df.columns else 0
    ml_norm = df[ml_proba_col].fillna(0) if ml_proba_col in df.columns else 0
    anomaly_norm = df[anomaly_score_col].fillna(0) if anomaly_score_col in df.columns else 0

    df["score_hibrido"] = np.round(
        (rule_norm * weights["rules"] +
         ml_norm * weights["ml"] +
         anomaly_norm * weights["anomaly"]) * 100,
        1
    )
    df["score_hibrido"] = df["score_hibrido"].clip(0, 100)

    if rule_score_col in df.columns:
        df["score_hibrido"] = df[["score_hibrido", rule_score_col]].max(axis=1)

    from src.risk.classification import classify_risk, get_risk_metadata

    df["semaforo_final"] = df["score_hibrido"].apply(classify_risk)

    if "semaforo_reglas" in df.columns:
        risk_rank = {"Verde": 0, "Amarillo": 1, "Rojo": 2}

        def _max_semaforo(a, b):
            return a if risk_rank.get(a, 0) >= risk_rank.get(b, 0) else b

        df["semaforo_final"] = [
            _max_semaforo(sr, sf)
            for sr, sf in zip(df["semaforo_reglas"], df["semaforo_final"])
        ]
    meta = df["semaforo_final"].apply(get_risk_metadata)
    df["nivel_riesgo"] = meta.apply(lambda m: m["nivel"])
    df["accion_sugerida"] = meta.apply(lambda m: m["accion"])

    return df


def get_model_metrics_summary(results: Dict) -> Dict:
    return {
        "auc_roc": results.get("auc_roc", 0),
        "cv_auc_mean": results.get("cv_auc_mean", 0),
        "precision_fraude": round(results.get("classification_report", {}).get("1", {}).get("precision", 0), 3),
        "recall_fraude": round(results.get("classification_report", {}).get("1", {}).get("recall", 0), 3),
        "f1_fraude": round(results.get("classification_report", {}).get("1", {}).get("f1-score", 0), 3),
        "top_features": results.get("feature_importance", [])[:10],
    }
