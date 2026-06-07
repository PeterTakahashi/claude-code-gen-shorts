#!/usr/bin/env bash
# Build English versions of every short across all biography projects.
# Output: projects/<proj>/output/shorts/<sid>/en/short.mp4
set -u
cd "$(dirname "$0")/.."

PROJECTS=(
  stevejobs elonmusk
  samaltman darioamodei jensenhuang masayoshison tadashiyanai
  markzuckerberg takafumihorie billgates jeffbezos larrypage
  paulgraham vitalikbuterin sambankmanfried marcandreessen
  georgehotz tomokonamba susumufujita keishikameyama
)

for proj in "${PROJECTS[@]}"; do
  echo "=== EN BUILD $proj ==="
  uv run python -m src.short_gen "$proj" --all --language en || true
done
echo "=== done ==="
