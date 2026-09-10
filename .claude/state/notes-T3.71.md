# T3.71 — restore rehearsal real + remedição §8 (2026-09-10)

Todos os comandos abaixo foram rodados em foreground via `ssh hunter-vps`
(exceto o `pg_restore`, lançado com `nohup ... &` dentro da sessão SSH, único
caso permitido, e sondado depois em chamadas curtas separadas). Nenhum
comando tocou o banco `hunter`, nenhum container foi parado, nenhum `git
pull` foi rodado. HEAD na VPS confirmado antes de começar: `572d3b6`.

## 0. Sanidade

```
$ ssh hunter-vps "echo OK && date -u && cd /opt/project-hunter && git rev-parse HEAD"
OK
Thu Sep 10 03:31:44 UTC 2026
572d3b610b3213a9f017299c4abdb53a73d37cba

$ ssh hunter-vps "docker ps --format '{{.Names}}' | grep -i postgres"
hunter-postgres-1
```

## 1. Estado do disco e dumps antes

```
$ ssh hunter-vps "ls -la /opt/backups/ | tail -20 && df -h / && cat /etc/cron.d/hunter-backup"
-rw------- 1 hunter hunter   26822350 Sep  6 15:55 hunter-20260906T135550Z.dump
-rw------- 1 hunter hunter  103837429 Sep  7 03:17 hunter-20260907T011701Z.dump
-rw------- 1 hunter hunter  405273906 Sep  8 03:18 hunter-20260908T011701Z.dump
-rw------- 1 hunter hunter  659133892 Sep  9 03:19 hunter-20260909T011701Z.dump
-rw------- 1 hunter hunter 1092793610 Sep 10 03:20 hunter-20260910T011701Z.dump
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1       348G  222G  126G  64% /
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
17 3 * * * hunter bash /opt/project-hunter/infra/vps/backup_postgres.sh >> /opt/backups/backup.log 2>&1
```

Sem `HUNTER_BACKUP_RETENTION_DAYS` no cron → default do script = 7 dias.
`infra/vps/backup_postgres.sh` linha 80: `find "$BACKUP_DIR" -maxdepth 1 -type f
-name 'hunter-*.dump' -mtime "+$RETENTION_DAYS" -print -delete` — **sim, poda**.

## 2. Rehearsal de restore (banco descartável)

```
$ ssh hunter-vps "date -u && docker exec hunter-postgres-1 createdb -U hunter hunter_restore_check && echo CREATED_OK"
Thu Sep 10 03:38:57 UTC 2026
CREATED_OK

$ ssh hunter-vps "date -u && time docker cp /opt/backups/hunter-20260910T011701Z.dump hunter-postgres-1:/tmp/restore_check.dump && docker exec hunter-postgres-1 ls -la /tmp/restore_check.dump"
Thu Sep 10 03:39:08 UTC 2026
real 0m4.118s
-rw------- 1 1001 1001 1092793610 Sep 10 01:20 /tmp/restore_check.dump

$ ssh hunter-vps "date -u && nohup docker exec hunter-postgres-1 pg_restore -U hunter -d hunter_restore_check --no-owner --no-privileges -j 2 -v /tmp/restore_check.dump > /tmp/restore_check.log 2>&1 & echo LAUNCHED_PID=\$!; disown; sleep 1; ps aux | grep pg_restore | grep -v grep"
Thu Sep 10 03:39:21 UTC 2026
LAUNCHED_PID=3224307
hunter   3224310  docker exec hunter-postgres-1 pg_restore ...
root     3224334  pg_restore -U hunter -d hunter_restore_check --no-owner --no-privileges -j 2 -v /tmp/restore_check.dump
(sessão SSH fechou sozinha aos 60s pelo wrapper "timeout 60" local; processo
remoto sobreviveu graças a nohup+disown — confirmado na sondagem seguinte)
```

Sondagens (cada uma uma chamada SSH curta e independente, nunca um sleep
longo local):

```
03:40:30Z — 4 processos pg_restore vivos; docker exec hunter-postgres-1 ps aux
            mostra 2x "postgres: hunter hunter_restore_check [local] COPY"
03:40:38Z — log: TABLE DATA opportunity_history_2026_09
03:42:25Z (após sleep 90 dentro da própria sessão) — log: TABLE DATA candles_1m_2026_09
03:44:48Z — log: TABLE DATA candles_1m_2026_08
03:44:57Z — log: TABLE DATA portfolio_currency_anchor
03:45:05Z — log: SEQUENCE SET outbox_events_id_seq / shadow_outbox_id_seq
03:45:22Z — log: SEQUENCE SET shadow_outbox_id_seq (última linha)
03:45:32Z — ps aux | grep pg_restore -> vazio; wc -l /tmp/restore_check.log -> 4990
```

**Resultado: pg_restore terminou às ~03:45:25Z, lançado 03:39:21Z → ~6 min,
0 processos remanescentes, log fechado em 4990 linhas.**

```
$ ssh hunter-vps "grep -iE 'error|WARNING' /tmp/restore_check.log | grep -v ... ; grep -ci error /tmp/restore_check.log"
0
```
Nenhum erro real (o único "match" de WARNING era o nome do tipo
`backtest_warning_code`, coincidência léxica, não um aviso).

## 3. Comparação de contagens (restaurado vs vivo)

Restaurado (`hunter_restore_check`):
```
agents 0 | candles_1m 5248305 | fills 0 | kill_switch_transitions 0 |
market_betas 9200 | orders 0 | portfolios 1 | positions 0 | risk_profiles 4 |
strategy_versions 40 | trades 0
```

Vivo (`hunter`, `begin transaction isolation level repeatable read read only`):
```
agents 0 | candles_1m 5384882 | fills 0 | kill_switch_transitions 0 |
market_betas 9600 | orders 0 | portfolios 1 | positions 0 | risk_profiles 4 |
strategy_versions 40 | trades 0
```

Iguais em 9 de 11 tabelas; `candles_1m` e `market_betas` diferem exatamente
pelo intervalo entre o dump (01:20Z) e a leitura do vivo (03:46Z, ~2h26):
β roda de hora em hora (9600-9200=400 ≈ 2 execuções × ~200 mercados) e
candles a cada minuto por mercado (5384882-5248305=136577).

## 4. RLS e role

```
$ docker exec hunter-postgres-1 psql -U hunter -d hunter_restore_check -c '\dp orders' -c '\dp positions' ...
orders    | tenant_isolation | (u): organization_id = current_setting('app.current_org') | (c): idem
positions | tenant_isolation | idem
SELECT rolname FROM pg_roles WHERE rolname='hunter_runtime'; -> hunter_runtime (existe, é global ao cluster)
```
Nota: `--no-privileges` não recria os `GRANT` de `hunter_runtime` nas tabelas
do banco descartável — esperado; não é um restore de produção.

## 5. Limpeza

```
$ docker exec hunter-postgres-1 psql -U hunter -d hunter_restore_check -c "SELECT pg_size_pretty(pg_database_size('hunter_restore_check'));"
6400 MB
$ docker exec hunter-postgres-1 dropdb -U hunter hunter_restore_check  -> DROPPED_OK
$ docker exec hunter-postgres-1 rm -f /tmp/restore_check.dump          -> TMP_CLEANED
$ docker exec hunter-postgres-1 psql -U hunter -d hunter -tAc "SELECT datname FROM pg_database WHERE datname='hunter_restore_check';" | wc -l
0
$ df -h /   -> 348G, 224G usado, 124G livre, 65%
```
Wall-clock total do rehearsal (createdb → dropdb): ~03:38:57Z → ~03:47:00Z ≈ **8 min**.

## 6. Remedição §8 (linhas 1–8, verbatim das consultas do doc)

```sql
begin transaction isolation level repeatable read read only;
SELECT count(*) FROM agents;                                    -- 0
SELECT count(*) FROM risk_profiles WHERE preset='paper_v1';      -- 0
SELECT risk_profile_id FROM portfolios;                          -- NULL
commit;
```

```sql
-- linha 2 (mercados executáveis)
SELECT symbol, apply_min_to_market, avg_price_mins FROM markets WHERE ...;
-- 18 linhas (era 15), todas min_mkt=t avg_mins=5

-- linhas 2+3 (funil momentum v3 / 24h)
-- sinais=366, d1_ok=51, d1_e_beta_ok=23  (era 171/22/0)

-- β válidos totais
SELECT count(*) FILTER (WHERE valid), count(*) FROM market_betas WHERE valid_until>now();
-- 16 válidos de 200

-- quais dos 18 monitorados SPOT têm β válido (join correto via perpétuo referenciado por agent_signals)
-- 12/18: ARB,BNB,BTC,DOGE,ETH,NEAR,PROM,SOL,SUI,UNI,XRP,ZEC
-- 6/18 sem: HOLO,IOST,MARSCOIN,PUMP,USD1,USDC
```

```
$ ssh hunter-vps "... redis-cli --no-raw HGETALL hb:execution:paper"
ts=2026-09-10T03:32:45.79Z  equity=19333.0111164813  kill_switch=ACTIVE
paper_autonomy=false  mark_quality=1  last_mtm=2026-09-10 03:32:00.014463+00 (~46s antes)
```

```
$ ssh hunter-vps "docker exec hunter-execution-worker-1 (via compose) python -c 'import hunter_execution_worker.avg_price as m; print(m.__file__)'"
/app/services/execution-worker/hunter_execution_worker/avg_price.py
$ docker inspect hunter-execution-worker-1 --format '{{.State.StartedAt}}'  -> 2026-09-09T15:20:52Z
$ docker logs --tail=500 hunter-execution-worker-1 | grep -iE 'avg_price_not_collected|...|entry_deferred|bridge_candidate_deferred'  -> vazio (0 ocorrências)
```

## 7. Retenção de backup — projeção

Tamanhos: 06/09 25,6 MiB · 07/09 99 MiB · 08/09 386 MiB · 09/09 628 MiB ·
10/09 1042 MiB (~1,02 GiB). Crescimento diário absoluto: +73M, +302M, +254M,
+434M (o último salto inclui o backfill de 90 dias da T3.62, evento único).

Retenção atual: 7 dias, cron sem override, script poda de fato
(`find -mtime +7 -delete`, confirmado na leitura do script). Com 7 dumps no
tamanho de hoje (~1G/dia, pior caso linear), o footprint da janela de 7 dias
fica em torno de 7-16 G — folga enorme contra os 124 G livres hoje (>100 dias
de teto antes de qualquer alerta, no ritmo atual).

Risco real não é o dia-a-dia, é um backfill futuro dos outros 184 mercados
(hoje só 16/200 têm β válido, via os 90 dias de histórico). Se esse backfill
for replicado para os 200, o tamanho do dump pode escalar ~12x (200/16),
chegando perto de 13 G/dump; com retenção de 7 dias isso significaria ~90 G
só de backups, contra 124 G livres agora (e menos no futuro, com o disco
crescendo por outras razões). Proposta (não aplicada): antes de rodar esse
backfill maior, revisar `RETENTION_DAYS` para algo como 4-5 dias via
`HUNTER_BACKUP_RETENTION_DAYS=4` no `/etc/cron.d/hunter-backup`, ou mover o
`/opt/backups` para storage fora do host (limitação já registrada em
`docs/DEPLOYMENT.md` §9.6).

## 8. Nota — edição concorrente

Durante a edição de `docs/ACTIVATION.md`, outro agente (T3.69, seção nova
"8b. Perfil de risco persistido") atualizou a célula "Verde?" da linha 8 da
tabela §8 entre minha leitura e minha escrita. O conteúdo é compatível com a
minha medição (mesma linha, mesmo fato: `risk_profile_id` NULL) — mantive a
edição deles e não revertida nada, só a minha coluna "Medido em 2026-09-10"
foi escrita por mim.
