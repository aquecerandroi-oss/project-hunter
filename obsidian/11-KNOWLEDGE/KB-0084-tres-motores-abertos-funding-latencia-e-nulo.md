---
tags: [knowledge, nota, plantao, ferramentas, backtest, funding, latencia, nulo, m3]
tema: como Freqtrade, Jesse e Hummingbot tratam funding no backtest, concorrência por par e orçamento de latência — e os dois testes de nulo que publicaram em 2026
fonte: documentação e código-fonte dos três projetos (Freqtrade docs + `backtesting.py`/`freqtradebot.py`/`worker.py` em `develop`; Jesse docs de Rule Significance Testing e changelog; Hummingbot `backtesting_engine_base.py`, `v2_funding_rate_arb.py`, Dashboard docs) — plantão T3.64, run 4
fonte_url: https://www.freqtrade.io/en/stable/leverage/ · https://raw.githubusercontent.com/freqtrade/freqtrade/develop/freqtrade/optimize/backtesting.py · https://docs.jesse.trade/docs/rule-significance-testing/bootstrap · https://raw.githubusercontent.com/hummingbot/hummingbot/master/hummingbot/strategy_v2/backtesting/backtesting_engine_base.py
lido_em: 2026-09-10
evidencia: documentação oficial e código lido (Freqtrade, Jesse, Hummingbot) + uma medição de usuário de 2023 (issue #9106) + correções da Astra sobre trechos que ela abriu e eu não (`position_executor_simulator.py`); nenhuma medição própria
hipotese_testavel: sim — reforço da H-P11 (dois testes de nulo separados) e H-P13 (cap por ocupação); diagnósticos D-P11 (cobertura de funding por versão) e D-P12 (decomposição da latência por etapa e build)
astra: concorda
status: arquivada
owner: sexta-feira
updated: 2026-09-10
confiança: "?"
---

# Três motores abertos diante de funding, latência e nulo (Freqtrade, Jesse, Hummingbot — set/2026)

> Nota de referência do plantão (faixa 4, ferramentas). Não é sobre edge; é sobre o que os frameworks
> abertos decidiram nas três perguntas que o Lab teve esta noite. Rascunho completo com todas as URLs e
> horas de leitura: `.claude/state/plantao/2026-09-10-0630-lane4.md`. `confiança` fica `?` porque a
> evidência mistura documentação, código e um relato de usuário.

## O que afirma

1. **Funding.** Só o Freqtrade simula funding no backtest: carrega duas séries por par (`funding_rate` e
   `mark`), combina-as (`combine_funding_and_mark`) e aplica o custo **a cada intervalo de funding**, não
   por candle (`_run_funding_fees` só roda quando `current_time % funding_fee_timeframe_secs == 0`),
   sobre o intervalo `date_last_filled_utc → current_time` da operação. Quando a série histórica não
   existe, a documentação manda pôr `futures_funding_rate = 0` e avisa que os resultados "will be
   inaccurate for historical timeranges where funding rates are not available". Calcula preço de
   liquidação, "but does not calculate liquidation fees". No Jesse, a página de futuros diz que o saldo
   "only changes when a position is closed" e não cita funding; a busca de issues por "funding" devolve
   "No results" — **ausência de menção na superfície inspecionada, não ausência provada no produto**
   (Astra). No Hummingbot, o motor V2 (`backtesting_engine_base.py`) recebe um único `trade_cost`
   (padrão 0,0002), resolução `"1m"`, e não contém as palavras "funding" nem "slippage"; a Astra abriu o
   `position_executor_simulator.py:35–55` e corrige: o `trade_cost` é descontado **duas vezes** (4 bps de
   ida e volta) e o stop consulta máxima/mínima. O script de arbitragem de funding do Hummingbot
   **codifica** Binance = 8 h (28 800 s) e Hyperliquid = 1 h — a mesma armadilha da nossa D-P3
   ([[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]]).
2. **Concorrência por par.** Freqtrade: "Only one open trade per pair is possible"; o empilhamento
   (`--enable-position-stacking`) é recurso de backtest cujos resultados "cannot be reproduced in
   dry/live trading"; no backtest os pares com operação aberta são processados primeiro e, sem stacking,
   a entrada exige `len(bt_trades_open_pp[pair]) == 0`. Estratégias são comparadas uma por vez sobre o
   mesmo dado, nunca competindo pelo mesmo par. **Isso é analogia arquitetural, não evidência para um
   cap por família** (Astra): instâncias separadas mantêm estados separados; o argumento para o cap é a
   exposição redundante medida no Hunter ([[KB-0083-uma-hora-de-34-r-deriva-e-impulso]], H-P7).
3. **Latência.** Freqtrade: `log_took_too_long` avisa `"Strategy analysis took {duration}s, more than
   25% of the timeframe ({time_limit}s). This can lead to delayed orders and missed signals."`; o loop
   roda a cada `process_throttle_secs` (5 s) alinhado ao próximo candle com 1 s de offset;
   `enter_positions()` percorre a whitelist em série e `break` quando `free_trade_slots <= 0` (os últimos
   da fila perdem o slot). Um usuário mediu em 2023 (issue #9106) 330 s → 111 s de backtest só removendo
   o arquivo de funding — outro motor, outra carga; vale para pôr funding no perfil, não como causa nossa.
   **Os 25 % são um aviso de duração, não uma garantia de execução aceitável abaixo de 225 s** (Astra);
   no Hunter o limite de 120 s incide em barra→abertura escolhida (`plan.py:48,94`).
4. **Nulo.** Freqtrade 2026.6 (29/06/2026) pôs um P-Value (t de uma amostra sobre o retorno médio por
   operação, `scipy.stats.ttest_1samp`, **bilateral**) e avisa: assume operações i.i.d., "trades overlap
   and cluster in time, so the figure is an optimistic lower bound", e com muitas estratégias "some will
   score a low p-value by chance alone". Jesse (Rule Significance Testing; look-ahead do próprio teste
   corrigido em 3.0.2, 05/08; blocos contíguos em 3.1.1, 04/09): backtest "só sinal" (+1/−1/0 por barra,
   nenhuma ordem), retorno = `signal_t × (log_return_t+1 − market_mean)`, bootstrap **estacionário** de
   blocos de comprimento médio 10 barras sobre a série centrada em zero, ≥ 2 000 simulações, `p_value =
   mean(sim_means >= observed_mean)` (unilateral); "nominal single-rule significance test … does not
   correct for trying many strategies"; "says nothing about multi-bar moves, transaction costs, position
   sizing, drawdown, or out-of-sample performance"; in-sample only.

## Onde foi mostrado

Documentação e código, não resultado empírico. Freqtrade `develop` (releases 2026.6–2026.8, 29/06–31/08);
Jesse 3.0.0–3.1.2 (01/08–09/09/2026); Hummingbot 2.12–2.16 (26/01–29/07/2026). A única medição é a do
usuário da issue #9106 (ETH/USDT:USDT, mai–set/2022, versão 2023.6, uma máquina).

## Como mediríamos aqui

- **Funding (D-P11):** por estratégia × versão × coorte, R bruto / custo / funding em colunas separadas;
  `ex-funding` sobre toda a população; líquido só onde determinável, com cobertura declarada; diferença
  líquido − ex-funding nas mesmas apostas. Premissa corrigida: o backfill de T3.75 já entrou para a v10
  (EXP-0025:202, n = 796, 2 `funding_missing`); cobertura das outras versões não publicada.
- **Latência (D-P12):** decompor barra→decisão em fila / candles / funding-mark / cálculo / persistência,
  por versão × mercado e por build (cache por família, `context_cache.py:86`); posição na fila dos
  `late:delay`; justificar 120 s por conta própria.
- **Nulo (H-P11, dois testes):** (A) expectancy líquida por aposta única contra zero com reamostragem
  temporal conjunta entre mercados, bloco com sensibilidade declarada; (B) regra contra entradas
  aleatórias elegíveis com geometria reconstruída, custos, ocupação e rearme. A variante "só sinal" do
  Jesse é pré-teste barato de (B). p > 0,10 não refuta.

## Hipótese testável no Lab

Nenhuma de edge nesta nota. Reforço da H-P11 e H-P13 (cap por intervalo de ocupação, mesmo orçamento
agregado de risco, sem previsão de fator de variância), e os diagnósticos D-P11/D-P12 — todos em
[[Hipoteses-do-plantao]].

## Por que pode falhar

Copiar o orçamento de 25 % do Freqtrade mudaria a política de execução e mascararia o atraso; copiar o
bootstrap do Jesse sobre uma lista de R confunde barra seguinte com operação (dependência entre
operações e entre mercados sobrevive à deduplicação de versões); tratar "não menciona funding" como
"não simula" é inferência de superfície; o 3× de 2023 não é medição nossa.

## Segunda opinião (Astra)

Concorda com contabilidade explícita, diagnóstico de fila, controle temporal e aposta única. Corrigiu:
premissa de funding desatualizada; 25 % ≠ validação dos 120 s; H-P11 misturava objetos; H-P13 confundia
deduplicação, ocupação e escala de risco (Var(4X) = 16 Var(X)); Hummingbot 4 bps e stop em máx/mín; p do
Freqtrade bilateral; 8 bots são analogia, não evidência. Ordem dela: D-P12 → H-P11 corrigida → H-P13 →
H-P12 (depois de confrontar a v10). Transcrição: `.claude/state/astra-review-plantao-20260910-0630.md`.

## Relacionados

[[Plantao/2026-09-10]] · [[Hipoteses-do-plantao]] · [[EXP-0025-mean-reversion-90-dias]] ·
[[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] ·
[[KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos]] ·
[[KB-0076-por-que-perdemos-2026-09-08]] · [[KB-0083-uma-hora-de-34-r-deriva-e-impulso]] ·
[[Strategy Backlog]] · [[11-KNOWLEDGE/Index|Conhecimento]]
