---
tags: [revisao-astra, seguranca, meme, carteiras, copia, piloto, h-037, pumpfun, nats, fonte]
date: 2026-10-09
updated: 2026-10-09
status: registro
owner: exchange-integration-specialist
decided_on: 2026-10-09
by: astra
tarefa: correção dos achados da revisão de segurança R1 (commit 4ca1055f, REQUEST_CHANGES; credencial limpa) e da revisão de código R2 da fonte de líderes do piloto de cópia (H-037)
veredito: R1 aceita integralmente (1 HIGH, 3 MEDIUM, 4 LOW de código); 2 revisões da Astra sobre a correção (9 e 7 pontos, todos aceitos e corrigidos com teste); a fila finita e o teto da memória (LOW-1) saíram junto; restam duas pendências nomeadas abaixo
---

# Segurança da fonte de líderes: o que a R1 achou, o que foi corrigido, o que a Astra ainda apontou (09/10/2026)

Contexto: [[copy-leader-source]] (a fonte e suas três rodadas) · decisão de uso: [[2026-10-06-nats-da-pumpfun-no-projeto-das-carteiras]] · piloto: [[2026-10-09-piloto-copiar-carteiras-no-papel]] · termos aceitos: [[2026-10-06-rea-na-pumpfun-apesar-dos-termos]] (parar no primeiro bloqueio). Lido antes: [[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes]]. Brutos: `.claude/state/astra-review-sec-copy-leader-source.md` (a Astra leu o commit, não a correção), `…-fix.md`, `…-fix2.md` (9 pontos) e `…-fix3.md` (7 pontos).

**A credencial estava limpa** (só em memória, nunca em log/exceção). Os achados eram sobre um servidor/pagina hostil ou doente, e sobre o que a fonte faz quando é recusada.

## Achados da R1 e correções

| Id | Achado | Correção (teste que falhava antes) |
|---|---|---|
| HIGH-1 | `MSG … -100\r\n` fazia `push()` girar para sempre; `-1` engolia o PING seguinte | `NatsParser` recusa tamanho < 0, `hdr` < 0 ou > tamanho, tamanho > teto, linha sem fim, CRLF ausente depois do payload e `MSG`/`HMSG` com número errado de campos (inclusive o comando sozinho) → `NatsProtocolError` → a conexão cai com a lacuna `nats_protocol_error` |
| MEDIUM-1 | `_rest` sem limite; `max_queue=None` | teto = `max_payload` do INFO (só pode baixar; duro 8 MiB, padrão 1 MiB) + folga; `max_queue=64`, `max_size=2 MiB` no `websockets.connect` |
| MEDIUM-2 | cada quadro malformado cancelava a semente e a reiniciava com `attempt=0` (3 chamadas RPC cada) | `SeedPolicy` por fonte: uma semente em voo é reaproveitada (marca `dirty` e pede **uma** de acompanhamento), intervalo mínimo de 5 s por carteira, backoff de falha e **prazo do backoff** (`next_at`) sobrevivem a novos gatilhos e à reconexão; vale também para o silêncio (uma por calmaria) |
| MEDIUM-3 | página inicial 5xx/403/429 usava a escada rápida e ignorava `Retry-After`; jitter antes do teto | 5xx e 401/403/418/429 da página (e do handshake) = `NatsRefused` na escada **lenta** (60→600 s), `Retry-After` em segundos **ou data HTTP** honrado até 24 h; jitter depois do teto (primeira espera ≥ 60 s; no teto o jitter desce); **3 recusas seguidas de credencial fresca** (recusa HTTP, ou auth com credencial recém-lida) param o lado NATS por **≥ 1 h** (e nunca antes do prazo do servidor), com `system_event` `leader_nats_stopped` e a lacuna `nats_stopped`; a cadeia segue cobrindo. Credencial **reaproveitada** recusada = rotação, não conta |
| LOW-2 | uma chamada já na fila do balde do `SolanaRpcClient` saía durante a pausa do guard | `SolanaRpcClient.set_pre_send_hook` (padrão sem efeito, mudança mínima em `rpc.py`) + `attach_guard`; qualquer 5xx também pausa (`is_blocking`) |
| LOW-3 | carteira com `*`, CRLF ou espaço chegava a um `SUB`; sem teto | `validate_wallets`: base58 de exatamente 32 bytes, **≤ 24** (20 da regra + 4 do Everton), erro que não repete o texto; vale nas três pontas (NATS, cadeia, combinador) e no `recompose` |
| LOW-4 | `LOG_LEVEL=DEBUG` + `WEBSOCKETS_MAX_LOG_SIZE` registraria o `CONNECT` com a senha | logger `websockets` fixado em WARNING; máscara **inteira** de `"pass":"…"` (aspas duplas e simples, escapes) e de `://user:senha@`; chave exata `pass` na máscara por chave; sem ReDoS (a regex de userinfo ancora em `://`) |
| LOW-1 | memória: `_held`, filas e buffer do socket sem teto | `OverflowQueue` finita (20 000) nas três filas com **episódio** de lacuna (`<nome>_overflow` aberta no primeiro descarte, fechada quando a fila cai à metade), lacunas coalescidas além de 2×teto **sem perder** a abertura nem o fechamento; `BalanceBook` com teto de 4 096 ativos por carteira (a semente é recusada **inteira**, e a união com o já aprendido também), lacuna `nats_baseline_overflow` |
| LOW-5 | páginas cruas da pump.fun no repositório | não é meu (o orquestrador tratou: `2854e492`) |

## Revisão de código R2 (junto)

`status_of` — razão desconhecida (inclusive `not_a_trade`) = `rpc_error`, nunca `divergent` · supervisor das tarefas filhas da cadeia (`chain_*_crashed`, reinício com backoff, recuperação REST) · saída por transferência derivada dos saldos (`kind='transfer'`, só queda de posição, só com logs legíveis; também de **outro mint** na mesma transação de um swap) · regra de `transfer` na NATS só com as pernas de SOL **e** WSOL vistas e nenhuma pagando (venda na PumpSwap paga em WSOL deixa de virar `leader_transfer`) · `nats_silent` re-semeia **uma vez por calmaria** · `recompose(wallet, start, end) -> Recomposition` (até 1 000 assinaturas, ordem pela **listagem** e não pela assinatura, incompleto explícito: `signature_cap`, `list_failed`, `tx_not_found:n`, `logs_partial:n`, `tx_unreadable:n`, `rpc_refused`).

## Astra sobre a correção

- **Rodada 1** (`…-sec-copy-leader-source.md`): ela leu o commit 4ca1055f em vez da árvore e confirmou a R1 (mais o teto de memória como MEDIUM). Sem efeito sobre o código.
- **Rodada 2** (`…-fix2.md`), 9 pontos: **a minha mudança em `logging.py` tinha desaparecido da árvore** (alguém desfez; reaplicada); parser ainda engolia quadro sem CRLF / com campos errados; recomposição devolvia `complete=True` omitindo a saída de outro mint e swap sem linha de lamports; ordenação por assinatura fabricava a posição final no mesmo slot; `OverflowQueue` continuava ilimitada para lacunas e adiava o aviso; `HELD_MAX` não valia para a semente; o prazo do backoff morria com a sessão; 5xx do RPC não pausava; `Retry-After` por data/> 1 h ignorado. **Todos aceitos e corrigidos com teste.**
- **Rodada 3** (`…-fix3.md`), 7 pontos: **ReDoS quadrático** na regex de userinfo que eu mesmo introduzi (3,6 s para 16 000 caracteres) · senhas curtas e `'` dentro de JSON passavam · `MSG`/`HMSG` sem argumentos sumiam · fila ilimitada para intervalos **fechados** e lacuna aberta descartada fabricava recuperação · união semente + aprendido furava o teto · a terceira recusa ignorava `Retry-After` > 1 h. **Todos aceitos e corrigidos com teste** (mais as duas notas de documentação).
- **Não houve rodada 4** sobre a última correção: está coberta por testes (1 444 + 91 verdes), mas **não revisada** pela Astra. Dito aqui para não parecer aprovação.
- A premissa "a listagem do RPC vem do mais novo ao mais antigo também dentro de um slot" a Astra confirmou na documentação e no código do Agave (v1.18+); **não validei o backend do provedor pago**. Se ele não garantir, a recomposição deve declarar `intra_slot_order_unknown`.

## Pendências nomeadas

1. **Tarefas de confirmação em voo** são limitadas pela taxa × 30 s, não por contagem (a Astra aceitou como melhoria futura, não bloqueio).
2. **`nats_silent` e a pista** (herdado de [[copy-leader-source]]): a regra congelada do desenho transforma inatividade normal em lacuna; decisão do desenho/orquestrador.
3. **Perda do `logging.py` na árvore:** durante esta tarefa o arquivo compartilhado (e o teste dele) voltou ao estado do commit sem eu tocar (a regra de árvore compartilhada proíbe `restore`/`checkout`). Quem integrar deve conferir `git diff packages/core/hunter_core/logging.py` antes do commit.

## Relacionados

[[copy-leader-source]] · [[2026-10-06-nats-da-pumpfun-no-projeto-das-carteiras]] · [[2026-10-09-piloto-copiar-carteiras-no-papel]] · [[EXP-M28-copiar-carteiras-no-papel]] · [[pumpfun-rt-latency]] · [[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes]]
