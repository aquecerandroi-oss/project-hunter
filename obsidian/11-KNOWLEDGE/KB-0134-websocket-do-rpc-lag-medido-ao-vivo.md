---
tags: [knowledge, nota, meme, pumpfun, websocket, rpc, latencia, m5]
tema: memecoin / pump.fun / websocket do RPC — lag confirmed 0,58 s, processed 0,42 s, cobertura 100 % logs×account
fonte: endpoint público wss://api.mainnet-beta.solana.com, 5 mints × 120 s, 18/09/2026
fonte_url: ""
lido_em: 2026-09-18
evidencia: medição própria (T4.52b-1 — infra/scripts/research/2026-09-18-t452b-ws-probe.py)
hipotese_testavel: não
astra: não consultada nesta nota
confiança: backtest do autor
owner: sexta-feira
updated: 2026-09-18
status: vivo
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# KB-0134 — WebSocket do RPC: lag `confirmed` 0,58 s, `processed` 0,42 s, cobertura 100 %

## O que afirma
Antes de construir o portão de evento (T4.52b), mediu-se ao vivo se `logsSubscribe`/`accountSubscribe`
da Solana entregam latência e cobertura suficientes para substituir o tique de 15 s do radar.

## Número
5 mints mais recentes, 120 s cada, endpoint público: em **`confirmed`** — `logs` p50 0,58 s / p95
0,61 s; `account` p50 0,53 s / p95 0,58 s. Em **`processed`** — `logs` p50 0,42 s / p95 0,44 s;
`account` p50 0,41 s / p95 0,44 s. **Cobertura: todo trade visto via `logsSubscribe` também apareceu
como mudança em `accountSubscribe` (overlap 100 %)**. Zero `429`, zero reconexões nas duas rodadas.

## O que muda na operação
Valida a escolha de desenho do T4.52b (WS do RPC keyed, não o PumpPortal pago): a latência medida fica
bem abaixo do orçamento de 0,5–1,5 s previsto no plano original, sustentando o alvo evento→proposta de
0,6–1,6 s p50. As fixtures gravadas nesta medição (`t452b_ws_{logs,account,slot}_notifications_raw.jsonl`)
alimentam os testes das tarefas seguintes (T4.52b-2/3).

## Relacionados
Atualização de 06/10/2026: o mesmo `logsSubscribe` público (`processed`) foi medido **contra** a NATS do site e o PumpPortal em [[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes|KB-0186]] — por par e não contra o segundo do bloco: a NATS chegou 0,14–0,16 s antes dele (mediana) e o HTTP do RPC público passou a responder 413 (cota de dados). Os 0,42 s daqui e os números "contra o bloco" de lá usam métodos diferentes e não se comparam.
`.claude/state/plan-T4.52b.md` · `.claude/state/notes-T4.52b-1.md` ·
[[11-KNOWLEDGE/KB-0124-latencia-de-decisao-e-o-alvo-de-milissegundos|KB-0124]]
