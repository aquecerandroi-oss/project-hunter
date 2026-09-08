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
| 6 | **Linha `paper` do momentum** | **Everton** (ou orquestrador com o seu "vai") | no container da API: `uv run python infra/scripts/activate_strategy_version.py momentum v1 --paper-line --dry-run --changelog "D10"`; sem `--dry-run` cria `momentum v2` `draft`, `purpose=paper`, `system_events` |
| 7 | **Ativação auditada** da linha `paper` | **Everton** | `activate_strategy_version.py momentum v2 --changelog "D10: coorte paper"` → `activated_at`, congelada; o strategy-worker passa a emitir sinais `purpose=paper` para essa coorte (a `research_only` continua ao lado) |
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
| 7 ativação auditada | **Everton** — `docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py momentum v3 --changelog D10_coorte_paper_ativada_por_Everton_2026-09-08` (sem aspas internas, por causa do PowerShell) |
| 8 flag | **Everton** — depois do 7 e com β válido |

## §8 — Checklist de aceite do modo autônomo (T3.29, medido na VPS em 2026-09-08 ~14:10Z)

O Everton vira a flag do passo 8 **quando toda linha estiver verde**. Cada linha
é uma medição, com a consulta que a produziu; nenhuma é opinião. Leituras feitas
como `docker exec hunter-postgres-1 psql -U hunter -d hunter` (somente `SELECT`).

| # | Condição | Medido em 2026-09-08 | Verde? |
|---|---|---|---|
| 1 | **Vínculo `agents`** habilitado para `momentum v3` + carteira `ever` | `SELECT count(*) FROM agents;` → **0** | 🔴 — rodar o §8a |
| 2 | **`avgPrice`** disponível para os mercados executáveis | 15/15 SPOT monitorados com `applyMinToMarket=true` e `avgPriceMins=5`; **22 de 22** sinais admissíveis de `momentum v3` em 24 h adiariam por `avg_price_not_collected` | 🟡 — código pronto (T3.29, `avg_price.py`), falta o **deploy** |
| 3 | **β válido** para algum mercado com sinal | 200 revisões vigentes, **1 válida** (BTCUSDT, β=1 por identidade); 199 `insufficient_history` com 423 barras contíguas contra 480 exigidas. Causa: o **próprio BTC** (a referência) só tem 1m desde `2026-08-21 20:32Z` (≈ 425 h). Resultado: **0** dos 171 sinais de 24 h passariam no `beta_validity` | 🔴 — falta backfill do BTC perpétuo até ≥ 20 dias contíguos |
| 4 | **Qualidade das marcas** (`mark_quality`) publicada e barrando admissão | campo novo no `hb:execution:paper` (T3.29); carteira sem posição ⇒ `1` por construção | 🟡 — falta o deploy |
| 5 | **Backup restaurável** | 3 dumps em `/opt/backups` (último `hunter-20260908T011701Z.dump`, 387 M, 01:18Z); cron `/etc/cron.d/hunter-backup` 03:17 diário com `bash`; `pg_restore --list` legível com **1730 entradas**, incluindo `TABLE DATA public {portfolios,trade_proposals,orders,fills,positions,trades,agents,risk_profiles,portfolio_exit_intents,market_betas,kill_switch_transitions}` | 🟡 — TOC provado; **restore real ainda não** (§restore abaixo) |
| 6 | **MTM vivo** | último ponto `1m` 36 s antes da leitura; `marks_stale=false`; equity 19.333,0111164813 USDT; kill switch `ACTIVE` | 🟢 |
| 7 | **`paper_autonomy` desligado até aqui** | `hb:execution:paper.paper_autonomy = false` | 🟢 (é o estado correto antes do aceite) |
| 8 | **Perfil de risco persistido** (`RISK_ENGINE.md` §2) | `portfolios.risk_profile_id` é **NULL** e não existe linha `risk_profiles.preset='paper_v1'`. Os limites em vigor são os certos — `admit(..., limits=PAPER_V1)` usa o objeto do motor —, mas a linha que a §2 chama de "única fonte" não foi semeada nesta VPS | 🟡 — não altera limite nenhum hoje; fecha antes de alguém fazer `admit` ler o perfil da carteira |

**Consultas, verbatim.** As duas que decidem as linhas 2 e 3:

```sql
-- linha 2: quantos mercados executáveis exigem avgPrice
SELECT symbol,
       (metadata->'spot_market_filters'->>'apply_min_to_market')::bool AS min_mkt,
       metadata->'spot_market_filters'->>'avg_price_mins' AS avg_mins
  FROM markets
 WHERE market_type='spot' AND status='active' AND delisted_at IS NULL AND is_monitored;
-- 15 linhas, todas min_mkt=t e avg_mins=5

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
--     171 |    22 |            0
```

**Leitura honesta do resultado.** Mesmo com o vínculo `agents` criado e com o
`avgPrice` implantado, **nenhum** dos 171 sinais das últimas 24 h teria virado
ordem: o `beta_validity` recusa todos menos BTCUSDT, e BTCUSDT não emitiu sinal
`momentum v3` na janela. Isso é a regra do Everton funcionando (§6 do contrato:
"sem beta validado, manter o ativo apenas em shadow"), não um defeito — e é
exatamente por isso que a linha 3 é a que bloqueia o aceite hoje.

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

**Sobre o restore (linha 5).** Nesta rodada a VPS foi tratada como **somente
leitura**: `pg_restore --list` foi executado sobre o dump mais recente (1730
entradas, tabelas do ledger presentes), e **nenhum** banco `hunter_restore_test`
foi criado — um restore real é `CREATE DATABASE` + escrita, e a instrução desta
tarefa era não escrever nada na VPS. O restore real continua **pendente** e é a
única prova que fecha a linha 5; ele deve rodar num banco separado e ser
derrubado no fim.

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

**Derivar** (o script vem do repositório por stdin, porque a imagem publicada pode ainda não tê-lo; `python -` lê o script da entrada padrão e os argumentos vêm depois do `-`):

```
ssh hunter-vps "docker exec -i hunter-api-1 python - momentum v2 --set atr_pct_min=0.0089 --changelog 'KB-0008: piso de custo' --dry-run" < infra/scripts/derive_variant.py
```

O `--dry-run` roda **todas** as recusas e não escreve nada; a saída nomeia a versão que nasceria, o que se moveu e o `params_hash`. Repita sem `--dry-run` para gravar. Toda corrida — sucesso, recusa ou erro — deixa linha em `system_events` (componente `activate_strategy_version`).

O que ele recusa, antes de qualquer escrita: migração ausente, pai inexistente, pai nunca ativado, pai que não é `research_only`, `code_ref` que este build não reproduz, parâmetro fora do schema congelado, valor que não valida, **valor fora da faixa declarada** (negativo onde o pai é positivo, piso ≥ teto, `AssumedCosts`/geometria que não instanciam — T3.26c/A2) e um conjunto que já existe no mesmo `code_ref`.

**Ativar a variante** (corrida separada e auditada, com o script *da imagem* — que agora reconhece a linha derivada e preserva o conteúdo dela):

```
ssh hunter-vps "docker exec hunter-api-1 python infra/scripts/activate_strategy_version.py momentum v4 --changelog T3.26_variante_KB-0008_ativada_por_Everton"
```

Sem aspas internas, por causa do PowerShell. Se aparecer `REFUSED: ... already carries its own default_parameters`, a imagem está **atrás** da T3.26c: faça o deploy e repita — não contorne editando o `changelog`.

## O que continua igual depois do passo 8
- Só ordens a mercado, só SPOT, sem alavancagem; fill pelo livro elegível após a latência declarada; sem fill fabricado.
- Risco 0,25 % por operação incluindo custos, soma ≤ 1 %, participação ≤ 1 % do minuto, β-BTC ≤ 0,5×, total ≤ 40 %, por moeda ≤ 10 %, máx. 5 posições, pendentes contam.
- Kill switch AVISO/BLOQUEADO como na diretiva; BLOQUEADO só sai com o Everton (OWNER).
- Uma proposta por ciclo (D3), `research_only` nunca vira ordem, `live` recusado por nome, `ENABLE_LIVE_TRADING=false`.

## Como desligar
`ENABLE_PAPER_AUTONOMY=false` + `compose.sh update` para a ponte parar de consumir (posições abertas continuam protegidas pelo worker). `activate_strategy_version.py momentum v2 --deprecate` não existe: deprecar é um `UPDATE status='deprecated'` auditado pelo dono do banco — registrar na T3.10 se virar rotina.

## Onde acompanhar
`/ever/portfolio` (patrimônio, kill switch, curva), `/ever/system` (worker, `autonomy`, pendências, proteções), `hb:execution:paper` no Redis, `obsidian/05-EXPERIMENTS/EXP-0005-momentum-paper.md`.

No `hb:execution:paper`, os campos que respondem "por que nada aconteceu":
`paper_autonomy` (a flag), `open_positions`/`marked_positions` e **`mark_quality`**
(fração das posições abertas marcadas a preço vivo — `1` numa carteira vazia;
abaixo de `1` a admissão é adiada com `marks_incomplete`), `last_mtm` (quando o
ponto foi escrito, que é outra pergunta), `degraded_protections` e
`protection_delay_s`.
