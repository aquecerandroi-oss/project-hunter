---
tags: [revisao-astra, cripto, custo, lab, diagnostico, mean-reversion, momentum]
date: 2026-10-07
updated: 2026-10-07
status: registro
owner: sexta-feira
decided_on: 2026-10-07
by: astra
tarefa: lab-cost-sweep — varredura de custo sobre os desfechos do Lab de cripto (R bruto, R do Lab, custo de equilíbrio k*, cenários Binance) e as candidatas ao próximo pré-registro
veredito: núcleo aritmético correto; 6 must-fix (redação, populações, horizonte, régua de custo, poder, momentum/volume_anomaly) aceitos e aplicados; rodada 2 achou resíduo em 2 e 3 e quatro números, corrigidos; ranking trocado — instrumento de custo antes da coorte da mean_reversion v14
---

# Revisão da Astra — varredura de custo do Lab (lab-cost-sweep)

**Pedido:** revisar o método (unidade de risco fixa, k* como razão de somas, bootstrap da razão por cluster, funding
ausente, spot sem funding, replays), a fidelidade da reprecificação, a aritmética de poder e o ranking das três
candidatas. Fonte bruta: `.claude/state/astra-review-lab-cost-sweep.md`. Resultado em
[[KB-0192-o-custo-do-lab-explica-a-perda-mas-nao-o-sinal]].

**Reprodução:** rodou `test_sweep.py` (14 passed), `check.py` (17 979 linhas; máx |dif| 7,5e-6 no `r_multiple` e
7e-11 no `r_ex_funding`) e `extra.py` (178 dias / 1 514 trades para a v14 a +0,10 R). Recalculou com `Decimal` as 5
linhas acima de 1e-6 usando o `exit_price` persistido: todas abaixo de 5e-11 R.

## Concorda

Unidade de risco `U` fixa (nomear "R do Lab"); k* como razão de somas, não média de k* individuais; bootstrap que
reamostra somas por cluster e recalcula a razão; funding desconhecido nunca vira zero; spot sem funding; replays
separados, sobreposição declarada, coorte futura reservada e nenhum rótulo de hipótese fabricado.

## Must-fix (todos aceitos)

1. **"Recomposição exata" → reprecificação condicionada.** A admissão depende do custo (`walker.py`, `_enter`:
   `stop < entry_price(open, custos) < alvo1`); com a abertura no stop, o Lab admite pelos 6 bp adversos. Corrigido
   no `sweep.py` e na nota; maker/rebate supõem preenchimento; spot é sensibilidade sobre preço de perpétuo.
2. **Populações todos × com funding com as próprias contagens.** Falha medida: replay v10 `c7d138eb` aparecia com
   +0,193 R ao lado de "89 dias", mas +0,193 é de 300 desfechos em 33 dias (todos: 798 em 89 dias, +0,073).
   `run.py` reescrito; o cenário sem funding passou a usar todos; spot rotulado "reconstruído sem funding".
3. **Horizonte ≠ custo.** A v1 já tem 4 h; a v7 mudou o stop (2 ATR). A queda do custo em R vem da unidade de risco;
   a candidata 3 passou a exigir justificativa de trajetória, não economia de custo.
4. **Mediana não decide.** 51 % a 10 bp e 49 % a 30 bp: mediana 10, custo efetivo 19,8 bp. Régua nova
   `Σ h·k / Σ h` (`sweep.effective_cost_bp`, com teste que falhou antes), entrada **e** saída.
5. **Poder qualificado.** A conta rejeita média = 0 quando a verdadeira é +0,10 R; dias com trades; sem paradas;
   referência condicional, potencialmente otimista. O pré-registro fixa calendário, futilidade e poder do
   procedimento completo.
6. **Redação.** "Momentum e volume_anomaly não são problema de custo" → "baratear não demonstra uma estratégia
   rentável"; o IC por dia do bruto da `momentum v3` contém zero (+0,006).

## Nice-to-have

Blocos de dias como sensibilidade extra (não feito; declarado que dia e mercado são duas sensibilidades, não
proteção conjunta); cobertura de pendentes/censurados (apontado o inventário `q_survey.sql`); a comparação spot/1 ×
sombra é descritiva e não identifica custo (escrito na nota).

## O que ela faria diferente — e o que mudou

Instrumento de custo **antes** da coorte da v14, podendo coletar as duas juntas depois de congelar o protocolo:
adotado. Manter a v14 pela escolha anterior, sem promovê-la a vencedora, e separar a escolha da linha paper (09/09)
da seleção para a `spot/1` (19/09, que usou os primeiros 23 sinais): adotado na nota. Discordância: nenhuma.

## Rodada 2 (só leitura; `.claude/state/astra-review-lab-cost-sweep-r2.md`)

Must-fix 1, 4, 5 e 6 **fechados**. Resíduo em 2 e 3, corrigido depois: a Tabela 1 da nota trazia mercados de todos os
terminais ao lado do `n` com funding (v1 112, não 113; e outros dez) — agora mercados e dias são da população com
funding e duração/atividade estão rotuladas "todos"; o `run.py` suprimia o cenário sem funding quando o subconjunto com
funding não tinha IC (replay v2 `7598d6c4`: todos 224 em 24 dias, −0,171 [−0,368; −0,002] no spot taker 10; com funding,
23 em 3 dias) — agora imprime; e uma frase "custo cai com o horizonte" que tinha sobrado virou "acompanha a unidade de
risco". Números corrigidos: sobreposição 48–100 % (não 55–99), outubro 1–5 dias (não 4), meses da v11 (bruto de
setembro +0,067, líquido −0,036), fator 10⁴ na fórmula de k*, 15 testes.

## Relacionados

[[KB-0192-o-custo-do-lab-explica-a-perda-mas-nao-o-sinal]] · [[KB-0191-oi-acima-da-semana-nao-separa-os-sinais-do-lab]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] · [[Mapa de Estrategias]] ·
[[Revisoes-Astra/Index|Revisões da Astra]]
