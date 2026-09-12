---
tags: [knowledge, nota, plantao, meme, pumpfun]
tema: memecoin / pump.fun / taxas-base / instrumento de coleta
fonte: Szwajcok et al. (arXiv 2609.10246, CCS'26); Kamat (arXiv 2607.02823 v3 + Zenodo RED-PUMP-2026-v1); Tarantelli, Marino, Naviglio & Lillo (arXiv 2602.14860); Kamat (arXiv 2607.02795 v3); MELT (arXiv 2602.13480 v2); Li et al. (arXiv 2608.20271); Chen et al. (arXiv 2603.24625 v2); Solidus Labs (05/2025); Dune jondar/pumpfun (congelado 03/2025)
fonte_url: https://arxiv.org/abs/2609.10246
lido_em: 2026-09-12
evidencia: um paper aceito em conferência (CCS'26) + cinco preprints com dado e método + um relatório de fornecedor + um dashboard Dune congelado; todos lidos por leitor automático de HTML/abstract em 2026-09-12 02:14–02:20 BRT; nenhuma medição própria; correções de leitura da Astra aplicadas
hipotese_testavel: sim
astra: concorda
status: vivo
owner: sexta-feira
updated: 2026-09-12
confiança: "?"
---

# pump.fun: as taxas-base e seus denominadores

> Nota do plantão T3.64 (run 13, faixa 1). Rascunho com todas as URLs e horas:
> `.claude/state/plantao/2026-09-12-0214-lane1.md`. Revisão: `.claude/state/astra-review-plantao-20260912-0214.md`.
> `confiança: "?"` porque a evidência é mista (paper aceito + preprints + fornecedor + dashboard) e nada foi replicado aqui.

## O que afirma

Não existe "a taxa de graduação da pump.fun". Os seis estudos empíricos abertos publicam números entre
0,198 % e "< 2 %" — e cada um mistura de forma diferente **período de coleta**, **seguimento individual
por token** e **razão de fluxos diários** (distinção da Astra). Além disso, o preprint mais novo (CCS'26)
mede manipulação em escala que muda o que "graduação" significa: wash trading atômico em ≥ 17 % das
transações, 63 % das criações vindas de clusters de criadores, 10 % de cópias. Graduação não é retorno;
a maioria das migradas colapsa em minutos.

| Estudo (lido em 2026-09-12) | O que a janela mede | Denominador | Período | Taxa |
|---|---|---|---|---|
| Kamat, arXiv 2607.02823 v3 (https://arxiv.org/html/2607.02823) | seguimento individual de **~6 min** — "Our collector's effective visibility window was approximately six minutes, not 24 hours" — limite inferior de 24 h | 832 941 com desfecho (860 213 lançamentos) | 08/05–10/06/2026 | **0,198 %** [0,189; 0,208] |
| Tarantelli, Marino, Naviglio & Lillo, arXiv 2602.14860 (https://arxiv.org/html/2602.14860) | seguimento individual até o fim do mês de coleta | 655 770 criados (184 282 com ≥ 30 swaps) | 01/09–01/10/2025 | **0,63 %** no texto; 4 338 ÷ 655 770 = **0,662 %** (Astra) |
| Szwajcok et al., arXiv 2609.10246 (https://arxiv.org/html/2609.10246v1) | período de coleta de 2 anos, todas as moedas | 15 245 966 | 14/01/2024–14/01/2026 | **1,02 %**; 2,0 % com WT1 vs 0,90 % sem; por intensidade 1–5 ocorrências 0,50 %, 6–25 0,65 % |
| Dune `jondar/pumpfun` (https://dune.com/jondar/pumpfun) | **razão de fluxos diários** (graduações do dia ÷ criações do dia) — não é graduação em 24 h de uma coorte | média 23 791/dia; 285 graduações/dia | congelado em 20/03/2025 (migração Raydium) | **1,13 %** |
| Mancino, arXiv 2512.11850 v3 (https://arxiv.org/abs/2512.11850) | não declarado no abstract | Q4 2024 | Q4 2024 | "Fewer than 2%" |
| MELT, arXiv 2602.13480 v2 (https://arxiv.org/html/2602.13480v2) | só migradas | 41 470 migradas | 12/2024–03/2025 | "<2% … reach migration stage" (afirmação) |

**O que acontece depois de graduar (mesmas fontes):** MELT — 84,13 % das migradas com rótulo "alto
risco" (mínimo da razão de preço < 0,3 em 20 min pós-migração **ou** anotação manual; pela tabela de
preço, ~72,95 % abaixo de 0,4 em 20 min — leitura da Astra); "36.5% of token supply is held by
coordinated accounts"; 21,4 % das transações pré-migração são wash. Chen et al. (arXiv 2603.24625 v2,
Orca/Raydium/Meteora, 1º sem. 2025) — vida mediana **0,01 dia**, "95.69%" das transações no dia 1,
78,9 % dos 76 469 candidatos a rug são pump-and-dump. Solidus Labs (05/2025) — "98.6% of tokens on
Pump.fun collapse" abaixo de US$ 1 000 de liquidez (≥ 5 trades, > 7 M tokens).

**Manipulação e sinais que a literatura já testou:**
- **WT1** (Szwajcok et al.): compra e venda da **mesma quantidade** pelo mesmo endereço dentro de **uma**
  transação — "17% of all trading transactions" (limite inferior); associação com graduação existe no
  agregado, mas **não** para 1–25 ocorrências.
- **Cluster de criador** por financiador comum (1 salto; 3 saltos): 322 620 / 290 319 clusters; top 1 %
  cria 58,6 %; maior cluster 10 531 endereços; "our data cannot assert malicious intent".
- **Cópias** por nome+símbolo+imagem (hash IPFS): 1,49 M (10 %); originais graduam 9,2 %.
- **Snipers** (Kamat, arXiv 2607.02795 v3, https://arxiv.org/abs/2607.02795): 1 012 cohorts persistentes;
  lift de **compradores** nos 30 min +16,1 % [13,0; 19,4]; lift de **entrada de SOL** +6,3 % [−0,5; 15,1],
  "not distinguishable from zero" — contagem de compradores é contaminável, SOL não mexeu.
- **Presença social** (Kamat 2607.02823): Cox HR Telegram 5,40 [4,73; 6,17], log(mcap) 4,51, Twitter 1,31,
  site 1,19 — com viés para baixo dependente da feature (janela de ~6 min); não é multiplicador causal.
- **Nº de trades até o nível de SOL** (Tarantelli et al.): sinal mais forte; poucos trades → maior
  probabilidade; breakeven de buy-and-hold `P(grad | vSol) > (vSol/115)²` e "all conditional
  graduation-probability curves remain below the economic breakeven over most of the vSol range";
  92,22 % dos tokens com ≥ 30 swaps têm ≥ 1 dump > 4σ antes da graduação; sem métrica out-of-sample.
- **Rug em 1 h com 5 min de dado** (Li et al., arXiv 2608.20271, https://arxiv.org/html/2608.20271v1):
  6,4 M tokens; XGBoost F1 0,7885, MCC 0,3947, AUCPRC 0,8011; "not yet sufficient for real-world
  deployment"; transferência entre venues MCC ≈ 0.

## Onde foi mostrado

Solana/pump.fun, on-chain (RPC/Geyser de terceiros, API pública da pump.fun, Jito bundle explorer,
Arkham) — nunca CEX. Períodos: Q4 2024 (Mancino), 12/2024–03/2025 (MELT, regime $TRUMP), 11/2024–06/2025
(Li), 1º sem. 2025 (Chen), 09/2025 (Tarantelli), 2024–2026 (Szwajcok), 05–06/2026 (Kamat). Custos: só
Tarantelli discute breakeven, **sem** gas, taxa de protocolo (1,25 %), taxa de criador e slippage.
Nenhum mede retorno líquido de uma política executável.

## Como mediríamos aqui

Só depois do T4.1/T4.2 (`meme_tokens`, `meme_trades`, `meme_snapshots`) — hoje não há dado próprio.
Pré-condições que esta nota fixa (Astra):
1. **D-P25 primeiro:** medir separadamente descoberta de criações e acompanhamento (curva, conclusão,
   migração, trades); referência independente por amostra de slots finalizados; cobertura por idade, dia,
   Mayhem, fonte; por horizonte, sucessos comprovados / negativos comprovados / desconhecidos; 99 % é
   indicador operacional, não garantia — perder seletivamente 1 % pode perder todos os graduados a 0,2 %.
   Antes disso, no dataset público (Zenodo, https://zenodo.org/records/21923106, 47,9 MB + 43,6 MB,
   CC-BY-4.0): reproduzir contagens, duplicatas, conflitos de desfecho e durações; só então a KM.
2. **Identidade por operação** em `meme_trades`: identificador canônico (assinatura + posição estável na
   transação), `UNIQUE` basta; `signature + (mint, side, amount)` falha (A compra 100 e B vende 100; A
   compra 100 duas vezes; CPI e log do mesmo fill). Sem isso, WT1 por token não é computável com fidelidade
   — o indicador binário por transação sim (uma linha por `signature`, resultado + versão do detector).
3. **Trades completos desde a criação** para a H-P29 (primeira passagem por nível); assinatura seletiva
   fabrica "poucos trades".
4. **Dois relógios:** `created_at` para exposição/conclusão; `migrated_at` para retorno pós-migração;
   acompanhamento até 14 d após a criação se a migração puder ocorrer até o 7º dia.

## Hipótese testável no Lab

Na fila [[Hipoteses-do-plantao]]: **D-P25** (instrumento), **H-P29** (associação trades × conclusão na
primeira passagem; política congelada com `p > (I−F)/(S−F)`, custos ×1,0254767, `vSol` virtual, saída
só após migração), **H-P30** (WT1 por intensidade e idade, marco de 1 h; retorno condicionado à migração),
**H-P27 reescrita** (volatilidade antecedente do BTC × conclusão em 24 h/168 h, coortes por dia UTC,
limites `[S/N, (S+U)/N]`), painel de reforço da **H-P28** (estratos de presença social e de cohort de
sniper; compradores únicos ao lado da entrada de SOL; `min_price_ratio_20m` pós-migração como desfecho
intermediário). Nenhuma é célula da `mean_reversion`; nenhuma toca execução.

## Por que pode falhar

- **Instrumento cego** (o corrigendo de Kamat): endpoint paginado → janela de minutos; todo timeout em
  ≈ 24 h e nada no meio; market cap ≠ graduação.
- **Denominadores diferentes** viram "tendência" falsa (0,2 % → 2,7 % pode ser janela, não regime).
- **Seleção e sobrevivência:** MELT e Chen só olham migradas/com pool; Tarantelli só ≥ 30 swaps para os
  dumps; Szwajcok usa 1 % das moedas.
- **Mudança de mecanismo:** PumpSwap (2025), Mayhem (11/2025), taxas por tier — nenhum estudo cobre o
  regime de setembro/2026.
- **Não transfere entre venues** (Li: MCC ≈ 0) e não transfere de graduação para retorno.
- **Multiplicidade:** um deploy de 15 dias com +117,7 % e p = 0,56 (Kamat 2606.08232) é o tipo de
  resultado que a [[KB-0079-onde-ganha-e-perde]] manda descartar.

## Segunda opinião (Astra)

Concorda com a tese (graduação ≠ retorno; market cap não prova liquidez; ausência não vira zero; prioridade
é evidência observável antes de sinal). Corrigiu nove leituras/desenhos: 0,662 % vs 0,63 %; WT1 por
intensidade; MELT ~72,95 % < 0,4; parábola só com `F = 0`; H-P29 em duas perguntas e primeira passagem;
identidade por operação em vez de "índice na PK"; H-P30 com marco de 1 h e dois relógios; H-P27
reescrita com volatilidade antecedente; D-P25 com descoberta e acompanhamento separados. Ordem de teste
dela: D-P25 → H-P29 → H-P30. Discordância residual: nenhuma.

## Relacionados

[[Strategy Backlog]] · [[Hipoteses-do-plantao]] · [[Plantao/2026-09-12|Plantão de 2026-09-12]] ·
[[KB-0065-a-coorte-de-memes-nao-se-distingue-do-resto]] · [[KB-0076-por-que-perdemos-2026-09-08]] ·
[[KB-0079-onde-ganha-e-perde]] · `docs/plans/T4-MEME-RADAR.md` · `.claude/state/notes-A4.1b-mayhem.md`
