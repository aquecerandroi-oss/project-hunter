# Notas T3.15b — bridge gate imports `PURPOSE_PAPER` e admite `paper`

Despachada para o backend-specialist em 2026-09-07; o agente travou no meio (invalid tool call após 692 s) mas deixou o diff completo e correto nos arquivos. A Sexta-feira validou rodando os gates.

## Entregue

1. **`bridge_screen.py`**: o portão (linha 232) agora recusa `live` **por nome** com motivo `live_forbidden` (mensagem "live é Fase 4; ENABLE_LIVE_TRADING=false"), recusa `research_only` como antes, recusa rótulos desconhecidos como `unknown_purpose` (fail-closed), e admite `paper`. Importa `PURPOSE_PAPER` e `PURPOSE_RESEARCH_ONLY` de `hunter_core.strategies.envelope`. `PURPOSE_LIVE` permanece definido localmente para a comparação da recusa.
2. **`shadow_builders.py`**: `PURPOSE_LIVE` trocado por `PURPOSE_PAPER` importado de `hunter_core.strategies.envelope`.
3. **`metrics.py`**: docstring de `bridge_candidates_total` atualizada com os novos motivos (`live_forbidden`, `unknown_purpose`).
4. **`docs/PIPELINE.md`** §8: item novo descrevendo o portão da ponte (admite `paper`, recusa `live` por nome, `research_only` como sempre, `unknown_purpose` para rótulos desconhecidos, `ENABLE_PAPER_AUTONOMY` default `false`).
5. **Testes**: todos os `purpose=shadow.PURPOSE_LIVE` trocados por `purpose=shadow.PURPOSE_PAPER` nos caminhos admissíveis. Dois testes novos:
   - `test_a_live_signal_is_refused_live_forbidden`: emite sinal `purpose="live"`, asserta `refused == "live_forbidden"`.
   - `test_an_unknown_purpose_is_refused_unknown_purpose`: emite sinal com propósito desconhecido, asserta `refused == "unknown_purpose"`.

## Saída real

```
test_bridge_eligibility.py      14 passed in 70.13s
test_bridge_refusal_dedupe.py    5 passed in 4.11s
test_bridge_consumer.py          3 passed in 37.39s
test_bridge_cycle.py             7 passed in 83.80s
ruff check                       All checks passed!
ruff format --check              60 files already formatted
pyright services/execution-worker  160 errors, 0 warnings  (todos pré-existentes em test_restart_recovery.py, não tocado)
check_file_size                  scanned 465 files; 0 over budget, 0 grandfathered
```

## Decisões de desenho

- **`unknown_purpose`** (não no brief): o subagent adicionou um terceiro ramo para rótulos não reconhecidos em vez de os deixar cair em `research_only`. É fail-closed e está correto — um rótulo que não é nenhum dos três known não deve passar.
- **`message=` no `_refuse`**: o subagent passou `message="live é Fase 4; ..."` como kwarg extra, que o `report_refusal` repassa para o log estruturado. Não é um campo que o `Screened` usa, apenas aparece no log — aceitável.
- **`PURPOSE_LIVE` permanece em `bridge_screen.py`**: definido localmente (linha 75) para a comparação da recusa. Não é mais o caminho admissível; é o caminho recusado por nome.

## Revisões obrigatórias

- **risk-engine-guardian**: não rodou (Astra fora até 12/09; cota do Codex esgotada). Pendente.
- **security-reviewer**: idem. Pendente.
- Astra: idem.

Nada foi ativado. Nenhuma linha `paper` existe em banco nenhum.
