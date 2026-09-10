# Ligar o fluxo paper — runbook de ativação (decisão do Everton, 2026-09-08: "bora ativar tudo")

Este é o caminho, na ordem, para a carteira `ever` passar a receber sinais do Lab por conta própria. Cada passo tem quem faz, o que prova e o que **não** muda. Nada aqui é automático: os passos 6, 7 e 8 são atos do Everton, auditados. A diretiva de origem (`.claude/state/directive-risk-engine-2026-09-06.md`) continua inteira; nenhum limite foi alterado.

## Por que não é uma flag só

| Fato medido | Consequência |
|---|---|
| Ligar o coletor spot no shard 0 com 200 perpétuos derrubou o socket perpétuo (1011, 8 reconexões em 6 min — `t30-proof.md` §1) | o spot precisa de um **processo próprio** (T3.0f); sem fita spot no hot state a admissão devolve `unavailable` e recusa tudo |
| `market_betas` vazia na VPS (2026-09-08 03:40Z): o job horário de β nunca foi escrito; a VPS tem 11 dias de velas e o `beta_v1` exige 20 contíguos numa janela de 30 | precisa do **produtor de β** (T3.7b) e de **backfill de 31 dias** nos 20 mercados que importam; sem β válido a admissão recusa ("sem β validado só shadow") |
| O rótulo `paper` só existe com a `0010` | o **segundo deploy** vem antes da linha `paper` |

## Os passos

| # | Passo | Quem | Prova |
|---|---|---|---|
| 1 | T3.0f: `market-worker-spot` como serviço próprio; revisão; commit | agentes / orquestrador | 30 min local: perpétuo sem reconexão, spot com 19 fitas, `hb:market:spot:binance` vivo (`t30f-proof.md`) |
| 2 | T3.7b: job horário de β no scanner + `request_backfill.py --days 31`; revisão do guardian; commit | agentes / orquestrador | revisões em `market_betas` com `valid_until > now()` para os mercados com ≥ 20 dias contíguos; motivos para os outros (`notes-T3.7b.md`) |
| 3 | Revisões da `0010` (database-architect, guardian, security) — feitas em 2026-09-08: nada bloqueia o **deploy**; o guardian **bloqueia ligar a ponte** até a T3.15c (a ponte passa a julgar a coluna `purpose`, não o envelope; o worker perde o poder de ativar um rascunho) e a T3.15e (ativação da linha derivada mantém o conteúdo copiado; uma coorte só pela ponte) | agentes | `.claude/state/review-T3.15-{db,risk,security}.md`, `notes-T3.15c.md`, `notes-T3.15e.md` |
| 4 | **Segundo deploy** (traz `0010`, T3.15b, T3.0f, T3.7b) | **Everton** | `ssh hunter-vps 'cd /opt/project-hunter && MARKET_SPOT=1 MARKET_SHARDS=4 bash infra/vps/compose.sh update'` (a flag `MARKET_SPOT=1` nasce na T3.0f) — depois: alembic em `0010`, `hb:market:spot:binance`, perpétuos intactos, `/ready` 200 |
| 5 | Backfill de 31 dias na VPS e primeira rodada de β | orquestrador (leitura) / script no container da API | `market.candles.backfilled` para os 20 mercados; `hb:scanner` com `beta_valid ≥ 1` |
| 6 | **Linha `paper` do momentum** | **Everton** (ou orquestrador com o seu "vai") | pelo serviço `ops` (T3.15d, DEPLOYMENT.md §3.4): `bash infra/vps/compose.sh run --rm ops python infra/scripts/activate_strategy_version.py momentum v1 --paper-line --dry-run --changelog "D10"`; sem `--dry-run` cria `momentum v2` `draft`, `purpose=paper`, `system_events` |
| 7 | **Ativação auditada** da linha `paper` | **Everton** | `activate_strategy_version.py momentum v2 --changelog "D10: coorte paper"` (mesmo serviço `ops`) → `activated_at`, congelada; o strategy-worker passa a emitir sinais `purpose=paper` para essa coorte (a `research_only` continua ao lado) |
| 8 | **`ENABLE_PAPER_AUTONOMY=true`** no `.env` da VPS + `compose.sh update` — T3.15c e T3.15e **implantadas em 2026-09-08 (`9a291d3`)**: a trava do guardian está liberada | **Everton** | log `execution_worker_starting paper_autonomy=true`; `hb:execution:paper` com `pending_requests` variando; primeira proposta em `trade_proposals` com `proposal_source=agent` |
| 8a | **Vínculo `agents`**: a linha que liga `momentum v3` (paper) à carteira `ever`. **Vem antes da flag** — sem ela a ponte não tem público (§8a) | **Everton** | `SELECT count(*) FROM agents WHERE status='enabled'` = 1; `hb:execution:paper` com `bridge_candidates` > 0 |
| 9 | Primeira avaliação datada do EXP-0005 depois do primeiro fill | Sexta-feira | SQL colado na página |

## 8a. O vínculo `agents` — medido em 2026-09-08 14:0xZ: **não existe**

```sql
-- rodado como leitura na VPS, 2026-09-08:
SELECT count(*) AS agents_total FROM agents;   -->  0
```

Zero linhas em `agents`. É **esta** a razão de "154 sinais paper, 0 propostas": a
consulta da ponte (`bridge_repo.py`, `_SIGNAL_SELECT`) só considera candidato um
sinal cuja versão a carteira **roda** — `EXISTS (SELECT 1 FROM agents ...)` —, e
`bridge_screen._agent_for` exige além disso `status='enabled'`, senão recusa por
nome (`agent_unavailable`). Ativar a versão (passo 7) não cria o vínculo; ligar a
flag (passo 8) sobre zero agentes só produz um laço que não acha nada.

**Comando auditado que o operador roda — ninguém mais.** Uma transação, com a
linha de auditoria junto: uma alocação de capital sem `audit_logs` é exatamente a
mutação silenciosa que a CLAUDE.md proíbe. Os ids abaixo são os medidos na VPS em
2026-09-08; confira cada um antes de executar (as três primeiras linhas são
leitura pura e existem para isso).

```sql
-- 1) conferência (leitura): os quatro ids têm de bater com o que está aqui
SELECT id, slug FROM organizations WHERE slug = 'ever';
    -- 01a07693-160f-70d0-aa35-c6c339187e8a
SELECT id, name FROM workspaces WHERE organization_id = '01a07693-160f-70d0-aa35-c6c339187e8a';
    -- 01a07693-163a-722f-b734-9e13dbd519dc
SELECT id, name, type, is_arena FROM portfolios
 WHERE organization_id = '01a07693-160f-70d0-aa35-c6c339187e8a';
    -- 01a07a1e-f6ae-7366-a7fe-ab3d9c83d488 | Carteira paper principal | paper | f
SELECT v.id, s.key, v.version, v.status, v.purpose FROM strategy_versions v
  JOIN strategies s ON s.id = v.strategy_id WHERE s.key='momentum' AND v.version='v3';
    -- 02751faa-b2ee-4dc6-95a0-67967f7dfb88 | momentum | v3 | active | paper

-- 2) o ato (uma transação, auditado)
BEGIN;
WITH novo AS (
  INSERT INTO agents (
    id, organization_id, workspace_id, portfolio_id, name, strategy_version_id,
    uses_custom_params, status, allowed_directions, market_filter, created_by
  ) VALUES (
    gen_random_uuid(),
    '01a07693-160f-70d0-aa35-c6c339187e8a',   -- org ever
    '01a07693-163a-722f-b734-9e13dbd519dc',   -- workspace ever
    '01a07a1e-f6ae-7366-a7fe-ab3d9c83d488',   -- Carteira paper principal
    'momentum v3 (paper)',
    '02751faa-b2ee-4dc6-95a0-67967f7dfb88',   -- momentum v3, purpose=paper
    false,
    'enabled',
    ARRAY['long']::trade_direction[],          -- SPOT long-only (RISK_ENGINE.md §3.1 check 3)
    '{}'::jsonb,
    '01a07692-dc7c-7ca2-bc0a-efd0ffb889e5'    -- Everton
  ) RETURNING id, organization_id, portfolio_id, strategy_version_id, status, name
)
INSERT INTO audit_logs (id, organization_id, actor_type, actor_id, action, entity_type, entity_id, after, metadata)
SELECT gen_random_uuid(), novo.organization_id, 'user',
       '01a07692-dc7c-7ca2-bc0a-efd0ffb889e5', 'agent.created', 'agent', novo.id,
       to_jsonb(novo), '{"origem": "docs/ACTIVATION.md passo 8a", "tarefa": "T3.29"}'::jsonb
  FROM novo;
COMMIT;
```

**Por que só `long`:** o `paper_v1` é SPOT sem empréstimo (`max_leverage = 1`), e a
ponte já recusa `direction_unsupported`; deixar `{long,short}` (o default da
coluna) faria a carteira aceitar na fila sinais que o motor recusa depois — ruído
no funil, não uma trava a mais.

**Para desligar** (não apaga histórico): `UPDATE agents SET status='paused' ...`,
auditado do mesmo jeito. A ponte então conta `agent_unavailable` em vez de
simplesmente não ver o sinal — que é a diferença entre "pausado" e "nunca
existiu", e o operador precisa vê-la.

## Estado em 2026-09-08 ~06:50Z
| Passo | Estado |
|---|---|
| 1 spot como serviço | **feito** (`0451066`), na VPS: 14 pares, 0 reconexões |
| 2 β | job horário na VPS; backfill de 31 dias pedido às 04:35Z (90 janelas), β válido quando a fila terminar (~12:00Z) |
| 3 revisões / T3.15c / T3.15e | **feito** e implantado (`e4b531a`, `9a291d3`) |
| 4 segundo deploy | **feito** (0010 e 0011 aplicadas; VPS em `9a291d3`) |
| 5 backfill + primeira rodada de β | em andamento |
| 6 linha `paper` | **feito**: `momentum v3` em rascunho (04:34Z) |
| 7 ativação auditada | **Everton** — `bash infra/vps/compose.sh run --rm ops python infra/scripts/activate_strategy_version.py momentum v3 --changelog D10_coorte_paper_ativada_por_Everton_2026-09-08` (T3.15d: já não é `docker exec hunter-api-1` — esse container não tem mais `DATABASE_URL_MIGRATIONS`, DEPLOYMENT.md §3.4; sem aspas internas, por causa do PowerShell) |
| 8 flag | **Everton** — depois do 7 e com β válido |

## §8 — Checklist de aceite do modo autônomo (T3.29, medido na VPS em 2026-09-08 ~14:10Z; remedido em 2026-09-10 ~00:47Z BRT / 03:47Z UTC, T3.71)

O Everton vira a flag do passo 8 **quando toda linha estiver verde**. Cada linha
é uma medição, com a consulta que a produziu; nenhuma é opinião. Leituras feitas
como `docker exec hunter-postgres-1 psql -U hunter -d hunter` (somente `SELECT`,
transação `repeatable read read only`). **Histórico 2026-09-08** (referência,
não repetido linha a linha): 0 `agents`; 15/15 spot com `avgPrice` mas sem
deploy; β válido só para BTCUSDT por identidade (1/200) e 0/171 sinais de 24 h
passariam; `mark_quality` sem deploy; backup só com TOC provado, sem restore
real; MTM e `paper_autonomy=false` já verdes; `risk_profile_id` NULL.

| # | Condição | Medido em 2026-09-10 (00:47 BRT / 03:47Z) | Verde? |
|---|---|---|---|
| 1 | **Vínculo `agents`** habilitado para `momentum v3` + carteira `ever` | `SELECT count(*) FROM agents;` → **0**, sem mudança | 🔴 — rodar o §8a (aguardando o Everton) |
| 2 | **`avgPrice`** disponível para os mercados executáveis | universo monitorado cresceu de 15 para **18/18** SPOT com `applyMinToMarket=true`/`avgPriceMins=5`; `avg_price.py` confirmado dentro da imagem em execução do `execution-worker` (`hunter-api:d21a11d`, `hunter_execution_worker/avg_price.py`, no ar desde 2026-09-09T15:20:52Z, 0 erros/avisos de `avg_price_*` nas últimas 500 linhas de log) | 🟢 — implantado e rodando; sem exercício real de admissão ainda porque `paper_autonomy=false` (linha 7) |
| 3 | **β válido** para algum mercado com sinal | **16 de 200** revisões vigentes válidas (perpétuos: ARB, BNB, BTC, DASH, DOGE, ETH, LINK, NEAR, PROM, SAHARA, SOL, SUI, TAO, UNI, XRP, ZEC) — os 16 mercados do backfill de 90 dias (T3.62); no funil real de `momentum v3`/24 h: **366 sinais, 51 passam `d1` (liquidez), 23 passam `d1`+β** (era 171/22/0 em 08/09). Dos 18 mercados SPOT monitorados, **12** têm β válido (ARB, BNB, BTC, DOGE, ETH, NEAR, PROM, SOL, SUI, UNI, XRP, ZEC); **6** ainda não (HOLO, IOST, MARSCOIN, PUMP, USD1, USDC — listagens mais novas, sem 20 dias contíguos de perpétuo) | 🟡 — melhora real (T3.62 fechou a causa-raiz do BTC), mas ainda não é toda a linha 3; falta backfill dos 6 restantes |
| 4 | **Qualidade das marcas** (`mark_quality`) publicada e barrando admissão | `hb:execution:paper.mark_quality = 1` (carteira sem posição); campo em produção desde o deploy de T3.29 | 🟢 |
| 5 | **Backup restaurável** | rehearsal real de restore executado nesta rodada (ver §restore abaixo): `pg_restore -j 2` do dump `hunter-20260910T011701Z.dump` (1,09 G) num banco descartável `hunter_restore_check`, **0 erros**, contagens batendo com o banco vivo | 🟢 — linha fechada |
| 6 | **MTM vivo** | `hb:execution:paper`: `ts=2026-09-10T03:32:45Z`, `last_mtm=03:32:00Z` (~46 s antes); equity 19.333,0111164813 USDT (sem mudança — carteira sem posição); kill switch `ACTIVE` | 🟢 |
| 7 | **`paper_autonomy` desligado até aqui** | `hb:execution:paper.paper_autonomy = false` | 🟢 (é o estado correto antes do aceite) |
| 8 | **Perfil de risco persistido** (`RISK_ENGINE.md` §2) | `portfolios.risk_profile_id` continua **NULL**; `risk_profiles` tem **4** linhas mas nenhuma com `preset='paper_v1'` (`SELECT count(*) FROM risk_profiles WHERE preset='paper_v1'` → 0). Sem mudança desde 08/09 | 🟡 — **procedimento pronto (T3.69, §8b): dois comandos, nenhum limite muda de valor**; falta o orquestrador rodá-los na VPS |

**Consultas, verbatim.** As duas que decidem as linhas 2 e 3:

```sql
-- linha 2: quantos mercados executáveis exigem avgPrice
SELECT symbol,
       (metadata->'spot_market_filters'->>'apply_min_to_market')::bool AS min_mkt,
       metadata->'spot_market_filters'->>'avg_price_mins' AS avg_mins
  FROM markets
 WHERE market_type='spot' AND status='active' AND delisted_at IS NULL AND is_monitored;
-- 08/09: 15 linhas, todas min_mkt=t e avg_mins=5
-- 10/09: 18 linhas, todas min_mkt=t e avg_mins=5 (universo monitorado cresceu)

-- linhas 2 e 3: o funil real de momentum v3 nas ultimas 24 h
WITH sig AS (
  SELECT s.id, sp.is_monitored, sp.volume_24h_usd, b.valid AS beta_valida
    FROM agent_signals s
    JOIN markets pm ON pm.id = s.market_id
    LEFT JOIN markets sp ON sp.market_type='spot' AND sp.exchange_id=pm.exchange_id
         AND sp.base_asset_id=pm.base_asset_id AND sp.quote_asset_id=pm.quote_asset_id
         AND sp.status='active' AND sp.delisted_at IS NULL
    LEFT JOIN LATERAL (SELECT valid FROM market_betas
                        WHERE market_id=pm.id AND valid_until>now()
                        ORDER BY window_end DESC LIMIT 1) b ON true
   WHERE s.strategy_version_id='02751faa-b2ee-4dc6-95a0-67967f7dfb88'
     AND s.emitted_at >= now() - interval '24 hours')
SELECT count(*) AS sinais,
       count(*) FILTER (WHERE is_monitored AND volume_24h_usd>=50000000) AS d1_ok,
       count(*) FILTER (WHERE is_monitored AND volume_24h_usd>=50000000 AND beta_valida) AS d1_e_beta_ok
  FROM sig;
--  sinais | d1_ok | d1_e_beta_ok
-- 08/09:  171 |    22 |            0
-- 10/09:  366 |    51 |           23   (16/200 β válidos, os do backfill T3.62)
```

**Leitura honesta do resultado — 08/09.** Mesmo com o vínculo `agents` criado
e com o `avgPrice` implantado, **nenhum** dos 171 sinais das últimas 24 h teria
virado ordem: o `beta_validity` recusava todos menos BTCUSDT, e BTCUSDT não
emitiu sinal `momentum v3` na janela.

**Leitura honesta do resultado — 10/09.** Com o backfill de 90 dias das 16
séries de referência (T3.62) concluído, o β passou a validar 12 dos 18
mercados SPOT monitorados (faltam HOLO, IOST, MARSCOIN, PUMP, USD1, USDC —
listagens recentes sem histórico contíguo suficiente de perpétuo) e **23 dos
366** sinais de 24 h já passariam `d1`+`beta_validity`. A linha 3 deixou de
ser um bloqueio total e virou parcial: ainda não é "toda a linha verde", mas a
causa-raiz do BTC identificada em 08/09 está fechada. Isso continua sendo a
regra do Everton funcionando (§6 do contrato: "sem beta validado, manter o
ativo apenas em shadow"), não um defeito.

**Nota operacional — as três pré-checagens que adiam uma entrada (T3.29/T3.29b,
regras escritas em `docs/RISK_ENGINE.md` §7.1).** Depois de virar a flag, "a
carteira não entrou em nada" tem causas diferentes e cada uma tem nome próprio
no log (`entry_deferred`/`bridge_candidate_deferred`) e no motivo gravado quando
a reserva de 30 s expira. Nenhuma delas recusa: adiam, nada é escrito, e o
candidato é lido de novo no segundo seguinte.

| Nome no log | O que aconteceu | O que o operador faz |
|---|---|---|
| `avg_price_not_collected` | o worker subiu sem o leitor de `avgPrice` ligado | conferir o deploy (é o que a linha 2 desta tabela mede) |
| `avg_price_unavailable` | o endpoint respondeu erro, ou preço não positivo, e não há cotação dentro do limite duro | olhar o log `avg_price_fetch_failed` e o orçamento de peso da Binance |
| `avg_price_stale` | a última cotação passou dos **30 s** (a vida da reserva) | mesmo caminho acima; se persistir, é rede ou rate limit |
| `avg_price_clock_skew` | o carimbo está **mais de 2 s à frente** do `now` do ciclo | é relógio, não mercado: conferir NTP do host. A métrica `hunter_execution_avg_price_clock_skew_total{outcome="refused"}` deve ficar em zero; `outcome="tolerated"` sobe de propósito, ~1 por janela de reuso por mercado |
| `avg_price_undated` | veio preço sem carimbo — um insumo sem idade não é insumo (§7) | não deve ocorrer com o leitor real; se ocorrer, é bug e não configuração |
| `marks_incomplete` | `mark_quality < 1`: alguma posição aberta não pôde ser marcada a preço vivo neste passo | ver `hb:execution:paper.mark_quality` e a fita do mercado da posição. **Uma única posição ilíquida adia todas as admissões novas daquela carteira até as marcas voltarem** — é o comportamento correto (sem saber o que já tem, a carteira não dimensiona entrada nova) e se resolve sozinho no passo em que a fita volta |
| `hot_state_unreachable` | o Redis do estado quente não pôde ser **lido** (diferente de "vazio") | é incidente de infraestrutura, não de mercado: olhar o Redis, não a exchange |

**As saídas de proteção não são afetadas por nenhuma delas** (regra 3 da
diretiva): stop, alvo e fechamento manual continuam correndo com a carteira
inteira sem marca, com o Redis fora e sem `avgPrice`.

**Sobre o restore (linha 5) — 08/09.** Naquela rodada a VPS foi tratada como
**somente leitura**: `pg_restore --list` foi executado sobre o dump mais
recente (1730 entradas, tabelas do ledger presentes), e **nenhum** banco foi
criado — a instrução daquela tarefa era não escrever nada na VPS. O restore
real ficou pendente.

**Restore real — 10/09 (T3.71), rehearsal completo.** Banco descartável
`hunter_restore_check` criado em `hunter-postgres-1` às 03:38:57Z; dump mais
novo (`hunter-20260910T011701Z.dump`, 1,09 G, gerado 03:20Z do mesmo dia)
copiado para dentro do container (`docker cp`, 4,1 s) e restaurado com
`pg_restore -U hunter -d hunter_restore_check --no-owner --no-privileges -j 2`.
Restore terminou **sem nenhum erro** (log completo, 4990 linhas) em
**~6 min** (lançado 03:39:21Z, processos encerrados ~03:45:25Z); banco
restaurado ocupou 6,4 G no disco. Wall-clock total do rehearsal (criar → medir
→ derrubar): **~8 min**. Contagens no banco restaurado batem com o banco vivo
(lido em transação `repeatable read read only`, sem escrever nada):
`portfolios` 1=1, `agents` 0=0, `risk_profiles` 4=4, `orders` 0=0, `fills`
0=0, `positions` 0=0, `trades` 0=0, `strategy_versions` 40=40,
`kill_switch_transitions` 0=0; `market_betas` 9.200 (restaurado) vs 9.600
(vivo) e `candles_1m` 5.248.305 vs 5.384.882 — as duas diferenças batem
exatamente com o intervalo de ~2h30 entre o instante do dump (01:20Z) e a
leitura do vivo (03:46Z): β roda de hora em hora (~400 linhas/execução) e
candles entram a cada minuto por mercado. `\dp` em `orders` e `positions`
mostrou a política `tenant_isolation` restaurada e ativa em ambas
(`organization_id = current_setting('app.current_org')`, `USING`/`CHECK`
idênticos ao vivo); a *role* `hunter_runtime` existe no cluster (roles são
globais, não por banco) — como o restore usou `--no-privileges`, os `GRANT`
para `hunter_runtime` **não** foram reaplicados nesse banco descartável
(esperado e correto para uma checagem de integridade de dados; um restore de
produção real precisaria reconceder os grants ou rodar sem `--no-privileges`).
Banco `hunter_restore_check` e o arquivo `/tmp/restore_check.dump` dentro do
container foram removidos ao final (`dropdb` + `rm`); disco da VPS antes/depois
do rehearsal: 62%→65% usado, 133 G→124 G livres (a alta é o dump de 1,09 G
que já existia em `/opt/backups` desde 03:20Z, não o rehearsal, que limpou
depois de si). **Linha 5 fechada**: dado restaurável e restaurado de verdade.

## 8b. Perfil de risco persistido: semear `paper_v1` e apontar a carteira (T3.69, linha 8)

**Nenhum limite muda de valor neste passo.** Os dois comandos abaixo persistem
exatamente os números que já estão em vigor — a linha semeada é
`hunter_risk.limits.PAPER_V1.model_dump(mode="json")` por construção
(`infra/scripts/seed_risk_reference.py`: `PAPER_V1_LIMITS = PAPER_V1.model_dump(...)`,
uma fonte, nunca duas). A diretiva do Everton ("documente e me apresente antes de
alterar os limites") vale para **valores**, e aqui nenhum valor muda. Prova
automatizada: `infra/scripts/tests/test_link_portfolio_risk_profile.py` semeia a
linha num Postgres real, lê o `jsonb` de volta e compara campo a campo com
`PAPER_V1` (frações são **strings** JSON, nunca números — `RiskModel` recusa
`float` na construção), e
`packages/core/tests/integration/test_schema_paper.py::test_the_seeded_paper_profile_has_exactly_one_source`
compara os bytes serializados do seed e do motor.

**Quem grava `portfolios.risk_profile_id` hoje: ninguém.** A auditoria da T3.69
percorreu todos os escritores. `apps/api/hunter_api/services/organizations.py`
grava `default_risk_profile_id` no **workspace** (uma cópia do preset `balanced`
para a org) — outra coluna, outra tabela;
`hunter_core.portfolio.opening.open_paper_wallet` **aceita** `risk_profile_id` e
todo chamador de produção (inclusive `infra/scripts/open_paper_wallet.py`, que
nem tem a flag) deixa em `None`. Por isso a carteira da VPS está NULL: não é
regressão, é uma coluna que nenhum caminho preenche. Daí o script novo,
`infra/scripts/link_portfolio_risk_profile.py`.

**Fonte declarada × fonte aplicada — dito, não escondido (residual T3.69b).**
O motor **não** lê o perfil da carteira hoje: `hunter_core.admission.admit`
recebe `limits: RiskLimits = PAPER_V1` e o `admission_cycle` do
`execution-worker` nunca passa o argumento, então quem decide é a **constante do
código**. A linha do banco é a fonte **declarada** (`RISK_ENGINE.md` §2, e o que
a API mostra em `/risk-limits` com `source='risk_profile'` em vez de
`engine_default`); a constante é a fonte **aplicada**. As duas são provadamente
iguais pelos testes acima, e o próprio script recusa o vínculo se a linha
divergir de `PAPER_V1` em qualquer campo. Fazer `admit` ler o perfil da carteira
é a **T3.69b** e não foi feito aqui.

**Os dois comandos, pelo serviço `ops`** (T3.15d — a imagem implantada, com o
DSN de dono; `compose.sh ops` recusa rodar se a imagem do `GIT_SHA` não existir
na máquina):

```
# 1. semear a linha risk_profiles.paper_v1 (mostra o que inseriria, depois insere)
bash infra/vps/compose.sh ops python infra/scripts/seed.py --only risk_profiles --dry-run
bash infra/vps/compose.sh ops python infra/scripts/seed.py --only risk_profiles --yes

# 2. apontar a carteira paper principal para ela
bash infra/vps/compose.sh ops python infra/scripts/link_portfolio_risk_profile.py \
    --portfolio 01a07a1e-f6ae-7366-a7fe-ab3d9c83d488 --preset paper_v1 --dry-run
bash infra/vps/compose.sh ops python infra/scripts/link_portfolio_risk_profile.py \
    --portfolio 01a07a1e-f6ae-7366-a7fe-ab3d9c83d488 --preset paper_v1 --yes \
    --actor <email ou identificação de quem pediu>
```

O `--dry-run` do passo 1 imprime uma linha `risk_profiles.paper_v1: NEW {...}`
com o perfil inteiro (medido localmente contra um banco que espelha a VPS —
4 linhas, sem `paper_v1`):

```
risk_profiles.paper_v1: NEW {'organization_id': None, 'name': 'Paper v1', 'preset': 'paper_v1',
 'limits': {'profile': 'paper_v1', 'day_timezone': 'America/Sao_Paulo', 'max_leverage': '1',
 'max_beta_age_s': 7200, 'max_book_age_s': 10, 'max_spread_pct': '0.0005', 'max_price_age_s': 10,
 'max_slippage_pct': '0.001', 'max_volume_age_s': 120, 'risk_per_trade_pct': '0.0025',
 'kill_switch_blocked': {'drawdown_pct': '0.08', 'daily_loss_pct': '0.02'},
 'kill_switch_warning': {'drawdown_pct': '0.04', 'daily_loss_pct': '0.01'},
 'max_beta_btc_exposure': '0.50', 'max_participation_pct': '0.01', 'max_stop_distance_pct': '0.03',
 'min_liquidity_usd_24h': '50000000', 'min_stop_distance_pct': '0.003',
 'max_asset_exposure_pct': '0.10', 'max_total_exposure_pct': '0.40', 'participation_window_s': 60,
 'max_entry_deviation_pct': '0.005', 'warning_size_multiplier': '0.5',
 'max_concurrent_positions': 5, 'max_aggregate_planned_risk_pct': '0.01'}, 'created_by': None}
```

Conferir esses números contra a tabela de `docs/RISK_ENGINE.md` §2 **antes** de
rodar o `--yes` é o passo de apresentação; se algum diferir, **não** rode o
`--yes` e volte ao Everton.

**O que cada recusa quer dizer** (todas com saída ≠ 0 e nada escrito):

| Recusa | Causa | O que fazer |
|---|---|---|
| `there is no system risk_profiles row with preset 'paper_v1'` | o passo 1 não rodou | rodar o passo 1 |
| `the stored paper_v1 limits differ from hunter_risk.limits.PAPER_V1 on: <campos>` | a linha do banco não é o objeto do motor | **parar** — é mudança de limite feita por ninguém; reconciliar deliberadamente e apresentar ao Everton |
| `already points at risk_profile <outro>` | a carteira já aponta para outro perfil | só com `--replace`, e só se mover for deliberado |
| `no portfolio <uuid> is visible to this connection` | id errado, ou DSN sem privilégio (`portfolios` é `FORCE ROW LEVEL SECURITY`) | conferir o uuid e que é o `ops` (DSN de dono) |
| `is type=<x>`/`is_arena` | não é a carteira paper principal | conferir o uuid |

Rodar o passo 2 de novo depois de pronto imprime `already points at paper_v1
(...); nothing to do` e **não** escreve uma segunda linha de auditoria.

**Verificação, somente leitura** (`docker exec hunter-postgres-1 psql -U hunter -d hunter`):

```sql
SELECT p.id                AS carteira,
       p.name,
       rp.preset::text     AS preset,
       rp.limits->>'risk_per_trade_pct'    AS risco_por_trade,
       rp.limits->>'max_total_exposure_pct' AS exposicao_total,
       rp.limits->>'max_concurrent_positions' AS vagas
  FROM portfolios p
  LEFT JOIN risk_profiles rp ON rp.id = p.risk_profile_id
 WHERE p.type = 'paper' AND NOT p.is_arena;
-- verde: preset = paper_v1, risco_por_trade = 0.0025, exposicao_total = 0.40, vagas = 5

SELECT action, actor_type, before, after, metadata->>'actor_input' AS quem
  FROM audit_logs
 WHERE action = 'portfolio.risk_profile_linked'
 ORDER BY created_at DESC LIMIT 5;
-- uma linha por vínculo escrito, na mesma transação do UPDATE
```

## 7. Derivar uma variante de pesquisa na VPS (T3.26 / T3.26c)

Uma **variante** é uma versão nova com um ou mais parâmetros mudados e o mesmo código: `derive_variant.py` copia o conjunto congelado do pai, aplica o `--set`, e grava um rascunho `research_only` (`activated_at = NULL`). **Nada é ativado nesse passo.** É o caminho da EXP-0006 (`momentum v4`, piso de custo, KB-0008).

**A imagem precisa ser deste commit (T3.26c) ou posterior.** Duas razões, e as duas são de perder experimento:

- o script importa `hunter_core.strategies.constraints`, que só existe a partir daqui — numa imagem antiga ele nem carrega (`ModuleNotFoundError`), o que é a falha barulhenta e portanto a boa;
- o **script da imagem** anterior a `be3674a` reconhecia uma linha derivada só pela frase `paper line of`, então ativar uma variante com ele caía na rota de pesquisa e reescrevia `default_parameters` a partir do código de hoje, apagando o override em silêncio. A T3.26c fechou isso de forma estrutural (a rota de pesquisa recusa um rascunho que já tem conjunto próprio), mas a trava só existe **na imagem nova**.

Confira a imagem antes de qualquer coisa:

```
ssh hunter-vps "docker exec hunter-api-1 python -c \"import hunter_core.strategies.constraints as c; print(c.__file__)\""
```

Sem saída ou com `ModuleNotFoundError`: **pare** e faça o deploy antes (`compose.sh update`).

**Derivar** (T3.15d: pelo serviço `ops`, não mais `docker exec hunter-api-1` — esse
container não carrega mais `DATABASE_URL_MIGRATIONS`, DEPLOYMENT.md §3.4). O
**caminho canônico** é o script *da imagem* — `Dockerfile.api-workers` faz
`COPY infra/scripts infra/scripts`, então qualquer imagem já implantada
(`compose.sh update` já rodou depois do commit que trouxe/alterou o script)
já o tem:

```
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh run --rm ops python infra/scripts/derive_variant.py momentum v2 --set atr_pct_min=0.0089 --changelog 'KB-0008: piso de custo' --dry-run"
```

**Fallback por stdin (T3.15e, MEDIUM)** — só quando o script é novo/mudou num
commit que ainda não foi implantado (a checagem de imagem acima já teria
mandado parar e fazer o deploy antes; isto é para quem precisa testar *antes*
de decidir se vale um deploy). `python -` lê o script da entrada padrão, e os
argumentos vêm depois do `-`; `-T` desliga o pseudo-TTY do `ssh` para o stdin
do `<` chegar ao `docker compose run` sem ficar preso. **O que roda aqui é o
arquivo local da máquina que digita o `ssh`** — não o do repositório na VPS,
não o da imagem — porque o `<` é resolvido pelo shell local antes do `ssh`
sequer abrir a conexão. Um checkout com edições não commitadas, ou num commit
diferente do que a VPS tem, roda exatamente esse conteúdo divergente contra o
banco de produção sem nenhum rastro em `git log`. Confira o hash antes de
mandar (e cole o hash no `--changelog`, para o `system_events` guardar qual
versão do script realmente rodou):

```
git status --short infra/scripts/derive_variant.py   # vazio: sem edição não commitada
git rev-parse HEAD:infra/scripts/derive_variant.py   # o blob que vai rodar

ssh -T hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh run --rm -T ops python - momentum v2 --set atr_pct_min=0.0089 --changelog 'KB-0008: piso de custo (blob <hash acima>)' --dry-run" < infra/scripts/derive_variant.py
```

O `--dry-run` roda **todas** as recusas e não escreve nada; a saída nomeia a versão que nasceria, o que se moveu e o `params_hash`. Repita sem `--dry-run` para gravar. Toda corrida — sucesso, recusa ou erro — deixa linha em `system_events` (componente `activate_strategy_version`).

O que ele recusa, antes de qualquer escrita: migração ausente, pai inexistente, pai nunca ativado, pai que não é `research_only`, `code_ref` que este build não reproduz, parâmetro fora do schema congelado, valor que não valida, **valor fora da faixa declarada** (negativo onde o pai é positivo, piso ≥ teto, `AssumedCosts`/geometria que não instanciam — T3.26c/A2) e um conjunto que já existe no mesmo `code_ref`.

**Ativar a variante** (corrida separada e auditada, com o script *da imagem* — que agora reconhece a linha derivada e preserva o conteúdo dela):

```
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh run --rm ops python infra/scripts/activate_strategy_version.py momentum v4 --changelog T3.26_variante_KB-0008_ativada_por_Everton"
```

Sem aspas internas, por causa do PowerShell. Se aparecer `REFUSED: ... already carries its own default_parameters`, a imagem está **atrás** da T3.26c: faça o deploy e repita — não contorne editando o `changelog`.

## 7b. Aposentar uma versão substituída por parâmetro (`--deprecate`, T3.39)

> **Latência do roster (medida na T3.56, 2026-09-09):** o `strategy-worker` recarrega o roster a cada `SHADOW_VERSION_REFRESH_S` (60 s), então uma versão pode emitir decisões por até um minuto depois de `deprecated_at` — `emitted_at > deprecated_at` nessa janela não é vazamento. Os acompanhamentos abertos continuam até o desfecho (o loader não filtra por versão); aposentar para a decisão nova, não a operação em voo. A linha `paper` só aposenta com zero slots-sombra abertos (portão do script), o que exige apanhar a janela ou mover a linha `paper` antes.

`--supersede` só existe para uma sucessora de **código**: quando o `code_ref`
já bate (uma variante por parâmetro, `derive_variant.py`), ele recusa de
propósito ("already frozen against this code"). Até a T3.39 não havia via
auditada para aposentar essa versão — nem uma sem sucessora nenhuma (K1: 0
decisões, `breakout v1`; recomendação descartar, `breakout v2`). `--deprecate`
é essa via: um `UPDATE status = 'deprecated'` (o único campo que a trigger de
congelamento deixa mutável, DATABASE.md §16.1), com o mesmo padrão de
auditoria em `system_events` — motivo, sucessora (se `--successor v<n>` for
dado) e o `code_ref`/`params_hash` congelados da versão.

**Recusas estruturais, não configuráveis** — e **as mesmas em `--supersede`**
(revisão T3.39b, ALTA-2: um escritor que move uma versão congelada para fora de
`active` não pode ser mais frouxo que o outro):
- `purpose = 'live'`: nunca aposentada nem sucedida por este script (Fase 4,
  `ENABLE_LIVE_TRADING=false`);
- `purpose = 'paper'` (a linha da carteira): exige `--force-paper` **e** nenhuma
  posição aberta nem slot de shadow em rastreamento
  (`shadow_episodes.open_outcome_signal_id`) — a diretriz do
  risk-engine-guardian para esta tarefa: "uma versão sendo aposentada nunca
  pode ser a linha paper com posições abertas". A checagem de posições segue o
  caminho real de produção (revisão T3.39b, ALTA-1) — `positions.metadata->>
  'proposal_id' -> orders.proposal_id -> trade_proposals.agent_id ->
  agents.strategy_version_id` — porque `positions.agent_id` nunca é escrito
  pelo execution-worker; e `--supersede` copia `purpose` explicitamente para a
  sucessora (ALTA-2), então uma linha paper superada continua paper, nunca cai
  no padrão `research_only` do schema.

**`changelog` é acrescentado, nunca sobrescrito (T3.47c).** O prefixo de
linhagem que `derive_variant.py` grava (`variante de v<n> | derived_from=v<n>
| overrides=... | params_hash=...`) — o mesmo que
`infra/scripts/obsidian_strategy_pages.py` lê para ligar a página da variante à
do pai — mora só nessa coluna; nenhuma outra guarda a linhagem. Até esta
tarefa `--deprecate` (e `--supersede`, na linha que ele aposenta) faziam
`changelog = :veredito`, apagando esse prefixo sempre que a versão aposentada
era uma variante (achado da T3.47b, CONCERN 3). Agora os dois passam pelo
mesmo `append_deprecation_note` (`hunter_strategy_worker.activation_db`): o
valor anterior sobrevive **byte a byte**, com uma linha datada acrescentada no
fim — `\n[deprecated <UTC iso>] <veredito>` — então uma variante aposentada
continua encontrável pelo pai e o veredito de por que foi aposentada fica
junto, não no lugar.

O roster do strategy-worker (`load_version_roster`) já filtra por
`status = 'active'`, mas o recarregamento tem um TTL de 60 s
(`ShadowConfig.version_refresh_s`, `SHADOW_VERSION_REFRESH_S`) — uma versão
recém-aposentada ou superada pode continuar avaliando por até um minuto antes
de sumir do roster do worker em execução.

```
uv run python infra/scripts/activate_strategy_version.py breakout v1 --deprecate \
    --changelog "K1: 0 decisões, custo de 200 avaliações/15min sem sinal" --dry-run
uv run python infra/scripts/activate_strategy_version.py breakout v2 --deprecate \
    --changelog "K1: descartar — bruta +0,01R líquida -0,08R em 8 decisões" --dry-run
```

Sem `--dry-run` para gravar. Na VPS, o mesmo comando pelo serviço `ops`
(T3.15d, DEPLOYMENT.md §3.4 — `docker exec hunter-api-1` não serve mais para
isto, o container não carrega `DATABASE_URL_MIGRATIONS`):
`bash infra/vps/compose.sh run --rm ops python infra/scripts/activate_strategy_version.py breakout v1 --deprecate --changelog "..."`.

## 7c. Derivar uma variante que só muda o **portão de regime** (`--policy`, T3.52)

Desde a `0017_eligibility_policy` uma versão pode declarar **em que contexto ela
tem permissão de decidir**: `strategy_versions.eligibility_policy`, congelada pela
primeira ativação como `default_parameters` e `purpose` (DATABASE.md §29). O
`strategy-worker` lê a série horária de regime (`market_regimes`, `scope = 'btc'`,
`classifier_version = 'regime_hourly_v1'`) na **última hora fechada antes do corte**
e, se o rótulo não estiver na lista, a versão não decide aquela barra — sai
`ineligible` com `eligibility_reason = regime_gate:<RÓTULO>`, sem re-armar o slot
(PIPELINE.md §4b item 10).

```
# mean_reversion só em lateral; nenhum parâmetro muda
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh run --rm ops python infra/scripts/derive_variant.py mean_reversion v6 --policy regime=btc:SIDEWAYS --changelog T3.52_regime_gate_lateral --dry-run"

# momentum só em alta
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh run --rm ops python infra/scripts/derive_variant.py momentum v8 --policy regime=btc:BTC_BULL --changelog T3.52_regime_gate_alta --dry-run"
```

Repita sem `--dry-run` para gravar e ative com o mesmo
`activate_strategy_version.py` da §7 (a variante carrega conteúdo próprio, então a
rota derivada é a que roda; o `--purpose` continua `research_only`).

O que muda em relação à §7, e vale saber antes de digitar:

- **`--policy` sozinho basta.** Uma variante que só move o portão **não** muda
  nenhum parâmetro: ela nasce com o *mesmo* `params_hash` do pai, de propósito, e
  a checagem de duplicata passa a comparar `code_ref` + `params_hash` + **portão**.
  Duas linhas com o mesmo conjunto e portões diferentes são dois experimentos;
  com o mesmo portão, seriam o mesmo contado duas vezes (e aí ele recusa).
- **Sem `--policy`, a variante herda o portão do pai** — como herda o schema, os
  parâmetros e o `code_ref`. Para tirá-lo, `--policy none` (que recusa quando o
  pai já não tem portão: um comando que não faz nada não deve parecer que fez).
- **Gramática:** `regime=<escopo>:<RÓTULO>[,<RÓTULO>…]`, escopo `btc` ou `global`,
  rótulos de `MarketRegime` (`SIDEWAYS`, `BTC_BULL`, `BTC_BEAR`, …). Recusa
  rótulo inexistente, lista vazia e **`UNKNOWN`** — deixar uma versão decidir no
  aquecimento do classificador é decidir sem contexto e chamar isso de contexto.
  Quem valida é a mesma função que o worker usa para ler a coluna, não uma cópia.
- **A linhagem carrega o portão:** o `changelog` congelado vira
  `variante de v6 | derived_from=v6 | overrides= | params_hash=<12 hex> | policy=btc:SIDEWAYS | <o motivo>`,
  e o segmento `policy=` sobrevive à ativação (sem ele, a linhagem de uma variante
  sem `--set` diria que nada mudou).
- **A imagem precisa ser deste commit (T3.52) ou posterior** e o banco precisa da
  `0017` aplicada — o `compose.sh update` roda `alembic upgrade head` antes de
  subir os serviços, e o `strategy-worker` **recusa iniciar** sem a coluna (é o que
  `migration_present` passou a exigir). O script recusa antes de escrever qualquer
  coisa: `0017_eligibility_policy não está aplicada`.
- **O que esperar da população:** um portão só remove **barras** — e isso **não**
  faz a filha ser um subconjunto das *decisões* do pai (T3.52d, PIPELINE §4b item
  11: `INELIGIBLE` não re-arma o slot, então a máquina de estados da filha evolui
  diferente e ela pode abrir episódio numa barra que o pai nunca considerou).
  Compare pareado por **(mercado, barra)** sobre as barras elegíveis
  compartilhadas (`t342-blocos/blocos.py`), nunca por decisão e nunca por médias
  soltas. Hoje 27 % das horas dos últimos 31 dias saem `UNKNOWN` (aquecimento do
  classificador, PIPELINE §4b item 5) e **essas horas também são removidas**,
  junto com as horas do rótulo recusado.

### A janela de horas (`hours=`, T3.59)

A segunda regra do mesmo envelope: `--policy hours=12-15` prende a versão às
barras que **fecham** entre 12:00 e 14:59:59 **UTC** (09:00–11:59 BRT) — janela
meia-aberta, uma ou mais por política (`hours=12-15+22-02`, que vira a
meia-noite), e é a hora da *decisão*, não a hora de onde o dado veio (uma barra
de 15 min que fecha às 12:00 resume 11:45–12:00 e é a primeira barra elegível da
janela). O motivo da recusa é `hours_gate:HH` com a hora em dois dígitos. Cinco
coisas que valem saber antes de digitar:

- **As regras são `AND` e a hora vem primeiro.** `--policy
  regime=btc:BTC_BULL,hours=12-15` grava as duas e a barra só decide se passar
  nas duas; a vírgula separa regras **e** rótulos, e quem as distingue é o `=`.
  A hora é avaliada antes porque não lê nada — logo uma barra fora da janela nem
  chega a custar a consulta do regime, e uma barra que falharia nas duas é
  reportada como `hours_gate:HH`.
- **Um `--policy` que não mencione uma regra do pai é recusado.** Escrever
  `--policy hours=12-15` sobre um pai com portão de regime tiraria o regime em
  silêncio e faria a filha decidir em **mais** contexto que o pai, que é a única
  direção perigosa. Repita a regra, ou escreva `regime=none` para tirá-la de
  propósito (`--policy none` continua tirando o portão inteiro).
- **A janela não pode cobrir o dia todo** (`0-24`, ou duas janelas que somem 24 h)
  nem se sobrepor a si mesma: um portão que nunca recusa é um portão em que
  alguém acredita e que não existe, e o script recusa antes de escrever.
- **Não há antecipação a defender aqui**, e é a diferença desta regra para a do
  regime: a hora de fechamento é propriedade da barra, então não há série que
  atrase, linha que envelheça nem relógio que ande — a mesma barra dá o mesmo
  veredito no replay e na faixa viva, hoje e daqui a um mês.
- **A perda de população é aritmética, não estatística:** `12-15` deixa passar
  3 das 24 horas, ou seja 12,5 % das **barras** do pai (contra os 30,8 % que o
  portão de regime deixou passar na T3.52d §3). Em decisões, o rateio uniforme
  de uma coorte de 184 daria ~23 em 31 dias — a hora 12 sozinha rendeu 16 na
  coorte de `momentum v10` (T3.54 §5), então pode ser mais; e uma versão que
  **some** janela ao portão de regime cai para a interseção das duas, que pode
  não chegar a dez. É por isso que a EXP-0023 pré-registra `n ≥ 30` como porta
  antes de qualquer leitura.

```
# a variante da EXP-0023 (janela pré-registrada; --dry-run primeiro, sempre)
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh run --rm ops python infra/scripts/derive_variant.py mean_reversion v10 --policy hours=12-15 --changelog EXP-0023_janela_12_15_UTC --dry-run"

# a irmã que mantém o portão de regime do pai — as duas regras, nomeadas
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh run --rm ops python infra/scripts/derive_variant.py momentum v11 --policy regime=btc:BTC_BULL,HIGH_VOLATILITY,hours=12-15 --changelog EXP-0023_janela_12_15_UTC --dry-run"
```

## O que continua igual depois do passo 8
- Só ordens a mercado, só SPOT, sem alavancagem; fill pelo livro elegível após a latência declarada; sem fill fabricado.
- Risco 0,25 % por operação incluindo custos, soma ≤ 1 %, participação ≤ 1 % do minuto, β-BTC ≤ 0,5×, total ≤ 40 %, por moeda ≤ 10 %, máx. 5 posições, pendentes contam.
- Kill switch AVISO/BLOQUEADO como na diretiva; BLOQUEADO só sai com o Everton (OWNER).
- Uma proposta por ciclo (D3), `research_only` nunca vira ordem, `live` recusado por nome, `ENABLE_LIVE_TRADING=false`.

## Como desligar
`ENABLE_PAPER_AUTONOMY=false` + `compose.sh update` para a ponte parar de consumir (posições abertas continuam protegidas pelo worker). Aposentar a própria linha paper é `activate_strategy_version.py <key> <version> --deprecate --force-paper` (§7b) — só depois de zerar posições e slots de shadow; a mesma trava (`--force-paper` + checagem limpa) vale para `--supersede <key> <version> --force-paper` quando o que muda é o código, não o status (revisão T3.39b, ALTA-2).

## 9. Re-seed seguro (`seed.py --dry-run` / `--only`, T3.39)

`seed.py` sem argumentos sempre fez tudo numa transação — inclusive
`risk_profiles`, cujos limites são a diretriz do Everton (RISK_ENGINE.md §2).
Duas lacunas fechadas nesta tarefa: não dava para reexecutar só a tabela
`strategies` (a chave `session_orb` está faltando na VPS; as descrições de
`breakout`/`mean_reversion` estão desatualizadas na tela do Lab), e não havia
como ver o que mudaria antes de escrever.

- `--dry-run`: roda todo escritor que a invocação rodaria, imprime o diff
  exato (`tabela.chave: campo: antigo -> novo`, ou `NEW` para uma linha nova) e
  desfaz a transação — nada é gravado.
- `--only exchanges|strategies|risk_profiles|feature_definitions|opportunity_weights`:
  restringe a transação a essa tabela só (`strategies` inclui
  `strategy_versions`, o rascunho `v1`; `risk_profiles` inclui `paper_v1`, como
  o `seed()` padrão já faz). `exchanges` entrou na T3.44c, quando a migração
  `0016` deu ao catálogo de exchanges o rótulo `planned` que o seed consegue de
  fato mover (DATABASE.md §28) — antes disso `seed_exchanges` não escrevia
  `status` e um re-seed dessa tabela não mudava nada do que uma linha guardada
  dizia.
- Sem `--only`, uma mudança nos limites de `risk_profiles` (qualquer um dos
  três presets ou `paper_v1`) recusa a gravação sem `--yes` — a diretriz:
  limite não muda sem ser apresentado antes. `--dry-run` é como se apresenta.

**Pendência do operador hoje** (VPS, pelo serviço `ops` — T3.15d, DEPLOYMENT.md
§3.4; `docker exec hunter-api-1` não serve mais para isto, o container não
carrega `DATABASE_URL_MIGRATIONS`):

```
bash infra/vps/compose.sh run --rm ops python infra/scripts/seed.py --only strategies --dry-run
bash infra/vps/compose.sh run --rm ops python infra/scripts/seed.py --only strategies
```

O primeiro comando mostra exatamente a linha nova (`strategies.session_orb: NEW
...`) e as descrições que mudariam; o segundo grava. Nenhum dos dois toca
`risk_profiles`, `feature_definitions` ou `opportunity_weights`.

**`--only risk_profiles`: a linha `paper_v1` e o vínculo da carteira (T3.69).**
O procedimento completo — os dois comandos, a saída do `--dry-run` verbatim, as
recusas e a consulta de verificação — está na **§8b**, porque é a linha 8 do
aceite. Em resumo, e sempre nesta ordem:

```
bash infra/vps/compose.sh ops python infra/scripts/seed.py --only risk_profiles --dry-run
bash infra/vps/compose.sh ops python infra/scripts/seed.py --only risk_profiles --yes
bash infra/vps/compose.sh ops python infra/scripts/link_portfolio_risk_profile.py \
    --portfolio 01a07a1e-f6ae-7366-a7fe-ab3d9c83d488 --preset paper_v1 --dry-run
bash infra/vps/compose.sh ops python infra/scripts/link_portfolio_risk_profile.py \
    --portfolio 01a07a1e-f6ae-7366-a7fe-ab3d9c83d488 --preset paper_v1 --yes --actor <quem>
```

`compose.sh ops <cmd>` e `compose.sh run --rm ops <cmd>` chegam no mesmo
container; prefira o primeiro — o subcomando `ops` recusa antes de rodar se a
imagem `hunter-api:${GIT_SHA}` não existir na máquina, e o `run` genérico
deixaria o Compose **construir** uma imagem de código nunca implantado
(revisão de segurança da T3.15e, achado F2). O `--yes` do `seed.py` é a
confirmação da diretriz de limites; como a linha `paper_v1` está **ausente** na
VPS, o que ele faz é um `INSERT` — nenhum valor guardado é reescrito, e se
algum dia a linha divergir do que o build carrega o próprio seed **para** com o
nome do campo divergente em vez de sobrescrever.

## Onde acompanhar
`/ever/portfolio` (patrimônio, kill switch, curva), `/ever/system` (worker, `autonomy`, pendências, proteções), `hb:execution:paper` no Redis, `obsidian/05-EXPERIMENTS/EXP-0005-momentum-paper.md`.

No `hb:execution:paper`, os campos que respondem "por que nada aconteceu":
`paper_autonomy` (a flag), `open_positions`/`marked_positions` e **`mark_quality`**
(fração das posições abertas marcadas a preço vivo — `1` numa carteira vazia;
abaixo de `1` a admissão é adiada com `marks_incomplete`), `last_mtm` (quando o
ponto foi escrito, que é outra pergunta), `degraded_protections` e
`protection_delay_s`.
