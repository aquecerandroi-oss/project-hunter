# Revisão obrigatória — T3.5 execution-worker (`7ecafd2`) — risk-engine-guardian, 2026-09-07 — DOIS BLOQUEIAM

Reproduzido em Postgres real (0008) com script isolado; 19 testes verdes; PnL, dupla contagem, fill fabricado, kill switch, pico com marca obsoleta, live: **corretos**.

## BLOQUEIA
1. **`entry.py:88-93` — proposta com reserva vencida é executada.** O `SELECT` filtra `status='approved' AND reservation_state='held'` e ignora `reserved_until`; `eligible_for` só exige livro posterior à decisão. Reproduzido: aprovada 15:30:00, executada 15:35:00 (270 s após a tenure). Correção: `AND reserved_until > :now` no SELECT e expirar a reserva na mesma transação quando vencida; teste.
2. **`protection.py:74-120` — o ciclo de proteção não trava a carteira** (só `positions`/intenções); `build_portfolio_state` lê caixa e posições em leituras separadas (READ COMMITTED) → MTM escreve equity 18.148,25 onde a verdade é 19.903,89 (−8,78 %) → BLOQUEADO latchado só o Everton destrava; ordem inversa infla o pico monotônico. Docstring `protection.py:3-5` e a mensagem do commit afirmam a trava que não existe. Correção: `effective_state(lock=True)`/`load_locked_state` no início de `run_protection_cycle` (sistema → org → carteira), antes de `load_open_positions`; docstring corrigida; teste com duas sessões.

## DEVE CORRIGIR
3. **Pó do spot mata a moeda e uma vaga para sempre** (`positions.py:232-240`, `entry.py:212-218`, `ledger.py:132`): `closing` com `qty > 0` conta em `slots_used`, exposição e `duplicate_position`; nada limpa. Reproduzido: 4 h depois do stop, `slots_used=1`, segunda ordem na moeda recusada. **Decisão (orquestrador, delegação):** resíduo abaixo de `min_qty` **não é posição**: não conta vaga, exposição nem duplicidade; continua **visível** e **valorizado** no patrimônio pela marca como "pó"; assentamento: quando o pó acumulado da moeda ≥ `min_qty` (ou `min_notional`), a proteção o vende junto da próxima saída ou num ciclo de varredura diário; até lá, `positions.status='closing'` + intenção `blocked_residual` é o marcador (coluna `positions.is_residual` pedida à T3.1e). Registrar em PIPELINE §8 e na página da carteira (T3.8c: "pó").
4. `admission_cycle.py:106-120` — `pending_request_without_geometry` é warning por linha por segundo para sempre (86.400/dia por pedido). Emitir na transição (linha nova) ou com janela; o gauge já cobre.
5. `protection.py:224-283` + `triggering.py:96` — proteção degradada grava uma linha `orders` por segundo sem fim e `_applied_attempts` refaz um UNION crescente. Backoff (1 s → 60 s) ou reutilizar a identidade da tentativa enquanto o motivo for "sem livro".
6. `cycles.py:66-72` + `config.py:79` vs `risk/daily.py:49` — `every()` dorme 60 s **depois** do trabalho; o ponto de MTM pode cair fora dos 60 s anteriores à virada em São Paulo → referência diária indisponível o dia inteiro (0,5–3 % dos dias, mais restarts perto da meia-noite). Alinhar à grade de minuto e/ou gravar um ponto extra imediatamente antes da virada.

## SUGESTÕES
7. Expiração audita só "reserved_until reached"; guardar o último motivo de adiamento (`avg_price_not_collected`, `no_book`, `book_before_latency`).
8. Linha `pending` arquivada sem digest: o motor carimba o seu — a ponte T3.14 tem de escrever o digest no INSERT.
9. Testes: execução tardia (item 1); §11 no **fill** (org bloqueada entre decisão e ordem).
10. Flaky `WinError 64` no teardown com dois arquivos testcontainers no mesmo processo.
