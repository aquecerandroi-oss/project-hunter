---
tags: [experimento, meme, pumpfun, paper, pre-registro, compradores, porta, m5]
updated: 2026-09-16
status: pre-registrado
owner: astra-quant
exp: EXP-M10
strategy: "meme/pumpfun — porta calibrada com o piso de compradores únicos em 25 aplicado na escolha da barra (reentrada), clone exato do conjunto vivo em todo o resto"
version: "gate fluxo_e_holders v2 (min_unique_buyers 25, reentrada) + exit alvo_3x_trailing_35_apos_1_5x_tempo_30m v1 (flow_v2/7; porta no relógio de 15 s, entrada na barra de 1 min)"
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

# EXP-M10 — o piso de 25 compradores únicos, aplicado na escolha da barra

> **Pré-registro escrito em 2026-09-16 (noite BRT), ANTES de existir qualquer proposta do conjunto `flow_v2/7`**
> e antes de o conjunto existir no banco. Protocolo congelado; avaliações acrescentadas pelo fechamento diário,
> nunca reescritas. A previsão padrão é `descartar`. Régua e disciplina:
> [[11-KNOWLEDGE/KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout|KB-0092]] e
> [[06-DECISIONS/2026-09-10-validacao-em-um-dia-e-lucro-real|a decisão de 10/09]].

## Diretiva de origem

O [[11-KNOWLEDGE/KB-0112-volume-do-minuto-participacao-e-r|KB-0112]] §4 achou que `unique_buyers` é a **única**
das três variáveis do minuto com sinal de cauda (Spearman com R ≥ +2 = **+0,153**, p = 0,004) e fechou pedindo o
piso 10 → 25. O [[11-KNOWLEDGE/KB-0114-compradores-unicos-o-piso-e-o-r|KB-0114]] mediu os sete pisos sobre 345
entradas em 5 dias (12–16/09, 3 cheios) e no §6 escreveu o rascunho deste braço. Esta página é esse rascunho
congelado como pré-registro — **nenhuma proposta do braço existe ainda**.

## Hipótese (congelada)

**H1:** exigir **≥ 25 compradores únicos no minuto**, aplicando o piso **na escolha da barra** (a moeda que não
qualifica no minuto 1 pode entrar no minuto 3 — reentrada, não recusa definitiva da moeda), aumenta o R médio do
conjunto vivo porque seleciona **variância a favor**: mais gente independente descobrindo a moeda ⇒ mais cauda,
e sob alvo 3× com piso −50 % a variância é assimétrica a favor. **H0 (previsão):** o ganho in-sample
(**+0,090 R**, IC [+0,038; +0,201], P(Δ > 0) = 1,00) é artefato da mesma amostra que o produziu — em especial da
faixa exclusiva 20–25 (n = 27, **uma** cauda, −0,096 R médio) — e prospectivamente o Δ não se separa do zero →
`descartar`.

## Definição congelada (`flow_v2/7`) — clone do conjunto vivo com **uma** mudança

| critério | limiar | recusa |
|---|---|---|
| idade (foto de 15 s) | 30–300 s | `age_below_min` / `age_above_max` |
| progresso da curva | 0,05–0,50 (fração 0–1) | `progress_below_min` / `progress_above_window` |
| fita | presente (`tape_reason IS NULL`) | `tape_blind` |
| fluxo | `net_sol_flow_60s > 0` | `flow_not_positive` |
| dev | ≤ 0,10, desconhecido recusa | `dev_share_above_max` / `dev_share_unknown` |
| snipers | **≥ 21** ([[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] §3) | `snipers_below_min` / `snipers_unknown` |
| pedigree | E2 (criador em série, clone) | `creator_serial` / `symbol_clone` |
| Mayhem | `exclude_mayhem: true` | `mayhem_curve` / `mayhem_unknown` |
| holders (barra de 1 min) | ≥ 20 — **fica no conjunto mesmo virando quase inerte** | `holders_below_min` |
| **compradores únicos (barra de 1 min)** | **≥ 25**, avaliado a cada barra até 5 min depois da porta (**reentrada**) | `buyers_below_min` |
| razão de vendas | `sells_1m / buys_1m ≤ 0,6` | `sells_ratio_above_max` |
| participação | ≤ 1 % do volume do minuto | `participation_above_cap` |

**Sem** exigência de "subindo" em holders ou progresso — isso é a [[05-EXPERIMENTS/EXP-M7-organica-lenta|EXP-M7]],
outro braço. Saídas idênticas às do conjunto vivo: alvo **3×**, trailing **35 %** armado depois de 1,5×, piso
**−50 %**, tempo **30 min**, `creator_dump`. Tamanho 0,05 SOL; taxa **1,75 % por perna**;
`R = (múltiplo líquido − 1) / 0,5`. Controle = o conjunto vivo (`min_unique_buyers = 10`) rodando **no mesmo
período**. Mexer em `min_holders`, `min_net_flow` ou no teto de participação **dentro deste braço** invalida a coorte.

## Portão de desenho (C1–C8) — congelado

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | **PASS** | Mecanismo declarado e falsificável: mais compradores distintos = mais variância; a cauda tem de subir junto com a média, senão o mecanismo é falso |
| C2 | Sobreajuste | **REVISE** | O 25 saiu de olhar sete pisos na mesma amostra que o mede (KB-0092); boa parte do ganho é tirar a faixa 20–25, com n = 27 e uma única cauda |
| C3 | Amostra | **PASS** | 273 entradas em 5 dias (**81,3/dia** de teto, antes de TTL/dedup/cooldown): 150 propostas fecham em poucos dias de radar |
| C4 | Regime | **REVISE** | 5 dias, 2 parciais; 12/09 e 16/09 têm 8 e 21 entradas — o LOO é fraco nas pontas, e o upgrade de 12/09 mudou o universo |
| C5 | Saídas | **PASS** | Saídas byte a byte iguais às do controle: esta página não fala de saída (isso é a [[05-EXPERIMENTS/EXP-M11-saida-drawdown-20-apos-1p5x|EXP-M11]]) |
| C6 | Concentração | **PASS** | 0,05 SOL, ≤ 1 % do volume do minuto, mesmo teto de abertas do vivo |
| C7 | Execução | **REVISE** | Entrada medida no mcap da barra, sem atraso de decisão ([[11-KNOWLEDGE/KB-0087-o-atraso-de-decisao-e-as-tres-correcoes|KB-0087]]); a reentrada **atrasa** a entrada de propósito e esse atraso extra não foi medido em produção |
| C8 | Invalidação | **PASS** | Quatro gatilhos de descarte escritos abaixo, mais a régua geral (≥ 100 apostas medidas e 30 dias, IC 95 % por blocos de dia, leave-top-out) |

## Previsões (congeladas, numéricas)

- **P1** Δ R médio contra o controle no mesmo período ∈ **[+0,04; +0,20]**, ponto **+0,09**.
- **P2** Cadência do braço entre **55 % e 85 %** da do controle (in-sample 273/345 = **79 %**).
- **P3** Taxa de cauda (`R ≥ +2`) do braço **acima** da do controle em **≥ 1,5 pp** (in-sample 18,7 % × 15,7 %)
  **e** taxa de ruína (`R ≤ −0,5`) igual ou maior (**46–49 %**). Média subindo **sem** a cauda subir = mecanismo falso.
- **P4** R **mediano** do braço **pior** que o do controle (in-sample **−0,42 × −0,31**): o piso é seletor de
  variância, não de acerto.
- **P5** Entre as barras que passam `buyers ≥ 25`, **≥ 96 %** já teriam `holders ≥ 20` (in-sample 96,5–99,3 %) —
  isto é, `holders_below_min` responde por **≤ 4 %** das recusas dentro do braço.

## Gatilhos de descarte (qualquer um basta)

1. Δ R médio ≤ 0 com IC 95 % de blocos de dia inteiramente ≤ +0,02 depois de **150 propostas**.
2. A taxa de cauda do braço **não** ficar acima da do controle (mecanismo falso, mesmo com a média agradando).
3. Cadência abaixo de **45 %** da do controle (a régua deixa de fechar em tempo útil).
4. O resultado depender de **um** dia: leave-one-day-out com qualquer remoção levando Δ abaixo de zero.

## Régua e prazo

Leitura **única** no fim, sem espiar para decidir: mínimo **150 propostas do braço E 10 dias corridos**, o que vier
por último, com LOO obrigatório. O **veredito de vida** (qualquer conversa sobre dinheiro real) só pela régua do
laboratório: **≥ 100 apostas medidas e 30 dias**, IC 95 % por blocos de dia, leave-top-out. Piso reprovado volta só
com **mecanismo novo**, nunca com dados novos.

## O que NÃO fazer

Subir o piso para 30, 40 ou 60 (KB-0114 §5: ≥ 60 dá 32,7 apostas/dia, vive de 13 apostas em dois dias e precisaria
de ~60 dias para se provar); tirar `min_holders` "porque virou inerte" **neste** braço (dois critérios de uma vez
impedem atribuir o efeito — é braço futuro); ajustar o 25 olhando os primeiros dias; contar apostas em moeda Mayhem;
ligar dinheiro real antes da régua.

## Braço semeado (T4.48)

**Quando:** 16/09/2026, noite (horário de Brasília, UTC−3) — o conjunto passou a existir no banco depois
que esta página foi congelada, como manda o pré-registro.

**Como:** migração `0049_meme_gate_buyers25_arm` (`down_revision = 0048_meme_creator_initial_buy`;
`infra/migrations/ddl/meme_gate_buyers25_arm.py`). Semeia **um** conjunto:

| campo | valor |
|---|---|
| `id` | `01994d00-6c1a-7000-8000-000000000014` |
| `name/version` | `flow_v2` / `7` |
| `kind` | `research_only` (**papel**) · `exp_ref` `EXP-M10` · `status` `active` |
| parâmetro que muda | `min_unique_buyers` **10 → 25** |
| base | `flow_v2/6` (`…0013`, migração `0044`) — todo o resto byte a byte igual (`size_sol` 0,05; alvo 3×; trailing 35 % após 1,5×; piso −50 %; 30 min; `max_participation_pct` 1 %; `min_holders` 20; `min_snipers` 21; `max_progress_pct` 50; `exclude_mayhem`; relógio 15 s) |

**Papel, por construção:** o executor só abre proposta de conjunto `kind = 'operator'`
(`hunter_meme_executor.auto_approve`: `WHERE rs.kind = 'operator' AND rs.status = 'active'`). Um conjunto
`research_only` **não alcança dinheiro real** — não é promessa de configuração, é o `WHERE` da consulta.

**Dois desvios em relação ao texto congelado acima, declarados (também em `docs/DATABASE.md` §57):**

1. A base é `flow_v2/6`, que carrega `pedigree_e2b: true` (EXP-M9) — a tabela de critérios desta página
   lista só a E2 v1. É o conjunto de **pesquisa** mais próximo da porta calibrada da mesa que existe no
   banco (`flow_v2/5` é anterior à calibragem de 16/09; `operator/5` é o da mesa, editado à mão).
   **Consequência para a leitura:** o controle desta EXP-M10 é `flow_v2/6`, não `operator/5` — os dois
   braços carregam E2-b, e o Δ só é atribuível ao piso de compradores se a comparação for essa.
2. `gate_version` continua **3** (a página diz "fluxo_e_holders v2", escrito antes da calibragem): o
   conjunto de critérios não mudou, só um limiar, e o campo é descritivo — quem identifica o braço é
   `flow_v2/7`.

**O que confirma / o que refuta, e até quando.** Leitura única ao fim de **≥ 150 propostas de `flow_v2/7`
E 10 dias corridos**, o que vier por último — ou seja, não antes de **26/09/2026** (BRT). Confirma (segue
vivo no laboratório) se, contra `flow_v2/6` no mesmo período: Δ R médio **> 0** com IC 95 % por blocos de
dia acima de +0,02, **e** taxa de cauda (R ≥ +2) acima da do controle em ≥ 1,5 pp, **e** cadência entre
55 % e 85 % da do controle, **e** o Δ sobrevivendo ao leave-one-day-out. Refuta (`descartar`) qualquer um
dos quatro gatilhos acima: Δ ≤ 0 com IC ≤ +0,02 depois de 150 propostas; cauda que não sobe (mecanismo
falso, mesmo com a média agradando); cadência < 45 % da do controle; resultado que depende de um único
dia. Sem espiar para decidir no meio; piso reprovado só volta com mecanismo novo.

## Avaliação
_(append-only; o fechamento diário acrescenta uma seção datada por dia com aposta fechada)_

## Fontes

[[11-KNOWLEDGE/KB-0114-compradores-unicos-o-piso-e-o-r|KB-0114]] §1–§6 (todos os números desta página) ·
[[11-KNOWLEDGE/KB-0112-volume-do-minuto-participacao-e-r|KB-0112]] §4–§5 ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] §3 (metodologia de R) ·
[[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] ·
[[11-KNOWLEDGE/KB-0106-snipers-e-graduacao-organica|KB-0106]] §7 ·
[[11-KNOWLEDGE/KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout|KB-0092]] ·
`infra/scripts/sql/research/2026-09-16-r28-q01-compradores-por-moeda-e-r.sql` ·
`...-r28-q02-*.sql` (reentrada) · `...-r28-q03-*.sql` (redundância com holders) ·
`packages/indicators/hunter_indicators/meme/rules.py` · `docs/RISK_ENGINE_MEME.md`.
