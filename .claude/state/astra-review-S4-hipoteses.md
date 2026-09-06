## RESUMO

**A: os cenários estão aritmeticamente corretos, mas não são limites garantidos do contrafactual. B: há forte evidência de falha de identificação temporal, mas “72 bugs de identidade” e “3 corridas comprovadas” excedem a evidência.**

Revisão como `quant-engineer`, em modo OPINIÃO. Tratei os números da VPS como dados fornecidos por você; não executei novamente seu SQL nem confirmei a equivalência entre o checkout local e os artefatos implantados.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Não executei suítes de testes. Fiz leitura estática e recalculei, com `Decimal` no PowerShell, os cenários a partir dos agregados informados. Saída:

```text
momentum_target             : 0,159674358974358974358974359
momentum_stop               : -0,3560242112725983693725629209
volume_target               : 0,4824519514767932489451476793
volume_stop                 : -0,4245364477080004915816640039
momentum_break_even         : 0,2203541666666666666666666667
volume_break_even           : -0,0662026785714285714285714286
momentum_missing_break_even : 1,3665357142857142857142857143
volume_missing_break_even   : 2,0227944444444444444444444444
```

São verificações de aritmética sobre seus números arredondados, não novas medições da VPS.

## MUST-FIX

**1. Não chamar os cenários de “intervalo que contém o contrafactual”.**

A conta é:

\[
E_{\mathrm{cenário}}=\frac{S-S_I+n_I\mu_{\mathrm{substituição}}}{N}
\]

Ela preserva os pesos corretos. **O problema não é média de médias; é transportar a média de outro grupo para os invalidados sem justificar essa hipótese.**

Cenário concreto de falha: invalidados podem ter outra geometria entrada–stop–alvo, outro tempo restante e outra exposição a funding. A média contrafactual deles pode ficar fora das médias dos targets e stops observados. Além disso, o modelo admite stop em abertura abaixo do nível, portanto a média observada dos stops não é um piso financeiro garantido ([walker.py:71](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:71)).

Enunciaria:

> “Dois cenários de substituição, mantendo os demais outcomes e o denominador fixos, produzem expectancies de −0,3560 e +0,1597 R no momentum, e −0,4245 e +0,4825 R no volume. Não são limites nem intervalos de confiança. Mostram sensibilidade à hipótese adotada para os invalidados.”

Bootstrap das distribuições de targets/stops **não resolve essa falta de identificação**: acrescentaria incerteza amostral a uma imputação ainda não validada.

**2. Corrigir o alcance da observação de MFE e separar os protocolos.**

O acompanhamento realmente para quando termina ([walker.py:173](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:173)). Portanto, o MFE do outcome não responde o que aconteceria depois da invalidação.

Mas “não está gravado em lugar nenhum” é forte demais: existem candles persistidos, potencialmente suficientes para replay. Falta verificar continuidade e cobertura até o horizonte de cada entrada ([market_data.py:33](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:33), [repo.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/repo.py:74)).

Também há dois protocolos no código local:

- **Momentum:** fechamento abaixo do máximo anterior, no timeframe da estratégia ([momentum_v1.py:282](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:282)).
- **Volume:** fechamento de **5 minutos abaixo do meio da barra do sinal**, não rompimento de 15 minutos ([volume_anomaly_v1.py:66](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:66), [volume_anomaly_v1.py:241](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:241)).

Cenário de falha: registrar ambos como teste da mesma regra de invalidação e depois atribuir a diferença de resultados apenas à estratégia.

**3. Trocar a classificação “72 bugs de identidade” por evidência graduada.**

Seu censo permite esta divisão:

| Casos | Enunciado defensável |
|---|---|
| **69** | Há candidato próximo, mas não exato; compatível com falha de identidade/grade temporal. |
| **3** | Há casamento exato na leitura atual; a causa histórica permanece por demonstrar. |
| **1** | Não há candidato em ±60 s no snapshot consultado; verificar também se a liquidação prevista era devida. |

O mecanismo de falha existe no código: `_cadence()` trunca diferenças para segundos inteiros; a grade usa essa cadência e uma âncora observada; o lookup exige igualdade exata ([funding.py:68](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:68), [funding.py:120](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:120), [funding.py:136](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:136)).

Exemplo: intervalo real de `14399,995 s` vira `14399 s`. Isso pode explicar pedidos quase um segundo antes da liquidação, além dos desencontros de milissegundos. É um mecanismo demonstrável; atribuí-lo a cada caso exige reconstruir seu histórico e sua âncora.

Cenário de falha: chamar o pedido de 10:00 de “dado realmente ausente” quando uma mudança de cadência ou grade incorreta poderia ter inventado uma liquidação devida naquele horário.

**4. Não declarar corrida comprovada pelos três deltas zero.**

Concordo com a implicação restrita: **se aquela mesma linha estivesse no `history` fornecido à função, aquele instante não falharia por igualdade**. Isso não prova quando a linha ficou visível.

O modelo `FundingRate` não registra horário de ingestão; `SignalOutcome.updated_at` não registra o snapshot da consulta de funding ([market_data.py:90](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:90), [agents.py:198](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents.py:198)). A consulta ainda tem recorte próprio por mercado e tempo ([repo.py:143](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/repo.py:143)).

A corrida é plausível: o coletor consulta, enfileira e depois persiste funding; o fluxo normal de acompanhamento seleciona apenas estados abertos ([funding.py:55](C:/dev/project-hunter/services/market-worker/hunter_market_worker/funding.py:55), [tracking_repo.py:160](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/tracking_repo.py:160)).

Para comprová-la, precisaria de evidência da visibilidade/commit da liquidação versus a leitura que calculou o outcome — logs ou histórico transacional suficientemente detalhados. **Os agregados e timestamps financeiros apresentados não bastam.** E os 69 desencontros também podem ter sofrido chegada tardia: os mecanismos não precisam ser mutuamente exclusivos.

**5. Não corrigir apenas com “nearest timestamp em ±2 s”.**

Cenário concreto: a grade contém `08:00:00` e o observado contém `08:00:00.005`. Hoje a função faz a união dos dois conjuntos. Se apenas `known.get()` ganhar tolerância, **a mesma liquidação pode ser cobrada duas vezes** ([funding.py:126](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/funding.py:126)).

Outro cenário: saída às `08:00:00`, liquidação registrada às `08:00:00.005`. Buscar uma janela maior e cobrar automaticamente pode incluir funding posterior à saída. O recorte atual termina em `exit_ts`, e há tratamento específico para saída intrabar ambígua ([settle.py:60](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:60)).

**±2 s é uma janela diagnóstica que cobre os desvios relatados; não uma tolerância correta já demonstrada.** Um protocolo de associação precisaria:

- Identificar o evento do mesmo mercado e validar a cadência vigente.
- Exigir associação única, sem reutilizar uma liquidação.
- Manter timestamp original e distinguir identidade do evento de incidência financeira.
- Recusar ambiguidades nas fronteiras de entrada/saída.
- Usar tolerância muito menor que metade do espaçamento mínimo validado entre eventos, com justificativa para sua magnitude.

A documentação da Binance expõe `fundingTime` e `markPrice` no histórico; não oferece, nessa especificação, uma garantia de jitter de ±2 s. [Documentação oficial](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History).

## NICE-TO-HAVE

**Aproveitar os limites de MFE já preservados.** “MFE nulo nos targets” não significa ausência total de informação: o toque fornece limite inferior e a máxima da barra fornece limite superior. O código armazena ambos ([excursions.py:125](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/excursions.py:125), [excursions.py:164](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/excursions.py:164)).

Assim, você pode comparar limites agregados de excursão, com população e duração explícitas. Isso melhora a descrição, mas continua sem responder o contrafactual pós-invalidação.

Também contaria **liquidações distintas afetadas**, além de outcomes: vários outcomes podem compartilhar a mesma falha de um único evento de funding.

## O QUE EU FARIA DIFERENTE

**Para A, registraria uma análise de sensibilidade com ponto de equilíbrio.**

Mantendo apenas os avaliáveis com `R_net` conhecido:

| Estratégia | Invalidados substituídos | Média contrafactual necessária para zerar a soma total |
|---|---:|---:|
| Momentum | 24 de 91 | **+0,22035 R** |
| Volume | 112 de 316 | **−0,06620 R** |

Isso responde uma pergunta concreta: “quanto os invalidados precisariam render sob outra saída para zerar esta coorte?”. Não estima a probabilidade de isso ocorrer.

Não misturaria esses 24/112 com os 71/156 da descrição geral de MFE. São populações diferentes, e as médias de duração tampouco significam que cada momentum tenha exatamente 3,5 horas restantes.

**Você está correto sobre 1 R.** Para momentum:

\[
q_i=\frac{target_i-entry_i}{entry_i-stop_i}
\]

Stop e alvo são simétricos em relação à referência, não à entrada; esta ainda incorpora os custos sintéticos de entrada ([momentum_v1.py:217](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:217), [pricing.py:47](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:47)). Portanto, `MFE ≥ 1R` não equivale a alcançar o alvo. Para volume, o stop é definido por outra geometria, não pelo mesmo `stop_atr=1.5`.

**Para o novo EXP, faria comparação pareada de regras de saída.**

Congelaria as mesmas entradas e acompanharia dois braços: regra atual versus regra sem invalidação, mantendo stop, alvo, horizonte e custos. Registraria por entrada a diferença de `R_net`, incluindo perdas evitadas, recuperações até alvo, expirações, funding e censuras.

É cientificamente válido **como comparação no modelo hipotético por barras**. O replay desta coorte seria exploratório; um período posterior, com protocolo congelado, serviria para confirmação. Ver o preço alcançar o alvo depois não basta: precisa verificar se o stop teria ocorrido antes.

Separaria dois objetivos:

- **Efeito da saída sobre entradas fixas:** comparação pareada.
- **Efeito sobre a estratégia completa:** inclui mudanças nas próximas entradas, pois o término libera o acompanhamento anterior ([outcomes.py:102](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/outcomes.py:102)).

Um monitor apenas adicional melhora o instrumento; mudar a saída testada introduz uma hipótese operacional nova, apropriada para outro EXP. Bootstrap futuro deve preservar dependência temporal e entre mercados simultâneos; reamostrar trades isolados não faz isso. [Referência de bootstrap para séries dependentes](https://stat.cmu.edu/~cshalizi/uADA/16/lectures/26.pdf). Um dia não sustenta inferência entre regimes ou dias.

**Para B, mediria separadamente seleção e custo de funding.**

A implementação realmente calcula `R_net` apenas nos casos disponíveis e mantém uma série separada de `r_ex_funding` ([lab_summary.py:136](C:/dev/project-hunter/apps/api/hunter_api/services/lab_summary.py:136), [settle.py:76](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:76)).

A direção do efeito da exclusão é **desconhecida**:

\[
\mu_{\mathrm{todos}}-\mu_{\mathrm{observados}}
=\frac{m}{N}\left(\mu_{\mathrm{ausentes}}-\mu_{\mathrm{observados}}\right)
\]

Funding positivo reduz o R da mesma operação; funding negativo aumenta. Isso não determina se excluir operações inteiras elevou ou reduziu expectancy e PF.

Com os dados individuais existentes, faria:

1. Comparação de `r_ex_funding` entre disponíveis e ausentes: mede a diferença observável de composição.
2. Reconciliação auditável das liquidações de **cada um dos 14/36 avaliáveis**, verificando todos os eventos devidos e `mark_price`, não apenas o primeiro motivo de falha.
3. Recálculo de expectancy e PF, preservando separadamente o resultado original e a leitura reconciliada.

Para zerar a soma da população completa, os 14 ausentes do momentum precisariam de média líquida **+1,36654 R**; os 36 do volume, **+2,02279 R**. Isso é outro ponto de equilíbrio, não estimativa.

O PF precisa dos R individuais reconciliados: sua mudança depende de quanto entra no numerador positivo e no denominador negativo. Não é correto simplesmente subtrair funding agregado do PF.

## CONCORDO COM

- O gate informado corresponde à maturação exigida por `is_evaluable()` ([lab_summary_metrics.py:66](C:/dev/project-hunter/apps/api/hunter_api/services/lab_summary_metrics.py:66)).
- MFE até a saída não identifica a consequência de manter a posição.
- Comparar apenas MFE determinado seleciona outcomes conforme o modo de saída.
- A igualdade exata contra uma grade inferida é um mecanismo concreto de falha.
- Manter os experimentos inconclusivos, sem alterar parâmetros ou ativação, é coerente com esta evidência.

**O que eu NÃO afirmaria:**

- “O contrafactual está dentro desses intervalos.”
- “A invalidação destrói operações vencedoras” ou “protege a estratégia”.
- “Todo target necessariamente tem MFE indeterminado”: uma saída na abertura pode ter extremo determinado ([excursions.py:119](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/excursions.py:119)).
- “72 liquidações estão recuperáveis” — são outcomes com candidatos; identidade, incidência, preço e eventos adicionais ainda precisam de validação.
- “Os três deltas zero provam corrida.”
- “Excluir funding enviesou as métricas para cima/baixo.”
- “134 mercados e centenas de outcomes equivalem a centenas de observações independentes.”

## OBSIDIAN

- **EXP-0001 — momentum em modo sombra:** acrescentar avaliação da VPS com identidade da coorte, cenários condicionais e ponto de equilíbrio; separar da avaliação local anterior.
- **EXP-0002 — volume_anomaly em modo sombra:** acrescentar avaliação da VPS, distinguir sua regra de invalidação e registrar limitações do funding.
- **Strategy Performance:** alinhar maturação ao gate atual e distinguir sensibilidade, identificação contrafactual e seleção por funding disponível.
- **Open Bugs:** registrar igualdade exata, truncamento da cadência e hipótese ainda não comprovada de chegada tardia.
- **Revisões da Astra:** registrar esta revisão e os requisitos propostos para comparação pareada de saídas.