# T4.26 — a identidade social e o evento "pode dar bum" (16/09/2026)

Camadas 1 e 2 do brief `brief-T4.26-identidade-social-e-eventos-que-podem-dar-bum.md`. Camada 3
(plantão) não foi tocada — é do orquestrador/plantão.

## Migração `0041_meme_social`

- `infra/migrations/ddl/meme_social.py` + `meme_social_checks.py`: onze colunas em `meme_tokens`
  (`twitter`, `telegram`, `website`, `description`, `twitter_kind`, `twitter_post_id`,
  `twitter_post_at`, `twitter_reuse_count`, `twitter_reuse_observed_at`, `social_observed_at`,
  `social_source`); nove escritas uma vez (`WRITE_ONCE_COLUMNS_0041`, somadas ao gatilho
  `meme_tokens_identity_is_written_once`), duas mutáveis (o contador de reuso, como
  `mayhem_state`). `meme_radar_features_v1` recriada com as nove colunas de identidade
  acrescentadas.
- `infra/migrations/ddl/meme_events.py`: tabela `meme_events` (global, sem RLS), FK `mint →
  meme_tokens`, três índices (`observed_at`, parcial não-casado, parcial casado); coluna
  `meme_proposals.event_id` (FK); seed `event_v0/1` (`research_only`, `EXP-M8`, `require_event:
  true`) — não mexe no `operator` ativo.
- Downgrade: refusa em ordem (proposta referenciando `event_v0/1` → evento existente → leitura
  social existente), restaura a view e o gatilho de `0024` **antes** de derrubar as colunas
  (senão o gatilho ficaria referenciando coluna inexistente).
- `packages/core/hunter_core/db/models/{meme,meme_events,meme_social_checks}.py`: modelo
  espelha a DDL byte a byte (nomes de CHECK batem com a convenção `ck_%(table)s_%(name)s`).
  `MemePaperBet` foi movido de `meme_lab.py` para um novo `meme_bets.py` (re-exportado) para abrir
  espaço para `event_id` em `MemeProposal` dentro do orçamento de 350 linhas.
- Testes: `packages/core/tests/integration/test_migrations.py` — `HEAD_REVISION` para
  `0041_meme_social`, `CREATOR_INDEX_REVISION` nova, dez `test_0041_*` (colunas, write-once vs.
  mutável, oito CHECKs isolados, seed do `event_v0/1`, tabela+grants, um casamento manual smoke,
  três refusals de downgrade, round-trip completo).

**Três bugs achados e corrigidos ao rodar `test_migrations.py` de verdade** (não só ao escrevê-lo):

1. `restore_radar_view_0024()` usava `CREATE OR REPLACE VIEW` para **remover** as nove colunas
   sociais — Postgres recusa (`cannot drop columns from view`). Corrigido para `DROP VIEW` +
   `CREATE VIEW`, o mesmo padrão que `restore_radar_view_0021` (`ddl/meme_graduation.py`) já usa
   pelo mesmo motivo.
2. `_CLEAN_0041` (o cleanup dos testes) fazia `DELETE FROM meme_tokens` sem declarar
   `SET LOCAL app.meme_retention = 'on'` primeiro — o gatilho `meme_tokens_retention_is_declared`
   recusa, o cleanup nunca roda, e linhas de teste ficam para trás poluindo o downgrade de
   qualquer teste seguinte no mesmo arquivo (`0038`/`0039`/`0040` chegaram a falhar por isso).
   Corrigido nos dois pontos de limpeza (`_CLEAN_0041` e o `finally` de
   `test_0041_reverses_on_a_clean_database_and_comes_back`).
3. Um caso do parametrizado de `test_0041_checks_refuse_a_malformed_social_read`
   (`twitter_kind = 'post'` sem `twitter`) violava **dois** CHECKs ao mesmo tempo
   (`a_twitter_link_names_its_kind` e `a_post_link_names_its_id`); Postgres relata só um, sem
   garantia de qual — trocado para `twitter_kind = 'profile'`, que isola o primeiro CHECK.

## Coleta (sem chamada nova)

- `hunter_exchanges/pumpfun/social.py` (novo): `classify_twitter_url` (profile/post/community/
  other, com a fórmula do snowflake `(id >> 22) + 1288834974657` ms — conferida contra o post do
  M-P17, bate 03:45:19 UTC = 00:45:19 BRT) e `truncate_description` (≤ 2000 chars, marcador).
  Reservados twitter (`i`, `home`, `explore`, `search`, `notifications`, `messages`, `settings`,
  `compose`) tratados como `other`, não `profile`.
- `normalize.parse_curve_state_rest` agora também extrai `uri` (metadata_uri), `twitter`,
  `website`, `telegram`, `description` do mesmo payload de `/coins/{mint}` — nenhuma chamada nova.
- `board_models.NormalizedRiskSnapshot` ganhou `twitter_reuse_count`; `indexer_rest.
  parse_risk_snapshot` extrai `twitterReuseCount` do mesmo payload de 65 campos.
- **Não implementado, declarado**: o `GET metadata_uri` (IPFS) opcional para quando a REST vem
  vazia (`MEME_METADATA_FETCH_ENABLED`). O brief o marca "opcionalmente"; cortado por orçamento
  de tarefa. Ambiente de teste não tem rede real de qualquer forma.

## Worker

- `repo_rows.TokenRow` + `repo.py`: os onze campos sociais entram no upsert; nove por
  `COALESCE(existing, new)` (escrita única), dois por `COALESCE(new, existing)` (mutável).
- `curve_rows.token_row_from_curve`: só grava `social_observed_at`/`social_source` quando
  `state.source == 'pumpfun_rest'` — a leitura RPC nunca tentou ler identidade social e não pode
  reivindicar uma observação que não fez.
- `risk._pool_row`: **bug achado e corrigido durante o TDD** — antes desta tarefa, `_pool_row` só
  era chamado quando `graduated_at is not None`; o contador de reuso nunca chegaria a
  `meme_tokens` para a maioria das leituras. Corrigido para rodar sempre que `graduated_at` **ou**
  `twitter_reuse_count` vier preenchido; e `pool_created_source` só é escrito quando
  `pool_created_at` também é (senão violaria `ck_meme_tokens_a_pool_names_its_source` na primeira
  leitura sem graduação) — pego pelo teste antes de chegar a produção.
- `hunter_indicators/meme/{identity,event_gate}.py` (novos): portões transversais, no molde de
  `pedigree.py` — `evaluate_identity_gate(require_twitter=…)` recusa `no_twitter`;
  `evaluate_event_gate(require_event=…)` recusa `no_event` a menos que `confirmed` + kind ∈
  {`public_figure_launch`, `exchange_listing`, `brand_launch`}. Nenhum dos dois toca
  `EntryGate`/`evaluate_entry` (congelados).
- `proposals_row.py` (novo, `GateRow` movido de `proposals.py` para abrir orçamento);
  `proposals_identity.py` (novo, `identity_features_of`/`event_features_of`); `proposals.py`
  chama os dois portões e passa os dois blocos para `gate_reasons`.
- `proposals_reasons.py`: os blocos `identity`/`event` só aparecem em `reasons` quando
  `spec.require_twitter`/`spec.require_event` — **achado por teste**: uma primeira versão que
  sempre mostrava o bloco `identity` quebrou
  `test_exp_m1_reasons_do_not_change_and_its_gate_still_takes_the_pedigree` (a decomposição
  congelada de EXP-M1 não pode ganhar um bloco novo). Corrigido para seguir o mesmo molde de
  linha/hype/fluxo: um conjunto que não pergunta não aparece na decomposição de outro.
- `lab_models.RuleSetSpec`: `require_twitter`/`require_event`, `bool`, padrão `false`.
- `lab_repo.py`/`lab_repo_fast.py`: os sete campos sociais e os cinco de evento entram no mesmo
  `SELECT`/`LEFT JOIN LATERAL meme_events … ORDER BY observed_at LIMIT 1` que já buscava o resto
  da identidade — **nenhuma consulta nova por linha julgada** (o `LATERAL` usa
  `ix_meme_events_mint`, tabela minúscula).

## O evento e o job de casamento

- `events_repo.py` (novo): a consulta `_MATCH` (CTE + `UPDATE … FROM candidates … RETURNING`),
  `link_proposals` (idempotente, `event_id IS NULL`), `count_events` (para
  `events_open`/`events_matched_1h`). Savepoint + `statement_timeout = 5000` ms, degrada para
  `None` (não mata o laço) — o molde exato de `lab_repo_fast.pedigree_for` (T4.24b).
- `events.py` (novo): `events_match_once(ctx)` (a cada 60 s, sem switch próprio — a consulta é
  barata e sempre bounded) e `spawn_events_match`, ligado em `main.py`.
- **`main.py` estava exatamente em 350 linhas** (o teto) antes desta tarefa. Para abrir espaço
  para o novo laço sem violar o orçamento, `_close` foi movido para `wiring.py` (renomeado
  `close_clients`) — refatoração mecânica, mesma lógica, só o endereço mudou. `main.py`: 338
  linhas; `wiring.py`: 298.
- **EXPLAIN, medido contra 150 007 linhas em `meme_tokens`** (dados sintéticos, ~156 dias de
  `created_at`, `ANALYZE` antes do plano; transação com `ROLLBACK` explícito — não deixou as 150 k
  linhas na base compartilhada dos testes):

  ```
  Update on meme_events
    ->  Nested Loop
          ->  Subquery Scan on c (rn = 1)
                ->  WindowAgg (row_number() <= 1)
                      ->  Sort (e.id, t.created_at)
                            ->  Nested Loop
                                  ->  Index Scan using ix_meme_events_unmatched on meme_events e
                                        Index Cond: (observed_at >= '2026-01-01…')
                                        Filter: (handle_hint IS NOT NULL OR symbol_hint IS NOT NULL)
                                  ->  Index Scan using ix_meme_tokens_created_at on meme_tokens t
                                        Index Cond: (created_at BETWEEN e.observed_at
                                                      AND e.observed_at + '01:00:00')
                                        Filter: (handle ILIKE match OR symbol match)
          ->  Index Scan using pk_meme_events on meme_events
                Index Cond: (id = c.event_id)
  ```

  Nenhum `Seq Scan` em `meme_tokens`. O laço externo é o índice parcial de `meme_events`
  (`ix_meme_events_unmatched`, tabela de poucas linhas por dia); o interno é
  `ix_meme_tokens_created_at`, que já existia desde `0021` — nenhuma coluna nova precisou de
  índice. Plano completo em `.claude/state/notes-T4.26-explain.txt` (gerado pelo próprio teste).

## O script auditado

`infra/scripts/meme_event.py add --kind … --title … [--url] [--mint] [--handle] [--symbol]
--confidence … --recorded-by … [--apply]` — dry-run por padrão, recusas nomeadas
(`kind_unknown`, `confidence_unknown`, `source_unknown`, `recorded_by_required`), audita em
`system_events` no apply, mesmo molde de `meme_rule_set.py`/`meme_ops_db.py`.

## EXP-M8

`obsidian/05-EXPERIMENTS/EXP-M8-evento-que-pode-dar-bum.md`, pré-registrada antes de existir uma
proposta. Portão de desenho `REVISE` (C3 amostra — eventos confirmed de figura pública são raros;
C7 execução — o casamento roda a cada minuto, não em tempo real). Nota de engenharia declarada: a
checagem de participação do gate (`rules._participation_refusals`) é incondicional para todo
conjunto — `max_participation_pct = 20` é número desta revisão, não do brief, porque um evento
recém-casado pode não ter fita de trades ainda. `Experiments Index.md` atualizado nas duas
tabelas.

## Docs

`docs/DATABASE.md` §52 (novo). `docs/PUMPFUN.md` não precisou de edição — os campos já estavam
documentados em §1.3/§3.1. Rótulos web pendentes (fora desta tarefa, listados em DATABASE.md
§52.6 e aqui): `twitter_kind` → perfil/post/comunidade/outro; `event.kind` (os seis valores);
`event.confidence` → confirmado/reportado/rumor. `pnpm gen:types` não rodado (não toquei
`apps/web`/TypeScript; o brief pede isso fora desta tarefa).

## Cortes de escopo declarados

1. `GET metadata_uri` (IPFS) — explicitamente "opcional" no brief, não implementado.
2. Heartbeat Redis (`hb:meme:radar` → `events_open`/`events_matched_1h`) e `GET /meme/sources` —
   `sources.py` estava a 349/350 linhas e `apps/api` não foi tocado; os dois números são
   calculados (`events_repo.count_events`) e logados via `structlog.debug` a cada tick, mas não
   expostos no heartbeat/API. Seguro de reverter depois com uma pequena divisão de `sources.py`.
3. Camada 3 (plantão): fora desta tarefa por instrução explícita.

## Achado colateral: árvore compartilhada

Durante a tarefa, uma task concorrente (T4.27, exclusão de moedas Mayhem do portão e o mcap
executável) editava ao vivo `packages/indicators/hunter_indicators/meme/{rules,rules_criteria,
curve,fast,replay,series}.py`, boa parte de `services/meme-worker/hunter_meme_worker/*.py`,
`packages/core/hunter_core/db/models/meme_features*.py` — e chegou a acrescentar a própria
migração `0042_meme_executable_mcap` **em cima da `0041`**, inclusive editando o mesmo
`test_migrations.py` (bumping `HEAD_REVISION`, acrescentando `SOCIAL_REVISION` e corrigindo os
três testes `test_0041_refuses_a_downgrade_*` para estagiar em `SOCIAL_REVISION` antes do `"-1"` —
exatamente o ajuste que este próprio arquivo já teria pedido de mim). Toda leitura de arquivo
desta tarefa foi refeita imediatamente antes de cada edição para pegar o estado mais recente;
nenhuma colisão de `Edit` ocorreu (nenhum conteúdo de uma tarefa foi perdido pela outra), e
`packages/core/tests/integration/test_migrations.py -k "0038 or 0039 or 0040 or 0041 or 0042"`
fechou em **23 passed** depois das duas convergirem. Ao final, `check_file_size.py` (0 arquivos
acima do orçamento) e o `git status --porcelain` completo mostram dezenas de arquivos de outras
tarefas (design audits, o `meme-executor`, KBs do plantão) — nada disso é desta tarefa; a lista
exata do que **é** está nas seções "Migração", "Coleta", "Worker" e "O evento…" acima.

## Testes — contagem exata

- `packages/exchange-adapters/tests/unit/test_pumpfun_social.py`: 16 novos.
- `test_pumpfun_normalize.py`: +2 (34 no arquivo).
- `test_pumpfun_indexer_rest.py`: +1 (6 no arquivo).
- `packages/indicators/tests/unit/test_meme_identity.py`: 3 novos.
- `packages/indicators/tests/unit/test_meme_event_gate.py`: 5 novos.
- `services/meme-worker/tests/test_proposals_identity_event.py`: 11 novos.
- `services/meme-worker/tests/test_curve_rows.py`: +2 (7 no arquivo).
- `services/meme-worker/tests/test_risk.py`: 3 novos (arquivo novo).
- `services/meme-worker/tests/test_events_persistence.py`: 6 novos (integração/testcontainer,
  inclui o EXPLAIN).
- `infra/scripts/tests/test_meme_event.py`: 9 novos.
- `packages/core/tests/integration/test_migrations.py`: 10 novos (`test_0041_*`).
- Suíte completa `services/meme-worker/tests -m unit`: 244 passed (era 220 antes desta tarefa —
  contando os que a T4.27 concorrente também acrescentou).
