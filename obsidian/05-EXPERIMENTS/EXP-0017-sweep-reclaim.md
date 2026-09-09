---
tags: [experimento, reversao, estrutura, liquidez, shadow-lab]
updated: 2026-09-08
status: em-andamento
owner: sexta-feira
exp: EXP-0017
strategy: sweep_reclaim
version: v1
result: inconclusivo
evaluable: 0
days: 0
last_eval: —
---

# EXP-0017 — comprar a perda falsa de um suporte (`sweep_reclaim_v1`)

> **Arquivado pela Sexta-feira em 2026-09-08 (T3.45/T3.45b)** a partir do rascunho do
> `quant-engineer` (`.claude/state/exp-drafts/EXP-0017-sweep-reclaim.md`, T3.45). "Hipótese",
> "Portão" e "Protocolo" vêm do rascunho **sem alteração de conteúdo** e são as seções
> **congeladas**; avaliações são **acrescentadas** abaixo, datadas.
>
> **Estado honesto:** a pré-checagem (abaixo) rodou e passou por margem estreita (57 eventos em
> 31 d × 4 mercados, 17 dias distintos, 30 % no maior mercado, cobertura 99,5 %; portão C1–C8 =
> 70,5 `REVISE`, C8 `fail` por desenho). O módulo `sweep_reclaim_v1` **foi implementado** no mesmo
> dia (commit `a9bacc6`, T3.45b: stop estrutural, porta de custo por `risk_pct_min = 0,006`, teto
> 0,3333 R, 46 testes, digests das versões vivas intactos) — **mas nenhum replay foi executado
> ainda**: não há coorte `research_only` ativa, não há avaliação de dia um. `sweep_reclaim:
> implemented, replay pending.` `status` sobe para `em-andamento` porque o código existe; `result`
> continua `inconclusivo` (nada foi medido sobre a hipótese, só sobre a população) e
> `evaluable`/`days` seguem `0` até o replay rodar. Origem: a candidata **#9** da
> `.claude/state/notes-T3.33.md` §2 ("perda falsa de suporte / recuperação"), rejeitada lá como
> *primeira suplente* por sobrepor o eixo da `mean_reversion_v1` — e chamada agora porque a quarta
> vaga vagou quando a `derivatives_v1` morreu na própria pré-checagem (T3.33d). Ligada a partir de
> [[Strategy Backlog]], [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]],
> [[KB-0076-por-que-perdemos-2026-09-08]], [[KB-0077-linhas-de-tendencia]],
> [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] e [[Experiments Index]].

## Hipótese (congelada)

Num perpétuo USDT, numa barra de 15 min cuja **mínima varre** (fura) a mínima de um **pivô de swing
confirmado** das últimas `pivot_lookback_bars` barras em pelo menos `sweep_atr` ATRs e cujo
**fechamento volta acima** daquela mínima (recuperação), com volume relativo ≥ `rvol_min`, o retorno
seguinte tem expectancy líquida hipotética maior que zero, com stop imediatamente abaixo da mínima
varrida, alvo em `target_r` múltiplos do risco e horizonte de 4 h.

**O que a hipótese é, em uma frase:** o teste de que **o estoque de stops abaixo de um suporte
visível é liquidez**, e que quem precisa daquela liquidez tem de recomprar — de modo que a varredura
que não segura (o preço fecha de volta acima do suporte) marca o fim do desequilíbrio, não o começo
de um.

**Por que ela não é a `mean_reversion_v1` com outro nome** — a objeção que a rejeitou na T3.33 e que
esta versão tem de responder. A `mean_reversion_v1` mede **distância à média** (z-score ≤ −1 dentro
de tendência de alta de 1 h): o gatilho dela é estatístico e o stop é uma convenção (1,0 ATR do
fechamento). Esta mede **estrutura**: o gatilho é um nível que existia antes e que foi perdido e
retomado dentro da mesma barra, e o **stop é o próprio dado** (a mínima da varredura), não uma
escolha. Duas consequências práticas separam as populações: (i) esta versão **não** exige tendência
de alta em 1 h — ela dispara em fundo de queda, que é exatamente onde a `mean_reversion_v1` se
recusa a olhar; (ii) esta versão exige um **pivô confirmado**, isto é, uma estrutura com no mínimo
sete barras de idade, e a `mean_reversion_v1` não conhece o conceito. Se as duas populações se
sobrepuserem mesmo assim, isso é medição do dia um (o EXP obriga a publicar a interseção por
`(mercado, barra)` contra a coorte da `mean_reversion`), não argumento de página.

**A divergência com o desenho das quatro anteriores, declarada.** Todas as versões vivas põem uma
**faixa de ATR%** (`atr_pct_min`/`atr_pct_max`) como porta de custo. Esta **não tem faixa de ATR%**.
O motivo é a lição medida da T3.40: a `momentum v5` congelou `atr_pct_min = 0,020` para impor um teto
de pedágio de 0,10 R e **decidiu zero vezes** em 31 dias × 4 mercados, porque o ATR% máximo observado
nesses mercados é **1,62 %**. O ATR% é um *proxy* do que interessa; o que interessa é a **distância
até o stop em fração do preço**, e é ela que entra na identidade do pedágio
(`custo_R = 0,0020 / risco%`, KB-0076 com a correção aritmética da notes-T3.40 §8b). Como aqui o stop
é **estrutural** — vem do dado, não de um múltiplo fixo do ATR —, `risco%` é observável na barra da
decisão e pode ser exigido **diretamente**. Esta versão troca a porta-proxy por uma porta exata:
`risk_pct_min`. É a única inovação de desenho do rascunho, e ela é falsificável na pré-checagem: se
a distribuição de `risco%` das varreduras estiver quase toda abaixo do piso, é o piso que mata a
candidata, e isso ficará escrito.

**O que a hipótese não é.** Não é "suporte funciona". Não é análise de Wyckoff (a *spring* clássica
exige contexto de acumulação, volume relativo *baixo* na perna final e teste posterior — nada disso
está aqui). Não é caça a stops **medida**: não vemos livro, nem liquidações, nem fluxo agressor
(`StrategyContext` tem OHLCV e mais nada — notes-T3.33 §1.2), então o mecanismo é **inferido pela
forma da barra**, e a versão não pode distinguir "stops varridos" de "uma venda grande que acabou".

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key = sweep_reclaim` (**família nova** no catálogo de referência),
  versão `v1`, `purpose = research_only`.
  Módulo `packages/core/hunter_core/strategies/sweep_reclaim_v1.py`.
- **`code_ref`:** digest por versão. Os digests das versões vivas **não se movem** com esta entrega:
  `momentum_v1` (`…ab2e0398…`), `volume_anomaly_v1` (`…9b8c14ab…`), `breakout_v1` (`…4c920b0c…`),
  `mean_reversion_v1` (`…a970c9d9…`). É teste de aceite, não expectativa.
- **O que o módulo importa, e só:** `aggregate`, `base`, `envelope`, `indicators`, `numeric`,
  `schema` — os mesmos irmãos da `mean_reversion_v1`. **Não** importa `tl_pivots`/`tl_scan`
  (o fecho da `trendline_breakout_v1`): a detecção de pivô desta versão mora **dentro do módulo**,
  pelo motivo da notes-T3.33 §1.1 (editar um irmão re-congela toda versão que o importa).
- **O que ela lê:** `ctx.candles_1m` e `ctx.source_bar_close`. **Nada de derivativos, livro, spot,
  regime ou score** — nenhum deles está no contexto.
- **Timeframe de decisão / de outcome:** 15 min (fechamentos distintos, UTC) / 1 min.
- **Escala:** ATR de Wilder(14) sobre 97 barras de 15 min (`wilder_v1` + `rolling_window_v1`), **uma
  leitura por barra de decisão**, e é ela que escala proeminência, varredura, stop e risco.
  **Divergência declarada contra `patterns/pivots.py` (T3.34):** lá cada pivô é escalado pelo ATR
  **da própria barra do pivô**; aqui há uma escala só, a da decisão. Uma escala por barra exigiria
  série de ATR dentro do módulo (~40 recomputações de 97 barras por avaliação) e mudaria o custo por
  barra do Lab inteiro. A diferença morde quando o ATR se move muito em 40 barras, e o efeito é
  simétrico (pivôs de um período mais calmo ficam **mais fáceis** de passar na proeminência quando a
  volatilidade sobe, e vice-versa). É convenção, não medição.
- **Regra de entrada (exata), na ordem dos motivos** — e a ordem é parte do contrato:
  1. elegibilidade (`ctx.eligible`);
  2. janela de sinal de 15 min disponível (`pivot_lookback_bars + pivot_k + 1 = 44` barras);
  3. janela de ATR disponível (97 barras de 15 min) e ATR aquecido;
  4. **pivô**: existe um pivô de mínima **confirmado** (k = 3: `low` estritamente menor que as 3
     lows à esquerda e ≤ as 3 à direita, empate para a barra mais velha) com índice em
     `[t − pivot_lookback_bars, t − pivot_k]` e proeminência ≥ `min_swing_atr` ATRs. O mais
     **recente** que satisfizer isso é o escolhido — um só, sempre;
  5. **varredura**: `low_t ≤ pivo_low − sweep_atr × ATR`;
  6. **recuperação**: `close_t > pivo_low`;
  7. **volume**: `rvol = volume_t / mediana(volume das rvol_window barras anteriores) ≥ rvol_min`;
  8. **piso de custo**: `risco% = (close_t − stop) / close_t ≥ risk_pct_min`;
  9. **teto de risco**: `risco_atr = (close_t − stop) / ATR ≤ risk_atr_max`;
  10. **guarda de geometria**: `0 < stop < close_t < alvo1`.
- **Geometria:** `stop = low_t − stop_buffer_atr × ATR`; `risco = close_t − stop`;
  `alvo1 = close_t + target_r × risco`; alvo informativo `close_t + target2_r × risco`.
  **O alvo é em R, não em ATR** — é a lição congelada da `session_orb_v1` (notes-T3.33 §4, item 3):
  com stop dado pelo dado, alvo fixo em ATR são duas estratégias com um nome só.
- **Invalidação (exata): NENHUMA.** Argumentada abaixo, e é uma escolha, não um esquecimento.
- **Horizonte:** 4 h (14 400 s) = 16 barras de decisão.
- **Custos assumidos:** spread total 2 bps, slippage 5 bps/lado, taxa 4 bps/lado,
  `max_entry_delay_s = 120`. Entrada/saída pelo perfil congelado do SHADOW-LAB §3.
- **Universo:** replay de abertura em ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT; `prospective` no universo
  elegível inteiro.

### Parâmetros congelados (20 chaves em `default_parameters`, mais o timeframe de decisão)

| chave | valor | por quê este valor |
|---|---:|---|
| *(timeframe de decisão)* | `15m` | **atributo de classe (`Strategy.timeframe`), não parâmetro**, como nas outras três. O mesmo quarto de hora: é o menor passo em que o custo de 20 bps não domina |
| `pivot_k` | `3` | o `k` da T3.34; confirmação em `index + 3`, e é o que impede que a decisão dependa do futuro |
| `min_swing_atr` | `1` | o padrão de `find_pivots`; sem ele todo tremor de uma fita quieta vira "suporte" |
| `pivot_lookback_bars` | `40` | 10 h de 15 min. Cabe folgado nos 1 560 min de `SHADOW_CONTEXT_MINUTES` e é o alcance em que um nível ainda é lembrado |
| `sweep_atr` | `0,25` | a varredura tem de ser visível **e** pequena; um quarto de ATR é penetração, não colapso. Convenção declarada |
| `rvol_window` | `20` | 5 h de mediana, o mesmo tamanho de janela que a `momentum_v1` usa |
| `rvol_min` | `1,5` | convenção declarada; é o valor que a `momentum_v1` e a `breakout_v1` já congelaram, e mantê-lo evita inventar um eixo novo |
| `atr_period` | `14` | Wilder |
| `atr_timeframe` | `15m` | a mesma barra da decisão |
| `atr_bars` | `97` | `rolling_window_v1`: 82 passos de suavização derrubam o peso da semente a ~0,23 % |
| `stop_buffer_atr` | `0,10` | o stop **abaixo** da mínima varrida, não nela: um stop no tick exato do extremo é varrido pela mesma mecânica que a tese descreve |
| `risk_pct_min` | `0,006` | **a porta de custo, e o número mais importante do contrato**: fixa o teto de pedágio em `0,0020/0,006 = 0,3333 R` — o mesmo teto que a `mean_reversion_v1` tem no piso dela |
| `risk_atr_max` | `3` | recusa a varredura de um pivô longe demais; o stop existe para ser tocado, não para ser decorativo |
| `target_r` | `2` | equilíbrio 44,5 % no piso de custo (tabela abaixo) |
| `target2_r` | `3` | informativo |
| `horizon_s` | `14400` | 4 h = 16 barras |
| `base_confidence` | `0,5` | constante não calibrada, como nas outras |
| `assumed_spread_bps` | `2` | SHADOW-LAB §3 |
| `slippage_bps` | `5` | SHADOW-LAB §3 |
| `fee_bps` | `4` | SHADOW-LAB §3 |
| `max_entry_delay_s` | `120` | SHADOW-LAB §3 |

### Geometria — a aritmética que escolheu o alvo, e o teto de pedágio

Com `a = 6 bps/lado` dentro dos preços e `f = 4 bps/lado` fora deles, `stop = C(1 − risco%)`,
`alvo = C(1 + target_r × risco%)`, entrada na abertura seguinte igual à referência (melhor caso),
reproduzido em `Decimal` nesta tarefa:

| `risco_atr` | ATR% | `risco%` | R_net no alvo (2R) | R_net no stop | acerto de equilíbrio | **pedágio** |
|---:|---:|---:|---:|---:|---:|---:|
| 0,6 | 0,003 | 0,180 % | 0,6652 | −1,5826 | **0,7041** | 1,1111 R |
| 1,0 | 0,004 | 0,400 % | 1,3026 | −1,3035 | 0,5002 | 0,5000 R |
| **1,0** | **0,006** | **0,600 %** | **1,5133** | **−1,2112** | **0,4446** | **0,3333 R** |
| 1,2 | 0,006 | 0,720 % | 1,5879 | −1,1786 | 0,4260 | 0,2778 R |
| 1,5 | 0,006 | 0,900 % | 1,6648 | −1,1449 | 0,4075 | 0,2222 R |
| 2,0 | 0,010 | 2,000 % | 1,8427 | −1,0670 | 0,3667 | 0,1000 R |
| 3,0 | 0,016 | 4,800 % | 1,9322 | −1,0278 | 0,3472 | 0,0417 R |

A linha em negrito é o **pior caso admitido** pelo contrato: `risk_pct_min = 0,006` recusa tudo o que
está acima dela na tabela. A primeira linha é o que a porta existe para impedir — **1,11 R de pedágio
por operação**, isto é, a operação inteira paga custo antes de o mercado opinar.

O alvo, no piso: `1,5R → equilíbrio 53,4 %`, `2R → 44,5 %`, `3R → 33,3 %`. Escolhi **2R**: 3R pede
uma perna de 1,2 % de preço em 4 h, que é meio ATR diário destes mercados, e a `momentum v6` (T3.40,
alvo 3 ATR) já está medindo o eixo "alvo mais longe" com contraste pareado — repetir o mesmo eixo
aqui seria gastar duas execuções na mesma pergunta ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]).

**Teto de pedágio, comparado (identidade `custo_R = 0,0020 / risco%`, KB-0076 corrigida pela T3.40):**

| versão | `risco%` no piso | teto de pedágio |
|---|---:|---:|
| `momentum v5` (T3.40 V1) | 3,000 % | 0,0667 R — **e zero decisões** |
| `breakout_v1` | 0,750 % | 0,2667 R |
| **`sweep_reclaim_v1`** | **0,600 %** | **0,3333 R** |
| `mean_reversion_v1` | 0,600 % | 0,3333 R |
| `momentum_v1` | 0,450 % | 0,4444 R |

O ponto que separa esta versão da `momentum v5`: as duas impõem teto de pedágio, e só esta o impõe
**sobre a grandeza que aparece na identidade**. A v5 impôs sobre o ATR% e matou a população inteira
porque nenhuma barra dos quatro mercados chega a 2 % de ATR; esta impõe sobre `risco%`, que é
`risco_atr × ATR%` — e `risco_atr` numa varredura é ~1 a 2, não 1,5 fixo. Se ainda assim a população
sumir, a pré-checagem dirá, e o número dela é `mais_piso_risco` contra `recuperaram`.

### Por que **nenhuma invalidação** — o argumento que a KB-0006 exige

A tese é que o preço acabou de recusar um nível: a mínima da varredura **é** a estrutura, e ela já
está no stop. Uma invalidação por fechamento abaixo de qualquer coisa acima do stop seria um segundo
stop, mais apertado e sem tese própria — exatamente o desenho que custou ≈ **−53 R** em 82 decisões
da `momentum v2` (notes-T3.33 §4). Esta versão é, portanto, o terceiro braço `INV-B` do Lab (sem
invalidação), ao lado de `mean_reversion_v1` e `session_orb_v1`, e a contribuição dela para aquele
experimento pareado é **observacional e confundida** — populações diferentes, entradas diferentes.
Está dito aqui porque a KB-0006 obriga a dizer, e porque o C8 do portão vai reprovar por isso.

## O que falsifica esta hipótese

- **Pré-checagem, antes de escrever o módulo** (`infra/scripts/sql/research/2026-09-09-sweep-reclaim-precheck.sql`,
  com as regras de morte P1–P4 escritas no cabeçalho **antes** de a consulta rodar):
  **menos de 20 eventos** sob a regra congelada inteira em 31 dias × 4 mercados → **não escrever o
  módulo**. Mais de 1 500 → não é condição, é relógio. Cobertura de barras de 15 min < 90 % → é bug
  de dado, não resultado.
- **Critérios de morte do dia um (replay de 31 dias × 4 mercados)**, herdados da notes-T3.33 §5.1,
  com um sexto que o brief da T3.45 acrescenta:

| # | Leitura | Decisão |
|---|---|---|
| K1 | < 20 decisões | ausência de população: **deprecar**. Mais 30 dias não a criam |
| K2 | > 1 500 decisões | é um relógio, não uma condição: deprecar ou re-especificar como versão nova |
| K3 | ≥ 100 avaliáveis **E** ≥ 30 dias distintos **E** expectancy **bruta** (`r_ex_funding`) < 0 | **deprecar**: perde antes do custo, e nenhum piso salva |
| K4 | `unavailable` > 40 % das barras | problema de janela/gap; corrigir a janela é versão nova |
| K5 | cobertura de `R_net` < 70 % | reportar por `r_ex_funding` e **declarar**; não mata, rebaixa |
| **K6** | **≥ 60 % das decisões vindas de um único mercado** | não mata; **proíbe** qualquer leitura agregada sem a decomposição por mercado ao lado, e o EXP tem de publicá-la |
| específico | `REJECTED / geometry` acima de 20 % das barras que passariam pelas portas 4–7 | o par `(sweep_atr, risk_pct_min, risk_atr_max)` está errado, e **corrigir é versão nova** — é literalmente o que matou a `breakout_v1` (14/14 rejeições, notes-T3.33e) |

- **Obrigação de regime (o que faltou na `derivatives_v1`, C4 = 40):** a primeira avaliação publica
  a decomposição por **regime de BTC** e por **decil de ATR%** na decisão. Sem isso, "funcionou" só
  descreve agosto de 2026.
- **Grupo de controle obrigatório.** Sobre as mesmas barras e mercados, comparar as decisões contra
  as barras em que **todas as outras condições valeram e só a recuperação não** (varreu e fechou
  **abaixo** do pivô). Esse é o par certo: isola a recuperação, que é a hipótese, do resto do
  gatilho. E, em separado, a interseção por `(mercado, barra)` com a coorte da `mean_reversion_v1`,
  que é a objeção de sobreposição que a T3.33 levantou.
- **Refutação limitada ao que ela pode negar:** ausência de separação entre os dois grupos, dentro de
  uma margem declarada antes, refuta **esta especificação** (este `sweep_atr`, este piso de custo,
  este horizonte) — não a ideia de que stops abaixo de suporte são liquidez.

## O que este experimento **não** prova

- **Não mede caça a stops.** Mede a **forma da barra**. Sem livro, sem liquidações e sem fluxo
  agressor no contexto, "varredura" é uma inferência sobre OHLC.
- **Não é a *spring* de Wyckoff**, que exige contexto de acumulação e um teste posterior com volume
  menor. O `rvol_min ≥ 1,5` desta versão é, na verdade, o **oposto** de uma parte da leitura clássica
  (que quer volume baixo na perna final) — divergência declarada contra a fonte que inspirou a ideia.
- **Multiplicidade.** É a quinta versão de pesquisa aberta na mesma semana ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]); a régua de
  maturidade (100 avaliáveis **E** 30 dias) e a proibição de ler o replay como confirmação valem
  inteiras.
- **O replay de abertura não confirma nada** — sai rotulado **REPLAY**, sobre a mesma janela que
  gerou a ideia.
- **O universo do replay é o de hoje**, não o de agosto (PIPELINE §6c).

## Portão C1–C8 (`edge-strategy-reviewer`) — aplicado em 2026-09-08, antes do módulo

Aplicado ao rascunho como ele está acima, com a fórmula de
`.claude/skills/edge-strategy-reviewer/references/review_criteria.md`. **Autoavaliação** — a mesma
ressalva que a revisão da T3.33a/b já registrou.

| # | Critério (peso) | Leitura sobre este EXP | Sev. | Nota |
|---|---|---|---|---|
| C1 | Edge Plausibility (20) | mecanismo causal nomeado e não genérico (estoque de stops como liquidez; quem varre precisa recomprar); termos de domínio presentes (`reversion`, `breakout`, `volume`) | pass | 80 |
| C2 | Overfitting Risk (20) | 6 condições de entrada (pivô+proeminência, varredura, recuperação, RVOL, piso de risco, teto de risco) + 0 filtro de tendência = 6 ≤ 10 → 80; penalidade −10 por limiar com casa decimal **nas condições**: `0,25`, `1,5`, `0,006` → −30 | **warn** | **50** |
| C3 | Sample Adequacy (15) | 252 × 0,8⁶ ≈ 66/ano ≥ 30 → 80. **Vale o mesmo aviso da EXP-0011:** a fórmula é de barra diária em ações e não sabe nada do nosso dado — quem responde é a pré-checagem, ao lado | pass | 80 |
| C4 | Regime Dependency (10) | o plano de validação **menciona regime** (decomposição por regime de BTC obrigatória na primeira avaliação) — a correção que a `derivatives_v1` só prometeu | pass | 80 |
| C5 | Exit Calibration (10) | `stop_loss_pct` no pior caso = `risk_atr_max × ATR%_máximo`. Escrevi 3 × 1,62 % ≈ 0,049 com o número da T3.40; a pré-checagem mediu **3,59 %** de ATR% máximo (XRPUSDT), então o pior caso real é **0,108** — ainda ≤ 0,15, mas com 28 % de folga, não 67 %. `take_profit_rr = target_r = 2,0` ≥ 1,5 | pass | 80 |
| C6 | Risk Concentration (10) | não aplicável por construção (`research_only`, sem carteira); o perfil que existiria é `PAPER_V1`: `risk_per_trade_pct = 0,0025 ≤ 0,015`, `max_concurrent_positions = 5 ≤ 10` | pass | 80 |
| C7 | Execution Realism (10) | **há filtro de volume** (`rvol_min = 1,5`); `export_ready_v1` não se aplica | pass | 80 |
| C8 | Invalidation Quality (5) | `invalidations = ()` — vazio | **fail** | 10 |

`confidence_score = (80·20 + 50·20 + 80·15 + 80·10 + 80·10 + 80·10 + 80·10 + 10·5)/100 =` **70,5**.

**Veredito: `REVISE`.** Não é `REJECT` (C1 e C2 não são `fail`, e 70,5 ≥ 35); **não é `PASS` apesar
de 70,5 ≥ 70**, porque existe um `fail` (C8) e a regra 3 exige "score ≥ 70 **e** nenhum `fail`". As
instruções de revisão, e o que foi feito com cada uma:

1. **C8 — sem invalidação. Recusada, e é o desenho.** O argumento inteiro está na seção
   "Por que nenhuma invalidação" acima; resumido: a estrutura já está no stop, e um segundo stop mais
   apertado é o desenho que custou −53 R à `momentum v2`. **Divergência declarada, não conserto.**
   Sem esse `fail` o escore seria 74,0 e o veredito `PASS`.
2. **C2 — três limiares com casa decimal.** Aceita como custo, não corrigida: `0,25` e `1,5` são
   convenções herdadas de versões existentes (não ajustadas a esta amostra) e `0,006` é a porta de
   custo, derivada da identidade do pedágio, não da série. Arredondá-los para inteiros para agradar
   ao portão seria ajustar o contrato à régua.
3. **Limite do próprio portão, declarado outra vez:** C3 devolve "amostra adequada" sem olhar em
   nenhum dado nosso. Na `derivatives_v1` ele devolveu 80 e a população **não existia**. É por isso
   que a pré-checagem abaixo é o portão que decide, e o C1–C8 é só a higiene da forma. Aqui a
   pré-checagem mediu **57 eventos em 31 dias × 4 mercados** — a fórmula do C3 estimou ~66/ano por
   mercado e a medida dá ~14/ano por mercado, isto é, o C3 **errou por 4×**, agora com número ao
   lado. Mesmo padrão, mercado diferente.
4. **Correção de contagem que a própria pré-checagem impôs ao C2:** medido, o pivô confirmado existe
   em **99,46 %** das barras e o `risk_atr_max` recusou **1** evento em 31 dias. As condições
   **ativas** são 5 (varredura, recuperação, RVOL, piso de custo, e o pivô só nominalmente), não 6.
   Isso não muda o C2 (5 ou 6 estão ambos ≤ 10, e a penalidade dos três decimais é a mesma), e está
   escrito porque um portão que conta condições merece saber quais delas **fazem** alguma coisa.

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-08 — pré-checagem sobre 31 dias × 4 mercados

Consulta **somente-leitura** na VPS (`hunter-postgres-1`, transação `repeatable read read only`),
janela `2026-08-08 ≤ open_time < 2026-09-08`, SQL literal em
`infra/scripts/sql/research/2026-09-09-sweep-reclaim-precheck.sql` com **P1–P4 escritas antes de
rodar**. Nenhuma escrita, nenhuma coorte, nenhum container tocado, nenhum replay executado.

`read_at = 2026-09-08 21:59:07.337335+00`.

**Q1 — cobertura de barras de 15 min e a distribuição de ATR% de Wilder (o CONCERN 2 da T3.33d,
aberto desde então, fechado aqui):**

```
  symbol  | barras_15m | pct_da_janela | com_atr | atr_pct_p10 | atr_pct_p50 | atr_pct_p90 | atr_pct_max | pct_atr_ge_0006 | pct_atr_ge_0003
----------+------------+---------------+---------+-------------+-------------+-------------+-------------+-----------------+-----------------
 DOGEUSDT |       2961 |         99.50 |    2865 |    0.001737 |    0.004368 |    0.008536 |    0.035645 |           28.55 |           65.20
 ETHUSDT  |       2961 |         99.50 |    2865 |    0.001253 |    0.003091 |    0.006122 |    0.013310 |           10.68 |           51.52
 SOLUSDT  |       2961 |         99.50 |    2865 |    0.001995 |    0.004021 |    0.007686 |    0.025002 |           23.80 |           64.64
 XRPUSDT  |       2961 |         99.50 |    2865 |    0.001770 |    0.004139 |    0.010527 |    0.035930 |           32.88 |           63.00
```

**P4 não dispara** (99,50 % de cobertura nos quatro). E há um segundo achado de qualidade de dado,
melhor do que eu esperava: `com_atr = 2 865 = 2 961 − 96` **nos quatro mercados**, e 96 é exatamente
o aquecimento da janela de 97 barras — ou seja, **zero** janelas perdidas por buraco interno. As 15
barras que faltam nos 31 dias estão numa borda, não espalhadas. Consequência para o dia um: `gap` e
`atr_gap` devem sair perto de zero, e K4 (40 %) não deve nem chegar perto.

E o aviso que a T3.33d deixou aberto como
**estimativa** vira **medição**: um `atr_pct_min = 0,006` recusa **67 % a 89 %** das barras destes
mercados (ETHUSDT: só **10,68 %** chegam lá; XRPUSDT, o mais volátil, 32,88 %). Até o piso de 0,003
da `momentum_v1` recusa **35 % a 48 %**. O piso que `breakout_v1` e `mean_reversion_v1` congelaram
morde muito mais do que se sabia quando foi congelado — e é a razão medida de esta versão **não** ter
faixa de ATR%. *(A T3.33d mediu `(high−low)/close` e avisou que o ATR de Wilder passaria menos vezes;
o sinal do aviso estava certo, e agora há o número.)*

**Q2 — o funil da regra congelada, porta a porta:**

```
  symbol  | barras_avaliaveis | com_pivo | varreram | recuperaram | mais_rvol | mais_piso_risco | eventos | dias_com_evento | pos_barreira_lb
----------+-------------------+----------+----------+-------------+-----------+-----------------+---------+-----------------+-----------------
 DOGEUSDT |              2865 |     2851 |      387 |          80 |        35 |              15 |      15 |              11 |              12
 ETHUSDT  |              2865 |     2856 |      378 |          93 |        52 |               9 |       9 |               8 |               9
 SOLUSDT  |              2865 |     2855 |      425 |         102 |        46 |              16 |      16 |               7 |              10
 XRPUSDT  |              2865 |     2836 |      420 |          93 |        44 |              18 |      17 |              10 |              12
 ZTOTAL   |             11460 |    11398 |     1610 |         368 |       177 |              58 |      57 |              17 |              43
```

**Nenhuma regra de morte disparou:**

| regra | limiar | leitura | disparou? |
|---|---|---|---|
| P1 | < 20 eventos | **57** (43 depois da barreira de re-arme, limite inferior) | **não** |
| P2 | > 1 500 eventos | 57 | não |
| P3 | ≥ 60 % de um mercado | **29,8 %** (XRPUSDT, 17 de 57); os quatro entre 9 e 17 | não |
| P4 | cobertura < 90 % | 99,50 % | não |

**O módulo pode ser escrito.** Brief de implementação: `.claude/state/brief-T3.45b-sweep_reclaim_v1.md`.
E o que o funil diz, incluindo o que ele diz **contra** o rascunho:

- **cadência: 57 eventos / (31 dias × 4 mercados) = 0,46 por mercado-semana**, ou 0,046 por
  mercado-dia. A estimativa da T3.33 §2 para esta candidata era **~0,3 por mercado-dia** — **errou
  por um fator de ~6**, e a leitura honesta é que a estimativa de frequência daquela tabela não vale
  nada sem consulta. Sobrevive a K1 com margem de **2,85×** (2,15× se a barreira morder tudo o que
  pode), não com folga;
- **`dias_com_evento` = 17 de 31.** Isto é o achado mais importante da pré-checagem e ele **não mata,
  mas condena o dia um a `inconclusivo` por construção**: a régua de maturidade exige **100
  avaliáveis E 30 dias distintos**, e não existem 30 dias distintos na janela para esta regra. O
  replay de 31 dias serve para K1, K2, K4, K6 e para a guarda de geometria — **não** para concluir
  nada. Quem pode amadurecer esta versão é a coorte prospectiva, e só ela;
- **a porta do pivô não é uma porta:** 11 398 de 11 460 barras (**99,46 %**) têm um pivô confirmado
  nas 40 barras anteriores. Com `k = 3`, proeminência de 1 ATR e 10 h de alcance, *quase sempre* há
  um suporte recente. O portão C2 contou 6 condições; honestamente são **5 ativas**;
- **a porta que a hipótese depende é a recuperação, e ela corta bem:** das 1 610 varreduras, só
  **368 (22,9 %)** fecham de volta acima do pivô. O grupo de controle pré-registrado ("varreu, não
  recuperou, com RVOL") tem **732 barras** — 12,8× o grupo tratado, contraste largo e barato;
- **a porta que mais corta é a de custo, e não era esse o plano:** RVOL leva 368 → 177 e o piso de
  `risco%` leva 177 → **58** (**corte de 67 %**). O `risk_atr_max = 3` recusou **exatamente 1**
  evento em 31 dias: é guarda, não condição;
- **o teto de risco e o piso juntos ainda são a melhor porta de custo que testamos**, e a comparação
  com a T3.40 continua valendo: o `atr_pct_min = 0,020` da `momentum v5` cortou **100 %**; este piso
  corta 67 % e deixa uma população viva. Mas "melhor que a que matou tudo" é uma régua baixa, e o
  número que importa está na Q3.

**Q3 — onde cai a porta de custo (distribuição de risco), e é aqui que o desenho leva o soco:**

```
              estagio             |  n   | risco_pct_p10 | risco_pct_p50 | risco_pct_p90 | risco_atr_p10 | risco_atr_p50 | risco_atr_p90 | pct_no_piso | pedagio_mediano_r
----------------------------------+------+---------------+---------------+---------------+---------------+---------------+---------------+-------------+-------------------
 A varreu                         | 1610 |       0.00063 |       0.00228 |       0.00744 |         0.213 |         0.640 |         1.356 |        15.4 |            0.8764
 B varreu+recuperou               |  368 |       0.00143 |       0.00372 |       0.01005 |         0.602 |         1.026 |         1.585 |        27.2 |            0.5381
 C varreu+recuperou+rvol          |  177 |       0.00159 |       0.00398 |       0.01210 |         0.722 |         1.206 |         1.984 |        32.8 |            0.5026
 D controle: varreu, NAO recuperou|  732 |       0.00065 |       0.00244 |       0.00752 |         0.215 |         0.659 |         1.445 |        17.1 |            0.8199
```

- **a varredura mediana é uma operação inviável a este custo.** No estágio C, o `risco%` mediano é
  **0,398 %**, que dá **0,50 R de pedágio por operação**. Só **32,8 %** das varreduras recuperadas
  com volume chegam ao piso de 0,6 %. Ou seja: a porta de custo desta versão não é um detalhe de
  parametrização — **ela é a estratégia**, e as 57 decisões que sobram são a minoria cara o bastante
  para pagar o pedágio;
- **`risco_atr` mediano de 1,206 no estágio C** confirma a aritmética que desenhou o contrato (eu
  supus "~1 a 2 ATR"): a linha 1,0/0,006 da tabela de geometria é o pior caso admitido, e o caso
  típico admitido é melhor que ela;
- **a recuperação já seleciona risco maior** (0,372 % contra 0,244 % do controle). Isso é mecânico —
  fechar acima do pivô depois de furá-lo obriga o fechamento a estar longe da mínima — e é uma
  **confusão declarada**: o grupo tratado e o de controle **não** têm a mesma geometria, então
  qualquer diferença de `R` entre eles mistura "a recuperação prevê" com "o risco é outro". O dia um
  tem de comparar **R normalizado**, e mesmo assim com a ressalva escrita.

**Q4 — sensibilidade DIAGNÓSTICA (o contrato já está congelado; isto não escolhe nada):**

```
              nome              | eventos | dias_distintos | mercados | pct_do_maior_mercado
--------------------------------+---------+----------------+----------+----------------------
 0 CONGELADA 0,25 / 1,5 / 0,006 |      57 |             17 |        4 |                 29.8
 1 sweep_atr 0,10               |      61 |             17 |        4 |                 31.1
 2 sweep_atr 0,50               |      45 |             17 |        4 |                 28.9
 3 sem RVOL                     |      99 |             18 |        4 |                 33.3
 4 risk_pct_min 0,004           |      86 |             23 |        4 |                 31.4
 5 risk_pct_min 0,003           |     112 |             25 |        4 |                 28.6
 6 sem piso de custo            |     176 |             30 |        4 |                 29.5
```

Três leituras, e a terceira é um aviso ao futuro:

1. **`sweep_atr` quase não importa** (61 / 57 / 45 entre 0,10 e 0,50): a profundidade da varredura
   não é o eixo caro. Uma v2 que mexa nela está mexendo no parâmetro errado;
2. **o piso de custo é o eixo**: 57 → 112 → 176 conforme ele cai de 0,006 para 0,003 e para zero — e
   o pedágio sobe de 0,333 R para 0,667 R e para "o que o mercado der" (0,88 R mediano no estágio A);
3. **e é exatamente por isso que a tentação de baixar o piso tem de ser recusada por escrito agora.**
   A variante 6 é a única que alcança os 30 dias distintos que a régua de maturidade pede. Trocar o
   piso por essa cobertura seria comprar maturidade estatística com uma população que **paga 0,88 R
   de pedágio mediano** — a definição operacional do que a KB-0076 chamou de "por que perdemos".
   Fica registrado: **quem propuser `risk_pct_min` menor está propondo um experimento novo, com EXP,
   portão e contraste pareado próprios**, não um ajuste desta versão.

**Result: `inconclusivo`** — nada foi medido sobre a hipótese. A pré-checagem mede **população**, não
**edge**: 57 barras satisfazem a forma da regra, e sobre o que acontece **depois** delas esta consulta
não diz absolutamente nada.

**Next Action:** escrever o módulo e os testes pelo brief T3.45b; ativar como `research_only`; rodar
o replay de 31 dias em duas fatias com a mesma coorte; preencher a avaliação de dia um abaixo — **e
rotulá-la `inconclusivo` desde já**, porque 17 dias distintos não viram 30.

### Avaliação de <segunda data> — replay de abertura

<não executado. A preencher: coorte, janela, mercados, recibos, comandos exatos, cobertura completa
(`R_net` conhecido / só `r_ex_funding` / nenhum, com motivos), K1–K6 um a um, decomposição por
regime de BTC e por decil de ATR%, o grupo de controle "varreu e fechou abaixo", a interseção por
`(mercado, barra)` com a coorte da `mean_reversion_v1`, `Result`, `Next Action`>

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| varredura em 2 barras (fura numa, recupera na seguinte) | 2026-09-08 | descartada para a v1: dobra a população **e** o espaço de busca, e a versão de 1 barra é o caso limpo. Fica como `v2` candidata | esta página |
| varredura de máxima → vender | 2026-09-08 | descartada antes de rodar: SPOT e long-only por decisão do Everton; `Decision.direction` é `Literal[LONG]` | esta página |
| faixa de ATR% (`atr_pct_min`/`atr_pct_max`) como porta de custo | 2026-09-08 | descartada com motivo medido: a `momentum v5` (T3.40) decidiu **zero** vezes com esse desenho; a porta aqui é `risk_pct_min`, que é a grandeza da identidade do pedágio | esta página + `.claude/state/notes-T3.40.md` |
| pivô escalado pelo ATR da própria barra (como `patterns/pivots.py`) | 2026-09-08 | descartada por custo por barra do Lab; divergência declarada no Protocolo | esta página |

## Relacionadas

[[Experiments Index]] · [[Strategy Backlog]] · [[EXP-0009-mean-reversion-pullback-em-tendencia]] ·
[[EXP-0012-momentum-teto-de-pedagio]] · [[KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo]] ·
[[KB-0076-por-que-perdemos-2026-09-08]] · [[KB-0077-linhas-de-tendencia]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] · [[Registro de Tentativas]]

## Fontes

`.claude/state/notes-T3.33.md` (§1.1, §1.2, §1.6, §2 #9, §4, §5.1) ·
`.claude/state/notes-T3.33d.md` (método da pré-checagem; CONCERN 2) ·
`.claude/state/notes-T3.33e.md` (as 14/14 rejeições de geometria da `breakout_v1`) ·
`.claude/state/notes-T3.34.md` (pivôs, `k`, proeminência, confirmação) ·
`.claude/state/notes-T3.40.md` (§8b, a correção da identidade do pedágio; `atr_pct_max_obs = 0,01623`) ·
`packages/indicators/hunter_indicators/patterns/pivots.py` ·
`packages/core/hunter_core/strategies/mean_reversion_v1.py` ·
`packages/core/hunter_core/strategies/indicators.py` ·
`infra/scripts/sql/research/2026-09-09-sweep-reclaim-precheck.sql`
