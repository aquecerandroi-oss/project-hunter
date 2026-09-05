#!/usr/bin/env bash
# T1.6b proof sampler: docker stats every 30s, service probe every 5 min.
export PATH="/c/Users/evert/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"
label="$1"; minutes="$2"
out=".claude/state/tmp/samples-${label}.txt"
: > "$out"
end=$(( $(date +%s) + minutes*60 ))
i=0
while [ "$(date +%s)" -lt "$end" ]; do
  ts=$(date -u +%H:%M:%S)
  stats=$(docker stats --no-stream --format "{{.Name}} {{.CPUPerc}} {{.MemUsage}}" $(docker ps --filter "name=market-worker" --format "{{.Names}}" | tr '\n' ' '))
  echo "[$ts] $stats" >> "$out"
  i=$((i+1))
  if [ $((i % 10)) -eq 1 ]; then
    echo "[$ts] PROBE $(MSYS_NO_PATHCONV=1 docker exec docker-api-1 python //tmp/measure_t16b.py 2>&1 | tail -1)" >> "$out"
    echo "[$ts] CANDLES $(docker exec docker-postgres-1 psql -U hunter -d hunter -Atc "select count(*) from candles;") GAPS_OPEN $(docker exec docker-postgres-1 psql -U hunter -d hunter -Atc "select count(*) from ingestion_gaps where status='open';")" >> "$out"
  fi
  docker exec docker-api-1 sh -lc 'sleep 28' >/dev/null 2>&1
done
echo "DONE $(date -u +%H:%M:%S)" >> "$out"
