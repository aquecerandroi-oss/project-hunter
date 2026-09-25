# R79 — H-019 (fluxo desacelerando) + H-017 (julgamento formal do braço recuo_v1)

Início: 2026-09-25. Notas incrementais (uma tentativa anterior de outro estudo travou).

## 0. Lido antes (regra Obsidian primeiro)
- KB-0149: §3 nada na entrada separa vencedora de perdedora (13 variáveis esgotadas; `buys_1m` pico, não patamar); §5 itens 24–26 (antecipação, limiar escolhido olhando = zero, patamar × pico); §2 a saída atual é a certa.
- KB-0157 (H-016 REFUTA): o ganho do recuo é de preço (+2,18 de +2,28 pp no papel), não entrar custa (as que não recuam são as vencedoras), o modelo é ~5,8 pp otimista vs real (+0,41 % modelado × −5,42 % real nas mesmas 65).
- KB-0158: H-015 REFUTA pela cláusula das vencedoras (36,5 % > 30 %); H-018 limite de dado; fila `mint_busy` recompra com dado velho.
- Fila: H-017 (≥150 resolvidas; CONFIRMA D ≥ +2 pp, IC>0 e bate "nada"; REFUTA IC sup < +1 pp ou não bate nada) e H-019 (tercil baixo de aceleracao_compra ≤ −0,05 vs alto, IC sup < 0, patamar, comprou_no_topo ≥ 1,5×; REFUTA IC sup > −0,01, pico, piso mata > 30 % das vencedoras, < 150 com fita completa = limite de dado).
- EXP-M24: protocolo congelado; no_pullback e pullback_killed:* = 0; censored/dropped/not_inserted/indeterminate/sem desfecho fora dos dois lados; primeira linha `entry_pullback_armed` por mint.
- docs/RESEARCH.md regra 6; DATABASE §64 (derived v3 windows 10s/30s/60s: buys, sells, buy_sol, ...; `{"reason":"window_not_covered"}`), §65 (a fita por features_end_time do braço é a de t0).
- Diários: 24/09 12 pares recuo +0,013 × sombra −0,067; 25/09 (24 h) recuo_v1 91 entradas +2,61 %/entrada, op5 papel 24 entradas −2,80 %.

## 1. Dados (extraídos 25/09 ~23:10Z, antes de calcular qualquer desfecho)
- `r79/q_pop.sql` → `r79/cache/pop.csv` (343 apostas): pista `meme_event_gate_v1`, porta `fluxo_e_holders/*`, `features_end_time ≥ 24/09 00:00Z`, reais (`meme_live_positions`) e papel (`meme_paper_bets`, `leg='single'`), fita juntada por `t.mint = p.mint AND t.as_of = p.features_end_time` (regra 6).
- Contagem cega (`r79/h019_count.py`): 340 com fita, 0 `derived.reason`, 0 janelas 10/60 s ausentes. **196 mints** (1.ª decisão por `features_end_time`, empate → real): recuo_v1 86, flow_v2/1 56, op5 real 38, op6 real 12, flow_v2/9 3, op5 papel 1. **195 resolvidas** (1 `indeterminate`), 100 em 24/09 e 95 em 25/09 (UTC); 145 papel, 50 real. **195 ≥ 150 → a cláusula de dado não dispara.**
- Distribuição de `aceleracao_compra` (SOL), cega ao desfecho: quantis 0/10/25/33/50/67/75/90/100 % = 0 · 0,042 · 0,297 · 0,548 · 1,028 · 1,620 · 2,061 · 3,794 · 6,0; 11 zeros (nenhuma compra nos últimos 10 s). Contagem: 0 · 0,218 · 0,5 · 0,639 · 1,0 · 1,466 · 1,714 · 3,219 · 6,0.
- `r79/q_h017.sql` → `r79/cache/h017.csv`: 171 armações `entry_pullback_armed` (171 mints, 24/09 05:46Z → 25/09 23:06Z), com a proposta/aposta do braço em `features_end_time = t0`, a trilha posterior e a proposta/aposta de `operator/5` no mesmo `(mint, t0)`.
- **Achado estrutural (H-017):** a "sombra de papel do `operator/5`" **só existe quando a mesa real aceita a proposta** (`status = filled`: 43 propostas → 43 apostas de papel + 42 reais). Nas 171 armações: op5 `filled` 39, `rejected` 122, `expired` 9, sem proposta 1. As recusas são do `auto_stage1` (checks da mesa): `creator_flow_unknown` 38, `below_min_sol` 29, `participation_above_cap` 16, `creator_net_seller` 14, `bundled_share_above_cap` 11, `top10_share_above_cap` 7, `top10_share_unknown` 3, cooldown 2, outros 2. O braço `research_only` **não** passa por esses checks → opera 122 decisões que a mesa real recusou. O controle emparelhado só existe em ~39 decisões.
- Retenção: `meme_gate_refusals_by_mint` (onde vivem `entry_pullback_armed`, `no_pullback`, `pullback_killed`) é podada em **7 d** (§54.2). As armações de 24/09 somem em ~01/10. O cache `r79/cache/h017.csv` guarda a trilha de hoje.

## 2. Desenho (congelado ANTES de calcular desfechos)

### 2.1 H-019 (Parte A)
- **População P:** 1.ª decisão por mint (`features_end_time`; empate → real, depois `entry_at`) entre as apostas da porta `fluxo_e_holders/*` na pista de eventos com fita; fita completa = janelas `10s` e `60s` com `buy_sol` (a própria regra `window_not_covered` da fita) e `derived.reason` nulo; resolvida = fechada, `pnl_sol` não nulo, `outcome_quality ≠ indeterminate`. n = 195.
- **r** = `pnl_sol ÷ SOL gasto` (real: `sol_spent_lamports/1e9`; papel: `entry.sol_spent`).
- **Variável:** `acc = (buy_sol_10s/10) ÷ (buy_sol_60s/60) = 6·buy_sol_10s/buy_sol_60s` ∈ [0, 6]; `buy_sol_60s = 0` → ausente (nunca zero). Secundária: o mesmo com `buys` (contagem).
- **Tercis de posto** da amostra P (cegos ao desfecho): baixo `≤ q1/3`, alto `> q2/3`, empates juntos. **D = média r(baixo) − média r(alto)**.
- **IC 95 %:** bootstrap por mint, 10 000, semente 79 (uma linha por mint, logo = bootstrap de linhas). **p:** permutação estratificada por dia UTC (`infra.research.resampling.permutation_p`, 10 000) no subconjunto baixo ∪ alto. **Holm** na família {SOL, contagem}.
- **Patamar:** extremos vizinhos `baixo ≤ Q(q)` × `alto > Q(1−q)`, q ∈ {0,20; 0,25; 0,30; 1/3; 0,40; 0,45; 0,50}; partições iguais colapsam. Patamar = os dois vizinhos imediatos do corte (q 0,30 e 0,40) com D ≤ −0,05 no mesmo sentido.
- **Complemento pelo moinho:** `run_hypothesis` com o enquadramento "piso" (selecionados = `acc > c1`, direção `high`, limiar congelado `c1`, MRE 0,05, grade = valores de `acc` nos mesmos quantis). Observabilidade: `as_of` = `derived.as_of` (captura síncrona), `computed_at` = `derived.as_of`, `tape_as_of` = maior `received_at` das trocas da fatia; decisão = `decided_at` da proposta.
- **`comprou_no_topo`** (T4.92, `meme_daily_ficha_classify.py`): perda **e** pico ≤ custo. Real: `high_water_sol ≤ initial_risk_sol`. Papel: `high_water_x ≤ 1` (`high_water_x` = maior marca líquida de venda ÷ SOL gasto, `paper_engine.mark_bet`). Taxa por tercil = casos ÷ decisões do tercil com marca; previsão: baixo ≥ 1,5× alto.
- **Contrafactual real:** todas as posições reais da pista com fita completa desde 24/09 (não só a 1.ª por mint); piso = `c1` congelado de P; bloqueadas = `acc ≤ c1`; ΔSOL = −Σ pnl das bloqueadas; perdas e ganhos bloqueados em SOL; vencedoras mortas nomeadas.
- **Regra de rótulo** (com a errata do R76 §0.4b-4, adotada antes do contraste): n < 150 → limite de dado; min(baixo, alto) < 20 → não identificável; (c) vencedoras no tercil baixo ÷ todas as vencedoras > 30 % → REFUTA (c); IC inferior de D > −0,01 → REFUTA (intervalo); D ≤ −0,05 **e** IC sup < 0 **e** patamar **e** `comprou_no_topo` ≥ 1,5× **e** o piso bloqueia mais perdas que ganhos → CONFIRMA; D ≤ −0,05 com IC sup < 0 mas sem patamar → REFUTA (b); a cláusula (a) literal (IC sup > −0,01) sozinha → NÃO CONFIRMA; resto → NÃO CONFIRMA. Nota estrutural: um tercil tem ~1/3 das linhas, então a (c) só não dispara se a taxa de vitória do baixo for < 0,9× a média.
- **Sensibilidades (descritivas):** (s1) sem `recuo_v1` (só braços de entrada imediata; o braço do recuo compra depois de `t0`, a variável é de `t0`); (s2) só reais; (s3) `gaps = 0`; (s4) por dia.

### 2.2 H-017 (Parte B) — protocolo do EXP-M24
- Decisão = 1.ª `entry_pullback_armed` por mint. Braço: aposta de papel resolvida → `r = pnl/sol_spent`; 1.ª linha de desfecho do recuo na trilha depois de `t0` = `no_pullback` ou `pullback_killed:*` → 0; `pullback_censored:*`, `pullback_dropped_cap`, `pullback_not_inserted/insert_failed/insert_saturated`, aposta `indeterminate`, armação sem desfecho → fora dos dois lados, contadas.
- Controle: aposta de papel de `operator/5` na mesma `(mint, t0)` resolvida; sem controle → fora dos dois lados, contada.
- (a) D = média(r_braço − r_op5) emparelhado, IC bootstrap por mint 10 000; (b) média r_braço contra 0 (mesmo IC). Julgamento só com ≥ 150 decisões resolvidas **emparelhadas** (a população do bloco é "emparelhadas com a sombra do operator/5"); abaixo disso, limite de dado com contagem e ETA. Descritivo: (b) em todas as decisões do braço (sem exigir controle), por dia UTC, e a nota do otimismo papel × real (~5,8 pp, R77).

### 2.3 Astra (desenho)
- **Astra indisponível:** `codex` devolveu `401 Unauthorized` (credencial rejeitada) nas duas tentativas de 25/09 ~23:20Z (`.claude/state/astra-stderr.log`). Desenho seguido como escrito em §2.1–§2.2, sem revisão externa; nova tentativa no veredito.
- Testes sintéticos: `r79/test_r79.py` (10 casos: valores conhecidos da aceleração, ausente ≠ zero, a variável não muda com trocas posteriores, a guarda do moinho apanha um batoteiro que lê depois da decisão, 1.ª por mint, tercis com empates, pico ≤ custo real/papel, classificação das armações, emparelhamento com 0 e fora sem controle).

## 3. Resultados H-019 (saída integral: `r79/h019.txt`; moinho: `r79/h019_mill.txt`; testes `r79/test_r79.py` 11/11)
Guardas (195): 0 trocas da fatia recebidas depois do `as_of`; `derived.as_of` = `as_of` em todas; 0 fitas depois da aprovação; gravação − `as_of` p50 0,98 s, máx 2,02 s (buffer assíncrono, só escrita). Moinho: 0 recusadas pela guarda.

| linha | n | cortes q1/3 · q2/3 | média r baixo / meio / alto | **D (baixo − alto) [IC 95 %]** | p perm (dia) | vencedoras no baixo | comprou_no_topo baixo → alto |
|---|---|---|---|---|---|---|---|
| **primária, SOL** | 195 (50 real) | 0,548 · 1,620 | −0,0099 / −0,0295 / −0,0468 | **+0,037 [−0,109, +0,183]** | 0,62 | **25/72 = 34,7 %** | 35,4 % → 40,0 % (**0,88×**) |
| secundária, contagem | 195 | 0,639 · 1,466 | −0,043 / +0,004 / −0,047 | +0,004 [−0,142, +0,144] | 0,95 | 22/72 = 30,6 % | 44,6 % → 43,1 % (1,04×) |
| Holm {SOL, contagem} | | | | | 1,0 · 1,0 | | |
| s1 sem recuo_v1 | 114 | 0,429 · 1,824 | −0,059 / −0,039 / −0,101 | +0,042 [−0,139, +0,227] | 0,68 | 30,3 % | 0,81× |
| s2 só reais | 50 | 0,485 · 1,450 | +0,006 / −0,020 / −0,072 | +0,078 [−0,054, +0,227] | 0,32 | 26,3 % | 23,5 % → 41,2 % (0,57×) |
| s3 gaps = 0 | 194 | | | +0,042 [−0,105, +0,190] | 0,58 | 36,1 % | 0,88× |
| s4 24/09 | 100 | | | +0,099 [−0,114, +0,323] | 0,38 | 39,5 % | 0,97× |
| s4 25/09 | 95 | | | −0,021 [−0,153, +0,107] | 0,76 | 29,4 % | 0,92× |

- **Sinal contrário à tese**: o tercil que desacelera rendeu **mais** (−1,0 %) que o que acelera (−4,7 %). Curva primária: D ∈ [+0,001, +0,073] em todos os 7 cortes, nenhum ≤ −0,05 → sem patamar no sentido previsto. Moinho (piso = seleciona `acc > c1`): D −0,028 [−0,149, +0,086], p 0,65, "pico", NÃO CONFIRMA.
- **Contrafactual real (piso SOL `acc > 0,548`)**: 60 posições reais com fita completa (Σ −0,1347 SOL); bloqueia 20: perdas evitadas −0,0839, ganhos mortos +0,0911 → **Δ −0,0072 SOL** (bloqueia mais ganho que perda), **6 de 21 vencedoras mortas**: SMITH +0,0154, CALLS +0,0122, Relaunch +0,0290, PREDICTED +0,0144, MEMEos +0,0123, $LAG +0,0078. Pela contagem (descritivo, secundária): Δ +0,0453, também 6 de 21 vencedoras (CALLS, SELVAGE, FACRO, PREDICTED, MEMEos, $LAG).
- **Rótulo (regra §2.1):** SOL → **REFUTA por (c)** (34,7 % > 30 %); contagem → REFUTA por (c) (30,6 %). A cláusula (a) literal também dispara (IC sup +0,183 > −0,01) — pela errata do R76 sozinha seria NÃO CONFIRMA; o intervalo não sustenta refutação estatística (IC inf −0,109). (b) não se aplica como refutação (sem efeito no sentido previsto para ter patamar ou pico); a previsão secundária falha (0,88× < 1,5×) e o piso não bloqueia mais perdas que ganhos.

## 4. Resultados H-017 (saída integral: `r79/h017.txt`; verificação do mecanismo `r79/pb_check.txt`)
- **Armações (1.ª por mint, 24/09 05:46Z → 25/09 23:06Z, 41,3 h): 171** — entrou 141, `pullback_killed` 16 (holders_below_min 6, participation_above_cap 5, creator_sold_during_wait 4, progress_trend_unknown 1), `no_pullback` 9, `pullback_censored` 5 (feed_lost 4, no_base_row 1). Resolvidas: 166.
- **Controle emparelhado existe em 39** (op5 `filled`); 127 resolvidas sem controle (op5 `rejected` 122 pelo `auto_stage1`, `expired` 9, sem proposta 1).
- **(a) D = braço − op5 = +0,0324 [−0,0062, +0,0819]** (n 39; braço −0,022 [−0,085, +0,045], op5 −0,055 [−0,130, +0,022]); melhor em 10, pior em 7, **igual em 22**. **(b) contra nada nos pares: −0,022 [−0,085, +0,045].**
- **Rótulo: LIMITE DE DADO (39 < 150 decisões resolvidas emparelhadas).** Não julgado.
- Por dia (UTC = BRT aqui; nenhum par entre 00–03Z): 24/09 n 10, D +0,0755 [0,000, +0,225]; 25/09 n 29, D +0,0176 [−0,017, +0,055].
- **O "25/09 negativo" do brief foi reproduzido e é um artefato de contagem:** os 24 pares **só com entradas** de 25/09 somam recuo −0,0526 × op5 −0,0339 SOL; o protocolo manda contar `no_pullback`/`pullback_killed` como 0 — as 5 não-entradas de 25/09 (FACRO, COMO, otto, frenlock, $LAG) eram **todas perdas do op5** (−0,0358 SOL somadas); com elas 25/09 dá recuo −0,0526 × op5 −0,0884 SOL (D +0,0176/SOL).
- **Decomposição de D (+0,0324):** 22 pares **entraram na mesma foto do op5** (fill de papel idêntico, contribuição 0,0000); 12 em foto posterior: +0,0125; 5 não-entradas: +0,0200. **Sem o Megawatt** (op5 −80,8 % por `creator_dump`, braço −6,1 %): D **+0,0136 [−0,0128, +0,0423]**.
- **Achado de fidelidade (o mais importante da Parte B):** o papel preenche "na primeira foto depois de `decided_at`". A sombra do op5 entrou 0,8–16 s depois de `t0` (mediana 9,6 s, p90 14,4 s — a foto seguinte), e o gatilho do braço veio em mediana 5,5 s (p10 0,8 s, p90 25 s) — antes dessa foto em 22 dos 34 pares que entraram. **Nesses 22 o papel não mede preço nenhum: os dois braços compram no mesmo ponto.** O que a H-017 queria medir (+2 pp de preço na entrada) só aparece nos 12 pares em foto posterior e na real, que pousa em ~1 s. Mais: em 59 de 141 gatilhos o preço do gatilho estava **acima** do preço de `t0` (subiu e recuou 3 % da nova máxima); mediana gatilho/t0 = 0,972 (p10 0,935, p90 1,193).
- **Verificação do mecanismo (EXP-M24 item 1):** 141 blocos `entry_pullback`, **0** com `trigger_price > armed_max_price × 0,97`. Item 2 (0 entradas depois de venda do criador): 4 mortes `creator_sold_during_wait` registradas; não refeito na fita.
- **Descritivo (b) em todas as 166 resolvidas do braço (sem exigir controle):** +0,0056 [−0,0385, +0,0511], Σ +0,0656 SOL; nas 39 que o op5 aceitou −0,022; nas **127 que a mesa real recusou +0,014** [−0,039, +0,071]; 24/09 +0,018, 25/09 −0,005. O "+2,61 %/entrada" do diário vem sobretudo das decisões que a mesa real **não** toma.
- **Papel × real (mesma proposta do op5, n 38):** real − papel = **+0,002 [−0,087, +0,086]** por SOL — nesta coorte o papel ao vivo não foi otimista em média (IC largo). Os ~6 pp do R77 (+0,41 % modelado × −5,42 % real) eram do **simulador** do R77 com aluguel de ATA e saídas históricas, não do motor de papel ao vivo; a ressalva continua a valer para qualquer leitura de nível do braço.
- **Ritmo e ETA:** 10 pares em 24/09 (coorte começou 05:46Z), 29 em 25/09. A ~29 pares/dia faltam 111 → **~4 dias (≈ 29–30/09)**, e **só se a mesa real continuar aceitando** (a sombra nasce da aceitação; mesa pausada = 0 pares). A trilha das não-entradas é podada em 7 d: as armações de 24/09 somem ~01/10 — o cache `r79/cache/h017.csv` guarda 24–25/09.

## 5. Astra (veredito)
- **Astra indisponível** também no veredito: `codex` → `401 Unauthorized` (credencial rejeitada), 25/09 ~23:50Z. Revisão adversária própria no lugar: (i) tercis cortados depois da censura do desfecho — só 1 linha `indeterminate`, efeito desprezível; (ii) a junção do controle cobre 170 de 171 armações (1 sem proposta do op5); (iii) a decomposição de D soma exatamente ao total (0 + 0,0125 + 0,0200 = 0,0324); (iv) o "25/09 negativo" do brief reproduzido ao dígito, o que confirma a junção.

## 6. Vereditos e entregáveis
- **H-019: REFUTA pela cláusula (c)** (34,7 % das vencedoras no tercil baixo > 30 %), com o efeito no sentido contrário (D +0,037 [−0,109, +0,183]); fila `status: concluída` + `veredito`. Sem CONFIRMA → nenhuma especificação de braço de papel.
- **H-017: LIMITE DE DADO** (39 < 150 emparelhadas); fila `status: em curso` (era `aberta`; o braço corre desde 24/09) + `veredito`. Fila recarrega (19 hipóteses) e `infra/research/tests/test_queue_and_report.py` 15/15.
- KB: `obsidian/11-KNOWLEDGE/KB-0159-a-desaceleracao-nao-avisa-o-topo.md`. EXP-M24: seção "Avaliações (acrescentadas, nunca reescritas)" com a avaliação de 2026-09-25 no fim da página; nada anterior editado (o frontmatter da EXP tem mudanças de outra pessoa, não mexidas).
- Só SELECT na VPS (transação `default_transaction_read_only=on`); nenhum `.env`, nenhuma chave, nenhum commit, nenhuma ordem, nenhum parâmetro mudado.
