"""
Repositorio de datos - CRUD entre DataFrames de pandas y la base de datos.
Maneja la persistencia bidireccional: DataFrame <-> MySQL/SQLite.
"""
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sqlalchemy import text, inspect

from src.db.config import get_engine, get_session
from src.db.models import (
    Base, Asegurado, Vehiculo, Poliza, Proveedor,
    Siniestro, Documento, DocumentoSubido, AnalisisRun,
)

TABLE_MODEL_MAP = {
    "asegurados": Asegurado,
    "vehiculos": Vehiculo,
    "polizas": Poliza,
    "proveedores": Proveedor,
    "siniestros": Siniestro,
    "documentos": Documento,
}


_SCHEMA_ALTER_COLUMNS = {
    "asegurados": [
        ("nombres_asegurado", "VARCHAR(200) NULL"),
    ],
    "siniestros": [
        ("placa_vehiculo", "VARCHAR(20) NULL"),
        ("similitud_narrativa_max", "DOUBLE DEFAULT 0"),
        ("numero_parte_policial", "VARCHAR(50) NULL"),
        ("prov_en_lista_restrictiva", "INT DEFAULT 0"),
        ("suma_asegurada", "DOUBLE NULL"),
    ],
    "documentos": [
        ("nombre_archivo_pdf", "VARCHAR(255) NULL"),
    ],
}


def _ensure_schema_columns():
    """Añade columnas nuevas en BD existente (TiDB/MySQL) sin borrar datos."""
    engine = get_engine()
    if "mysql" not in str(engine.url):
        return
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _SCHEMA_ALTER_COLUMNS.items():
            if table not in existing_tables:
                continue
            have = {c["name"] for c in inspector.get_columns(table)}
            for col_name, ddl in columns:
                if col_name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {ddl}"))


def init_database():
    from src.db.config import ensure_tidb_database

    ensure_tidb_database()
    engine = get_engine()
    Base.metadata.create_all(engine)
    _ensure_schema_columns()
    return True


def drop_all_data():
    """Vacía tablas; cada una en su propia transacción (TiDB tolera TRUNCATE fallido sin romper el pool)."""
    engine = get_engine()
    is_mysql = "mysql" in str(engine.url)
    tables_order = [
        "documentos_subidos", "documentos", "siniestros", "polizas",
        "vehiculos", "proveedores", "asegurados", "analisis_runs",
    ]

    for t in tables_order:
        _truncate_table(engine, t, is_mysql)


def _truncate_table(engine, table_name: str, is_mysql: Optional[bool] = None) -> None:
    if is_mysql is None:
        is_mysql = "mysql" in str(engine.url)
    safe = table_name.replace("`", "")
    try:
        with engine.begin() as conn:
            if is_mysql:
                conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            try:
                if is_mysql:
                    conn.execute(text(f"TRUNCATE TABLE `{safe}`"))
                else:
                    conn.execute(text(f"DELETE FROM {safe}"))
            except Exception:
                conn.execute(text(f"DELETE FROM {safe}"))
            if is_mysql:
                conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    except Exception:
        pass


def _sanitize_datasets_for_db(datasets: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    Alinea claves foráneas con las tablas del mismo Excel antes de insertar en TiDB.
    Evita IntegrityError 1452 por id_poliza / id_asegurado huérfanos.
    """
    out = {name: df.copy() for name, df in datasets.items()}

    def _id_set(table: str, col: str) -> set:
        if table not in out or col not in out[table].columns:
            return set()
        return set(out[table][col].dropna().astype(str).str.strip())

    aseg_ids = _id_set("asegurados", "id_asegurado")
    pol_ids = _id_set("polizas", "id_poliza")
    veh_ids = _id_set("vehiculos", "id_vehiculo")
    prv_ids = _id_set("proveedores", "id_proveedor")

    if "vehiculos" in out and aseg_ids and "id_asegurado" in out["vehiculos"].columns:
        v = out["vehiculos"]
        out["vehiculos"] = v[v["id_asegurado"].astype(str).str.strip().isin(aseg_ids)].copy()

    if "polizas" in out and aseg_ids and "id_asegurado" in out["polizas"].columns:
        p = out["polizas"]
        out["polizas"] = p[p["id_asegurado"].astype(str).str.strip().isin(aseg_ids)].copy()
        pol_ids = _id_set("polizas", "id_poliza")

    if "siniestros" in out:
        s = out["siniestros"]
        mask = pd.Series(True, index=s.index)
        if pol_ids and "id_poliza" in s.columns:
            mask &= s["id_poliza"].astype(str).str.strip().isin(pol_ids)
        if aseg_ids and "id_asegurado" in s.columns:
            mask &= s["id_asegurado"].astype(str).str.strip().isin(aseg_ids)
        s = s.loc[mask].copy()
        if "id_vehiculo" in s.columns:
            if veh_ids:
                s["id_vehiculo"] = s["id_vehiculo"].apply(
                    lambda x: str(x).strip()
                    if pd.notna(x) and str(x).strip() in veh_ids
                    else None
                )
            else:
                s["id_vehiculo"] = None
        if prv_ids and "id_proveedor" in s.columns:
            s["id_proveedor"] = s["id_proveedor"].apply(
                lambda x: str(x).strip()
                if pd.notna(x) and str(x).strip() in prv_ids
                else None
            )
        elif "id_proveedor" in s.columns:
            s["id_proveedor"] = None
        out["siniestros"] = s
        sin_ids = _id_set("siniestros", "id_siniestro")

        if "documentos" in out and sin_ids and "id_siniestro" in out["documentos"].columns:
            d = out["documentos"]
            out["documentos"] = d[
                d["id_siniestro"].astype(str).str.strip().isin(sin_ids)
            ].copy()

    return out


def _save_dataframe_on_connection(conn, df: pd.DataFrame, table_name: str) -> int:
    df_clean = _prepare_for_db(df, table_name)
    df_clean.to_sql(
        table_name,
        conn,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=500,
    )
    return len(df_clean)


def save_dataframe(df: pd.DataFrame, table_name: str) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        return _save_dataframe_on_connection(conn, df, table_name)


def save_all_datasets(
    datasets: Dict[str, pd.DataFrame],
    *,
    full_replace: bool = True,
) -> Dict[str, Any]:
    """
    Guarda datasets en orden FK (una transacción en MySQL/TiDB).
    full_replace=True: vacía todas las tablas antes (reemplazo total).
    full_replace=False: solo vacía las tablas que se van a escribir.
    """
    order = ["asegurados", "vehiculos", "polizas", "proveedores", "siniestros", "documentos"]
    results: Dict[str, Any] = {}
    engine = get_engine()
    is_mysql = "mysql" in str(engine.url)

    init_database()
    clean = _sanitize_datasets_for_db(datasets)
    dropped_sin = 0
    if "siniestros" in datasets and "siniestros" in clean:
        dropped_sin = len(datasets["siniestros"]) - len(clean["siniestros"])
    if dropped_sin > 0:
        results["_fk_rows_dropped"] = dropped_sin

    try:
        with engine.begin() as conn:
            if is_mysql:
                conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))

            if full_replace:
                for t in [
                    "documentos_subidos", "documentos", "siniestros", "polizas",
                    "vehiculos", "proveedores", "asegurados", "analisis_runs",
                ]:
                    _truncate_table_on_connection(conn, t, is_mysql)
            else:
                for table_name in order:
                    if table_name in clean:
                        _truncate_table_on_connection(conn, table_name, is_mysql)
                for name in clean:
                    if name not in order:
                        _truncate_table_on_connection(conn, name, is_mysql)

            for table_name in order:
                if table_name not in clean:
                    continue
                results[table_name] = _save_dataframe_on_connection(
                    conn, clean[table_name], table_name
                )

            for name, df in clean.items():
                if name in order:
                    continue
                results[name] = _save_dataframe_on_connection(conn, df, name)

            if is_mysql:
                conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    except Exception as e:
        err = str(e)[:200]
        for table_name in order:
            if table_name in clean and table_name not in results:
                results[table_name] = f"error: {err}"
        if not any(isinstance(v, str) and str(v).startswith("error") for v in results.values()):
            results["siniestros"] = f"error: {err}"

    return results


def _truncate_table_on_connection(conn, table_name: str, is_mysql: bool) -> None:
    safe = table_name.replace("`", "")
    try:
        if is_mysql:
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        try:
            if is_mysql:
                conn.execute(text(f"TRUNCATE TABLE `{safe}`"))
            else:
                conn.execute(text(f"DELETE FROM {safe}"))
        except Exception:
            conn.execute(text(f"DELETE FROM {safe}"))
    except Exception:
        pass


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
    failed = 0
    with engine.begin() as conn:
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            try:
                conn.execute(sql, batch)
                count += len(batch)
            except Exception:
                for params in batch:
                    try:
                        conn.execute(sql, params)
                        count += 1
                    except Exception:
                        failed += 1
    if failed:
        print(f"[DB] update_siniestros_scores: fallidas={failed}, exitosas={count}")

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
        elif pd.api.types.is_integer_dtype(df[col]):
            df[col] = df[col].apply(lambda x: int(x) if pd.notna(x) else None)
        elif pd.api.types.is_float_dtype(df[col]):
            df[col] = df[col].apply(lambda x: float(x) if pd.notna(x) else None)

    return df


def _doc_subido_to_dict(row: DocumentoSubido) -> Dict[str, Any]:
    alertas = []
    inconsistencias = []
    campos = {}
    try:
        if row.alertas:
            alertas = json.loads(row.alertas)
    except json.JSONDecodeError:
        pass
    try:
        if row.inconsistencias:
            inconsistencias = json.loads(row.inconsistencias)
    except json.JSONDecodeError:
        if row.inconsistencias:
            inconsistencias = [row.inconsistencias]
    try:
        if row.campos_extraidos:
            campos = json.loads(row.campos_extraidos)
    except json.JSONDecodeError:
        pass
    return {
        "id": row.id,
        "id_documento": row.id_documento,
        "id_siniestro": row.id_siniestro,
        "tipo_documento": row.tipo_documento,
        "nombre_archivo": row.nombre_archivo,
        "score_documento": row.score_documento,
        "semaforo": row.semaforo,
        "alertas": alertas,
        "inconsistencias": inconsistencias,
        "campos_extraidos": campos,
        "vinculado_dataset": bool(row.vinculado_dataset),
        "estado": row.estado,
        "fecha_carga": row.fecha_carga.isoformat() if row.fecha_carga else None,
        "fecha_analisis": row.fecha_analisis.isoformat() if row.fecha_analisis else None,
        "texto_preview": (row.texto_extraido or "")[:400],
    }


def save_documento_subido(record: Dict[str, Any]) -> int:
    init_database()
    session = get_session()
    try:
        row = DocumentoSubido(
            id_documento=record.get("id_documento"),
            id_siniestro=record.get("id_siniestro"),
            tipo_documento=record.get("tipo_documento"),
            nombre_archivo=record.get("nombre_archivo"),
            ruta_almacen=record.get("ruta_almacen"),
            texto_extraido=(record.get("texto_extraido") or "")[:50000],
            campos_extraidos=record.get("campos_extraidos"),
            score_documento=record.get("score_documento"),
            semaforo=record.get("semaforo"),
            alertas=record.get("alertas"),
            inconsistencias=record.get("inconsistencias"),
            vinculado_dataset=1 if record.get("vinculado_dataset") else 0,
            estado=record.get("estado", "analizado"),
            fecha_analisis=record.get("fecha_analisis") or datetime.utcnow(),
        )
        session.add(row)
        session.commit()
        return row.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_documento_subido(doc_id: int, updates: Dict[str, Any]) -> bool:
    session = get_session()
    try:
        row = session.query(DocumentoSubido).filter(DocumentoSubido.id == doc_id).first()
        if not row:
            return False
        for key, val in updates.items():
            if hasattr(row, key):
                setattr(row, key, val)
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_documentos_subidos(limit: int = 100) -> List[Dict[str, Any]]:
    init_database()
    session = get_session()
    try:
        rows = (
            session.query(DocumentoSubido)
            .order_by(DocumentoSubido.fecha_carga.desc())
            .limit(limit)
            .all()
        )
        return [_doc_subido_to_dict(r) for r in rows]
    finally:
        session.close()


def get_documento_subido(doc_id: int) -> Optional[Dict[str, Any]]:
    session = get_session()
    try:
        row = session.query(DocumentoSubido).filter(DocumentoSubido.id == doc_id).first()
        if not row:
            return None
        d = _doc_subido_to_dict(row)
        d["texto_extraido"] = row.texto_extraido
        return d
    finally:
        session.close()
