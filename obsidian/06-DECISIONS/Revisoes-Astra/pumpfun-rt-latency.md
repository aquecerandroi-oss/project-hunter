---
tags: [revisao-astra, meme, pumpfun, nats, latencia, medicao, h-030]
date: 2026-10-06
updated: 2026-10-06
status: registro
owner: exchange-integration-specialist
decided_on: 2026-10-06
by: astra
tarefa: sonda de latência do tempo real da pump.fun (NATS anônimo do site, boards, PumpPortal, logsSubscribe público) — desenho e código antes dos números finais; resultados, texto e correções depois
veredito: rodada 1 REQUEST_CHANGES no instrumento (7 pontos, 6 HIGH e 1 MEDIUM, todos aceitos e consertados com teste); rodada 2 REQUEST_CHANGES no texto e em pontos restantes (6 pontos, todos aceitos), tabelas principais reproduzidas por ela; a pergunta de escopo da credencial e do canal por carteira ficou com o Everton
---

# Revisão da Astra: a sonda de latência do tempo real da pump.fun (06/10/2026)

A medição e os números estão em [[KB-0186-o-tempo-real-da-pumpfun-chega-uns-0-1-s-antes-das-outras-fontes]]. Código em `infra/scripts/research/2026-10-06-pumpfun-realtime-latency*.py` e `infra/scripts/pumpfun_rt_probe_*.py`; as revisões brutas são `.claude/state/astra-review-pumpfun-rt-latency.md` (rodada 1, durante a corrida longa de 45 min) e `.claude/state/astra-review-pumpfun-rt-latency-2.md` (rodada 2, com os números das duas janelas). A pergunta de escopo está em [[2026-10-06-nats-da-pumpfun-escopo-da-credencial]].

## Rodada 1 — desenho e código

| # | Achado (cenário de falha) | Decisão |
|---|---|---|
| 1 | O RPC assina só o programa `pump`, mas a NATS trouxe trades `pump_amm` (842 de 2 857 quadros na leitura parcial): viravam "ausência do RPC" | **Aceito.** Só `pump` entra na comparação; `pump_amm` é contado à parte (`nats_programs`) e fica sem referência. Teste `test_pump_amm_trades_are_not_compared…` |
| 2 | A reconexão reescrevia a exposição (só o último `sub` por moeda): minutos saudáveis viravam "reprise" | **Aceito.** Lista de intervalos por assinatura, fechada por `UNSUB` ou pela próxima quebra de sessão; teste do segundo intervalo |
| 3 | `bt < sub_t − 2 s` não prova reprise e comparava com o relógio local sem offset | **Aceito.** Rótulo "replay-like", offset do `server-time` aplicado, sensibilidade com folga 0/2/4 s |
| 4 | Elegibilidade assimétrica: o RPC entrava pelo próprio recebimento e a NATS por outro critério; o vencedor da borda sumia | **Aceito.** Coorte simétrica (interior de 3 s) com a contraparte procurada na captura inteira; chegada só na borda não é par nem perda; teste da borda |
| 5 | Assinatura identifica a transação, não a perna: o saldo de uma carteira contava como entrega do trade de outra | **Aceito em parte.** Declarado "primeira notícia da transação"; saldo casado por assinatura + carteira. **Não feito:** identidade de perna além do programa (uma transação com duas moedas da pump conta como uma) |
| 6 | Falha de envio podia matar a expiração sem marcar a corrida como degradada; uma falha da CORE derrubava a UNIFIED | **Aceito.** `_send` não levanta, hook com erro é registrado, `guarded()` registra o crash da tarefa; testes. A corrida 1 já estava no ar com o código antigo; a corrida 2 usou o novo |
| 7 | O smoke não valida a análise (janela negativa) e as bordas censuravam deltas | **Aceito.** Janela vazia levanta `ValueError`; cohort no interior com contraparte na captura inteira |
| N | Nice-to-have: ISO sem fuso, `Recorder` com `"w"`, empate nos "chegou primeiro", "nunca wildcard" | **Aceitos**: ISO sem fuso recusado, `Recorder` com `"x"`, empate ≤ 10 ms, e a frase correta é "wildcard só no último componente (a moeda) de cada carteira". **Não feito:** fila limitada e drenagem após congelamento (o atraso do laço mediu p99 0,025 s; a captura se divide em qualquer parada > 60 s) |

Disputa de fundo que ficou assim: a Astra pede comparar com "o baseline efetivamente usado na VPS"; **não dá** sem a chave do RPC pago (nunca lemos `.env`). Fica como limite escrito na nota.

## Rodada 2 — resultados, texto e correções

A Astra recalculou os dois relatórios em memória: **as tabelas principais e as contagens batem integralmente** com os `report.json`.

| # | Achado | Decisão |
|---|---|---|
| 1 | "A NATS não traz informação que a cadeia não tenha" excedia um inventário de 4 amostras por grupo, só chaves de topo | **Aceito.** Título e texto trocados por "nas amostras examinadas…; equivalência não demonstrada"; proveniência de `solPriceUsd`, `is_banned` e atribuição marcada como não demonstrada |
| 2 | "Não reprisou histórico" e "0 % com folga 0/2/4 s" estavam errados: com folga 0 s são 2,28 % e 1,19 % dos quadros | **Aceito.** A sensibilidade publica a parcela por folga; texto: "0 % com 2 e 4 s; classificação temporal não prova reprise nem a ausência" |
| 3 | A população do KOL contava eventos `add` (readições) como moedas que "nasciam" com KOL (676 eventos = 587 moedas; 18 eventos, 2 moedas no primeiro add) | **Aceito.** `add_events_pump` separado de moedas distintas; medida no primeiro `add`; texto "observação desta sonda, não mede antecipação" |
| 4 | O saldo perdia a carteira depois do casamento (bug reproduzido: 2 esperadas, 1 entregue) | **Aceito.** Perna = assinatura + carteira também no numerador e no delta; teste. Sem efeito nos totais publicados (nenhuma assinatura teve duas carteiras esperadas) |
| 5 | A contraparte NATS depois do `UNSUB` + folga não era procurada (RPC "exclusivo" falso); `BREAKS` sem `send_failed`/`crashed`/`err` | **Aceito.** Só o quadro positivamente replay-like fica fora da busca; `BREAKS` ampliado; testes. Sem efeito nos pares publicados (cobertura 100 %) |
| 6 | "Empata" para o PumpPortal contra o RPC não era sustentado; "perde 10–12 %" escondia uma queda de 4,8 s; "sem parada" ≠ fontes ininterruptas; "não cria edge" descartava sem medir | **Aceito.** Rótulo "empata" retirado; "não observamos 10,3 % e 12,5 %" com a queda registrada; saúde por fonte no relatório; frase "não demonstramos benefício operacional ou econômico" |
| N | Nice: `<10 ms` × `≤10 ms`, graduação por coorte, saúde por fonte, "até um segundo de erro" | **Aceitos** (cabeçalho `≤`, coorte na graduação, `health`, nota sem o limite inventado) |

### A pergunta de escopo (e o que ficou com o Everton)

A Astra separou duas coisas: a credencial compartilhada que a home entrega ao navegador anônimo **não é** login pessoal nem contorno automático; mas "o servidor aceitar um assunto não demonstra que esse assunto, para qualquer carteira, pertença ao acesso normal do visitante anônimo". Ela teria parado **antes de ampliar para carteiras arbitrárias** e pedido o escopo. **Concordo e registro como falha minha:** o canal por carteira foi extensão minha além dos assuntos pedidos (novas moedas, trades, boards). Já havia parado em 20 carteiras. A decisão (parar, manter só o que a página da moeda faz, ou manter com decisão escrita) está na INBOX; a [[2026-10-06-rea-na-pumpfun-apesar-dos-termos|decisão de 06/10]] **não** foi editada.

## O que ficou sem resposta

- Medida contra o RPC pago/Geyser da VPS e da própria VPS (a região muda os atrasos).
- Checagem "segundo da NATS × `getBlockTime`" (o HTTP do RPC público passou a responder 413).
- Se `app`/`surface`/`surfaceAttribution`/`relayer` vêm preenchidos para rotas de terceiros.
- O limite de assinaturas por carteira do servidor.
