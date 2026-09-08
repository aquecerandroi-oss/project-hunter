# Brief para a database-architect — `replay_runs` precisa de uma linha que não é um replay (recibo de estresse, T3.36)

**Origem:** T3.36 (quant-engineer, 2026-09-08). **Prioridade:** baixa — a passada de estresse já
funciona e grava o recibo num JSONL; isto é a diferença entre um recibo que sobrevive ao disco de
quem rodou e um recibo que o placar consegue consultar. **Nada aqui muda dado existente.**

## O que aconteceu

A T3.36 entregou a *passada de estresse* (`hunter_strategy_worker/replay/stress.py`): dada uma
coorte `replay:<uuid>` já gravada, ela **reprecifica** os desfechos das entradas congeladas sob
custo ×2, stop e alvo ×0,75/×1,25, entrada atrasada uma barra, cada mercado deixado de fora e cada
metade da janela, e devolve uma tabela com veredito. A sessão é `READ ONLY` no Postgres: a passada
não escreve **nada** no Lab, por construção.

O brief pedia o recibo em `replay_runs` com `kind = 'stress'`. **Não é representável hoje**, por
três motivos, e nenhum deles é contornável de fora:

1. **não existe coluna `kind`** (`0013_replay_runs`);
2. `CHECK (cohort = 'replay:' || run_id::text)` — o recibo de estresse **não tem `run_id` próprio**;
   ele fala *sobre* a coorte de outra corrida. Escrever a mesma `run_id` da coorte de origem
   colidiria com `uq_replay_runs_slice (run_id, window_from, window_to)` e faria uma passada de
   estresse apagar (por `ON CONFLICT DO NOTHING`) o recibo do replay que ela mediu;
3. metade das colunas obrigatórias não tem significado aqui (`bars_evaluated`, `signals`,
   `decision_lag_s`, `workers`, `evaluations_by_state`): uma passada de estresse não avalia barra
   nenhuma nem emite sinal nenhum. Preenchê-las com zero seria inventar número.

Enquanto isso: o recibo vai para um JSONL (`--ledger`), append-only, com `stress_version`, coorte,
`as_of`, `input_digest` (impressão digital das linhas lidas), semente, reamostras, a tabela inteira
por cenário e o veredito com os motivos.

## O que eu peço (e o que **não** peço)

**Peço a decisão de modelagem, não uma coluna específica.** As duas formas que enxergo:

- **(a) `replay_runs.kind`** (`text NOT NULL DEFAULT 'replay'`, CHECK em `('replay','stress')`) mais
  `source_run_id uuid NULL` (a coorte medida) e o relaxamento do `CHECK` de coorte e da unicidade
  para o caso `stress` — mexe numa tabela que hoje tem um invariante limpo ("uma linha = uma fatia
  de replay") e o suja com um segundo tipo de linha;
- **(b) tabela própria `stress_runs`** (`id`, `cohort` — FK lógica para a coorte medida —, `as_of`,
  `stress_version`, `input_digest`, `seed`, `resamples`, `verdict`, `rows jsonb`, `created_at`),
  `SELECT`/`INSERT` para `hunter_worker`, sem `UPDATE`/`DELETE`, como a `0013` fez. Custa uma tabela
  e preserva o invariante da outra.

Minha inclinação é **(b)**, pelo mesmo argumento que a própria `0013` usa para não guardar recibo em
`system_events`: a linha tem outra vida útil e outro leitor. Mas a decisão é da database-architect —
e o número de tabelas do schema também é um custo.

**Não peço:** nenhuma mudança em `signal_outcomes`, `agent_signals`, `shadow_episodes` ou no padrão
de coorte. A passada de estresse não cria coorte, não cria sinal e não toca desfecho.

## Contrato do recibo (o JSONL de hoje, campo a campo)

`hunter_strategy_worker/replay/stress_report.py::StressRun.to_jsonable`:

| campo | tipo | o que é |
|---|---|---|
| `stress_version` | int | versão do conjunto de cenários (`hunter_indicators.replay.stress.STRESS_VERSION`) |
| `cohort` | text | a coorte medida — `replay:<uuid>` |
| `as_of` / `generated_at` | timestamptz | corte de dados e relógio de parede |
| `versions` | text[] | rótulos `<key>_<version>` das versões que a coorte contém |
| `markets` | text[] | `<exchange>:<symbol>` dos mercados com entrada admitida |
| `cases` / `partial` / `limit` | int / bool / int? | entradas congeladas lidas; `partial` marca corrida com `--limit` |
| `seed` / `resamples` | int | semente e reamostras do intervalo por blocos de dia |
| `input_digest` | text | sha256 das linhas lidas (mesma função do EXP-0004) |
| `seconds` | numeric | duração |
| `verdict` / `reasons` | text / text[] | `robusto`, `frágil a custos`, `frágil a parâmetros`, `dependente de um mercado`, `dependente de metade`, `amostra_insuficiente`, `sem_vantagem_na_base` |
| `rows` | jsonb | uma entrada por cenário: `key`, `family`, `kind`, `total`, `n`, `targets`, `stops`, `expectancy_r`, `profit_factor` (+ motivo do nulo), `sum_r`, `dropped` por motivo, `delta_vs_base` com `pairs`/`blocks`/`ci_low`/`ci_high` |

Se a escolha for **(b)**, `rows` cabe inteiro numa coluna `jsonb` e o resto vira coluna. Se for
**(a)**, o mapeamento precisa dizer o que fazer com `bars_evaluated` e companhia — e a minha
opinião registrada é que preencher com zero é pior do que não ter a linha.

## O que a T3.36 não fez de propósito

Não editei `infra/migrations/**` (fora do escopo declarado do brief) e não escrevi nada no banco da
VPS (a passada é `READ ONLY` por transação). O JSONL não é solução provisória disfarçada: ele
continua existindo depois da tabela, pelo mesmo motivo que o `--ledger` do replay existe — é o que
sobrevive a um banco reconstruído.
