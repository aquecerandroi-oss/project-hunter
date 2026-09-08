---
tags: [experimento, mean-reversion, custo]
updated: 2026-09-08
status: em-andamento
owner: quant-engineer
exp: EXP-0015
strategy: "mean_reversion"
version: "v3"
result: inconclusivo
evaluable: 11
days: 4
last_eval: "2026-09-08"
---

# EXP-0015 — mean_reversion com teto de pedágio 0,20 R (`atr_pct_min` 0,006 → 0,010)

> Rascunho para a Sexta-feira arquivar em `obsidian/05-EXPERIMENTS/`. O número **EXP-0015** é a
> próxima vaga livre lida em 2026-09-08T21:45Z; se outra tarefa tomar o número antes, renumerar.

## Hipótese (congelada)

A mesma do [[EXP-0014-mean-reversion-teto-025]], com o piso um degrau acima: com `stop_atr = 1`,
`atr_pct_min = 0,010` ⇒ **pedágio ≤ 0,20 R**. A T3.33e mediu que **70 % das decisões abaixo de
ATR% 1,0 % são líquidas negativas com bruta positiva**; este EXP é a versão literal daquela
observação: proibir a decisão exatamente abaixo de 1,0 %.

**O que a hipótese não promete:** nada além de custo. E este EXP nasce com um problema declarado que
o irmão não tem — ele **ultrapassa a régua do EXP-0006**.

## Portão de desenho (C1–C8) — congelado

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade da vantagem | **PASS com ressalva** | Idêntico ao EXP-0014: `custo_R = 0,0020 / ATR%` com `stop_atr = 1`. Mecanismo aritmético, não preditivo |
| C2 | Risco de sobreajuste | **REVISE** | O limiar tem origem declarada (0,20 R) **e** coincide com o ponto que a T3.33e nomeou depois de olhar esta mesma janela — é a fronteira entre "origem teórica" e "garimpo". A diferença medida contra o EXP-0014 são **6 decisões e 0,55 R**: escolher 0,010 em vez de 0,008 por causa deste replay seria decidir por ruído |
| C3 | Adequação da amostra | **REJECT** | Previsto e medido: 11 das 37 decisões do pai têm ATR% ≥ 0,010 ⇒ corte de **70,3 %**. A regra do EXP-0006/[[KB-0008]] ("um piso que elimina mais de 70 % dos sinais é outra estratégia, não a mesma com menos ruído") **dispara**, por 0,3 ponto percentual. Pior: as 11 decisões vivem em **4** dias, todos entre 2026-08-20 e 2026-08-23; nos 16 dias seguintes esta versão **não decide nada**. `n = 11 < 30` ⇒ o estresse recusa veredito |
| C4 | Dependência de regime | **REJECT declarado** | Consequência do C3: 100 % das decisões em 4 dias consecutivos de um recorte de 31. Isto não é uma estratégia com menos custo, é uma **aposta num episódio de volatilidade** |
| C5 | Calibração das saídas | **PASS** | Stop 1 ATR com piso 0,010 ⇒ distância mínima do stop **1,0 % do preço**, dentro da banda `[0,003; 0,03]` do `paper_v1`. Ressalva medida: **2 das 11** decisões têm ATR% > 3 % e somam −0,13 R — recusadas pelo sizing numa linha `paper` (e agora são 18 % da população, não 12 %) |
| C6 | Concentração de risco | **PASS como pesquisa** | `research_only`, sem carteira. Mas registre-se: 11 operações em 31 dias sobre 4 mercados é uma frequência que não sustenta avaliação estatística nenhuma |
| C7 | Realismo de execução | **PASS com ressalva forte** | Mesmos custos assumidos do pai. **Duas ressalvas medidas:** (a) o teto é médio, não garantido — a pior decisão pagou **0,269 R** contra os 0,20 R prometidos, porque o risco inicial efetivo varia entre 0,61 e 1,08 ATR; (b) no estresse, `entrada_mais_1_barra` deu Δ **−0,1262 R com IC [−0,3072; −0,0397]**, que **exclui zero** — esta população depende de entrar na barra certa |
| C8 | Qualidade da invalidação | **PASS por herança** | Sem invalidações nesta janela (0 de 11) |

**Veredito do portão:** **`REVISE`** — C3 e C4 reprovam e C2 fica na fronteira. O EXP existe para
ficar registrado e para a coorte prospectiva rodar, **não** como candidato a promoção.
2026-09-08, quant-engineer.

## Protocolo (congelado na ativação)

- **Strategy:** `mean_reversion` / `v3`
- **code_ref:** `hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f` (idêntico ao do pai `v1`)
- **params_hash / params_format:** `a71311773886` / `1`
- **Parameters:** `{"fee_bps":"4","atr_bars":"97","stop_atr":"1","horizon_s":"14400","atr_period":"14","target_atr":"1.5","atr_pct_max":"0.05","atr_pct_min":"0.01","target2_atr":"2.5","zscore_bars":"20","slippage_bps":"5","atr_timeframe":"15m","trend_sma_bars":"20","base_confidence":"0.5","trend_timeframe":"1h","zscore_depth_min":"1","max_entry_delay_s":"120","assumed_spread_bps":"2"}`
- **Linhagem:** `variante de v1 | derived_from=v1 | overrides=atr_pct_min=0.01 | params_hash=a71311773886 | T3.42 V2: coorte de pesquisa do teto de pedagio 0,20 R (atr_pct_min 0,010) aberta`
- **Timeframe, agregação, entrada, saída, custos, reentrada:** idênticos ao [[EXP-0014-mean-reversion-teto-025]] (mesmo `code_ref`, só `atr_pct_min` difere)
- **Cohort:** `replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4` (retrospectiva) e `prospective` (aberta em **2026-09-08T21:34:01,491564Z** = 18:34:01 Brasília)
- **Controle predeclarado:** o **pai** `mean_reversion v1` na coorte `replay:d0f77894-1e04-454e-a49f-d9a98d894968`
- **Universo elegível:** `markets.is_monitored` **de hoje** (`docs/PIPELINE.md` §6c)
- **Markets:** binance ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT (replay); universo monitorado inteiro (prospectiva)
- **Janela de replay:** 2026-08-08 → 2026-09-08, em duas fatias contíguas

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-08 — **REPLAY** (retrospectiva) — `read_at = 2026-09-08T21:37:59Z`

> **Rótulo obrigatório: REPLAY.** Mesma janela que gerou a hipótese ([[KB-0010]]).

**SQL usado:** `q10-pop.sql`, `q11b-pareado-v2.sql`, `q12-motivos.sql`, `q13-blocos.sql`,
`q21-identidade.sql`, `q24-dias.sql` em `.claude/state/exp-drafts/t342-sql/`.

**Cobertura (contagens completas):**

| Emitidos | Pendentes | Entradas | Não entradas | Ativos | Target | Stop | Expired | Invalidated | Censurados | Funding indisponível | Avaliáveis |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 11 | 0 | 11 | 0 | 0 | 4 | 3 | 4 | 0 | 0 | 0 | **11** |

**Livro-razão** (11 904 barras): `unavailable` 448 (`warmup` 140, `atr_warmup` 308),
`not_triggered` 11 437 (`no_uptrend_1h` 5 288, `not_stretched` 5 424, `close_below_mid` 525,
**`atr_out_of_range` 200**), `triggered` 19. As 200 recusas de ATR estão todas abaixo do piso
(máx 0,9347 %).

**Métricas:** expectancy bruta **+0,6587 R**, custo **0,1452 R**, expectancy líquida **+0,5131 R**,
soma **+5,64 R**, acerto **36,4 %**, PF líquido **2,6919**, PF bruto **3,5380**, **4** dias com
outcome avaliável. `PnL de carteira` e `Max Drawdown`: **não aplicáveis**.

**Os quatro grupos pareados (método T3.26):**

| Grupo | n | avaliáveis | bruta (R) | custo (R) | líquida (R) | soma R | dias |
|---|---:|---:|---:|---:|---:|---:|---:|
| pai pareado com a variante | 11 | 11 | +0,6587 | 0,1452 | **+0,5131** | +5,64 | 4 |
| pai **sem par** (eliminadas pelo piso) | 26 | 26 | +0,1782 | 0,2606 | **−0,0836** | −2,17 | 9 |
| variante pareada com o pai | 11 | 11 | +0,6587 | 0,1452 | +0,5131 | +5,64 | 4 |
| variante **sem par** no pai | **0** | 0 | — | — | — | — | — |

**Δ pareado decisão a decisão: 0,0000 R em 11 pares**, `mesmo_risco_inicial = 11/11`,
`mesmo_motivo = 11/11`. Subconjunto exato do pai — e **subconjunto exato do EXP-0014** também: a
diferença entre as duas variantes são as 6 decisões da faixa [0,008; 0,010), que valem
**−0,0912 R por decisão, −0,55 R no total**.

**Contraste com bootstrap de blocos por dia** (11 dias, 10 000 reamostragens, semente 20260908):
Δ = expectancy(variante) − expectancy(pai) = **+0,4193 R**, **IC 95 % [−0,0072; +1,7829] — contém
zero** (por pouco, e com apenas 9 925 de 10 000 reamostragens produzindo alguma decisão acima do
piso: em 75 reamostragens de dias a variante **não decide nada**, o que por si só descreve a
fragilidade).

**Passada de estresse** (`replay.stress`, `as_of 2026-09-08T21:40:18Z`, 11 entradas congeladas):
`custos_x2` **+0,3530 R / PF 2,0686** (Δ −0,1601); **dois cenários com IC do Δ excluindo zero** —
`stop_x0.75` +0,2618 [+0,1635; +0,4830] e `entrada_mais_1_barra` −0,1262 [−0,3072; −0,0397] —, o que
com `n = 11` é sensibilidade a parâmetro e a temporização de entrada, não robustez.
**Veredito da passada: `amostra_insuficiente` (11 de 30)**.

- **Result:** **inconclusivo**
- **Conclusion:** os números de superfície são os melhores das três populações (PF 2,69, expectancy
  +0,51 R, custo 0,145 R) e **não valem nada como evidência**: 11 operações, 4 dias consecutivos,
  70,3 % das decisões do pai eliminadas — a régua do EXP-0006 diz, com essa contagem, que isto **é
  outra estratégia**, que precisa do seu próprio desenho e da sua própria coleta, e não a
  `mean_reversion` com menos custo. A diferença real contra a irmã 0,008 são 6 operações
- **Next Action:** coorte `prospective` aberta em 2026-09-08T21:34:01Z; reavaliar em **30 dias**
  contra `v1` e `v2` na **mesma** janela. **Não** promover a `paper`. Se a frequência prospectiva
  também for ~0 (o piso corta os dias calmos e o universo prospectivo é 200 mercados, não 4),
  `descartar` — e o eixo do teto de pedágio fica esgotado nesta estratégia

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| `atr_pct_min = 0,006` (`mean_reversion v1`, pai) | 2026-09-08 16:32:33Z | desenho original do [[EXP-0009]] | [[EXP-0009-mean-reversion-pullback-em-tendencia]] |
| `atr_pct_min = 0,008` (`v2`) | 2026-09-08 21:24:26Z | pedágio ≤ 0,25 R | [[EXP-0014-mean-reversion-teto-025]] |
| `atr_pct_min = 0,010` (`v3`) | **2026-09-08 21:34:01Z** | pedágio ≤ 0,20 R; fronteira da T3.33e | **este EXP** |

## Relacionadas

[[EXP-0014-mean-reversion-teto-025]] · [[EXP-0009-mean-reversion-pullback-em-tendencia]] ·
[[EXP-0012-momentum-teto-de-pedagio]] · [[KB-0076-por-que-perdemos-2026-09-08]] · [[KB-0008]] ·
[[KB-0010]] · [[Experiments Index]] · [[Strategy Backlog]]

## Fontes

`.claude/state/notes-T3.42.md` · `replay_runs` coortes
`replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4` e `replay:d0f77894-1e04-454e-a49f-d9a98d894968` ·
`system_events` · livro-razão `--explain-ledger` de 11 904 linhas ·
`.claude/state/stress-mean-reversion-v1-2026-09-08.md`.
