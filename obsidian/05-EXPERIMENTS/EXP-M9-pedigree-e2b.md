---
tags: [experimento, meme, pumpfun, paper, pre-registro, pedigree, e2b, clones, graduacao, m5]
updated: 2026-09-16
status: pre-registrado
owner: sexta-feira
exp: EXP-M9
strategy: "meme/pumpfun — E2-b (pedigree v2): recusar a moeda que nasceu cheia (curva ≤ 60 s do mint) ou cujo maior comprador pagou ≥ 35 % do SOL comprado desde o mint, com guarda de ≥ 10 compradores na fita; braço de papel ao lado da porta calibrada da mesa"
version: "criterio pedigree_e2b v1 (e2b_top_buyer_share_max 0,35, e2b_min_buyers 10, e2b_born_full_s 60) sobre o gate fluxo_e_holders v3 (flow_v2/6, migração 0044_meme_gate_e2b_arm, relógio de 15 s)"
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

# EXP-M9 — E2-b: a moeda que nasce cheia e a carteira que paga a subida sozinha

> **Pré-registro escrito na T4.31 em 16/09/2026 (2x:xx BRT), ANTES de existir uma proposta do conjunto
> `flow_v2/6`.** Protocolo congelado; avaliações acrescentadas pelo fechamento diário, nunca reescritas.
> É a **E2-b** de [[11-KNOWLEDGE/KB-0103-clones-fundo-com-preco-forjado-assinatura-e-custo|KB-0103]] e
> [[11-KNOWLEDGE/KB-0105-e2b-replicacao-12-13-09-e-efeito-em-R|KB-0105]], irmã da E2 v1 de
> [[05-EXPERIMENTS/EXP-M6-exclusoes-de-pedigree|EXP-M6]]. A previsão padrão é `descartar`.

## Diretiva de origem

O plantão de 16/09 achou um viveiro de clones "fundo/instituição" (`WOFI`, `WOTF`, `NTDA`, `ECTF`,
`KIBA`, mais `NVDA`/`OPENAI`/`SPACEX`) com preço forjado. KB-0103 mediu a assinatura em 3 dias (2 877
graduadas, rótulo de fita em 390) e encontrou **dois** eixos que separam — e não são os que a E2 v1 usa:
**velocidade** (a curva enche no mesmo minuto do mint) e **concentração** (uma carteira paga um quinto a
um terço do SOL da subida). Mediu também o custo da E2 de hoje: **recusa 51,3 % das graduações orgânicas
para pegar 34,9 % das forjadas**. KB-0105 replicou fora da amostra (12 e 13/09): a direção replica com
folga (recall 92–100 % a um custo de 3,9–11,4 %), o **nível não** (o custo de 2,0 % vira 11,4 % em 12/09).
Nas 103 apostas de papel **medidas** desses dois dias a E2-b marcaria 41, somando **−14,2 R de −18,9 R** —
mas os dois dias são perdedores e as três maiores ganhadoras escapam **por falta de fita**, não por mérito.
Isso é motivo para **pré-registrar um braço**, nunca para creditar vantagem (KB-0092: não se ajusta nos
primeiros dias) e nunca para ligar na mesa.

## Hipótese (congelada)

**H1:** entre as moedas que a porta calibrada da mesa já aprovaria, as que a E2-b marca (nasceram cheias
**ou** têm uma carteira com ≥ 35 % do SOL comprado desde o mint, com ≥ 10 compradores na fita) têm R médio
**pior** que as que ela deixa passar, e a diferença é grande o bastante para pagar o que a regra custa em
frequência. **H0 (previsão):** o efeito medido em 12–13/09 é o de dois dias perdedores e não se sustenta
prospectivamente; a diferença de R entre marcadas e não marcadas fica dentro do IC 95 % por blocos de dia,
e a regra sai **cara em cobertura** (recusa por `e2b_top_buyer_unknown` mais do que por vício) →
`descartar`.

## Definição congelada (`pedigree_e2b/1` sobre `flow_v2/6`)

| critério | limiar | recusa |
|---|---|---|
| nasceu cheia | `meme_tokens.completed_at − created_at ≤ 60 s`, **só quando `completed_at ≤` o instante julgado** | `e2b_born_full` |
| concentração | maior comprador ≥ **0,35** do SOL comprado desde `created_at − 60 s` até o instante julgado (fita `meme_trades`, soma por `trader`, lado `buy`) | `e2b_top_buyer_share` |
| guarda | a perna da concentração só fala com ≥ **10** compradores distintos na fita; abaixo disso não pergunta | — (registrado em `reasons`) |
| dado ausente | sem fita até o instante julgado (ou leitura falhou/estourou 8 s) | `e2b_top_buyer_unknown` |
| **base (a porta da mesa, 16/09)** | idade 30–300 s, progresso 5–50 %, holders ≥ 20 **sem exigir subida**, compradores ≥ 10, vendas/compras ≤ 0,6, fluxo líquido > 0, snipers ≥ 21 (sem teto útil: 1 000), dev ≤ 10 %, criador não vendedor líquido, E2 v1 + reincidência, Mayhem excluído | as recusas já nomeadas de EXP-M5/M6 |

Saídas e tamanho: os de `flow_v2/5` (alvo 3×, trailing 35 % após 1,5×, 30 min, piso 50 %, quebra de linha),
0,05 SOL, 5 abertas, taxa 1,75 %. Relógio de **15 s**. `research_only`: nasce aprovada por `rules`, em
papel, e **nunca** toca o dinheiro da mesa. `flow_v2/5` continua ativo — ele é o controle mais próximo sem
a E2-b, e `operator/5` (a mesa) segue **sem** o critério, de propósito.

**Confundimento declarado (não mascarar):** `flow_v2/6` é `flow_v2/5` **mais a calibração da mesa de 16/09**
(sem os dois "subindo", `min_snipers 21`, progresso ≤ 50 %, Mayhem fora) **mais** a E2-b. O contraste
`flow_v2/6 × flow_v2/5` mistura as duas coisas; o contraste limpo é **dentro de `flow_v2/6`**: as recusas
nomeadas `e2b_*` são contadas por tick ao lado das demais, então "quantas linhas a E2-b, e só ela, tirou"
é medível — e as apostas marcadas/não marcadas por carimbo retrospectivo (o mesmo SQL de KB-0105 §4) dão o
contraste em R sem precisar de dois conjuntos.

## Portão de desenho (C1–C8) — congelado

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | **PASS** | Uma carteira que paga a subida inteira não é demanda: é preço forjado; a moeda que enche em 60 s nunca teve compradores |
| C2 | Sobreajuste | **REVISE** | Dois limiares (0,35 e 60 s) escolhidos numa amostra rotulada e conferidos noutra; a sensibilidade está em KB-0105 §3 e **não** será remexida nos primeiros 30 dias |
| C3 | Amostra | **REVISE** | O rótulo das duas KBs existe só nas 21–25 % de graduadas com fita, e em 13/09 são 13 forjadas; a régua aqui é de apostas, não do rótulo |
| C4 | Regime | **REVISE** | A prevalência de forjadas oscilou 11–54 % entre dias; precisão anda com prevalência, e falta um dia **ganhador** na medição |
| C5 | Saídas | **PASS** | As de `flow_v2/5`, inalteradas — E2-b é porta de entrada, nunca saída |
| C6 | Concentração | **PASS** | 0,05 SOL, 5 abertas, ≤ 1 % do volume, em papel |
| C7 | Execução | **REVISE** | A perna do tempo quase nunca dispara ao vivo (a mesa entra ~130–170 s antes de encher); quem decide ao vivo é a concentração, e a fita chega com atraso próprio |
| C8 | Invalidação | **PASS** | A régua: ≥ 100 apostas e 30 dias, IC 95 % por blocos de dia, leave-top-out; menos que isso, `descartar` |

## Previsões (congeladas)

- **P1** `e2b_top_buyer_unknown` será a **recusa E2-b mais frequente** nos 7 primeiros dias, e ficará entre
  **10 % e 60 %** das linhas avaliadas por `flow_v2/6` (ponto **25 %**) — a fita cobria 21–25 % das
  graduadas em 12–16/09, e o conjunto julgado aqui é o rastreado, mais bem coberto. Medida: contagem de
  recusas por nome em `meme_lab_ticks` ÷ linhas avaliadas do conjunto.
- **P2** `e2b_born_full` será **rara ao vivo** (≤ 2 % das linhas avaliadas): quem já encheu é recusada antes
  por `curve_complete`; essa perna vale sobretudo como rótulo.
- **P3** entre as linhas com fita **e** ≥ 10 compradores, `e2b_top_buyer_share` marcará entre **15 % e 45 %**
  (ponto 30 %) — a fatia mediana aos ~2 min foi 0,428 em 12/09, mas com a guarda o corte cai.
- **P4** o R médio das apostas **marcadas** menos o das **não marcadas** ficará entre **−0,60 e +0,10 R**
  (ponto −0,20 R) com IC 95 % por blocos de dia **cruzando zero** → `descartar` (H0). Só uma diferença
  ≤ −0,30 R com IC inteiro abaixo de zero, ≥ 100 apostas medidas e ≥ 30 dias muda a previsão.
- **P5** `flow_v2/6` proporá **menos** que `flow_v2/5` no mesmo período, e a queda virá **mais** de
  `e2b_top_buyer_unknown` do que das duas recusas de vício somadas (é o preço da cobertura, não da regra).

## Régua (congelada)

≥ **100 apostas medidas** e ≥ **30 dias** de sombra; IC 95 % por blocos de **dia**; leave-top-out; controle =
as apostas do mesmo conjunto não marcadas, e `flow_v2/5` como referência de frequência. Abaixo da régua o
veredito é `descartar` — nunca "promissor". Nenhum limiar se move dentro da janela (KB-0092).

## O que NÃO fazer

Ligar a E2-b na mesa (`operator/5`) antes da régua; ajustar 0,35/60 s olhando os primeiros dias; ler
`e2b_top_buyer_unknown` como "moeda limpa" ou como "moeda suja" — é ausência de dado, e é medida como tal;
citar os −14,2 R de KB-0105 como ganho (são dois dias perdedores, e as maiores ganhadoras escaparam por
falta de fita, não por mérito).

## Avaliação
_(append-only; o fechamento diário acrescenta uma seção datada por dia com aposta fechada)_

## Fontes

`packages/indicators/hunter_indicators/meme/pedigree_e2b.py` ·
`packages/indicators/tests/unit/test_meme_pedigree_e2b.py` ·
`services/meme-worker/hunter_meme_worker/{lab_repo_e2b,proposals,proposals_reasons,lab_models}.py` ·
`services/meme-worker/tests/test_proposals_e2b.py` ·
`infra/migrations/versions/0044_meme_gate_e2b_arm.py` + `infra/migrations/ddl/meme_gate_e2b_arm.py` ·
`infra/scripts/sql/research/2026-09-16-r13-q0{1..5}-*.sql` ·
[[11-KNOWLEDGE/KB-0103-clones-fundo-com-preco-forjado-assinatura-e-custo|KB-0103]] ·
[[11-KNOWLEDGE/KB-0105-e2b-replicacao-12-13-09-e-efeito-em-R|KB-0105]] ·
[[11-KNOWLEDGE/KB-0104-taxas-base-sem-as-nascidas-cheias|KB-0104]] ·
[[05-EXPERIMENTS/EXP-M6-exclusoes-de-pedigree]] · [[09-OPERATIONS/Diario/2026-09-16]].
