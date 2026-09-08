---
tags: [experimento, breakout, volatilidade, shadow-lab]
updated: 2026-09-08
status: proposto
owner: sexta-feira
exp: EXP-0008
strategy: breakout
version: v1
result: inconclusivo
evaluable: 0
days: 0
last_eval: —
---

# EXP-0008 — rompimento após compressão de volatilidade (`breakout_v1`)

> **RASCUNHO do quant-engineer (T3.33, 2026-09-08).** Escrito em `.claude/state/exp-drafts/` para a
> Sexta-feira arquivar em `obsidian/05-EXPERIMENTS/EXP-0008-breakout-compressao-de-volatilidade.md`
> e ligar a partir de [[Strategy Backlog]], [[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]],
> [[KB-0003-rompimento-de-canal-e-data-snooping]], [[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] e
> [[Experiments Index]]. Não editei `obsidian/**`.
>
> **Nada foi rodado. Nada foi ativado.** As seções "Hipótese" e "Protocolo" estão **congeladas** e
> nunca mudam; as avaliações serão **acrescentadas** abaixo, datadas. Brief de implementação:
> `.claude/state/brief-T3.33a-breakout_v1.md`.

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
   que este experimento existe para descobrir, e [[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]]
   registra que a apresentação clássica da família (Weinstein, O'Neil, Minervini) é **retrospectiva
   sobre ações que subiram muito** — viés de seleção na forma mais pura, sem grupo de controle no
   material lido.

**O nome é o que ele mede.** Isto é uma **razão de contração de mediana de TR**, não "VCP". Reduzir
um método a um indicador e conservar o nome e a evidência do método original é a armadilha que a
Astra nomeou para esta família inteira.

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
- **Entrada/saída:** o perfil congelado do SHADOW-LAB §3 — abertura da primeira barra de 1 min
  estritamente posterior a `decision_at`, `P_entry = O(1+0,0006)`, `P_exit = base(1−0,0006)`, taxa
  fora dos preços, gap na abertura antes de toques intrabar, stop antes de alvo na mesma barra.
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

## Portão C1–C8 — veredito de 2026-09-08, **antes** de escrever o módulo (T3.33a)

Critérios de `.claude/skills/edge-strategy-reviewer/references/review_criteria.md`, aplicados ao
contrato congelado acima pelo quant-engineer. Cada nota vem da tabela do arquivo, não de opinião.

| # | Critério | Severidade | Nota | Peso | Contribuição | Por quê, literal |
|---|---|---|---:|---:|---:|---|
| C1 | Edge Plausibility | pass | 80 | 20 | 16,0 | a tese tem mecanismo causal declarado ("a base comprime porque a oferta secou; a expansão resolve o desequilíbrio") e termos de domínio (`breakout`, `volume`, volatilidade) |
| C2 | Overfitting Risk | **warn** | **40** | 20 | 8,0 | 5 condições (≤ 10 → 80) **menos 10 por limiar decimal**: `0,75`, `1,5`, `0,005`, `0,05` → −40 |
| C3 | Sample Adequacy | pass | 80 | 15 | 12,0 | fórmula do arquivo: `252 × 0,8^5 = 82,6` oportunidades/ano ≥ 30. **Não é frequência medida** — a de planejamento é 0,3–1/mercado-dia (`notes-T3.33` §2) |
| C4 | Regime Dependency | **warn** | **40** | 10 | 4,0 | o plano de validação (`notes-T3.33` §5) **não** menciona regime; não há corte cruzado por regime declarado |
| C5 | Exit Calibration | pass | 80 | 10 | 8,0 | `stop_loss_pct` no teto da faixa = `1,25 × 0,05 = 0,0625 ≤ 0,15`; `take_profit_rr = 2,5/1,25 = 2,0 ≥ 1,5` |
| C6 | Risk Concentration | pass | 80 | 10 | 8,0 | não há `risk_per_trade` nesta versão (`research_only`, sem carteira, sem Risk Engine) e o limite de posições é **um acompanhamento por (versão, mercado, coorte)** — 4 mercados ≤ 10. Pontuado por ausência de violação, e isso está dito |
| C7 | Execution Realism | pass | 80 | 10 | 8,0 | há filtro de volume (`rvol_min = 1,5`); `export_ready_v1` não se aplica a este produto |
| C8 | Invalidation Quality | **warn** | **40** | 5 | 2,0 | **uma** invalidação (`close_below(base_low)`), e o critério pede duas |

`confidence_score = 66,0`. C1 e C2 não são `fail`, então não há REJECT imediato; 66,0 < 70, então o
veredito é **REVISE**.

**Veredito: REVISE.** As três revisões são **obrigações de relato na primeira avaliação**, não
mudanças no protocolo congelado — nenhuma delas altera hipótese, parâmetro ou regra de entrada:

1. **C2** — os quatro limiares decimais são exploratórios e estão declarados como tal. A primeira
   avaliação **tem** de publicar a distribuição de `squeeze_ratio` sobre barras que disparam e que
   não disparam, e a sensibilidade da faixa de ATR%, para que uma versão futura escolha um quantil
   em vez de um palpite. Já está no contrato (§ "Premissas numéricas declaradas"); a nota continua
   40 porque em v1 nenhum dos quatro foi medido.
2. **C4** — a primeira avaliação **tem** de quebrar o resultado por regime de BTC, além de mercado e
   decil de ATR%. O SQL existe (`infra/scripts/sql/research/2026-09-08-07-regime-btc.sql`, T3.32).
   Não vira condição de entrada: pôr regime na regra seria outra versão.
3. **C8** — a segunda invalidação **não** entra na v1, de propósito. [[KB-0006]] e a T3.32 mostram
   que política de saída só se compara **pareada sobre as mesmas entradas** (`brief-T3.27`,
   `INV-A/B/C/E`); acrescentar uma saída junto com uma entrada nova produziria duas mudanças e
   nenhuma atribuição. A divergência contra o critério fica registrada aqui.

## Teto de custo declarado — confere, e **não** vale no piso congelado

`notes-T3.32` fechou a identidade aritmética `custo_R × (risco/preço) = 0,0020` nas dez populações
medidas (desvio ≤ 1,9×10⁻⁵). Aplicada a esta geometria (`stop = C − 1,25·ATR`, entrada
`C(1+0,0006)`), com `a = 6 bps/lado` dentro dos preços e `f = 4 bps/lado` fora:

```
$ uv run python  (Decimal, prec 28)
breakout_v1  stop_atr=1.25 target_atr=2.5
 atr_pct  risco/preco   custo_R  R_net alvo  R_net stop  equilibrio   <=0.25R?
   0.005     0.006846    0.2921      1.5310     -1.2035      0.4401        NAO
0.0059238     0.008000    0.2500      1.5984     -1.1740      0.4235   (fronteira)
  0.0064     0.008595    0.2327      1.6260     -1.1619      0.4168        sim
    0.01     0.013092    0.1528      1.7538     -1.1059      0.3867        sim
    0.02     0.025585    0.0782      1.8730     -1.0537      0.3600        sim
    0.05     0.063062    0.0317      1.9473     -1.0212      0.3440        sim

momentum_v1  stop_atr=1.5 target_atr=1.5 (referência)
   0.003     0.005097    0.3924      0.4893     -1.2736      0.7224
 0.01401     0.021602    0.0926      0.8787     -1.0638      0.5476

atr_pct mínimo para custo_R <= 0,25 R com stop_atr=1,25: 0.00592384
atr_pct_min congelado                                  : 0.005
custo_R no piso congelado                              : 0.2921459854014598540145985401
```

Duas leituras, e a segunda é uma **concern declarada**:

- as colunas `R_net alvo`, `R_net stop` e `equilibrio` **reproduzem exatamente** a tabela de
  geometria congelada acima (1,5310 / −1,2035 / 0,4401 a ATR% 0,5 %). A aritmética do brief está
  correta e a assimetria 1,25/2,5 faz o que promete: 44,0 % de equilíbrio contra 72,2 % do
  `momentum_v1` no piso dele;
- **o teto de 25 % que a Astra propôs no contrato comum não vale no piso congelado.** "Custo nominal
  de 20 bps ≤ 25 % da distância percentual do stop" exige `atr_pct ≥ 0,0059238` com `stop_atr = 1,25`.
  Com `atr_pct_min = 0,005` o pedágio no piso é **0,2921 R**, isto é **29,2 % da distância do stop** —
  acima do teto. O piso foi escolhido pelo equilíbrio de 44,0 %, não pelo teto de custo, e as duas
  regras discordam numa faixa estreita (`0,0050 ≤ atr_pct < 0,0059`).
  **Não mudei o parâmetro**: ele está congelado no brief e mudá-lo seria outra versão. A obrigação
  que fica é de relato: a primeira avaliação publica quantas decisões caem nessa faixa e qual a
  expectancy delas, e é esse número — não este cálculo — que decide se a `v2` sobe o piso para
  0,0059/0,0064.

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
  mas são populações diferentes: o contraste pareado é o `brief-T3.27` (`INV-A/B/C/E`).
- **Multiplicidade.** É uma de quatro versões abertas no mesmo dia
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]); entra em
  [[Registro de Tentativas]] com a data de início antes da primeira barra.
- **O replay de abertura não confirma nada** — é a mesma janela que gerou a hipótese, e sai rotulado
  como **REPLAY**.
- **Mistura de slot.** Uma versão nova compete pelo mesmo "um acompanhamento por (versão, mercado,
  coorte)"; comparações com o `momentum` têm de dizer isso.

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de <primeira data> — replay de abertura

<a preencher com: coorte, janela, mercados, recibos do livro-razão, comandos exatos, contagens de
cobertura completas, métricas com denominador explícito, a decomposição por `squeeze_ratio`, o
`Result` e a `Next Action`>

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| — | — | — | — |

## Relacionadas

[[Experiments Index]] · [[Strategy Backlog]] · [[EXP-0001-momentum-v1]] ·
[[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]] ·
[[KB-0003-rompimento-de-canal-e-data-snooping]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] · [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[Registro de Tentativas]]

## Fontes

`.claude/state/notes-T3.33.md` · `.claude/state/brief-T3.33a-breakout_v1.md` ·
`infra/scripts/activate_strategy_version.py` ·
`services/strategy-worker/hunter_strategy_worker/replay/run.py`
