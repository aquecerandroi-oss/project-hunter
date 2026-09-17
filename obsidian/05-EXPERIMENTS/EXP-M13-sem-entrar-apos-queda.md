---
tags: [experimento, meme, pumpfun, paper, pre-registro, drawdown, entrada, porta, m4]
updated: 2026-09-16
status: pre-registrado
owner: astra-quant
exp: EXP-M13
strategy: "meme/pumpfun — porta calibrada com recusa de entrada quando a curva perdeu ≥ 50 % do pico de real_sol_reserves com o pico nos últimos 60 s; clone do conjunto vivo em todo o resto"
version: "gate fluxo_e_holders v3 (recent_drawdown_block X=0,50 N=60 s) + exit alvo_3x_trailing_35_apos_1_5x_tempo_30m v1 (flow_v2/8; porta no relógio de 15 s, drawdown na foto de curva)"
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
---

# EXP-M13 — não entrar depois da queda

> **Pré-registro escrito em 2026-09-16 (noite BRT), ANTES de existir qualquer proposta do braço** e antes
> de o critério existir no código ou no banco. Protocolo congelado; avaliações acrescentadas pelo fechamento
> diário, nunca reescritas. A previsão padrão é `descartar`. Régua e disciplina:
> [[11-KNOWLEDGE/KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout|KB-0092]] e
> [[06-DECISIONS/2026-09-10-validacao-em-um-dia-e-lucro-real|a decisão de 10/09]].

## Diretiva de origem

A [[03-TRADING/Meme/Candidatas/2026-09-16-21h40-brt|R41]] mostrou a **primeira compra real** da mesa
(TAXCOIN, 21:31:28 BRT) saindo **71 s depois de a curva perder 24 de 29,6 SOL reais**, com saída
`creator_dump` 48 s depois (−0,0098 SOL). A porta não tem critério de "queda recente". A
[[11-KNOWLEDGE/KB-0118-nao-entrar-depois-da-queda|KB-0118]] mediu nove variantes do filtro sobre 613
entradas da porta atual em 5 dias (12–16/09) e fechou nesta. A
[[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta|KB-0108]] já tinha o mesmo sinal **na saída**
(precisão 84,3 %, lead 70 s); este braço é a **perna de entrada**, e só isso.

## Hipótese (congelada)

**H1:** recusar a entrada quando, na foto de curva mais recente, a moeda perdeu **≥ 50 %** do pico de
`real_sol_reserves` observado nos **últimos 60 s**, aumenta o R médio do conjunto vivo porque a foto de
curva (defasagem mediana **12 s**) enxerga um colapso que as features de fita, agregadas em 60 s, ainda
não mostram — e essa célula é onde a **cauda desaparece** (≥ +2 R cai de ~13 % para **4,1 %**).

**H0 (previsão):** o ganho in-sample (**Δ +0,038 R**, IC [+0,022; +0,054], P(Δ > 0) = 1,00) é artefato da
mesma amostra que escolheu X e N entre nove combinações; prospectivamente o Δ não se separa do zero →
**`descartar`**.

## Definição congelada (`flow_v2/8`) — clone do conjunto vivo com **uma** mudança

`flow_v2/8` = próxima versão livre de `flow_v2` (/6 reservada ao [[05-EXPERIMENTS/EXP-M9-pedigree-e2b|EXP-M9]],
/7 ao [[05-EXPERIMENTS/EXP-M10-compradores-25|EXP-M10]]).

| critério | limiar | recusa |
|---|---|---|
| idade (foto de 15 s) | 30–300 s | `age_below_min` / `age_above_max` |
| progresso da curva | 0,05–0,50 (fração 0–1) | `progress_below_min` / `progress_above_window` |
| fita | presente (`tape_reason IS NULL`) | `tape_blind` |
| fluxo | `net_sol_flow_60s > 0` | `flow_not_positive` |
| dev | ≤ 0,10, desconhecido recusa | `dev_share_above_max` / `dev_share_unknown` |
| snipers | ≥ 21 | `snipers_below_min` / `snipers_unknown` |
| pedigree | E2 (criador em série, clone) | `creator_serial` / `symbol_clone` |
| Mayhem | `exclude_mayhem: true` | `mayhem_curve` / `mayhem_unknown` |
| holders | ≥ 20 | `holders_below_min` |
| compradores únicos | ≥ 10 (o **vivo**; o piso 25 é o EXP-M10, outro braço) | `buyers_below_min` |
| razão de vendas | `sells_60s / buys_60s ≤ 0,6` | `sells_ratio_above_max` |
| participação | ≤ 1 % do volume do minuto | `participation_above_cap` |
| **queda recente (NOVO)** | **`real_sol_atual < 0,50 × max(real_sol_reserves)` nos últimos 60 s ⇒ recusa** | **`recent_drawdown`** |
| **queda recente — sem foto** | **foto de curva ausente ou com > 30 s de defasagem ⇒ recusa** | **`recent_drawdown_unknown`** |

**Definição operacional do critério novo** (congelada, sem look-ahead: só fotos com `observed_at ≤ t_decisão`):

- `pico = max(real_sol_reserves)` sobre `meme_curve_snapshots` em `[t_decisão − 60 s, t_decisão]`;
- `atual = real_sol_reserves` da **última** foto com `observed_at ≤ t_decisão`;
- recusa se `pico > 0` **e** `atual / pico < 0,50`;
- **recusa também** se não houver foto em `[t_decisão − 30 s, t_decisão]` (fail-closed — sem isso o critério
  vira ruído de cobertura, e a KB-0118 mediu com defasagem p90 de 14 s);
- **avaliado a cada decisão** (relógio de 15 s): a moeda recusada hoje pode entrar 30 s depois se a curva
  parar de cair — é **reentrada**, não banimento da moeda. Isto é deliberado: a célula `dd > 50 %` com pico
  **velho** (60–180 s) foi a **melhor** de todas (+0,566 R, n = 17) e o braço não pode cortá-la.
- `real_sol_reserves` em **SOL**; `curve_progress_pct` fração 0–1; `mayhem_mode` texto.

Saídas idênticas às do conjunto vivo: alvo **3×**, trailing **35 %** armado depois de 1,5×, piso **−50 %**,
tempo **30 min**, `creator_dump`. Tamanho 0,05 SOL; taxa **1,75 % por perna**; `R = (múltiplo líquido − 1)/0,5`.
Controle = o conjunto vivo (`flow_v2/5`) rodando **no mesmo período**. Mexer em qualquer outro limiar dentro
deste braço invalida a coorte.

## Portão de desenho (C1–C8) — congelado

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | **PASS** | Mecanismo declarado e falsificável: a foto de curva (12 s) chega antes da fita (60 s); se o ganho vier de outra coisa, a coorte recusada não teria por que ter cauda de 4,1 % contra ~13 % |
| C2 | Sobreajuste | **REVISE** | X e N escolhidos entre **nove** combinações na mesma amostra que os mede (KB-0092). O que não depende da escolha é a coorte cortada ser negativa nos **5 dias separados** (−0,35/−0,46/−0,07/−0,40/−0,23) |
| C3 | Amostra | **PASS** | 540 entradas sobreviventes em 5 dias (108/dia de **teto**, antes de TTL/dedup/cooldown): 150 propostas fecham em poucos dias de radar |
| C4 | Regime | **REVISE** | 5 dias, dois parciais (12/09 com 16 entradas, 16/09 com 75); o LOO é fraco nas pontas |
| C5 | Saídas | **PASS** | Saídas byte a byte iguais às do controle; a perna de saída por drawdown é a [[05-EXPERIMENTS/EXP-M11-saida-drawdown-20-apos-1p5x|EXP-M11]], **outro** braço — rodar os dois juntos confunde a atribuição |
| C6 | Concentração | **PASS** | 0,05 SOL, ≤ 1 % do volume do minuto, mesmo teto de abertas do vivo |
| C7 | Execução | **REVISE** | O critério depende de **frescor de dado**: em produção a foto de curva pode faltar, e o `fail-closed` transforma buraco de coleta em recusa. A fração de `recent_drawdown_unknown` é **parte do que se mede** |
| C8 | Invalidação | **PASS** | Quatro gatilhos abaixo, mais a régua geral (≥ 100 apostas medidas e 30 dias, IC 95 % por blocos de dia, leave-top-out) |

## Previsões (congeladas, numéricas)

- **P1** Δ R médio contra o controle no mesmo período ∈ **[+0,00; +0,08]**, ponto **+0,038**.
- **P2** Cadência do braço entre **80 % e 95 %** da do controle (in-sample 540/613 = **88,1 %**).
- **P3** A coorte **recusada** por `recent_drawdown` (medida à parte, em papel, como se tivesse entrado) tem
  R médio **negativo** e taxa de cauda (≥ +2 R) **abaixo de 8 %** (in-sample −0,305 R e 4,1 %). Se a recusada
  empatar com o resto, o mecanismo é falso **mesmo que o Δ agrade**.
- **P4** R **mediano** do braço **igual ou pior** que o do controle (in-sample −0,713 × −0,655): o filtro tira
  apostas mortas-vivas que saem por tempo perto de zero, não melhora o acerto.
- **P5** `recent_drawdown_unknown` responde por **≤ 10 %** das recusas do braço (a defasagem medida da foto de
  curva é mediana 12 s, p90 14 s, máx 16 s). Acima disso o braço está medindo cobertura, não queda, e a leitura
  é **nula** por instrumento.

## Gatilhos de descarte (qualquer um basta)

1. Δ R médio ≤ 0 com IC 95 % de blocos de dia inteiramente ≤ +0,01 depois de **150 propostas**.
2. P3 falhar: a coorte recusada **não** ser pior que o resto (mecanismo falso).
3. Cadência abaixo de **70 %** da do controle — o filtro estaria cortando muito mais do que os 11,9 % medidos,
   sinal de que em produção ele lê outra coisa.
4. O resultado depender de **um** dia: leave-one-day-out com qualquer remoção levando Δ abaixo de zero.

## Régua e prazo

Leitura **única** no fim, sem espiar para decidir: mínimo **150 propostas do braço E 10 dias corridos**, o que
vier por último, com LOO obrigatório. O **veredito de vida** (qualquer conversa sobre dinheiro real) só pela
régua do laboratório: **≥ 100 apostas medidas e 30 dias**, IC 95 % por blocos de dia, leave-top-out. Critério
reprovado volta só com **mecanismo novo**, nunca com dados novos.

## O que NÃO fazer

Alargar N para 120 s ou 300 s "para pegar a TAXCOIN" — a KB-0118 §3 mostra que isso corta junto a PPC (+1,78×)
e que o Δ **cai** (+0,024 e +0,018 contra +0,038); baixar X para 20 % (Δ +0,035 com IC cruzando o zero e −32 %
de cadência); transformar o critério em **banimento** da moeda em vez de recusa por decisão (mataria a célula de
+0,566 R); rodar junto com EXP-M10 ou EXP-M11 no mesmo conjunto; usar `mcap_sol` em vez de `real_sol_reserves`
([[11-KNOWLEDGE/KB-0115-volta-ao-piso-e-real-ou-artefato|KB-0115]]); ligar dinheiro real antes da régua.

## Avaliação
_(append-only; o fechamento diário acrescenta uma seção datada por dia com aposta fechada)_

## Fontes

[[11-KNOWLEDGE/KB-0118-nao-entrar-depois-da-queda|KB-0118]] §1–§6 (todos os números desta página) ·
[[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta|KB-0108]] §3 (o mesmo sinal na saída) ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] §3 (metodologia de R) ·
[[11-KNOWLEDGE/KB-0115-volta-ao-piso-e-real-ou-artefato|KB-0115]] · [[11-KNOWLEDGE/KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout|KB-0092]] ·
[[03-TRADING/Meme/Candidatas/2026-09-16-21h40-brt|R41]] ·
`infra/scripts/sql/research/2026-09-16-r42-q01-drawdown-na-entrada-e-r.sql` · `…-r42-q02-*.sql` · `…-r42-q03-*.sql` ·
`packages/indicators/hunter_indicators/meme/rules.py` · `docs/RISK_ENGINE_MEME.md`.
