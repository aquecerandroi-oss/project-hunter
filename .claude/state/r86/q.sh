#!/usr/bin/env bash
# R86 — roda um .sql só-leitura na VPS (BEGIN READ ONLY + default_transaction_read_only) e escreve no stdout.
# uso: bash q.sh arquivo.sql > saida.csv
set -euo pipefail
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh exec -T -e PGOPTIONS='-c default_transaction_read_only=on' postgres psql -U hunter -d hunter -v ON_ERROR_STOP=1 -q" < "$1"
