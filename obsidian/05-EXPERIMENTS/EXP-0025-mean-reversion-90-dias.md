---
tags: [experimento, mean-reversion, replicacao, 90-dias, custo]
updated: 2026-09-10
status: em-andamento
owner: sexta-feira
exp: EXP-0025
strategy: "mean_reversion"
version: "v1 + v2 + v10 (replay 90 dias, 16 mercados)"
result: reprovada
evaluable: 798
days: 89
last_eval: "2026-09-10"
---

# EXP-0025 — 90 dias, 16 mercados: agosto era a história inteira

> **Arquivada pela Sexta-feira em 2026-09-10 (plantão de arquivamento)** a partir de
> `.claude/state/notes-T3.62b.md` (quant-engineer, continuação da T3.62), que por sua vez completa o
> que a T3.62 (16 mercados, 31 dias) e o [[EXP-0021-timeframe|EXP-0021]] (`mean_reversion v10`, eixo
> de timeframe) tinham deixado em aberto: **a vantagem sobrevive fora da janela e do universo que a
> geraram?** Este é o primeiro `EXP-NNNN` do Lab com população suficiente para responder pela régua
> (≥ 100 avaliáveis **e** ≥ 30 dias) nas três versões, no eixo `r_ex_funding`. Nada aqui é dinheiro
> real (`ENABLE_LIVE_TRADING=false`); nenhuma versão foi ativada, promovida ou depreciada por esta
> nota — as recomendações abaixo são para o orquestrador. Medições completas, comandos e SQL
> verbatim em `.claude/state/notes-T3.62b.md`.

## Hipótese (congelada, pré-registrada no brief da T3.62b)

A [[EXP-0021-timeframe|EXP-0021]] mediu `mean_reversion v10` como `robusto` em **31 dias × 4
mercados** (T3.54): 54 decisões, líquida +0,2013 R. A T3.62 replicou isso para **16 mercados** na
mesma janela de calendário e mediu +0,1105 R líquido / PF 1,451 em 30 dias. **A pergunta
pré-registrada desta tarefa:** essa vantagem é da estratégia ou da janela de agosto–setembro? Testada
em três eixos, todos fixados **antes** de rodar:

1. `v10`, `v1` e `v2` (mesmo `code_ref`, três contrastes de parâmetro) replayadas em **90 dias × 16
   mercados**, três janelas de ~30 dias cada, para separar estratégia de calendário;
2. o funil K1–K6 congelado em `docs/plans/SHADOW-LAB.md`, incluindo **K3** (bruta < 0 com ≥ 100
   avaliáveis e ≥ 30 dias) — o critério que 31 dias nunca tinham amostra para sequer testar;
3. `--stress` sobre a coorte da `v10`, C5 (fração acima do teto de risco de 3 % do `paper_v1`) e a
   decomposição 4 mercados originais vs. 12 novos.

## Portão de desenho (C1–C8)

**Não aplicável a esta página.** As três versões (`v1`, `v2`, `v10`) já passaram pelo portão nas
páginas onde nasceram — [[EXP-0009-mean-reversion-pullback-em-tendencia|EXP-0009]] (`v1`, veredito
`REVISE`, 65,5) e [[EXP-0021-timeframe|EXP-0021]] (`v10`, herda o portão da `v6`/`v2`). Esta página
não muda parâmetro nem código; é reavaliação de população sobre o mesmo desenho.

## Protocolo (congelado — três braços, mesmo `code_ref`, parâmetro difere)

- **Strategy:** `strategies.key = mean_reversion`. Três `strategy_versions`, sufixo de `code_ref`
  idêntico (`…239dadc3f0bd395f`) — **o contraste é de parâmetro, não de código**.

| versão | `atr_pct_min` | `stop_atr` | alvos (ATR) | `atr_timeframe` / `atr_bars` |
|---|---:|---:|---:|---|
| `v1` | 0,006 | 1,0 | 1,5 / 2,5 | 15m / 97 |
| `v2` | 0,008 | 1,0 | 1,5 / 2,5 | 15m / 97 |
| `v10` | 0,008 | 1,5 | 2,25 / 3,75 | 1h / 24 |

- **Timeframe de decisão / de outcome:** 15 min (`v1`/`v2`) e 1 h (`v10`) / 1 min.
- **Custos assumidos:** spread 2 bps, slippage 5 bps/lado, taxa 4 bps/lado, `max_entry_delay_s = 120`
  — perfil congelado do Lab.
- **Cohort:** `replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3` (`v10`, 12/12 fatias), `replay:fa005985-
  0b55-4820-904c-8ada589e441c` (`v1`, 12/12), `replay:da706026-319a-451e-950e-7728ca9ae563` (`v2`,
  12/12) — cada uma 3 janelas de 30 d × 4 fatias de 4 mercados, `--workers 3`.
- **Janela:** `2026-06-12T00:00Z → 2026-09-10T00:00Z`, fronteiras de calendário
  (`2026-06-12/07-12/08-11/09-10`), fita **100 % completa** (0 minutos com buraco nos 3 recortes de
  30 dias × 16 mercados).
- **Universo:** os 16 mercados vivos do Lab (ARB BNB BTC DASH DOGE ETH LINK NEAR PROM SAHARA SOL SUI
  TAO UNI XRP ZEC), 4 fatias de 4 mercados cada (`s1`: ETH/SOL/XRP/DOGE — os 4 originais; `s2`–`s4`:
  os 12 novos).
- **Eixo primário de medição:** `r_ex_funding` (bruto menos spread e taxa, **sem** funding), não
  `r_multiple`. Forçado por `funding_rates` só existir a partir de 2026-08-08T16:00Z — ver Concern 1
  abaixo. É o mesmo eixo que `SHADOW-LAB.md` usa para definir K3.
- **Bootstrap:** blocos de **dia inteiro**, 20 000 reamostragens, semente `20260910`. Δ entre janelas
  é **não pareado** (J1/J2 e J3 não compartilham nenhum dia); Δ entre grupos de mercado é **pareado
  por dia** (compartilham o calendário).

## Concern 1 — `funding_rates` só existe desde 2026-08-08T16:00Z

O backfill de 90 dias trouxe vela, não funding. Cobertura de `R_net` (com funding): `v10` 37,59 %
(300/798), `v1` 46,59 % (253/542), `v2` 57,76 % (175/302) — **K5 dispara nas três**. Por isso o eixo
de medição é `r_ex_funding`, que tem cobertura 100 % nas três e é o eixo que a própria régua K3
define. Onde o funding é conhecido (as 300 decisões da `v10` em agosto–setembro) o arrasto medido é
**−0,0011 R** de média (mediana 0,0000) — desprezível frente ao efeito de +0,23 R/operação que a
janela de agosto produz. K5 rebaixa a confiança na precificação final; não é o que decide o veredito.

## Concern 2 — `--stress` só enxerga a janela em que há funding

O motor de estresse reprecifica a partir de `r_multiple`, então o cenário `base` da `v10` roda sobre
**n = 300**, não 798 — é a janela J3 (agosto–setembro), não os 90 dias. `1a_metade_ate_2026-07-26 →
n = 0` não significa que a estratégia não decidiu em junho/julho (decidiu 510 vezes); significa que
nenhuma daquelas decisões é reprecificável hoje. O veredito `dependente de metade` do motor está
tecnicamente certo e substantivamente vazio — o julgamento de 90 dias vem das seções §Avaliação
abaixo, não do `--stress`.

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-10 — replay de 90 dias, `as_of` ~2026-09-10T03:00Z–04:00Z (`.claude/state/notes-T3.62b.md`)

**Cobertura das 36 corridas (12 fatias por versão, 0 erros nas três):**

| versão | fatias | barras | decisões (`n`) | dias distintos | `unavailable` | K4 |
|---|---:|---:|---:|---:|---:|---:|
| `v10` | 12 | 138 240 | **798** | 89 | 1 280 (aquecimento) | 0,926 % |
| `v1` | 12 | 138 240 | **543*** | 83 | 1 280 | 0,926 % |
| `v2` | 12 | 138 240 | **303*** | 68 | 1 280 | 0,926 % |

\* a análise por decisão usa 542/302 (uma decisão de cada excluída por falta de par no dump do CSV;
diferença de 1, sem efeito no veredito). Livros-razão fecham exato: 414 720 barras = 36 × 11 520,
`barras = linhas` sem resto.

**Resultado pooled, 90 dias (eixo `r_ex_funding`, IC 95 % por bootstrap de blocos de dia):**

| versão | n | dias | bruta | pedágio p50 | **ex-funding** | PF | acerto % | IC 95 % |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `v10` | 798 | 89 | +0,0728 | 0,1034 | **−0,0293** | 0,910 | 48,6 | [−0,1336; +0,0728] |
| `v1` | 542 | 83 | +0,1270 | 0,2169 | **−0,0910** | 0,851 | 45,6 | [−0,2129; +0,0311] |
| `v2` | 302 | 68 | +0,1325 | 0,1722 | **−0,0343** | 0,940 | 46,4 | [−0,1695; +0,0999] |

**As três negativas** — checado por duas implementações independentes que concordam bit a bit
(SQL em Postgres e NumPy sobre o CSV baixado: `v10` = −0,0293 nos dois caminhos).

**As três janelas de 30 dias, a pergunta central (`v10`; `v1`/`v2` no mesmo padrão em
`notes-T3.62b.md` §5):**

| janela | n | dias | bruta | pedágio p50 | ex-funding | PF | acerto % |
|---|---:|---:|---:|---:|---:|---:|---:|
| J1 jun-12→jul-12 | 328 | 30 | −0,0156 | 0,1065 | **−0,1216** | 0,695 | 43,0 |
| J2 jul-12→ago-11 | 182 | 29 | +0,0251 | 0,1164 | **−0,0919** | 0,726 | 46,2 |
| **J3 ago-11→set-10** | 288 | 30 | +0,2037 | 0,0837 | **+0,1155** | 1,483 | 56,6 |

**Nas três versões, sem exceção: J1 negativa, J2 negativa, J3 positiva.** O Δ(J3 − J1J2), bootstrap
não pareado por blocos de dia: `v10` **+0,2265 R, IC 95 % [+0,0085; +0,4293]**; `v1` +0,2629
[+0,0328; +0,4873]; `v2` +0,3247 [+0,0706; +0,5715] — **os três IC excluem zero**. A diferença entre
a janela de agosto e as duas anteriores não é ruído amostral, nas três versões. **Ressalva
pré-registrada:** as três versões não são independentes (`v2`/`v10` compartilham `atr_pct_min`, `v1`
só afrouxa o piso) — "três de três" é um resultado visto por três lentes correlacionadas, não um
teste com p = 1/8.

**4 mercados originais vs. 12 novos, Δ pareado por dia (`v10`):** originais +0,0002 R, novos
−0,0354 R, Δ +0,0356 [−0,1056; +0,1793] — **a vantagem que a T3.62 mediu nos 4 originais encolheu
para exatamente zero** em 90 dias; não há vantagem em nenhum dos dois grupos.

**Funil K1–K6 (`docs/plans/SHADOW-LAB.md` linhas 153–162):**

| critério | `v10` | `v1` | `v2` |
|---|---|---|---|
| K1 (< 20 decisões) | 798 ✔ | 543 ✔ | 303 ✔ |
| K2 (> 1 500) | 798 ✔ | 543 ✔ | 303 ✔ |
| **K3 (≥ 100 e ≥ 30 d e bruta < 0)** | 798/89d/−0,0293 → **DISPARA** | 542/83d/−0,0910 → **DISPARA** | 302/68d/−0,0343 → **DISPARA** |
| K4 (`unavailable` > 40 %) | 0,926 % ✔ | 0,926 % ✔ | 0,926 % ✔ |
| K5 (cobertura `R_net` < 70 %) | 37,59 % ✘ | 46,59 % ✘ | 57,76 % ✘ |
| K6 (≥ 60 % num mercado) | 10,5 % ✔ | 13,1 % ✔ | 20,5 % ✔ |

**K3 dispara nas três** — é a primeira vez que a régua tem amostra para sequer testar essa cláusula
(31 dias nunca alcançavam 30 dias distintos com folga). Pela régua, K3 disparado é "deprecar ou
declarar", e K5 também disparou (rebaixa confiança, não decide sozinho).

**C5 — fração acima do teto de risco de 3 % (`v10`, `initial_risk / p_entry`, banda `paper_v1`
`[0,003; 0,03]`):** 90 dias inteiros **16,8 %** (134/798) — metade dos 32,3 % que a T3.62 media só
na janela de agosto. **C5 é propriedade de versão × regime, não só de versão**: J1 9,1 %, J2 6,0 %,
J3 32,3 % — o mesmo eixo de ATR% que produz o ganho de expectancy em agosto também estoura o teto de
risco com o dobro da frequência.

**Estresse (só alcança a janela J3, ver Concern 2):** `v10` `dependente de metade` (mas artefato,
ver Concern 2) e `custos_x2` → −0,0896 R; `v1` `frágil a custos` (−0,1482, PF 0,751); `v2` `frágil a
custos` (−0,0706, PF 0,875). Custo dobrado sobre os 90 dias, primeira ordem: `v10` −0,1313 R, `v1`
−0,3090 R, `v2` −0,2012 R — **as três frágeis a custos** por margem não discutível.

**Isolamento:** 0 linhas de `shadow_outbox`/`trade_proposals` nas 1 644 decisões; nenhuma saiu de
`research_only`.

**Dias distintos com outcome avaliável:** 89 (`v10`), 83 (`v1`), 68 (`v2`).
**Versão da métrica / proveniência:** SQL de pesquisa `2026-09-10-t362b-q*.sql` + bootstrap local
(`.claude/state/exp-drafts/t362b/blocos90.py`, 14 testes) sobre `agent_signals`/`signal_outcomes`.

- **Result: `reprovada`** nas três — população suficiente (≥ 100 avaliáveis **e** ≥ 30 dias, no eixo
  `r_ex_funding` com cobertura 100 %), K3 disparado, bruta negativa nas três, PF < 1 em duas de três.
  Este é o primeiro `EXP-NNNN` da família `mean_reversion` a sair do limiar editorial de
  `inconclusivo` por população — e sai reprovado.
- **Conclusion:** a vantagem que a [[EXP-0021-timeframe|EXP-0021]]/T3.62 mediram é a janela de
  agosto–setembro inteira, e só ela. Fora dela (jun–jul, jul–ago) as três versões perdem. Não é
  sorte: o Δ entre a janela de agosto e as duas anteriores exclui zero nas três. A vantagem nos 4
  mercados originais também não sobrevive (+0,0002 R em 90 dias). Nenhuma das três é candidata a
  linha `paper` neste desenho.
- **Next Action:** nenhuma promoção, nenhuma ativação, nenhuma depreciação automática — recomendação
  de depreciar as três fica para o orquestrador/Everton. O que sobra de valioso é a hipótese de um
  **portão de regime** que só deixe a família operar na janela em que ela funciona — isso é versão
  nova ([[EXP-0020-regime-gate]] é o precedente de desenho), medida do zero, não ajuste de parâmetro.
  Cruzar J3 com `market_regimes` (é um recorte de calendário, não de regime, nesta nota) é a próxima
  pergunta barata.

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| eixo `r_multiple` (com funding) | 2026-09-10 | recusado — cobertura 37,6–57,8 %, filtrar por ele mediria só agosto–setembro de novo | esta página, Concern 1 |
| `--stress` sobre os 90 dias inteiros | 2026-09-10 | tentado; o motor reprecifica só a partir de `r_multiple` e devolve `n = 0` fora da janela com funding — artefato, não achado | esta página, Concern 2 |
| corte por `market_regimes` em vez de calendário | — | mais barato depois desta nota; não feito aqui | próxima tarefa |

## Relacionadas

[[Experiments Index]] · [[mean_reversion]] · [[EXP-0009-mean-reversion-pullback-em-tendencia]] ·
[[EXP-0019-piso-atr]] · [[EXP-0021-timeframe]] · [[EXP-0020-regime-gate]] ·
[[KB-0076-por-que-perdemos-2026-09-08]] · [[Diario/2026-09-10]] ·
[[07-BUGS/Open Bugs|Open Bugs]] (T3.73/T3.74, achados de instrumento da mesma janela)

## Fontes

`.claude/state/notes-T3.62b.md` · `infra/scripts/sql/research/2026-09-10-t362b-q00-coorte-v10.sql` ·
`2026-09-10-t362b-q01-janela-e-cobertura.sql` · `2026-09-10-t362b-q10-populacoes-e-portas.sql` ·
`2026-09-10-t362b-q11-dump-decisoes.sql` · `2026-09-10-t362b-q12-recibos-e-isolamento.sql` ·
`.claude/state/exp-drafts/t362b/blocos90.py` + `test_blocos90.py` · `docs/plans/SHADOW-LAB.md`
(linhas 153–162, K1–K6) · `packages/risk-core/hunter_risk/limits.py:151-152` (banda `paper_v1`)
