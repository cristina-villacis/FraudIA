#!/usr/bin/env python3
"""Build step for Vercel (sin bash). Verifica o genera el bundle de analisis."""
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(ROOT)

csv_path = os.path.join(ROOT, "data", "processed", "siniestros_scored.csv")
bundle_dir = os.path.join(ROOT, "data", "processed", "vercel_bundle")

if os.path.isfile(csv_path) and os.path.isdir(bundle_dir):
    print("Bundle OK:", csv_path)
    sys.exit(0)

print("Generando bundle desde data/synthetic...")
rc = subprocess.call(
    [sys.executable, "scripts/prepare_vercel_bundle.py", "--from-dir", "data/synthetic"],
)
sys.exit(rc)
