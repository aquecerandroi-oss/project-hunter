---
tags: [experimento, momentum, custo]
updated: 2026-09-08
status: em-andamento
owner: quant-engineer
exp: EXP-0012
strategy: "momentum"
version: "v5"
result: inconclusivo
evaluable: 0
days: 0
last_eval: "2026-09-08"
---

# EXP-0012 — momentum com teto de pedágio (`atr_pct_min` 0,003 → 0,020)

> Rascunho para a Sexta-feira arquivar em `obsidian/05-EXPERIMENTS/`. O número **EXP-0012** é a
> próxima vaga livre lida em 2026-09-08T19:25Z; se outra tarefa tomar o número antes, renumerar.

## Hipótese (congelada)

Proibir a decisão quando o risco inicial for pequeno demais em relação ao preço põe um **teto
declarado no pedágio**: com `stop_atr = 1,5` e `atr_pct_min = 0,020`, o stop fica a ≥ 3,0 % do preço
e os 20 bps de ida e volta custam **≤ 0,067 R** por operação (a [[KB-0076]] mede
`custo_R × risco% = 0,0020` constante em dez populações, onde `risco%` é a **distância do stop** em
fração do preço). É a variante V1 do brief T3.32 §"Variantes exatas a derivar", que pede "teto
≤ 0,10 R" — satisfeito com folga.

**Correção aritmética declarada:** a [[KB-0076]] escreve "a v4 (0,0089) já testa 0,22 R" aplicando a
identidade ao **ATR%** em vez de à distância do stop. Como `risco% = stop_atr × ATR% = 1,5 × ATR%`,
os números certos são **≈ 0,15 R para a `v4`** (0,0020 / 0,01335) e **≤ 0,067 R para esta `v5`**
(0,0020 / 0,03). O sinal e a ordenação das variantes não mudam; a magnitude sim.

**O que a hipótese não promete:** um teto de custo **não cria** vantagem, só para de destruí-la
([[KB-0076]] item 9). O bruto da `momentum v2` na janela de replay é +0,082 R — cortar custo sobre
um bruto de ~0 não inverte o sinal.

## Portão de desenho (C1–C8) — congelado

Nenhum código novo: a variante é `momentum_v1` congelada (`sha256:ab2e0398…`) com **um** parâmetro
movido. O portão avalia o **desenho da variante**, não a estratégia-mãe.

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade da vantagem | **PASS com ressalva** | O mecanismo não é de previsão, é **aritmético**: `custo_R = 0,0020 / risco%` (identidade medida em dez populações, desvio ≤ 1,9×10⁻⁵, [[KB-0076]]). Quem está do outro lado é a corretora e o livro, não um perdedor informado — por isso o efeito esperado é **cortar despesa**, e a ressalva é que despesa cortada não é vantagem |
| C2 | Risco de sobreajuste | **PASS** | Um limiar, dois algarismos significativos (`0,020`), **origem declarada**: é o valor que faz `custo_R ≤ 0,10 R` na aritmética do C1 (na verdade ≤ 0,067 R — ver a correção acima), não um valor garimpado numa curva de resultado. Nenhuma condição de entrada nova (as quatro portas do `momentum_v1` continuam as mesmas) |
| C3 | Adequação da amostra | **REVISE** | Estimativa declarada **antes** da corrida: a `v4` (piso 0,0089) cortou 86 % das decisões em 31 dias × 4 mercados; um piso 2,2× maior cortaria mais. A conta feita depois (livro-razão) deu **100 %** nesses quatro mercados. No universo prospectivo de 200 mercados a frequência é outra, e é o que a coorte `prospective` mede — o primeiro sinal saiu 19 min após a ativação |
| C4 | Dependência de regime | **PASS por herança** | Igual à mãe; a [[KB-0076]] item 6 mediu que a perda da `momentum` é uniforme por hora, dia e direção do BTC, e `market_regimes` tem uma única linha `UNKNOWN` — não há regime a excluir hoje, e o envelope grava `regime_reason=no_regime_asof` |
| C5 | Calibração das saídas | **REJECT do preset `paper_v1`; PASS como pesquisa** | Stop 1,5 ATR com `atr_pct_min = 0,020` ⇒ distância **mínima** do stop **exatamente 3,0 % do preço**, que é o **teto** `max_stop_distance_pct` do `paper_v1` (`limits.py:151-152`, banda `[0,003; 0,03]`, comparação inclusiva em `checks.py:252`). Consequência aritmética: só a barra que cai exatamente no piso passaria; **toda barra com ATR% > 2,0 % teria o sizing recusado pelo Risk Engine**. É `research_only` e **não é candidata a linha `paper`** sem uma conversa sobre o preset — escrito aqui para o `code-reviewer` não descobrir depois |
| C6 | Concentração de risco | **PASS** | Nada muda: `research_only`, sem linha em `agents`, sem carteira; o teto reduz a frequência, nunca a aumenta |
| C7 | Realismo de execução | **PASS** | Mesmos custos assumidos da mãe (2 bps de spread total, 5 bps de slippage por lado, 4 bps de taxa por lado), mesmo `max_entry_delay_s = 120 s`, mesmos mercados |
| C8 | Qualidade da invalidação | **PASS por herança declarada** | Herda `close_below prior_max` do `momentum_v1` **de propósito**: o EXP-0007 mediu os três braços INV sobre entradas congeladas e nenhum se distingue de zero (Holm ≥ 0,83) — mexer nela aqui misturaria dois experimentos |

**Veredito do portão:** `PASS` com as ressalvas de C3 e C5 registradas — 2026-09-08, quant-engineer.
Se o C5 for julgado impeditivo, o caminho é um piso menor (a faixa 0,010–0,015 mantém o stop dentro
do preset) e isso é **outro** EXP, não uma edição deste.

## Protocolo (congelado na ativação)

- **Strategy:** `momentum` / `v5`
- **code_ref:** `hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c` (idêntico ao do pai `v2`)
- **params_hash / params_format:** `2aef4a5ff989…` / `1`
- **Parameters:** `{"fee_bps":"4","atr_bars":"97","rvol_min":"1.5","stop_atr":"1.5","horizon_s":"14400","atr_period":"14","return_min":"0","target_atr":"1.5","atr_pct_max":"0.05","atr_pct_min":"0.02","rvol_window":"96","target2_atr":"3","target3_atr":"4.5","slippage_bps":"5","atr_timeframe":"15m","base_confidence":"0.5","lookback_closes":"20","max_entry_delay_s":"120","assumed_spread_bps":"2"}`
- **Linhagem:** `variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.02 | params_hash=2aef4a5ff989 | T3.40 V1: coorte de pesquisa do teto de pedagio (atr_pct_min 0,020) aberta`
- **Timeframe de decisão / de outcome:** 15 min / 1 min, UTC
- **Agregação e ATR:** 1 m → 15 m só com barras UTC contíguas e finais; ATR = Wilder(14) de 15 min, seed e âncora persistidos no envelope
- **Entrada:** open da primeira barra de 1 min estritamente posterior a `decision_at`, com `entry_bar_open − source_bar_close ≤ 120 s`
- **Saída:** gap na abertura primeiro, depois toques intrabar; stop e alvo na mesma barra → **stop** (convenção pessimista); horizonte 4 h contado da entrada
- **Custos assumidos (hipóteses, não tarifas verificadas):** spread total 2 bps, slippage 5 bps por lado, taxa 4 bps por lado; funding assinado
- **Política de reentrada:** um acompanhamento `pending_entry|active` por `(strategy_version_id, market_id, cohort)`; rearme só depois do término anterior
- **Cohort:** `replay:72cf5671-ec16-4d62-afd6-ace3f7bbf4e1` (retrospectiva) e `prospective` (aberta em 2026-09-08T18:57:05,384576Z)
- **Controle predeclarado:** o **pai** `momentum v2` na coorte `replay:f8d8279c-1fba-42ae-95ef-202042f96c60`, pareado por `(mercado, barra de decisão)` — o método da T3.26
- **Universo elegível:** `markets.is_monitored` **de hoje** (limitação declarada do motor de replay, `docs/PIPELINE.md` §6c); `provenance.eligibility_observed_at` guarda o relógio da corrida
- **Markets:** binance ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT (replay); universo monitorado inteiro (prospectiva)
- **Data de início da coleta:** 2026-09-08 (prospectiva); janela de replay 2026-08-08 → 2026-09-08

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-08 — **REPLAY** (retrospectiva) — `read_at = 2026-09-08T19:11:21Z`

> **Rótulo obrigatório: REPLAY.** Esta é a **mesma janela** que gerou a hipótese ([[KB-0010]]).
> Não é evidência prospectiva e não decide ativação nenhuma sozinha.

**SQL usado:** `q10-pop.sql` e `q11-pareado.sql`, transcritos verbatim em
`.claude/state/notes-T3.40.md` §SQL.

**Cobertura (contagens completas):**

| Emitidos | Pendentes | Entradas | Não entradas | Ativos | Target | Stop | Expired | Invalidated | Censurados | Funding indisponível |
|---|---|---|---|---|---|---|---|---|---|---|
| **0** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

**O livro-razão diz por quê** (11 904 barras, 4 mercados, 31 dias, `--explain-ledger`):

| estado | n | motivo | n |
|---|---:|---|---:|
| `unavailable` | 448 | `warmup` | 448 |
| `not_triggered` | 11 456 | `no_breakout` | 10 221 |
| | | `rvol_low` | 534 |
| | | `atr_out_of_range` | **701** |
| `triggered` | **0** | `signal` | **0** |

Das 701 barras que chegaram ao porteiro de ATR (as que já passaram rompimento e volume relativo), a
distribuição de `atr_pct_15m` é: mín 0,064 %, p50 0,442 %, p90 0,926 %, p99 1,544 %,
**máx 1,756 %**. **Zero** barras ≥ 2,0 %. O mesmo se lê na população do pai: o `atr_pct` máximo
observado nas 224 decisões da `momentum v2` é **1,623 %**.

**Métricas:** todas **nulas por população vazia** — não por OHLC indeterminado. Não há `target/stop`,
não há `R_net`, não há Profit Factor. `PnL de carteira` e `Max Drawdown`: **não aplicáveis** (não há
carteira no Shadow Lab).

**Os quatro grupos pareados (método T3.26):**

| Grupo | n | avaliáveis | expectancy bruta (R) | expectancy líquida (R) | soma R |
|---|---:|---:|---:|---:|---:|
| decisões do pai **acima** do piso 0,020 | **0** | 0 | — | — | — |
| decisões do pai **abaixo** do piso (eliminadas) | **224** | 222 | +0,0820 | −0,1717 | −38,13 |
| decisões da variante **pareadas** com o pai | 0 | 0 | — | — | — |
| decisões da variante **sem par** no pai | 0 | 0 | — | — | — |

- **Dias distintos com outcome avaliável:** 0
- **Versão da métrica / proveniência:** `agent_signals` + `signal_outcomes` + `replay_runs`, coorte `replay:72cf5671-ec16-4d62-afd6-ace3f7bbf4e1`
- **Result:** **inconclusivo** (regra prospectiva; e, nesta janela, por população vazia)
- **Conclusion:** o teto de pedágio de 0,10 R **corta 100 % das decisões** desta janela nestes quatro
  mercados. A regra editorial do EXP-0006/[[KB-0008]] ("um piso que elimina 70 % dos sinais é outra
  estratégia, não a mesma com menos ruído") é ultrapassada da forma mais forte possível: não sobra
  **nenhuma** decisão para comparar. O motivo é geométrico e está medido — ETH/SOL/XRP/DOGE **não
  têm** ATR de 15 min a 2 % do preço nestes 31 dias
- **Next Action:** deixar a coorte `prospective` correr sobre o universo inteiro (onde há mercados de
  ATR% maior — o primeiro sinal saiu às 19:16:21Z, 19 min após a ativação) e **reavaliar em 30 dias**.
  **Não** promover a `paper`. Se a frequência prospectiva também for ~0, a recomendação vira
  **descartar**, e o eixo do teto de custo passa a exigir um universo de ATR alto declarado no
  desenho — o que é outro EXP

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| `atr_pct_min = 0,0089` (`momentum v4`) | 2026-09-08 13:05:13Z | primeiro passo do mesmo eixo; teto ≈ 0,15 R (a KB escreve 0,22 R — ver correção acima) | [[EXP-0006]] |
| `atr_pct_min = 0,020` (`momentum v5`) | 2026-09-08 18:57:05Z | teto ≤ 0,067 R, satisfazendo o "≤ 0,10 R" que a [[KB-0076]] item 8 nomeia | **este EXP** |

## Relacionadas

[[EXP-0006-momentum-piso-de-custo]] · [[KB-0076-por-que-perdemos-2026-09-08]] · [[KB-0008]] · [[KB-0010]] · [[Experiments Index]] · [[Strategy Backlog]]

## Fontes

`.claude/state/notes-T3.40.md` (comandos, recibos e SQL verbatim) · `replay_runs` coortes
`replay:72cf5671-ec16-4d62-afd6-ace3f7bbf4e1` e `replay:f8d8279c-1fba-42ae-95ef-202042f96c60` ·
`system_events` (`strategy_version_variant_derived`, `strategy_version_activated`,
`replay_run_finished`) · livro-razão `--explain-ledger` de 11 904 linhas.
