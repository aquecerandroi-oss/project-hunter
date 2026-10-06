---
tags: [knowledge, meme, pumpfun, pumpswap, rpc, helius, coleta, carteiras, onda-0, h-030]
tema: o que custa coletar o programa inteiro da pump.fun e da PumpSwap (volume, bytes, RPC público contra pago, carteiras distintas, linha no banco)
fonte: sondagem de leitura de 05/10/2026 desta máquina (infra/scripts/research/2026-10-05-wallet-tape-probe.py; saídas em .claude/state/carteiras-lucro/probe/run1, run2, run3), RPC público api.mainnet-beta.solana.com
fonte_url: https://www.helius.dev/docs/billing/credits
lido_em: 2026-10-05
evidencia: medição própria (144 min válidos em três janelas, dois horários, um dia) + preços públicos da Helius lidos em 05/10 (credits e pricing) + revisão da Astra em duas rodadas
hipotese_testavel: não (é medição de infraestrutura; serve ao H-030 e ao orçamento da onda 1b/2)
astra: concorda com a direção do go/no-go, discorda de "não cabe na VPS" (não demonstrado); 6 pontos obrigatórios da segunda rodada tratados — ver Revisoes-Astra/wallet-tape-probe
status: vivo
owner: exchange-integration-specialist
updated: 2026-10-05
confiança: "backtest do autor"
tipo: leitura
hipotese: —
variavel: eventos de swap/s, bytes/s, carteiras distintas, atraso do RPC público
populacao: programa pump (6EF8…) e PumpSwap (pAMM…) inteiros, segunda-feira 05/10/2026, 16h–20h BRT
efeito: —
ic: —
veredito: —
proximo_passo: piloto de WS pago por pelo menos um ciclo diário; decisão do Everton e do database-architect sobre retenção/formato antes da migração 1b
classe_de_perda: —
mercado: meme
---

# KB-0183 — O que custa coletar o programa inteiro da pump.fun e da PumpSwap (05/10/2026)

## O que afirma

Coletar **todos** os swaps das duas pontas é um problema de **volume**, não de decodificação: **330–353 eventos de
swap por segundo** (28,5–30,5 M/dia entregues; 31 M/dia pela contagem de blocos), 5 a 10 vezes a hipótese do desenho
([[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]]), e **217–254 GB/dia** de WebSocket sem compressão. O RPC **público**
aguentou duas janelas (39 e 15 min) e falhou numa de 90 min; o **pago** custa, por estimativa, **US$ 650–760/mês**. A
linha do banco, estimada em **529 B** com índices, leva a **136–149 GB em 9 dias**: o armazenamento aprovado (10–20 GB) não vale mais.
O desenho completo dos números é a seção 8 de `docs/design/seguir-carteiras-lucrativas.md`.

## Onde foi mostrado (próprio)

| Janela (UTC, 05/10) | Resultado |
|---|---|
| run 1, 19:03–20:34, 90,1 min válidos (a máquina dormiu 4 651 s depois) | PumpSwap: 60 quedas, atraso p50 até 112 slots (≈ 30 s), ~43 % do que a cadeia produziu; pump: 19 quedas, p50 3–69 slots |
| run 2, 22:01, 39,1 min | 0 quedas; atraso p50 0; auditoria por bloco **pump 6 314/6 320, PumpSwap 17 373/17 373** (as 6 faltantes são tx falhas) |
| run 3, 22:46, 15 min | 0 quedas; 353 swaps/s; 73 235 carteiras; 58 % com 1 swap; 29 % dos swaps < 0,01 SOL |

Decodificação: **0 falhas** em ~480 mil `TradeEvent` e ~730 mil `SellEvent` (layout de 02/10, T4.8e). O `BuyEvent` da PumpSwap é **36 %**
dos swaps e **ganhou decodificador na onda 1a** (KB-0184). Em três compras reais a carteira e a pool dele, lidas por deslocamento, batem com as contas 0 e 1 da instrução `buy`.

## O que a literatura/documentação diz

A própria Solana diz que seus endpoints públicos não são para produção (https://solana.com/docs/references/clusters). A Helius cobra o WebSocket
padrão por bytes sem compressão: **2 créditos por 0,1 MB**; Business US$ 499 por 100 M créditos, extras a US$ 5 por milhão
(https://www.helius.dev/docs/billing/credits, https://www.helius.dev/pricing, lidos em 05/10/2026; sujeitos a mudar).

## Como mediríamos aqui

Sondagem somente leitura (`logsSubscribe` por programa + `getSlot`, `getTransaction`, `getBlock` por HTTP lentos), decodificadores commitados, auditoria independente de
cobertura por `getBlock` julgada 180 s depois do fetch e contagem do que a cadeia emitiu independente do socket. Leitura: `…/2026-10-05-wallet-tape-probe-read.py --run <dir>`.

## Hipótese testável no Lab

Nenhuma: é infraestrutura. O piloto pago deve repetir a mesma auditoria de blocos sobre o provedor final.

## O que muda na operação

- **Nada liga.** Não há coletor 24/7; a onda 2 espera o piloto e a decisão de armazenamento.
- A medição do atraso em **slots** segue; as frases em **segundos** ("5 slots ≈ 2 s") precisam de nova conversão: o slot dura hoje **≈ 268 ms** (3,73 slots/s, `getRecentPerformanceSamples`), logo 5 slots ≈ 1,34 s.
- `getTransaction`/`getBlock` com `maxSupportedTransactionVersion = 0` falhavam quando há transação **versão 1** (13 % de um bloco amostrado): **corrigido** na onda 1a (`tx_rpc.py` e `rpc_wallet.py` passaram a `1`, [[Resolved Bugs]]; prova ao vivo e armadilhas do `BuyEvent` em [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro|KB-0184]]).

## Por que pode falhar

- Um dia, dois horários, segunda-feira; o RPC público degradou uma vez e a causa (horário, rota, balanceador, minha rede) não foi isolada.
- A linha de 529 B é fórmula por tipo de coluna, não tabela medida (WAL, TOAST e padding ficam fora); o custo da Helius é estimativa por preço de tabela, não fatura.
- Carteiras por dia: só cenários (Heaps 0,9–1,8 M; linear 1,7–5,3 M); a união inclui carteiras do `BuyEvent` lidas por deslocamento.
- Contagem de eventos nos logs bate com as inner instructions (1 099/1 099), mas identidade do payload não foi comparada.

## Segunda opinião (Astra)

[[wallet-tape-probe]] — duas rodadas: 7 pontos sobre o desenho da medição (antes da corrida) e 6 sobre o código e os resultados (depois).

## Relacionados

[[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro|KB-0184]] (o `BuyEvent` decodificado) · [[EXP-M15-carteiras-vencedoras]] · [[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]] · [[KB-0134-websocket-do-rpc-lag-medido-ao-vivo]] ·
[[KB-0124-latencia-de-decisao-e-o-alvo-de-milissegundos|KB-0124]] · [[T4.8e-decoders]] · [[Exchange Adapters]] · [[carteiras-lucro-design]]

## Armazenamento depois da medição (acrescentado em 05/10/2026, database-architect)

O diálogo [[wallet-tape-storage]] (3 rodadas com a Astra, DECISÃO CONJUNTA) fechou como guardar esta fita. O desenho é a §9 de `docs/design/seguir-carteiras-lucrativas.md`. O que esta nota passa a saber:

- **A linha da onda 0 (529 B) era otimista.** A tabela real parecida, `meme_trades` com 2 índices, mede **599–616 B/linha** na VPS. A linha enxuta da fita (assinatura bytea 64, carteira/mint bytea 32, sem btree) tem **248 B** pela aritmética de tupla (`pg_column_size`), ou 7,1–7,7 GB/dia. Isso é cálculo, ainda não tabela medida.
- **Só a assinatura** (64 B incompressíveis, ~1 evento por tx) custa 1,92 GB/dia, ou 13,44 GB em 7 dias. Nenhuma opção completa apresentada demonstrou caber nos 10–20 GB aprovados.
- **Lotes abertos crescem sem teto num mercado de sacos mortos.** A fita parcial de 01/10 deu 0,216 posição aberta nova por trade, o que sugere 2–6,5 M posições/dia (cenário, não medida de lotes).
- **Decisão:** fita enxuta no Postgres com poda por dependência (pico normal ~7,17 d = 50,7–55,1 GB), contabilidade intacta numa campanha finita e faixa de planejamento de 80–175 GB. Pedido ao Everton: teto de 100 GiB e +100 GiB de disco. Ondas 1b definitiva e 2 seguradas até o piloto físico.
- **O motor puro não escala para a janela real** (~210 M fills, ~95 GB de RAM estimados). Nasce a onda 1c-bis, com prova de equivalência.
- **Seguidores** (pergunta secundária, [[2026-10-05-carteiras-seguidores-como-pergunta-secundaria]]) ganham uma tabela pequena de fotos de perfil com `known_at`, de ~0,5 MB/noite.
