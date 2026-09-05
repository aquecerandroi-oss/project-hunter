#!/usr/bin/env bash
# T1.6b — coleta da prova de capacidade. NÃO é código de produção: fica em .claude/state.
#
#   bash .claude/state/profile/proof.sh <label> <duracao_s> [container ...]
#
# Coleta, para cada container informado (default: docker-market-worker-1):
#   - docker stats (CPU/mem) no início, no meio e no fim
#   - perfil py-spy de 90 s
#   - heartbeat hb:market:binance e hb:market:binance:* do Redis
#   - /api/v1/system/market-status (markets_ok, markets_degraded, ...)
# Saída: .claude/state/profile/proof-<label>.txt
set -u
export PATH="/c/Program Files/nodejs:/c/Users/evert/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"
cd /c/dev/project-hunter || exit 1

LABEL="${1:?label}"; DURATION="${2:-600}"; shift 2 || true
CONTAINERS=("$@"); [ ${#CONTAINERS[@]} -eq 0 ] && CONTAINERS=(docker-market-worker-1)
OUT=".claude/state/profile/proof-${LABEL}.txt"
DC="docker compose -f infra/docker/docker-compose.yml"

say() { echo "$@" | tee -a "$OUT"; }
run() { say ""; say "\$ $*"; { "$@" 2>&1; } | tee -a "$OUT"; }

: > "$OUT"
say "# T1.6b prova — ${LABEL} — início $(date -u +%FT%TZ) — duração ${DURATION}s"
say "# containers: ${CONTAINERS[*]}"

run docker stats --no-stream "${CONTAINERS[@]}"
say ""; say "--- heartbeat no início ---"
$DC exec -T redis redis-cli --scan --pattern 'hb:market:*' 2>&1 | tee -a "$OUT" | while read -r k; do
  [ -n "$k" ] && { echo "\$ HGETALL $k" >> "$OUT"; $DC exec -T redis redis-cli hgetall "$k" >> "$OUT" 2>&1; }
done

sleep "$((DURATION / 2))"
say ""; say "--- meio da corrida $(date -u +%FT%TZ) ---"
run docker stats --no-stream "${CONTAINERS[@]}"

for c in "${CONTAINERS[@]}"; do
  say ""; say "--- py-spy 90 s em ${c} ---"
  MSYS_NO_PATHCONV=1 docker run --rm --pid="container:${c}" --cap-add SYS_PTRACE --cap-add SYS_ADMIN \
    -v "C:/dev/project-hunter/.claude/state/profile:/out" python:3.12-slim \
    sh -c "pip install --quiet py-spy 2>/dev/null; py-spy record --pid 1 --duration 90 --rate 120 --format raw --output /out/raw-${LABEL}-${c}.txt" 2>&1 | tail -2 | tee -a "$OUT"
  uv run --no-project python .claude/state/profile/buckets.py ".claude/state/profile/raw-${LABEL}-${c}.txt" 2>&1 | tee -a "$OUT"
done

sleep "$((DURATION / 2))"
say ""; say "--- fim da corrida $(date -u +%FT%TZ) ---"
run docker stats --no-stream "${CONTAINERS[@]}"

say ""; say "--- heartbeat no fim ---"
$DC exec -T redis redis-cli --scan --pattern 'hb:market:*' 2>&1 | tee -a "$OUT" | while read -r k; do
  [ -n "$k" ] && { echo "\$ HGETALL $k" >> "$OUT"; $DC exec -T redis redis-cli hgetall "$k" >> "$OUT" 2>&1; }
done

say ""; say "--- contagem de chaves quentes (ticker/book/candles) ---"
for pat in 'mkt:*:ticker:*' 'mkt:*:book:*' 'mkt:*:candles:1m:*'; do
  n=$($DC exec -T redis redis-cli --scan --pattern "$pat" 2>/dev/null | wc -l)
  say "$pat -> $n chaves"
done

say ""; say "--- market_persist_lag / erros no log ---"
for c in "${CONTAINERS[@]}"; do
  say "[$c]"
  docker logs --since "${DURATION}s" "$c" 2>&1 | grep -c "market_persist" | tee -a "$OUT"
  docker logs --since "${DURATION}s" "$c" 2>&1 | grep -iE '"level": ?"(error|critical)"' | tail -10 | tee -a "$OUT"
done

say ""; say "# fim $(date -u +%FT%TZ)"
echo "PROOF_DONE -> $OUT"
