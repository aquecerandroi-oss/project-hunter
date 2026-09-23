# R67 — pré-registo (escrito ANTES de correr `oos.py`, 23/09/2026)

**Hipótese (do R65, escolhida in-sample nas 87 operações reais):** `buys_1m` (compras no minuto
anterior à decisão, gravado em `meme_proposals.reasons`) é **inversamente** relacionado com o
desfecho. Corte candidato: `buys_1m <= 25`.

**Desfecho primário:** retorno líquido por SOL arriscado, `ret = pnl_sol / size_sol`.
**Secundário (descritivo):** `hit15 = high_water_x >= 1,15` — proxy do alvo +15 % da mesa real.
O `hit15` é confundido pelo tempo de vida da aposta; por isso reporto o hold mediano por balde e
**nunca** promovo nada por ele.

**Teste primário, UM só, congelado:** corte fixo `buys_1m <= 25` na fatia principal (apostas de papel
`flow_v2`, 12–21/09, fechadas, `outcome_quality='measured'`, excluídas as propostas que também
viraram posição real). p por **permutação estratificada por dia** (10 000); IC 95 % por **bootstrap de
cluster de mint** (10 000).

**Tudo o resto é curva/robustez, não teste:** varredura de limiares fixos (10/15/20/25/30/40) e
percentis móveis (P30/P40/P50/P60 dos 3 dias anteriores), fatias por braço e por dia, split temporal
(ajustar em 19–20/09, testar em 21/09), estratificação por idade/progresso/SOL real na curva.

**Critério de sucesso (decidido antes de ver qualquer número):**
1. sinal da diferença positivo (`<=corte` melhor) em **≥ 3 das 4** fatias independentes;
2. p de permutação **< 0,05** na fatia principal com o corte congelado 25;
3. a curva de limiares mostra **planalto**: ≥ 4 limiares consecutivos com diferença positiva, e IC 95 %
   que não cobre zero em pelo menos 2 deles;
4. o efeito sobrevive à estratificação por idade, progresso e SOL real na curva (média ponderada
   dentro de estratos com o mesmo sinal e ≥ 50 % do tamanho do efeito não-estratificado).

Falhar (2) **ou** (3) ⇒ veredito "não sobrevive, fica em sombra". Falhar só (1) ou (4) ⇒
"sobrevive fraco", parâmetro só em sombra com regra de refutação.

**Ressalva estrutural assumida antes de correr:** as apostas de papel `flow_v2` correm com
0,05 SOL / alvo 3× / 1800 s / trailing 35 %; a mesa real corre 0,07 / 1,15× / 300 s / trailing 10 %.
Isto testa a **direção** do efeito de seleção de entrada, não o PnL transferível.

---

## Emenda 1 — após a revisão de desenho da Astra, AINDA antes de correr qualquer teste

`.claude/state/astra-review-r67-design.md`. Mudanças aceites:

1. **Independência (o maior risco).** Excluo da fatia principal **todos os mints que aparecem nas 87
   do R65** (não só as propostas), e **deduplico para uma aposta por mint** (a mais antiga): vários
   braços `flow_v2` propõem a mesma moeda no mesmo tique e isso transformaria um movimento em cinco
   "confirmações". Com uma linha por mint, a permutação dentro do dia é válida (linhas independentes)
   e o bootstrap por linha é o bootstrap por cluster.
2. **`hit15` é descritivo, ponto final.** Depende da política de saída de cada braço; não é
   "probabilidade de tocar +15 % em 300 s". Não entra em nenhum critério de decisão. O ideal (máximo
   em 300 s fixos desde o fill, medido mesmo depois da saída) não está coberto por esta coleta.
3. **Exclusão de `indeterminate` pode selecionar.** Reporto as exclusões por balde e por dia e faço
   sensibilidade tratando as indeterminadas como retorno 0 e como pior caso.
4. **As 15 reais de 16–18/09 NÃO são holdout** — participaram das 87 onde o corte foi descoberto.
   Passam a ser reportadas como descritivas, não como fatia de validação.
5. **Critério de sucesso congelado (substitui o anterior):** Δ = média(`ret` com `buys_1m` ≤ 25) −
   média(`ret` com > 25) na fatia principal. **Confirmado** se: Δ > 0 **e** IC 95 % (bootstrap por
   mint) inteiramente positivo **e** p de permutação bilateral < 0,05, **sem reversão material** nas
   sensibilidades pré-definidas (dedup, indeterminadas, estratificação por idade/progresso/SOL real,
   leave-one-day-out). Caso contrário: **não confirmado**, e **não procuro outro corte**.
   A varredura de limiares fica como descrição da forma do efeito (planalto vs pico) — sem p, sem IC
   a decidir nada.
6. Mesmo um "confirmado" aqui **não autoriza dinheiro real**: mede associação **sob a saída
   `flow_v2`** (3×/1800 s/trail 35 %); a transferência para 1,15×/300 s não está demonstrada.
