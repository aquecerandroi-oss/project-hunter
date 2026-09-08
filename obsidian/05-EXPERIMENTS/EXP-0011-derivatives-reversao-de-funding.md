---
tags: [experimento, derivativos, funding, shadow-lab]
updated: 2026-09-08
status: proposto
owner: sexta-feira
exp: EXP-0011
strategy: derivatives
version: v1
result: nao-iniciado
evaluable: 0
days: 0
last_eval: ""
---

# EXP-0011 — comprar depois de funding liquidado negativo (`derivatives_v1`)

> **Arquivado pela Sexta-feira em 2026-09-08 (T3.32b)** a partir do rascunho do `quant-engineer`
> (T3.33, `.claude/state/exp-drafts/EXP-0011-derivatives-reversao-de-funding.md`).
> **Nada foi rodado. Nada foi ativado.** "Hipótese" e "Protocolo" **congelados**; avaliações
> **acrescentadas** abaixo, datadas. Brief: `.claude/state/brief-T3.33d-derivatives_v1.md`.
> Esta é a única das quatro aberta **contra** uma recomendação explícita da nossa própria base
> ([[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]]) — e a divergência está declarada
> abaixo, não escondida.

## Hipótese (congelada)

Num perpétuo USDT, depois de uma **taxa de funding liquidada negativa além do componente de juros**
(`funding_rate ≤ −0,0001`, isto é, ≤ −0,01 % no intervalo de 8 h), precedida de uma **queda real**
nas últimas 2 h (retorno de 8 barras de 15 min ≤ −1 × ATR%) e numa barra de 15 min que **fecha acima
do próprio meio**, o retorno seguinte tem expectancy líquida hipotética maior que zero, com stop a
2,0 ATR e alvo a 3,0 ATR da referência e horizonte de 8 h.

**O que a hipótese é, em uma frase:** o teste, com método, da afirmação mais repetida e menos testada
do mercado — *funding negativo = vendidos aglomerados = fundo local* —, na única metade que nos é
implementável (comprada, execução SPOT, long-only por decisão do Everton).

**A divergência com a nossa própria base, declarada.**
[[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] recomenda **não gastar braço de sombra
com funding**. O `quant-engineer` foi contra, e o motivo é que a recomendação dela é sobre *funding
como filtro direcional acoplado ao momentum*, com prior desfavorável vindo de um estudo que mede a
**variação** semanal da taxa no **BTC**. Esta é outra pergunta: o **nível** da taxa liquidada como
estado de posicionamento, com gatilho de preço próprio e grupo de controle no próprio replay.
[[KB-0023-funding-extremo-como-contrarian-a-afirmacao-mais-repetida]] diz textualmente que **nenhum
teste com método foi localizado** nas fontes consultadas. O custo de descobrir é uma corrida de
replay, e o desenho abaixo faz a candidata morrer barato se o estado não existir.

**O que a hipótese não é.** Não é "funding prevê preço". Não é *cash-and-carry* — as estratégias de
carry com Sharpe alto da literatura são duas pernas, dois mercados e exposição direcional zero; nós
temos uma perna, um mercado e exposição direcional total, e nenhum daqueles números se transfere.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key = derivatives`, versão `v1`, `purpose = research_only`.
  Módulo `packages/core/hunter_core/strategies/derivatives_v1.py`.
- **`code_ref`:** digest por versão; os digests de `momentum_v1` (`…ab2e0398…`) e
  `volume_anomaly_v1` (`…9b8c14ab…`) **não se movem** com esta entrega (teste).
- **O que a estratégia lê de derivativos, e só:** `ctx.funding` — **uma** observação, não série.
  **Não** lê open interest (num replay `ctx.open_interest` é sempre `None`: o `ts` durável é um balde
  de rodada de poll e nunca prova `<= cut`), **não** lê `index_price` (nunca é preenchido em
  `NormalizedFunding`, nem pelo caminho durável nem pelo hot state), **não** lê liquidações (não
  existem no contexto).
- **Instrumento declarado:** num replay a leitura vem de `funding_rates` — funding **liquidado**
  (`funding_kind = "realized"`, `ts` = o instante da liquidação), com até ~8 h de idade. A versão
  recusa uma leitura com mais de `funding_max_age_s = 32 400 s` como **`UNAVAILABLE / funding_stale`**,
  nunca como "condição falsa": um mercado cujas liquidações pararam de chegar não prova nada sobre a
  hipótese e não pode rearmar o slot.
- **Timeframe de decisão / de outcome:** 15 min (fechamentos distintos, UTC) / 1 min.
- **Regra de entrada (exata), na ordem:** elegibilidade → disponibilidade e idade do funding →
  janela de sinal 15 m → janela de ATR (Wilder 14 × 15 m, 97 barras, `rolling_window_v1`) →
  `funding_rate ≤ −0,0001` → **houve queda** (`return_8×15m ≤ −1 × ATR%`) → **estabilização**
  (`close ≥ (high+low)/2`) → `0,006 ≤ ATR% ≤ 0,05`.
- **Geometria:** `stop = C − 2,0·ATR`, `alvo1 = C + 3,0·ATR`, alvo informativo `C + 5,0·ATR`.
- **Invalidação (exata): NENHUMA.** A tese é que o preço está temporariamente abaixo de onde o
  posicionamento vai empurrá-lo; uma regra que sai quando o preço cai mais contradiz a tese.
- **Horizonte:** 8 h (28 800 s) = um ciclo de funding.
- **Custos assumidos:** spread total 2 bps, slippage 5 bps/lado, taxa 4 bps/lado,
  `max_entry_delay_s = 120`. Entrada/saída pelo perfil congelado do `docs/plans/SHADOW-LAB.md` §3.
- **Parâmetros congelados:** a tabela de `.claude/state/brief-T3.33d-derivatives_v1.md` §7, 18 chaves.
- **Universo:** replay de abertura em ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT; `prospective` no universo
  elegível inteiro.

### Geometria — por que o stop é largo

Uma tese de squeeze com stop apertado é um gerador de ruído: a entrada acontece logo depois de uma
queda, na parte mais volátil do movimento. Equilíbrio sob o custo assumido:

| geometria | ATR% | R_net no alvo | R_net no stop | acerto de equilíbrio |
|---|---:|---:|---:|---:|
| 1,5/1,5 (`momentum_v1`, referência) | 0,003 | 0,4893 | −1,2736 | 0,7224 |
| **2,0/3,0 (esta)** | 0,006 | 1,2684 | −1,1102 | **0,4667** |
| **2,0/3,0** | 0,010 | 1,3578 | −1,0670 | 0,4400 |

### O único número que não é chute

`funding_min_abs = 0,0001` é **0,01 %**, que é exatamente o **componente de juros** da fórmula de
funding da Binance por intervalo de 8 h ([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]). "Mais
negativo que o componente de juros" é uma linha **mecanicamente significativa** — quer dizer que o
componente de prêmio virou negativo —, não um limiar ajustado. Todo o resto (`drop_bars = 8`,
`drop_min_atr = 1`, `funding_max_age_s = 32 400`) é convenção declarada.

### As duas objeções estruturais que esta versão **não** resolve (KB-0023)

1. **Funding é variável limitada.** Teto e piso são fixados pela corretora; um mercado no limite
   **não fica mais extremo**, e a escala satura exatamente onde o sinal deveria ser mais forte.
2. **Ao saturar, o que muda é a cadência.** A corretora comprime o intervalo para 1 h; **quem lê só a
   taxa não enxerga o regime de cadência**, e confundir os dois produz leitura errada em qualquer
   direção.

Esta versão lê **o nível, e só**. Por isso a primeira avaliação é obrigada a publicar, por decisão,
`funding_rate`, `funding_kind`, a idade da leitura e a distribuição da taxa — para que uma versão
futura consiga separar saturação de extremidade.

## Portão de desenho (C1–C8) — **pendente**

O portão de oito critérios é a tarefa **T3.36**
(`.claude/state/brief-T3.36-validation-gate-and-stress-pass.md`). O **método** já existe como
referência (`.claude/skills/edge-strategy-reviewer/references/review_criteria.md`); o que ainda não
existe é a **seção correspondente no [[_TEMPLATE-EXP]]**. O veredito (PASS/REVISE/REJECT) é escrito
**pelo implementador, antes do código**, e o `code-reviewer` confere que ele existe.
**C1 (plausibilidade da vantagem) e C3 (adequação da amostra) são os que mordem aqui**: a base já registra prior desfavorável, e esta é a candidata com
menor frequência esperada das quatro — a Astra estimou 0,05–0,3 entrada/mercado/dia e avisou que
provavelmente **não** chega a 100 observações em 31 dias.

## O que falsifica esta hipótese

- **Pré-checagem, antes de escrever o módulo** (uma consulta, no brief §13): quantas liquidações
  negativas além do juro existiram na janela nos quatro mercados, e quantas linhas de
  `funding_rates` têm `mark_price` não nulo. Menos de ~10 negativas no total → **K1 vai disparar**,
  não escreva o módulo. `mark_price` majoritariamente nulo → `_resolve_funding` não consegue montar
  a observação e a versão responderia `funding_unavailable` em toda barra: isso é **bug de dado a
  reportar**, não resultado de estratégia.
- **K1/K2/K3/K4/K5** de `.claude/state/notes-T3.33.md` §5.1. **K5 morde com força aqui:** um
  horizonte de 8 h quase sempre atravessa uma liquidação de funding, então espere cobertura de
  `R_net` bem menor que a das outras três, com `meta.r_ex_funding` como métrica separada e cobertura
  própria ([[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]]).
- **Grupo de controle obrigatório.** Sem contraste, "60 % de acerto" só descreve a deriva do mercado
  no período. A primeira avaliação compara, sobre as mesmas barras e mercados, as decisões com
  funding negativo contra as barras em que **todas as outras condições** valiam e só o funding não —
  o pareamento que a [[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] impôs como padrão.
- **Refutação limitada ao que ela pode negar:** ausência de separação entre os dois grupos, dentro de
  uma margem declarada antes, refuta **esta especificação** (este limiar, esta cadência, este
  horizonte) — não a ideia de posicionamento aglomerado.

## O que este experimento **não** prova

- **Não testa "funding extremo"**, testa **funding negativo além do juro**: a saturação está fora do
  alcance do instrumento.
- **Não testa a metade vendida** do folclore, que é a metade em que a maioria das anedotas se apoia.
  A decisão do Everton (SPOT, long-only) a exclui, e `Decision.direction` é `Literal[LONG]`.
- **Multiplicidade:** uma de quatro versões abertas no mesmo dia
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]), e aberta **contra** a
  recomendação explícita de [[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] — o que
  aumenta, não diminui, o dever de reportar o resultado seja ele qual for. T-038 do
  [[Registro de Tentativas]].
- **O replay de abertura não confirma nada**; sai rotulado **REPLAY**.
- **PnL de carteira / Max Drawdown de carteira:** **não aplicável** — `research_only`, sem carteira.

## Avaliações (acrescentadas, nunca reescritas)

**Nenhuma ainda.** A primeira será acrescentada aqui, datada, com: saída da consulta de pré-checagem;
coorte, janela, mercados, recibos, comandos exatos, cobertura completa **com a tabela de funding**
(`R_net` conhecido / só `r_ex_funding` / nenhum, com motivos), métricas com denominador, distribuição
de `funding_rate` e `funding_kind` na decisão, contraste contra o grupo de controle, `Result` e
`Next Action`.

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| funding positivo extremo → vender | 2026-09-08 | descartada **antes** de rodar: SPOT e long-only por decisão do Everton; `Decision.direction` é `Literal[LONG]` | esta página |
| prêmio contra o índice (`mark − index`) | 2026-09-08 | descartada: `index_price` nunca é preenchido em `NormalizedFunding` | `.claude/state/notes-T3.33.md` §1.4 |
| quadrantes de open interest | 2026-09-08 | descartada: num replay `ctx.open_interest` é sempre `None` | `.claude/state/notes-T3.33.md` §1.3 |

## Relacionadas

[[Experiments Index]] · [[Strategy Backlog]] ·
[[KB-0023-funding-extremo-como-contrarian-a-afirmacao-mais-repetida]] ·
[[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] ·
[[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]] ·
[[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] ·
[[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] ·
[[KB-0076-por-que-perdemos-2026-09-08]] · [[Registro de Tentativas]] ·
[[Dialogos/2026-09-08-quatro-estrategias]]

## Fontes

`.claude/state/notes-T3.33.md` · `.claude/state/brief-T3.33d-derivatives_v1.md` ·
`services/strategy-worker/hunter_strategy_worker/derivatives.py` ·
`services/strategy-worker/hunter_strategy_worker/replay/environment.py` ·
`infra/scripts/activate_strategy_version.py` ·
`services/strategy-worker/hunter_strategy_worker/replay/run.py`
