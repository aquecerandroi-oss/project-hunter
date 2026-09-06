**RESUMO**

Concordo com a análise estratificada, com duas correções:

1. **Harvey não exige carteira com vários ativos; exige escala da exposição.** O estudo também examina ativos individuais. Seus resultados não validam stops de 1,5 ATR nem Sharpe do Lab; tampouco autorizam transferir a redução de caudas para stops. “Melhora só em ações e crédito” descreve aquela amostra, não uma impossibilidade universal. [Harvey et al., síntese dos autores](https://www.man.com/insights/the-impact-of-volatility-targeting).
2. **O ATR não serve apenas à geometria:** também seleciona sinais pelo filtro de 0,3%–5%. Portanto, a análise mede comportamento **dentro dessa população selecionada**. [momentum_v1.py:204](/C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:204)

**ARQUIVOS**

Nenhum criado ou modificado. Parecer como `quant-engineer`.

**TESTES**

Não executados; revisão documental e leitura do código, sem cálculo de resultados.

**MUST-FIX**

- **Usar o ATR efetivamente persistido na decisão.** O momentum grava `atr_pct_15m` e recalcula Wilder numa janela móvel; `atr_14_pct` do Feature Engine usa checkpoint ancorado. Trocar os campos pode mudar o decil e analisar uma medida diferente daquela que gerou o sinal. [momentum_v1.py:256](/C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:256), [indicators.py:28](/C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:28), [trend.py:88](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:88)
- **Não definir R como exatamente 1,5 ATR:** o denominador implementado é `P_entry − stop`, incluindo o deslocamento até a entrada e seu preço sintético. Usar o risco nominal distorceria justamente a comparação custo/R. [pricing.py:9](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:9)
- **Estabilidade não comprova boa normalização:** expectancy igualmente negativa em todos os decis seria estável. E ausência de diferença significativa pode ser apenas falta de potência.

**NICE-TO-HAVE**

Mostrar duração e proporções de `stop`, `target`, `expired` e `invalidated` por faixa: ajudam a interpretar diferenças de expectancy.

**O QUE EU FARIA DIFERENTE**

**Corte:** manteria ATR% como eixo primário; custo/R como decomposição secundária. Com custos proporcionais constantes, o custo relativo ao risco nominal varia aproximadamente como `1/ATR%`: trocar o eixo tende a inverter a ordenação, sem separar mecanismos. Reportaria retorno antes dos custos e descontos em R, **todos com o mesmo denominador**, evitando descontar spread/slippage duas vezes. Eles já entram nos preços sintéticos. [pricing.py:9](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:9)

Não usaria **custo realizado/R** para formar grupos: preço de saída e funding realizado dependem do caminho futuro. Para classificação, somente uma estimativa congelada com informação disponível na decisão.

**Pré-registro proposto:**

- Congelar versão, coorte, campo de ATR, período UTC e população de sinais; calcular limites dos decis numa janela histórica definida e mantê-los na avaliação futura. Fixar tratamento de empates.
- Primária: expectancy líquida por decil; mostrar todos, com emitidos, entradas, maturados, avaliáveis, censurados e funding ausente. Não imputar desconhecidos como zero.
- Congelar prazo, método de incerteza por blocos temporais contendo todos os mercados e precisão desejada. Dez decis são resolução descritiva, não garantia de amostra suficiente.
- Para afirmar estabilidade, definir previamente uma margem econômica `δ` e exigir intervalos simultâneos compatíveis com equivalência; “não significativo” não basta.
- Toda escolha motivada pelos dados atuais permanece exploratória. Escolher depois o “melhor decil” para filtrar sinais cria uma **nova hipótese de estratégia**, exigindo validação futura própria.

Decis agrupados também podem separar moedas diferentes, não apenas regimes da mesma moeda; mostraria composição por mercado e período.

**CONCORDO COM**

Análise diagnóstica primeiro. Ela pode identificar fragilidade condicionada à volatilidade; não demonstra que **1,5** seja o melhor multiplicador.

**OBSIDIAN**

- **KB-0007 — ATR e escala por volatilidade:** distinguir exposição, geometria, seleção e normalização da métrica.
- **EXP-0001-momentum-v1:** acrescentar protocolo estratificado separado, preservando o protocolo original.
- **Strategy Backlog:** registrar como candidata de análise, sem ativação ou variante automática.