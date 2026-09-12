# Notas T4.15 — o fechamento diário do Lab meme (12/09/2026, início ~15:0x BRT)

Árvore em `2e14972` (T4.12 + T4.11 + T4.14) no início. A `0030_meme_gate_v2` (T4.16, paralela) **não
existia em disco** quando a `0031_meme_lab_ticks` nasceu (primeira versão revisava a `0029`); apareceu
durante a tarefa e o primeiro testcontainer acusou duas cabeças → a `0031` passou a revisar
`0030_meme_gate_v2` (a cabeça em disco no momento), cadeia linear. `HEAD_REVISION` em
`packages/core/tests/integration/test_migrations.py` continua `0029` — **não editei** (T4.16 mexe na
mesma linha); quem fechar as duas tarefas sobe para `0031_meme_lab_ticks`.

## 0. Leitura (o que o código já tinha)

- `meme_diary.py` gera as seções 1–5 e deixa a 6 como stub `(a preencher pelo arquivista — Sexta-feira)`;
  recusa reescrever nota existente (exit 2) e recusa dia sem aposta fechada sem `--allow-empty` (exit 3).
- `lab.py::lab_tick` guardava `state.refusals = {nome_do_conjunto: {motivo: n}}` só em memória e no heartbeat
  (`lab_gate_refusals`); nada durável por tick → a cobertura do dia não era reconstruível.
- `meme_diary_wallets.gather_wallets` já devolve as compras reais com `lab_verdicts` por conjunto (T4.12).
- Régua do vault: `obsidian_lint.py` exige frontmatter em toda nota, **nenhuma órfã** (todo diário datado
  precisa de link de entrada) e append-only nas seções datadas (`### Avaliação de <data>`) das EXP-*.
- A imagem `hunter-api` leva `infra/scripts` mas **não** `obsidian/` nem `.claude/state/` — `--apply` no
  `ops` só faz sentido com os dois bind mounts (DEPLOYMENT §3.6b); `compose.sh ops` não aceita opções do
  `run`, por isso o cron chama o `docker compose` diretamente com o que o `compose.sh` monta.

## 1. Desenho

- **`0031_meme_lab_ticks`**: `meme_lab_ticks` (PK `ticked_at`; `tick_minute`, contadores do `TickReport`,
  `refusals jsonb` = o dicionário do heartbeat). Global, sem RLS. `hunter_worker` SELECT/INSERT, `hunter_app`
  SELECT, DELETE a ninguém. Descida recusa com linhas (§17.7). Modelo ORM `MemeLabTick` (registro em
  `models/__init__.py`, só ADD) para o `alembic check`; classe de grants acrescentada em
  `test_schema_privileges.py` (só ADD).
- **Laço**: `lab_ticks.record_tick` (módulo novo) grava a linha na própria sessão `hunter_worker`, `ON
  CONFLICT DO NOTHING`; falha vira `warning` e o tick segue (a ausência aparece no diário como "sem ticks
  gravados"). Hunk em `lab.py`: o `TickReport` vira variável, `record_tick` antes do heartbeat (3 linhas + 1
  import); sobreviveu à reorganização da T4.16 (o testcontainer prova a linha gravada com as recusas do
  portão v2: `symbol_unknown`/`creator_unknown`).
- **Job** `infra/scripts/meme_close_day.py` (`--day`, padrão = ontem em Brasília; `--dry-run|--apply`;
  `--allow-empty`; `--vault-root`/`--state-dir` para testes) + `meme_close_stats.py` (IC 95 % por blocos de
  hora, bootstrap semente 20260912 × 2 000; contraste pareado; régua; tercis), `meme_close_lesson_kit.py`
  (modelos, células, veredito), `meme_close_lessons.py` (as 9 lições de regra), `meme_close_inputs.py`
  (dataclasses), `meme_close_render.py` (seção 6) + `meme_close_render_ops.py` (cobertura, operador, reais,
  leave-top-out, pré-registro), `meme_close_outputs.py` (linhas `M-L`, lote, avaliação EXP, índice),
  `meme_close_queries.py` (SQL como `hunter_app`). Todos ≤ 350 linhas.
- Régua para uma linha `M-L`: n ≥ 30 apostas fechadas, ≥ 3 blocos de hora, as duas células do contraste com
  n ≥ 10 e IC 95 % do Δ (pareado por blocos) fora de zero. Contraste das lições em bandas/tercis = a célula
  mais desviante contra as demais; das saídas = a saída que mais custou R contra as outras.
- Idempotência do `--apply`: diário existente com a seção 6 no stub → completa; seção 6 escrita → recusa
  (exit 2) antes de tocar em qualquer outra coisa; EXP/INBOX/README só recebem o bloco se o marcador do dia
  não existir; o lote não é sobrescrito.
- Órfãs: o job acrescenta a linha de índice em `Diario-Meme/README.md` ("## Diários gerados") para que o
  diário datado tenha link de entrada mesmo quando nenhuma lição passa a régua.

## 2. Provas rodadas (saída real no relatório)

- Unit: `test_meme_close_{stats,lessons,render,day}.py` — 17 passed.
- Testcontainer (`timeout 590`): `test_meme_close_day_integration.py` — 2 testes (tick real + `--apply` numa
  cópia do vault com `obsidian_lint.py` limpo, append-only provado com `check_exp_rewrite`, segunda execução
  recusada).
- `ruff check`/`ruff format --check`/`pyright` nos arquivos da tarefa; `check_file_size.py`; `obsidian_lint.py`
  no vault real (só as duas adições deliberadas: parágrafo `M-L` no INBOX e linha na tabela do README de
  Trading/Meme).

## 3. Preocupações para o relatório

- `HEAD_REVISION` (acima). `test_migrations.py`/`test_schema_privileges.py` completos não rodados (suíte
  pesada, fora do orçamento de um container); a privilégios ganhou a classe da tabela nova.
- `pyright` acusa `HEARTBEAT_PREFIX` redefinido em `lab.py` — vem da reorganização da T4.16
  (`lab_heartbeat.py`), não do hunk desta tarefa.
- Commit/push do que o cron escreve na VPS é decisão de operação em aberto (DEPLOYMENT §3.6b).
- Retenção de `meme_lab_ticks`: nenhuma ainda (~0,5 M linhas/ano), declarado em DATABASE §42.
