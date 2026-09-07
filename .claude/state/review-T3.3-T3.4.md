# Revisão adversarial — T3.3 (`8a6a69f`) e T3.4 (`edd5d7e`) — REQUEST_CHANGES (code-reviewer, 2026-09-07)

Rodado: `portfolio` + `execution` unit 148 passed; 4 mutantes em memória matam a suíte pelo motivo certo. Scripts de cenário no scratchpad do orquestrador (`t33_fx.py`, `t34.py`, `t34b.py`).

## BLOQUEIA
1. **`execution/triggers.py:187-198` (e `:175-177`) — um print inválido no lote apaga um stop já tocado.** `check_triggers` valida o lote inteiro antes de procurar cruzamento; qualquer print malformado (`received_at` no futuro por relógio de outro host, `trade_id` não numérico, `ts` futuro) devolve `unavailable` e descarta os válidos: `[100@90]` → `triggered`; `[100@90, 101 received_at=now+2s]` → `unavailable`. No ciclo seguinte o 90 está `stale`. Posição fica sem proteção. **Correção:** avaliar o cruzamento sobre o prefixo validado e reportar a indisponibilidade do resto (ou `triggered` + "resto indeciso"). Teste com lote misto.
2. **`execution/intents.py:263` — `apply_attempt` não é idempotente:** reaplicar o mesmo `ExecutionReport` soma o fill (0,4 → 0,8); com `intended_qty = 0,8` a redelivery marca FULFILLED com 0,4 ainda na posição. **Correção:** `filled_qty` derivado da soma dos fills por `attempt_id` (jornal) ou `apply_attempt` recusa `attempt_id` já aplicado (`applied_attempts`). Teste de redelivery na intenção (o existente só conta linhas na entrada).
3. **`portfolio/opening.py:140-141` — `FxPolicy` não tem banda de plausibilidade do valor:** `rate = 1e-10` credita 10^15 USDT com CHECK fechando; erro de escala do coletor (0,54321 em vez de 5,4321) abre com 184.081 USDT e é **irreversível** (âncora imutável, D7). **Correção:** banda declarada e versionada na `FxPolicy` (`USDTBRL`: `1 ≤ rate ≤ 100`, motivo escrito) + teste; opcionalmente comparação com a última observação aceita.

## DEVE CORRIGIR
4. `execution/adapter.py:11-13` docstring diz que a T3.3 aplica o relatório; ninguém aplica ainda (T3.5). Corrigir o texto.
5. `portfolio/ledger.py:187-247` + `db/repositories/equity.py:40-78` — `brl_unavailable_reason` e `stale_marks` não são persistidos (só em memória); linha gravada com `fx_observation_id = NULL` indistinguível. Mínimo: `AuditEvent`/log estruturado na recusa + dívida de coluna para a T3.1b/T3.10.
6. `db/repositories/portfolio.py:47-62` — escopo `(organization_id, workspace_id)` duplicado à mão; a T3.1b move a permanência para `(organization_id)`; alinhar numa constante só e a mensagem de `WalletAlreadyOpen`.
7. `portfolio/opening.py:215-221` — ramo de corrida (`IntegrityError` → `WalletAlreadyOpen` por substring do nome do índice) sem teste com duas transações concorrentes.
8. `execution/triggers.py:204-233` — `not_triggered` publicado com preço abaixo do stop quando o negócio ≤ watermark; reportar `already_reported`/`unavailable`.
9. `execution/paper.py:94-96,148-150,238-239` — replay por `entry:{proposal_id}` devolve o relatório antigo mesmo com `qty` diferente; falhar alto ou `replayed=True` + `requested_qty` divergente.

## SUGESTÕES
10. `pricing.py:158-164` `mark_price` reimplementa validade (sem `received_at ≤ now`); usar `usable_trade`.
11. `book_walk.py:168` `BookLevel.price` sem `gt=0` → `ValidationError` escapa; recusar `non_positive_level` no `eligible_book`.
12. `portfolio/state.py:285` `costs += qty*price` fora de `LEDGER_CONTEXT`.
13. `portfolio/state.py:139-141` exposição soma sem olhar direção; asserção long-only.
14. `opening.py:176` `capital_brl` parâmetro: fixar 100.000 no serviço e recusar outro valor (diretiva §1).
15. `PERCENT_PRICE_BY_SIDE` parseado e nunca usado; aplicar ou declarar por quê com fonte.
16. `test_opening_policy.py:49,52` dois testes sem `assert`.

## Correto
`floor_10dp_v1` fecha o CHECK em 20.000 taxas aleatórias incl. 3,5; identidade BRL; `unavailable` terceiro veredito; `LiveExecutionAdapter` sem caminho de fill (teste de AST do grafo de imports); sem float/sleep/print; módulos ≤ 350.
