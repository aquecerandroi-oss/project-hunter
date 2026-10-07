---
tags: [revisao-astra, cripto, custo, mean-reversion, pre-registro, sequencial, h-036]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: quant-engineer
decided_on: 2026-10-07
by: astra
tarefa: pré-registro da H-036 (mean_reversion v14 em coorte futura, ao custo Binance medido) e o instrumento de custo da KB-0193
veredito: "rodada 1 — não aprovaria como confirmatório: 9 must-fix (sequencial, REFUTA depois de parar, precedência, simulação fiel, B estrito, substituto de 15,7 bp, entrada passiva, export cego, manifesto), todos aceitos na emenda 1 (07:40:58Z); rodada 2 — 3 fechados, 6 parciais com 6 defeitos reproduzidos (quantil t permissivo, metades, população vazia, adiamento de REFUTA, p99/estresse, export da semana da consulta), todos aceitos na emenda 2 (07:54:07Z); rodada 3 — os seis fechados, nenhum must-fix novo; tudo antes de T0 = 12:00Z"
---

# Revisão da Astra — pré-registro da H-036

**Pedido:** revisar o bloco [[Fila de Hipoteses#H-036 — `mean_reversion v14` em coorte futura, ao custo Binance medido (a v14 tem vantagem fora da amostra?)|H-036]]
(registrado às 07:08Z, T0 = 2026-10-07 12:00Z) e o instrumento de custo
([[KB-0193-o-custo-binance-medido-nos-instantes-do-lab]]). Fontes brutas: `.claude/state/astra-review-H-036-prereg.md`,
`-r2.md`, `-r3.md`; código e saídas em `.claude/state/h036/` (manifesto `manifest.txt`).

## Rodada 1 — 9 must-fix, todos aceitos (emenda 1)

1. **Calendário ≠ informação.** O LD-OBF em frações de calendário supunha informação proporcional ao tempo; na
   simulação dela, informação tardia levava o cruzamento a 2,83 %. → **Haybittle-Peto com gasto de Bonferroni**
   (0,0005/0,0005/0,024), válido para qualquer distribuição da informação.
2. **REFUTA depois de parar pela própria média** não tem cobertura de análise fixa: com θ = +0,10 a regra dava REFUTA
   em 3,9–5,4 %. → limite t(**0,9975**) calibrado pelo procedimento inteiro.
3. **Rótulos contraditórios** (média 0,075, EP 0,005: CONFIRMA e REFUTA ao mesmo tempo) e portões só na final. →
   precedência portões → CONFIRMA → REFUTA/NC → continua; portões em toda consulta.
4. **A simulação não era o procedimento** (sem estresse, metades erradas, sem portões). → função de decisão única
   (`decision.decide`) usada pela simulação e pela consulta.
5. **"B estrito" não é política executável** (o toque sem atravessar exige esperar; saída na abertura testada contra o
   alvo original). → primário **todo a mercado**; B vira sensibilidade.
6. **15,7 bp não é teto** (é a média do estresse histórico). → sai da regra; portão de cobertura de 90 % e teste de
   instabilidade no p99.
7. **Entrada passiva:** a trajetória depois do preenchimento não é reconstruída por OHLC. → "não demonstrada nesta
   aproximação", não refutada.
8. **Export com bid/ask** deixava calcular o retorno; janela de 7 d truncada pela poda; exemplo antes de T0. → export
   **só de spread**, semanal, com contagem de snapshots e guarda de T0.
9. **Manifesto inexistente** e "nenhuma decisão até L3" contraditório. → manifesto com sha256 de tudo; decisões do
   protocolo permitidas, as demais encerram em LIMITE operacional.

Ao aplicar o item 4 achei um problema que ela não apontou: com choques persistentes de 5 dias (S5) o EP agrupado por
**dia** levava o alfa a **0,043** e o REFUTA indevido a 0,089 (`design2_calib.txt`); as somas diárias da coorte exposta têm
assimetria −0,81. → EP agrupado por **semana ISO** (alfa S5 0,019).

## Rodada 2 — 6 defeitos reproduzidos, todos aceitos (emenda 2)

1. Quantil t por Cornish-Fisher permissivo com 4 gl: t(0,9995; 4) 8,187 contra 8,610 exato; um t de 8,4 confirmava
   indevidamente. → **quantil exato** (beta incompleta + bisseção), recalibrado, constantes mantidas.
2. Metades com número ímpar de dias punham o dia mediano na primeira; um caso de 181 dias confirmava com a primeira
   metade negativa. → piso.
3. População só com `no_entry` quebrava `look.py`; o ensaio filtrava `exit_ts` e escondia pendentes. → contagens por
   estado, continua/LIMITE; o ensaio mantém `no_entry` e declara que não valida exclusões.
4. A instabilidade podia adiar uma parada por futilidade e criar novas chances de REFUTA; os erros simulados não eram
   tetos (IC de Wilson: alfa 0,0236 [0,0216; 0,0258], REFUTA 0,0189 [0,0171; 0,0209]). → REFUTA instável para como NÃO
   CONFIRMA; garantia escrita como união de Bonferroni **condicional** ao nível marginal do t + simulação declarada.
5. p90/p99 só do minuto exato; estresse reaproveitava o spread da saída quando faltava o minuto seguinte. → todas as
   pernas medidas; +1 → +2 min → p90.
6. A cadência semanal deixava sem export os sinais de segunda a quarta da semana da consulta. → **export complementar
   obrigatório** antes de abrir os desfechos.

## Rodada 3 — fechamento

Os seis fechados; 35 testes, 49 hashes conferidos sem divergência; **nenhum must-fix novo** antes de T0.

## O que ficou como desacordo ou limite declarado

Nenhuma discordância. Limites que a própria emenda declara: a garantia de erro é condicional ao nível marginal do t
agrupado por semana; a simulação reamostra só 25 dias expostos (não cobre regime novo); impacto e deslizamento do
stop não são medidos (cláusula de estresse); o ensaio não valida o portão de exclusões.

## Relacionados

[[KB-0193-o-custo-binance-medido-nos-instantes-do-lab]] · [[KB-0192-o-custo-do-lab-explica-a-perda-mas-nao-o-sinal]] ·
[[06-DECISIONS/Revisoes-Astra/lab-cost-sweep|lab-cost-sweep]] · [[KB-0149-o-que-a-mesa-real-ensinou]] ·
[[Fila de Hipoteses]] · [[Mapa de Estrategias]] · [[Revisoes-Astra/Index|Revisões da Astra]]
