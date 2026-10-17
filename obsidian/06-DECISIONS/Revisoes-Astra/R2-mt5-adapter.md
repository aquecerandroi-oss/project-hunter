---
tags: [revisao-astra, b3, mt5, rico, robo, adaptador, execucao, exchange-adapters, mercado-tradicional]
date: 2026-10-17
updated: 2026-10-17
status: registro
owner: exchange-integration-specialist
decided_on: 2026-10-17
by: exchange-integration-specialist + astra
tarefa: "R2 do desenho docs/design/robo-b3-mt5.md §9 — adaptador MT5 (porta Mt5Port, conversão Decimal↔float, would_delete_stop, vigia da especificação, tabela de retcodes, falso do MT5 e suíte de contrato)"
veredito: "1 rodada sobre o diff. 8 must-fix (2 CRITICAL, 6 HIGH) mais lacunas; todos reproduzidos pela Astra contra o falso e todos aceitos e corrigidos com teste. Duas lacunas respondidas sem mudar o código (UNREADABLE limpa com leitura boa; SpecPin completo é composição de R5). Não certifica a semântica da Rico (T7, T8, T9, T13, T14 decidem) nem autoriza dinheiro real"
---

# Revisão da Astra — adaptador MT5 (R2)

**Pedido:** revisar `packages/exchange-adapters/hunter_exchanges/mt5/`, `packages/exchange-adapters/tests/mt5/` e o
falso em `services/b3-robot/tests/fakes/` contra o contrato congelado `docs/RISK_ENGINE_B3.md` (commit `5e71f345`).
Fonte bruta: `.claude/state/astra-review-R2-mt5-adapter.md`. As guardas G1–G7, o claim e a atribuição são de R5 e não
foram cobrados de R2.

**Notas lidas antes e o que mudaram:** [[00-HOME]] (toda entrada passa por proposta e motor de risco; o robô B3 é uma
quarta operação com motor próprio); [[Execution Engine]] (linha B3: nenhuma ordem direcional de saída, um só remetente,
nenhuma mutação sem identidade e autoridade); [[Revisoes-Astra/R0a-risk-engine-b3|R0a-risk-engine-b3]] (a tabela de
retcodes fechada por ação, `position_id` ≠ ticket, piso de proteção, `floor_unplaceable`); [[KB-0149-o-que-a-mesa-real-ensinou]]
(§4.20–§4.21: o que para sem alarme é o que mais custa → trava `ipc_hung` e resultado tardio que não se perde).
Nenhuma estratégia mudou nesta tarefa (nenhuma nota de `--note` necessária).

## Must-fix (todos reproduzidos por ela contra o falso; todos aceitos)

1. **CRITICAL — a fila executava mutação depois de `ipc_hung`.** A trava era conferida só na admissão: A trava, B
   (`order_send`) espera na fila, A volta e B sai com a trava ligada. **Correção:** o trabalhador marca `started` sob
   trava e **pula** o que foi abandonado ou o que estava na fila quando a pista travou ("trabalho que não começou nunca
   começa depois"); o prazo estourado de um trabalho não iniciado o abandona sem travar a pista; `Mt5IpcTimeout.started`
   diz se pode ter havido efeito (`False` ⇒ `Mt5NotSent("guard_ipc_hung")`, `True` ⇒ `UNCERTAIN`). Testes: três em
   `test_ipc_and_secrets.py`.
2. **CRITICAL — cancelar a coroutine abandonava um envio possível sem rastro.** `asyncio.CancelledError` não era tratado;
   a ordem executava depois e nada era guardado. **Correção:** cancelamento (e prazo) de uma **mutação já iniciada** deixa
   a pista `unresolved`: nenhuma mutação nova (`guard_unresolved_send`) até o chamador recolher o resultado tardio em
   `drain_late_results()`. R5 deve tratar `CancelledError` num envio como `unknown`.
3. **HIGH — piso inexequível chegava ao terminal.** `sltp_refusal` não via o toque. **Correção:** `send_sltp` lê o tick e a
   guarda recusa `sl_wrong_side_of_touch` / `tp_wrong_side_of_touch` (com `trade_stops_level × point`), `quote_invalid` e
   `quote_unavailable`/`quote_unreadable`. É o "nenhum envio" do contrato §4.2/§4.4 (R5 mapeia o pedido que carrega o piso
   em `floor_unplaceable`).
4. **HIGH — resultado tardio devolvia o objeto cru** (um `account_info` tardio carrega `login` e `server`). **Correção:**
   `LateResult` não guarda o objeto cru; só o que o `on_late` do adaptador produz (um `SendOutcome` normalizado com
   `error="late_result"` para `order_send`; `None` para leituras) e o nome do tipo da exceção.
5. **HIGH — dado malformado virava margem.** `float(True)` = 1. **Correção:** `decimal_from_number` recusa `bool`,
   `NaN`/`inf`, texto e `None`; `calc_margin` e `order_check` (margem e margem livre) viram `Mt5ReadError(malformed:…)`.
   Junto, o I-$-1: nenhuma chamada a `float()` fora de `convert.py`/`builders.py`/`parse.py` (teste por AST).
6. **HIGH — o falso ensinava a identidade errada na inversão *netting*.** Eu havia modelado dois negócios e um
   `position_id` novo; ela, citando a ajuda oficial, afirma que o identificador **fica** e o ticket muda. **Correção:**
   modelo A é o padrão (um negócio `DEAL_ENTRY_INOUT`, mesmo `position_id`, ticket novo — também é o que o contrato §4.2
   pressupõe) e o modelo B ficou como gancho (`hooks.reversal_new_identifier`). **Não consegui confirmar na fonte oficial
   (sem rede nesta tarefa): é pergunta aberta para a sessão demo** — o robô v1 nunca inverte de propósito.
7. **HIGH — a virada do pregão no falso mantinha os stops.** `end_of_day()` agora zera `sl`/`tp` das posições (§4.4);
   teste de contrato: a posição atravessa, perde o stop, e o reparo é uma SLTP nova.
8. **HIGH — patrimônio do falso ignorava comissões** (variação −1 contra negócios líquidos −5). Agora a comissão de cada
   negócio entra no saldo; o autoteste reconcilia `Δsaldo = Σ(profit + commission)`.

Lacunas menores aceitas: `position_id` das ordens do falso agora é preenchido no fill; faixa de conversão declarada
(≈ 1 bilhão de passos; fora dela o valor é exato **ou** recusado, nunca outro número) com dois testes.

## Onde discordei ou só registrei

- **`UNREADABLE` limpa com uma leitura boa que bate com o pin; `CHANGED` não.** Ela notou que "só o `rearm` limpa" não vale
  para os dois. O contrato (§3.9 do desenho e check 23) trava a **divergência**; `spec_unreadable` é "3 falhas
  seguidas", função da contagem consecutiva — uma leitura boa que confere com o pin é exatamente a verificação que
  faltava. Mantido, com a distinção escrita no módulo e nos testes (`test_spec_watcher.py`).
- **`SpecSnapshot` não é o `SpecPin` completo** (faltam `order_lifecycle_proven`, `comment_preserved`,
  `stale_ticket_rejection_proven`). Correto: são evidências da sessão demo (T14, T8, T13); R5/R1 compõem com o snapshot
  no armamento. Escrito na docstring; sem mudança de código.

## Como foi verificado (e a honestidade sobre o TDD)

Os módulos puros (constantes, retcodes, conversão, guardas, vigia, import lazy) nasceram test-first com o vermelho
visto (`ModuleNotFoundError`). O adaptador e o falso foram escritos contra o contrato **antes** da suíte de contrato —
desvio do ciclo; compensado com **28 mutações** de produção e do falso (16 + 12 após esta revisão), cada uma
precisando derrubar a suíte: as três que sobreviveram na primeira rodada das correções (trabalho em fila) mostraram
testes fracos, que foram reescritos até todas morrerem. As correções desta revisão tiveram o teste escrito antes
(vermelho visto em guardas e fronteira de `float`).

## O que a base aprendeu

1. **Prazo de uma chamada IPC não é prazo de uma ordem.** O que importa é se a chamada *começou*; trabalho em fila que
   não começou tem de ser descartável, senão a trava de IPC trava só os outros.
2. **Cancelar o `await` não cancela a chamada ao terminal.** Um envio cujo aguardador desistiu é `unknown` até alguém
   recolher o resultado.
3. **Um objeto cru do fornecedor nunca atravessa a fronteira, nem como "resultado tardio":** `account_info` carrega
   `login` e `server`.
4. **`float(True)` é 1.0.** Campo numérico de resposta externa passa por um conversor que recusa `bool`.
5. **Um falso que reconcilia só o lucro bruto ensina R5 a ignorar custo** (KB-0149: 72 % do prejuízo foi custo).

## Perguntas abertas para a sessão demo (T-provas)

`positions_get`/`orders_get` vazios devolvem `()`, não `None`; `history_orders_get(ticket=…)` desconhecido devolve `()`;
`order_check` aprova com `retcode 0`; a inversão mantém o `POSITION_IDENTIFIER`; o `time` do tick é o relógio do servidor
(T11). O contrato `live` (`HUNTER_LIVE_TESTS=1`, `HUNTER_LIVE_MT5_SYMBOL`, só conta DEMO) responde às quatro primeiras.

## Relacionadas

[[Execution Engine]] · [[Exchange Adapters]] · [[Revisoes-Astra/R0a-risk-engine-b3|R0a-risk-engine-b3]] ·
[[Dialogos/robo-b3-mt5]] · [[KB-0149-o-que-a-mesa-real-ensinou]] · contrato `docs/RISK_ENGINE_B3.md`
