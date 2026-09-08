# Brief (para o `database-architect`) — a tabela `replay_runs`

**Origem:** T3.19b (quant-engineer) entregou o motor de replay histórico
(`services/strategy-worker/hunter_strategy_worker/replay/`). O brief da T3.19b pedia uma linha de
livro-razão por corrida e **proibiu** o autor de escrever a migração: "if that table needs a
migration, write the brief for `database-architect` instead of the migration". Este é o brief.
**Nada aqui ativa nada nem chega à carteira**; uma linha de `replay_runs` é um recibo.

## 1. O que existe hoje, e por que não basta

A forma da linha já está definida e testada em
`hunter_strategy_worker/replay/ledger.py::ReplayRun.to_jsonable()`. Ela é gravada em dois lugares:

1. **`system_events`** (`component = 'replay_engine'`, `event = 'replay_run_finished'`, `data` = o
   JSON inteiro). É o canal auditado que o worker já pode escrever (`APPEND_ONLY_TABLES`), e foi
   usado na prova real da T3.19b. **Retenção de 30 dias** (`docs/DATABASE.md` §12) — mais curta que
   a janela do próprio protocolo de replicação, que conta 15 e 30 dias de resultados;
2. um **JSONL** local (`--ledger caminho.jsonl`), append-only. Honesto e frágil: uma corrida de mais
   de 30 dias atrás só é comprovável se alguém guardou o arquivo.

A pergunta que o placar e o plantão vão fazer — "quantas operações simuladas esta versão já
acumulou, sobre que janela, e quando?" — precisa de uma tabela.

## 2. Colunas pedidas (uma transcrição do `to_jsonable`)

| Coluna | Tipo | Notas |
|---|---|---|
| `id` | `uuid` PK | = o `run_id` do rótulo `replay:<run_id>`; **não** um uuid7 novo. O rótulo já é a identidade da população |
| `cohort` | `text NOT NULL` | `replay:<uuid>`; vale o mesmo CHECK de `shadow_episodes` (`SHADOW_COHORT_PATTERN`) **mais** a exigência do prefixo `replay:` — uma corrida nunca é `prospective` |
| `strategy_version_id` | `uuid NOT NULL` FK `strategy_versions(id)` | `ON DELETE CASCADE`, como `shadow_episodes` |
| `window_from` / `window_to` | `timestamptz NOT NULL` | semiaberto `[from, to)`; CHECK `window_to > window_from` |
| `markets` | `text[] NOT NULL` | `<exchange>:<symbol>`, a mesma chave do bloco 3 da REPLICATION.md |
| `started_at` / `finished_at` | `timestamptz NOT NULL` | CHECK `finished_at >= started_at` |
| `bars_evaluated` | `integer NOT NULL` | CHECK `>= 0` |
| `signals` | `integer NOT NULL` | |
| `outcomes_resolved` | `integer NOT NULL` | terminal + no_entry + censored |
| `outcomes_open` | `integer NOT NULL` | horizonte ainda aberto no relógio de parede |
| `seconds` | `numeric(12,3) NOT NULL` | **não** `double precision`: é o número que vira taxa em relatório |
| `decision_lag_s` | `integer NOT NULL` | premissa da corrida (`REPLAY_DECISION_LAG_S`); duas corridas com lag diferente não são a mesma população de `no_entry: late` |
| `workers` | `smallint NOT NULL` | |
| `evaluations_by_state` | `jsonb NOT NULL DEFAULT '{}'` | `{triggered, not_triggered, unavailable, ineligible, rejected}` |
| `errors` | `integer NOT NULL DEFAULT 0` | |
| `created_at` | `timestamptz NOT NULL DEFAULT now()` | |

**Uma corrida é fatiada.** A prova da T3.19b rodou 31 dias em 11 comandos com o **mesmo** cohort
(passos curtos, `--from/--to` fatiados). Duas leituras possíveis, e a decisão é sua:

- (a) uma linha **por fatia** (`id` deixa de ser o `run_id`; vira `uuid7` e o `run_id` fica numa
  coluna `run_id uuid NOT NULL` com índice), o que dá o histórico de throughput fatia a fatia;
- (b) uma linha **por corrida** com `UPSERT` acumulando (`bars_evaluated = bars_evaluated + :n`,
  `window_to = greatest(...)`), o que dá o total mas perde a cadência.

A recomendação do autor é **(a)**: somar é sempre possível a partir das fatias, separar não é. Nesse
caso `UNIQUE (run_id, window_from, window_to)` torna a repetição de uma fatia idempotente — que é
exatamente o que a identidade `uuid5` dos sinais já garante do outro lado.

## 3. Índices

- PK;
- `(strategy_version_id, window_from DESC)` — a pergunta do placar;
- `(run_id)` se a opção (a) for escolhida (o `UNIQUE` acima já começa por ela).

Sem partição: uma corrida por versão por janela é da ordem de dezenas por dia, não milhões.

## 4. Grants

- `hunter_worker`: `SELECT, INSERT`. **Nunca `UPDATE` nem `DELETE`** — um recibo que pode ser
  editado não é recibo. Se a opção (b) for escolhida, ela exige `UPDATE` e por isso a (a) é
  preferida também aqui.
- `hunter_app`: `SELECT`. O placar lê; não escreve.
- Retenção: nenhuma. Estas linhas são o registro de pesquisa (regra do `Registro de Tentativas`).

## 5. Depois da migração

`hunter_strategy_worker/replay/ledger.py::record_run` ganha um terceiro ramo (o `INSERT` na tabela)
ao lado do `system_events` e do JSONL — **não** um reescrita: os três continuam, porque o
`system_events` é o canal operacional (alarme, `level = warning` quando a corrida teve erros) e o
JSONL é o que sobrevive a um banco recriado. O `to_jsonable()` já é a linha, campo por campo.
