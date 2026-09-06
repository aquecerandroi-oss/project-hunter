## RESUMO

**A identidade matemática está correta sob uma condição específica; a conclusão “nos afeta pouco” ainda não está demonstrada. A defesa contra minutos ausentes existe. O cruzamento proposto é executável, mas esperar zero interseções com gaps recuperados está errado.**

**1. Inflação constante se cancela?**

Sim, se for um **mesmo fator multiplicativo positivo** em toda a janela, incluindo a barra atual:

\[
\frac{cV_{\text{atual}}}{\operatorname{mediana}(cV_1,\ldots,cV_{288})}
=
\frac{V_{\text{atual}}}{\operatorname{mediana}(V_1,\ldots,V_{288})}.
\]

Isso corresponde à divisão implementada em [volume_anomaly_v1.py:139](/C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:139). A calculadora `RelativeVolume` também divide o volume atual pela mediana das janelas anteriores: [volume.py:79](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/volume.py:79).

O argumento falha nestes casos:

- **Contaminação aditiva constante:** exemplo hipotético, volume atual 400 e mediana 100 dão razão 4. Somar 100 a cada barra produz 500/200 = 2,5. “Constante” precisa significar fator, não quantidade.
- **Fator variável:** volume artificial concentrado na barra atual pode fabricar um pico; concentrado no histórico pode escondê-lo. Mesma corretora não garante fator constante.
- **Outros caminhos do produto:** fatores constantes, mas diferentes entre mercados, preservam a razão de cada mercado e alteram a seleção do universo. Nosso ranking usa volume absoluto de 24 horas e seleciona os primeiros: [universe_repo.py:191](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_repo.py:191), [universe_repo.py:204](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_repo.py:204).
- **Interpretação econômica:** invariância da razão não demonstra que aquele volume representa liquidez executável ou demanda independente.

Portanto, eu escreveria: **“A razão é invariável a uma escala multiplicativa comum; não medimos se a contaminação real obedece a essa condição.”**

**2. `aggregate()` exige minutos contíguos e recusa a avaliação?**

**Sim, no caminho examinado.**

- Exige entradas finais de 1 minuto: [aggregate.py:65](/C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:65).
- Define uma janela exata terminando em `source_bar_close`: [aggregate.py:103](/C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:103).
- Percorre cada minuto; qualquer minuto ausente retorna `Window(reason="gap")`, descartando o resultado inteiro: [aggregate.py:135](/C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:135).
- A estratégia transforma essa indisponibilidade em avaliação sem decisão: [volume_anomaly_v1.py:122](/C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:122).

Ressalva: ausência no começo da série pode ser classificada como `warmup`, também sem avaliação, conforme [aggregate.py:114](/C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:114).

Assim, **“faltam minutos → denominador menor → razão maior” não descreve esse código**. Mesmo numa implementação permissiva, reduzir uma barra histórica não necessariamente reduziria a mediana de 288 barras.

**3. H-KB0018 item 1 é executável? Zero interseções é o esperado?**

**O cruzamento é executável como triagem; zero interseções históricas não é uma garantia do desenho.**

Há mercado, timeframe, início/fim e timestamps de recuperação em [market_data.py:134](/C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:134). Porém, o recovery recupera candles **finais de 1 minuto**, verifica cobertura e mantém o gap como `recovered`: [recovery.py:127](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:127), [recovery.py:159](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:159). Não encontrei nesse caminho a suposta troca de granularidade.

**Contraexemplo:** faltou o minuto 10:00; ele foi recuperado às 10:03; uma avaliação às 10:05 recebe todos os minutos necessários. O sinal pode ser válido e sua janela intersectar o registro histórico do gap.

Também há uma correção de intervalo. Com os parâmetros padrão, tomando `T = source_bar_close`:

| Parte | Intervalo de abertura dos candles |
|---|---|
| Denominador: 288 barras | `[T − 1445 min, T − 5 min)` — **1440 minutos** |
| Numerador | `[T − 5 min, T)` |
| Janela completa da razão | `[T − 1445 min, T)` |

Isso decorre do pedido de `volume_window + 1` barras e da exclusão da última na mediana: [volume_anomaly_v1.py:122](/C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:122), [volume_anomaly_v1.py:139](/C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:139).

Para a janela completa, o predicado é mesmo mercado, timeframe `1m`, `gap_start < T` e `gap_end >= T − 1445 min`. `gap_end` representa o último minuto incluído: [recovery.py:63](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:63).

O cruzamento deve separar recuperados antes da decisão, recuperados depois e casos inconclusivos. **Nem essa classificação temporal prova sozinha o conteúdo visto pela estratégia:** o contexto combina Postgres e Redis, podendo conter um minuto ainda ausente na persistência: [context.py:60](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/context.py:60). Além disso, `gap_start` pode ser encurtado e `detected_at` atualizado; a tabela não é um histórico imutável: [recovery.py:146](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:146), [recovery.py:181](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:181).

**A expectativa correta é zero decisões produzidas com minutos obrigatórios ausentes no contexto efetivamente avaliado.** Interseções são candidatos a investigação, não bugs automáticos.

**4. Declarar os PDFs não lidos basta ou devemos cortar a fonte?**

**Não precisa cortar a fonte inteira. Precisa limitar cada afirmação à evidência realmente consultada e identificar os resumos utilizados.** A ressalva não valida números ou classificações sem referência verificável.

Nesta sessão consegui acessar o texto do PDF do arXiv, versão de julho de 2021. O apêndice, página 62, identifica **Binance como UT1, “Unregulated Tier-1”**, segundo a classificação daquele estudo. A amostra principal cobre **9 de julho a 3 de novembro de 2019**, não genericamente 2019–2020. Isso não caracteriza a Binance USDⓈ-M atual. [Crypto Wash Trading, páginas 4 e 62](https://arxiv.org/pdf/2108.10984).

Os 77,5% e 79,1% aparecem nessa versão, na página 5. São estimativas agregadas do grupo, não números atribuíveis automaticamente à Binance. Não conferi a versão publicada de 2023 nem o relatório Bitwise nesta revisão. [Crypto Wash Trading, página 5](https://arxiv.org/pdf/2108.10984).

## ARQUIVOS

Nenhum arquivo criado ou modificado.

## TESTES

Testes automatizados e consultas ao banco **não executados**. Conclusões baseadas em inspeção do código e consulta à fonte primária; não há contagem medida de interseções.

## MUST-FIX

1. **Retirar a afirmação de que gaps já inflam o denominador/razão neste fluxo.** Cenário: indisponibilidade corretamente recusada vira diagnóstico falso de sinal contaminado, levando a corrigir uma falha não demonstrada.

2. **Substituir “qualquer interseção vira bug”.** Cenário: backfill completo antes da decisão gera sinal válido, mas o protocolo o condena por existir um registro `recovered`.

3. **Retirar “denominador limpo” e “risco descartado” após resultado negativo.** Cenário hipotético: volume artificial varia suavemente, sem números repetidos ou redondos, e não há gaps; ambos os testes passam mesmo com razão distorcida.

4. **Restringir “nos afeta pouco” à invariância matemática demonstrada.** Cenário: inflação constante específica de um mercado altera sua posição no universo monitorado, embora sua razão permaneça idêntica.

## NICE-TO-HAVE

Registrar versão/página de cada fonte e separar contagem de **sinais intersectados** da contagem de **pares sinal–gap**, evitando duplicidade no relatório.

## O QUE EU FARIA DIFERENTE

Reformularia H-KB0018 como auditoria de cobertura e disponibilidade no momento da decisão. Manteria a investigação de volume artificial como hipótese separada, cujo resultado negativo significa apenas “não detectado pelos diagnósticos utilizados”.

## CONCORDO COM

A identidade multiplicativa, a defesa de continuidade, a cautela com extrapolação de spot para perpétuos e a decisão de não alterar parâmetros com base nesta nota.

## OBSIDIAN

- **Volume relatado e o denominador que usamos** — corrigir os quatro must-fix, os intervalos e a proveniência bibliográfica.
- **EXP-0002-volume-anomaly-v1** — acrescentar o protocolo corrigido de auditoria, preservando hipótese e avaliações anteriores.
- **Market Collector** — explicitar que um gap recuperado pode intersectar legitimamente a janela de um sinal posterior.
- **Revisoes-Astra/KB-0018** — registrar esta revisão e distinguir conclusões do código de verificações empíricas ainda pendentes.