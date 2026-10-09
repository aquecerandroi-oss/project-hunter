---
tags: [revisao-astra, meme, copiar-carteiras, h-037, exp-m28, papel, ligacao, flag]
date: 2026-10-09
updated: 2026-10-09
status: registro
owner: backend-specialist
decided_on: 2026-10-09
by: astra
tarefa: tarefa F do desenho de H-037 — ligar a pista de cópia no meme-worker atrás de MEME_COPY_LANE (off|paper)
veredito: "REQUEST_CHANGES por um ponto (orçamento de RPC compartilhado); o ponto vira pré-condição operacional documentada, não código desta tarefa — o resto absorvido"
---

# Revisão da Astra: a flag `MEME_COPY_LANE` (tarefa F do H-037)

Liga a pista de cópia ([[copy-lane]], `copy_wiring.start_copy_lane`) e a fonte de líderes (NATS + cadeia) ao
`TaskGroup` do `meme-worker`, desligada por padrão. Código: `services/meme-worker/hunter_meme_worker/copy_main.py`
e quatro linhas em `main.py`. Experimento: [[EXP-M28-copiar-carteiras-no-papel]]. Como ligar:
[[03-TRADING/Meme/README|README do Meme]], seção "Pista de cópia no papel". Transcrição bruta (fonte citada, não
o registro): `.claude/state/astra-review-copy-wiring-main.md`.

## O que foi lido antes e o que mudou no plano

- [[00-HOME]] e o [[03-TRADING/Meme/README|README do Meme]]: a convenção do `meme-worker` é uma chave por pista
  (`MEME_LAUNCH_LANE`, `MEME_EVENT_GATE`) lida do ambiente em módulo próprio porque `config.py` está no teto de
  350 linhas, com valor desconhecido lido como `off` e um aviso. Segui a mesma forma, com dois valores só.
- [[EXP-M28-copiar-carteiras-no-papel]]: tudo é papel, a pista é `research_only`, nada vira ordem. Por isso **não há
  valor `on`/`live`**.
- [[copy-lane]]: a pista fica inerte sem conjunto `copy_v0` ativo e só abre a fonte depois da recuperação
  (`CopyFleet.run`). Isso é o que torna `paper` sem a semente (tarefa E) inofensivo: nenhuma conexão NATS/WS abre.
- O código, contra o texto do autor da pista: `build_leader_source(rpc, feed)` pede um objeto com `.call`;
  `RadarContext.chain` é tipado `ChainSource`, que **não** tem `.call` (a instância é um `SolanaRpcClient`, mas o
  tipo não diz). Passar `ctx.chain` não passaria no pyright e acoplaria a pista ao tipo concreto.

## Decisões de código (com o motivo)

| Decisão | Motivo |
|---|---|
| `SolanaRpcClient` **dedicado** para as confirmações; a pista continua precificando por `ctx.chain` | `ChainSource` não tem `.call`; as confirmações (`getTransaction`, `getSignaturesForAddress`, semente de saldos) não gastam o balde da cadeia do radar |
| Fonte e feed **novos a cada `stream()`** (`_RenewedLeaderSource`), um `LeaderSourceStats` compartilhado | `ChainLeaderSource.stream` fecha o feed no `finally` e `SolanaWsClient.aclose()` é definitivo (`_closed = True`, `listen()` sai do laço): reusar a fonte depois de uma falha ou de uma troca de conjunto deixaria a cadeia surda sem erro |
| Supervisor em volta de `start_copy_lane` (`CopyLaneRuntime.run`) | `run_copy_lane_forever` já reinicia a frota, mas uma exceção fora dela (ex.: o `heartbeat` do Redis levantando em `_inert`) subiria ao `TaskGroup` e derrubaria o radar |
| `build_copy_lane` devolve `None` antes de tocar o contexto quando a flag não é `paper` | com `off` nada é construído nem aberto, e o teste prova com construtores que explodem |

## O que a Astra apontou

- **Must-fix (HIGH): orçamento de RPC compartilhado.** O cliente dedicado tem baldes próprios e o cooldown de 429
  não é visto pelos outros. No endpoint público, com `MEME_WATCH_WALLETS` ligado, o observador de carteiras
  (`wallets_state.py:99`, também com cliente e balde próprios) e a pista chamam os mesmos métodos e podem somar
  além da cota do IP.
  - **Decisão: absorvido como pré-condição, não como código desta tarefa.** O raio é o mesmo que o radar já tem hoje
    (três clientes `SolanaRpcClient` com baldes independentes: `ctx.chain`, o do observador e agora o da pista); um
    orçamento agregado com cooldown compartilhado é uma mudança no adaptador (`SolanaRpcClient`), fora dos arquivos
    desta tarefa. Escrito no README do Meme: **rodar `paper` com `SOLANA_RPC_URL` pago**. A taxa de 429 da pista
    **não foi medida**; deve ser olhada no ensaio antes de T0, e a mudança do adaptador, se ela pedir, é tarefa nova.
- **Nice-to-have, aceitos:** a garantia "nunca derruba o `TaskGroup`" foi reescrita para "isola exceções
  operacionais" (`SystemExit`/`KeyboardInterrupt` passam de propósito); o teste de Redis falhando em `_inert`
  fica coberto pelo teste genérico de crash do supervisor (a exceção sobe do `start_copy_lane` do mesmo jeito).
- **Nice-to-have, não feito:** cancelamento com a composição real NATS → sessão → socket usando transportes falsos.
  Os testes do adaptador cobrem o fechamento dos filhos; o desta tarefa cobre o do invólucro. Fica para o ensaio.
- **Construção antes do `try` e ordem do fechamento:** `SolanaRpcClient()` só monta um `httpx.AsyncClient` (sem
  conexão) e `close_clients` já captura por cliente; não mudei.

## Onde concordo e onde discordo

Concordo com o diagnóstico do feed único e com `Exception` como fronteira do supervisor. Discordo só de tratar o
cliente dedicado como causa do problema: sem ele a pista disputaria o balde da cadeia do radar, que é o mais escasso. O risco real é a cota do
endpoint, e esse é operacional.

## Relacionados

[[copy-lane]] · [[copy-leader-selection]] · [[EXP-M28-copiar-carteiras-no-papel]] · [[Fila de Hipoteses]] ·
[[Revisoes-Astra/Index|índice das revisões]]
