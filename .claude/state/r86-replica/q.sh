#!/usr/bin/env bash
# r86-replica — roda um .sql na VPS dentro de BEGIN READ ONLY ... COMMIT (stdin) e escreve no stdout.
set -euo pipefail
{ echo "BEGIN READ ONLY;"; cat "$1"; echo "COMMIT;"; } | ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh exec -T -e PGOPTIONS='-c default_transaction_read_only=on' postgres psql -U hunter -d hunter -v ON_ERROR_STOP=1 -q -X"
