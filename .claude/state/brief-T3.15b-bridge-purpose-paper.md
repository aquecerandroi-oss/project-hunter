# Brief T3.15b — bridge gate imports `PURPOSE_PAPER` and admits `paper`

**Owner:** backend-specialist. **Revisores depois (obrigatórios):** risk-engine-guardian, security-reviewer. **Não commitar.** **Regra operacional: nunca Bash em background; comandos em primeiro plano com timeout ≤ 5 min; suítes com testcontainers um arquivo por invocação; Astra indisponível até 2026-09-12.** Base: `main` em `0db5fbb`.

## Contexto

A T3.15 (commit `6b837ac`) adicionou a constante `PURPOSE_PAPER = "paper"` em `packages/core/hunter_core/strategies/envelope.py:41` e fez o portão de admissão (`admission/sources.py:263-275`) recusar `live` por nome e aceitar `paper`. Mas o **portão da ponte** (`bridge_screen.py:219`) não foi atualizado — ele ainda admite `live` (linha 61 define `PURPOSE_LIVE = "live"`) e recusa todo o resto como `research_only`. É o **inverso** do que deveria: a ponte deve admitir `paper` e recusar `live` (Fase 4) e `research_only` (shadow).

Hoje nenhum sinal tem `purpose=paper` (nenhuma linha `paper` existe em banco), então a ponte não admite nada — coerente com "nada ativa". Mas o portão está logicamente errado e precisa estar certo antes da ativação (D10, sete condições).

## Leia antes

- `packages/core/hunter_core/strategies/envelope.py:33-53` — `PURPOSE_PAPER`, `PURPOSE_RESEARCH_ONLY`, docstrings
- `packages/core/hunter_core/admission/sources.py:62-68,263-275` — `PURPOSE_LIVE` recusado por nome, `PURPOSE_PAPER` aceito
- `services/execution-worker/hunter_execution_worker/bridge_screen.py:57-64,219-220` — o portão atual, que aceita `live` e recusa o resto
- `services/execution-worker/tests/shadow_builders.py:35-36` — `PURPOSE_LIVE` definido para os testes
- `services/execution-worker/tests/test_bridge_eligibility.py` — todos os testes usam `purpose=shadow.PURPOSE_LIVE` para o caminho admissível
- `services/execution-worker/tests/test_bridge_refusal_dedupe.py:49` — `purpose="live"` no signal do teste de dedupe
- `services/execution-worker/tests/test_bridge_consumer.py:79` — idem
- `services/execution-worker/tests/test_bridge_cycle.py` — idem (6 usos)
- `.claude/state/notes-T3.15.md` §"Pendências" — descreve exatamente esta tarefa

## Entregar

1. **`bridge_screen.py`**: trocar `PURPOSE_LIVE` por `PURPOSE_PAPER` importado de `hunter_core.strategies.envelope`. O portão (linha 219) passa a:
   - Se `signal.purpose == PURPOSE_LIVE`: recusar com motivo `purpose_live_forbidden` (mensagem: "live é Fase 4; ENABLE_LIVE_TRADING=false"), **por nome**, com `purpose=signal.purpose` no log.
   - Se `signal.purpose != PURPOSE_PAPER`: recusar com motivo `research_only` como hoje (mantém o nome — todo sinal não-paper e não-live é shadow).
   - Se `signal.purpose == PURPOSE_PAPER`: passar (candidato).
   - Remover `PURPOSE_LIVE = "live"` da linha 61 e do `__all__` (linha 57). Importar `PURPOSE_PAPER` de `hunter_core.strategies.envelope`.
2. **`shadow_builders.py`**: trocar `PURPOSE_LIVE = "live"` (linha 35) por `PURPOSE_PAPER = "paper"` importado de `hunter_core.strategies.envelope`. Atualizar a docstring (linha 36).
3. **Testes**: em todos os testes onde `purpose=shadow.PURPOSE_LIVE` era o caminho admissível, trocar para `purpose=shadow.PURPOSE_PAPER`. Onde o teste exercita a recusa de `research_only`, manter. Adicionar:
   - Um teste que verifica que `purpose=live` é recusado com motivo `purpose_live_forbidden` (não `research_only`).
   - Um teste que `purpose=paper` passa a porta (candidato, não recusado).
   - No teste de dedupe (`test_bridge_refusal_dedupe.py:49`), trocar `purpose="live"` para `purpose="paper"` no signal do helper.

## Arquivos permitidos

- `services/execution-worker/hunter_execution_worker/bridge_screen.py`
- `services/execution-worker/tests/shadow_builders.py`
- `services/execution-worker/tests/test_bridge_eligibility.py`
- `services/execution-worker/tests/test_bridge_refusal_dedupe.py`
- `services/execution-worker/tests/test_bridge_consumer.py`
- `services/execution-worker/tests/test_bridge_cycle.py`
- `.claude/state/notes-T3.15b.md` (relatório)

## Provar

```
uv run pytest services/execution-worker/tests/test_bridge_eligibility.py -q -p no:randomly
uv run pytest services/execution-worker/tests/test_bridge_refusal_dedupe.py -q -p no:randomly
uv run pytest services/execution-worker/tests/test_bridge_consumer.py -q -p no:randomly
uv run pytest services/execution-worker/tests/test_bridge_cycle.py -q -p no:randomly
uv run ruff check services/execution-worker && uv run ruff format --check services/execution-worker
uv run pyright services/execution-worker
uv run python infra/scripts/check_file_size.py
```

Nada em `.env*`, `infra/migrations/**`, `packages/core/**`, `apps/**`. Relatório em português no formato estendido com saída real; `.claude/state/notes-T3.15b.md`.
