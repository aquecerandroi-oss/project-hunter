#!/bin/bash
# usage: q.sh file.sql  -> runs read-only on VPS
cat "$1" | timeout 600 ssh hunter-vps 'docker exec -i -e PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=500000" $(docker ps -qf name=postgres | head -1) psql -U hunter -d hunter -X -v ON_ERROR_STOP=1 -P pager=off'
