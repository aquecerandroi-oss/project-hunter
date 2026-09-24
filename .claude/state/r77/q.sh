#!/usr/bin/env bash
# R76 — roda um .sql só-leitura na VPS (transação READ ONLY forçada) e escreve o CSV no stdout.
# uso: bash q.sh arquivo.sql > saida.csv
set -euo pipefail
ssh hunter-vps "docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 -q" < "$1"
