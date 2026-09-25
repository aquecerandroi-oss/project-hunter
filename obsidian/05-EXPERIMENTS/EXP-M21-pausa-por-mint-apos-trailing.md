---
tags: [experimento, meme, entrada, cooldown, mint, trailing, m4, r64]
status: rascunho (pré-registro proposto; nada ativado)
owner: sexta-feira
updated: 2026-09-19
origem: R64, 19/09/2026 — Musepaid recomprada 25 s depois de uma saída por trailing; diário de 19/09 ("candidata a pausa por mint")
previsao: confirma no papel (R das recompras < 0) → candidata a portão de entrada na mesa; se as recompras rápidas (< 60 s) forem a exceção positiva, o desenho da pausa muda
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: recompra
mercado: meme
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

## Contraexemplo registrado (20/09/2026, parecer da Astra sobre R64)

**NARKY#2 é o contraexemplo, e fica escrito antes da coleta.** Nas 24 operações reais de 19/09 a pausa de
5 min teria removido **um alvo vencedor** (NARKY#2, **+0,0142 SOL**, alvo em 6 s, recompra 25 s depois da saída
por trailing de NARKY#1) e uma perda pequena (Musepaid#2, −0,0018) — saldo **−0,0124 SOL** para a mesa real
naquele corte, contra 0/19 e −0,338 SOL nas recompras de papel. O "0/19 papel, 1 real" da justificativa original
omitia isso; a leitura honesta é: **populações discordam, e a mesa real perde um alvo**.

**5 vs 15 min é indistinguível com os dados de hoje:** todas as recompras (papel e real) ocorreram em **< 5 min**
(R64 §5), então `W = 15` e `W = 60` produzem exatamente o mesmo corte — não há evidência específica para 15 min,
só para "menos de 5". A pausa continua em **avaliação prospectiva** (não é melhoria demonstrada); o Everton pode
escolhê-la como limite de exposição repetida, não como vantagem. A regra de decisão acima não muda: `fast`
(< 60 s) com R > 0 e o resto < 0 vira "pausa de 60 s a 5 min".

Fonte: `.claude/state/astra-review-estrategia-2026-09-20.md` (item 2) · `.claude/state/notes-R64.md` §5.
Família alternativa proposta no mesmo parecer: [[EXP-M22-absorcao-de-venda]].

## Aplicada no real em 20/09 (T4.78, decisão do Everton)

**Aplicada no real em 20/09 por decisão do Everton, 300 s, medição em sombra; regra de decisão em 3 dias.**
Everton, 20/09/2026 00:3x BRT: "eu exijo que mexa pelo menos um pouco na estratégia". Contra o parecer da Astra
(item 2 acima — manteria em papel), ele escolheu aplicar a pausa como **limite de exposição repetida**, não como
vantagem demonstrada. O que foi ligado:

- **Check 28 `mint_cooldown_after_loss`** no motor puro (`hunter_risk_meme`, `docs/RISK_ENGINE_MEME.md` §4): depois de
  uma posição **real** fechar com `pnl_sol < 0`, nenhuma compra nova no mesmo mint por `MEME_MINT_COOLDOWN_AFTER_LOSS_S`
  segundos (padrão **300**; `0` desliga). Vale para `operator/5`, `operator/6` e a pista de lançamento; vendas nunca.
  Recusa `mint_cooldown_after_loss:<segundos restantes>`. 300 e não 900: todas as recompras observadas (papel e real)
  vieram em < 5 min (R64 §5), não há evidência para mais.
- **Medição em sombra:** o check roda **por último**, então `meme_live_orders.reason = mint_cooldown_after_loss:*` só
  aparece quando tudo o mais passou — cada linha dessas é uma entrada que a mesa teria feito. Contagem por nome em
  `hb:meme:executor` → `refusals.mint_cooldown_after_loss`; a janela em `policy.mint_cooldown_after_loss_s`. A proposta
  aberta pelo robô (estágio 1) continua sendo marcada `rejected` como qualquer recusa — o papel **não** preenche essa
  proposta específica; a contrafactual continua vindo dos braços de papel sem pausa (a população da R64 §4) e das
  linhas `refused` acima. O robô não reabre o mint enquanto a recusa esfria (`refusal_cooldown`: espera **os segundos
  restantes anunciados** na recusa, capados pelos 120 s do dono — nunca uma janela fixa reiniciada), para não gastar
  três leituras RPC por reproposta.
- **Revisão da Astra (20/09, `.claude/state/astra-review-T4.78-mint-cooldown.md`):** dois achados, ambos corrigidos
  antes de integrar — (1) a leitura das perdas é **por mint da proposta** (uma linha), não "últimos 50 mints", que numa
  janela saturada omitiria o candidato e leria como "sem perda"; (2) o robô do estágio 1 espera o restante anunciado
  (`:10` = 10 s), não os 300 s do teto. Ela mantém a segunda opinião: limite de exposição, não vantagem demonstrada.
- **Regra de decisão em 3 dias (23/09):** somar, nas linhas `refused` com esse motivo, o que a compra barrada teria
  dado (preço do fill do braço de papel gêmeo ou da próxima foto da curva); se a soma for ≥ 0 (a pausa custou alvo),
  desligar (`=0`) e voltar ao papel; se for < 0 e n ≥ 10, manter e reavaliar a janela (60 s a 5 min, se o `fast` pagar).
  NARKY#2 (+0,0142) já está no lado "custou alvo" do corte de 19/09 — a conta começa dele.

