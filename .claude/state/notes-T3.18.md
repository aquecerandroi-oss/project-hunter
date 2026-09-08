# Notes — T3.18 (Lab scoreboard)

## API (backend-specialist, 2026-09-08)

**Entregue:** itens 1, 2, 6 (parte `apps/api`) e 7 do brief.

**Endpoints novos**, ambos globais/no-RLS como o resto do Shadow Lab (DATABASE.md §16 —
`agent_signals`/`signal_outcomes`/`strategy_versions` não têm `organization_id`; não há schema
change no escopo desta entrega para acrescentar um):

- `GET /api/v1/lab/shadow/scoreboard?as_of=` — uma linha por `strategy_version` que **já emitiu**
  pelo menos um sinal até `as_of` (não "toda versão ativada" — uma versão sem sinal na população
  congelada não aparece). Campos: `version` (id/key/version/purpose/status/activated_at/code_ref),
  `emitted`, `evaluable`, `pending`, `no_entry`, `censored`, `distinct_days`, `distinct_markets`,
  `hit_rate`/`net_profit_rate` (com `numerator`/`denominator`), `expectancy_r`, `profit_factor`,
  `sum_r`, `worst_streak`, `max_drawdown_r`, `maturity` (`{evaluable, days, threshold, mature}`),
  `verdict` (`inconclusivo|validada|reprovada`).
- `GET /api/v1/lab/shadow/curve?version_id=&as_of=` — série `[{ts, r, cum_r}]` de todo outcome
  **resolvido** (terminal, `r_multiple` não nulo), ordenada por `exit_ts`, capada em 2000 pontos
  (`truncated`). Deliberadamente **não** aplica o portão de maturação do horizonte
  (`is_evaluable()`): esse portão existe para não enviesar estatística agregada, não para recortar
  uma trajetória.

**Decisão registrada (path fora do padrão `/orgs/{org}/...` do brief):** o brief pedia
`/orgs/{org}/lab/{scoreboard,curve}`. Implementei em `/api/v1/lab/shadow/{scoreboard,curve}` —
mesmo prefixo dos outros três endpoints do Lab (`/versions`, `/summary`, `/signals`), porque
Shadow Lab é global por desenho documentado (DATABASE.md §16: "Nenhuma tabela nova é de tenant...
sem `organization_id` e sem RLS"). Colocar estes dois sob `/orgs/{org_id}/...` exigiria uma
migração fora do escopo desta entrega e contradiria a arquitetura vigente. Ver CONCERNS no relatório
final para o pedido de confirmação ao quant-engineer/database-architect/Everton.

**Reuso, não reinvenção:** toda a matemática de `hit_rate`, `net_profit_rate`, `expectancy_r`,
`profit_factor`, `sum_r` e o portão de maturação (`is_evaluable`) vêm de
`lab_summary_metrics.py`/`lab_summary.py` (S3), literalmente as mesmas funções que já reproduzem o
SQL do plantão (EXP-0001/EXP-0002). Só `worst_streak`, `max_drawdown_r` e o veredito mecânico são
novos (`lab_scoreboard_metrics.py`).

**Arquivos:**
- `apps/api/hunter_api/repositories/lab_scoreboard.py` (novo)
- `apps/api/hunter_api/services/lab_scoreboard_metrics.py` (novo — pure math)
- `apps/api/hunter_api/services/lab_scoreboard.py` (novo — assembly)
- `apps/api/hunter_api/services/lab_curve.py` (novo — assembly)
- `apps/api/hunter_api/schemas/lab_scoreboard.py` (novo)
- `apps/api/hunter_api/schemas/lab_curve.py` (novo)
- `apps/api/hunter_api/routers/lab_scoreboard.py` (novo — router próprio para não estourar o
  budget de 350 linhas de `routers/lab.py`)
- `apps/api/hunter_api/routers/lab.py` (modificado — `_resolve_as_of` virou `resolve_as_of`,
  público, para ser reusado pelo router novo; comportamento idêntico)
- `apps/api/hunter_api/app.py` (modificado — registra o router novo)
- `apps/api/tests/unit/test_lab_scoreboard_metrics.py` (novo — 18 casos)
- `apps/api/tests/integration/test_lab_scoreboard_api.py` (novo — 15 casos, testcontainers)
- `docs/plans/SHADOW-LAB.md` (modificado — seção "Placar (T3.18)")
- `packages/shared-types/src/generated/api.d.ts` (regenerado via `pnpm gen:types`;
  `packages/shared-types/openapi.json` não é rastreado — não foi commitado)

**Testes:** `uv run pytest apps/api/tests/unit -q -p no:randomly` → 406 passed. Novo arquivo unit
(18 casos) e integração (15 casos, um arquivo por invocação) verdes isoladamente. `ruff
check`/`ruff format --check` limpos em `apps/api`. `pyright` limpo nos arquivos tocados (rodar
`uv run pyright` sem escopo no repo inteiro aponta ~2348 erros pré-existentes em
`services/execution-worker/tests/**`, alheios a esta entrega — T3.15c está em voo nesses arquivos).
`check_file_size.py`: nenhum arquivo novo/tocado acima de 350 linhas (maior é
`repositories/lab_scoreboard.py` com 132).

**Achado, não corrigido (fora do escopo desta entrega):** `test_lab_api.py::
test_summary_counts_and_metrics_over_a_mixed_population` já falha em `main` antes desta entrega —
`decimal_plain()` (`schemas/lab_common.py`) remove zeros à direita ("0.5000" vira "0.5"), mas o
teste espera a string com zeros. Não toquei em `lab_common.py` nem em `test_lab_api.py`; meus testes
novos já usam a forma correta (sem zeros à direita).
