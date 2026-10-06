---
tags: [revisao-astra, meme, pumpfun, carteiras, leaderboard, seguidores, h-030]
date: 2026-10-06
updated: 2026-10-06
status: registro
owner: exchange-integration-specialist
decided_on: 2026-10-06
by: astra
tarefa: releitura da superfície pública da pump.fun (docs/PUMPFUN.md §10) e implicações para o H-030
veredito: REQUEST_CHANGES no texto e nas condições de uso pelo H-030 — 9 must-fix, todos aceitos (8 integralmente, 1 em parte: ela sugeria omitir POST; o orquestrador pediu o POST de leitura do PnL de holders e ele foi feito, declarado como o 3.º POST)
---

# Revisão da Astra: releitura da pump.fun de 06/10/2026

Tarefa: [[KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas]] e `docs/PUMPFUN.md` §10 (notas cruas em
`.claude/state/notes-pumpfun-releitura-2026-10-06.md`; capturas passivas do REA em `.claude/state/rea-pumpfun-capture-2026-10-06.md`). A revisão bruta é
`.claude/state/astra-review-pumpfun-releitura.md` (documental: ela leu as notas e o §10, não revalidou o site; o parecer foi dado sobre a versão **antes** da segunda captura do REA e do POST de PnL de holders).
Ela concordou com a direção (o quadro como pista prospectiva, C-PnL como critério, sem `username`, controle na fita, respeito a autenticação) e discordou da forma e das condições.

## O que ela disse e o que foi feito

| # | Achado (cenário de falha) | Decisão |
|---|---|---|
| 1 | "Continuam mortas", "404 de `/nats/token`" e "sumiu do registro" misturavam estado observado, contrato do bundle e ausência de teste; descartar fonte ainda usada ou tratar um HTTP nunca observado | **Aceito.** O §10 separa HTTP / bundle / REA / não testado; "mortas" virou "404 em 12/09; nada em 06/10"; `/nats/token` ficou "só no bundle, não chamado"; `/kols` e `livestream-api` ficaram "chamadas pelo navegador, resposta não verificada" |
| 2 | "Nova" e "mudou" não demonstram novidade desde setembro (`/following/v3/*/count`, `/mint-positions`, `/pnl-leaderboard/positions` já estavam no bundle de 12/09; Mayhem é conteúdo; o `Coin` não tem diff completo) | **Aceito e confirmado por `git show HEAD:docs/PUMPFUN.md`.** "Nova" → "ausente do mapa de 12/09" / "no mapa só como bundle, agora chamada"; Mayhem "igual (forma)"; `Coin`: "cinco campos antes não registrados foram observados, não é diff completo" |
| 3 | `holder-rewards` não prova `limit` ignorado; "grupo próprio" de limite não demonstrado; 15 B é uma resposta; 300 é a união da rodada; "âncora 02:00" é um palpite | **Aceito (todos retirados ou qualificados).** Conferi: `limit=3` devolveu 3 moedas. 11 B na contagem de seguindo. Os três `windowStartSec` terminam em 02:00 UTC |
| 4 | `buySpendSol ≈ 0` não prova "tokens recebidos"; `isVerified` não é o selo KOL do R61; sufixo `pump` não é classificador de programa | **Aceito.** E achei um fato que ela pedia para checar: o #1 semanal tinha `isVerified` true no quadro e `verified` false no `/overview` |
| 5 | Universo: se só as descobertas do site concorrerem ao top-30, o experimento mede "C-PnL dentro da seleção da pump.fun"; e `known_at` precisa respeitar o corte do retrato | **Aceito, entra no §10.4 e no KB.** Observação adicional rotulada; os controles vêm da fita inteira |
| 6 | Foto de seguidores: congelar fonte por campo, `known_at` por resposta, `degraded[]`; `is_verified` e `created_coins_count` descritivos | **Aceito.** Também: `followers/count` só cobre `followers`; as três fontes não coincidem (27 709 × 27 710) |
| 7 | `/user-trades`: reconciliação, retenção, tx + evento/perna, inventário de abertura, `received_at` | **Aceito.** Formulação: "800 trades de uma carteira, ~10 dias, cursor restante"; slot não identifica trade (corrigi "casar por slot") |
| 8 | `top-trader-trades`: só descritivo, sem poder confirmar; uma operação antiga devolvida hoje não era sinal | **Aceito.** Pré-declarado; hipótese confirmatória sobre o site exige protocolo próprio |
| 9 | "Descartados" × corpos brutos em pasta temporária; não é só GET | **Aceito.** Corpos apagados ao fim; §10 diz "três POST de leitura". Os agregados não são reproduzíveis de respostas preservadas, e isso está escrito |

Nice-to-have aceitos: colunas HTTP/bundle/REA/não testado; 10 d 1 h 11 min (≈ 10,05 dias) em vez de "10,1"; "as páginas de taxas conferem, on-chain não verificado".

## Divergências

- **Ela omitiria POST sob a regra de "só GET".** O orquestrador pediu a forma do `POST /pnl/coin/{mint}/holders` (leitura, anônimo, corpo copiado do bundle, 5 carteiras públicas da mesma moeda). Foi feito, com o corpo vindo do bundle e declarado no §10 e aqui. Concordo com ela no resto: nada de POST com sessão, nada de `/nats/token`.
- **O que ela sugeriu chamar e eu não chamei:** equivalência `/users` × `/overview` × `followers/count` numa carteira com zero seguidores e outra sem perfil, duas páginas de uma segunda carteira, repetição do quadro, `top-trader-trades` com `to`, `/candles?res=`. Fora do orçamento (64 unidades, já acima do "~60"); ficam como lista para a próxima leitura. Só o re-teste de `/coins/{mint}` foi feito (e deu 404).

## O que a Astra não viu e a releitura achou depois dela

- `GET /coins/{mint}` responde **404** em dois mints; `/coins-v3/{mint}` 200. O código já sabe desde ~25/09 (T4.97b/R80), mas `PumpFunRestClient.get_curve_state` ainda chama a rota. Isto veio do re-teste que a própria revisão provocou (item 1).
- `POST profile-api /pnl/coin/{mint}/holders`: `has_untrusted_basis` em 3 de 5 linhas.

## Relacionado

[[KB-0185-o-que-a-pumpfun-publica-sobre-carteiras-lucrativas]] · [[EXP-M15-carteiras-vencedoras]] · [[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]] · [[2026-10-05-carteiras-seguidores-como-pergunta-secundaria]] · [[wallet-tape-probe]] · [[Revisoes-Astra/Index|índice das revisões]]
