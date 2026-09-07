# Revisão adversarial — T3.1b (`296f3c1`), T3.6 (`9a0ac45`), T3.12 (`ae2657d`) — APPROVE_WITH_NITS (code-reviewer, 2026-09-07; Astra indisponível)

Sondas SQL como os papéis reais em Postgres próprio até a 0006; mutações matam os testes pelo motivo certo; 48 unit verdes.

## DEVE CORRIGIR (antes da T3.5/T3.8)
1. **`admission/dedupe.py:94-105` + `service.py:188-201`** — `by_idempotency_key` casa também um pedido ainda não decidido (`status='pending'`, `risk_decision='{}'`) e `RiskDecision.model_validate({})` explode com 10 erros; no modelo da T3.1c (API registra o pedido, worker admite) a ordem manual nunca seria decidida. Correção: `find_admitted` só considera linhas decididas; o worker **decide a linha existente** em vez de inserir outra. → **T3.5** (+ `decided_at` fabricado em `service.py:115`, sugestão 9).
2. **`apps/api/hunter_api/services/admission.py:129-187`** — roda a admissão inteira como `hunter_app`; com a 0007 vira 500. Correção: o adaptador registra o pedido (`source='manual'`, `status='pending'`) e o execution-worker admite. → **T3.5/T3.8**.
3. **`infra/migrations/ddl/paper.py:411-417` `_OBSERVED_EQUITY`** — o teto do pico conta snapshot de qualquer resolução; a curva operacional é só `1m` (`curve.py:36`). Um roll-up 1h/1d futuro com máximo do período sobe o teto, o pico nunca cai, a carteira fica `TRADING_DISABLED` para sempre. Correção: `resolution = '1m'` no subselect. → **T3.1c** (se não entrar, follow-up imediato).
4. **`docs/RISK_ENGINE.md:592` e `docs/plans/M3.md:136`** ainda dizem "uma principal por workspace"; a 0006 é por organização. → T3.1c/docs.
5. **`risk/transitions.py:146-160`** — nenhuma transição publica `kill_switch.changed` (`publish=False` em todos os chamadores); o contrato exige reação < 1 s. Destravado pela 0007 (worker tem INSERT em outbox). → **T3.5** (o worker publica após `evaluate_and_persist`) e a API na retomada (via pedido ao worker).

## SUGESTÕES
6. `daily.py:207-216` rotula `equity <= 0` como `UNAVAILABLE_STALE_OBSERVATION` (motivo mentiroso na evidência).
7. `transitions.py:282-286` `organization_kill_switch` devolve `ACTIVE` quando a linha não é visível (fail-open; inalcançável hoje).
8. `routers/risk.py:171-186` `ConcurrentTransition` não traduzida (500).
10. `resume.py:320` caixa inventado = patrimônio quando o ponto não traz caixa.
11. Duas transições da mesma carteira numa transação: mensagem culpa o movimento errado; adicionar ramo "moveu mais de uma vez".
12. `is_arena=true` é porta lateral sem OWNER/auditoria e `participation.py` chaveia o orçamento por carteira (cada arena ganha orçamento próprio no mesmo mercado — pré-requisito de "trava própria" do contrato não existe). Hoje só o script cria carteira; registrar para a T3.13/M4.
13. Corrida `expired × consumed`: no caminho do fill, `ReservationCycleClosed` = "a reserva morreu, não liquide", nunca retentável. → condição da **T3.5**.
14. `Settings.system_kill_switch` por processo: o `GET .../risk/kill-switch` deveria dizer de qual processo veio `system`.

## Handoff para a T3.1c
`packages/core/tests/integration/{admission_fixtures.py, test_risk_kill_switch.py}` gravam `portfolio_equity_snapshots` como `hunter_app`; com a 0007 (revoga esse DML) ficam vermelhos — as fixtures têm de escrever como `hunter_worker`.
