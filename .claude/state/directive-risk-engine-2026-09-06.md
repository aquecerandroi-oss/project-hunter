# Diretiva do Everton — carteira virtual e Risk Engine (2026-09-06, verbatim)

> Estas são minhas decisões para o dimensionamento da carteira virtual e o Risk Engine do Hunter.
>
> Aplique ao projeto existente. Não recrie o sistema e não habilite dinheiro real. Todos os valores abaixo são parâmetros iniciais de teste, não uma estratégia de lucro já validada.
>
> **1. CAPITAL VIRTUAL**
> - Começar com R$100.000 fictícios.
> - Reinvestir automaticamente os lucros.
> - Se o motor operar em USDT, converter o equivalente na abertura e registrar a cotação e a fonte.
> - Não confundir R$100.000 com 100.000 USDT.
> - Mostrar resultados em reais e na moeda operacional, separando resultado das operações de variação cambial.
> - Não fazer aportes nem resetar a carteira para apagar prejuízos.
>
> **2. RISCO POR OPERAÇÃO**
> - Limite de perda planejada: 0,25% do patrimônio atual por operação, incluindo custos estimados.
> - Inicialmente isso corresponde a R$250 de risco, não a R$250 de compra.
> - Soma dos riscos planejados das posições e entradas pendentes: máximo de 1% da carteira.
> - Não liberar risco de 1% por operação sem minha aprovação.
> - O limite é um teto, não uma meta: não aumentar posição nem afastar stop para atingir 0,25%.
>
> **3. TAMANHO DAS ORDENS E LIQUIDEZ**
> - Novas entradas podem representar no máximo 1% do volume de referência de um minuto.
> - Referência: menor valor entre o volume do último minuto completo e a mediana dos últimos 30 minutos completos.
> - Agregar as ordens de todos os agentes no mesmo mercado.
> - Validar também a profundidade atual do livro de ofertas.
> - Não fracionar ordens para contornar limites.
> - Travas de entrada não podem impedir saídas de proteção; simular seus custos e condições de execução.
>
> **4. EXPOSIÇÃO E CONCENTRAÇÃO**
> - Exposição ajustada ao BTC: máximo de 0,5 vez o patrimônio, somando valor das posições multiplicado pelo valor absoluto dos betas.
> - Exposição total: máximo de 40% da carteira.
> - Exposição por moeda: máximo de 10%.
> - Máximo de cinco posições abertas.
> - Incluir entradas pendentes nas reservas e nos limites para evitar ultrapassagens simultâneas.
> - Sem beta validado, manter o ativo apenas em shadow.
> - O radar pode acompanhar mais moedas, sem abrir posição em todas.
>
> **5. KILL SWITCH**
> MODO AVISO:
> - Perda diária de 1% OU drawdown de 4%.
> - Reduzir pela metade o tamanho final aprovado das novas entradas.
> MODO BLOQUEADO:
> - Perda diária de 2% OU drawdown de 8%.
> - Bloquear novas entradas e cancelar entradas pendentes.
> - Continuar gerenciando posições existentes e suas proteções.
> - Não liquidar tudo automaticamente.
> - Retomar somente com minha autorização.
> Calcular perdas e drawdown sobre o patrimônio total, incluindo posições abertas e custos. Usar America/Sao_Paulo para o início do dia e manter o maior patrimônio histórico sem resets.
>
> **6. MODALIDADE**
> - Somente SPOT.
> - Sem empréstimos, alavancagem, short ou futuros.
> - Margem isolada não se aplica a esta etapa.
> - Manter ENABLE_LIVE_TRADING=false.
>
> **7. UNIVERSO NEGOCIÁVEL**
> - Manter piso de 50 milhões de USDT de volume negociado nas últimas 24 horas, por par e na exchange de execução.
> - Preferir menos mercados negociáveis a reduzir o piso inicialmente.
> - Ativos abaixo do piso continuam no radar e em shadow, sem consumir capital da carteira principal.
> - O filtro de volume não substitui a validação do livro de ofertas.
>
> **IMPLEMENTAÇÃO E VALIDAÇÃO**
> Atualize a documentação, as configurações, o backlog e o Obsidian. Implemente o Risk Engine e integre-o à carteira virtual existente.
> Antes de ativar o modo autônomo, teste: cálculo de tamanho, exposição e risco agregado; redução efetiva das entradas no modo aviso; bloqueio de entradas sem desligar as proteções; ordens simultâneas e fills duplicados; reconciliação de saldos, taxas e PnL; dados atrasados, reconexões e reinícios; mínimos e incrementos de ordem da exchange; execuções piores que o stop planejado, sem fabricar proteção perfeita.
> Se houver conflito com o código ou com os dados disponíveis, documente e me apresente antes de alterar os limites.
> Não force operações para gerar atividade nem otimize para prometer retorno diário.
> Ao concluir, apresente arquivos alterados, testes executados, resultados e pendências. Só declare o modo autônomo pretendido pronto quando o fluxo completo estiver verificado.

## Análise do orquestrador (Claude), 2026-09-06 — conflitos a apresentar antes de alterar limites

Os limites do Everton são coerentes entre si (0,25 % por operação × 4 perdas = 1 % diário de aviso; 10 % por moeda × 5 posições ≤ 40 % total; com stop a 2,5 % o notional de 0,25 % de risco é 10 % do patrimônio) e **resolvem** os dois defeitos que a rodada 8 encontrou no contrato antigo (`docs/RISK_ENGINE.md`): o multiplicador do kill switch passa a atuar sobre o tamanho final aprovado (R-KS-1) e o risco por operação passa a ser o limitante de fato (o teto por moeda e o de participação entram como tetos, não como substitutos). O que **não** é coerente com o sistema que existe hoje, e é decisão dele, não nossa:

1. **SPOT vs perpétuos.** Todo o pipeline (M1/M2, Lab) é Binance USDS-M perpétuos: universo, velas, book, funding, liquidações, features. Não existe adaptador spot. Opções: (a) construir o adaptador spot (universo, velas, book e trades do spot; tamanho M1) antes da carteira; (b) a carteira virtual executa **long-only, sem alavancagem, sem funding**, sobre os preços do perpétuo como proxy do spot, rotulada como proxy, enquanto (a) é construída; (c) ambos: spot para o preço de execução (uma stream `bookTicker` spot por par negociável, barata), perpétuo para sinais e features. Recomendação: (c) — os pares negociáveis (piso de 50 M) são poucos dezenas.
2. **"Carteira virtual existente" não existe.** O Lab acompanha sinais em R sem tamanho (KB-0036). Carteira, posições, ordens, fills simulados, saldos e PnL são o M3/M4 e têm de ser construídos. O que existe e se reaproveita: sinais congelados, custos assumidos, funding, book no hot state, regime.
3. **Participação de 1 % do volume de 1 min é o limitante que vai fechar quase tudo.** Medido na VPS (KB-0067/0071): volume de cotação mediano de 1 min = 4.605 USDT → teto mediano de **46 USDT** por entrada; com risco de 0,25 % de ~18 mil USDT (≈ 45 USDT) e stop a 2,5 %, a posição desejada é ≈ 1.800 USDT, 40× o teto. Só os maiores mercados (BTC, ETH, SOL…) passariam. Alternativas para ele escolher: referência de 5 ou 30 minutos, ou participação de 5–10 % do minuto; a regra pode ficar como está e o Risk Engine publica o limitante vencedor (R-PROV-1) para a decisão ser feita com dado.
4. **Beta validado não existe em código.** O β contra o BTC foi medido por SQL (KB-0060) e não é feature. Precisa de cálculo versionado (janela, frequência, mínimo de barras) com marca de validade; até lá, pela regra dele, nenhum ativo sai do shadow. Proposta: β diário de 30 dias sobre retornos de 1 h, recalculado a cada hora fechada, válido só com ≥ 20 dias contíguos; BTC tem β = 1 por definição.
5. **Câmbio BRL.** Fonte pública e gratuita: par `USDTBRL` do spot da Binance (REST público). Registrar cotação, fonte e instante na abertura; PnL em BRL separado em resultado operacional (USDT × câmbio de abertura) e variação cambial (USDT × Δcâmbio).
6. **Início do dia em America/Sao_Paulo.** O sistema é UTC em tudo; o dia do kill switch é calculado no fuso e armazenado em UTC (com DST não havendo mais no Brasil, o offset é fixo −03:00, mas usar a zona nomeada mesmo assim).
7. **Cinco posições vs 27 acompanhamentos simultâneos no Lab.** Não é conflito: a carteira e o shadow são camadas distintas; o shadow continua sem limite e a carteira escolhe entre os sinais elegíveis (critério de escolha a decidir: score do M2? ordem de chegada? R esperado?). Isso é uma decisão a apresentar.
8. **Piso de 50 M de volume 24 h.** Na medição da rodada 8, 182 de 232 somas ficaram abaixo (completude não verificada, e `volume_24h` estava quebrado até `fa9f957`). Remedir depois do fix antes de dizer quantos pares são negociáveis.
