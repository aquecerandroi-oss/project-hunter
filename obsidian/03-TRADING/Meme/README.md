---
tags: [meme, trading, catalogo, m4]
status: vivo
owner: sexta-feira
updated: 2026-09-12
---

# Meme — o que uma "estratégia" é aqui

Esta pasta é a irmã meme de [[03-TRADING/Estrategias/README|Estrategias]], não uma extensão dela.
`Estrategias/` é o catálogo gerado por script (T3.20) das versões de `strategy_versions` — um mundo
com orderbook, `MarketSpec`/`MarketLiquidity` reais (`docs/RISK_ENGINE.md`). pump.fun não tem
orderbook: o preço é uma função determinística de duas reservas virtuais numa curva de bonding
(`docs/plans/T4-MEME-RADAR.md` §0, §3). Por isso um conjunto de regras de meme não é uma linha de
`strategy_versions` — é uma linha de uma tabela irmã, planejada, ainda não escrita:
`meme_rule_sets` (`.claude/state/brief-T4.6-lab-meme-continuo.md`).

**Origem desta pasta:** decisão do Everton de 2026-09-12,
[[06-DECISIONS/2026-09-12-meta-7m-e-lab-meme|registrada aqui]] — diretriz (d): "o Lab vai ficar em
cima das meme coins simulando sem parar".

## O que é uma "estratégia" de meme aqui

Um **conjunto de regras pré-registrado sobre a curva de bonding**: uma porta de entrada (idade do
token, janela de progresso da curva, criador não vendedor líquido quando conhecido, participação
limitada ao volume do último minuto da curva) e uma saída (múltiplo-alvo `k×`, trailing a partir do
pico, time stop, saída forçada em migração/conclusão da curva ou sinal de rug) —
`hunter_indicators.meme.rules` (planejado, T4.5), funções puras sobre uma linha de
`meme_features_1m`.

**Pré-registrado** tem o mesmo significado de sempre no projeto: parâmetros congelados **antes** de
rodar, numa página `EXP-M<n>` no formato de `_TEMPLATE-EXP.md` — protocolo escrito uma vez e nunca
editado, avaliações acrescentadas abaixo, datadas, nunca reescritas (a mesma regra `exp_reescrita`
do linter vale aqui). Nenhuma estratégia de meme pula essa porta por causa da meta em dinheiro —
ver [[06-DECISIONS/2026-09-12-meta-7m-e-lab-meme]] §3.

## Três séries de nome que não se confundem

| Série | O que é | Onde vive |
|---|---|---|
| `M-A`, `M-B`, `M-E`, `M-G` | Rótulos informais de candidatos citados nas notas de conhecimento de meme de 2026-09-06 (KB-0057, KB-0058, KB-0059, KB-0064) — nunca viraram pré-registro formal; ficam como histórico de discussão, não como estratégia registrada | dentro do texto das próprias `KB-00xx` — não são páginas |
| `EXP-M<n>` | Pré-registro formal de um conjunto de regras sobre a curva (T4.5) — protocolo congelado, régua editorial idêntica à de `momentum`/`mean_reversion` (≥ 100 avaliáveis **e** ≥ 30 dias, IC 95 % por blocos de dia, 2 de 3 janelas) | `obsidian/05-EXPERIMENTS/EXP-M<n>-<slug>.md`, listada em [[Experiments Index]] |
| `M-P<n>` | Hipótese de pesquisa (ainda não é candidata de estratégia) especificamente sobre meme/pump.fun, na fila do plantão | `00-INBOX/Hipoteses-do-plantao.md`, a partir desta decisão — ver o cabeçalho daquele arquivo |
| `M-L<n>` | Lição **medida** pelo fechamento diário do Lab (T4.15): um contraste do dia que passou a régua (n ≥ 30 apostas fechadas, ≥ 3 blocos de hora, IC 95 % fora de zero) — hipótese com número, ainda não candidata; vira `EXP-M<n>` com previsão `descartar` | `00-INBOX/Hipoteses-do-plantao.md`, escrita por `infra/scripts/meme_close_day.py`; o diário completo do dia em [[09-OPERATIONS/Diario-Meme/README|Diário Meme]] |

**Estado nesta data (2026-09-12):** a primeira página `EXP-M*` existe desde a T4.5 desta mesma
sessão — [[EXP-M1-comprar-cedo-na-curva]], "comprar cedo na curva e vender em ROI alto", a hipótese
que o próprio Everton enunciou. Ela está **pré-registrada, não rodada**: o simulador puro existe
(`hunter_indicators.meme`), o coletor da T4.2 ainda não gravou uma linha de `meme_curve_snapshots`, e
por isso `result: nao-iniciado` com 0 avaliáveis e 0 dias.

## Conjuntos ativos

| Conjunto | Pré-registro | Status | Último veredito |
|---|---|---|---|
| `comprar_cedo_na_curva v1` + `alvo_2x_trailing_30_tempo_15m v1` — perfil `meme_paper_v0` (idade 30–600 s, progresso 2–50 %, participação ≤ 1 %; 2× / trailing 30 % / time stop 15 min / piso 50 % / dump do criador) | [[EXP-M1-comprar-cedo-na-curva]] | **descartada em 2026-09-12** (T4.16: 9/9 negativas, 5 delas artefato `rug_no_snapshot` → `indeterminate`; aposentado por `meme_rule_set.py --deprecate`) | `descartar` — sucessora [[EXP-M5-fluxo-e-holders]] |
| `a_linha_manda v1` + `alvo_2x_trailing_30_tempo_15m_linha v1` — conjunto `trendline_v0/1` (T4.10, `0026`: EXP-M1 com idade ≥ 5 min **e** fundos ascendentes **e** rompimento da janela anterior **e** banda 0–25 % sobre o suporte; saída com **linha rompida**) | [[EXP-M2-a-linha-manda]] | **pré-registrado** — paper, sem chave, sem ordem real | — (nenhuma corrida; portão = `REVISE`, veredito **previsto** `descartar`) |
| `sonda_de_hype v1` + `alvo_3x_trailing_40_tempo_10m v1` + escala pela porta de `trendline_v0/1` — conjunto `hype_probe_v0/1` (T4.10, `0026`: 30 s–5 min, `hype_score ≥ 0,6`, sonda 0,01 SOL → perna 2 de 0,04 SOL com `parent_bet_id`) | [[EXP-M3-sonda-de-hype]] | **descartada em 2026-09-12** (T4.16: 8/8 sondas em giro de robô, vendas ≈ compras; aposentado por `meme_rule_set.py --deprecate`) | `descartar` — sucessora `hype_probe_v0/2` ([[EXP-M5-fluxo-e-holders]], braço 2) |
| `sonda_de_hype v1` + `alvo_10x_trailing_50_apos_3x_tempo_2h v1` / `alvo_25x_trailing_50_apos_3x_tempo_2h v1` — conjuntos `moonshot_v0/1` e `moonshot_v0/2` (T4.11, `0029`: a porta da EXP-M3, 0,02 SOL, trailing 50 % só depois de 3×, 7 200 s, **segura através da migração** e é marcada pela fita da pool PumpSwap; saída `dead`) | [[EXP-M4-moonshot]] | **pré-registrado** — paper, sem chave, sem ordem real | — (nenhuma corrida; portão = `REVISE`, veredito **previsto** `descartar`) |
| `fluxo_e_holders v1` + `alvo_3x_trailing_35_apos_1_5x_tempo_30m v1` — conjunto `flow_v2/1` (T4.16, `0030`: idade 30–300 s, fluxo líquido > 0, ≥ 10 compradores, `sells/buys ≤ 0,6`, holders e progresso subindo, snipers ≤ 2, dev ≤ 10 %; **decidido por fotografia de 15 s** e preenchido na seguinte; 3× / 35 % após 1,5× / 30 min / dump / linha / piso 50 %) | [[EXP-M5-fluxo-e-holders]] | **pré-registrado** — paper, sem chave, sem ordem real | — (nenhuma corrida; portão = `REVISE`, veredito **previsto** `descartar`) |
| `sonda_de_hype v2` + `alvo_3x_trailing_40_tempo_10m v1` + escala por `trendline_v0/1` — conjunto `hype_probe_v0/2` (T4.16: a sonda + fluxo > 0, ≥ 10 compradores, `sells/buys ≤ 0,6`; relógio de 1 min) | [[EXP-M5-fluxo-e-holders]] (braço 2) | **pré-registrado** — paper | — (nenhuma corrida; veredito **previsto** `descartar`) |
| `exclusoes_de_pedigree v1` — filtro transversal de **toda** porta (T4.16: `creator_prior_mints_1h ≥ 2` → `creator_serial`, `symbol_dup_24h ≥ 3` → `symbol_clone`, desconhecido recusa) | [[EXP-M6-exclusoes-de-pedigree]] | **pré-registrado** — em vigor por padrão em todo conjunto | — (nenhuma corrida; portão = `PASS`, veredito **previsto** `descartar` como filtro autônomo) |
| `organica_lenta v1` + `alvo_5x_trailing_40_apos_2x_tempo_60m_segura_migracao v1` — `organic_v0/1` (T4.22: entrar 3–30 min depois, curva 10–30 % subindo, holders ≥ 20 subindo, top-10 ≤ 30 %, snipers ≤ 2, segurar pela migração) | [[EXP-M7-organica-lenta]] | **pré-registrado** — semeado pela `0035` em 13/09 | — (nenhuma corrida; portão = `REVISE`, veredito **previsto** `descartar`) |

Uma linha por `EXP-M<n>`, no mesmo espírito da página de família de `03-TRADING/Estrategias/**`
(`docs/OBSIDIAN.md` §1). Status e veredito são copiados da página do experimento, nunca decididos
aqui.

## O que ainda é planejado, não implementado

| Peça | Tarefa | Status nesta data |
|---|---|---|
| Coleta on-chain + WS (curva, criação, migração) | T4.1 | Planejado — sem código no repo nesta data |
| `meme_tokens`, `meme_curve_snapshots`, `meme_features_1m` (Postgres) | T4.2 | Planejado — nenhuma migração no repo nesta data |
| Simulador puro da curva + `PaperCurveWallet` + regras + `EXP-M1` | T4.5 | Planejado — em execução nesta sessão |
| `docs/RISK_ENGINE_MEME.md` (doutrina de risco, tetos em SOL, kill switch) | T4.4 | Planejado — em execução nesta sessão, arquivo ainda não existe |
| Laço contínuo do Lab (`meme_rule_sets`, apostas paper por minuto, diário automático) | T4.6 | Planejado — depende de T4.2/T4.4/T4.5 |
| Tela `/meme` e painel Meta | T4.3, T4.3b | Especificação em `docs/plans/T4-MEME-RADAR-UI.md`; painel Meta em [[06-DECISIONS/2026-09-12-meta-7m-e-lab-meme]] §4 |

**Nenhuma execução real em nenhum ponto desta cadeia.** T4.1–T4.3 são só leitura por desenho
(`docs/plans/T4-MEME-RADAR.md` §0); T4.5/T4.6 são paper sobre dado real da curva; dinheiro real
depende de switch explícito do Everton (`ENABLE_MEME_LIVE_TRADING`) depois do fluxo verificado — ver
[[06-DECISIONS/2026-09-12-meta-7m-e-lab-meme]] §3.

## Relacionadas

[[03-TRADING/Estrategias/README|Estrategias (catálogo geral)]] · [[Experiments Index]] · [[03-TRADING/Meme/Estudo-2026-09-12-21-apostas|Estudo das 21 apostas de 12/09]] ·
[[Strategy Backlog]] · [[06-DECISIONS/2026-09-12-meta-7m-e-lab-meme]] ·
[[02-MARKET/Meme/README|Meme (Mercado)]] · [[09-OPERATIONS/Diario-Meme/README|Diário Meme]] ·
[[11-KNOWLEDGE/README-meme|Meme (Conhecimento)]] · [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] · [[03-TRADING/Meme/Terminal-do-pumpfun|Terminal do pump.fun]] ·
`docs/plans/T4-MEME-RADAR.md` · `docs/plans/T4-MEME-RADAR-UI.md`

## Pista de cópia no papel (H-037, 09/10/2026)

Como ligar: **primeiro** a semente auditada dos conjuntos `copy_v0/1` (e `copy_everton_v0/1`) pela tarefa E do desenho (`docs/design/copiar-carteiras-papel.md` §9), **depois** `MEME_COPY_LANE=paper` no ambiente do `meme-worker` (valores `off`, o padrão, e `paper`; qualquer outro vira `off` com aviso; não existe `on` nem `live`). Com `off` nada é construído nem aberto; com `paper` sem semente a pista fica inerte (`copy_state=inert`) e não abre NATS nem WS. Rode `paper` com `SOLANA_RPC_URL` pago: o cliente RPC da pista tem baldes próprios e não divide a cota do endpoint com o radar nem com `MEME_WATCH_WALLETS`. Ver [[EXP-M28-copiar-carteiras-no-papel]] e [[Revisoes-Astra/copy-wiring-main|copy-wiring-main]].

## Operações traçadas

Um gráfico por aposta fechada, uma página por conjunto: [[03-TRADING/Meme/Apostas-tracadas/README|Operações traçadas (meme)]] — desenhadas por `meme_render_bets.py` (`docs/PIPELINE.md` §9c).

## Candidatas do radar (rodadas de pesquisa)

Uma página por rodada: o que estava dentro da janela do executor naquele instante, o que a porta de
encanamento produziria e o pedigree dos criadores. Não é pré-registro nem recomendação — é leitura do
banco com hora e SQL anexados.

- [[03-TRADING/Meme/Candidatas/2026-09-16-16h|2026-09-16 — R1 (14:47–15:47 BRT)]]
- [[03-TRADING/Meme/Candidatas/2026-09-16-17h|2026-09-16 — R14 (15:18–16:18 BRT)]] — porta calibrada = porta em vigor (5 propostas/h vs 3 da anterior), termos `PAID`/`ARGUS`/`ZEC` sem candidata comprável, conclusão: nenhuma
- [[03-TRADING/Meme/Candidatas/2026-09-16-17h02-brt|2026-09-16 — R23 (16:17–17:02 BRT)]] — mesa: 7 ordens reais, todas recusadas na admissão (2 recusas boas, 1 ruim: BRINAA +31,5 %); porta em vigor entrega 9 moedas/h (0,15/min) e o executor admitiria **0** (7 sem retrato de risco, 2 com top-10 em 27 %); Kintsugi passou a porta às 16:20, foi a 66 % com 408 holders e **não virou proposta**; `X*`/`casinu`/`ZEC` sem candidata comprável; conclusão: nenhuma
- [[03-TRADING/Meme/Candidatas/2026-09-16-17h30-brt|2026-09-16 — R30 (17:00–17:27 BRT · última hora 16:25–17:25)]] — mesa: 2 ordens reais, ambas recusadas por dado ausente (`creator_flow_unknown` + `bundled_share_unmeasurable`), recusa boa (SOLAMI −41 %); porta em vigor 10 moedas/h → admissão **0** (só 2 têm retrato e as 2 com bundle > 20 %); a "janela de encanamento" (prog ≤ 85 %, bundle ≤ 35 %, top-10 ≤ 30 %) dá 30 moedas/h e **2 admitidas/h** — GRANDMAJIL e NIKKI, **as duas perderam** (NIKKI −78,8 % em 2 min); esperar 120 s pelo retrato levaria de 2 para ~10/h; 49,8 % das moedas da hora terminam no piso de curva vazia (~28 SOL); conclusão: nenhuma
- [[03-TRADING/Meme/Candidatas/2026-09-16-21h40-brt|2026-09-16 — R41 (19:28–21:40 BRT · última hora 20:30–21:30)]] — **a mesa real comprou pela primeira vez**: TAXCOIN `7s4dKm…`, 0,05 SOL às 21:31:28 BRT, saída por `creator_dump` 48 s depois, **−0,009764 SOL (−18,5 %)**, as 25 checagens passaram porque havia **um** retrato de risco (bundle 14,99 %) 67 s antes — e a compra caiu **71 s depois de a curva perder 24 de 29,6 SOL reais**; 19 ordens em 7 moedas na janela, **3 recusas ruins seguidas** (CELINE, funemployed, PPC — todas `creator_flow_unknown`, todas dobraram o SOL real); dia atualizado: **76 ordens, 35 moedas, 74 recusadas, 2 confirmadas**, placar **17 boas / 9 ruins / 7 neutras / 1 graduada / 1 comprada**; última hora: **10 de 10 de maior demanda perderam SOL real** (−34,8 a −100 %), retrato em **0 de 10** e fita em 1 de 10; **o deploy pendente admitiria ZERO** (retrato chega em ≤ 60 s para 4 das 16 da porta, e as 4 reprovam no bundle de 20 % — a TAG `3U3Y79…`, **78,3 SOL reais e −1,5 %**, é perdida por 2,3 pp); perfil da noite: **o pico do KB-0098 não apareceu** (criação 24,1/min às 21 h contra 32,6/min às 19 h, janela caindo de 4,10 para 1,99/min), mas **graduações lideram** (57,5/h); cadência estimada **~0,5 compra/hora** (n = 1)
- [[03-TRADING/Meme/Candidatas/2026-09-16-17h56-brt|2026-09-16 — R35 (17:25–17:55 BRT · última hora 16:50–17:50)]] — **desfecho passa a ser lido na cadeia** (`real_sol_reserves`, [[11-KNOWLEDGE/KB-0115-volta-ao-piso-e-real-ou-artefato|KB-0115]]); mesa: 7 ordens reais recusadas em 4 moedas, **3 recusas comprovadamente boas** (ZIPPY −98,2 %, KITTYGBIKE −99,9 %, YOLO −96,5 % de SOL real) e as **duas primeiras recusas do dia por valor acima do teto** (YOLO bundle 40,83 %; TOKTIP progresso 53,53 %); porta em vigor **9 moedas/h → admissão 0**, janela de encanamento **30/h → 1 admitida** (NIKKI, **−39,1 SOL reais em 4 min**); 9 das 10 de maior demanda esvaziaram a curva (−59,5 a −100 %); termos de vigilância (GROK/HYPED/DONO/ILY/LUV) = **310 moedas no dia** e **0 de 6 com desfecho positivo**; achado: `curve_progress_pct` de 15 s dizia 37,7 % numa curva com **0,014 SOL reais**; conclusão: nenhuma (TOKTIP era a melhor do dia e descarregou 10 SOL em 15 s no instante da decisão)

## Estudos de 16/09

- [[03-TRADING/Meme/Estudo-2026-09-16-o-que-a-mesa-propos-hoje-rendeu|R10 — o que a mesa propôs hoje rendeu]] — 35 propostas de `operator/5`, zero posições abertas (19 expiraram em paper, 16 recusadas na admissão); R simulado (teto, não medido) +17,49 R em 35 propostas; o teto de progresso 50 % custou +9,07 R mas mantém a razão certa (acerta mais na faixa que protege); prioridade real é o progresso negativo por bug de denominador, não o teto.
- [[03-TRADING/Meme/Estudo-2026-09-16-o-que-a-admissao-nova-admitiria-hoje|R26 — o que a admissão nova admitiria hoje]] — reavalia as 26 ordens do dia contra T4.28g (espera pelo retrato), T4.28h (`creator_flow_unknown` com `dev_share` medido) e o teto de `top10_share` a 30 % do KB-0109.
- [[03-TRADING/Meme/Balanco-2026-09-16-mesa-real|R39 — balanço do dia da mesa real (11:46–19:28 BRT)]] — **58 ordens, 29 moedas, 100 % recusadas, zero assinatura**; cada recusa julgada pela cadeia (`real_sol_reserves`, KB-0115): **16 boas, 6 ruins, 6 neutras, 1 graduou** (GREMLIN encheu a curva 8 s depois da 4.ª recusa por `progress_above_window`); comprar todas daria **−7,51 R por moeda / −23,54 R pelas 58 ordens** (regra da mesa: 3×, trailing 35 % após 1,5×, 30 min, piso −50 %, 1,75 %/perna); **28 das 58 recusas são por dado ausente** (27 `creator_flow_unknown`) e **8 recusas por "progresso abaixo de 2 %" caíram em curvas com 11,6–23,2 SOL reais** (INCEPT lida como −5×10⁵ %); a janela de encanamento compraria **1 moeda no dia** (RIZZLERS, −1,64 R) e, na versão frouxa, 17 moedas por −5,75 R — recusando a GREMLIN assim que o retrato chegasse (bundle 39,8 %); gargalo = **bundle ausente em 36 das 39 ordens com progresso na janela**.
- [[03-TRADING/Meme/Estudo-2026-09-16-a-porta-real-versus-a-replica|R27 — a porta real versus a réplica]] — Kintsugi não virou proposta porque a porta mudou de teto para piso de snipers entre 16:20 e 16:25 BRT; não foi corrida nem bug de gravação, foi a réplica comparando contra uma porta que já não estava mais em vigor.

## Balanços do dinheiro real — estágios 1 e 1b (17–18/09)

**Nota sobre a lacuna:** entre R44 e R60 (16–18/09) a pesquisa quant continuou em ritmo diário, mas
foi registrada em `.claude/state/notes-R44.md`…`notes-R60.md` e `.claude/state/notes-T4.*.md` — não em
páginas `Candidatas/` como as rodadas de 16/09 acima. Os achados dessas ~15 notas foram compilados nas
[[11-KNOWLEDGE/KB-0119-entrada-depois-da-queda-em-producao|KB-0119]] a
[[11-KNOWLEDGE/KB-0134-websocket-do-rpc-lag-medido-ao-vivo|KB-0134]] em 18/09, para não ficarem só no
estado de trabalho. As duas páginas de balanço abaixo continuam sendo a referência número a número.

**A faixa nota a nota:** [[11-KNOWLEDGE/KB-0119-entrada-depois-da-queda-em-producao|KB-0119]] ·
[[11-KNOWLEDGE/KB-0120-piso-de-snipers-e-as-vencedoras-do-papel|KB-0120]] ·
[[11-KNOWLEDGE/KB-0121-teto-de-vendas-compras-06-descarta-25-por-cento|KB-0121]] ·
[[11-KNOWLEDGE/KB-0122-clones-de-simbolo-filtram-lixo-e-barram-boas|KB-0122]] ·
[[11-KNOWLEDGE/KB-0123-quase-metade-das-graduacoes-nasce-cheia|KB-0123]] ·
[[11-KNOWLEDGE/KB-0124-latencia-de-decisao-e-o-alvo-de-milissegundos|KB-0124]] ·
[[11-KNOWLEDGE/KB-0125-relogio-de-atividade-pico-14-20-brt|KB-0125]] ·
[[11-KNOWLEDGE/KB-0126-slippage-de-compra-1-por-cento-mata-acima-de-50|KB-0126]] ·
[[11-KNOWLEDGE/KB-0127-blockhash-expirado-e-prioridade-fixa-sem-reenvio|KB-0127]] ·
[[11-KNOWLEDGE/KB-0128-cadeia-vence-fita-no-fluxo-do-criador|KB-0128]] ·
[[11-KNOWLEDGE/KB-0129-cap-diario-cego-a-entrada-da-tesouraria|KB-0129]] ·
[[11-KNOWLEDGE/KB-0130-tesouraria-usdc-sol-block-ate-prova-ao-vivo|KB-0130]] ·
[[11-KNOWLEDGE/KB-0131-dado-mal-formado-derruba-o-processo-duas-vezes|KB-0131]] ·
[[11-KNOWLEDGE/KB-0132-t445-teria-recusado-a-taxcoin|KB-0132]] ·
[[11-KNOWLEDGE/KB-0133-papel-vs-real-custo-fixo-e-atraso-de-30s|KB-0133]] ·
[[11-KNOWLEDGE/KB-0134-websocket-do-rpc-lag-medido-ao-vivo|KB-0134]]

- [[03-TRADING/Meme/Balanco-2026-09-16-mesa-real|Balanço 16/09 — mesa real (R39)]] — primeiro dia
  completo da mesa real, 58 ordens, zero fills.
- [[03-TRADING/Meme/Balanco-2026-09-17-estagio-1|Balanço 17/09 — estágio 1 (R54)]] — as primeiras 5
  compras reais fecham: 0 vitórias, **−0,0449 SOL (−0,87 R)**; o erro está na entrada (compra logo
  depois de uma queda), não na saída.
- [[03-TRADING/Meme/Balanco-2026-09-18-estagio-1b|Balanço 18/09 — estágio 1b (R56)]] — 7 compras, 6
  fills, **1 vitória (PS, +0,66 R)**, **+0,0078 SOL líquido**; a vitória veio de duas falhas de envio
  com sorte, não de acerto de porta; diagnostica `blockhash_expired` e o buraco cadeia×fita da COVER.

## Tempo de ciclo do `meme-worker` — a série da trava §6.8 (07/10/2026)

Antes de 07/10 nenhum log nem heartbeat guardava quanto tempo a cadeia e o Lab levam por ciclo (o
`chain_cycle_s` do radar é só o lote de RPC, não o passo inteiro; `meme_lab_ticks` não tem duração). A trava de
ciclo do §6.8 do [[EXP-M26-grafico-em-moedas-maduras|EXP-M26]] ("+ 20 % no p95") ficava **não mensurável** — e
"não mensurável" nunca conta como "passou". O Everton decidiu em 07/10 **instrumentar antes do seed**
(item 3 de "Decisões do Everton (07/10/2026)"). Código: `hunter_meme_worker/cycle_metrics.py`, ligado em
`main.py` em volta de `chain_once` e `lab_once`. Revisão: [[06-DECISIONS/Revisoes-Astra/meme-cycle-metrics|meme-cycle-metrics]].

**O que é um ciclo.** A duração de parede de **uma chamada do passo** de `collect.forever`, em milissegundos
inteiros (aritmética inteira sobre `monotonic_ns`), **sem** o `sleep` que o `forever` dorme depois e sem a
publicação do próprio número (o tempo de publicar fica **fora** do número medido, mas **dentro** da cadência: a
cadência real é `passo + publicação (≤ 1 s) + período`). No Lab o passo é o `lab_tick` inteiro (inclui `record_tick` e o
`write_lab_heartbeat`). **Overrun** = ciclo mais longo que o período nominal (`chain_cycle_s` = 60 s;
`lab_cycle_s` = 15 s). É um **limiar de trabalho, não um prazo perdido**: a cadência real é sempre
`duração + período`, então um Lab que passa de 10 s para 13 s ficou 30 % mais lento **sem nenhum overrun**. A
guarda compara o **p95** por conta própria; o contador é só alarme.

**Campos novos em `hb:meme:radar`** (strings; vazio = ainda não medido, nunca `0`; escritos logo após cada
ciclo, um `HSET` com orçamento próprio de 1 s; prefixo `chain_` para a cadeia e `lab_` para o Lab). O leitor
**tem de ancorar em `run_id`**: o `ts` geral do heartbeat não diz se esses números são do processo que roda
(**em todo boot** o processo publica uma geração vazia para **os dois** laços, **inclusive** com o laço desligado
por configuração ou com o radar inteiro desligado (`MEME_ENABLED=false`), com `<loop>_cycle_enabled=false`: assim os
campos do processo anterior são sobrescritos e um laço desligado nunca parece ter números atuais. O hash
compartilhado **não** é apagado — há outros escritores. Pressuposto: **uma instância** do `meme-worker` por chave
(`hb:meme:radar`); o compose declara um serviço, mas nada impõe exclusão mútua, e dois processos alternariam gerações
na mesma chave).

| campo | significado |
|---|---|
| `<loop>_cycle_run_id` · `<loop>_cycle_since` | a geração da série (uuid do processo) e o início dela (UTC) |
| `<loop>_cycles_total` | ciclos registrados nesta geração |
| `<loop>_overruns_total` | ciclos acima do período nominal |
| `<loop>_last_cycle_ms` · `<loop>_last_cycle_at` | o último ciclo e quando terminou (UTC, ISO-8601) |
| `<loop>_cycle_ms_p50` · `_p95` · `_p99` · `_max` | posto mais próximo sobre o anel |
| `<loop>_cycle_window_n` | amostras no anel agora (anel fixo: 120 ciclos concluídos na cadeia, 480 no Lab; só dá ~2 h se o trabalho for desprezível) |
| `<loop>_cycle_nominal_ms` · `<loop>_cycle_enabled` | o período nominal usado para contar overrun; se o laço está ligado neste processo (`false` = geração vazia anunciada só para limpar o anterior) |
| `<loop>_cycle_publish_failed_total` | publicações que falharam ou estouraram o orçamento de 1 s |

Log: `meme_cycle_overrun` (warning; `loop`, `duration_ms`, `nominal_ms`, `overruns_total`, `suppressed`) só em
overrun e no máximo uma vez a cada 300 s por laço; `suppressed` diz quantos foram engolidos. Falha do `HSET` é
`meme_cycle_metrics_publish_failed`, nunca para o laço. Um passo que levanta exceção não é registrado (o
`forever` relança e o processo cai, como antes) — para a guarda, uma interrupção é **ausência de evidência**,
nunca melhora.

**A série durável (histórico por ciclo, 07/10/2026).** Cada ciclo concluído vira **ao menos uma linha em
`system_events`** (`component = 'meme-worker'`, `level = info`), **sem migração** (a tabela já existe, é
append-only — `UPDATE`/`DELETE` negados aos dois papéis, provado em Postgres real —, `hunter_worker` tem `INSERT`, não é
tabela de tenant). Três eventos (`hunter_meme_worker/cycle_history.py`):

| `event` | `data` | quando |
|---|---|---|
| `cycle` | `{loop, run_id, seq, ended_at, duration_ms}` | um por ciclo concluído; `seq` = `cycles_total` do laço dentro do `run_id` |
| `generation_start` | `{loop, run_id, started_at, enabled, nominal_ms, window}` | em todo boot, para **os dois** laços, ligados ou não (laço desligado deixa esta linha e nenhum ciclo: é assim que a ausência se explica) |
| `generation_end` | `{loop, run_id, ended_at, cycles_total, overruns_total, clean}` | no desligamento, se a fila ainda alcança o banco: `clean = true` para SIGTERM, `false` quando um laço caiu e derrubou o processo. **Geração sem ele = término não comprovado** (não necessariamente queda: `kill -9`, queda antes do fechamento ou desligamento com o banco fora, em que a fila morre com o processo): a cauda é desconhecida e a cobertura só se prova até o último `seq` contíguo |

**Contrato do leitor** (a tabela **não** promete unicidade): um COMMIT aplicado com a confirmação perdida faz o
escritor repetir o lote, então um ciclo pode existir duas vezes. A identidade é **`(loop, run_id, seq)`**,
deduplicada **antes** de qualquer percentil (para as linhas `generation_*` a identidade é **`(event, loop, run_id)`**); as janelas se cortam por **`data->>'ended_at'`**, nunca por `created_at`
(que é o instante da persistência e se move com o banco fora); a ordem é por `(loop, run_id, seq)`, nunca por
`created_at` (um lote é uma transação: todas as linhas dele têm o mesmo). A consulta pronta é a constante
`CYCLES_SINCE_SQL` do módulo (`DISTINCT ON`, parâmetros `:since`/`:until` em UTC; provada contra Postgres real,
inclusive com um ciclo duplicado, um fora da janela e um persistido mais de um dia depois dela). `created_at` só poda partições, **nos dois lados** (`[since − 1 dia, until + 1 dia)`): uma linha persistida mais de um dia depois do fim da janela, ou de um worker com o relógio mais de um dia adiantado, fica fora do que a consulta lê. Um salto de `seq` **dentro** de um `run_id` é **buraco
declarado**, nunca preenchido.

**Escrita.** O worker enfileira (fila limitada de 4 096 linhas ≈ 13 h; **nunca bloqueia um laço**; cheia, descarta a
mais antiga e conta — `dropped_total` é um **limite superior** do que se perdeu) e uma tarefa própria (`flush`, depois
dorme 5 s: não é período fixo; roda também com `MEME_ENABLED=false`) grava em lote de até 500 como `hunter_worker`, sob
**um** orçamento de 10 s para o banco e os contadores juntos — **teto rígido**: a escrita roda numa tarefa que o flush
**abandona** ao fim do orçamento (`asyncio.timeout` esperaria o cancelamento terminar, e contra um par travado o cancelamento
do asyncpg não tem prazo), contada em `_abandoned_total`, com **uma escrita em voo por vez** (uma escrita abandonada que ainda
confirma depois duplica linhas: o contrato do leitor as colapsa); falha guarda as linhas para a próxima tentativa; no
desligamento, `generation_end` dos dois laços (`clean` conforme a causa) e depois o esvaziamento da fila em até 3 s (também
teto rígido; para na primeira falha). Contadores no hash:
`cycle_history_written_total`, `_failed_total`, `_dropped_total`, `_abandoned_total`, `_queued` (publicados só quando mudam;
zerados no boot). Volume ~7 200 ciclos/dia (estimativa nominal, não medida em produção). **Retenção de 30 dias, por partição
mensal inteira**: a base "antes" e a janela do experimento têm de ser **exportadas e congeladas** antes de
expirarem. Sem a partição do mês da escrita, o lote falha e espera (`failed_total`). A base do "antes" é
**prospectiva, a partir do deploy** deste código — o desenho do EXP-M26 ainda cita "72 h antes de I1" e **essa série
não existe** (o instrumento não recupera o passado). **Ainda faltam, antes de a guarda valer:** congelar a janela por
`ended_at`, a cobertura mínima e o tratamento de reinícios e de caudas desconhecidas (decisão do orquestrador/Everton);
sem prova de cobertura a guarda é **não mensurável**.

**O que isto não é.** O hash do Redis guarda só o anel de agora; um reinício zera o anel e um seed com o processo
vivo mistura nele os ciclos de antes com os de depois — por isso a comparação "antes × depois" se faz **pelas linhas
individuais de `system_events` por `run_id`/janela**, nunca pelo p95 do anel (p95 de p95 não é p95 dos ciclos).
Interrupção do worker é **ausência de evidência**, nunca melhora. Revisão e aceite:
[[06-DECISIONS/Revisoes-Astra/meme-cycle-metrics|meme-cycle-metrics]] (o `database-architect` aprovou o lado do banco em
09/10: Rodada 3 abaixo; contrato em `docs/DATABASE.md` §73).

**Rodada 3 (`database-architect`, 09/10/2026) — APROVADO no lado do banco; 2 pendências de ciclo de vida corrigidas.**
Bruto: `.claude/state/astra-review-db-meme-cycle-history.md`. Síntese e decisões:
[[06-DECISIONS/Revisoes-Astra/meme-cycle-metrics|meme-cycle-metrics]] ("Rodada 3").

| # | severidade | achado | situação |
|---|---|---|---|
| 1 | HIGH | uma queda de laço recebia `generation_end` "limpo" (o `finally` fechava igual) | **corrigido:** `generation_end` leva `clean`; `false` quando a saída não foi cancelamento — e a causa é lembrada **antes** da limpeza (uma queda seguida de SIGTERM durante o fechamento dos clientes continua queda; conferência da Astra). Texto corrigido: **ausência de `generation_end` = término não comprovado**, não "queda" |
| 2 | MEDIUM | com `MEME_ENABLED=false` os `generation_start` ficavam na fila e nunca eram gravados | **corrigido:** o gravador e o fechamento rodam em volta de todo o `run_meme` (`CycleInstruments.supervised`), ligado ou não; o gravador não morre com uma exceção inesperada (loga e tenta de novo) |
| 3 | LOW | os 10 s do flush e os 3 s do close não eram teto rígido contra um par travado | **corrigido no histórico:** escrita abandonada no orçamento (`_abandoned_total`, uma em voo por vez). O defeito de fundo (docstring D3 de `hunter_core/db/session.py`) está em [[Open Bugs]] |
| 4 | LOW | UUID v4 gerado no banco contra a regra de v7 | **desvio declarado** em `docs/DATABASE.md` §73 (v7 não elimina duplicatas: a PK é `(created_at, id)`) |
| 5 | LOW | o docstring dizia que atraso de persistência > 1 dia não exclui a linha (só havia limite inferior) | **corrigido:** a consulta ganhou `created_at < :until + 1 dia`; o texto agora diz o que exclui. A exclusão aparece como **buraco de `seq`** (cobertura não provada, guarda não mensurável); a Astra a vê como exclusão sem sinal — decisão do orquestrador em [[06-DECISIONS/Revisoes-Astra/meme-cycle-metrics|meme-cycle-metrics]] |
| 6 | nit | leitores de `generation_*` deduplicam por `(event, loop, run_id)` | **escrito** (módulo, README, `docs/DATABASE.md` §73) |

Sem índice novo antes de um `EXPLAIN (ANALYZE, BUFFERS)` com volume representativo (não medido). Retenção mensal pode manter
mais de 30 dias de linhas, nunca menos.
