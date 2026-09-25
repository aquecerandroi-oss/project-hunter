---
tags: [experimento, meme, pumpfun, paper, pre-registro, saida, drawdown, m5]
updated: 2026-09-16
status: pre-registrado
owner: astra-quant
exp: EXP-M11
strategy: "meme/pumpfun — mesma porta da mesa, saída S4: alvo 3×, piso −50 %, tempo 30 min e recuo de 20 % do pico na série de 15 s armado só depois de 1,5×, no lugar do trailing 35 %"
version: "gate fluxo_e_holders v1 (o vivo, sem alteração) + exit dd20_after_15x v1 (alvo_3x_dd20_apos_1_5x_tempo_30m), comparação pareada com o conjunto de saída vivo"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# EXP-M11 — recuo de 20 % do pico, armado só depois de 1,5×, no lugar do trailing

> **Pré-registro escrito em 2026-09-16 (noite BRT), ANTES de existir qualquer proposta ou aposta do conjunto de
> saída `dd20_after_15x`.** Protocolo congelado; avaliações acrescentadas pelo fechamento diário, nunca
> reescritas. A previsão padrão é `descartar` — e aqui ela é **a leitura direta do número de hoje**, cujo IC
> pareado cruza o zero. Disciplina: [[11-KNOWLEDGE/KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout|KB-0092]],
> [[06-DECISIONS/2026-09-10-validacao-em-um-dia-e-lucro-real|decisão de 10/09]].

## Diretiva de origem

A [[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta|KB-0108]] mediu o **dd20** (mcap da série de 15 s
≤ 80 % do pico corrente, pico sempre calculado **até a foto anterior**) como o melhor **detector** de morte:
precisão 84 %, recall 35 %, lead 70 s. A [[11-KNOWLEDGE/KB-0110-saida-por-drawdown-20-na-serie-de-15s|KB-0110]]
perguntou se detector bom vira **saída** boa e simulou quatro variantes sobre as **291** entradas da porta atual
(12–16/09). Só **S4** ganha em R total **e** em mediana sem tocar a cauda. Esta página congela S4 como braço.

## Hipótese (congelada)

**H1:** trocar o trailing de 35 % pelo **recuo de 20 % do pico na série de 15 s, armado só depois de 1,5×**,
melhora o R das mesmas entradas, porque o dd20 tem lead de 70 s sobre a morte e, **armado tarde**, corta no verde
(+0,359 R médio nas 33 saídas por gatilho) em vez de cortar no ruído (−0,453 R em S1, onde ele é armado desde a
entrada — 20 % do preço de entrada é menos que a largura de uma vela de 15 s). **H0 (previsão):** o Δ pareado
medido é **+0,0115 R com IC 95 % [−0,003; +0,027]** — cruza o zero, toca só **21 de 291** apostas e foi medido
numa janela de **2,5 min** (§ limitação) → `descartar`.

## Definição congelada (`dd20_after_15x v1`)

**Entradas: as mesmas da mesa, sem uma vírgula de diferença** — porta calibrada (`operator/5` + `snipers ≥ 21`),
foto de 15 s com `age_s` 30–300 s, curva viva, não-Mayhem, `curve_progress_pct` 0,05–0,50, fita presente,
`net_sol_flow_60s > 0`, `dev_share ≤ 0,10`, pedigree E2; entrada na primeira barra de 1 min (até 5 min) com
`holders ≥ 20`, `unique_buyers ≥ 10`, `sells_1m/buys_1m ≤ 0,6`. **Só a saída muda.**

| regra | conjunto vivo (**S0**, controle) | **este braço (S4)** |
|---|---|---|
| alvo | 3× | 3× (igual) |
| piso | −50 % | −50 % (igual) |
| tempo | 30 min | 30 min (igual) |
| `creator_dump` | sim | sim (igual) |
| trailing | **35 % armado depois de 1,5×** | **removido** |
| recuo do pico (15 s) | — | **20 % do pico corrente, armado só depois de 1,5× do preço de entrada**; pico até a foto **anterior** (causal); preenchimento no mcap observado da foto |

Comparação **pareada aposta a aposta** (mesma moeda, mesma entrada, mesmo minuto), bootstrap de **blocos de dia**;
tamanho 0,05 SOL; taxa 1,75 % por perna; `R = (múltiplo líquido − 1) / 0,5`.
**S1, S2 e S3 ficam fora**: S1/S2 transformam HOM de +3,79 R em −0,02 R (−3,81 R de cauda, mais que o R total
inteiro de S0) e S3 é neutro (+0,0002 R) — fica como **telemetria**, sem autorização de venda.

## A limitação que a página carrega na testa (KB-0113)

[[11-KNOWLEDGE/KB-0113-ate-onde-as-series-acompanham-uma-aposta|KB-0113]]: a série de 15 s dura **150 s medianos**
depois da entrada (p90 241 s) porque `fast_lane.young_mints` larga a moeda aos **300 s de vida** e **ignora o pin**
— **91 %** das paradas são esse teto, não morte nem migração. Logo "tempo 30 min" é, hoje, "até a série acabar":
**226 de 291** apostas de S0 fecham assim. Consequências aceitas por escrito: (i) o **nível** de R desta simulação
não é o R da mesa (é o de uma janela de ~2,7 min com saída a mercado no fim); (ii) o teste é **favorável ao dd20
por construção** — ele é o único gatilho com tempo de disparar nessa janela — **e mesmo assim ele não ganha**.
**Dependência declarada: a T4.33** (a correção da via rápida para respeitar o conjunto fixado, ~+2 % de linhas/dia,
e um rótulo para "fechado por tempo sem observação posterior"). **Sem a T4.33 no ar, este braço roda mas não é
julgável** — nenhuma leitura de veredito antes dela.

## Portão de desenho (C1–C8) — congelado

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | **PASS** | Detector com lead medido de 70 s e precisão 84 % (KB-0108); armar depois de 1,5× é exatamente o que impede morder a moeda que ainda sobe |
| C2 | Sobreajuste | **REVISE** | Quatro variantes foram comparadas na mesma amostra e escolheu-se a melhor; "20 %" e "1,5×" não foram varridos, mas a escolha do braço é in-sample |
| C3 | Amostra | **REVISE** | 291 apostas pareadas, mas o gatilho toca **33 (11,3 %)** e difere do controle em **21** — o n efetivo do contraste é ~21, não 291 |
| C4 | Regime | **REVISE** | 5 dias (2 parciais); S4 ≥ S0 em **4 de 5** dias, perdendo só em 12/09 (n = 11) |
| C5 | Saídas | **PASS** | É uma página **de saída**: entradas congeladas e idênticas ao controle; nenhuma saída depende de fotografia ausente |
| C6 | Concentração | **PASS** | 0,05 SOL, mesmos tetos do vivo; a troca não muda tamanho nem número de abertas |
| C7 | Execução | **REVISE** | Saída preenchida no mcap observado da foto de 15 s, sem atraso de decisão nem impacto além da taxa ([[11-KNOWLEDGE/KB-0088-o-teto-de-participacao-nos-motores-de-backtest|KB-0088]]) |
| C8 | Invalidação | **PASS** | Gatilhos abaixo + régua (≥ 100 apostas medidas e 30 dias, IC 95 % por blocos de dia, leave-top-out) + a pré-condição T4.33 |

## Previsões (congeladas, numéricas)

- **P1** Em **≥ 85 %** dos pares o desfecho será **idêntico** ao do controle (in-sample 270/291 = 92,8 %); o gatilho
  dd20 dispara em **8–15 %** das apostas (in-sample 11,3 %).
- **P2** Δ R médio pareado ∈ **[−0,03; +0,08]**, ponto **+0,012**, com IC 95 % de blocos de dia **contendo o zero**
  → `descartar` (H0). Só Δ ≥ +0,10 com IC inteiramente acima de +0,02 muda a previsão.
- **P3** R médio **das saídas pelo gatilho** > 0 (in-sample **+0,359**). Se ficar ≤ 0, o mecanismo ("armado tarde
  corta no verde") está falsificado e o braço morre mesmo com Δ positivo.
- **P4** Soma do **top-10** de R do braço igual à do controle dentro de **± 0,05 R** (in-sample +33,62 nos dois):
  **zero perda de cauda**. Qualquer perda de cauda ≥ 1 R repete o erro do `line_broken` em KITE e reprova.
- **P5** Enquanto a T4.33 não estiver no ar, **≥ 60 %** das apostas fecharão por tempo/fim de série (in-sample
  226/291 = 77,7 %) — e nenhuma leitura de veredito é feita nesse regime.

## Gatilhos de descarte (qualquer um basta)

1. Δ pareado ≤ 0 depois de **100 apostas medidas** com o gatilho tendo disparado em ≥ 30 delas.
2. R médio das saídas por dd20 ≤ 0 (mecanismo falso).
3. Perda de cauda ≥ 1 R contra o controle no top-10.
4. Veredito lido **antes** da T4.33: a coorte é invalidada por construção (censura de 300 s).

## O que NÃO fazer

Armar o dd20 desde a entrada ou depois de +30 % (S1/S2 já reprovados: −0,006 e −0,010 R pareados e −3,81 R de
cauda cada); vender por S3 (telemetria, não ordem); "ajustar" 20 % ou 1,5× olhando os primeiros dias; mexer na
porta dentro desta página (a porta é a EXP-M10); tratar o nível de R desta simulação como R de 30 min; ligar
dinheiro real — a KB-0110 §6.4 manda passar pelo protocolo de validação em um dia **depois** de a série cobrir o
horizonte, e a retenção de 7 dias da série de 15 s faz a partição de setembro cair por volta de **08/10**.

## Avaliação
_(append-only; o fechamento diário acrescenta uma seção datada por dia com aposta fechada)_

## Fontes

[[11-KNOWLEDGE/KB-0110-saida-por-drawdown-20-na-serie-de-15s|KB-0110]] §1–§6 (S0–S4, Δ pareados, cauda, R por dia) ·
[[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta|KB-0108]] (dd20 como detector: 84 % / 35 % / 70 s) ·
[[11-KNOWLEDGE/KB-0113-ate-onde-as-series-acompanham-uma-aposta|KB-0113]] §1–§4 (censura de 300 s, T4.33) ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] §3 ·
[[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] ·
`infra/scripts/sql/research/2026-09-16-r20-q01-entradas-porta-atual.sql` ·
`...-r20-q02-serie-15s-pos-entrada.sql` · `infra/scripts/research/2026-09-16-r20-sim-saidas-15s.py` ·
`infra/scripts/sql/research/2026-09-16-r25-q0{1,2,3}-*.sql` ·
`services/meme-worker/hunter_meme_worker/fast_lane.py` · `docs/RISK_ENGINE_MEME.md`.
