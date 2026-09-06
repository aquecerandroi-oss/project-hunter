# Notas de desenho — S3a (API do Shadow Lab)

Decisões tomadas ao implementar `.claude/state/brief-S3-lab-api.md`, com o contrato fixado em
`.claude/state/contract-S3-lab.md` (revisado pela Astra antes da implementação,
`.claude/state/astra-review-S3-lab-api-contract.md`, e depois com o diff,
`.claude/state/astra-review-S3-lab-api-diff.md`). Onde o brief ou o plano `docs/plans/SHADOW-LAB.md`
eram omissos ou colidiam com o schema já congelado pela S0, a escolha está aqui com o motivo.

## 1. `Evaluation.state` não existe no Postgres — `decisions` é `null`
O brief pedia contagens "por `Evaluation.state`". Essa classe
(`packages/core/hunter_core/strategies/base.py`) só existe em memória do `strategy-worker` — vira
métrica Prometheus (`health.record`, `services/strategy-worker/hunter_strategy_worker/consumer.py`)
e nunca uma linha durável; nem todo `TRIGGERED` vira sinal (um episódio desarmado ou já
acompanhando uma entrada absorve a decisão sem emitir nada — achado da Astra na revisão do
contrato). Resultado: `counts.decisions` é sempre `null` com `decisions_reason:
"evaluation_state_not_persisted"`; `counts.signals_emitted` é a única contagem de decisão que a
API pode honestamente afirmar. Da mesma forma, `coverage` não afirma nada sobre avaliações que
nunca viraram sinal — `coverage.markets_with_signals`, não "avaliados".

## 2. População financeira madura (gate de horizonte) — must-fix 2 da Astra
Toda métrica financeira (`target_rate`, `net_profit_rate`, `expectancy`, `PF`,
`sum_of_hypothetical_r`, bloco `r_ex_funding`) exige, além de `tracking_state='terminal'`, que o
horizonte tenha maturado até `as_of`: `meta.entry_plan.entry_bar_open + meta.horizon_s <= as_of`
e `exit_ts <= as_of` (cinto de segurança contra vazamento de futuro). Sem isso, uma janela recente
super-representaria stops rápidos frente a operações que ainda não tiveram chance de expirar —
cenário reproduzido em `test_summary_maturity_gate_excludes_a_fast_stop_before_its_horizon_elapsed`.
O gate é calculado em Python (`services/lab_summary_metrics.py::is_evaluable`), não em SQL: a
consulta busca por `strategy_version_id` + janela de `decision_at` e a maturação lê
`meta` (JSONB) por linha — aceitável no volume atual (centenas de linhas por versão); documentado
como pendência para `database-architect` se crescer.

## 3. `decision_at`/`cohort` não são colunas — são o envelope
S0 congelou o schema antes desta API existir; ambos vivem só em
`agent_signals.supporting_features` (imutável, escrito uma vez). `repositories/lab_common.py`
extrai via `->>'decision_at'`/`->>'cohort'` com `cast(..., DateTime(timezone=True))` para
filtro/ordenação/cursor. Sem índice de expressão — mesma pendência do item 2.

## 4. `superseded_by` é best-effort, nunca uma FK
`strategy_versions` não tem essa coluna; `infra/scripts/activate_strategy_version.py` só grava a
relação como texto livre no `changelog` da linha deprecated (`"superseded by v2 (code_ref ..."`)
e em `system_events`. `repositories/lab_versions.py` extrai a versão sucessora com uma regex
(`^superseded by (\S+)`) e resolve o id por `(strategy_id, version)`. A Astra confirmou (revisão do
contrato) que não há fonte melhor e que o campo nunca deve ser tratado como identidade —
`changelog` continua mutável.

## 5. Censura sem o terceiro segmento vira `gap:unknown`, nunca é descartada
O dado real local (`docker-postgres-1`, 2026-09-06) tem `censored_reason` como
`gap:2026-09-06T00:54:00+00:00` — sem o sufixo `:failed|:unregistered|:stalled` que
`notes-S2.md` §16 e o `gaps.py` atual escrevem. Um worker rodando uma imagem anterior a essa
correção gravou assim. `services/lab_summary_metrics.py::bucket_censored_reason` trata isso como
`gap:unknown` (contado à parte) em vez de descartar a linha ou quebrar — é dado real, não um bug
desta API. Reproduzido em `test_summary_counts_and_metrics_over_a_mixed_population`.

## 6. 503 do Postgres é uma dependência própria, não a `PrincipalSession` compartilhada
`routers/lab.py::lab_session` reimplementa o que `hunter_api.deps.principal_session` faz
(`user_session` + `app.current_user`, sem organização — pesquisa é global, DATABASE.md §16), só que
com um `try/except OperationalError` em volta do `yield`. Uma dependência FastAPI com `yield`
tem sua exceção pós-`yield` relançada exatamente no ponto do `yield` (mesmo mecanismo de um
`@contextmanager`) — por isso o `except` pega tanto uma falha ao abrir a transação quanto uma
falha em `session.execute(...)` já dentro do corpo da rota. Testado com `monkeypatch` no método do
repositório (não desligo o Postgres real: o container é compartilhado com toda a suíte de
integração, a mesma razão pela qual `test_system_workers_api.py` usa `WRONGTYPE` real em vez de
matar o Redis).

## 7. Métricas calculadas em Python com `Decimal`, não agregação SQL
O brief pede "métricas calculadas em SQL/Decimal (nunca float)". O gate de maturação do item 2
precisa ler `meta` por linha, o que inviabiliza uma agregação SQL pura sem uma expressão gerada; a
escolha foi buscar as linhas cruas (`repositories/lab_summary.py::outcomes_for`, filtradas por
`strategy_version_id` + janela de decisão) e fazer toda a contagem/soma em Python com `Decimal`
(nunca `float`) em `services/lab_summary_metrics.py`. Correto e testável (26 testes unitários sem
IO); mais caro que uma agregação SQL se o volume crescer — mesma pendência dos itens 2 e 3.

## 8. `funding_not_settleable`, não "indisponível"
Nice-to-have da Astra: uma liquidação zero comprovada produz um `r_multiple` válido
(`settle.py`), então "funding indisponível" seria falso para esse caso. O nome escolhido é
`funding_not_settleable`: matura, terminal, mas `r_multiple` ainda `null`.

## 9. PF sempre carrega o denominador explícito
Must-fix 3 (medium) da Astra: `profit_factor` agora sempre inclui `sum_positive`,
`sum_negative_abs` e `sample_size`, mesmo quando `value` é `null` — um PF nulo por falta de amostra
é uma população diferente de um PF nulo por falta de perdas, e o consumidor não deveria ter que
re-derivar as somas para saber qual é qual.

## 10. Excursões nunca são recortadas
`schemas/lab_signals.py::SignalListItemOut.excursions` é `dict[str, Any]` e passa
`signal_outcomes.meta.excursions` inteiro — unidade (`price`, nunca R), método, cobertura completa/
parcial, janelas de barra, risco inicial e preço de referência. Nice-to-have da Astra, aplicado.

## 11. TDD parcial, declarado
Os testes unitários de `lab_summary_metrics.py` (`apps/api/tests/unit/test_lab_metrics.py`) foram
escritos depois da primeira versão da implementação, não antes — dado o tamanho do desenho (duas
rodadas de reconciliação com a Astra antes de qualquer código), TDD estrito teria significado
escrever e reescrever os testes a cada rodada de contrato. Os testes de integração
(`test_lab_api.py`) foram escritos e rodados contra a implementação já existente, e um deles
(`test_summary_counts_and_metrics_over_a_mixed_population`) pegou um bug real de formatação
(`sum_positive`/`sum_negative_abs` sem quantização, `"1.5000000000"` em vez de `"1.5000"`) —
corrigido em `lab_summary_metrics.py::profit_factor`. Registrado como desvio do "escreva o teste
que falha primeiro" — a cobertura final é a mesma, a ordem não foi estritamente TDD em todo o
módulo.

## 12. `apps/api/tests/integration/lab_fixtures.py` é um arquivo novo, não uma extensão de `analysis_fixtures.py`
T2.6 está em voo nesse módulo (routers de radar/opportunities/anomalies/regime); o brief não lista
`analysis_fixtures.py` entre os arquivos permitidos. Um arquivo próprio evita qualquer conflito de
merge e mantém o escopo desta tarefa isolado.
