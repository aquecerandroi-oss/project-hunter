# Notas T4.43 — o portão de recusa por moeda ligado ao tique de 15 s (16/09/2026)

Execução backend-specialist. Sem commit; nada real tocado; `.env*` intocado. Não tocados
(concorrência declarada no brief): tudo de T4.38/T4.39/T4.41.

## O que ficou pronto

1. **`lab_fast.fast_gate_step`** agora chama `proposals.evaluate_gate` uma vez por linha em vez de
   uma vez por lote (o plano que a nota T4.35 já tinha deixado escrito: comportamento idêntico, o
   corpo do laço do portão não depende de linhas irmãs). Os rascunhos continuam batidos num só
   `insert_proposals` por conjunto — só o portão passou a rodar linha a linha; nenhuma consulta nova
   ao banco por isso, só chamadas de função a mais em memória.
2. **`_trail_row`** (`lab_fast.py`) decide, por linha e por conjunto: zero recusas → proposta;
   exatamente uma, e não `already_open` → quase-passou; `already_open` sozinha → descartada de
   propósito (é uma posição já aberta, dispara antes do portão julgar qualquer critério — gravá-la
   afogaria o teto com um nome que não ensina "por que não"); duas ou mais → descartada
   (`is_trail_candidate`, já testado em T4.35).
3. **`gate_refusal_trail.decode_value_limit`** — tabela de 15 nomes que já decodificam um par
   numérico (`age_*`, `progress_*`, `participation_above_cap`, `distance_*`, `hype_below_min`,
   `dev_share_above_max`, `snipers_*`, `top10_*`, `buyers_below_min`, `holders_below_min`); um nome
   fora da tabela grava a linha com os dois `NULL`, como o schema já previa.
4. **`lab_trail.py`** (novo, 105 linhas) — `RefusalTrailState` (dois contadores desde o boot),
   `write_refusal_trail` (o corte + a inserção batida, uma vez por tique, só quando há candidatos) e
   a poda diária: `should_prune_trail_today` (decisão pura, testável sem banco),
   `prune_trail_batches` (o laço em lotes sobre `prune_refusal_trail`) e `maybe_prune_trail` (junta os
   dois, é o que `collect.prune_once` chama).
5. **`config_trail.py`** (novo, 46 linhas) — `trail_max_rows_per_tick()` lê
   `MEME_GATE_TRAIL_MAX_ROWS_PER_TICK` (padrão 200, o mesmo `DEFAULT_TRAIL_CAP` de T4.35), e
   `TRAIL_RETENTION_DAYS = 7`. Segue o precedente de `events_config.py`/`fast_lane_config.py`: um
   módulo pequeno lido direto do ambiente, nada em `MemeConfig` (que já estava no teto de 350 linhas
   e continua exatamente lá — não tocado).
6. **Heartbeat** (`lab_heartbeat.py`): `lab_refusal_trail_rows` (linhas gravadas, desde o boot) e
   `lab_refusal_trail_capped` (linhas **descartadas** pelo teto, desde o boot — decisão deliberada:
   contar quanto se perde ensina mais do que contar quantos tiques estouraram o teto).
7. **`lab.py`**: um campo só em `LabState` (`trail: RefusalTrailState`) — 2 linhas (import + campo),
   o arquivo fecha exatamente em 350. Sem docstring no campo por causa disso; o tipo já se documenta
   em `lab_trail.py`.
8. **`context.py`**/**`collect.py`**: `RadarState.last_trail_prune_day` (o dia calendário UTC da
   última poda) e a chamada a `maybe_prune_trail` dentro do `prune_once` já existente — a poda roda
   uma vez por dia, não a cada hora como a retenção de `meme_tokens` ao lado.
9. Documentação: `docs/DATABASE.md` §54.2.1 (a ligação, o corte de `already_open`, os dois campos do
   heartbeat, a poda diária), `docs/RISK_ENGINE_MEME.md` item 16 (a consulta real que responde "por
   que não a moeda X", e a nota de que a ligação foi feita).

## Decisões que desviam da letra do brief, por quê

- **`already_open` nunca vira linha da trilha.** O brief não menciona esse caso; decidi excluí-lo
  porque ele é estrutural (dispara antes de qualquer critério do portão ser lido) e, sem o corte,
  toda aposta aberta seria "quase-passou" a cada tique de 15 s enquanto durasse — na prática
  dominaria o teto de 200 linhas/tique e faria exatamente o que a tabela existe para evitar (uma
  pilha que não ensina nada). Documentado em três lugares (docstring de `lab_fast.py`, §54.2.1,
  este arquivo) para não ser reinventado por engano depois.
- **Poda diária via `maybe_prune_trail` dentro do `prune_once` existente**, não um laço novo: o
  brief pede "uma vez por dia" e "do laço de manutenção existente" — não havia um laço diário
  separado do `retention` (hourly, `config.retention_cycle_s`), então usei o mesmo `prune_once` com
  um portão de dia calendário (`RadarState.last_trail_prune_day`) em vez de rodar a cada hora. A
  decisão pura (`should_prune_trail_today`) é testada sem banco; o laço em lotes em si
  (`prune_trail_batches`) reaproveita `lab_repo_fast.prune_refusal_trail`, já testado contra Postgres
  em T4.35 (`test_lab_repo_fast_trail.py`) — não dupliquei esses testes.
- **`capped_total` conta linhas descartadas, não tiques capados.** O brief só diz
  "`lab_refusal_trail_capped` (since boot)"; escolhi linhas porque "quanto se perde" é a pergunta que
  importa para calibrar o teto, e um contador de tiques perderia essa magnitude.

## Arquivos

**Criados:** `services/meme-worker/hunter_meme_worker/{lab_trail,config_trail}.py`,
`services/meme-worker/tests/{test_lab_trail,test_config_trail}.py`, esta nota.

**Modificados:** `services/meme-worker/hunter_meme_worker/{lab_fast,gate_refusal_trail,lab,
lab_heartbeat,context,collect}.py`, `services/meme-worker/tests/{test_gate_refusal_trail,
test_lab_fast}.py`, `docs/{DATABASE,RISK_ENGINE_MEME}.md`.

## Comandos e saídas (reais)

```
$ uv run pytest services/meme-worker/tests/{test_lab_trail,test_config_trail,test_gate_refusal_trail}.py -q
  → 27 passed (1.39s)
$ uv run pytest services/meme-worker/tests/test_lab_fast.py -q                → 7 passed (67.28s)
$ uv run pytest services/meme-worker/tests/test_lab_repo_fast_trail.py services/meme-worker/tests/test_lab_mayhem.py services/meme-worker/tests/test_outcome_quality.py -q
  → 12 passed (37.73s)
$ uv run pytest services/meme-worker/tests -q -m "not live" --ignore=... (a lista completa do brief)
  → 362 passed (232.89s)
$ uv run ruff check . / ruff format --check .           → só arquivos pré-existentes fora do meu
  escopo (infra/scripts/research/2026-09-16-*.py, obsidian/*, services/market-worker/*) — nenhum
  arquivo meu.
$ uv run pyright services/meme-worker                    → 3 erros pré-existentes, nenhum meu
  (test_lab_persistence.py, test_mayhem.py: ChainSource.get_curve_states já pedia `commitment` antes
  desta tarefa — provavelmente T4.42, arquivo de outro agente, não tocado por mim).
$ uv run python infra/scripts/check_file_size.py         → scanned 914 files; 0 over budget
```

## Pendências / observações para quem vier depois

- `decode_value_limit` cobre 15 nomes; `sells_ratio_above_max` (uma razão calculada, não um campo
  direto) ficou de fora de propósito — decodificá-lo exigiria reproduzir a divisão de
  `rules_criteria._sells_to_buys` fora de `hunter_indicators`, e o schema já aceita `NULL`/`NULL`
  para um nome ainda não decodificado.
- `lab.py` fechou exatamente em 350 linhas outra vez; qualquer campo novo em `LabState` exige split
  antes (o mesmo aviso que a nota T4.35 deixou, ainda vale).
