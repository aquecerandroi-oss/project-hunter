---
tags: [experimento, meme, pumpfun, curva, paper, pesquisa, linhas, moedas-maduras, h-022, m26]
updated: 2026-10-01
status: "desenho congelado (decisão conjunta com a Astra, 5 rodadas); I1/I2/L1/R1/C1 no ar desde 27/09; F não aprovado por instrumento em 01/10 (leitura de pedigree do minuto > 8 s); nenhum braço semeado, nenhuma proposta"
owner: quant-engineer
exp: EXP-M26
strategy: "meme/pumpfun — gráfico em moedas maduras (15–120 min, ainda na curva): grafico_ctrl_v1/1 (C, sem linha), grafico_v1/1 (L, linha + saída atual), grafico_v1/2 (H, linha + pacote de saída do EXP-M2) — os três research_only, carteira paper do Lab meme"
version: "porta comum grafico_maduro v1 (min_age_s/max_age_s 900/7200, progresso 5–90 %, participação ≤ 1 %, exclude_mayhem, size_sol 0,07); L/H com require_higher_lows+require_breakout_15m+banda 0–0,25; seed pela migração 00xx (T7 `S`, pendente)"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: "2026-10-01"
tipo: pesquisa
hipotese: H-022
variavel: "linha_ok na 1.ª oportunidade por mint do controle grafico_ctrl_v1/1 — três classes congeladas (true/false/desconhecida), lida dos insumos gravados em meme_mature_opportunities (R1) no tique da 1.ª avaliação"
populacao: "oportunidades prospectivas com evaluated_at entre T0 e o corte — moeda 900–7200 s, na curva, progresso 5–90 %, não Mayhem, participação ≤ 1 % (≥ 7 SOL/min a 0,07 SOL), pedigree; unidade = 1.ª oportunidade por mint desde o seed (C) e 1.ª decisão comum por mint desde o seed (par H/L)"
efeito: —
ic: —
veredito: em_curso
proximo_passo: "consertar a leitura de pedigree da via de 1 min (só as duas contagens quando nenhum conjunto 1m pede repeat_dumper) -> F de novo -> J congelado -> S -> P (48 h) -> T0 -> corte (>= 7 d, <= 21 d) -> leitura (corte + 2 h)"
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
| F | funil de viabilidade de 24 h (sem desfecho), depois de I1/I2/L1/R1/C1 | quant-engineer | Astra | **não aprovado — instrumento (01/10)**: mercado passa os pisos, a leitura de pedigree do minuto passa do corte de 8 s; consertar e repetir (avaliação de 2026-10-01) |
| J | spec do moinho, congelado com impressão digital antes do seed | quant-engineer | Astra | **pendente** |
| S | migração de semente dos três conjuntos `research_only` (`grafico_ctrl_v1/1`, `grafico_v1/1`, `grafico_v1/2`) | backend-specialist | database-architect | **pronto, retido** (escrita como `0067`, renumerada para `0068` e depois `0069_meme_mature_chart_arms`, ainda fora do commit; só entra depois de F e J, pela decisão conjunta) |
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

### Avaliação 2026-10-01 (F, 02:48–03:16Z) — o mercado passa os pisos, o instrumento não: F NÃO PASSA; J e S parados

> **Resultado:** a etapa F do funil **falhou por instrumento**. A população madura existe e enche os pisos com
> folga, menos o `true`, que passa com pouca folga. Mas a leitura de pedigree do minuto, que volta a rodar
> quando C/L/H ficarem ativos, levou **6,2–13,7 s** para os ~385 mints de cada minuto. O laço corta essa leitura
> aos **8 s**, e **26 dos 42 minutos** cronometrados passaram do corte. Cada leitura cortada vira
> `pedigree_unknown` em todas as linhas do minuto, isto é, `sem_proposta` **por instrumento**, que tem teto de
> 5 %. Pelo desenho (§4, "Se falhar: por instrumento… conserta-se e repete-se o F"), **nenhum limiar foi
> mexido**. O J não foi congelado e a semente `0069` ficou **intocada**. Nenhum desfecho foi lido: nenhuma
> aposta, PnL ou saída.

**O que foi lido antes:**
- esta página: Protocolo, Braços e "Estado da construção";
- o desenho, `docs/design/exp-m26-grafico-moedas-maduras.md`: §2.2 ("a primeira oportunidade, definição única
  para F, J e a leitura") e §4 ("Funil F", pisos e o "se falhar");
- [[Fila de Hipoteses]] H-022;
- [[KB-0149-o-que-a-mesa-real-ensinou]], §5: antecipação mente com convicção, e não se escolhe limiar olhando;
- [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]]: a C2 só vem depois do veredito da H-022;
- [[KB-0169-fibonacci-e-lta-diaria-no-dado]]: contexto do diário, não muda nada aqui;
- `docs/RESEARCH.md`;
- [[06-DECISIONS/Revisoes-Astra/Token-state-history|Token-state-history]] (a 0067 e a pergunta do J em aberto);
- a seção §69 do `docs/DATABASE.md`, que já avisava: "Custo que volta com um conjunto `1m` ativo… medir
  `meme_pedigree_read_failed` no piloto P". O F mediu antes.

**Como foi medido.** O banco da VPS foi lido só em modo leitura (`BEGIN READ ONLY`,
`default_transaction_read_only=on`). R1 está vazia, porque nada foi semeado. Por isso a porta pura de
`grafico_ctrl_v1/1` foi avaliada **fora do Lab, com o código de R1** (desenho §4):
- **Porta:** `evaluate_entry(entry_features_of(row, spec), spec.gate)`, com o `spec` montado dos parâmetros
  congelados da semente (`infra/migrations/ddl/meme_mature_chart_arms.py`).
- **1.ª passagem por mint:** ordenada por `end_time` **antes** de olhar a linha, desde 27/09 06:00Z (K = 60 no
  ar).
- **Janela F:** [28/09 06:30Z; 01/10 00:00Z), 65,5 h. Ela começa 2 h depois da `0067` (28/09 04:24:42Z): todo
  mint com idade ≤ 7 200 s dentro da janela nasceu com o histórico instalado.
- **`completed_at`/`migrated_at`:** os conhecidos no `computed_at` da linha, lidos do histórico da `0067`.
- **Cobertura:** `coverage_of` (o mesmo de R1), sobre as fotos de (T − 16 min, T] recebidas até T.
- **Classe:** `classe_linha` do J.
- **Pedigree:** as duas contagens de `PEDIGREE_V1`. E = `creator_serial`/`symbol_clone`; I = o resto.

Arquivos em `.claude/state/m26/f/`: `f1_superset.sql`, `f2_modelo.sql`, `f_funil.py`, `f_saida.txt`,
`f3_pedigree_render.py`, `f3_pedigree{,_b}.out`, `f3_explain.out`, `f3_duas_contagens.out` e
`f4_sensibilidade.out`.

**Números do mercado (provisórios; ver as ressalvas da Astra abaixo):**

| dia (UTC) | oportunidades | E | não-E | `true` | `false` | `desconhecida` (U) | I (offline) |
|---|---|---|---|---|---|---|---|
| 28/09 (desde 06:30Z, 17,5 h) | 372 | 141 | 231 | 10 | 210 | 11 | 0 |
| 29/09 | 391 | 152 | 239 | 13 | 216 | 10 | 0 |
| 30/09 | 377 | 163 | 214 | 10 | 194 | 10 | 0 |
| **janela (65,5 h)** | **1 140** | **456** | **684** | **33** | **620** | **31** | **0** |

- **Pisos do F contra a medição:**
  - C ≥ 50 oportunidades/dia: **417,7/dia** (não-E 250,6/dia). Passa.
  - `true` ≥ 8/dia: **12,1/dia** (dias inteiros: 13 e 10). Passa, com pouca folga.
  - `false` ≥ 24/dia: **227,2/dia**. Passa.
  - `desconhecida` + instrumento ≤ 15 % das não-E: **4,5 % offline** (31/684, todas `cobertura:gap`). Passa
    **só sem o corte de 8 s**; ver abaixo.
- **Classes:**
  - `false` traçada 489, `flat` 115, `out_of_range` 16;
  - `true` 33;
  - cobertura das não-E: `covered` 371, `covered_from_birth` 282, `gap` 31.
- **Idade na 1.ª oportunidade:** p10/p50/p90 = 915 / 994 / 2 333 s.
- **Estratos:** 11 de 11 blocos de 6 h têm os dois grupos. O `true` vai de 1 a 6 por bloco.
- **E = 40 % (456/1 140).** Por nome: `symbol_clone` 380 e `creator_serial` 164. Pela conta da Astra, isso dá 88
  com as duas, 292 só `clone` e 76 só `serial`. É uma exclusão por regra conhecida, que **não dilui** os tetos.
- **Instrumento:**
  - atraso do fold (`computed_at − end_time`) nas 1.ªs oportunidades: p50 3,1 s, p99 5,5 s, máximo 6,0 s; nenhuma
    acima de 60 s;
  - via do estado do token: `history` 202, `sem_mudanca` 938;
  - recusas da porta antes da 1.ª passagem: `curve_complete` 648 e `already_migrated` 623 (moedas graduadas que
    continuam com série);
  - I1: 46–76 maduras/min por bloco desde 27/09 06:00Z. As linhas de `meme_features_1m` por minuto foram de
    ~320–328 para ~375–394, +15–23 % (o desenho previa +18,5 %).
- **Ritmo.** Com 12,1 `true`/dia, as 150 `true` do corte levam **~12–13 dias**, dentro do teto de 21 dias. É
  abaixo da estimativa do desenho (15–30/dia), que avisava ter fator 3 de incerteza.

**O que reprova o F: a leitura de pedigree do minuto.**
- **O que a lê.** `lab_repo_e2b.lineage_for` só lê o pedigree no relógio de 1 min quando algum conjunto desse
  relógio julga (24/09, `954f0a50`). Com C/L/H ativos, a leitura volta para **todos** os mints do minuto, e não
  só para os que passam a porta. O laço a corta aos 8 s (`lab_repo_fast.pedigree_for`).
- **Cronometragem:** `lab_repo_fast._PEDIGREE` renderizado com os parâmetros de `pedigree_for` e os mints de um
  minuto fechado (375–416 mints), em duas rodadas seguidas:
  - 1.ª rodada (03:02–03:04Z): **2 de 12** acima de 8 s, entre 6,24 e 8,74 s;
  - 2.ª rodada (03:04–03:10Z): **24 de 30**, entre 7,16 e 13,71 s;
  - `EXPLAIN ANALYZE`: 7,89 s.
- **Onde está o custo.** Ele está em `creator_prior_dump_count` e no **diagnóstico** `creator_prior_dead_count`:
  63 559 moedas anteriores dos mesmos criadores, em 7 dias, percorridas para 386 mints (~1,1 M buffers). Nenhuma
  das duas contagens é usada por C/L/H, que têm `pedigree_repeat_dumper false`. **Só as duas contagens que eles
  usam levam 28–69 ms.**
- **Por que piorou desde 24/09.** Naquele dia a mesma leitura levou ~3 s com ~320 mints (DATABASE §66). Hoje são
  ~385 mints por minuto, em parte **pelo próprio I1**, e há mais moedas por criador serial.
- **Consequência.** Nos minutos cortados, toda 1.ª oportunidade de C vira I, e a seguinte não a substitui
  (desenho §2.2). O que se mediu foi a fração de **consultas lentas**, não a de oportunidades perdidas (ressalva
  da Astra). Mesmo assim, o trecho mais rápido (2/12 ≈ 17 %) já passa três vezes do teto de 5 %. Além disso, uma
  E que só se soube pela leitura offline não seria conhecida no tique cortado.

**Segunda opinião (Astra, [[06-DECISIONS/Revisoes-Astra/EXP-M26-F|EXP-M26-F]]):**
- **Ela concorda:** F não passa por instrumento, conserta-se e repete-se antes de J/S. P não serve para adiar um
  bloqueio que já se conhece.
- **Must-fix 2 (relógio).** O laço lê o estado do token no tique (≥ T + 60 s), e não no `computed_at`.
  - Medido (`f4_sensibilidade.out`): das 1 140 1.ªs oportunidades, **3 / 6 / 15** tiveram a conclusão ou a
    migração carimbada depois do `computed_at` e até T + 60 / 120 / 180 s. Mudaria ≤ 1,3 % delas. Não muda
    nenhum piso, mas o F repetido deve usar o relógio do tique.
- **Must-fix 3 (Mayhem, criador e símbolo como eram no tique).** Não medido.
  - As 10 028 linhas do superconjunto têm `mayhem_enabled = false`, mas isso não prova **quando** o `false` foi
    aprendido. Uma moeda antiga descoberta depois pode empurrar uma contagem de pedigree.
  - Isso afeta E e a 1.ª oportunidade. Fica como **desconhecido** declarado.
- **Conserto que ela recomenda, e eu também.** Na via de 1 min, quando nenhum conjunto desse relógio pede
  `pedigree_repeat_dumper`, ler só as duas contagens. O caminho completo da pista de 15 s (a mesa) não muda.
  - Os diagnósticos que não foram lidos ficam **ausentes**, nunca zero.
  - Filtrar primeiro pela porta pura mudaria a trilha de recusas das outras pistas.
- **O F repetido precisa de:**
  - o relógio do tique e a auditoria do que só se soube depois;
  - ≥ 24 h pela via corrigida, com o corte real e sob carga, contando a união U/I por oportunidade;
  - testes de equivalência das decisões e de preservação da pista de 15 s;
  - a duração do ciclo do Lab e as guardas das outras pistas (§6.8).

**Próximo passo.** Antes de repetir o F: uma tarefa do backend-specialist, com revisão do quant-engineer, do
code-reviewer e do database-architect, que conserte a leitura de pedigree da via de 1 min. A ordem congelada não
muda: **F (de novo) → J congelado → S → P → T0**.
- A pergunta aberta do J (o que fazer se a janela [L, L + 1 h] fechar sem export com prova) **não** foi levada
  à Astra nesta tarefa, porque a ordem manda parar no F.
- A semente `0069_meme_mature_chart_arms` (não commitada) **não foi tocada**.

**Rótulo desta etapa:** F **não aprovado — instrumento**. Não é veredito da H-022, que segue `aberta`.

### Conserto do instrumento do F (2026-10-01, à tarde) — a leitura de pedigree do minuto leva 40 ms, não 7–14 s

> **Resultado:** o defeito que reprovou o F por instrumento (a leitura de pedigree do minuto passando do corte de 8 s)
> foi consertado **no código**; o F **ainda não foi repetido**, o J **não** foi congelado e a semente `0069` **segue
> intocada**. Nenhum limiar foi mexido. Esta seção não reescreve a avaliação acima: a corrige no que ela deixou
> aberto. Detalhe do banco em `docs/DATABASE.md` §69 ("Correção de 2026-10-01").

**O que foi lido antes:** [[00-HOME]]; esta página (avaliação de 2026-10-01 e Protocolo); o desenho
(`docs/design/exp-m26-grafico-moedas-maduras.md` §2.2, em que o pedigree **desconhecido** conta como I
("`sem_proposta` por instrumento"), e §4 funil F, "se falhar: por instrumento… conserta-se e repete-se");
[[KB-0149-o-que-a-mesa-real-ensinou]] §5 (item 24: antecipação mente com convicção; item 25: não se escolhe limiar
olhando o resultado, então nenhum piso do F foi mexido para a leitura caber); `docs/DATABASE.md` §66 e §69; a entrada
de [[Open Bugs]] "A leitura de pedigree do minuto leva 6–14 s…"; [[06-DECISIONS/Revisoes-Astra/EXP-M26-F|EXP-M26-F]]
(o conserto recomendado) e [[Workers]] (onde o `meme-worker` está descrito).

**O que mudou (código):**
- `lab_repo_pedigree.py` (extraído de `lab_repo_fast.py`, que estava em 350 linhas) tem duas consultas. A completa,
  `_PEDIGREE`, é **byte a byte a de antes** (hash pinado em teste) e é o que a pista de 15 s (a mesa real) segue lendo.
  A leve, `_PEDIGREE_COUNTS`, lê só `creator_prior_mints_1h` e `symbol_dup_24h`.
- `lab_repo_e2b.lineage_for` usa a leve quando **todo** conjunto da pista é do relógio `1m` e **nenhum** tem
  `pedigree_repeat_dumper`. Qualquer conjunto de outro relógio, ou com a chave ligada, recebe a completa.
- `creator_prior_dump_count` e `creator_prior_dead_count` não lidos chegam **ausentes** (`None`), nunca `0`. Nada filtra
  pela porta pura, então a trilha de recusas das outras pistas não muda.

**O que foi medido na VPS (só leitura, mesmo minuto fechado de 387 mints):** completa 6,93–7,69 s em 5 rodadas
(`EXPLAIN ANALYZE` 9 154 ms); só as duas contagens 46,8–68,7 ms (`EXPLAIN ANALYZE` 39 ms); mesmas somas nas duas colunas
comuns (2 952 e 10 906, 0 desconhecidos). Armadilha de medição registrada: ao envolver a consulta em
`SELECT … FROM (consulta) q`, o Postgres **poda** da subconsulta as colunas que o externo não referencia, e a leitura
"completa" cronometrou ~40 ms. O externo precisa referenciar as quatro colunas (`f5_pedigree_after.py`).

**O que o F repetido herda como obrigação (não é feito aqui):** relógio do tique para `completed_at`/`migrated_at`;
≥ 24 h pela via corrigida com o corte de 8 s real; união U/I por oportunidade; e a leitura leve **deixa os dois
diagnósticos como `null` em `meme_mature_opportunities.pedigree` e no bloco `pedigree` das razões** dos conjuntos
`1m` (não é zero: "não lido"). Quem ler esses campos na pista de 1 min sem olhar a chave `null` os leria como
"criador sem despejo", e não é isso.

**Segunda opinião:** [[06-DECISIONS/Revisoes-Astra/EXP-M26-pedigree-fix|EXP-M26-pedigree-fix]].

**Rótulo desta etapa:** instrumento consertado e medido; **F a repetir**. Não é veredito da H-022, que segue `aberta`.

#### Acréscimo de 2026-10-01 (revisões do conserto): o que o F repetido não consegue provar sozinho

Origem: [[06-DECISIONS/Revisoes-Astra/EXP-M26-pedigree-fix-revisoes|as três revisões do conserto]] (quant-engineer, §3).

- **A leitura leve não é exercitada em produção antes da semente.** Nenhum conjunto `1m` está ativo até a `0069`, então
  `lineage_for` não chama `pedigree_for(full=False)` hoje; o F repetido, sozinho, só mede o que a consulta faz fora do laço
  (como esta tarefa fez), não o laço real sob carga.
- **Próxima tarefa (não feita aqui): um medidor de produção.** Chamar `pedigree_for(full=False)` a cada minuto fechado
  durante ≥ 24 h, sobre **todos** os mints das linhas do portão, dentro de `begin_nested` + `SET LOCAL
  statement_timeout = 8000`, gravando **todo** minuto, inclusive as falhas e os minutos sem leitura. Dono sugerido:
  backend-specialist, com revisão do database-architect e do quant-engineer. **Não está implementado.**
- **A guarda do §6.8 é ambígua e tem de ser corrigida por texto antes de semear.** "Apostas abertas do EXP-M26 ≤ 10 em
  qualquer janela de 15 min" (desenho, §6, item 8) pode significar **simultâneas** ou **em qualquer momento da janela**. Pela
  segunda leitura, ~5 % das janelas passariam de 10, numa contagem às cegas (feita sem olhar desfecho). A redação precisa
  dizer qual das duas vale, e o texto congelado do desenho só muda por esse caminho, antes da semente.
- **Condição de ativação do conserto:** ligar `pedigree_repeat_dumper` em qualquer conjunto `1m` devolve a pista à leitura
  completa (ver `docs/DATABASE.md` §69, "Condição de ativação"); não se liga sem índice medido ou prova de carga.
