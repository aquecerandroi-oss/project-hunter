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

## 8c. O vínculo `agents` agora é um script (T4.72, 2026-09-19)

O SQL manual acima continua correto, mas de 2026-09-08 até hoje ninguém o
rodou: o time pivotou para o funil de memes (`foco-total-memes`, 16/09) com o
checklist do §8 parcialmente verde (linha 3, β, ainda amarela em 10/09 —
`.claude/state/notes-T3.71.md`) e a linha 1 (`agents`) nunca saiu de zero.
`equity=19333.0111164813`, `trade_proposals=0`, `trades=0` no `hb:execution:paper`
de 10/09 são exatamente os números de hoje: nada mudou porque ninguém rodou o
passo 8a, não porque o caminho tenha um defeito novo.

`infra/scripts/link_portfolio_agent.py` é esse passo, repetível e
pré-checado (mesmo padrão auditado de `link_portfolio_risk_profile.py`):
recusa uma versão que não seja `purpose=paper`/`status=active`, escreve
`allowed_directions=ARRAY['long']` sempre (a mesma razão do §8a: `paper_v1`
é SPOT sem alavancagem), e reativa em vez de duplicar se o agente já existir
pausado. Testes: `infra/scripts/tests/test_link_portfolio_agent.py`
(testcontainers, 10 casos: refusals de org/versão/status/purpose, dry-run,
criação, replay idempotente, reativação).

```
uv run python infra/scripts/link_portfolio_agent.py \
    --org-slug ever --strategy momentum --version v3 --dry-run
uv run python infra/scripts/link_portfolio_agent.py \
    --org-slug ever --strategy momentum --version v3 --yes --actor "Everton"
```

Na VPS, pelo serviço `ops` (T3.15d, DEPLOYMENT.md §3.4), depois do deploy que
traz este script para a imagem:

```
bash infra/vps/compose.sh run --rm ops python infra/scripts/link_portfolio_agent.py \
    --org-slug ever --strategy momentum --version v3 --dry-run
bash infra/vps/compose.sh run --rm ops python infra/scripts/link_portfolio_agent.py \
    --org-slug ever --strategy momentum --version v3 --yes --actor "Everton"
```

**Este script não decide qual versão linkar nem vira a flag.** A candidata com
histórico auditado é `momentum v3` (a mesma da [[EXP-0005-momentum-paper]],
D10) — único veredito até aqui é `inconclusivo` (30 outcomes/1 dia, abaixo do
limiar de 100/30 dias), não "positivo"; o script existe para o dia em que
Everton decidir ligar mesmo assim (aprender operando, `real-como-aprendizado`)
ou por uma versão com evidência melhor. Rodar o script não muda
`ENABLE_PAPER_AUTONOMY`, que continua um passo separado e seu (passo 8).

**Checklist do §8 — o que precisa ser remedido antes de virar a flag.** A
última medição real é de 2026-09-10 (T3.71); este agente não tem acesso SSH à
VPS (roda em sandbox local com testcontainers), então não pôde remedir as
linhas ao vivo — os números abaixo são o último estado conhecido, não um novo
`read_at`. Comandos exatos para o operador rodar de novo, na ordem do §8:

| # | Linha | Última medição (10/09) | Consulta para remedir |
|---|---|---|---|
| 1 | `agents` | 0 linhas | `SELECT count(*) FROM agents WHERE status='enabled';` (o script acima resolve) |
| 2 | `avgPrice` | 🟢 18/18 SPOT | `SELECT count(*) FROM markets WHERE market_type='spot' AND is_monitored AND (metadata->'spot_market_filters'->>'apply_min_to_market')::bool;` |
| 3 | β válido | 🟡 12/18 monitorados, 23/366 sinais 24h | consulta completa em §8, "linhas 2 e 3" — **provavelmente mudou em 9 dias sem acompanhamento**, remedir antes de decidir |
| 4 | `mark_quality` | 🟢 | `HGET hb:execution:paper mark_quality` |
| 5 | backup restaurável | 🟢 (rehearsal 10/09) | repetir o rehearsal do §8 se > 30 dias desde a última prova |
| 6 | MTM vivo | 🟢 | `HGETALL hb:execution:paper` (`ts`/`last_mtm` recentes) |
| 7 | `paper_autonomy=false` até aqui | 🟢 (correto) | `HGET hb:execution:paper paper_autonomy` |
| 8 | `risk_profile` persistido | 🟢 (`paper_v1` linkado, 10/09) | `SELECT rp.preset FROM portfolios p JOIN risk_profiles rp ON rp.id=p.risk_profile_id WHERE p.type='paper' AND NOT p.is_arena;` |

Vermelho real hoje: **linha 1** (script pronto, não rodado — ato do Everton) e
**linha 3**, que só a remedição ao vivo decide (o β depende do backfill/job
horário terem seguido rodando durante o pivô para memes, o que este agente não
pôde confirmar). Passo a passo completo para ligar de vez: `.claude/state/notes-T4.72.md`.

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
| 8 | **Perfil de risco persistido** (`RISK_ENGINE.md` §2) | **Medido em 2026-09-10 11:52 BRT (14:52Z), depois de o Everton rodar os dois comandos do §8b:** `risk_profiles` tem a linha global `preset='paper_v1'`; `portfolios.risk_profile_id` da *Carteira paper principal* aponta para ela; `audit_logs` tem `portfolio.risk_profile_linked` às 14:51:25Z; `hb:execution:paper.risk_profile = risk_profile_linked`. Histórico: em 08/09 e até 11:50 BRT de 10/09 a coluna era NULL e não havia `paper_v1` (a carteira admitia zero entradas por `risk_profile_missing`, T3.69b) | 🟢 — nenhum limite mudou de valor; o motor aplica a linha e a compara campo a campo com `PAPER_V1` |

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

**A partir da T3.69b estes dois comandos ligam a carteira, e antes deles ela não
admite nada — dito com todas as letras.** O `execution-worker` resolve os limites
da carteira a partir de `portfolios.risk_profile_id` a cada passo de admissão
(`hunter_execution_worker.risk_profile`) e recusa admitir enquanto não puder
confiar na linha, com o motivo no log e em `hb:execution:paper.risk_profile`:

| O que o Everton vê antes do §8b | O que ele vê depois |
|---|---|
| `risk_profile: risk_profile_missing` no heartbeat; nenhuma proposta nova, nem manual nem autônoma; `POST /order-requests` continua respondendo `202` e a solicitação fica **pendente**, sem decisão | `risk_profile: risk_profile_linked`; a admissão volta a decidir exatamente como antes, com **os mesmos números** — agora lidos da linha |

Nada disso afeta saída de proteção, MTM, kill switch ou a tela: stops e alvos de
qualquer posição aberta continuam correndo (regra 3 da diretiva). E a recusa é
reversível sem restart: no passo seguinte ao vínculo, a mesma carteira admite.

Dois outros motivos aparecem no mesmo campo quando a linha existe mas não serve:
`risk_profile_invalid` (não valida como `RiskLimits` — chave a mais, chave a
menos, fração gravada como número JSON) e `risk_profile_diverged` (valida, mas
difere de `hunter_risk.limits.PAPER_V1` campo a campo, e os campos vêm nomeados
no log). Nos dois casos o motor **não** adota a linha e **não** volta para a
constante: recusa. A tela do Risk Center mostra o mesmo fato em
`preset.diverged_from_engine`.

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

SELECT action, actor_type, before, after, metadata->>'actor_input' AS actor_input_nao_verificado
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

**Rodar o replay de validação da variante (T3.80).** Nunca por `docker exec
hunter-strategy-worker-1 ...` — em 10/09/2026 um replay rodado assim, dentro do
container do worker vivo, fez o atraso de decisão da linha viva subir de 26 s
para 90 s de mediana (p95 171 s) enquanto durou, competindo por CPU e pool de
banco com o processo que precisa ficar instantâneo. O serviço dedicado é
`replay-worker` (`docs/DEPLOYMENT.md` §5.2 tem o orçamento e o portão
completos):

```
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh replay python -m hunter_strategy_worker.replay.run --version momentum:v4 --from 2026-08-08 --to 2026-09-08 --markets all"
```

Pausa sozinho (motivo na saída) se a linha viva estiver degradada em qualquer
um dos eixos que o portão lê — heartbeat velho/ausente, `outbox_lag_s`, atraso
de decisão (`decision_lag_p50_s`/`_p95_s`, o eixo que a T3.80 fechou) ou
`consumer_lag` — e `replay/run.py` recusa de saída se `HUNTER_ROLE=strategy` estiver no
ambiente, então mesmo um `docker exec` no worker vivo por engano é recusado
com o motivo na tela, nunca aceito em silêncio.

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

### A amplitude do universo (`breadth=`, T3.77)

A terceira regra do mesmo envelope: `--policy breadth=0.10-0.60` prende a versão
às barras em que a fração das perpétuas monitoradas que **caíram nos 5 minutos
completos antes do fechamento** ficou entre 0,10 (inclusive) e 0,60 (exclusive) —
faixa meia-aberta no topo, lida da série persistida `market_breadth` (`0019`,
`breadth_v1`, uma linha imutável por minuto fechado, produzida pelo
`scanner-worker`). A recusa por valor é `breadth_gate:0.97` (duas casas, para o
histograma de `ineligible` continuar sendo um histograma; o valor exato com
quatro casas vai no envelope) e a recusa por ausência de série é
`breadth_unavailable`. Quatro coisas que valem saber antes de digitar: (i) **a
âncora é exata** — a linha vale para o minuto que ela nomeia, então um produtor
atrasado *emudece* a versão em vez de deixá-la decidir com o valor de três
minutos atrás, e não há janela de tolerância a calibrar; (ii) **cobertura recusa,
nunca inclina para baixo** — abaixo de 80 % do universo monitorado o produtor
grava a linha como inutilizável e o portão responde `breadth_unavailable`, porque
"0,97 de seis mercados" diria "o universo desabou" quando a verdade é "não deu
para olhar"; (iii) **a ordem é hora, regime, amplitude**, e a amplitude é a última
de propósito: uma versão que só declare as duas regras antigas reporta byte a byte
o motivo que reportava antes da T3.77 existir; (iv) **o número que motivou a
regra** é o de 09/09 às 22:08Z, quando 194 das 200 perpétuas caíram no mesmo
minuto (KB-0083) — e a faixa é **célula, não filtro**, até a EXP-0027 dizer o
contrário. Como toda regra do envelope, largar a amplitude do pai em silêncio é
recusado: repita `breadth=…`, escreva `breadth=none` para tirá-la, ou
`--policy none` para tirar o portão inteiro.

**A série mudou de nome, e a política passa a dizer qual (T3.88).** A regra agora
grava um quarto campo: `{"breadth": {"window_m": 5, "min": "0.10", "max": "0.60",
"version": "breadth_v2"}}`. `breadth_v2` é a **mesma aritmética** da `breadth_v1`
(5 min, `<` estrito, piso de 80 %) sobre **outro universo**: os mercados com ≥ 90
dias de velas de 1 min — os 16 do universo sombra (T3.82) — em vez dos ~200
monitorados. O motivo é o custo que a T3.77 declarou e ninguém pagou: com 200 no
denominador, 87 dos últimos 91 dias saíam `insufficient_coverage`, e a EXP-0027
não tinha passado nenhum para ler. Quatro coisas para o operador: (i) `--policy
breadth=0.10-0.60` grava `breadth_v2` (a série atual, resolvida **na derivação** e
nunca relida por um build posterior) e `--policy breadth=0.10-0.60@breadth_v1`
grava a antiga, byte a byte como era; (ii) a nota humana da linhagem **não muda**
(`breadth=0.10-0.60`), então nenhuma variante já gravada parece diferente — a série
é auditável no corpo da política e em todo envelope que a versão escreve; (iii) uma
política sem `version` é **recusada** (a versão emudece, o operador vê) em vez de
completada com o padrão do build: era exatamente assim que uma célula
pré-registrada podia ser reapontada para outro universo entre dois deploys; (iv)
uma versão presa a `breadth_v2` num dia em que o produtor só escreveu `breadth_v1`
responde `breadth_unavailable` — falha fechada, nunca "a outra série serve".
Popular os 90 dias é o `infra/scripts/backfill_breadth.py --days 90` (relatório
primeiro, `--apply --reason` depois, sempre pelo `compose.sh run --rm ops`):
129 600 minutos, ~3,5 min medidos em testcontainer.

```
# a variante da EXP-0027 (faixa pré-registrada; --dry-run primeiro, sempre)
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh run --rm ops python infra/scripts/derive_variant.py mean_reversion v10 --policy breadth=0.10-0.60 --changelog EXP-0027_amplitude_010_060 --dry-run"
```

```
# a variante da EXP-0023 (janela pré-registrada; --dry-run primeiro, sempre)
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh run --rm ops python infra/scripts/derive_variant.py mean_reversion v10 --policy hours=12-15 --changelog EXP-0023_janela_12_15_UTC --dry-run"

# a irmã que mantém o portão de regime do pai — as duas regras, nomeadas
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh run --rm ops python infra/scripts/derive_variant.py momentum v11 --policy regime=btc:BTC_BULL,HIGH_VOLATILITY,hours=12-15 --changelog EXP-0023_janela_12_15_UTC --dry-run"
```

### A dispersão BTC × alts (`dispersion=`, T3.90)

A **quarta** regra do mesmo envelope: `--policy dispersion=-0.05-0.00` prende a
versão às barras em que a **mediana do retorno de 24 h das alts menos o retorno de
24 h do BTC** ficou entre −0,05 (inclusive) e 0,00 (exclusive) — faixa meia-aberta
no topo, lida da série persistida `market_dispersion` (`0020`,
`dispersion_24h_v1`, uma linha imutável por minuto fechado, produzida pelo
`scanner-worker`). Negativo é a *discordância* que motivou a regra: em 10/09 e
11/09 o plantão mediu a mediana das 16 perpétuas em −4,80 %/−3,85 % com o BTC em
−1,50 %/−1,30 %, isto é, dispersão de −0,033 e −0,0255 (H-P18). A recusa por valor
é `dispersion_gate:-0.08` (duas casas, para o histograma de `ineligible` continuar
sendo um histograma; o valor exato com seis casas vai no envelope) e a recusa por
ausência de série é `dispersion_unavailable`.

Seis coisas que valem saber antes de digitar. (i) **Os limites são com sinal**, e
a gramática entende os dois: `-0.05-0.00`, `-0.10--0.03` (as duas pontas
negativas) e `0.00-0.10` são faixas válidas; o separador é o `-` **entre** os dois
números, não o primeiro que aparece. (ii) **Não há campo de horizonte**: 24 h, o
universo (os 16 com ≥ 90 d de velas de 1 min) e a referência (`BTCUSDT`) vivem
dentro da string da versão, então nenhum botão da política pode reapontar uma
célula pré-registrada para outro número — a lição da T3.88 aplicada antes de
existir a primeira linha. (iii) **A série é obrigatória na política**:
`--policy dispersion=-0.05-0.00` grava `dispersion_24h_v1` (resolvida **na
derivação**, nunca relida por um build posterior) e `@<série>` a nomeia
explicitamente; um corpo sem `version` é **recusado**, e a versão emudece em vez
de decidir contra uma série que ninguém pré-registrou. (iv) **A âncora é exata** —
a linha vale para o minuto que ela nomeia, então um produtor atrasado *emudece* a
versão em vez de deixá-la decidir com o valor de quinze minutos atrás, e não há
janela de tolerância a calibrar. (v) **Cobertura e referência recusam, nunca
inclinam** — abaixo de 80 % do universo, ou sem retorno de 24 h do BTC, o produtor
grava a linha como inutilizável (`insufficient_coverage`, `btc_missing`) e o
portão responde `dispersion_unavailable`, porque uma mediana de três mercados
diria "as alts capitularam" quando a verdade é "não deu para olhar". (vi) **A
ordem é hora, regime, amplitude, dispersão**, e a dispersão é a última de
propósito: uma versão que só declare as três regras antigas reporta byte a byte o
motivo que reportava antes da T3.90 existir. Como toda regra do envelope, largar a
dispersão do pai em silêncio é recusado: repita `dispersion=…`, escreva
`dispersion=none` para tirá-la, ou `--policy none` para tirar o portão inteiro.

Popular os 90 dias é o `infra/scripts/backfill_dispersion.py` (relatório primeiro,
`--apply --reason` depois, sempre pelo `compose.sh run --rm ops`). O relatório traz
uma coluna a mais que o da amplitude — `dobra` — porque aqui **três** regras
decidem o que é dobrável: o dia passa o piso, **a véspera dele também passa** e a
referência é densa nos dois. O motivo é o horizonte: num fold de 24 h cada minuto
de um dia lê velas do dia anterior, então um dia mantido depois de um dia pulado
seriam 1 440 lápides permanentes (`0020` não dá `UPDATE`/`DELETE` a ninguém).
Consequência declarada: `--days 90` dobra no máximo **89** dias.

```
# a variante do braço A da EXP-0029 (faixa pré-registrada; --dry-run primeiro, sempre)
ssh hunter-vps "cd /opt/project-hunter && bash infra/vps/compose.sh run --rm ops python infra/scripts/derive_variant.py mean_reversion v10 --policy dispersion=-0.10--0.03 --changelog EXP-0029_discordancia_-010_-003 --dry-run"
```

## O que continua igual depois do passo 8
- Só ordens a mercado, só SPOT, sem alavancagem; fill pelo livro elegível após a latência declarada; sem fill fabricado.
- Risco 0,25 % por operação incluindo custos, soma ≤ 1 %, participação ≤ 1 % do minuto, β-BTC ≤ 0,5×, total ≤ 40 %, por moeda ≤ 10 %, máx. 5 posições, pendentes contam.
- Kill switch AVISO/BLOQUEADO como na diretiva; BLOQUEADO só sai com o Everton (OWNER).
- Uma proposta por ciclo (D3), `research_only` nunca vira ordem, `live` recusado por nome, `ENABLE_LIVE_TRADING=false`.
- A ordem manual paper (`POST /api/v1/orgs/{org_id}/portfolios/{portfolio_id}/order-requests`, T3.68) não depende de `ENABLE_PAPER_AUTONOMY`: é o caminho do operador, sempre ativo, mesmo com a ponte desligada.

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

## 9b. Executor real de memecoins — o que o Everton digita e decide (T4.14)

Nada desta lista é feito por agente; cada item é um ato dele. Contrato:
`docs/RISK_ENGINE_MEME.md` (§3, §12); operação: `docs/DEPLOYMENT.md` §3.7; schema:
`docs/DATABASE.md` §40.

1. **Os cinco números de política** (§3.1, coluna "live" — hoje vazia de propósito):
   `MEME_WALLET_MAX_SOL` (o que aceita perder **inteiro**), `MEME_MAX_SOL_PER_TRADE`,
   `MEME_DAILY_LOSS_CAP_SOL`, `MEME_MAX_OPEN_POSITIONS`, `MEME_COOLDOWN_S`. Sem os cinco
   o executor recusa subir com a flag ligada (`policy_missing`, nomes na mensagem).
2. **A decisão escrita**, porque os Portões A (VM1–VM9 na VPS + 7 dias de papel) e B
   (EXP-M1: ≥ 100 operações e ≥ 30 dias) estão **vermelhos** hoje: um arquivo
   `obsidian/06-DECISIONS/AAAA-MM-DD-teste-pequeno-meme-real.md` dizendo o escopo
   (`max_sol_per_trade`, `max_total_sol`, `max_trades`, validade). O executor lê o
   `meme_gates.json` com `small_test_authorization` apontando para esse arquivo; o escopo
   vira teto **adicional** (`min` com os cinco acima) e contador de compras
   (`small_test_scope_exhausted` depois de `max_trades`).
3. **`meme_gates.json`** em `/opt/project-hunter/run/meme/` (formato em
   `packages/core/hunter_core/execution/meme/gates.py`), assinado por ele, com validade.
4. **O `.env` da VPS**: `ENABLE_MEME_LIVE_TRADING` ligada, `SOLANA_WALLET_SECRET_KEY`
   (a carteira **dedicada**, criada por ele, com saldo ≤ `MEME_WALLET_MAX_SOL` — saldo
   acima recusa entradas, `wallet_over_max_sol`), `SOLANA_RPC_URL` (RPC próprio com
   chave), `MEME_GATES_FILE=/run/hunter/meme_gates.json`, e — só se quiser liquidação
   automática em `EMERGENCY` (§14.4) — `MEME_AUTO_CLOSE_ON_EMERGENCY=true`; para o estágio 1
   sem clique (item 9), `MEME_LIVE_AUTO_APPROVE` ligada.
5. **Subir**: `MEME_LIVE=1 MEME=1 MEME_ENABLED=true bash infra/vps/compose.sh update`;
   conferir `hb:meme:executor` (`live_enabled=true`, `gates`, `wallet_pubkey`, `policy`,
   `kill_switch=ACTIVE`) e `GET /api/v1/orgs/ever/meme/live` (`executor.status=alive`).
6. **Aprovar REAL na mesa**: a proposta entra com `"mode": "live"` em
   `POST …/meme/proposals/{id}/approve` (ou `…/proposals/manual`) — recusada
   `meme_live_disabled` enquanto a API não tiver a mesma flag. **A tela ainda não tem o
   botão "Aprovar (REAL)"** (a T4.14 não tocou `apps/web`; o que a mesa precisa renderizar
   está em `.claude/state/notes-T4.14.md` §7): até lá é `curl`/HTTP com `Idempotency-Key`.
   O laço de papel continua preenchendo a mesma proposta em sombra, para comparar.
7. **Vender agora**: `POST …/meme/live/positions/{id}/sell-now` (TRADER+,
   `Idempotency-Key`); o executor vende na curva na passada seguinte, ao preço de então.
8. **Desligar em 5 s**: `touch /opt/project-hunter/run/meme/meme.kill` (§3.7); a trava
   diária só sai pelo `UPDATE` dele.
9. **Modo sozinho (estágio 1) — T4.28** (decisão dele de 16/09/2026 01:2x BRT, registrada em
   `obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md`, "Estágio 1 — sozinho"): com
   `MEME_LIVE_AUTO_APPROVE` ligada no `.env` da VPS, o executor abre **ele mesmo** a proposta
   `proposed` do conjunto `operator` ativo como proposta real — exatamente o que o clique em
   "Aprovar (REAL)" grava (`decided_by = executor:auto_stage1`, `decision = suggested`,
   `mode = live`) — e a admissão segue **inalterada** (25 checks, sizing, escopo, kill switch relido
   antes de assinar). Só é lida com `ENABLE_MEME_LIVE_TRADING` ligada **e** o `small_test_authorization`
   nos portões (sem escopo escrito o boot recusa `auto_approve_needs_small_test`); o escopo do
   estágio 1 é o de sempre — `max_sol_per_trade 0,05`, `max_total_sol 0,25`, `max_trades 5` — e agora o
   `max_total_sol` também fecha a torneira (`small_test_scope_exhausted`, somando o SOL real que cada
   compra confirmada tirou da carteira) e a última compra é **clampada** ao que sobra. Freios só deste
   modo: 1 compra por tique e por mint, proposta com mais de 60 s fica para a mão dele,
   `MEME_LIVE_AUTO_APPROVE_MAX_PER_HOUR` (padrão 5; desde a T4.28e conta só as propostas que a
   admissão deixou passar — recusa não gasta vaga), e toda recusa da admissão marca a proposta
   `rejected` com o motivo (a mesa mostra por quê). Desde a **T4.28f** há também uma **carência por
   mint**: uma moeda que a admissão acabou de recusar por um motivo que não muda em dois minutos
   (`progress_below_window`, `progress_above_window`, `token_too_old`, `token_age_unknown`,
   `program_not_allowed`, `unsupported_quote`, `progress_denominator_missing`) não é reaberta por
   `MEME_LIVE_AUTO_APPROVE_REFUSAL_COOLDOWN_S` (padrão 120 s; `0` desliga) — a mesa repropõe o mesmo
   mint a cada ~20 s e em 16/09 o robô abriu a mesma moeda 5 vezes para levar 5 recusas iguais. Motivo
   que o relógio limpa sozinho (`token_too_young`, `curve_state_stale`, `volume_unavailable`,
   `marks_incomplete`, `wallet_over_max_sol`) **não** segura a retentativa. O pulo aparece no
   heartbeat em `auto_skipped.recently_refused`. O heartbeat `hb:meme:executor` publica
   `auto_approve`, `auto_approved_1h`, `auto_refused_1h`, `auto_skipped`, `small_test_used_sol`,
   `small_test_trades_done`, `small_test_remaining_sol`. **Desligar:** `MEME_LIVE_AUTO_APPROVE=false`
   (ou apagar a linha) + `MEME_LIVE=1 MEME=1 MEME_ENABLED=true bash infra/vps/compose.sh update` —
   ou o kill switch do item 8, que também pára as aprovações automáticas na hora (o executor não abre
   proposta com o switch bloqueando). **O estágio 2 (US$ 1 000/operação) continua exigindo o clique**
   até nova decisão escrita. A validade do `meme_gates.json` tem de cobrir o estágio (hoje:
   `small_test_authorization.expires_at` e `valid_until` ≥ 2026-09-18 — ele edita o arquivo).
   **Editar o `meme_gates.json` vale em até um tique (10 s), sem `docker restart`** (T4.28d): o
   executor relê o arquivo quando o `mtime` muda, recompõe a política (`hb:meme:executor` mostra
   `gates`, `gates_mtime`, `gates_reloaded_at`) e, se o arquivo ficar inválido, **trava** o kill
   switch com `gates_invalid:<motivo>` (destrava só na mão dele). Grave o arquivo de forma atômica
   (`cp gates.json gates.tmp && editar && mv gates.tmp meme_gates.json`) para o tique nunca ler um
   JSON pela metade; os contadores do escopo (compras feitas, SOL gasto) **não** são zerados pela
   releitura. **T4.28f:** se mesmo assim um tique pegar o arquivo pela metade (`nano` grava no lugar),
   a primeira falha de leitura **não trava** — ela é adiada por um tique (o heartbeat mostra
   `gates_reload_error = deferred:gates_file_invalid` e o log,
   `meme_executor_gates_reload_deferred`), e a trava só vem se o tique seguinte falhar de novo. Um
   arquivo **completo** que diz não (vencido, Portão C desligado, escopo sumido com o robô armado)
   continua travando na hora.

9c. **Deixar o `dev_share` medido responder por um criador desconhecido (T4.28h) — decisão dele.**
   `MEME_CREATOR_UNKNOWN_ALLOWED_IF_DEV_MEASURED=true` (+ opcional
   `MEME_CREATOR_UNKNOWN_MAX_DEV_SHARE_PCT`, padrão `0.10`) no `.env` da VPS faz o executor admitir
   uma compra com `creator_flow_unknown` **desde que** o `dev_share` esteja medido, datado, com
   ≤ 600 s e dentro do teto — a mesma regra do `operator/5` da mesa. **Motivo medido (16/09/2026):**
   11 das 22 ordens reais do dia foram recusadas `creator_flow_unknown` porque o `creator_sold` do
   fold de 1 min chega +123 a +441 s depois da criação e a entrada acontece entre 30 e 300 s — a mesa
   propunha o que o executor recusava. Ligar isto **afrouxa** o check 10 para o caso "desconhecido";
   um criador **conhecido** vendedor líquido continua recusado, e a admissão marca o caso com
   `creator_unknown_dev_share_measured` (o heartbeat mostra os dois campos em `policy`). Desligar é
   apagar a linha + `compose.sh update`. Um valor ilegível (`sim`, `maybe`) **recusa o boot** pelo
   nome da variável.

9c-bis. **Alinhar a janela de progresso do executor com a mesa (T4.58) — decisão dele.** O check 9
   (`curve_progress`) do executor tem a **última palavra** sobre a janela de progresso da curva e vem
   de fábrica em **2 %–50 %** (`MEME_PAPER_V0`, `curve_progress_min_pct`/`max_pct`); o
   `max_progress_pct` do portão `operator/5` da mesa **não consegue passar dele na prática** — em
   18/09/2026 11:06 BRT, com o portão da mesa em 100 %, a primeira proposta (JAYCAT, 61,7 %) foi
   recusada `progress_above_window` pelo executor. Para abrir a janela até a curva inteira, no
   `.env` da VPS: `MEME_CURVE_PROGRESS_MAX_PCT=1.0` (e, se quiser, `MEME_CURVE_PROGRESS_MIN_PCT`,
   padrão `0.02`; frações de 0 a 1) + `compose.sh update`. Ausentes ⇒ os padrões; ilegível, fora de
   `[0, 1]` ou `min ≥ max` ⇒ o boot recusa pelo nome (`policy_missing`, com a janela na mensagem),
   como as cinco. O heartbeat `hb:meme:executor` publica a janela vigente em
   `policy.curve_progress_min_pct`/`curve_progress_max_pct`.

9d. **Tesouraria — trocar USDC por SOL sozinho quando o gás fica baixo (T4.54), decisão dele
   de 17/09/2026** ("eu quero deixar atualizado para usar outra moeda"). Desligada por padrão.
   Para ligar, no `.env` da VPS: `MEME_TREASURY_ENABLED=true` (mais nada é obrigatório — os
   padrões são `MEME_TREASURY_SOL_FLOOR=0.30`, `MEME_TREASURY_SOL_TARGET=0.60`,
   `MEME_TREASURY_MAX_USDC_PER_SWAP=25`, `MEME_TREASURY_MAX_USDC_PER_DAY=50`,
   `MEME_TREASURY_MAX_SLIPPAGE_BPS=50`, `MEME_TREASURY_MIN_INTERVAL_S=600`; qualquer um pode
   ser sobrescrito na mesma `.env`) e `MEME_LIVE=1 MEME=1 MEME_ENABLED=true bash
   infra/vps/compose.sh update`. A troca só sai com `ENABLE_MEME_LIVE_TRADING` **também** ligada
   (nunca em papel) e com o kill switch destravado — o mesmo `touch
   /opt/project-hunter/run/meme/meme.kill` do item 8 também para a tesouraria na hora. Cada
   tentativa (cotada, recusada, simulada, enviada, confirmada ou falha) vira uma linha em
   `meme_treasury_swaps`; `hb:meme:executor` publica `treasury` (`enabled`, `last_swap_at`,
   `last_result`, `wallet_usdc`). Detalhe técnico e o que fica de fora do escopo mainnet:
   `docs/RISK_ENGINE_MEME.md` § "Tesouraria — USDC → SOL (T4.54)".

9e. **Envio: reenvio, prioridade dinâmica e slippage de saída (T4.55) — nada a ligar, tudo
   revisável.** R56 (`.claude/state/notes-R56.md` §2.1) mediu 3 de ~23 envios reais em 30 h mortos em
   `blockhash_expired_never_landed` e uma venda em `6003 TooLittleSolReceived`: a causa era **uma**
   transação com 0,000004 SOL de prioridade, enviada **uma** vez e nunca reenviada, e uma venda a 1 %
   de tolerância numa curva que caiu 14 % num segundo. Desde a T4.55 o executor (a) reenvia os
   **mesmos bytes assinados** a cada 2 s enquanto espera a confirmação (mesma assinatura — a rede
   deduplica, nunca uma posição dupla), (b) escolhe a prioridade pelo p75 das taxas recentes do
   programa pump + a curva do mint, com piso e teto, e (c) vende com tolerância própria. As variáveis,
   todas opcionais no `.env` da VPS (valor ilegível ou fora da faixa cai no padrão — nunca recusa o
   boot; **não** são política de capital):

   | Variável | Padrão | O que faz |
   |---|---|---|
   | `MEME_RESEND_INTERVAL_S` | `2` | cadência do reenvio dos mesmos bytes durante a janela de confirmação (`MEME_LIVE_CONFIRM_TIMEOUT_S`, 30 s); `0` volta ao envio único |
   | `MEME_PRIORITY_FEE_FLOOR_MICRO_LAMPORTS` | `100000` | piso da prioridade em µL/CU (com 400 000 CU = 0,00004 SOL, 0,08 % de uma compra de 0,05) |
   | `MEME_PRIORITY_FEE_MAX_SOL` | `0.002` | teto do **custo total** da prioridade; o teto em µL/CU é `max_sol / compute_unit_limit` (5 000 000 com 400 000 CU) — igual ao `max_priority_fee_sol` do perfil, que a admissão continua conferindo (check 20) |
   | `MEME_BUY_MAX_SLIPPAGE_PCT` | `1` | (T4.59) tolerância (em **por cento**) do `max_sol_cost` de toda compra; faixa `(0, 20]` — acima disso é política de capital, não ajuste. 18/09: EMRLD e TIME morreram com `6002 TooMuchSolRequired` a 1 %; a carteira pode pagar até `sol_final × (1 + pct)`. Publicado como `buy_max_slippage_pct` no `policy` do heartbeat |
   | `MEME_EXIT_MAX_SLIPPAGE_PCT` | `5` | tolerância (em **por cento**) do `min_sol_output` de toda venda |
   | `MEME_PANIC_EXIT_MAX_SLIPPAGE_PCT` | `15` | tolerância das vendas `creator_dump` e `rug_signal` — a venda que tem de acontecer numa curva derretendo |

   Leitura da taxa: `getRecentPrioritizationFees` no RPC dele, no máximo uma vez por tique, 1,5 s de
   prazo, cache de 10 s; falhou ⇒ paga o piso e conta em `priority_fee_read_failures`. O que o
   `hb:meme:executor` publica: `resends_total`, `resend_errors_total`, `last_resends`,
   `priority_fee_reads`, `priority_fee_read_failures`, `priority_fee_last` (JSON com `micro_lamports`,
   `source` = `p75`|`floor`|`cap`|`floor:read_failed`|…, `p75_micro_lamports`, `samples`, `fee_sol`),
   `exit_max_slippage_pct`, `panic_exit_max_slippage_pct`. Cada ordem grava em `intent` o
   `priority_fee` escolhido, o `max_slippage_bps` usado e, depois de liquidada, `resends`.
   `skipPreflight` continua desligado e `maxRetries: 0` continua — o reenvio é nosso, não do nó.

9f. **Tamanho por convicção (T4.61b, corrigido na T4.61c) — a flag é dele, padrão desligado.** Até
   18/09 toda compra real saía a `min(MEME_MAX_SOL_PER_TRADE, size_sol da proposta)`, fixo (0,28 SOL).
   Com `MEME_CONVICTION_SIZING=on` o executor compra uma **fração desse teto** decidida pela evidência
   que a admissão já tem (criador lido na cadeia ou só na fita, compradores únicos, tendência de
   holders, concentração) e **recusa** `entry_after_drop` quando o SOL real da curva está ≥ 50 % abaixo
   do pico dos últimos 60 s (KB-0118), `entry_after_drop_unknown` quando há menos de duas fotos da
   curva na janela ou a leitura falhou (a borda que não se vê recusa, nunca desconta),
   `conviction_too_low` quando o produto cai abaixo de 0,25 e `conviction_too_small` quando o tamanho
   dimensionado fica abaixo de `MEME_MIN_TRADE_SOL` — nunca acima do teto, nunca pó. A escada entra
   **no motor** (check 26 `conviction` + teto `conviction`): uma compra descontada mostra
   `binding_constraint = conviction` na mesa, e uma recusa da escada é `admission_approved = false`
   com `first_refusal` nomeando, como qualquer outra. Desligada, **nada é lido nem calculado** (custo
   zero; `admission.conviction = {enabled: false, evaluated: false}`) e o tamanho é o de hoje. Ligada,
   a leitura tem prazo próprio (3 s) e nunca derruba o executor: falhou ⇒ `read_failed` na ordem e
   `entry_after_drop_unknown`. `entry_after_drop` cola 30 s de carência no robô (abaixo dos 60 s da
   KB-0118). Regra e evidência: `docs/RISK_ENGINE_MEME.md` § "Tamanho por convicção".

   **Antes de ligar** (revisão `.claude/state/review-T4.61b.md`, fechada na T4.61c): A1 leitura guardada,
   A2 uma foto ⇒ recusa, A4 `binding_constraint = conviction`, A5 piso real, A9 `approved = false`.

   | Variável | Padrão | O que faz |
   |---|---|---|
   | `MEME_CONVICTION_SIZING` | `off` | `on` avalia e aplica a escada; qualquer outro valor é `off`. Publicado como `conviction_sizing` no `policy` do heartbeat |
   | `MEME_MIN_TRADE_SOL` | `0.02` | **política de capital, opcional (T4.61c)**: a menor compra que o perfil live envia — piso do check 23 e da recusa `conviction_too_small`. Ilegível, ≤ 0 ou acima de `MEME_MAX_SOL_PER_TRADE` recusa o boot pelo nome. Um escopo escrito (`max_sol_per_trade` do teste pequeno) menor que o piso puxa o piso para o número do escopo. Com a flag desligada também vale: um teto entre 0,001 e 0,02 SOL (participação, restante do escopo) passa a recusar em vez de mandar pó |
   | `MEME_CONVICTION_TAPE_ONLY_MULT` | `0.5` | multiplicador quando o `creator_verdict.decided_by` é só a fita (ou ninguém falou) |
   | `MEME_CONVICTION_MIN_UNIQUE_BUYERS` / `MEME_CONVICTION_BUYERS_MULT` | `25` / `0.5` | limiar de `unique_buyers_60s` (EXP-M10) e o multiplicador abaixo dele ou sem leitura |
   | `MEME_CONVICTION_HOLDERS_MULT` | `0.5` | `holders_rising` falso ou desconhecido |
   | `MEME_CONVICTION_BUNDLED_MAX_PCT` / `MEME_CONVICTION_TOP10_MAX_PCT` / `MEME_CONVICTION_CONCENTRATION_MULT` | `0.10` / `0.20` / `0.5` | frações; acima de qualquer uma (ou sem leitura) aplica o multiplicador |
   | `MEME_CONVICTION_DROP_PCT` / `MEME_CONVICTION_DROP_WINDOW_S` | `0.50` / `60` | queda do SOL real (`recent_drawdown_pct` v1 sobre as fotos da janela + a leitura desta admissão) que **recusa** `entry_after_drop`; menos de duas fotos na janela recusa `entry_after_drop_unknown` |
   | `MEME_CONVICTION_FLOOR` | `0.25` | produto abaixo disto recusa `conviction_too_low` |
   | `MEME_CONVICTION_EVIDENCE_MAX_AGE_S` | `120` | idade máxima da linha de 15 s usada para compradores/holders |

   `MEME_CONVICTION_PEAK_UNKNOWN_MULT` **deixou de existir** na T4.61c (sem foto era desconto; agora é
   recusa). Multiplicadores em `(0, 1]`, frações em `(0, 1]`, inteiros com piso; valor ilegível ou fora
   da faixa cai no padrão — nunca recusa o boot e nunca sobe o teto (o teto continua sendo
   `MEME_MAX_SOL_PER_TRADE`, política de capital dele). Só `MEME_MIN_TRADE_SOL` recusa o boot, porque é
   política.

9g. **Saída por evento (T4.63) — a flag é dele, padrão desligado.** CITIZEN (18/09, `KB-0139`) foi
   de +82 % a −80 % entre dois tiques de 10 s do laço de saídas. Com `MEME_EVENT_EXITS=on` o executor
   abre um WebSocket de RPC Solana próprio (`SOLANA_RPC_WS_URL`; vazio deriva de `SOLANA_RPC_URL`,
   `https`→`wss`; sem nenhum, o público — que **não** serve para produção), assina a curva de cada
   posição aberta e vende no instante em que a **mesma** regra do tique dispara (`decide_exit`, os
   mesmos `target_x`/`trailing_pct`/`max_hold_s` do conjunto), pela **mesma** venda (trava por
   posição, `CurveRead` fresco, simulação, tolerância normal/pânico, reenvio). Uma venda do criador
   vista no `TradeEvent` carimba `creator_sold_seen_at` com a fração medida e dispara `creator_dump`
   ali. O tique de 10 s continua como reserva: WS caído = "só tique", nunca executor parado. Nada de
   política, tamanho ou admissão muda. Regra: `docs/RISK_ENGINE_MEME.md` §9 "T4.63: saída por
   evento".

   | Variável | Padrão | O que faz |
   |---|---|---|
   | `MEME_EVENT_EXITS` | `off` | `on` liga o runtime; qualquer outro valor é `off` com aviso. Publicado como `event_exits_enabled` no heartbeat |
   | `SOLANA_RPC_WS_URL` | vazio | o WS do executor (o mesmo nome que o portão de evento do radar usa); vazio deriva de `SOLANA_RPC_URL` |
   | `MEME_EVENT_COMMITMENT` | `confirmed` | `confirmed` \| `processed` — o mesmo do radar; `processed` não decide sozinho |

   **Ligar:** no `.env` da VPS `MEME_EVENT_EXITS=on` (e `SOLANA_RPC_WS_URL` se o provedor usa outro
   host para WS), `compose.sh update meme-executor`. **Conferir** no `hb:meme:executor`:
   `event_exits_ws_state = connected`, `event_exits_subscriptions = 2 × posições abertas`,
   `event_exits_updates_60s > 0` enquanto a moeda negocia; depois da primeira saída por evento,
   `event_to_sell_submit_s_p50` (alvo: < 2 s) e `event_exits_triggered_total`. `event_exits_restarts_total`
   ou `event_exits_dropped` crescendo é o sinal de que o WS do provedor não aguenta — a mesa continua
   protegida pelo tique. **Desligar:** `MEME_EVENT_EXITS=off` + `update`; nada mais precisa mudar.

9h. **Perfil de lançamento no executor (T4.67b, EXP-M18) — a flag é a mesma do radar, padrão
   desligado; o executor só age em `on`.** A pista de lançamento (T4.67a) escreve propostas
   `launch_v0/1` a cada `create`; em `paper` ela mede no papel e o executor **não toca** nessas
   propostas (nenhuma consulta, nenhuma linha); em `on`, com `ENABLE_MEME_LIVE_TRADING=true`, o
   executor as admite pelo perfil rápido (`docs/RISK_ENGINE_MEME.md` §18: checks 10, 11, 12 e 26
   gravados `skipped` por nome; 7, 8, 9, 21 e 23 sob a regra do lançamento; o resto igual à §4),
   compra com blockhash pré-buscado, piso de prioridade próprio e tolerância de 10 %, e sai em segundos
   (`time_stop_s` 6, queda de 20 % do pico, primeiro sell de terceiro — pelo evento, T4.63, e por um
   tique de 2 s). **Custo fixo declarado:** rent da ATA + rede + prioridade ≈ 0,003 SOL por bilhete de
   0,01 (~29 %); `MEME_CLOSE_ATA_ON_FULL_SELL=1` recupera o rent na venda cheia.

   | Variável | Padrão | O que faz |
   |---|---|---|
   | `MEME_LAUNCH_LANE` | `off` | `off` \| `paper` \| `on` — compartilhada com o radar; o executor age **só** em `on` (e só com a flag de real); outro valor lê como `off` com aviso. `launch_lane_mode` no heartbeat |
   | `MEME_LAUNCH_MAX_OPEN` | `2` | teto de posições de lançamento (abertas + pendentes com `lane = launch`), separado do global `MEME_MAX_OPEN_POSITIONS`, que continua contando todas |
   | `MEME_LAUNCH_TICKET_SOL` | `0.01` | o bilhete (teto `launch_ticket` do sizing); nunca acima de `MEME_MAX_SOL_PER_TRADE`; abaixo de `MEME_MIN_TRADE_SOL` o piso segue o bilhete |
   | `MEME_LAUNCH_PRIORITY_FLOOR_MICRO_LAMPORTS` | `1000000` | piso da taxa de prioridade do lançamento (0,0004 SOL com 400 k CU); `max(p75, piso)` limitado por `MEME_PRIORITY_FEE_MAX_SOL` e pelo check 20 (5 % do bilhete) |
   | `MEME_LAUNCH_BUY_SLIPPAGE_PCT` | `10` | tolerância da **instrução** de compra, em por cento, faixa (0, 20] |
   | `MEME_LAUNCH_SKIP_SIMULATION` | `false` | `true` pula o `simulateTransaction` do executor antes de assinar (≈ 100 ms); o preflight do nó continua. Risco: uma assinatura gasta (journal) por transação que só o simulador pegaria; se pousar com erro, taxa de rede paga |
   | `MEME_LAUNCH_MAX_PARTICIPATION_PCT` | `0.10` | fração do SOL real já na curva que o bilhete pode ser (o 1 % do perfil exigiria 1 SOL no primeiro segundo) |
   | `MEME_LAUNCH_MAX_AGE_S` | `5` | idade máxima da moeda na admissão (do carimbo do `create` da proposta); mais velha ⇒ `launch_proposal_stale`/`token_too_old`, sem RPC |

   **Ligar:** `MEME_LAUNCH_LANE=on` no `.env` da VPS (o radar passa a `on` junto — é a mesma
   variável), `MEME_EVENT_EXITS=on` (sem ele só o tique de 2 s vende), `compose.sh update
   meme-worker meme-executor`. **Conferir** no `hb:meme:executor`: `launch_lane_mode = on`,
   `launch_blockhash_age_s < 10`, depois da primeira compra `proposal_to_submit_ms_p50` (alvo:
   < 1 000 ms; acima disso a tese da EXP-M18 já não é a que está sendo medida), `launch_refusals`
   (esperado: `participation_above_cap` e `launch_proposal_stale` dominando), `launch_open ≤ 2`,
   `launch_buys_total` × `launch_sells_total` (devem andar juntos: uma posição de 6 s que não vendeu
   é `blocked_exits`). **Desligar:** `MEME_LAUNCH_LANE=paper` (o radar continua medindo) ou `off` +
   `update`; as posições abertas continuam sendo vendidas pelos tiques.

9i. **Troca à vista (spot) manual pela Jupiter, qualquer par (T4.73)** — Everton, 19/09/2026:
    usar a Binance como sinal e comprar na Solana pela carteira do robô, via Jupiter. Diferente da
    tesouraria (9j abaixo, automática, só USDC → SOL), esta é uma ferramenta manual e auditada:
    `infra/scripts/meme_spot_swap.py`, rodado por `compose.sh ops`, dry-run por padrão.

    ```bash
    # dry-run: cota, mostra a rota, o impacto e a saída esperada (sem tocar a carteira)
    bash infra/vps/compose.sh ops python infra/scripts/meme_spot_swap.py \
        --from SOL --to <MINT> --amount 0.02 --reason "teste T4.73"

    # o mesmo, com o verificador rodando de verdade (chave pública só, nunca a secreta)
    bash infra/vps/compose.sh ops python infra/scripts/meme_spot_swap.py \
        --from SOL --to <MINT> --amount 0.02 --reason "teste T4.73" \
        --user ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4

    # ida e volta, ainda em dry-run: compra + cotação de venda de volta, custo em fração
    bash infra/vps/compose.sh ops python infra/scripts/meme_spot_swap.py \
        --from SOL --to <MINT> --amount 0.02 --round-trip --reason "teste T4.73"

    # aplicar de verdade (assina com SOLANA_WALLET_SECRET_KEY do .env da VPS, nunca impressa)
    bash infra/vps/compose.sh ops python infra/scripts/meme_spot_swap.py \
        --from SOL --to <MINT> --amount 0.02 --round-trip --apply --reason "teste T4.73"
    ```

    Tetos recusados por nome antes de montar qualquer coisa: `--amount` acima de 0,05
    SOL-equivalente exige `--i-know`; impacto de preço acima de `--max-impact-pct` (padrão 1%);
    `--apply` exige o interruptor de emergência **exatamente** `ACTIVE` e só aceita um par com uma
    perna em SOL (a outra ponta pode ser qualquer mint). Cada tentativa grava uma linha em
    `meme_treasury_swaps` (mesma tabela da tesouraria, `input_mint`/`output_mint` preenchidos) e um
    `system_events`. Detalhe e o que ainda não foi provado ao vivo: `docs/RISK_ENGINE_MEME.md`
    §16.4.

    **Teto duro, piso da carteira e códigos de saída (T4.73b/T4.73c).** Além do teto brando de
    0,05, há um teto **duro** de 0,10 SOL-equivalente que `--i-know` **não** levanta; e uma perna de
    compra com SOL só passa se `carteira − amount − 0,01 ≥ MEME_WALLET_MIN_SOL_AFTER_SWAP` (padrão
    0,30 SOL, lido do `.env` da VPS; valor inválido ou ≤ 0 recusa, nunca cai para um piso menor).
    O script sai com **0** quando a operação (ou o dry-run) terminou limpa, **64** uso errado,
    **65** recusada por nome (antes ou dentro de uma perna), **66** perna enviada mas **não
    confirmada** em 20 s — a linha fica `submitted` com a assinatura impressa, a volta do
    `--round-trip` **não** dispara e a reconciliação é manual, pela assinatura (a tesouraria
    automática não a toca: os leitores dela só veem linhas com `input_mint IS NULL`) —, **67** perna
    falhou na cadeia. Num wrapper, só o 0 é sucesso.

10. **Simular uma venda numa curva com *holder rewards* antes de confiar nela (T4.29c)** — só ele pode
    rodar (o agente não tem carteira nem posição). A T4.8c provou por simulação de mainnet uma *compra*
    numa moeda `is_holder_reward = true` e *vendas* só em curvas normais; a venda numa curva HR nunca
    foi simulada. A doc oficial diz que nada muda na instrução (`docs/HOLDER_REWARDS_README.md` do
    commit `81091419e4457566469d4e2a27f64ed84d42419c` de `pump-fun/pump-public-docs`, sha256
    `ce2a57883f342aa7f4142058e58f93e639efd64fed426b2f1f2d63d21f4cc6a1`: "Trading holder rewards coins —
    There are **no changes to any trade instruction**"), e o `sell` do `idl/pump.json` do mesmo commit
    continua com as mesmas 14 contas + `fee_config`/`fee_program`. Isto aqui é a prova disso na cadeia.

    Na VPS, com a moeda HR já **na carteira do robô** (o `--user` é o endereço **público**; o script
    nunca lê `.env`, nunca lê a chave e não tem caminho para `sendTransaction`):

    ```bash
    cd /opt/project-hunter && uv run python infra/scripts/meme_simulate_trade.py \
        --simulate-only --sell --mint <MINT_HR> \
        --user ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4 \
        --rpc "$SOLANA_RPC_URL" --json-out /tmp/sim_sell_hr.json
    ```

    **"ok" é:** `is_holder_reward=True` na linha da curva; `verify ok=True` (verificador §9.1);
    `simulateTransaction SELL ... ok=True err=None` com `units_consumed` na casa de 50–70 mil e um log
    `Program log: Instruction: Sell`; e a última linha `rpc calls=N sendTransaction=0`. Vender só parte:
    `--amount <subunidades>`. Uma compra se simula igual, com `--buy --budget-sol 0.01`.

    **Não é ok** e o que significa: `err=Custom:3` (sem saldo do token naquela ATA — a moeda não está
    nessa carteira); `bonding curve not found` (moeda já graduou — a venda seria na PumpSwap, que não
    existe, item (a) abaixo); `unsupported_quote:<mint>` (moeda cotada em token que não é SOL nativo —
    o executor recusa antes de cotar, como na T4.8b/T4.8c); `holds no <mint>` (o script se recusa a
    simular uma venda sem saldo real, porque isso não provaria nada). Sem `--simulate-only` ele sai com
    código 2 antes da primeira chamada de RPC.

    **Já rodado uma vez (16/09/2026 18:21 UTC), sem carteira dele:** numa moeda HR com um detentor real
    achado na fita pública (`Bo5vHuDB…`), `ok=True`, 53 041 CU, `Instruction: Sell` — a venda em curva HR
    deixou de ser fé. O `TradeEvent` da simulação mostrou `holder_rewards = creator_fee` (mesma taxa, outro
    destinatário), então o custo que o executor já usa continua certo. O que continua **sem** prova é a
    venda **da carteira dele**, com a posição dele — é isso que o comando acima faz.

    O script também imprime o `FeeConfig` lido da cadeia (`fee_config <PDA> slot=… tiers=1 …`, T4.29c) ou
    `meme_fee_config_unavailable` quando a conta não pôde ser lida — neste caso as taxas usadas são a
    constante datada de 20/05/2026 (95 + 30 bps), que em 16/09/2026 é exatamente o que a conta diz.

**O que não está pronto e ele precisa saber antes de ligar:** (a) venda **depois** da
migração para a PumpSwap não existe — uma posição que migrar fica `open` com
`blocked: pumpswap_sell_not_implemented` e sai só pelo site, na mão; com `max_hold_s`
curto o `time_stop` vende antes na curva; (b) a devnet não foi exercida (faucet público
recusou de novo) — a prova de ponta a ponta é a simulação na mainnet pelo caminho do
executor, sem envio; (c) os checks 10–12 e 21 dependem do que o radar mede
(`meme_features_1m`): mint sem `bundled_share` medido é recusado
`bundled_share_unmeasurable`, sem volume orgânico é `volume_unavailable` — é a doutrina
"insumo ausente não vira zero", não um defeito.

## Onde acompanhar
`/ever/portfolio` (patrimônio, kill switch, curva), `/ever/system` (worker, `autonomy`, pendências, proteções), `hb:execution:paper` no Redis, `obsidian/05-EXPERIMENTS/EXP-0005-momentum-paper.md`.

No `hb:execution:paper`, os campos que respondem "por que nada aconteceu":
`paper_autonomy` (a flag), `open_positions`/`marked_positions` e **`mark_quality`**
(fração das posições abertas marcadas a preço vivo — `1` numa carteira vazia;
abaixo de `1` a admissão é adiada com `marks_incomplete`), `last_mtm` (quando o
ponto foi escrito, que é outra pergunta), `degraded_protections` e
`protection_delay_s`.
