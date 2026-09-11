---
tags: [knowledge, nota, capacidade, backtest, ferramentas, participacao, m3]
tema: como os motores de backtest abertos tratam o teto de participação (fração do volume da barra que uma ordem pode tomar) — quem corta quantidade, quem só piora o preço e quem não faz nada; e onde a D-P19 do Lab fica nessa régua
fonte: Zipline (`slippage.py`), LEAN/QuantConnect (docs + `VolumeShareSlippageModel.cs`), backtrader (`fillers.py`), Freqtrade (docs), vectorbt (`enums.py`), NautilusTrader (docs + exemplo), Hummingbot (docs) — plantão T3.64, run 8, faixa 4 + correções da Astra
fonte_url: https://raw.githubusercontent.com/stefan-jansen/zipline-reloaded/main/src/zipline/finance/slippage.py
lido_em: 2026-09-11
as_of: "2026-09-11T08:45:00Z"
read_at: "2026-09-11T08:45:00Z"
evidencia: código e documentação oficial (convenções de motor, nenhuma medição de mercado) + a medição própria da D-P19 (`.claude/state/notes-D-P19.md`) como ponto de comparação; nenhuma calibração própria de impacto
hipotese_testavel: "sim — D-P22 (instrumento): teto de participação causal dentro do replay, sequencial, com orçamento compartilhado; sem edge"
astra: concorda
status: vivo
owner: sexta-feira
updated: 2026-09-11
confiança: "?"
---

# O teto de participação nos motores de backtest — quem corta, quem só piora o preço, quem ignora

> Nota do plantão de mercado (T3.64, run 8, faixa 4, leitura 05:20–05:45 BRT de 2026-09-11). Toda
> afirmação carrega a URL aberta. Onde eu errei e a Astra corrigiu está dito por extenso.

## O que afirma

Nenhum bot cripto aberto (Freqtrade, Jesse, Hummingbot, vectorbt) impõe teto de participação no
backtest. O teto existe nos motores de ações que os praticantes copiam — e mesmo neles há **três
comportamentos diferentes** que a literatura de fórum mistura como se fossem um:

| motor | o que faz com uma ordem maior que a fração da barra | parâmetros (padrão) | fonte (lida 2026-09-11) |
|---|---|---|---|
| Zipline `VolumeShareSlippage` | **corta a quantidade** ao `volume_limit` da barra (fill parcial, o resto fica para a barra seguinte) **e** aplica impacto quadrático no preço | `volume_limit = 0.025`, `price_impact = 0.1`; `DEFAULT_EQUITY_VOLUME_SLIPPAGE_BAR_LIMIT = 0.025`; `FixedBasisPointsSlippage`: 5 bp, `volume_limit = 0.1` | https://raw.githubusercontent.com/stefan-jansen/zipline-reloaded/main/src/zipline/finance/slippage.py |
| LEAN `VolumeShareSlippageModel` | **só piora o preço**: `volumeShare = Math.Min(order.AbsoluteQuantity / barVolume, _volumeLimit)`, `slippagePercent = volumeShare² × _priceImpact`; a quantidade preenche inteira ("the pre-built fill models assume orders completely fill") | `volume_limit` 0.025, `price_impact` 0.1; **cripto sem volume → "the model returns zero slippage"** | https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Orders/Slippage/VolumeShareSlippageModel.cs · https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/supported-models · https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/key-concepts |
| LEAN, exemplo de fill model customizado | corta a quantidade a uma fração da barra **anterior** | "fill only 30% of the volume of the previous second bar" | idem key-concepts |
| backtrader `FixedBarPerc` | corta a quantidade a `perc` % do volume da barra | `perc = 100.0` (= sem teto até o usuário mudar) | https://raw.githubusercontent.com/mementum/backtrader/master/backtrader/fillers.py |
| vectorbt | corta ao `max_size` **que o usuário passa** ("Higher than that will be partly filled"); nada de volume | `max_size`, `allow_partial`, status `MaxSizeExceeded`/`PartialFill` | https://raw.githubusercontent.com/polakowo/vectorbt/master/vectorbt/portfolio/enums.py |
| Freqtrade | nada: "All orders are filled at the requested price (no slippage) as long as the price is within the candle's high/low range"; "Exchange trading limits are respected" (mínimos do câmbio); teto por ativo só à mão em `custom_stake_amount`, grampeado em `[min_stake, max_stake]` do câmbio/carteira | `max_open_trades` ("Only one open trade per pair"), `tradable_balance_ratio` 0.99 | https://www.freqtrade.io/en/stable/backtesting/ · https://www.freqtrade.io/en/stable/strategy-callbacks/ · https://www.freqtrade.io/en/stable/configuration/ |
| Hummingbot (dashboard) | nada declarado: pede "Start Date … End Date … Backtesting Resolution … Trade Cost" e cala sobre fills e volume | — | https://hummingbot.org/dashboard/backtest/ |
| NautilusTrader | com L2/L3, "the recorded book supplies price levels and sizes" (o teto vem do livro gravado); com L1, `prob_fill_on_limit` (padrão 1,0: preenche ao **tocar**) e `prob_slippage` (um tick adverso) | exemplo: `prob_fill_on_limit=0.95, prob_slippage=0.05`; `StaticLatencyModel(base 5 ms, insert 2 ms, update 3 ms, cancel 1 ms)` — **exemplo, não recomendação** | https://nautilustrader.io/docs/latest/concepts/backtesting/fill-models/ · https://raw.githubusercontent.com/nautechsystems/nautilus_trader/develop/examples/backtest/model_configs_example.py |

Régua do impacto quadrático (Astra, sobre o `slippage.py`): `0,1 × share²` dá **0,10 / 0,625 / 2,50 bp**
por execução a 1 % / 2,5 % / 5 % de participação. É curva de estresse de motor de ações em barra de
minuto; não há calibração para o nosso minuto cripto, e a origem "2012" que eu atribuí não está provada
em nenhuma fonte aberta.

## Onde foi mostrado

Em lugar nenhum: são convenções de código. O 2,5 % do Zipline/LEAN é parâmetro padrão para ações
americanas em barra de minuto; o 30 % do LEAN é exemplo didático; o 100 % do backtrader é "sem teto".
A única medição desta nota é a nossa: a D-P19 (2026-09-11, `.claude/state/notes-D-P19.md`) usou **1 % do
volume do minuto** e 2 %/5 % como sensibilidade — está dentro da faixa dos motores e do lado
conservador — e converteu o teto em dinheiro: 1 R mediano R$ 53,57 (perp) / R$ 18,14 (spot) e **cenário
com toda aposta fechando +1 R** de R$ 393,60/dia (perp). Linguagem corrigida pela Astra: isso é
cenário, não impossibilidade estrutural (ganhos > 1 R existem; 30 entradas/dia supõem o horizonte de 4 h,
não o tempo em posição medido — `notes-D-P19.md:363`).

## Como mediríamos aqui

**D-P22** (instrumento; extensão **sequencial** da D-P19, senão é a mesma medida com outro nome):

- teto por barra e mercado = participação × **volume causal** (referência dos 60 s já fechados;
  consumo/reservas móveis do contrato `docs/RISK_ENGINE.md:361`; `packages/risk-core/hunter_risk/sizing.py:174`
  já desconta participação usada). **Nunca** o volume final do minuto de abertura — é look-ahead.
  `quote_volume × participação` é notional; quantidade exige o preço;
- orçamento **compartilhado** entre ordens simultâneas do mesmo mercado (1 % por ordem multiplica a capacidade);
- participação ∈ {1 %, 2,5 %, 5 %}; entradas e saídas em ordem, capital ocupado, custos por tamanho;
- reportar por mercado: cortes por participação **separados** das outras recusas; fração do notional
  pretendido que sobrevive; **1 R monetário e PnL líquido em colunas distintas**; ocupação e saídas
  parciais; cobertura SPOT própria (não substituir pelo volume perp);
- coluna de sensibilidade: impacto quadrático `0,1 × share²` **no mesmo notional** que o
  `k·√(notional/ADV)` da D-P19, declarando minuto vs ADV; spread, travessia do livro, impacto e atraso
  separados (sem custo duplicado); ambos os coeficientes **por calibrar**;
- roda no replay separado da linha viva (T3.80), sem edge — só cobertura.

## Hipótese testável no Lab

Não é candidata de estratégia; é instrumento. O que a D-P22 responde: **quanto do que a regra quer
fazer cabe** no minuto de cada mercado, e quanto disso vira dinheiro — por mercado, por hora, com
participação declarada. Refutação do uso: se a fração cortada for ~0 em todos os 16 a 1 %, o teto não
é a restrição ativa e a expectancy ≤ 0 (D-P19) fica como única explicação da meta não caber.

"Quantos mercados vigiar" (Astra): não é "os que cabem na participação" — é o ganho marginal de
oportunidades **executáveis** e de **informação** (um mercado pode informar regime sem receber capital),
sujeito a cobertura, latência e recursos; universos progressivos escolhidos no treino e avaliados fora
dele, com a opção "nenhum". Nenhum motor aberto publica número para 15 m; o que codificam é CPU (loop
serial pela whitelist a cada `process_throttle_secs` = 5 s no Freqtrade; "it's best to keep this list
short" — https://www.freqtrade.io/en/stable/bot-basics/, https://www.freqtrade.io/en/stable/strategy-customization/).

## Por que pode falhar

- **Look-ahead no volume:** o erro mais fácil é dimensionar pela barra que ainda está aberta.
- **Custo duplicado:** spread fixo + travessia + impacto + slippage somados duas vezes (KB-0076, KB-0086).
- **Coeficientes emprestados:** 0,1 e 2,5 % são convenção de ações; `k` do √ não é nosso (D-P19 §7).
- **Cripto sem volume = slippage zero (LEAN):** a ausência de dado vira custo zero em silêncio.
- **Maker por "cruzou":** cruzar o limite não prova execução passiva (fila, tamanho no nível, sequência
  intrabar) — a célula maker da D-P14 continua sensibilidade, não viabilidade.
- **Dois volumes de 24 h convivem** (D-P19 §6): o teto muda conforme a fonte; reportar os dois.

## Relacionados

[[KB-0069-capacidade-e-impacto-o-teto-que-o-livro-impoe]] ·
[[KB-0070-a-tabela-de-capacidade-quantos-mercados-suportam-cada-tamanho]] ·
[[KB-0084-tres-motores-abertos-funding-latencia-e-nulo]] ·
[[KB-0086-ic-positivo-nao-paga-o-pedagio-btc-perp-5-min]] ·
[[KB-0087-o-atraso-de-decisao-e-as-tres-correcoes]] ·
[[Plantao/2026-09-11|Plantão de 2026-09-11]] · [[Hipoteses-do-plantao]] · [[11-KNOWLEDGE/Index|Conhecimento]]

## Fontes

Todas listadas na tabela acima (lidas 05:20–05:45 BRT de 2026-09-11) · `.claude/state/plantao/2026-09-11-0605-lane4.md` ·
`.claude/state/notes-D-P19.md` · `.claude/state/astra-review-plantao-20260911-0605.md`
