**RESUMO**
Testaria **(1) primeiro no Lab**, como diagnóstico da mean_reversion: ataca diretamente a explicação da família positiva. Papel assumido: `quant-engineer`; parecer, sem execução.
A hipótese é **refutável, mas apenas dividir decisões por sinal × tercil não basta**: precisamos de um controle e de separar mecanismo de rentabilidade.

**ARQUIVOS**
Nenhum criado ou modificado.

**TESTES**
Nenhum teste ou replay executado; conferi código, memória e as três fontes.
Protocolo proposto:
1. Congelar versões, decisões, universo, entradas, saídas, custos, `as_of`, `read_at` e digests; separar replay de prospectivo e não duplicar decisões entre variantes.
2. Definir barra anterior como a última **fechada antes da entrada**, alinhada ao instante da decisão; usar `sign(close−open)`, com dojis separados.
3. Calcular `i = 2×taker_buy_volume/volume−1`; cruzar sinal com tercis de **|i|**, separando fluxo concordante/discordante com o candle. Tercis assinados sozinhos confundem direção e intensidade; essa distinção vem do [paper, §5](https://arxiv.org/html/2608.21888v1).
4. Fixar cortes dos tercis numa janela anterior; conferir cobertura histórica e manter ausências explícitas, sem imputar zero.
5. Medir reversão da próxima barra, retorno bruto em bps e expectancy líquida em R pela saída original; decompor retorno até 15 min e depois, sem somar médias de populações diferentes.
6. Comparar com contrarian lag-1 no mesmo mercado/período, pareado por sinal, fluxo, ATR% e tendência; aplicar a mesma execução/saída. Só decisões selecionadas não identificam o valor adicional da seleção.
7. Pré-registrar dois testes: **ganho incremental sobre o controle > 0** e **expectancy líquida > 0 a 20 bps**, com IC por blocos temporais conjuntos entre mercados, multiplicidade e confirmação fora da amostra.
Resultado incremental positivo refuta “é só lag-1”; líquido positivo robusto refuta “não paga 20 bps”. Falta de significância não confirma nenhuma delas.

**MUST-FIX**
**Funding: testar a transição antes de confiar nos resultados dos contratos afetados.** `_cadence()` usa moda ([funding.py:174](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:174)).
Cenário: histórico dominado por 8 h, entrada às 09h e saída às 13h após a mudança, settlement das 12h ausente; a grade antiga pode devolver custo zero ([funding.py:278](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:278), [funding.py:322](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:322)).
Se a linha das 12h existir, ela é cobrada mesmo fora da grade ([funding.py:289](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:289)); portanto, não é correto dizer que a moda simplesmente ignora todo funding de 4 h. Impacto no universo atual não foi medido.

**NICE-TO-HAVE**
(2) vem depois: estudo de eventos para MAE, slippage e desempenho líquido, com janelas-controle equivalentes. Movimento absoluto maior não prevê direção; correlação móvel não prova hedge estável nem FOMC “inofensivo”.
Correção factual: foi **04/09**, divulgação referente a agosto, não 04/08. [SOTN #380](https://www.talos.com/insights/bitcoins-shifting-macro-identity)

**O QUE EU FARIA DIFERENTE**
Não trataria **1,3 bp como teto universal**: é resultado de captura em BTC/ETH spot; nossa regra inclui tendência horária, desvio e estabilização ([mean_reversion_v1.py:186](/C:/dev/project-hunter/packages/core/hunter_core/strategies/mean_reversion_v1.py:186), [linha 212](/C:/dev/project-hunter/packages/core/hunter_core/strategies/mean_reversion_v1.py:212)).
O [paper](https://arxiv.org/html/2608.21888v1) sustenta previsibilidade direcional, não lucro nem causalidade do fluxo; no holdout, pares significativos caem de 90% para 60%. Autocorrelação linear próxima de zero não contradiz dependência de sinais.

**CONCORDO COM**
Priorizar custos e decisões congeladas. “Positiva” e “HIGH_VOLATILITY ganha” continuam descrições amostrais, não validação. O item (3) está fiel ao [anúncio da Binance](https://www.binance.com/en-BH/support/announcement/detail/68eb952fbf3e4abbb105c78ed6c406e6): nove contratos TradFi específicos, sem generalização para todos os perps.

**OBSIDIAN**
- **Hipóteses do plantão** — registrar os dois testes separados e o controle pareado.
- **EXP-0009 — recuo comprado dentro de tendência de 1 h** — acrescentar diagnóstico proposto, preservando protocolo original.
- **KB-0026 — funding num horizonte de 4h e o viés de exclusão** — incluir transição de cadência e falso zero por settlement ausente.