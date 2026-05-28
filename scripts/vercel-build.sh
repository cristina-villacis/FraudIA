#!/usr/bin/env bash
# Build en Vercel: usa bundle ya en Git o regenera desde data/synthetic
set -euo pipefail
echo "=== FraudIA Vercel build ==="
if [ -f "data/processed/siniestros_scored.csv" ] && [ -d "data/processed/vercel_bundle" ]; then
  echo "Bundle de analisis encontrado en el repo."
  ls -la data/processed/vercel_bundle/ | head -20
  exit 0
fi
echo "Regenerando bundle (datos sinteticos + pipeline)..."
python scripts/prepare_vercel_bundle.py --from-dir data/synthetic
echo "=== Build OK ==="
