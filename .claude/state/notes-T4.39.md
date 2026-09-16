# T4.39 — o PDA da curva é derivado na ingestão e no reconcile; os 13 615 do Mayhem são reparados

**Data:** 16/09/2026 · **Origem:** R36 (`.claude/state/notes-R36-pda-mayhem.md`, `docs/PUMPFUN.md` §9)

## O que mudou

R36 achou 13 615 das 112 108 linhas de 7 dias de `meme_tokens` gravando o mesmo endereço em
`bonding_curve` — o PDA `["sol-vault"]` compartilhado do programa Mayhem, não a curva de mint nenhum —
porque o frame `create` do PumpPortal traz esse valor em `bondingCurveKey` para moeda Mayhem contaminada
(43/100 na amostra de R36; 0/100 fora de Mayhem). O executor já estava seguro (deriva sempre); o radar
não estava.

Três frentes:

1. **Ingestão nunca mais confia no frame.** `hunter_exchanges.pumpfun.normalize.parse_new_token` deriva
   `bonding_curve_address(mint)` (`pumpfun/pdas.py`, novo — extraído de `tx.py`, que reexporta as duas
   funções para não quebrar import nenhum) e grava sempre o PDA em `bonding_curve`. O valor do frame só
   sobrevive em `bonding_curve_raw` (coluna nova) quando discordava — `NULL` é o caso comum (o frame já
   concordava). `discovery._handle` conta
   (`hunter_meme_token_bonding_curve_replaced_total{mayhem_enabled}`) e loga
   (`meme_token_bonding_curve_replaced`, mint + os dois endereços) a substituição no momento em que ela
   vira linha durável — nunca por `mint` no rótulo (cardinalidade ilimitada).
2. **`reconcile_once` deriva, não lê.** Parou de ler `tracked.bonding_curve` (e o `if tracked is None or
   tracked.bonding_curve is None: continue` que isso exigia) — deriva o PDA do mint a cada tique, como o
   executor já fazia. Um mint nunca visto com curva reconhecida agora também é reconciliável: a derivação
   só precisa do mint.
3. **Os 13 615 já gravados são reparados fora da migração.** `0047_meme_bonding_curve_raw` só acrescenta
   a coluna nova (nullable, gatilho de escrita única estendido, downgrade recusado enquanto alguma linha
   carregar um valor — §17.7, o canal do PumpPortal não tem replay). `infra/scripts
   /meme_repair_bonding_curve.py` faz a reescrita revisável: candidato é toda linha cujo `bonding_curve`
   discorda do PDA derivado do próprio mint (nunca um endereço fixo — a mesma função que o executor e o
   `reconcile_once` usam), `--apply` exige `--reason`, desliga/religa
   `meme_tokens_identity_is_written_once` **dentro** da transação (a mesma disciplina de `0024`'s
   `backfill_graduation_signals`), grava as duas colunas num único `UPDATE` (a expressão à direita do
   `SET` lê a linha antes da mudança) e deixa uma linha em `system_events` com a contagem por
   `mayhem_enabled`. Idempotente: repetir depois de aplicar não acha nada, porque toda linha reparada
   ganhou `bonding_curve_raw IS NOT NULL`.

## Achado no caminho — `repo.py` já tinha uma correção de `prune_tokens` no disco

Ao retomar o trabalho da instância anterior, `services/meme-worker/hunter_meme_worker/repo.py` já trazia
uma exclusão de mint com `meme_event_matches` correspondente no `_PRUNE_TOKENS` (a FK real de `0043`,
`fk_meme_event_matches_mint_meme_tokens`, ao contrário do `mint` em texto solto de toda aposta/proposta) —
sem relação com o PDA, mas testada por `test_persistence.py` (arquivo de T4.38, fora do escopo desta
tarefa). Mantida como estava: não é meu escopo removê-la, e removê-la quebraria aquele teste.

## Arquivos

- `packages/exchange-adapters/hunter_exchanges/pumpfun/{models,normalize,tx}.py`, novo `pdas.py`
- `packages/exchange-adapters/tests/unit/test_pumpfun_normalize.py`
- `services/meme-worker/hunter_meme_worker/{collect,discovery,repo,repo_rows,metrics}.py`, novo
  `repo_token_sql.py` (extraído de `repo.py` para caber no teto de 350 linhas — só `UPSERT_TOKEN`)
- `services/meme-worker/tests/{test_discovery_rows,test_discovery_bonding_curve_metric,
  test_reconcile_derives_curve}.py` (as duas últimas novas)
- `infra/migrations/ddl/meme_bonding_curve_raw.py`, `infra/migrations/versions
  /0047_meme_bonding_curve_raw.py` (encadeada em `0046_meme_rule_set_history`)
- `infra/scripts/meme_repair_bonding_curve.py` (novo) + `infra/scripts/tests
  /test_meme_repair_bonding_curve.py` (novo, Postgres real — write-once trigger provado e contornado)
- `packages/core/tests/integration/test_migration_0047.py` (novo — arquivo próprio porque
  `test_migrations.py` está fora de escopo nesta tarefa; upgrade nomeado, não `"head"`)
- `docs/DATABASE.md` §55, `docs/PUMPFUN.md` §9.1 (adendo — mantido o §9 original intocado)

## Gates

`ruff check`/`ruff format --check`: limpos nos arquivos acima. `pyright` (modo `strict`): limpo — dois
achados corrigidos no caminho (`Candidate` sem anotação de lista, protocolo `ChainSource.get_curve_states`
sem `commitment` no fake de teste) e uma pragma `# pyright: reportPrivateUsage=false` no teste que chama
`discovery._handle` diretamente (padrão já usado por `test_activity.py`/`test_creator_watch.py`).
`check_file_size.py`: `repo.py` estava em 355 linhas com a coluna nova — dividido em `repo.py` (267) +
`repo_token_sql.py` (101), o `UPSERT_TOKEN` isolado por ser a única coisa que só existia para servir
aquela query. `uv run pytest` da lista de gates: ver saída no relatório do agente.
