---
tags: [experimento, meme, entrada, cooldown, mint, trailing, m4, r64]
status: rascunho (pré-registro proposto; nada ativado)
owner: sexta-feira
updated: 2026-09-19
origem: R64, 19/09/2026 — Musepaid recomprada 25 s depois de uma saída por trailing; diário de 19/09 ("candidata a pausa por mint")
previsao: confirma no papel (R das recompras < 0) → candidata a portão de entrada na mesa; se as recompras rápidas (< 60 s) forem a exceção positiva, o desenho da pausa muda
---

# EXP-M21 — Pausa por mint depois de uma saída por trailing: a recompra paga?

## Hipótese
Uma moeda de que acabámos de sair por trailing (o pico já cedeu ≥ 10 %) **não** merece uma nova entrada nos 5 min seguintes:
a segunda entrada tem R médio negativo e acerto abaixo da base, em qualquer conjunto de regras. A pausa por mint é um
portão de **entrada** barato (uma consulta ao livro de posições/apostas) e não toca nas saídas.

## Por que agora
R64 (KB-0146): nas 294 apostas de papel de 19/09, **19 entradas depois de uma saída por trailing no mesmo mint (qualquer
conjunto) deram 0 acertos, −0,338 SOL, R médio −0,58** (base do dia −0,125); depois de qualquer saída por perda
(trailing/max_loss/line_broken/creator_dump) foram 54 entradas, 9 acertos, R −0,28. Nas 24 reais a mesma pausa **tira um
alvo** (NARKY#2, +0,014 em 6 s — a mesa real chegou antes dos espelhos de papel, que perderam todos) e uma perda pequena
(Musepaid#2, −0,002). Populações discordam; só a medição prospectiva resolve.

## Método (papel primeiro, `research_only`; sem tocar na mesa)
- Sem braço novo: **medir como filtro contrafactual** sobre todas as apostas de papel fechadas e sobre a mesa real,
  por 3 dias (esperadas ≥ 40 recompras no papel; hoje foram 19 + 35 fora da janela de trailing).
- Definição congelada: `recompra` = aposta/posição cujo mint teve uma saída por `trailing` (reason exato) de **qualquer**
  conjunto nos `W` minutos anteriores à entrada, `W ∈ {5, 15, 60}`; sub-corte `same_set` (mesmo conjunto) e
  `fast` (entrada < 60 s depois da saída — o caso Musepaid/NARKY#2).
- Métricas: R médio e mediano das recompras vs não-recompras (mesmo conjunto, mesmo dia), acerto, soma PnL SOL, n;
  para a mesa real, PnL SOL que a pausa teria tirado/poupado, alvo a alvo.
- Origem dos limiares: W = 5 min é o que hoje cobre 100 % das recompras (todas em < 5 min); 15/60 são sensibilidade.

## Regra de decisão (congelada)
- **Confirma** se, em 3 dias e n ≥ 40 recompras no papel, o R médio das recompras for < 0 com IC95 abaixo de zero **e**
  a soma que a pausa tira da mesa real for ≤ 0 (não custar alvo líquido) ou o `fast` explicar toda a diferença.
- **Descarta** se o R médio das recompras não for distinguível da base ou se na mesa real a pausa custar > 0,01 SOL/dia.
- Se `fast` (< 60 s) tiver R > 0 e o resto < 0, o desenho vira "pausa de 60 s a 5 min", não de 0 a 5 min.
- Confirmado → candidata a portão de entrada (um dia de validação: replay + estresse + replicação) — decisão do Everton.

## Não faz parte
Mudar trailing, alvo ou armar depois: R64 mostrou que na amostra de 24 a regra atual foi a melhor de 52 braços e que os
rugs são de um bloco (KB-0146). Fechar a ATA na venda cheia (`MEME_CLOSE_ATA_ON_FULL_SELL=1`, T4.46) é operação, não
experimento — 0,030 SOL do prejuízo de 19/09 e 0,051 SOL parados em 34 contas.

Ligações: [[KB-0146-trailing-apertado-e-rent-de-ata]] · [[KB-0143-o-que-antecede-o-dump]] · [[KB-0141-sniper-de-lancamento]] ·
`.claude/state/notes-R64.md` · `.claude/state/r64/metrics.py` (`cooldown_bets`, `cooldown_positions`)
