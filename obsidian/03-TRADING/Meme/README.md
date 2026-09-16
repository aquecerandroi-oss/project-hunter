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
- [[03-TRADING/Meme/Candidatas/2026-09-16-17h56-brt|2026-09-16 — R35 (17:25–17:55 BRT · última hora 16:50–17:50)]] — **desfecho passa a ser lido na cadeia** (`real_sol_reserves`, [[11-KNOWLEDGE/KB-0115-volta-ao-piso-e-real-ou-artefato|KB-0115]]); mesa: 7 ordens reais recusadas em 4 moedas, **3 recusas comprovadamente boas** (ZIPPY −98,2 %, KITTYGBIKE −99,9 %, YOLO −96,5 % de SOL real) e as **duas primeiras recusas do dia por valor acima do teto** (YOLO bundle 40,83 %; TOKTIP progresso 53,53 %); porta em vigor **9 moedas/h → admissão 0**, janela de encanamento **30/h → 1 admitida** (NIKKI, **−39,1 SOL reais em 4 min**); 9 das 10 de maior demanda esvaziaram a curva (−59,5 a −100 %); termos de vigilância (GROK/HYPED/DONO/ILY/LUV) = **310 moedas no dia** e **0 de 6 com desfecho positivo**; achado: `curve_progress_pct` de 15 s dizia 37,7 % numa curva com **0,014 SOL reais**; conclusão: nenhuma (TOKTIP era a melhor do dia e descarregou 10 SOL em 15 s no instante da decisão)

## Estudos de 16/09

- [[03-TRADING/Meme/Estudo-2026-09-16-o-que-a-mesa-propos-hoje-rendeu|R10 — o que a mesa propôs hoje rendeu]] — 35 propostas de `operator/5`, zero posições abertas (19 expiraram em paper, 16 recusadas na admissão); R simulado (teto, não medido) +17,49 R em 35 propostas; o teto de progresso 50 % custou +9,07 R mas mantém a razão certa (acerta mais na faixa que protege); prioridade real é o progresso negativo por bug de denominador, não o teto.
- [[03-TRADING/Meme/Estudo-2026-09-16-o-que-a-admissao-nova-admitiria-hoje|R26 — o que a admissão nova admitiria hoje]] — reavalia as 26 ordens do dia contra T4.28g (espera pelo retrato), T4.28h (`creator_flow_unknown` com `dev_share` medido) e o teto de `top10_share` a 30 % do KB-0109.
- [[03-TRADING/Meme/Balanco-2026-09-16-mesa-real|R39 — balanço do dia da mesa real (11:46–19:28 BRT)]] — **58 ordens, 29 moedas, 100 % recusadas, zero assinatura**; cada recusa julgada pela cadeia (`real_sol_reserves`, KB-0115): **16 boas, 6 ruins, 6 neutras, 1 graduou** (GREMLIN encheu a curva 8 s depois da 4.ª recusa por `progress_above_window`); comprar todas daria **−7,51 R por moeda / −23,54 R pelas 58 ordens** (regra da mesa: 3×, trailing 35 % após 1,5×, 30 min, piso −50 %, 1,75 %/perna); **28 das 58 recusas são por dado ausente** (27 `creator_flow_unknown`) e **8 recusas por "progresso abaixo de 2 %" caíram em curvas com 11,6–23,2 SOL reais** (INCEPT lida como −5×10⁵ %); a janela de encanamento compraria **1 moeda no dia** (RIZZLERS, −1,64 R) e, na versão frouxa, 17 moedas por −5,75 R — recusando a GREMLIN assim que o retrato chegasse (bundle 39,8 %); gargalo = **bundle ausente em 36 das 39 ordens com progresso na janela**.
- [[03-TRADING/Meme/Estudo-2026-09-16-a-porta-real-versus-a-replica|R27 — a porta real versus a réplica]] — Kintsugi não virou proposta porque a porta mudou de teto para piso de snipers entre 16:20 e 16:25 BRT; não foi corrida nem bug de gravação, foi a réplica comparando contra uma porta que já não estava mais em vigor.
