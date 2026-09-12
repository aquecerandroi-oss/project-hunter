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

**Estado nesta data (2026-09-12):** a primeira página `EXP-M*` existe desde a T4.5 desta mesma
sessão — [[EXP-M1-comprar-cedo-na-curva]], "comprar cedo na curva e vender em ROI alto", a hipótese
que o próprio Everton enunciou. Ela está **pré-registrada, não rodada**: o simulador puro existe
(`hunter_indicators.meme`), o coletor da T4.2 ainda não gravou uma linha de `meme_curve_snapshots`, e
por isso `result: nao-iniciado` com 0 avaliáveis e 0 dias.

## Conjuntos ativos

| Conjunto | Pré-registro | Status | Último veredito |
|---|---|---|---|
| `comprar_cedo_na_curva v1` + `alvo_2x_trailing_30_tempo_15m v1` — perfil `meme_paper_v0` (idade 30–600 s, progresso 2–50 %, participação ≤ 1 %; 2× / trailing 30 % / time stop 15 min / piso 50 % / dump do criador) | [[EXP-M1-comprar-cedo-na-curva]] | **pré-registrado** — carteira paper, sem chave, sem ordem real | — (nenhuma corrida; portão de desenho C1–C8 = `REVISE`, veredito **previsto** `descartar`) |
| `a_linha_manda v1` + `alvo_2x_trailing_30_tempo_15m_linha v1` — conjunto `trendline_v0/1` (T4.10, `0026`: EXP-M1 com idade ≥ 5 min **e** fundos ascendentes **e** rompimento da janela anterior **e** banda 0–25 % sobre o suporte; saída com **linha rompida**) | [[EXP-M2-a-linha-manda]] | **pré-registrado** — paper, sem chave, sem ordem real | — (nenhuma corrida; portão = `REVISE`, veredito **previsto** `descartar`) |
| `sonda_de_hype v1` + `alvo_3x_trailing_40_tempo_10m v1` + escala pela porta de `trendline_v0/1` — conjunto `hype_probe_v0/1` (T4.10, `0026`: 30 s–5 min, `hype_score ≥ 0,6`, sonda 0,01 SOL → perna 2 de 0,04 SOL com `parent_bet_id`) | [[EXP-M3-sonda-de-hype]] | **pré-registrado** — paper, sem chave, sem ordem real | — (nenhuma corrida; portão = `REVISE`, veredito **previsto** `descartar`) |
| `sonda_de_hype v1` + `alvo_10x_trailing_50_apos_3x_tempo_2h v1` / `alvo_25x_trailing_50_apos_3x_tempo_2h v1` — conjuntos `moonshot_v0/1` e `moonshot_v0/2` (T4.11, `0029`: a porta da EXP-M3, 0,02 SOL, trailing 50 % só depois de 3×, 7 200 s, **segura através da migração** e é marcada pela fita da pool PumpSwap; saída `dead`) | [[EXP-M4-moonshot]] | **pré-registrado** — paper, sem chave, sem ordem real | — (nenhuma corrida; portão = `REVISE`, veredito **previsto** `descartar`) |

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
