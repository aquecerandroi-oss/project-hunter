---
tags: [experimento, trendline, geometria, shadow-lab]
updated: 2026-09-08
status: proposto
owner: sexta-feira
exp: EXP-0016
strategy: trendline_breakout
version: v1
result: nao-iniciado
evaluable: 0
days: 0
last_eval: —
---

# EXP-0016 — rompimento e repique de linha de tendência (`trendline_breakout_v1`)

> **RASCUNHO do quant-engineer (T3.34b, 2026-09-08).** Para a Sexta-feira arquivar em
> `obsidian/05-EXPERIMENTS/EXP-0016-trendline-breakout.md` e ligar a partir de
> [[Strategy Backlog]], [[KB-0077-linhas-de-tendencia]],
> [[KB-0003-rompimento-de-canal-e-data-snooping]] e [[Experiments Index]].
> Não editei `obsidian/**`.
>
> **Nada foi rodado. Nada foi ativado. Nada foi commitado.** "Hipótese" e "Protocolo" são
> **congelados**; avaliações são **acrescentadas** abaixo, datadas. Briefs:
> `.claude/state/brief-T3.34b-trendline-breakout-strategy.md` (contrato) e
> `.claude/state/brief-T3.34b-trendline-breakout-strategy-impl.md` (decisão do porte).

## Hipótese (congelada)

Num perpétuo USDT de 15 min, o **rompimento de uma resistência descendente com pelo menos três
toques confirmados e volume relativo ≥ 1,5** tem expectancy líquida hipotética positiva; e a
**invalidação estrutural** — fechar de volta abaixo da linha rompida — corta a cauda esquerda melhor
do que a invalidação de momentum de `momentum_v1` (fechar abaixo da máxima anterior).

Segunda porta, medida em separado desde o dia um: o **repique confirmado numa suporte ascendente**
(extremo dentro de 0,25 ATR da linha, fechamento a 0,5 ATR dela) tem expectancy própria, sem
exigência de volume.

**A ressalva antes da tese, e ela é grande.** "Linha de tendência" é a figura mais desenhada e menos
medida da análise técnica, e [[KB-0003-rompimento-de-canal-e-data-snooping]] existe exatamente
porque um canal desenhado depois do fato explica qualquer gráfico. O que torna esta versão refutável
não é a figura: é que **a geometria é determinística e o corte é uma barra**
(`.claude/state/notes-T3.34.md` §2.1), então "a linha que existia às 14:15" é uma afirmação
verificável, não uma opinião de quem desenhou.

## Portão de desenho (C1–C8) — congelado

**Declaração de processo, porque ela muda como este portão deve ser lido:** o brief pedia o portão
preenchido **antes** do módulo; nesta sessão ele foi escrito **depois**, na mesma tarefa, pelo mesmo
quant que escreveu o código. É **autoavaliação**, não revisão viva — o mesmo defeito registrado na
`notes-T3.33a.md` §2 — e a revisão da Astra sobre as regras de decisão (não sobre a geometria, que
ela já revisou na T3.34) continua **pendente**.

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade da vantagem | **REVISE** | Mecanismo declarado: uma resistência descendente com três toques é um nível onde vendedores apareceram três vezes; quando ela cede **com volume**, quem estava vendendo naquele nível é forçado a recomprar. Quem está do outro lado é o vendedor do nível, que agora tem prejuízo. **Mas:** é o mesmo mecanismo do `breakout_v1` (que deu **0 decisões** em 31 d) e do `session_orb_v1` (−0,19 R), com a diferença de o nível ser inclinado em vez de horizontal. Nada nesta casa mediu que a inclinação acrescente informação, e a KB-0077 §7 lista **seis** coisas que um humano teria traçado diferente. `REVISE`, não `PASS` |
| C2 | Risco de sobreajuste | **REVISE** | **Dezoito** parâmetros de geometria congelados de uma vez (`pivot_k`, `min_swing_atr`, `tolerance_atr`, `break_atr`, `bounce_atr`, `retest_bars`, `bounce_bars`, `max_anchors`, `max_lines`, `parallel_tol`, dois baldes de deduplicação…), **nenhum medido** — todos vêm do brief da T3.34 e da prática clássica. É a versão com mais graus de liberdade já congelada aqui. O que segura o risco: (a) os valores foram escolhidos **antes** de qualquer replay, na T3.34, para desenhar figuras, não para render expectancy; (b) a faixa de varredura da tabela do brief §5 é para o **EXP**, e mexer nela é versão nova. O que não segura: com 18 botões, um resultado positivo na primeira janela vale pouco |
| C3 | Adequação da amostra | **REVISE, com número a publicar no dia um** | Não sei estimar a frequência. As figuras da T3.34 dão 4 a 9 eventos por mercado em 14 dias de 15 min (1344 barras), mas aquilo é **uma varredura retrospectiva**, não uma por barra, e a contagem por corte vivo é outra coisa. Se a frequência ficar perto disso, quatro mercados em 31 d dão ~30 decisões brutas e **K1 é risco real**. É o primeiro número que o replay tem de publicar |
| C4 | Dependência de regime | **PASS por herança declarada** | `market_regimes` só tem `UNKNOWN` no banco, então nenhuma versão desta casa sabe cortar por regime hoje ([[KB-0076]] item 6). A versão traz um substituto próprio e mensurável: **inclinação da linha** (`line_slope_per_bar`, no envelope), e o dia um tem de publicar expectancy por decil de inclinação. Se a vantagem existir só nas linhas quase horizontais, a hipótese é sobre níveis, não sobre tendências |
| C5 | Calibração das saídas | **PASS com ressalva** | Stop **estrutural** (pivô de baixa) com piso de 2 ATR e teto de 3 ATR, então a distância fica entre 2 e 3 ATR; a ~2 % de ATR% isso é 4 %–6 % do preço, **acima** do `max_stop_distance_pct` de 3 % do `paper_v1` — irrelevante aqui (`research_only`, sem carteira) e **impeditivo** se alguém quiser promover a `paper`. Está declarado, não escondido. Alvo `max(largura do canal, 2 R)`: com 2 R o equilíbrio bruto é 33,3 %, e o pedágio medido de 0,1333 R no piso de ATR o leva a ~37,8 % |
| C6 | Concentração de risco | **PASS** | `research_only`, sem carteira, sem ordens. A única carga é computacional: uma varredura completa custou 194 ms em 1344 barras na T3.34, e aqui a janela é de 96 barras por corte (medido nos testes: a suíte inteira, 32 casos com séries de 120 barras, roda em ~2 s). O `retire_after_break` **reduz** o número de linhas vivas |
| C7 | Realismo de execução | **PASS** | Custos idênticos aos das outras versões (2 + 5 + 4 bps, `max_entry_delay_s = 120`), entrada na abertura da barra seguinte pelo perfil congelado do SHADOW-LAB §3. O pedágio declarado é **0,1333 R** no piso de ATR e no risco máximo, contra 0,3333 R do `session_orb_v1`: o stop largo desta versão é caro em preço e **barato em R** |
| C8 | Qualidade da invalidação | **PASS — e é o ponto da versão** | A invalidação é a **linha projetada na barra da decisão**, um nível estrutural que uma guarda obriga a ficar estritamente entre o stop e a referência (`REJECTED / geometry_invalidation` caso contrário). Não é o stop com outro nome (fica acima dele) nem código morto (fica abaixo da referência). É o contraste direto com `momentum_v1`, cuja invalidação por máxima anterior matou 41,8 % dos desfechos da variante de alvo 3 ATR ([[EXP-0013]]) |

**Veredito do portão: `REVISE`** — 2026-09-08, quant-engineer, **autoavaliação**. Três `REVISE`
(C1, C2, C3) e nenhum `FAIL`. As três revisões pedidas, em ordem:

1. **C3 antes de tudo:** se o replay de 31 d der < 20 decisões, **K1 dispara** e a versão morre no
   dia um sem que nada de C1 ou C2 tenha sido testado. Publicar a contagem primeiro.
2. **C2:** nenhuma varredura de parâmetros nesta janela. A tabela de faixas do brief §5 existe para
   uma janela **futura**, e usá-la agora seria escolher os 18 botões olhando o resultado.
3. **C1:** a comparação que interessa não é "positiva ou negativa", é **contra o `breakout_v1`**
   (mesmo mecanismo, nível horizontal) na mesma janela e nos mesmos mercados.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key = trendline_breakout` (**família nova**, acrescentada a
  `infra/scripts/seed_reference.py`), versão `v1`, `purpose = research_only`.
  Módulo `packages/core/hunter_core/strategies/trendline_breakout_v1.py`.
- **`code_ref`:** `hunter_core.strategies.trendline_breakout_v1@sha256:7b83a1ff07946fa743d12c9d098f15b538c2e2b19f5269363203ee0671e19648`
  (fecho de 13 módulos: `aggregate, base, canonical, envelope, indicators, numeric, schema,`
  `tl_events, tl_lines, tl_pivots, tl_scan, tl_setup, trendline_breakout_v1`). Confirmar no
  `--dry-run` **antes** de escrever. Os digests das versões vivas **não se moveram**:
  `momentum_v1 …ab2e0398…`, `volume_anomaly_v1 …9b8c14ab…`, `session_orb_v1 …a4d514ad…`.
- **A geometria está dentro do fecho por construção.** Os cinco módulos `tl_*` são uma **cópia** de
  `hunter_indicators.patterns` (T3.34, `db798b8`), mantida idêntica por
  `packages/core/tests/unit/strategies/test_tl_parity.py`. Importar o pacote de pesquisa fecharia um
  ciclo de distribuição **e** deixaria a aritmética que produz as decisões **fora** do digest.
- **Timeframe de decisão / de outcome:** 15 min (fechamentos distintos, UTC) / 1 min.
- **Regra de entrada (exata), na ordem:** elegibilidade → janela de 97 barras de 15 min → janela de
  ATR (Wilder 14 × 15 m, 97 barras, `rolling_window_v1`) → varredura da geometria nas **96** últimas
  barras → evento **nesta barra** (rompimento de resistência descendente, ou repique de suporte
  ascendente; rompimento primeiro) → volume relativo ≥ 1,5 (só no rompimento) → qualidade da linha
  (`touches ≥ 3`, `violations ≤ 1` no rompimento / `≤ 2` no repique) → `0,005 ≤ ATR% ≤ 0,05`.
- **Geometria:** `stop = min(mínima do último pivô de baixa confirmado, C − 2·ATR)`;
  `risk = C − stop`; `alvo1 = C + max(largura do canal, 2·risk)`;
  `invalidação = close_below(linha projetada na barra da decisão)`; horizonte 8 h.
- **Três recusas (`REJECTED`, o mercado não re-arma):** `geometry`, `geometry_invalidation`,
  `risk_too_wide`.
- **`retire_after_break` ligado:** uma linha cujo rompimento é mais velho que a janela de reteste
  deixa de ser desenhada. É a **única regra que a cópia acrescenta** à T3.34 (correção 1 da
  KB-0077), e é por isso que existe cópia em vez de edição: as figuras da T3.34 já foram publicadas.
- **Parâmetros congelados:** 37 chaves, a tabela do brief §5 mais `mode`, os dois
  `max_violations_*` e os seis parâmetros de varredura que viajam no envelope (`pattern_params`).
- **Universo:** replay em ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT; `prospective` no universo elegível.

### A correção ao brief que virou parâmetro (declarar, não esconder)

O brief §5 propunha `max_violations = 0` no rompimento. **Zero é impossível:**
`TrendLine.violations` conta os fechamentos através da linha **até o corte**, e a linha sobrevive
deliberadamente ao próprio rompimento para que o rompimento possa ser reportado
(`notes-T3.34.md` §2.4) — a barra que rompe **é** uma violação. Com 0, a versão responderia
`line_weak` a todo rompimento que existe. O congelado é **1**, que diz o que o brief queria dizer:
*nenhuma violação antes desta barra*. Provado por teste
(`test_max_violations_zero_would_refuse_every_breakout_there_is`).

### Premissas numéricas declaradas (nenhuma medida)

Os 18 parâmetros de geometria vêm da T3.34; `target_r = 2,0` é convenção; `atr_pct_min = 0,005` é o
piso do `breakout_v1` (KB-0008); `stop_atr_max = 2,0` e `max_risk_atr = 3,0` são escolhidos pela
identidade do pedágio: `0,002 / (risco_atr · ATR%)` R dá **0,1333 R** no piso de ATR com risco de
3 ATR e **0,2 R** com risco de 2 ATR. O teto declarado desta versão é, portanto, **0,1333 R**.

## O que falsifica esta hipótese

- **K1/K2/K3/K4/K5** de `.claude/state/notes-T3.33.md` §5.1 (< 20 decisões; > 1500 decisões;
  ≥ 100 avaliáveis **e** ≥ 30 dias **e** expectancy bruta < 0; `unavailable` > 40 %; cobertura de
  `R_net` < 70 %).
- **Específico e obrigatório (brief da impl.):** se **≥ 60 %** das decisões vierem de **um modo**
  (só rompimento ou só repique) **ou** de **um mercado**, a hipótese não é "linhas de tendência", é
  aquela porta ou aquele ativo, e tem de ser **reenunciada como tal antes** de qualquer avaliação
  seguinte — reenunciar depois de ver o resultado é seleção retrospectiva
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).
- **Decomposição obrigatória no dia um:** por modo (rompimento/repique), por mercado, e por **decil
  de `line_slope_per_bar`** (o substituto de regime desta versão, C4).
- **Se a expectancy do rompimento for indistinguível da do `breakout_v1`** na mesma janela e nos
  mesmos mercados, a inclinação não fez trabalho nenhum e o que sobra é um rompimento de nível
  qualquer — hipótese diferente e já testada.

## O que o dia um tem de publicar, além do recibo padrão

O recibo padrão (barras, segundos, barras/s, contagem por estado, sinais, desfechos, erros) e:

1. **linhas válidas por barra avaliada** (média e distribuição) — é o número que diz se a geometria
   existe no dado real ou se `no_line` domina;
2. **distribuição de `touches`** das linhas que dispararam (3, 4, 5+);
3. **fração de rompimentos com reteste** dentro de `retest_bars`;
4. **taxa de `risk_too_wide`** e de `geometry_invalidation` sobre as barras que de outro modo teriam
   disparado. **Acima de 20 %**, o par (pivô estrutural, teto de risco) está errado — e isso é
   **versão nova**, não ajuste (brief §4);
5. **linhas aposentadas por barra** (`pattern_retired_lines`), para medir o efeito da única regra
   que a cópia acrescentou.

## O que este experimento **não** prova

- **Não valida a figura "linha de tendência".** Valida **uma** regra determinística de traçado, com
  18 constantes, uma das seis possíveis (KB-0077 §7 lista o que um humano faria diferente).
- **Não decide entre as duas portas.** Escolher rompimento ou repique depois de ver os dois é o data
  snooping que a regra dos 60 % existe para pegar; uma versão por porta é versão **nova**.
- **O replay de abertura não confirma nada** — a janela avaliada é a mesma que gerou a hipótese, e
  sai rotulado **REPLAY**. Serve para **matar**, não para promover.
- **Multiplicidade:** é a oitava versão aberta nesta casa.
- **A elegibilidade replayada é a de hoje**, não a da janela (PIPELINE §6c).

## Avaliações (acrescentadas, nunca reescritas)

*(nenhuma: a versão não foi ativada e nenhum replay foi rodado — T3.34b entrega só o código)*

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| `max_violations_breakout = 0` (literal do brief §5) | 2026-09-08 | recusado **antes** de rodar: a barra que rompe é ela própria uma violação, então 0 recusaria todo rompimento que existe | esta página, "A correção ao brief" |
| importar `hunter_indicators.patterns` | 2026-09-08 | recusado: ciclo de distribuição **e** geometria fora do `code_ref` | brief da impl. §0, opção A |
| `PatternScan` dentro do `MarketContext` (`base.py`) | 2026-09-08 | recusado **nesta task**: re-congelaria `momentum_v1` e `volume_anomaly_v1` e o Lab emudeceria atrás de um `/ready` verde | brief da impl. §0, opção B |
| aposentar a linha rompida **dentro** de `find_lines` | 2026-09-08 | recusado: quebraria a paridade numérica com o pacote de pesquisa. A aposentadoria é aplicada depois da seleção, e o custo (a vaga não vai para a próxima candidata) está declarado no docstring de `tl_scan.py` | `tl_scan.py`, docstring |

## Relacionadas

[[Experiments Index]] · [[Strategy Backlog]] · [[KB-0077-linhas-de-tendencia]] ·
[[KB-0003-rompimento-de-canal-e-data-snooping]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[EXP-0008-breakout-compressao-de-volatilidade]] · [[EXP-0010-session-orb-faixa-de-abertura]] ·
[[Registro de Tentativas]]

## Fontes

`.claude/state/notes-T3.34.md` · `.claude/state/notes-T3.34b.md` ·
`.claude/state/brief-T3.34b-trendline-breakout-strategy.md` ·
`.claude/state/brief-T3.34b-trendline-breakout-strategy-impl.md` ·
`.claude/state/astra-review-T3.34-trendlines.md` · `infra/scripts/seed_reference.py` ·
`infra/scripts/activate_strategy_version.py` ·
`services/strategy-worker/hunter_strategy_worker/replay/run.py`
