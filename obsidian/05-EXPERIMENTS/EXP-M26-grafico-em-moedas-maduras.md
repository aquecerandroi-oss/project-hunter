---
tags: [experimento, meme, pumpfun, curva, paper, pesquisa, linhas, moedas-maduras, h-022, m26]
updated: 2026-09-26
status: desenho congelado (decisão conjunta com a Astra, 5 rodadas); construção em andamento — I1/L1/R1; nenhum braço semeado, nenhuma proposta
owner: quant-engineer
exp: EXP-M26
strategy: "meme/pumpfun — gráfico em moedas maduras (15–120 min, ainda na curva): grafico_ctrl_v1/1 (C, sem linha), grafico_v1/1 (L, linha + saída atual), grafico_v1/2 (H, linha + pacote de saída do EXP-M2) — os três research_only, carteira paper do Lab meme"
version: "porta comum grafico_maduro v1 (min_age_s/max_age_s 900/7200, progresso 5–90 %, participação ≤ 1 %, exclude_mayhem, size_sol 0,07); L/H com require_higher_lows+require_breakout_15m+banda 0–0,25; seed pela migração 00xx (T7 `S`, pendente)"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
tipo: pesquisa
hipotese: H-022
variavel: "linha_ok na 1.ª oportunidade por mint do controle grafico_ctrl_v1/1 — três classes congeladas (true/false/desconhecida), lida dos insumos gravados em meme_mature_opportunities (R1) no tique da 1.ª avaliação"
populacao: "oportunidades prospectivas com evaluated_at entre T0 e o corte — moeda 900–7200 s, na curva, progresso 5–90 %, não Mayhem, participação ≤ 1 % (≥ 7 SOL/min a 0,07 SOL), pedigree; unidade = 1.ª oportunidade por mint desde o seed (C) e 1.ª decisão comum por mint desde o seed (par H/L)"
efeito: —
ic: —
veredito: em_curso
proximo_passo: "I1+I2+L1+R1 (com testes de integração) -> C1 -> 24 h -> F -> J congelado -> S -> P (48 h) -> T0 -> corte (>= 7 d, <= 21 d) -> leitura (corte + 2 h)"
classe_de_perda: comprou_no_topo
mercado: meme
---

# EXP-M26 — estrutura do gráfico em moedas maduras (15–120 min, ainda na curva)

> **Desenho congelado em 26/09/2026**, autoria do quant-engineer com cinco rodadas de diálogo com a Astra
> (`.claude/state/dialogue-EXP-M26.md`, decisão conjunta na rodada 5). Protocolo completo em
> `docs/design/exp-m26-grafico-moedas-maduras.md`. **Nada foi semeado, nenhuma proposta existe, nenhum
> desfecho foi lido.** A seção "Protocolo" é escrita uma vez e **nunca** muda; avaliações são
> **acrescentadas** abaixo, datadas. H-022 está na [[Fila de Hipoteses]].

## O que é

- Os cinco estudos anteriores de entrada em moeda nova (R65/R67, H-016, H-019, H-020, H-021) fecharam sem
  vantagem, e a H-021 mostrou que o limite é **estrutural**: a porta compra com 1,6 min de vida (mediana) e
  a linha de produção quase nunca existe nem chega às pistas rápidas
  ([[KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta]]). O EXP-M2 (`trendline_v0/1`) teve 0 propostas
  porque a linha **nunca foi julgada por desfecho**, não porque não houvesse mecanismo — ver "Avaliação de
  2026-09-26" em [[EXP-M2-a-linha-manda]].
- A ideia deste experimento: parar de procurar o gráfico onde ele não existe e testar moedas que **já têm
  gráfico** — 15–120 min de vida, ainda na curva, retidas por uma política nova de retenção
  (`MEME_TRACK_MATURE_TOP_K`, I1) em vez de podadas pelo rastreador aos ~13 min (p50).
- Ataca a maior classe de perda medida na mesa real: [[Perdas/comprou_no_topo|comprou_no_topo]] (20 casos,
  −0,2642 SOL em 24–25/09).
- Não é dinheiro real. Os três conjuntos são `research_only`: nascem aprovados por `rules`, o executor
  nunca abre ordem para eles.

## Braços (congelado — mudar qualquer item é braço novo e EXP nova)

**Porta comum `grafico_maduro` v1** (todos os três braços partem dela):

| parâmetro | valor |
|---|---|
| `min_age_s` / `max_age_s` | 900 / 7 200 |
| `require_progress`, `min_progress_pct` / `max_progress_pct` | true, "5" / "90" |
| `max_participation_pct` | "1" |
| `require_creator_not_net_seller` | false |
| `exclude_mayhem` | true |
| `pedigree_exclusions` / `pedigree_repeat_dumper` | true / false |
| `size_sol` / `max_sol_per_bet` / `max_exposure_per_mint_sol` | "0.07" |
| `wallet_max_sol` / `daily_loss_cap_sol` / `max_open_positions` | "100.0" / "10.0" / 25 |
| `fee_pct` / `priority_fee_sol` | "1.75" / "0" |

| braço | linha exigida | saída | papel na H-022 |
|---|---|---|---|
| **`grafico_ctrl_v1/1`** (C) | nenhuma | **atual** `alvo_1_15x_trailing_10_tempo_5m` v1: `target_x "1.15"`, `trailing_pct "10"`, `trailing_arm_x null`, `max_hold_s 300`, `max_loss_pct "50"`, `exit_on_line_break true`, `line_break_snapshots 2`, `exit_on_migration true` | **população da primária** — a 1.ª decisão por mint é o 1.º minuto elegível; `linha_ok` é lido nesse minuto |
| **`grafico_v1/1`** (L) | `require_higher_lows true`, `require_breakout_15m true`, `min_distance_to_support_pct "0"`, `max_distance_to_support_pct "0.25"` (banda congelada do EXP-M2, T4.10) | a mesma atual | política "esperar a estrutura" — **descritivo** contra C; base do par com H |
| **`grafico_v1/2`** (H) | a mesma de L | **pacote EXP-M2** `alvo_2x_trailing_30_tempo_15m_linha` v1: `target_x "2"`, `trailing_pct "30"`, `max_hold_s 900`, `max_loss_pct "50"`, `exit_on_line_break true`, `line_break_snapshots 2`, `exit_on_migration true` | **secundária** — pacote de saída mais longo, pareado com L na mesma decisão |

- **Por que a primária fica dentro de C.** L contém C; o 1.º minuto elegível de C numa moeda chega antes ou
  junto do de L/H, e a feature é lida antes de qualquer aposta do EXP-M26 na moeda (sem a contaminação de
  I2). Comparar L contra C mediria o custo de esperar a estrutura, não a estrutura em si — por isso L − C é
  **descritivo**, nunca a primária.
- **H − L é um pacote, não "horizonte".** Alvo, trailing e prazo mudam juntos; herdado do pré-registro do
  EXP-M2 (12/09), pareado por (mint, `features_end_time`, foto de fill), medido **sob observação conjunta**
  L+C+H — as apostas abertas dos três braços somam fotos de 15 s (I2) e a linha usa todas as fotos
  utilizáveis.
- Banda 0–0,25 e pacote H **não foram escolhidos olhando dado** — vêm do pré-registro do EXP-M2. Só 5/90 %
  de progresso e 900/7 200 s são deste desenho, e vêm do brief e da mecânica da curva.

## Protocolo (congelado — nunca editar)

- **População.** Oportunidades prospectivas com `evaluated_at` entre T0 e o corte; unidade = 1.ª oportunidade
  por mint desde o seed (C, `meme_mature_opportunities`/R1; um mint cuja 1.ª caiu no piloto técnico nunca
  entra) e 1.ª decisão comum por mint desde o seed (par H/L). Desfecho = `pnl_sol / size_sol` da aposta de
  papel, **condicional ao fill**; venda sem praça executável (foto com `complete = true` ou em/depois de
  `completed_at`/`migrated_at`, qualquer que seja o gatilho) é censura nomeada.
- **Primária (D_linha).** Diferença de médias de PnL/SOL `true` − `false` dentro de C, estimador
  **estratificado** (dia × bloco de 6 h, pesos `n_true·n_false/n`, só estratos com os dois grupos) —
  associação preditiva no mesmo instante, não efeito causal da espera. `true`/`false`/`desconhecida` são as
  três classes congeladas do desenho §2.2 do protocolo (`true` = coberta + `higher_lows` ∧ `breakout_15m` ∧
  banda 0–0,25; `false` = coberta com algum critério falho, ou `flat`/`out_of_range` cobertos; `desconhecida`
  = falha de coleta, nunca `false`).
- **Secundária (D_pacote).** Média das diferenças H − L por par completo, mesma família de Holm (2 p),
  pareado por (mint, `features_end_time`, foto de fill), sob observação conjunta L+C+H.
- **Calendário.** Seed → **T0** = seed + 48 h de piloto técnico (fora da inferência) → **corte** = 1.º 00:00Z
  depois de 7 dias completos desde T0 em que C já tem ≥ 150 `true` **e** ≥ 450 `false` inscritas, no máximo
  o 00:00Z do dia 21 desde T0 → **leitura** = corte + 2 h (900 s de posse, fill, foto de venda e folga).
  Inscrição: só entram oportunidades com `evaluated_at` em [T0, corte); nada novo entra depois do corte.
- **Censura / estresse.** Estresse de censura aplicado aos preenchidos sem desfecho precificável:
  censurados de `true` em **perda integral** (−`sol_spent`/`size_sol`), censurados de `false` na média
  observada por estrato; a conclusão exige que o IC inferior de D continue > 0 sob esse estresse. Descritivo,
  sempre publicado: −0,50/SOL, ponto de inversão, grade 2D. Secundária: três casos de par incompleto
  (§4 do protocolo).
- **Cláusulas de instrumento.** NÃO CONFIRMA por instrumento se `desconhecida` > 20 % das oportunidades
  inscritas, ou `sem_proposta` por instrumento > 5 %, ou a união {`sem_proposta`, sem fill, preenchido sem
  desfecho} > 20 % das elegíveis dentro de `true` ou `false`, ou se a coleta parou pela guarda de custo do
  instrumento (§6.8 do protocolo: apostas abertas do EXP-M26 > 10 em qualquer janela de 15 min, ou as demais
  guardas de cobertura/latência da cadeia). Parada pela guarda encerra a coleta e dá NÃO CONFIRMA por
  instrumento **qualquer que seja o n**.
- **Rótulo.** `CONFIRMA` só se `min(L_mint, L_blocos) > 0` nos dois bootstraps (por mint e por blocos de
  6 h) e toda a previsão da H-022 bate; `REFUTA` se `max(U_mint, U_blocos) < +0,03` (o MRE); senão NÃO
  CONFIRMA. Família de Holm sobre {p_primária, p_secundária}, fixa antes de ver dado.

## Estado da construção (26/09/2026)

Nada estava construído quando o desenho foi congelado (§7 do protocolo: "ninguém construiu nada ainda").
No repositório, hoje:

| # | o quê | dono | revisão | estado |
|---|---|---|---|---|
| I1 | retenção madura limitada (`MEME_TRACK_MATURE_TOP_K`, orçamento à parte, `mcap_observed_at`) | backend-specialist | quant-engineer, code-reviewer | **feito** (`f5e75ef9`, 27/09) |
| I2 | acompanhar a posição do EXP-M26 até ao fecho (fixar `approved` sem aposta; série de 15 s por pertença) | backend-specialist | quant-engineer | **feito** (`f5e75ef9`, 27/09) |
| L1 | causalidade da saída `line_broken` (`line_support_causal`, `line_support_max_age_s`, `support_stale`) | backend-specialist | quant-engineer, risk-engine-guardian | **feito** (`191647ec`, 27/09 — padrão global, não só EXP-M26) |
| R1 | registro durável `meme_mature_opportunities` (1.ª avaliação, insumos do tique, recusas, `proposal_id`) | backend-specialist | database-architect, quant-engineer | **feito** (`ee5ffaa6`, 27/09 — migração `0066`) |
| C1 | `MEME_TRACK_MATURE_TOP_K=60` no compose de produção | devops-engineer | — | **feito** (`f5e75ef9`, 27/09) |
| F | funil de viabilidade de 24 h (sem desfecho), depois de I1/I2/L1/R1/C1 | quant-engineer | Astra | **pendente** |
| J | spec do moinho, congelado com impressão digital antes do seed | quant-engineer | Astra | **pendente** |
| S | migração de semente dos três conjuntos `research_only` (`grafico_ctrl_v1/1`, `grafico_v1/1`, `grafico_v1/2`) | backend-specialist | database-architect | **pronto, retido** (migração `0067` escrita e testada; só entra depois de F e J, pela decisão conjunta) |
| P | piloto técnico de 48 h (só contagens e motivos, fora da inferência) | quant-engineer | — | **pendente** |

Ordem congelada: I1 + I2 + L1 + R1 (com testes de integração) → C1 → 24 h → F → J congelado → S → P (48 h) →
T0 → corte → leitura. Nenhuma etapa pula a anterior.

## Riscos

Lista completa em `docs/design/exp-m26-grafico-moedas-maduras.md` §6; resumo:

1. **Sobrevivência** — a moeda viva aos 15 min já é selecionada (3,9 % das que tinham série no minuto 15) e a
   retenção por maior `mcap_sol` seleciona outra vez. A primária é **dentro de C**, mesma população nos dois
   grupos: a sobrevivência não a envenena, mas o nível de C não generaliza para a moeda de 1–4 min.
2. **Antecipação** — na entrada (linha lida só com `received_at ≤ end_time`), no fill/venda e na saída
   `line_broken` (por isso L1 exige `computed_at` e suporte fresco ≤ 120 s) e na retenção (I1 só lê o que já
   chegou até o `prune`).
3. **Os braços mexem no instrumento** — apostas abertas do EXP-M26 somam fotos de 15 s; por isso a primária
   lê a linha no 1.º minuto de C, antes de qualquer aposta do EXP-M26 na moeda.
4. **Confusão com progresso** — a previsão exige o sinal em ≥ 2 dos tercis avaliáveis de
   `curve_progress_pct`; se só vive entre tercis, é progresso (uma das 13 variáveis esgotadas).
5. **Redundância com "está subindo"** — cláusula de identidade contra `mcap_slope_15m`.
6. **Latência da via de 1 min** — fold p99 5,3 s + tique do Lab; fill ≤ 60 s pela cadeia, ≤ 15 s se já na
   série de 15 s.
7. **Papel × real** — sem MEV, sem transação falhada, sem prioridade; custo real só entra pela sensibilidade
   contábil.
8. **Custo do instrumento sobre as outras pistas** — guardas de cobertura/latência/apostas abertas nas 72 h
   antes de I1; se alguma falhar, os três conjuntos são aposentados (`K = 0` + `--deprecate`) e o resultado é
   NÃO CONFIRMA por instrumento.
9. **Muitos braços** — três, com família de Holm de 2 contrastes; nada de variantes antes da leitura.

## Relacionado

[[Fila de Hipoteses]] (H-022) · [[EXP-M2-a-linha-manda]] (por que morreu com 0 propostas) ·
[[KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta]] · [[KB-0149-o-que-a-mesa-real-ensinou]] ·
[[Perdas/comprou_no_topo]] · [[Mapa de Estrategias]] · [[Dicionario de Variaveis]] ·
[[Experiments Index]] · `docs/design/exp-m26-grafico-moedas-maduras.md` (desenho completo, com as
consultas cegas em `.claude/state/m26/`) · `.claude/state/dialogue-EXP-M26.md` (5 rodadas com a Astra)

## Fontes

`docs/design/exp-m26-grafico-moedas-maduras.md` · `.claude/state/m26/{q1..q11}.sql` e `outputs.txt` ·
`hunter_indicators/meme/lines.py`, `rules.py`, `exits.py` · `services/meme-worker/hunter_meme_worker/
{tracker,tracker_mature,tracker_types,tracker_pins,lines_exit,lab_repo_lines,lab_params,lab_models,lab_bets}.py`

## Avaliações (acrescentadas, nunca reescritas)
