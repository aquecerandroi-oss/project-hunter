---
tags: [knowledge, nota, plantao, custos, funding, point-in-time, btc, perpetuos, m3]
tema: em BTCUSDT perpétuo a 5 min, uma família inteira de fatores com IC positivo no holdout não paga o pedágio em nenhuma célula de custo (Zeng et al. 2026) — e a auditoria point-in-time dos arquivos públicos da Binance que veio antes
fonte: Zeng, Yang, Han & He (Tsinghua/BUPT/Nanjing), "Point-in-Time Audit Before Alpha: Public-Archive Availability and a Negative Matched-Budget Study on BTC Perpetual Futures", arXiv 2608.25348v1 — HTML completo lido no plantão T3.64, run 5 (faixa 1)
fonte_url: https://arxiv.org/html/2608.25348
lido_em: 2026-09-10
evidencia: estudo dos próprios autores (preprint, não revisado) com protocolo congelado e holdout retrospectivo — 2 anos, 5 min, uma exchange, um instrumento; 23 execuções × 20 células de custo dependentes; nenhuma medição própria
hipotese_testavel: sim — D-P14 (fronteira de custo por versão viva da `mean_reversion`, com funding só nos settlements cruzados) e a auditoria point-in-time dos nossos mark/index/funding antes de somar o replay
astra: concorda
status: arquivada
owner: sexta-feira
updated: 2026-09-10
confiança: "backtest do autor"
---

# IC positivo não paga o pedágio: BTC perp a 5 min, 460 células de custo negativas (Zeng et al., arXiv 2608.25348)

> Nota de referência do plantão (faixa 1, pesquisa e dados). Justifica **auditar dados e custos**, não
> condenar toda reversão intradiária (Astra). Rascunho com todas as URLs e horas:
> `.claude/state/plantao/2026-09-10-0730-lane1.md`.

## O que afirma

1. **Auditoria point-in-time dos arquivos públicos da Binance** (BTCUSDT USDⓈ-M, 01/08/2024 → 01/08/2026,
   barras de 5 min). Exigindo trade + mark + index + OI numa grade contínua exata, "the longest
   unrepaired intersection was 304.57… days"; relaxando para trade/mark/index faltam 288 barras em
   29/06/2026 no mark e no index; o arquivo de funding tem 2 190 linhas e **nenhum campo de hora de
   publicação**; OI foi desabilitado porque a hora de publicação não é verificável. Sobram 209 951 decisões
   elegíveis e 727 dias UTC completos. A disponibilidade do funding no backtest usa **hipótese de atraso**,
   não carimbo comprovado (Astra).
2. **Estudo negativo com orçamento pareado.** Três buscadores de fatores (agente auditado, busca aleatória,
   GP de árvore) numa DSL de expressões (profundidade ≤ 4, lookbacks 3…288 barras), mesmo orçamento:
   candidatos qualificados 39/39/29; IC médio de teste 0,235 [0,155; 0,355], 0,191 [0,116; 0,268], 0,155
   [0,126; 0,177]. "No evaluated run had positive net Sharpe at primary costs" (6 bp taxa + 2 bp slippage
   por lado): Sharpe líquido mediano −28,0 / −21,2 / −30,1. Grade taxa {4, 5, 6, 8, 10} bp × slippage
   {1, 2, 5, 10} bp por lado: "all 460 executed cost cells were negative"; funding realizado só quando a
   posição cruza um settlement. "Positive IC did not imply an economically usable strategy."
3. **Limites declarados.** Custo linear sem impacto; um instrumento; não é uma estratégia de reversão — é
   busca de fatores; as 460 células são 23 execuções × 20 células **dependentes**, não 460 replicações.

## Onde foi mostrado

Binance USDⓈ-M, BTCUSDT, 5 min, 2024-08 → 2026-08, holdout retrospectivo congelado; taxa 4–10 bp e
slippage 1–10 bp por lado; funding por settlement cruzado.

## Como mediríamos aqui

- **D-P14 — fronteira de custo por versão viva** da `mean_reversion` (por aposta única): expectancy
  líquida numa grade taxa {2 (maker), 4, 5, 6, 8, 10} bp × slippage {1, 2, 5, 10} bp por lado, spread
  fixado uma vez (não contado de novo no slippage), funding só nos settlements cruzados; reportar o
  **maior custo suportável** com IC e cobertura, e "nenhuma célula positiva" quando for o caso. A célula
  maker de 2 bp é sensibilidade económica, **não** viabilidade — viabilidade maker exige preenchimento,
  fila e seleção adversa; mudar o preço de entrada exige revalidar a geometria, não só descontar bps.
- **Auditoria point-in-time própria:** nos 90 dias do replay, barras de 15 m com mark/index/funding
  ausentes por mercado, antes de somar qualquer resultado — é a mesma pergunta do `funding_missing` e do
  backfill da T3.75 ([[KB-0084-tres-motores-abertos-funding-latencia-e-nulo]], D-P11).

## Hipótese testável no Lab

Não há hipótese de edge; há a régua. O replay de 90 dias diz "família negativa fora de consolidação"
numa régua só (20 bps, [[KB-0076-por-que-perdemos-2026-09-08]]); a fronteira diz **onde** a família
morre e se algum custo plausível a salva — o que decide se a T3 investe em execução maker ou em outra
família. Refutação do uso: se a fronteira ficar abaixo de 2 + 1 bp em todas as versões, a família não
tem custo que a salve.

## Por que pode falhar

Um instrumento e uma exchange; 5 min ≠ 15 m; sinais de fatores ≠ regra da `mean_reversion`; o custo
linear subestima impacto em alts pequenas (nosso universo tem PROM, SAHARA, TAO); o holdout é
retrospectivo, não prospectivo; o nosso 4 bps "não é maker nem taker" (KB-0038).

## Segunda opinião (Astra)

`astra-review-plantao-20260910-0730.md` (2026-09-10 11:47–11:51 BRT): concorda com o uso (auditar dados
e custos), corrige a leitura das 460 células (dependentes) e do holdout (retrospectivo), pede a fronteira
com IC e cobertura em vez de "célula de equilíbrio", spread fixado uma vez, e a célula maker só como
sensibilidade. Ordem: D-P15 (contabilidade de funding) → D-P14 (esta) → D-P13.

## Relacionados

[[Strategy Backlog]] · [[KB-0082-reversao-de-15-minutos-o-sinal-e-o-fluxo]] ·
[[KB-0076-por-que-perdemos-2026-09-08]] · [[KB-0084-tres-motores-abertos-funding-latencia-e-nulo]] ·
[[KB-0085-auditoria-de-liquidez-o-sinal-de-uma-covariancia]] ·
[[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] · [[EXP-0025-mean-reversion-90-dias]] ·
[[Plantao/2026-09-10]] · [[Hipoteses-do-plantao]] · [[11-KNOWLEDGE/Index|Conhecimento]]
