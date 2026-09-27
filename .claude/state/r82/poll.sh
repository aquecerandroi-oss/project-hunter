#!/usr/bin/env bash
# R82 — regra de parada congelada antes de qualquer desfecho: a 1.ª extração com >= 150 pares resolvidos
# (t0 <= extração - 15 min) é a população do veredito. Reextrai a cada 5 min (só SELECT), sem imprimir PnL.
set -uo pipefail
cd "$(dirname "$0")"
for i in $(seq 1 36); do
  bash q.sh q_h017.sql > cache/h017_poll.csv 2>poll.err || { echo "falha na extração $i"; sleep 300; continue; }
  n=$(uv run --project C:/dev/project-hunter python -c "
import h017
rows = h017.load('cache/h017_poll.csv'); pop, _ = h017.population(rows); pairs, _ = h017.pair_rows(pop); print(len(pairs))")
  echo "$(date -u +%FT%TZ) tentativa $i: pares resolvidos $n"
  if [ "$n" -ge 150 ]; then mv cache/h017_poll.csv cache/h017.csv; echo "PRONTO: $n pares"; exit 0; fi
  sleep 300
done
echo "desisti depois de 36 tentativas"; exit 1
