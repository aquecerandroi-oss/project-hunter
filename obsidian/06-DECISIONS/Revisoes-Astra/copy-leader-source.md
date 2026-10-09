---
tags: [revisao-astra, meme, carteiras, copia, piloto, h-037, pumpfun, nats, fonte, contrato]
date: 2026-10-09
updated: 2026-10-09
status: registro
owner: exchange-integration-specialist
decided_on: 2026-10-09
by: astra
tarefa: a fonte de líderes do piloto de copiar carteiras no papel (tarefa A, packages/exchange-adapters/hunter_exchanges/pumpfun/leader_source*.py) e a emenda 0b do contrato leader_events.py
veredito: três rodadas, todas REQUEST_CHANGES (12 achados na 1, 10 na 2, 7 na 3); tudo o que tinha cenário concreto foi consertado com teste, exceto duas pendências registradas abaixo (espera interna do limitador do cliente RPC; consequência do silêncio na pista)
---

# Revisão da Astra: a fonte de líderes do piloto (09/10/2026)

Código: a [[2026-10-09-piloto-copiar-carteiras-no-papel|decisão do piloto]] pede acompanhar ~20 carteiras ao vivo pelo canal por carteira da NATS ([[2026-10-06-nats-da-pumpfun-no-projeto-das-carteiras]]), com o fallback on-chain obrigatório e lacuna explícita. A fonte é `NatsLeaderSource` (+ `leader_source_nats_{wire,state,session,io}.py`), `ChainLeaderSource` (+ `leader_source_chain_{run,derive,fetch}.py`, `leader_source_rpc_guard.py`) e o combinador `CombinedLeaderSource`. Lido antes: [[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes]], [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro]], [[pumpfun-rt-latency]] e o desenho `docs/design/copiar-carteiras-papel.md` §2. Brutos: `.claude/state/astra-review-copy-leader-source.md`, `…-r2.md`, `…-r3.md`.

## O que a base ensinou e mudou no plano

- **O canal por carteira manda saldos absolutos, não swaps** (KB-0186): o delta e o lado saem do saldo anterior. Daí a semente (`getBalance` + `getTokenAccountsByOwner`) com corte de slot por ativo, a espera limitada pela perna de SOL e a regra "sem baseline, sem evento".
- **O KB-0186 mediu o canal de saldo ~0,34 s DEPOIS do `logsSubscribe` do mesmo slot.** "Milissegundos" aqui é o nosso trecho em processo (recv → fila), não vantagem sobre a cadeia: o ganho potencial da NATS é pequeno e não demonstrado. A confirmação on-chain e o caminho dos logs existem justamente por isso.
- **Decimais:** a NATS manda o saldo em decimal de UI. Mints da pump têm 6; o wSOL tem 9 (apareceu como `malformed` na primeira corrida live, 148 de 2 581 quadros). Outra escala é contada (`unsupported_scale`) e não é lacuna.

## Rodada 1 — 12 achados

| # | Achado | Decisão |
|---|---|---|
| 1 | SOL desconhecido virava 0 e eliminava uma compra válida | **Aceito.** `sol_delta_lamports: int \| None` (emenda 0b); compra espera ≤ 300 ms pela perna de SOL, venda sai na hora |
| 2 | Confirmação PumpSwap podia confirmar transferência como trade | **Aceito.** Só vale evento de swap atribuído à carteira (`read_transaction_logs`); logs ilegíveis ≠ "sem trade" |
| 3 | Semente com o menor slot fabricava delta | **Aceito.** Corte de slot por ativo; perna com slot ≤ corte é `stale` |
| 4 | Recuperação pulava transações (âncora avançava) | **Aceito.** Âncora congelada enquanto degradado, paginação, retries, lacuna `chain_recovery_failed` |
| 5 | A interseção de quedas escondia perda da NATS | **Aceito.** Toda lacuna de filha passa com a razão própria + `no_coverage:…` quando as duas perdem |
| 6 | Notificação anterior ao registro do id some no cliente | **Aceito em parte.** Âncora lida antes do subscribe + backfill; `state.dropped` vira alarme. O cliente (`rpc_ws.py`) não é meu |
| 7 | 401/403/418 do RPC entravam na escada de retry | **Aceito.** `RpcGuard` + pausa + `system_event` |
| 8 | Confirmação negativa encerrava a chave | **Aceito.** `LeaderConfirmation` sempre emitida; falha ⇒ uma segunda chance quando a rota de logs prova a tx |
| 9 | Carimbo do follow-up dependia de quem vencia | **Aceito.** `first_seen_at` preservado; `confirmed_at` separado |
| 10 | Fechar não cancelava fetches; estados expulsos | **Aceito.** Tarefas vivas separadas do cache; nunca se expulsa pendência |
| 11 | `detail=str(exc)` podia vazar a credencial | **Aceito.** Só a classe da exceção; teste com senha sintética no texto |
| 12 | Módulo NATS com 366 linhas | **Aceito.** Dividido; nenhum módulo passa de 307 |

## Rodada 2 — 10 achados (todos aceitos)

Multi-mint on-chain levantava exceção antes de tirar o SOL; mint ausente do snapshot herdava baseline anterior (a Astra achou que **o meu próprio teste consagrava o erro** `+5`); logs parcialmente legíveis escondiam trades; o cool-down não alcançava a chamada na fila nem o seed e a listagem; `_trim` expulsava pendências; o prazo de 300 ms dependia da ordem dos callbacks; silêncio por carteira; lacunas instantâneas são intervalos vazios (`[start, end)` não cobre nada); ausência de âncora confundida com recuperação; escada de 8 tentativas contra "até 3 em 30 s". Corrigidos com teste: `ChainRead.partial`, `TxFetcher` (reconfere a pausa dentro do slot), `RpcGuard`, `loss_gap` (≥ 1 ms), reset de baseline + ressemear na perda, `nats_silent`, `_newest` com três estados.

## Rodada 3 — 7 achados

| # | Achado | Estado |
|---|---|---|
| 1 | Prazo de 30 s não incluía fila e RPC; 8 tentativas contra "até 3" | **Consertado.** 3 tentativas (0, +1 s, +6 s), `wait_for` com o prazo restante cobrindo slot + chamada |
| 2 | O guard checa a pausa antes das esperas internas do limitador do cliente (`rpc.py:105`) | **Aberto, não é meu arquivo.** Precisa de um gancho "pré-envio" em `SolanaRpcClient._call` (3 linhas) — registrado para o orquestrador |
| 3 | Leitura parcial: confirmar o mint oculto dava `divergent`; `unresolved` sumia; evento saía antes da lacuna; SOL inteiro para um mint | **Consertado.** parcial ⇒ `rpc_error/logs_partial`; `unresolved` ⇒ `partial`; lacuna antes dos eventos; parcial ⇒ SOL `None` |
| 4 | `_first`/`_tokens` expulsos com pendência viva | **Consertado.** Nunca se expulsa chave com pendência |
| 5 | Voltar do silêncio fecha a lacuna sem baseline nova | **Consertado de outro jeito:** a semente é refeita **quando o silêncio é anunciado**, não quando a carteira volta (refazer na volta perderia justamente o 1º trade); teste com venda perdida no silêncio |
| 6 | Histórico vazio no corte nunca era retomado | **Consertado.** Depois de corte vazio ainda há backfill (tudo que aparece é novo) |
| 7 | `PostReserves` recusava reserva virtual negativa (i128) | **Consertado.** Só `virtual_quote_reserves` pode ser negativo |

## O que ficou sem resposta (e quem decide)

- **Espera interna do limitador do `SolanaRpcClient`** (item 3.2 acima): uma chamada já passada pelo guard pode sair durante a pausa se o balde do cliente estiver vazio. Mitigação atual: baldes com folga e RPC pago.
- **`nats_silent` e a pista.** A regra do desenho (silêncio > 60 s numa carteira ativa na última hora ⇒ lacuna) transforma inatividade normal em lacuna; `copy_book.py` marca `gap_reason` na cópia aberta e não desfaz ao fechar, então uma compra seguida de dois minutos de espera "contamina" a cópia mesmo com as duas fontes saudáveis. Não mudei a regra congelada: é decisão do desenho/orquestrador (ver relatório).
- **Confirmação depois da lacuna:** a pista não reavalia a cobertura pelo `block_time` quando a confirmação chega; falta teste integrado dessa fronteira (pista C).
- **Número de tentativas:** o desenho diz "até 3 tentativas em 30 s"; está implementado assim (0, +1 s, +6 s). Se o orquestrador preferir mais tentativas cedo, é um parâmetro (`retry_delays_s`).

## Relacionados

[[2026-10-09-piloto-copiar-carteiras-no-papel]] · [[2026-10-06-nats-da-pumpfun-no-projeto-das-carteiras]] · [[EXP-M28-copiar-carteiras-no-papel]] · [[copy-leader-selection]] · [[pumpfun-rt-latency]] · [[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes]] · [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro]]
