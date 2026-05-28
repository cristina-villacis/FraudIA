#!/usr/bin/env python3
"""
Build Vercel: genera o carga datos → pipeline completo → empaqueta para API/chatbot.

Flujo:
  1. Datos sintéticos (--synthetic) o carpeta existente (--from-dir)
  2. Feature engineering + reglas + ML + score híbrido
  3. Exporta CSV + JSON de contexto (dashboard, modelo, NLP)
  4. En runtime Vercel solo se sirve ese bundle + OpenAI explica/responde

Uso local (antes de git push):
  python scripts/prepare_vercel_bundle.py --synthetic
  python scripts/prepare_vercel_bundle.py --from-dir data/synthetic
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.ingestion.generate_synthetic import main as generate_synthetic  # noqa: E402
from src.ingestion.load_data import load_all_from_directory  # noqa: E402
from src.pipeline.run_full_analysis import execute_full_pipeline, save_vercel_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Preparar bundle de análisis para Vercel")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Generar datos sintéticos antes del análisis (recomendado en build Vercel)",
    )
    parser.add_argument(
        "--from-dir",
        default="data/synthetic",
        help="Carpeta con CSV/Excel de tablas (default: data/synthetic)",
    )
    parser.add_argument("--seed", type=int, default=None, help="Semilla para datos sintéticos")
    args = parser.parse_args()

    data_dir = os.path.join(ROOT, args.from_dir)
    seed = None

    if args.synthetic:
        print("[1/4] Generando datos sintéticos...")
        seed = generate_synthetic(seed=args.seed)
        data_dir = os.path.join(ROOT, "data", "synthetic")
        print(f"      Semilla: {seed}")
    else:
        print(f"[1/4] Cargando datos desde {data_dir}...")

    if not os.path.isdir(data_dir):
        print(f"ERROR: no existe {data_dir}. Use --synthetic o cargue archivos.")
        return 1

    print("[2/4] Leyendo tablas...")
    datasets = load_all_from_directory(data_dir)
    if "siniestros" not in datasets:
        print("ERROR: falta tabla siniestros.")
        return 1

    print(f"      Tablas: {', '.join(datasets.keys())} ({len(datasets['siniestros'])} siniestros)")

    print("[3/4] Ejecutando pipeline (features, reglas, ML, score híbrido)...")
    result = execute_full_pipeline(datasets, persist_csv=True)
    result["data_source"] = "synthetic" if args.synthetic else args.from_dir
    result["seed"] = seed

    print("[4/4] Guardando bundle para Vercel...")
    bundle_path = save_vercel_bundle(result, root=ROOT)
    print(f"      CSV: data/processed/siniestros_scored.csv")
    print(f"      Bundle: {bundle_path}")
    print(f"      Registros: {result['total_records']} | AUC: {result.get('auc_roc')} | "
          f"{result['duration_seconds']}s")
    print("Listo. Despliegue en Vercel usará este análisis para dashboard y chatbot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
