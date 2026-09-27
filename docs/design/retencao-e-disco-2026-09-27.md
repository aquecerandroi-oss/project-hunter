---
status: proposta (nada executado)
autor: database-architect
data: 2026-09-27
decide: Everton (todo passo que apaga dado ou reduz o que o backup protege)
---

# Retenção e disco da VPS — proposta de 27/09/2026

Tudo aqui foi medido na VPS entre 03:10Z e 04:30Z de 27/09/2026, só com `SELECT`, `COPY … TO STDOUT` de
amostra (`TABLESAMPLE`), `df`, `ls`, `docker system df` e `printenv` de valores não secretos. **Nada foi
apagado, nenhum DDL, nenhum `VACUUM`.** Tamanhos em GiB (o "G" do `df` e do `pg_size_pretty`).

Antecedentes no Obsidian: `obsidian/07-BUGS/Open Bugs.md`, entrada "Disco da VPS em 88 % — o banco cresce
~6 GB/dia e ninguém poda a outbox (plantão 18/09)" — lá já estavam a outbox sem poda (17 G), a
`opportunity_history_2026_09` (25 G, +4,2 G/dia) e o cron `hunter-partitions` ausente. O
`obsidian/09-OPERATIONS/Diario/2026-09-26.md` **não menciona o disco** (o dia foi a parada da mesa real
no escopo do teste pequeno); o incidente de 27/09 ainda não está registrado no Obsidian.

## 0. O estado agora

| Medida | 18/09 (Open Bugs) | 27/09 03:12Z |
|---|---|---|
| `df -h /` | 306 G de 348 G (88 %) | **221 G usados, 127 G livres (64 %)** — alguém removeu 5 dos 8 dumps depois da falha da noite; o brief falava em 86 % |
| Banco (`pg_database_size`) | 58 G | **129 G** (volume `hunter_hunter_pg` 141,4 GB = 131,7 G, com WAL de 721 M) |
| `/opt/backups` | 41 G | **63,4 G** em 3 dumps (24/09 18,3 G · 25/09 21,8 G · 26/09 23,4 G) |
| Dump da noite | 10,6 G, 32 min | 26/09: 23,4 G em **81 min**; 27/09: **falhou** (`write /dev/stdout: no space left on device`, 01:31Z) |
| Docker | imagens 178 G, cache 37 G | imagens 6,3 GB (3,8 recuperáveis), build cache 11,6 GB (10,2 recuperáveis) |

**O banco cresce ~8 G/dia** (58 → 129 G em 8,2 dias = 8,6 G/dia; média dos últimos 7 dias pelas tabelas,
§1, 7,9 G/dia; dias de pico passam de 13 G). Já implantado por outra tarefa (`3771a020`): o backup lê
`HUNTER_BACKUP_RETENTION_DAYS` do `.env` e o padrão caiu para 3 dias; o ambiente da VPS já tem
`HUNTER_BACKUP_RETENTION_DAYS=3` (`printenv`). Com `-mtime +3`, isso guarda em geral **4** dumps, 5
durante a escrita (o script avisa que `+N` guarda N+1; pelos `mtime` pode sobrar um a mais por uma noite, §4).

## 1. As 20 maiores relações, o crescimento e quem as poda

Tamanho total = heap + índices + TOAST (`pg_total_relation_size`). Crescimento: contagem por dia numa
amostra `TABLESAMPLE SYSTEM` (1–5 %) × o tamanho médio da linha na própria tabela; média dos últimos 3–7 dias.

| # | Relação | Total | Heap / índ. / TOAST | Linhas | Cresce/dia | Retenção no contrato | Job | Roda? |
|---|---|---|---|---|---|---|---|---|
| 1 | `opportunity_history_2026_09` | **63 G** | 0,5 / 0,3 / **62 G** | 4,46 M | ~256 mil linhas, **~3,4 G** (picos 8,7 G em 19/09 e 24/09) | 90 d (§1.3) | `prune_partitions.py` | **não** — sem cron |
| 2 | `outbox_events` | **33 G** | 30 / 3,6 / 0 | 36,8 M | ~2,06 M linhas, **~1,95 G** | despachadas > 7 d | `prune_outbox_events.py` (cron `hunter-outbox`) | **nunca rodou**: cron não instalado, `n_tup_del = 0`, sem `outbox-prune.log` |
| 3 | `feature_snapshots_2026_09` | 8,2 G | 3,6 / 0,3 / 4,4 | 3,44 M | ~125–200 mil, ~0,3–0,4 G | 14 d | `prune_partitions.py` | não |
| 4 | `meme_curve_snapshots_2026_09` | 4,0 G | 1,9 / 2,1 / — | 9,99 M | ~1,1 M, ~0,45 G (dobrou desde 23/09) | 90 d | `prune_partitions.py` | não |
| 5 | `meme_trades_2026_09` | 3,3 G | 2,0 / 1,4 / — | 6,00 M | ~0,5 M, ~0,27 G | 90 d | idem | não |
| 6 | `meme_features_15s_2026_09` | 3,2 G | 1,7 / 1,5 / — | 6,35 M | ~0,6 M, ~0,31 G | 7 d | idem | não |
| 7 | `meme_market_activity_1m_2026_09` | 2,7 G | 1,5 / 1,1 / — | 7,18 M | ~0,9 M, ~0,34 G | 30 d | idem | não |
| 8 | `meme_board_observations_2026_09` | 2,6 G | 1,9 / 0,8 / — | 3,40 M | ~0,25 M, ~0,19 G | **nenhuma** (ausente da §1.3 e de `partition_retention.py`) | — | — |
| 9 | `meme_features_1m_2026_09` | 2,2 G | 1,4 / 0,9 / — | 3,93 M | ~0,48 M, ~0,27 G | 90 d | `prune_partitions.py` | não |
| 10 | `candles_1m_2026_09` | 1,9 G | 1,2 / 0,8 / — | 9,28 M | ~0,4 M, ~0,08 G | 90 d | idem | não |
| 11 | `opportunities` | 1,5 G | 0,08 / 0,02 / **1,4 G** | 20 mil | inchaço de UPDATE (12,3 M updates; ~70 kB de TOAST por linha viva) | vivo | autovacuum (6 272 passadas) | sim |
| 12 | `market_snapshots_2026_09` | 1,1 G | 0,7 / 0,4 / — | 6,07 M | ~0,3 M, ~0,055 G | 30 d | `prune_partitions.py` | não |
| 13 | `feature_baselines` | 1,1 G | 0,5 / 0,6 / — | 1,95 M | revisões imutáveis | nenhuma | — | — |
| 14 | `meme_tokens` | 388 M | — | 464 mil | ~20 mil/dia | 90 d por linha | `collect.prune_once` (meme-worker, de hora em hora) | **sim** (`n_tup_del` 39; nada tem 90 d ainda) |
| 15 | `anomalies` | 330 M | — | 117 mil | 36,5 M updates | nenhuma | — | — |
| 16 | `candles_1m_2026_08` | 248 M | — | 1,27 M | backfill | 90 d → cai em 30/11 | `prune_partitions.py` | não |
| 17 | `meme_decision_tapes` | 190 M | 66 M / 6 M / 118 M | 39,5 mil | ~13 mil, ~60 M | 7 d / 90 d com `proposal_ids` (§64) | `decision_tape_writer.maybe_prune` | ligado; nada tem 7 d (1ª linha 24/09) — a 1ª poda real é 01/10 |
| 18 | `market_betas` | 180 M | — | 91 mil | revisões | nenhuma | — | — |
| 19 | `open_interest_history` | 161 M | — | 1,2 M | ~8 M | nenhuma (não particionada, §4) | — | — |
| 20 | `candles_1m_2026_07` | 140 M | — | 714 mil | backfill | 90 d → cai em 30/10 | `prune_partitions.py` | não |

Logo abaixo: `meme_risk_snapshots_2026_09` 138 M (**sem retenção**, como a `board`), `liquidations_2026_09`
133 M (30 d), `meme_gate_refusals_by_mint` 88 M (7 d por linha, **roda**: linha mais velha 20/09,
`n_tup_del` 33 936). `system_events_2026_09` tem 3,3 M, e nenhum `system_event` registra poda ou partição.
`processed_events` está vazia, e o cron de `prune_processed_events.py` não faz falta hoje.

**Crons na VPS** (`/etc/cron.d`, fuso da máquina Europe/Berlin): só `hunter-backup` (03:17 CEST = 01:17Z)
e `hunter-meme-close`. **Não existem** `hunter-outbox`, `hunter-partitions` (criação) nem nenhum cron de
`prune_partitions.py` (o `infra/vps/README.md` diz que "ainda não tem cron"). **Na prática, toda
retenção por partição do §1.3 está desligada.** Mesmo com os crons instalados hoje, nada cairia antes de
29/09 (o `candles_1m_2026_06`, 85 M), porque tudo o que é grande está na partição de setembro.

### 1.1 O defeito estrutural: partição mensal com retenção curta

`is_expired` só derruba um mês quando a **borda superior** passa da janela (`partition_retention.py`).
Numa partição mensal, a tabela guarda então entre `retenção` e `retenção + 31` dias:

| Tabela | Retenção | O mês de setembro cai em | O que a tabela carrega no pico |
|---|---|---|---|
| `meme_features_15s` | 7 d | 08/10 | 38 dias (5,4× os 7 d) |
| `feature_snapshots` | 14 d | 15/10 | 45 dias |
| `meme_market_activity_1m`, `market_snapshots`, `liquidations`, `system_events` | 30 d | 31/10 | 61 dias |
| `opportunity_history`, `meme_curve/trades/features_1m`, `candles_1m` | 90 d | **30/12** | 121 dias |

As três séries meme de 90 d mais a `board` (hoje sem retenção nenhuma), juntas a 1,18 G/dia, chegam a **~143 G** no pico com 90 d. Por isso a
opção "manter 90 d" não cabe neste disco (ver §5).

## 2. Quem precisa de quê (citando o código)

| Dado | Quem lê | Janela que o leitor usa de fato |
|---|---|---|
| `opportunity_history` | API: `apps/api/hunter_api/repositories/opportunities.py:323-333` (`list_history`, `DEFAULT_HISTORY_LIMIT = 100` em `:61`), `radar.py:96-102` (último score), `radar_coverage.py:62-67` (`MAX(score)` de toda a série); ponte de execução: `services/execution-worker/hunter_execution_worker/bridge_universe.py:294-323` (`radar_score`, a última linha com `ts <= at`, com recaída para `opportunities`); pesquisa: 3 SQL de 09/09 (`infra/scripts/sql/research/2026-09-09-radar-0{1,2,4}-*.sql`) | **~2 h** no padrão (100 linhas a ~50/h por oportunidade, medido) e até **~10 h** no teto do endpoint (`MAX_HISTORY_LIMIT = 500`, `schemas/opportunities.py:38`; 50 com `include_envelope`) — a consulta não tem janela de tempo, então a trajetória de uma oportunidade longa fica mais curta com retenção; a ponte, minutos, **mas** a mesma consulta aceita o score de `opportunities` sem limite de idade: com o scanner parado ela devolve um score velho, não `None`. Nenhum `r7x`/`m26` lê a tabela. **A mesa de perpétuos nunca operou:** `trade_proposals` e `orders` têm **0 linhas**; `agent_signals` recebeu 980 em 7 d |
| `outbox_events` | só o despachante e o `reconcile(since=…)` | fila; 7 d = teto da janela de replay (§1.3). Os streams são todos de perpétuos (`anomalies.detected` 1,99 M/dia, `opportunities.updated` 1,30 M, `market.candles.closed` 0,37 M); **meme-worker e meme-executor não escrevem outbox** (grep) |
| `feature_snapshots` | `services/scanner-worker` (5 módulos), `hunter_indicators.features/regime/patterns`; pesquisa: 6 SQL e `.claude/state/r70` | 14 d no contrato |
| `meme_features_1m/15s`, `meme_trades`, `meme_curve_snapshots` | meme-worker (porta, Lab), meme-executor, API; pesquisa: 81/93/33/51 SQL em `infra/scripts/sql/research`, `.claude/state/r59…r81`, `m26` | a pesquisa lê **tudo desde 12/09** (`>= '2026-09-12'` é o filtro mais comum); a porta ao vivo lê segundos/minutos |
| `meme_board_observations` | API `repositories/meme_sources.py:30` (frescor), `hunter_indicators.meme` (2), pesquisa (2 SQL, `r66`, `m26`) | frescor = minutos; pesquisa esporádica |
| `meme_risk_snapshots` | executor: `repo_context.py:87-97`, `risk_snapshot.py:61` (últimos 600 s); pesquisa: 27 SQL, `r80` | 600 s ao vivo |
| `meme_market_activity_1m` | escrita do meme-worker; API (frescor); pesquisa: 1 SQL, `m26` | minutos |
| `candles` | todo o pipeline de perpétuos; backfill/replay até 30 d (§1.3) | 30 d |
| **Dado de decisão** — `meme_proposals`, `meme_paper_bets`, `meme_live_orders/positions`, `trade_proposals/orders/fills`, `audit_logs`, `meme_decision_tapes` (7/90 d) | mesa real, Lab, fichas | **fica como está**; somados têm < 300 M |

## 3. Plano de retenção por tabela

"Libera agora" = volta ao `df` no dia. "Estável" = faixa depois que as quedas mensais entram em regime
(mínimo logo depois de uma queda, máximo na véspera).

| Tabela | Proposta | Libera agora | Estável | Quem decide |
|---|---|---|---|---|
| `opportunity_history` | **(a)** gravar menos: uma linha por oportunidade a cada 5 min **ou** quando `status`/`stage` muda (hoje: 50 linhas/h, 96 % com score diferente), **cada linha com o seu `envelope`** — ele é o que permite recalcular o score depois que baselines, pesos e regime mudaram (`hunter_core/db/models/analysis.py:282-286`), então tirá-lo seria perder explicabilidade → ~0,7 G/dia; **ou (b)** desligar o scanner de perpétuos enquanto o foco é meme. Retenção 90 → **14 d**. **`TRUNCATE opportunity_history_2026_09`** (nenhum leitor quebra com a tabela vazia, §2) | **63–65 G** com o `TRUNCATE`; 0 sem ele | (a) 10–32 G; (b) 0 | **Everton** (apaga histórico; muda §1.3) |
| `outbox_events` | instalar o cron `hunter-outbox` (7 d, já é o contrato) → a população cai para ~15 M e a tabela para de crescer por reuso interno (o autovacuum precisa passar; um snapshot longo, como o do `pg_dump` de 80 min, atrasa esse reuso); **opcional:** 7 → **2 d** + um `VACUUM FULL` numa janela com os escritores de perpétuos parados | 0 (só o cron); **~29 G** com 2 d + `VACUUM FULL` | 33 G (arquivo) com 7 d; ~4 G com 2 d | o cron: contrato já decidido, Everton instala; 2 d + `VACUUM FULL`: **Everton** (janela de replay 7 → 2 d) |
| `feature_snapshots` | manter 14 d; só instalar a poda | 0 (setembro cai em 15/10: ~9,8 G) | 5–18 G (0 com o scanner desligado) | contrato já decidido |
| `meme_curve_snapshots`, `meme_trades`, `meme_features_1m` | `MEME_RETENTION_DAYS` 90 → **30 d** (ou 45 d, §5), com **arquivo do mês antes do `DROP`** (`pg_dump -Fc` da partição, ~0,18 × o tamanho, ~6 G/mês acumulando) até haver offsite; a mesma janela para graduada e não graduada (§33.4 continua valendo — o que a Astra vetou foi escolher pelo desfecho, não o prazo) | 0 (setembro cai em 31/10 com 30 d) | 30 d: 35–72 G; 45 d: 53–90 G; 90 d: 106–143 G | **Everton** (muda §33.4 e o alcance da pesquisa) |
| `meme_board_observations`, `meme_risk_snapshots` | **dar retenção** — hoje é "para sempre" por omissão: a mesma de `MEME_RETENTION_DAYS` | 0 | 30 d: 6–12 G | **Everton** (hoje nada as apaga) |
| `meme_features_15s` | manter 7 d; só instalar a poda | 0 (setembro cai em 08/10: ~4,4 G) | 2–12 G | contrato já decidido |
| `meme_market_activity_1m`, `market_snapshots`, `liquidations`, `system_events` | manter 30 d; só instalar a poda | 0 (setembro cai em 31/10: ~5,5 G) | ~13–27 G | contrato já decidido |
| `candles_1m` | manter 90 d (pequena; os meses de junho a agosto caem em 29/09, 30/10 e 30/11) | 0,08 G em 29/09 | 7–10 G | contrato já decidido |
| `opportunities` (TOAST 1,4 G) | nada agora (inchaço estável de UPDATE; `VACUUM FULL` devolveria ~1,2 G, não vale uma trava) | — | ~1,5 G | — |
| decisão (propostas, apostas, ordens, posições, auditoria, fitas 7/90 d) | **não mexer** | — | < 2 G | — |

**Downsample** das séries meme (ex.: `meme_curve_snapshots` a 1/min depois de 14 d) foi considerado e
**não** entra: o `hunter_worker` não tem `DELETE` nessas pais (§33.4) e um rollup exigiria tabela nova e
migração; a relação custo/ganho é pior que encurtar a janela e arquivar o mês. Partição **semanal** para as
séries meme de alto volume cortaria o excesso de +31 d (§1.1) e é a correção estrutural, mas é
arquitetural (§1.3/§15.5 fixam mensal) — plano separado, depois desta emergência.

## 4. Backup

Composição do dump de hoje, estimada comprimindo com gzip -6 uma amostra `COPY` de cada tabela
(0,05–5 % das linhas) × a contagem de linhas. O total estimado (26,6 G) bate com a série do `backup.log`
(23,4 G em 26/09, +~2 G/dia):

| Tabela | No dump | Bytes/linha |
|---|---|---|
| `opportunity_history` | **17,2 G (65 %)** | 4 145 |
| `outbox_events` | 3,7 G (14 %) | 107 |
| `feature_snapshots` | 1,5 G | 455 |
| 6 séries meme somadas | ~3,2 G | 55–220 |
| `candles_1m` + `market_snapshots` | ~0,6 G | 39–42 |
| resto | ~0,4 G | — |

| Opção | Dump hoje | Cresce/dia | Pegada de backup no disco | Tempo |
|---|---|---|---|---|
| Hoje (completo, retenção 3 → 4 dumps + 1 escrevendo) | ~27 G | ~2 G | **~110–140 G** em uma semana | 80+ min |
| Guardar 3 dumps (`HUNTER_BACKUP_RETENTION_DAYS=2`) | ~27 G | ~2 G | ~85–110 G | idem |
| **3 dumps + `--exclude-table-data-and-children=opportunity_history`** | **~9,4 G** (~7,2 G depois da poda de 7 d da outbox; ~6,1 G com 2 d) | ~0,5 G | **~28 G** hoje; ~65–90 G no regime de §5 | ~20–30 min (estimado) |
| + excluir também `feature_snapshots`, `candles`, `market_snapshots` (regeneráveis por backfill/recomputo) | −2,1 G | −0,1 G | −6 G | — |
| Compressão `-Z zstd:3` no lugar do gzip padrão | ratio parecido, mais rápido | — | — | a medir uma vez |

- O que a exclusão custa: num restore, `opportunity_history` volta **com schema e vazia**. Ela é explicação
  histórica do radar de perpétuos, não estado: nenhuma FK aponta para ela (a única sai dela para
  `opportunities`, `analysis.py:268`) e nenhuma posição, ordem ou aposta depende dela.
- **A outbox fica no dump** (correção da revisão da Astra). O `reconcile` republica os payloads **da própria
  `outbox_events`** (`outbox_store.py:217`, `outbox_recovery.py:74`) — não os reconstrói das tabelas de
  negócio. Um dump sem ela perderia, num restore, a obrigação de publicar os eventos pendentes daquele
  instante e a capacidade de recompor um Redis perdido. Depois da poda de 7 d ela custa ~1,6 G no dump; com
  2 d, ~0,5 G.
- **Retenção por idade não é contagem de arquivos.** `find -mtime +2` apaga o que tem **pelo menos 3
  períodos completos de 24 h** pelo `mtime` (fim da escrita), e o script só poda depois de validar o dump
  novo. Um dump novo mais curto que o antigo deixa o antigo "jovem demais" por uma noite: o de 25/09
  terminou às 02:33Z, e um dump reduzido que termine às ~01:45Z de 28/09 o encontra com 2 d 23 h → ele
  **sobrevive**. Recomendação para o `devops-engineer`: reter por **quantidade** (os N dumps válidos mais
  novos), nunca apagando antes de o substituto passar no `pg_restore --list`.
- O dump mora **no mesmo disco** (`infra/vps/README.md`, seção Backup): protege de erro humano e de
  corrupção lógica, não da perda do disco. Offsite é pago (ordem de US$ 5–7 por TB/mês em armazenamento
  de objeto; confirmar o preço antes) → **decisão do Everton**. Com a exclusão, o volume offsite fica em
  ~7–30 G por dump.
- `zstd` está compilado no servidor (`pg_config --configure` mostra `--with-zstd`; `pg_dump` 16.15 aceita
  `-Z zstd:N`). O nível pesa bem menos que a exclusão; recomendo medir `zstd:3` contra o padrão uma vez.
- `pg_dump` 16 tem `--exclude-table-data-and-children` (pega a pai e todas as partições); o padrão
  `'opportunity_history*'` também serve.

## 5. Previsão de disco por opção

Modelo por tabela: partições mensais que caem na borda superior + retenção; dump = soma das razões medidas
na §4 (a outbox pelas linhas vivas); backup noturno às 01:17Z, que **falha se o livre menos uma reserva
operacional de 20 G** (WAL, temporários de `VACUUM`, crescimento durante o dump) for menor que o dump;
arquivo local do mês meme, quando incluído, acumula sem retenção. Ponto de partida: 127 G livres em 27/09
03:15Z; taxas da §1; horizonte de **150 dias** ("—" = nenhuma falha **nos 150 dias simulados**, não
"nunca"). Script de trabalho `scratchpad/forecast4.py`, fora do repositório; estimativas de ±15 %.

| Opção | O que inclui | 1ª falha de backup | Disco cheio | Pico do banco | Livre em 150 d | Livre mínimo |
|---|---|---|---|---|---|---|
| O0 | nada além da retenção 3 já implantada | **01/10 (+4 d)** | **06/10 (+10 d)** | 209 G | 0 | — |
| O1 | backup: 3 dumps sem dados de `opportunity_history` | 10/10 (+13 d) | 14/10 (+18 d) | 272 G | 0 | — |
| O2 | O1 + crons (outbox 7 d, poda de partição com o contrato atual) | 19/10 (+22 d) | 24/10 (+28 d) | 281 G | 0 | — |
| O3 | O2 + `opportunity_history` 1 linha/5 min (em +2 d) e 14 d | 27/11 (+61 d) | 28/12 (+93 d) | 243 G | 0 | — |
| O3′ | O3 com `opportunity_history` a 90 d (contrato) | 30/10 (+33 d) | 19/11 (+53 d) | 265 G | 0 | — |
| O4 | O3 + `TRUNCATE opportunity_history_2026_09` + outbox 2 d + `VACUUM FULL` (em +1 d) | 11/12 (+75 d) | 26/01 (+121 d) | 232 G | 0 | — |
| **O5** | **O4 + meme 90 → 30 d (e `board`/`risk` 30 d)** | **—** | **—** | **169 G** | **98 G** | **55 G** |
| O5a | O5 + arquivo local de cada mês meme (~6 G/mês) | — | — | 169 G | 74 G | 38 G |
| O5b | O4 + meme 45 d | 14/02 (+140 d) | — | 195 G | 98 G | 17 G |
| O5c | O4 + meme 60 d | 26/12 (+90 d) | — | 204 G | 43 G | 0 |
| O6 | O5 com o scanner de perpétuos desligado em vez de gravar menos | — | — | 138 G | 133 G | 99 G |

**Sensibilidade (meme crescendo 1,5×, o que já aconteceu entre 23 e 26/09):** O5 não enche, mas um backup
falha em 25/11; O5a enche em 29/01; O5b e O5c enchem em meados de dezembro; **só O6 atravessa os 150 dias**
(uma falha de backup em 29/01).

**Conclusão.** Com partição mensal e este disco, a combinação que atravessa os 150 dias no cenário-base é
**O5** (perpétuos enxutos + `TRUNCATE` + outbox 2 d + meme 30 d); com o crescimento meme continuando, só
**O6** (perpétuos desligados) segura. Janelas meme de 45–60 d exigem uma de três coisas: offsite (tira os
dumps do disco), partição semanal nas séries meme (tira o excesso de até +31 d, §1.1) ou disco maior.
Esses números mostram a preferência por 30 d, não que 45 d seja impossível.

## 6. Comandos que implementariam cada passo (nada executado)

Ordem sugerida. Onde há "**decisão do Everton**", o passo apaga dado ou reduz o que o backup protege.

**Passo 0 — devolver disco sem tocar em dado (hoje, ~10 G).** Imagem e cache se reconstroem do git.
```bash
ssh hunter-vps 'docker builder prune -f --filter until=72h && docker image prune -a -f --filter until=72h'
```

**Passo 1 — backup menor (decisão do Everton: reduz o que o dump protege).** Em `infra/vps/backup_postgres.sh`, a linha do `pg_dump`
(o arquivo acabou de ser mexido por `3771a020`; a mudança vai para o `devops-engineer`, não para esta proposta):
```bash
compose exec -T postgres pg_dump -U hunter -d hunter -Fc -Z zstd:3 \
  --exclude-table-data-and-children=opportunity_history > "$TARGET"
```
Retenção por quantidade no lugar do `find -mtime` (§4), ou, sem mexer no script, `HUNTER_BACKUP_RETENTION_DAYS=2`
na linha do `.env` da VPS (o Everton edita; agente não escreve `.env`). Com `-mtime +2`, pelos `mtime` reais:
na 1ª noite sai só o de 24/09 (o de 25/09 fica com 2 d 23 h), **+9 G** líquidos; na 2ª, o de 25/09, **+12 G**;
na 3ª, o de 26/09, **+14 G** — `/opt/backups` vai de 63 G a ~28 G em três noites. Se o Everton quiser o
espaço na hora: `rm /opt/backups/hunter-20260924T011701Z.dump /opt/backups/hunter-20260925T011701Z.dump`
devolve 40 G (**decisão do Everton**: são backups; o de 26/09 continua lá).

**Passo 2 — ligar a retenção que o contrato já decidiu (o Everton instala; sudo).**
```bash
# a) outbox, 7 d (receita de infra/vps/README.md "Poda da outbox"): primeira passada em fatias
bash infra/vps/compose.sh ops python infra/scripts/prune_outbox_events.py --dry-run
bash infra/vps/compose.sh ops python infra/scripts/prune_outbox_events.py --max-batches 200
printf '%s\n' 'SHELL=/bin/bash' 'PATH=/usr/local/bin:/usr/bin:/bin' \
  '37 4 * * * hunter cd /opt/project-hunter && flock -n /tmp/hunter-outbox-prune.lock bash infra/vps/compose.sh ops python infra/scripts/prune_outbox_events.py >> /opt/backups/outbox-prune.log 2>&1' \
  | sudo tee /etc/cron.d/hunter-outbox >/dev/null && sudo chmod 644 /etc/cron.d/hunter-outbox
# b) criação de partições (receita do README; hoje existem até 2026_12)
printf '%s\n' 'SHELL=/bin/bash' 'PATH=/usr/local/bin:/usr/bin:/bin' \
  '7 4 * * * hunter cd /opt/project-hunter && bash infra/vps/compose.sh ops python infra/scripts/create_partitions.py >> /opt/backups/partitions.log 2>&1' \
  | sudo tee /etc/cron.d/hunter-partitions >/dev/null && sudo chmod 644 /etc/cron.d/hunter-partitions
# c) poda de partições (NOVO; ainda não tem receita no README). SÓ DEPOIS da correção abaixo.
bash infra/vps/compose.sh ops python infra/scripts/prune_partitions.py --dry-run
printf '%s\n' 'SHELL=/bin/bash' 'PATH=/usr/local/bin:/usr/bin:/bin' \
  '47 5 * * * hunter cd /opt/project-hunter && flock -n /tmp/hunter-partitions-prune.lock bash infra/vps/compose.sh ops python infra/scripts/prune_partitions.py >> /opt/backups/partitions-prune.log 2>&1' \
  | sudo tee /etc/cron.d/hunter-prune-partitions >/dev/null && sudo chmod 644 /etc/cron.d/hunter-prune-partitions
```
**Pré-requisito do item (c) — correção de código antes do cron (achado da revisão, conferido no código).**
`prune_partitions.prune()` (`infra/scripts/prune_partitions.py:109-121`) roda **todos** os `DETACH`/`DROP`
numa transação só (`engine.begin()`), **sem `lock_timeout`**, e o `DETACH` é o não concorrente
(`hunter_core/db/models/_partitions.py:126`), que pede `ACCESS EXCLUSIVE` na pai. Cenário: o dump das
01:17Z segura `ACCESS SHARE` em todas as tabelas por 80 min; um `DETACH` que chega nesse intervalo fica na
fila e **tudo o que chega depois dele na mesma pai também** — os `INSERT` do meme-worker em
`meme_features_15s` param até o dump terminar. Correção (tarefa pequena, `backend-specialist`, revisão do
database-architect): uma transação por partição com `SET LOCAL lock_timeout = '3s'` (o mesmo padrão de
`create_partitions.py`, §1.3), falha registrada e seguindo para a próxima, `system_event` no fim; e o horário
fora da janela do dump (05:47 CEST = 03:47Z na linha acima; o dump de hoje termina ~02:40Z, o reduzido bem
antes). Com o contrato de hoje, o podador derruba `candles_1m_2026_06` em 29/09,
`meme_features_15s_2026_09` em 08/10, `feature_snapshots_2026_09` em 15/10 e as de 30 d em 31/10.

**Passo 3 — perpétuos (decisão do Everton).** Escolher (a) gravar menos ou (b) desligar.
- (a) código em quem decide gravar a linha de histórico no scanner (`services/scanner-worker/hunter_scanner_worker/writers.py::write_history`
  recebe as linhas; tarefa para o `backend-specialist`, revisada pelo `quant-engineer`): gravar só se mudou
  `status`/`stage` ou se passaram 300 s da última amostra da oportunidade. **Sem migração:** cada linha
  preservada continua completa, com `decomposition` **e** `envelope` (tornar o `envelope` anulável foi
  descartado — ele é o que torna "recalcule este score com o que ele viu" verdadeiro, `analysis.py:282-286`).
- (b) `bash infra/vps/compose.sh stop scanner-worker` (e tirá-lo do `up` padrão). **Atenção:** o
  `bridge_universe.radar_score` (`:294-323`) cai para o score de `opportunities`, que não tem limite de
  idade — com o scanner parado, a ponte ordenaria sinais por um score velho em vez de receber `None`. Parar
  o scanner pede também um corte de idade nessa consulta (tarefa do `risk-engine-guardian`, dono da ponte).
- Retenção 90 → 14 d: `partition_retention.py` (`"opportunity_history": 14`) + a linha da §1.3.
- Espaço na hora: `TRUNCATE` da partição (devolve os ~65 G ao `df` depois do commit; nenhum leitor quebra com
  a tabela vazia — lista vazia na API, variação zero no radar, `MAX` nulo aceito em `radar_coverage`):
  ```sql
  BEGIN; SET LOCAL lock_timeout = '3s'; TRUNCATE opportunity_history_2026_09; COMMIT;
  ```
  rodado como dono (`bash infra/vps/compose.sh exec -T postgres psql -X -v ON_ERROR_STOP=1 -U hunter -d hunter`).
  O `lock_timeout` limita a **espera** pelo lock, não a operação. Efeitos visíveis: a trajetória das
  oportunidades abertas recomeça do zero; `radar_coverage` passa a reportar o `MAX(score)` desde o `TRUNCATE`.

**Passo 4 — outbox 2 d + `VACUUM FULL` (decisão do Everton; janela de replay 7 → 2 d).** O
`infra/vps/README.md` diz "nunca `VACUUM FULL`" porque ele trava o despachante; a proposta contorna isso
parando os escritores de perpétuos (a mesa meme não usa outbox):
```bash
bash infra/vps/compose.sh ops python infra/scripts/prune_outbox_events.py --retention-days 2
# parar e religar OS MESMOS containers (sem build, sem recriar, sem mudar perfis):
# `compose.sh up` faz `up -d --build --remove-orphans` (compose.sh:220) e depende de MEME/MEME_LIVE/MARKET_SPOT
PERP="hunter-scanner-worker-1 hunter-market-worker-1 hunter-market-worker-1-1 hunter-market-worker-2-1 hunter-market-worker-3-1 hunter-market-worker-spot-1 hunter-strategy-worker-1 hunter-strategy-worker-1-1 hunter-strategy-worker-2-1 hunter-strategy-worker-3-1 hunter-execution-worker-1"
docker ps --format '{{.Names}}' | sort > /tmp/antes.txt
docker stop $PERP
bash infra/vps/compose.sh exec -T postgres psql -X -v ON_ERROR_STOP=1 -U hunter -d hunter \
  -c "SET lock_timeout='5s'" -c "VACUUM (FULL, VERBOSE, ANALYZE) public.outbox_events"
docker start $PERP
docker ps --format '{{.Names}}' | sort | diff /tmp/antes.txt -   # tem de sair vazio
```
Dois `-c` separados de propósito: vários comandos num `-c` só viram uma transação, e `VACUUM` recusa rodar
dentro de uma. Reescreve só as linhas vivas (~4 M, ~4 G); o arquivo antigo existe até o fim, então reservar
**~10 G livres** (tabela nova + índices reconstruídos + WAL), não 4. Leva alguns minutos; o market-worker
recupera os minutos parados pelo backfill de lacunas (`ingestion_gaps`). **Condição:** o
`market-worker-spot` alimenta a mesa real `spot/1` — a janela só acontece com **zero posição spot aberta**
(conferir `spot_positions` abertas e o heartbeat antes) e com o `risk-engine-guardian` de acordo; meme-worker e
meme-executor seguem rodando (não escrevem outbox). No cron, trocar para
`--retention-days 2`, mudar a §1.3 e o `RETENTION_DAYS` do script.

**Passo 5 — meme 90 → 30 d (decisão do Everton).**
- `MEME_RETENTION_DAYS=30` no `.env` da VPS (o Everton edita) — vale para curve/trades/features_1m **e** para a
  poda por linha de `meme_tokens` (`app.meme_retention`).
- `partition_retention.py`: `"meme_board_observations": config.meme_retention_days`,
  `"meme_risk_snapshots": config.meme_retention_days`; linhas novas na §1.3 e na §33.4.
- Antes de cada `DROP`, arquivar o mês (até haver offsite), só de dados, validado antes de o podador agir:
  ```bash
  for t in meme_curve_snapshots meme_trades meme_features_1m meme_board_observations meme_risk_snapshots; do
    f="/opt/backups/archive-${t}_2026_09.dump"
    bash infra/vps/compose.sh exec -T postgres pg_dump -U hunter -d hunter -Fc -Z zstd:9 --data-only \
      -t "public.${t}_2026_09" > "$f.tmp" \
      && bash infra/vps/compose.sh exec -T postgres pg_restore --list < "$f.tmp" >/dev/null \
      && mv "$f.tmp" "$f" || { rm -f "$f.tmp"; echo "ARQUIVO FALHOU: $t"; }
  done
  ```
  ~6 G por mês de meme, **acumulando** — o padrão `hunter-*.dump` da retenção do backup não os apaga (é o
  O5a da §5). Restaurar exige recriar a partição antes (`--data-only` não traz o schema). Isso só vira
  rotina se o `prune_partitions.py` ganhar um gancho `--archive-dir` que recusa o `DROP` quando o arquivo
  falhar — mudança de código revisada pelo database-architect.

## 7. O que muda no contrato quando o Everton decidir

Nada foi alterado em `docs/DATABASE.md` por esta proposta. Se aprovada, a mesma tarefa que muda o código
atualiza:
- §1.3, tabela: `opportunity_history` 90 → 14 d; `outbox_events` 7 → 2 d (se o passo 4 for aprovado, e o
  parágrafo "os 7 dias são o teto da janela de replay" junto); **linhas novas** para
  `meme_board_observations` e `meme_risk_snapshots`; `meme_*` com o valor novo de `MEME_RETENTION_DAYS`; a
  coluna "Job" deixa de dizer `analytics-worker` e passa a dizer os crons reais.
- §33.4: o prazo (não a regra "mesma janela para graduada e não graduada").
- §1.3/§15.5: se a partição semanal das séries meme for aprovada, isso é plano arquitetural próprio.

Lacunas que já existem no contrato e ficam registradas aqui: `meme_board_observations` e
`meme_risk_snapshots` (§35, `0023`) nunca receberam retenção; a §1.3 atribui a poda de partições e a criação
"agendada no analytics-worker", que não existe, e nenhum cron substituiu isso na VPS.

## 8. Recomendação (para o Everton decidir)

1. **Hoje, sem apagar dado:** passo 0 (cache/imagens, ~10 G) e a correção do `prune_partitions.py` (§6,
   passo 2c) antes de qualquer cron de poda.
2. **Hoje, com decisão:** passo 1 (backup sem os dados de `opportunity_history`, retenção por quantidade) e
   passo 2a/2b (outbox 7 d e criação de partições — o contrato já decidiu, falta instalar).
3. **Esta semana, com decisão:** passo 3 — gravar menos **ou** desligar os perpétuos, mais o `TRUNCATE`
   (~65 G na hora). Sem isso, nenhuma opção passa de dezembro (§5: O3′/O4).
4. **Com janela marcada:** passo 4 (outbox 2 d + `VACUUM FULL`, ~29 G), com zero posição spot aberta.
5. **Antes de 31/10:** passo 5 — meme 30 d, com `board`/`risk` ganhando retenção; o arquivo local do mês só
   se o Everton quiser guardar o histórico de pesquisa até haver offsite.
6. **Depois da emergência (arquitetural, plano próprio):** partição semanal para as séries meme de alto
   volume, e offsite dos dumps. Só com um dos dois uma janela meme de 45–60 d volta a caber.

## 9. Segunda opinião (Astra)

Parecer completo em `.claude/state/astra-review-retencao-disco-2026-09-27.md` (só leitura, 27/09). Cada
achado foi conferido no código antes de entrar aqui:

| Achado da Astra | Conferido em | Decisão |
|---|---|---|
| `VACUUM` dentro de um `psql -c` com vários comandos falha (bloco de transação) | documentação do psql | **aceito**: dois `-c` (passo 4) |
| `compose.sh up` faz `--build --remove-orphans` e depende de perfis | `infra/vps/compose.sh:220` | **aceito**: `docker stop/start` dos mesmos containers, com `diff` antes/depois |
| excluir a outbox do dump perde o que o `reconcile` republicaria | `outbox_store.py:217`, `outbox_recovery.py:74` | **aceito**: a outbox fica no dump; só `opportunity_history` sai |
| `-mtime +N` não garante N+1 dumps | `backup_postgres.sh:87` e os `mtime` reais | **aceito**: números de liberação refeitos; recomendada retenção por quantidade |
| o podador de partições pode travar a ingestão esperando lock | `prune_partitions.py:109-121`, `_partitions.py:126` | **aceito**: virou pré-requisito do cron (passo 2c) |
| "nunca" no modelo, reserva operacional e arquivos acumulando | modelo refeito (`forecast4.py`) | **aceito**: reserva de 20 G, arquivo como O5a, horizonte explícito |
| a API lê até 500 linhas, não 100 | `schemas/opportunities.py:38` | **aceito** (§2); não muda o plano: 500 linhas ≈ 10 h ≪ 14 d |
| `envelope` anulável custa explicabilidade | `analysis.py:282-286` | **aceito**: descartado; a redução é só de frequência |
| parar o scanner não dá `None` na ponte (score velho de `opportunities`) | `bridge_universe.py:294-323` | **aceito**: registrado no passo 3(b) como tarefa do `risk-engine-guardian` |

Sem discordâncias abertas.
