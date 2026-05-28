"""
Repositorio de datos - CRUD entre DataFrames de pandas y la base de datos.
Maneja la persistencia bidireccional: DataFrame <-> MySQL/SQLite.
"""
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy import text, inspect

from src.db.config import get_engine, get_session
from src.db.models import (
    Base, Asegurado, Vehiculo, Poliza, Proveedor,
    Siniestro, Documento, AnalisisRun,
)

TABLE_MODEL_MAP = {
    "asegurados": Asegurado,
    "vehiculos": Vehiculo,
    "polizas": Poliza,
    "proveedores": Proveedor,
    "siniestros": Siniestro,
    "documentos": Documento,
}


def init_database():
    engine = get_engine()
    Base.metadata.create_all(engine)
    return True


def drop_all_data():
    engine = get_engine()
    is_mysql = "mysql" in str(engine.url)
    tables_order = ["documentos", "siniestros", "polizas", "vehiculos", "proveedores", "asegurados", "analisis_runs"]

    with engine.begin() as conn:
        if is_mysql:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for t in tables_order:
            try:
                conn.execute(text(f"DELETE FROM {t}"))
            except Exception:
                pass
        if is_mysql:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))


def save_dataframe(df: pd.DataFrame, table_name: str) -> int:
    engine = get_engine()
    df_clean = _prepare_for_db(df, table_name)
    is_mysql = "mysql" in str(engine.url)

    if is_mysql:
        cols = list(df_clean.columns)
        col_names = ", ".join(cols)
        placeholders = ", ".join(f":{c}" for c in cols)
        sql = text(f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})")

        inserted = 0
        with engine.begin() as conn:
            for _, row in df_clean.iterrows():
                params = {}
                for c in cols:
                    val = row[c]
                    if val is None or (isinstance(val, float) and val != val):
                        params[c] = None
                    elif hasattr(val, "item"):
                        params[c] = val.item()
                    else:
                        params[c] = val
                try:
                    conn.execute(sql, params)
                    inserted += 1
                except Exception:
                    pass
        return inserted
    else:
        df_clean.to_sql(table_name, engine, if_exists="append", index=False, method="multi", chunksize=500)
        return len(df_clean)


def save_all_datasets(datasets: Dict[str, pd.DataFrame]) -> Dict[str, int]:
    order = ["asegurados", "vehiculos", "polizas", "proveedores", "siniestros", "documentos"]
    results = {}
    engine = get_engine()
    is_mysql = "mysql" in str(engine.url)

    init_database()

    if is_mysql:
        with engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))

    drop_all_data()

    for table_name in order:
        if table_name in datasets:
            try:
                count = save_dataframe(datasets[table_name], table_name)
                results[table_name] = count
            except Exception as e:
                results[table_name] = f"error: {str(e)[:60]}"

    for name, df in datasets.items():
        if name not in order:
            try:
                count = save_dataframe(df, name)
                results[name] = count
            except Exception as e:
                results[name] = f"error: {str(e)[:60]}"

    if is_mysql:
        with engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

    return results


def load_dataframe(table_name: str) -> Optional[pd.DataFrame]:
    from src.utils.dataframe_columns import ensure_str_columns

    engine = get_engine()
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return None
    df = pd.read_sql_table(table_name, engine)
    if df.empty:
        return None
    return ensure_str_columns(df)


def load_all_datasets() -> Dict[str, pd.DataFrame]:
    datasets = {}
    for table_name in TABLE_MODEL_MAP:
        df = load_dataframe(table_name)
        if df is not None:
            datasets[table_name] = df
    return datasets


def update_siniestros_scores(df_scored: pd.DataFrame) -> int:
    engine = get_engine()

    score_cols = [
        "id_siniestro", "score_reglas", "score_hibrido",
        "ml_fraud_probability", "anomaly_score",
        "semaforo_final", "num_alertas", "alertas_reglas",
    ]
    available = [c for c in score_cols if str(c) in [str(x) for x in df_scored.columns]]
    if "id_siniestro" not in available:
        return 0

    df_update = df_scored[[c for c in df_scored.columns if str(c) in available]].copy()
    df_update.columns = [str(c) for c in df_update.columns]
    df_update = df_update.where(pd.notnull(df_update), None)

    update_cols = [c for c in available if c != "id_siniestro"]
    set_clause = ", ".join(f"{c} = :{c}" for c in update_cols)
    sql = text(f"UPDATE siniestros SET {set_clause} WHERE id_siniestro = :id_siniestro")

    def _to_native(val):
        if val is None:
            return None
        if isinstance(val, (np.floating, float)) and val != val:
            return None
        if isinstance(val, np.floating):
            return float(val)
        if isinstance(val, np.integer):
            return int(val)
        return val

    batch_size = 50
    rows = []
    for _, row in df_update.iterrows():
        rows.append({col: _to_native(row[col]) for col in available})

    count = 0
    with engine.begin() as conn:
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            for params in batch:
                try:
                    conn.execute(sql, params)
                    count += 1
                except Exception:
                    pass

    return count


def save_analysis_run(
    total: int, rojos: int, amarillos: int, verdes: int,
    score_prom: float, auc: float = None,
    anomalias: int = None, duracion: float = None,
) -> int:
    session = get_session()
    try:
        run = AnalisisRun(
            total_siniestros=total,
            rojos=rojos,
            amarillos=amarillos,
            verdes=verdes,
            score_promedio=round(score_prom, 2),
            auc_roc=round(auc, 4) if auc else None,
            anomalias_detectadas=anomalias,
            duracion_segundos=round(duracion, 2) if duracion else None,
        )
        session.add(run)
        session.commit()
        return run.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_analysis_history() -> List[Dict]:
    session = get_session()
    try:
        runs = session.query(AnalisisRun).order_by(AnalisisRun.fecha_ejecucion.desc()).limit(20).all()
        return [
            {
                "id": r.id,
                "fecha": r.fecha_ejecucion.isoformat() if r.fecha_ejecucion else None,
                "total": r.total_siniestros,
                "rojos": r.rojos,
                "amarillos": r.amarillos,
                "verdes": r.verdes,
                "score_promedio": r.score_promedio,
                "auc_roc": r.auc_roc,
                "anomalias": r.anomalias_detectadas,
                "duracion": r.duracion_segundos,
            }
            for r in runs
        ]
    finally:
        session.close()


def get_db_stats() -> Dict:
    engine = get_engine()
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    stats = {"tables": {}}
    for t in tables:
        df = pd.read_sql(text(f"SELECT COUNT(*) as n FROM {t}"), engine)
        stats["tables"][t] = int(df["n"].iloc[0])
    stats["total_tables"] = len(tables)
    return stats


def _prepare_for_db(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c) for c in df.columns]

    if table_name in TABLE_MODEL_MAP:
        model = TABLE_MODEL_MAP[table_name]
        model_cols = set(c.name for c in model.__table__.columns)
        df = df[[c for c in df.columns if c in model_cols]]

    for col in df.select_dtypes(include=["datetime64"]).columns:
        df[col] = df[col].dt.date

    date_cols = [c for c in df.columns if "fecha" in str(c).lower()]
    for col in date_cols:
        if df[col].dtype == "object":
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    df = df.replace({np.nan: None, np.inf: None, -np.inf: None})

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].apply(lambda x: str(x)[:500] if isinstance(x, str) else x)

    return df
