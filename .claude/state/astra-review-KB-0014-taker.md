## RESUMO

**(1) Sim: o campo chega ao contexto e não é preservado na agregação.**

O caminho está completo:

- [`repo.py:97`](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/repo.py:97) seleciona `Candle.taker_buy_volume`; a linha 124 o repassa ao `NormalizedCandle`.
- [`context.py:60`](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/context.py:60) carrega essas velas, combina com Redis e entrega os objetos a `build_context`.
- [`base.py:189`](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:189) filtra e ordena os objetos, preservando-os em `candles_1m` na linha 197.
- [`aggregate.py:40`](C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:40) define `Bar` sem `taker_buy_volume`; [`_fold`, linha 77](C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:77), soma apenas `volume` e retorna OHLCV.

Precisão: o campo continua nas velas originais do contexto; **não é transportado para as barras agregadas**. Isso também não garante valor não nulo em toda avaliação: o domínio admite `None` em [`market.py:266`](C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:266).

**(2) A justificativa está parcialmente desatualizada; a disponibilidade operacional não ficou demonstrada.**

Hoje já existe código que preenche o campo:

- O coletor calcula `covered_until` e publica no Redis em [`market-worker/coverage.py:153`](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:153).
- O scanner lê essa prova em [`scanner-worker/coverage.py:102`](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/coverage.py:102).
- O scanner aplica `covered_until` ao `SourceEntry` em [`scanner-worker/context.py:122`](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/context.py:122), usando o instante comprovado como corte na linha 96.

**Mas esses arquivos estão sem commit e não encontrei integração do publicador ao worker:** a composição em [`main.py:85`](C:/dev/project-hunter/services/market-worker/hunter_market_worker/main.py:85) e o laço em [`streaming.py:45`](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:45) não acionam o tracker; a busca por suas chamadas encontrou apenas testes.

Portanto: **“a busca não retorna nada” é falso hoje; “já está disponível em produção” também seria uma conclusão indevida.** No fluxo integrado inspecionado, permanece a pendência. Sem prova suficiente, [`windows.py:174`](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:174) recusa a janela. As três calculadoras dependem dessa verificação em [`micro.py:193`](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/micro.py:193) e na linha 232. Não consultei a VPS.

**(3) `0,10` pode ser uma hipótese honesta, mas “não é calibração” é categórico demais.**

É uma **escolha informada pela distribuição observada da variável**, embora não haja evidência apresentada de otimização por outcome. Não chamaria isso de fraude ou *p-hacking* automaticamente.

O problema é a justificativa: mediana e p95 marginais não determinam a retenção entre candidatos da estratégia. O que interessa ao filtro adicional é:

`P(imbalance ≥ 0,10 | demais condições da estratégia satisfeitas)`

Essas condições incluem volume, fechamento e retorno, verificadas em [`volume_anomaly_v1.py:155`](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:155), linhas 162 e 172. **Nem mesmo “todos os picos de volume” é exatamente a população final de entrada.**

`0,10` significa pelo menos **55% do volume com agressor comprador**. É interpretável, mas os percentis apresentados não demonstram que seja útil ou melhor que outro corte. A formulação honesta seria: “limiar exploratório informado pelos dados, sem seleção por outcome, a congelar antes da validação futura”. Separar descoberta de confirmação é o princípio metodológico relevante. [Nosek et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC5856500/)

**(4) Não: os percentis não demonstram “1m é ruído; 5m é utilizável”.**

Para minutos com volume positivo:

\[
I_{5m}=\sum_{i=1}^{5}w_i I_i,\qquad w_i=\frac{V_i}{\sum_jV_j}.
\]

Logo, o desequilíbrio agregado é uma **média ponderada por volume**. Cancelamento entre minutos pode reduzir a dispersão mecanicamente, mesmo sem qualquer capacidade preditiva. Sob independência, variâncias iguais e pesos fixos, sua variância seria \(\sigma^2\sum_iw_i^2\); com pesos iguais, \(\sigma^2/5\). Essas são hipóteses ilustrativas, não propriedades comprovadas da amostra.

Os percentis tampouco provam que a maioria dos minutos tem poucos negócios. E uma distribuição centrada em zero pode conter informação direcional forte. **O que foi apresentado demonstra menor dispersão marginal em 5m; não identifica quanto vem da agregação nem estabelece utilidade preditiva.**

## ARQUIVOS

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO, papel `quant-engineer`.

## TESTES

Não executei testes nem SQL; os números da nota não foram revalidados. Inspeção estática com `Get-Content`, `rg` e `git status`.

Saída real relevante de `git status --short`:

```text
?? services/market-worker/hunter_market_worker/coverage.py
?? services/scanner-worker/hunter_scanner_worker/context.py
```

## MUST-FIX

1. **Corrigir o estado da cobertura na nota.** A afirmação de busca vazia em [KB-0014:97](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0014-taker-buy-volume-o-que-temos-medido.md:97) já não corresponde ao checkout. **Cenário:** duplicar trabalho existente ou declarar as features operacionais só porque encontrou o publicador, sem verificar suas chamadas.

2. **Retirar a conclusão de inutilidade de 1m baseada em dispersão**, em [KB-0014:75](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0014-taker-buy-volume-o-que-temos-medido.md:75). **Cenário:** descartar informação do último minuto do pico porque a distribuição marginal é larga, enquanto a agregação dilui justamente essa informação.

3. **Reformular a justificativa de `0,10` e congelar a validação**, em [KB-0014:112](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0014-taker-buy-volume-o-que-temos-medido.md:112). **Cenário:** o corte preservar quase todos — ou quase nenhum — dos candidatos relevantes; ajustar depois de observar outcomes e reportar o resultado como confirmação do corte original.

4. **Não tratar ausência de diferença detectada como prova de redundância**, em [KB-0014:129](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0014-taker-buy-volume-o-que-temos-medido.md:129). **Cenário:** uma amostra pequena produz intervalo amplo, e uma feature potencialmente útil é descartada como redundante. Isso pode ser apenas inconclusivo.

## NICE-TO-HAVE

Incluir SQL dos percentis, corte temporal exato e distribuição de `trade_count`, separando população inteira, picos e candidatos que passam pelos demais filtros.

## O QUE EU FARIA DIFERENTE

Primeiro observaria o desequilíbrio sem alterar decisões. Mediria retenção na população candidata, congelaria um único protocolo e avaliaria valor incremental numa janela futura, com custos e incerteza que considere dependência entre mercados e períodos.

## CONCORDO COM

Preservar a evidência antes de experimentar; manter volume zero como indefinido; investigar informação adicional ao preço. A hipótese merece teste — os percentis atuais não a validam.

## OBSIDIAN

- **KB-0014 — `taker_buy_volume`: o que temos, medido:** corrigir cobertura, interpretação dos percentis e classificação do limiar.
- **Features (Feature Engine):** distinguir componentes implementados, integração pendente e disponibilidade comprovada.
- **Registro de Tentativas:** registrar a inspeção que motivou `0,10` e o protocolo futuro antes de executar o braço.
- **Revisões da Astra — KB-0014:** registrar este parecer e seus cenários de falha.