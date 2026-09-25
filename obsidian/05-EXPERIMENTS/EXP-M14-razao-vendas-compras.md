---
tags: [experimento, meme, pumpfun, paper, pre-registro, vendas-compras, porta, m5]
updated: 2026-09-17
status: pre-registrado
owner: astra-quant
exp: EXP-M14
strategy: "meme/pumpfun - porta calibrada com teto de sells/buys em 1.0 aplicado na escolha da barra, clone exato do conjunto vivo em todo o resto"
version: "gate fluxo_e_holders v2 (max_sell_buy_ratio 1.0, reentrada) + exit alvo_3x_trailing_35_apos_1_5x_tempo_30m v1 (flow_v2/x; porta no relogio de 15 s, entrada na barra de 1 min)"
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

# EXP-M14 — teto de 1.0 em sells/buys (razao de vendas/compras), aplicado na escolha da barra

**Pre-registro escrito em 2026-09-17 (02:00 BRT), apos analise R48 de 24h de moedas graduadas e antes de o conjunto existir no banco.**

Protocolo congelado; avaliacoes acrescentadas pelo fechamento diario, nunca reescritas. Previsao padrao: `descartar`. Regua e disciplina: KB-0092 e decisao de 10/09.

## Diretiva de origem

R48 analisou a distribuicao de `buy_sell_ratio` (sells/buys) em moedas que graduaram nos ultimos 24h. Achado principal: o cap 0.6 da porta viva (operator/5, flow_v2/6) descarta 113 de 459 graduadas (24.6%), com taxa de graduacao 4x menor abaixo de 0.6 (0.53% vs 2.12%). Um cap em 1.0 reteria 95%+ das graduadas enquanto captura o pico de taxa (2.21% no bucket 1.0-1.5).

## Hipotese (congelada)

H1: elevar o teto de `buy_sell_ratio` de 0.6 para 1.0, aplicando o limite na escolha da barra (reentrada, nao recusa definitiva), aumenta o R medio do conjunto porque recupera moedas que iniciam com sell pressure moderado mas depois se estabilizam. H0 (previsao): o ganho em graduacoes eh compensado por maior ruina (sell pressure precoce = marker de pump-dump), e o R liquido sai negativo.

## Definicao congelada (flow_v2/x) - clone do conjunto vivo com UMA mudanca

max_sell_buy_ratio: 0.6 PARA 1.0 (reentrada ate 5 min apos a porta)
Demais criterios identicos a flow_v2/6: holders >= 20, buyers >= 10, progress 0.05-0.50, dev <= 0.10, snipers >= 21, E2 pedigree, exclude_mayhem, participation <= 1%, net_sol_flow > 0.

Saidas: alvo 3x, trailing 35% apos 1.5x, piso -50%, tempo 30 min. Size 0.05 SOL, taxa 1.75% por perna. R = (multiplo liquido - 1) / 0.5. Controle = flow_v2/6 no mesmo periodo.

## Portao de desenho (C1-C8) - congelado

| C | Criterio | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade | PASS | Mecanismo falsificavel: sell pressure < 1.0 captura transicao pump→dump |
| C2 | Sobreajuste | REVISE | O 1.0 saiu de olhar 24h (459 graduadas); faixa 0.6-1.0 tem n=979 e 21 graduadas |
| C3 | Amostra | PASS | 459 graduadas em 24h, 28k mints com >=3 leituras - cadencia alta |
| C4 | Regime | REVISE | Um dia; padroes variam por hora da semana. Upgrade poller em 16/09 pode ter mudado universo |
| C5 | Saidas | PASS | Saidas identicas ao controle |
| C6 | Concentracao | PASS | 0.05 SOL, <= 1% volume, mesmo teto do vivo |
| C7 | Execucao | REVISE | Reentrada ate 5 min atrasa entrada de proposito. Impacto nao medido |
| C8 | Invalidacao | PASS | Quatro gatilhos de descarte, regua geral (>=100 apostas, 30 dias, IC 95%) |

## Previsoes (congeladas, numericas)

- P1: Delta R medio contra controle em [-0.00; +0.15], ponto +0.05
- P2: Cadencia do braco entre 70% e 95% do controle (in-sample ~85%)
- P3: Taxa de ruina (R <= -0.5) nao sobe mais de 3pp acima do controle
- P4: R mediano do braco melhor que controle (P50 1.0 vs 1.19 em graduated)
- P5: Graduacao < 2.5% (in-sample 1.83%, 340 NULLs escondidos)

## Gatilhos de descarte

1. Delta R <= -0.05 com IC <= +0.00 depois de 150 propostas
2. Taxa de ruina subir > 3pp acima do controle
3. Cadencia < 60% do controle
4. R mediano pior que controle

## Regua e prazo

Leitura UNICA ao fim: minimo 150 propostas do braco E 10 dias corridos, o que vier por ultimo, LOO obrigatorio. Veredito de vida (dinheiro real) so pela regua do lab: >=100 apostas e 30 dias.

## O que NAO fazer

Subir cap para 1.5+ (taxa ruina sobe); tirar max_sell_buy_ratio neste braco; ajustar 1.0 olhando dias iniciais; ligar dinheiro real antes regua.

## Braco semeado

Quando: 2026-09-17 apos R48 congelada
Como: migracao 0050_meme_gate_sells_buys_arm
Conjunto: flow_v2/8, kind=research_only, exp_ref=EXP-M14, max_sell_buy_ratio 0.6 → 1.0
Papel: executor so abre kind='operator', research_only nao alcanca dinheiro real
Controle: flow_v2/6 (max_sell_buy_ratio 0.6) mesmo periodo

## Braco semeado (T4.49)

**Quando:** 2026-09-17, ~02:50 BRT (UTC-3), depois de R48 e R51 congeladas.

**Migracao:** `0050_meme_gate_ratio10_arm` (sobre `0049_meme_gate_buyers25_arm`), toda a semente em
`infra/migrations/ddl/meme_gate_ratio10_arm.py`. Sem mudanca de schema, nada aposentado.

**Conjunto:** `flow_v2/8`, id `01994d00-6c1a-7000-8000-000000000015`, `kind=research_only`,
`exp_ref=EXP-M14`, `status=active`, relogio de 15 s.

**Parametros:** `flow_v2/6` inteiro com **um** valor mexido — `max_sells_to_buys` `"0.6"` para `"1.0"`.
Tudo o mais byte a byte igual (holders >= 20, buyers >= 10, progress 5-50 %, dev <= 0,10, snipers 21-1000,
`pedigree_e2b`, `exclude_mayhem`, participacao <= 1 %, fluxo > 0; saidas alvo 3x / trailing 35 % apos 1,5x /
piso 50 % / 1800 s; size 0,05 SOL; fee 1,75 %). `test_migration_0050` prova a igualdade tirando a chave dos
dois conjuntos.

**Quatro desvios declarados** (tambem em `docs/DATABASE.md` § 58):

1. A chave real e `max_sells_to_buys`, **string**, e nao o `max_sell_buy_ratio` que este pre-registro
   nomeia — esse e o nome da coluna de feature (`meme_features_1m.buy_sell_ratio`). Mexer no nome da pagina
   teria semeado um parametro que nenhum codigo le, isto e, um clone do controle com outro rotulo.
2. O slug previsto aqui (`0050_meme_gate_sells_buys_arm`) nao e o que subiu: a revisao e
   `0050_meme_gate_ratio10_arm`. Mesma `0050`, mesmo braco.
3. A base e `flow_v2/6`, que carrega `pedigree_e2b: true` — que e exatamente o controle que este
   pre-registro nomeia; a leitura honesta e `flow_v2/8` contra `flow_v2/6`, nunca contra `operator/5`.
4. `gate_version` continua 3: o conjunto de criterios nao mudou, so um limiar, que os proprios `params`
   carregam.

A "reentrada ate 5 min" **nao** virou parametro: a porta e julgada a cada foto de 15 s dentro de 30-300 s,
entao a moeda acima do teto numa barra e abaixo numa seguinte e proposta ali. Recusa definitiva exigiria
chave nova, e nenhuma foi criada.

**Papel por construcao:** o executor so abre proposta de `kind = 'operator'`
(`hunter_meme_executor.auto_approve._OPERATOR_PROPOSED`), logo `research_only` nunca alcanca dinheiro real.

**Regra de decisao e prazo:** leitura UNICA quando **ambos** fecharem — >= 150 propostas de `flow_v2/8` **e**
10 dias corridos, ou seja, nao antes de **2026-09-27 (BRT)**. Antes disso nenhum numero do braco decide nada.
Veredito: descartar se qualquer gatilho da secao "Gatilhos de descarte" disparar (delta R <= -0,05 com IC
<= +0,00 apos 150 propostas; ruina > 3 pp acima do controle; cadencia < 60 % do controle; R mediano pior que
o controle). Previsao registrada continua `descartar`. Vida (dinheiro real) so pela regua do lab: >= 100
apostas e 30 dias.

## Avaliacao

(append-only; fechamento diario acrescenta secao datada)

## Fontes

R48 (analise bruta, caveats, SQL)
KB-0099 §3 (metodologia R)
docs/DATABASE.md § meme_features_1m (definicao buy_sell_ratio)
packages/indicators/hunter_indicators/meme/rules.py
docs/RISK_ENGINE_MEME.md

