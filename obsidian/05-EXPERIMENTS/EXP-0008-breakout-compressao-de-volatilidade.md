---
tags: [experimento, breakout, volatilidade, shadow-lab]
updated: 2026-09-08
status: proposto
owner: sexta-feira
exp: EXP-0008
strategy: breakout
version: v1
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
---

# EXP-0008 — rompimento após compressão de volatilidade (`breakout_v1`)

> **Arquivado pela Sexta-feira em 2026-09-08 (T3.32b)** a partir do rascunho do `quant-engineer`
> (T3.33, `.claude/state/exp-drafts/EXP-0008-breakout-compressao-de-volatilidade.md`).
> **Nada foi rodado. Nada foi ativado. Não existe módulo `breakout_v1.py` ainda.** As seções
> "Hipótese" e "Protocolo" estão **congeladas** e nunca mudam; as avaliações serão **acrescentadas**
> abaixo, datadas. Brief de implementação: `.claude/state/brief-T3.33a-breakout_v1.md`.
> `result: nao-iniciado` é o estado honesto enquanto não houver uma única barra avaliada.

## Hipótese (congelada)

Num perpétuo USDT de 15 minutos, um fechamento que rompe a máxima das 20 barras anteriores **e** vem
precedido de **contração de amplitude verdadeira** — a mediana do TR das últimas 8 barras contra a
mediana das 32 anteriores, **as duas terminando em `t−1`** — tem expectancy líquida hipotética maior
que zero, com stop a 1,25 ATR e alvo a 2,5 ATR da referência.

Duas afirmações separadas, e só a segunda é a hipótese:

1. **aritmética, já fechada:** a 1,25/2,5 com o custo assumido do Lab, a taxa de acerto de equilíbrio
   é **44,0 %** no piso de ATR% de 0,5 % e 38,7 % a 1 %, contra **72,2 %** da geometria simétrica
   1,5/1,5 do `momentum_v1` no piso dele ([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] e a tabela
   abaixo). Isso é geometria, não vantagem;
2. **a hipótese:** que a **contração antes do rompimento** selecione rompimentos melhores. Isso é o
   que este experimento existe para descobrir, e
   [[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]] registra que a apresentação
   clássica da família (Weinstein, O'Neil, Minervini) é **retrospectiva sobre ações que subiram
   muito** — viés de seleção na forma mais pura, sem grupo de controle no material lido.

**O nome é o que ele mede.** Isto é uma **razão de contração de mediana de TR**, não "VCP". Reduzir
um método a um indicador e conservar o nome e a evidência do método original é a armadilha que a
Astra nomeou para esta família inteira ([[Dialogos/2026-09-08-quatro-estrategias]]).

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key = breakout`, versão `v1`, `purpose = research_only`,
  `status = active` após ativação auditada por `infra/scripts/activate_strategy_version.py`.
  Módulo `packages/core/hunter_core/strategies/breakout_v1.py`.
- **`code_ref`:** digest por versão, congelado na ativação. Requisito de contrato verificado por
  teste: os digests de `momentum_v1`
  (`…@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c`) e de
  `volume_anomaly_v1` (`…@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22`)
  **não se movem** com esta entrega.
- **Timeframe de decisão / de outcome:** 15 min (fechamentos distintos, UTC) / 1 min.
- **Agregação e ATR:** 1 m → 15 m só com barras UTC contíguas e finais até `source_bar_close`;
  ATR = Wilder(14) de 15 min sobre `atr_bars = 97`, `rolling_window_v1`, seed/âncora persistidos —
  **o mesmo contrato de ATR do `momentum_v1`**, de propósito, para que as duas populações sejam
  comparáveis por volatilidade depois.
- **Regra de entrada (exata), na ordem:** elegibilidade → janela de sinal → janela de ATR →
  `squeeze_ratio = mediana(TR das 8 barras até t−1) / mediana(TR das 32 barras até t−1) ≤ 0,75` →
  `close(t) > máxima das 20 máximas anteriores` → `volume relativo ≥ 1,5` (mediana de 96 barras,
  atual excluída) → `0,005 ≤ ATR% ≤ 0,05`. A barra do rompimento **não entra** em nenhuma das duas
  janelas de contração (KB-0053, decisão de instrumento 3).
- **Geometria:** `stop = C − 1,25·ATR`, `alvo1 = C + 2,5·ATR`, alvo informativo `C + 4·ATR`.
- **Invalidação (exata):** `close_below(base_low)` em 15 min, onde `base_low` é a **mínima das 8
  barras até t−1** — a mínima da base de compressão, não o nível de rompimento. Guarda obrigatória:
  a decisão é **recusada** (`REJECTED / geometry_invalidation`) se não valer
  `stop < base_low < referência`, para que a invalidação nunca seja código morto (abaixo do stop) nem
  um stop disfarçado (acima da referência).
- **Horizonte:** 6 h (21 600 s).
- **Custos assumidos (hipóteses declaradas, não tarifas verificadas):** spread total 2 bps,
  slippage 5 bps por lado, taxa 4 bps por lado, `max_entry_delay_s = 120`.
- **Entrada/saída:** o perfil congelado do `docs/plans/SHADOW-LAB.md` §3 — abertura da primeira barra
  de 1 min estritamente posterior a `decision_at`, `P_entry = O(1+0,0006)`, `P_exit = base(1−0,0006)`,
  taxa fora dos preços, gap na abertura antes de toques intrabar, stop antes de alvo na mesma barra.
- **Parâmetros congelados:** a tabela de `.claude/state/brief-T3.33a-breakout_v1.md` §6, 20 chaves.
- **Universo:** replay de abertura em ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT; coorte `prospective` no
  universo elegível inteiro.
- **Faixas declaradas:** entrada `breakout_v1` em `packages/core/hunter_core/strategies/constraints.py`.

### Geometria — a aritmética que escolheu 1,25/2,5

`R_net = (P_exit − P_entry − f(P_entry+P_exit))/(P_entry − stop)`, `a = 6 bps/lado`, `f = 4 bps/lado`:

| geometria | ATR% | R_net no alvo | R_net no stop | acerto de equilíbrio |
|---|---:|---:|---:|---:|
| 1,5/1,5 (`momentum_v1`) | 0,003 | 0,4893 | −1,2736 | 0,7224 |
| 1,5/1,5 | 0,010 | 0,8324 | −1,0888 | 0,5667 |
| **1,25/2,5 (esta)** | 0,005 | 1,5310 | −1,2035 | **0,4401** |
| **1,25/2,5** | 0,010 | 1,7538 | −1,1059 | 0,3867 |

### Premissas numéricas declaradas (nenhuma é medida)

`squeeze_max = 0,75`, `8/32` barras e `rvol_min = 1,5` são a forma proposta pela KB-0053 com limiar
exploratório. `atr_pct_min = 0,005` é um meio-termo entre o 0,003 do `momentum_v1` e o 0,0089 da
KB-0008, escolhido pelo equilíbrio de 44,0 % da tabela acima, não por ajuste em amostra.

## Portão de desenho (C1–C8) — **pendente**

O portão de oito critérios (C1 plausibilidade da vantagem · C2 overfitting por contagem de condições
e precisão dos limiares · C3 adequação da amostra · C4 dependência de regime · C5 calibração da
saída · C6 concentração de risco (limites do preset `paper_v1`) · C7 realismo de execução
(executável em SPOT, piso de liquidez, atraso de entrada) · C8 qualidade da invalidação) é a tarefa
**T3.36** (`.claude/state/brief-T3.36-validation-gate-and-stress-pass.md`). O **método** já existe
como referência (`.claude/skills/edge-strategy-reviewer/references/review_criteria.md`); o que ainda
não existe é a **seção correspondente no [[_TEMPLATE-EXP]]**. O veredito (PASS/REVISE/REJECT) é
escrito **pelo implementador, antes do código**, e o `code-reviewer` confere que ele existe.
Enquanto ele não for escrito, esta seção fica **pendente** de propósito — deixá-la em branco
esconderia que o portão não foi aplicado, e ausência de veredito **não é** aprovação.

## O que falsifica esta hipótese

- **K1** — menos de 20 decisões no replay de 31 dias × 4 mercados: a regra não dispara; deprecar.
- **K2** — mais de 1 500 decisões: `squeeze_ratio ≤ 0,75` não é uma condição, é quase toda barra.
- **K3** — ≥ 100 avaliáveis **E** ≥ 30 dias **E** expectancy **bruta** (`r_ex_funding`) < 0: deprecar;
  não há custo a corrigir num resultado que já é negativo antes dos custos.
- **K4** — `unavailable` acima de 40 % das barras: problema de janela/gap; corrigir é **versão nova**.
- **K5** — cobertura de `R_net` abaixo de 70 %: reportar por `r_ex_funding` e declarar.
- **específico desta versão** — `REJECTED / geometry_invalidation` acima de 20 % das barras que
  disparariam: a base é mais larga que o stop e o par `(squeeze_window_bars, stop_atr)` está errado;
  corrigir é versão nova.
- **e o mais importante:** se, na população do replay, o `squeeze_ratio` não separar nada — isto é,
  se a expectancy do lado comprimido for indistinguível da do lado não comprimido sobre o **mesmo**
  conjunto de rompimentos — a hipótese morre mesmo que a expectancy total seja positiva, porque o
  positivo teria vindo da geometria, não da contração. **Esta decomposição é obrigatória na primeira
  avaliação**, no formato pareado que a [[EXP-0006-momentum-piso-de-custo]] usou.

## O que este experimento **não** prova

- **Não é um teste de política de saída.** As quatro versões da T3.33 têm invalidações diferentes,
  mas são populações diferentes: o contraste pareado é o `brief-T3.27`
  ([[EXP-0007-momentum-invalidacao-bracos-INV]], `INV-A/B/C/E`).
- **Multiplicidade.** É uma de quatro versões abertas no mesmo dia
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]); entra em
  [[Registro de Tentativas]] (T-035) com a data de início antes da primeira barra.
- **O replay de abertura não confirma nada** — é a mesma janela que gerou a hipótese, e sai rotulado
  como **REPLAY**.
- **Mistura de slot.** Uma versão nova compete pelo mesmo "um acompanhamento por (versão, mercado,
  coorte)"; comparações com o `momentum` têm de dizer isso.
- **PnL de carteira / Max Drawdown de carteira:** **não aplicável** — `research_only`, sem carteira.

## Avaliações (acrescentadas, nunca reescritas)

**Nenhuma ainda.** A primeira avaliação será acrescentada aqui, datada, depois do replay de abertura,
com: coorte, janela, mercados, recibos do livro-razão, comandos exatos, contagens de cobertura
completas, métricas com denominador explícito, a decomposição por `squeeze_ratio`, o `Result` e a
`Next Action`. Nada é preenchido antes de existir.

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| — | — | — | — |

## Relacionadas

[[Experiments Index]] · [[Strategy Backlog]] · [[EXP-0001-momentum-v1]] ·
[[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]] ·
[[KB-0003-rompimento-de-canal-e-data-snooping]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0076-por-que-perdemos-2026-09-08]] · [[Registro de Tentativas]] ·
[[Dialogos/2026-09-08-quatro-estrategias]]

## Fontes

`.claude/state/notes-T3.33.md` · `.claude/state/brief-T3.33a-breakout_v1.md` ·
`infra/scripts/activate_strategy_version.py` ·
`services/strategy-worker/hunter_strategy_worker/replay/run.py`
