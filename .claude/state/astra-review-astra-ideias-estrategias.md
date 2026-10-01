## RESUMO

**Eu priorizaria carry protegido e desbloqueios de tokens.** Completaria a fila com desmonte de posições alavancadas, fluxo vendedor de ETFs e divergência entre exchanges. São mecanismos novos em relação às hipóteses descartadas; nenhuma das cinco está confirmada para nós.

Atuei como **quant-engineer**, em OPINIÃO. Considerei a memória solicitada e as páginas de Perdas em `obsidian/03-TRADING/Meme/Perdas`. Também excluí C1, que já aparece como **H-027**, além de C2. [Fila de Hipóteses:316](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:316>)

**As cinco propostas abaixo são para pesquisa no Lab.** Não encontrei sustentação suficiente para recomendar uma diretamente à `spot/1` com ficha de 0,05 SOL. A premissa histórica de 0,001 SOL por perna consumiria **4% da ficha na ida e volta**, antes do custo variável. Isso é uma premissa a verificar, não uma medição atual. [KB-0169:128](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0169-fibonacci-e-lta-diaria-no-dado.md:128>)

A ordenação é meu julgamento de **valor esperado da pesquisa: plausibilidade de lucro líquido × capacidade de testar ÷ esforço**. Não é uma estimativa estatística de rentabilidade.

| Ordem | Hipótese nova | Fonte potencial do lucro | Esforço estimado¹ |
|---|---|---|---|
| 1 | Carry: comprar spot e vender perpétuo do mesmo ativo | Pagamento por financiar demanda alavancada | 5–8 dias |
| 2 | Short de desbloqueios grandes, com proteção de mercado | Oferta programada de tokens de insiders | 5–8 dias |
| 3 | Compra após cessar desmonte forçado | Pressão temporária de vendas compulsórias | 4–6 dias |
| 4 | Short de BTC após fluxo vendedor anormal nos ETFs | Informação externa ao mercado de perpétuos | 3–5 dias |
| 5 | Convergência do mesmo perpétuo entre exchanges | Fragmentação temporária de preços | 8–12 dias |

¹ Preparação de dados e simulador de pesquisa; não inclui espera por amostra, contratação de dados ou implementação em produção.

### Protocolo comum às cinco

Os números abaixo são **escolhas propostas para pré-registro**, não resultados encontrados:

- Congelar universo, fórmulas, custos e período antes de observar os desfechos. Usar histórico já inspecionado apenas para desenvolvimento; confirmação em janela reservada ou prospectiva.
- Retorno sobre **todo o capital necessário**, incluindo caixa de proteção e dinheiro parado entre oportunidades. Não dividir o lucro apenas pela margem.
- Custos: tarifas taker aplicáveis, spread, impacto, atraso e funding efetivamente liquidado. Sem supor execução maker. Piso de estresse: **20 bps por ida e volta de cada posição perpétua** e **30 bps na posição spot**, aumentando quando a execução estimada custar mais. São premissas conservadoras propostas, não tarifas atuais verificadas.
- `D` = vantagem líquida contra o controle especificado. **CONFIRMA:** `D ≥ MRE`, limite inferior do IC95% > 0, teste de permutação em blocos com Holm nas cinco hipóteses `< 0,05`, lucro líquido em nível > 0, sinal positivo nas duas metades temporais e estabilidade nos limiares vizinhos indicados.
- **REFUTA:** limite superior do IC95% de `D < MRE`, com dados e amostra válidos. **NÃO CONFIRMA:** demais casos, incluindo cobertura insuficiente. Essa distinção segue o protocolo do projeto. [RESEARCH.md:65](C:/dev/project-hunter/docs/RESEARCH.md:65)
- Bootstrap com 10.000 réplicas, preservando dependência temporal e choques simultâneos entre moedas. Quantidades mínimas abaixo são pisos de admissibilidade; não garantem potência.

### 1. Carry protegido: spot comprado + perpétuo vendido

**Tese — duas linhas:**  
Quando a demanda por alavancagem paga funding persistentemente positivo, podemos receber esse fluxo mantendo proteção contra a direção do ativo.  
O lucro precisa sobreviver aos custos das duas posições, à variação do diferencial de preços e ao capital necessário para manter a proteção.

**Novidade.** É uma carteira que recebe um pagamento contratual. O item 13 do backlog propõe observar prêmio contra índice; não é esse teste de carteira com duas posições e contabilidade de funding. [Strategy Backlog:61](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Strategy Backlog.md:61>)

**Evidência e qualidade: `backtest do autor`.** He, Manela, Ross e von Wachter apresentam teoria e estratégia empírica de divergência spot–perp. Porém, as condições de custo do artigo não demonstram viabilidade para nosso tamanho e execução; perpétuos também não têm vencimento que assegure convergência. [Fundamentals of Perpetual Futures](https://arxiv.org/html/2212.06888v5)

**Dados.** Existem contratos para `funding_rates`, preços e estado de mercado em `market_snapshots`. Falta conferir cobertura histórica, sincronizar preços spot/perp executáveis e simular caixa/margem das duas posições. [market_data.py:64](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:64), [market_data.py:90](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:90)

**Teste pré-registrável:**

- **População:** BTC e ETH, contratos lineares USDT e spot correspondente na mesma exchange; sem empréstimo para comprar spot.
- **Variável/entrada:** funding realizado dos últimos sete dias, extrapolado mecanicamente para 14 dias. Entrar quando receita projetada menos custo completo superar **0,40% do capital total**. Não atribuir lucro antecipado à convergência.
- **Posição/horizonte:** quantidades iguais do ativo, spot comprado e perp vendido; encerrar ambas após **14 dias**, contabilizando funding e diferencial de saída reais. Uma posição por ativo.
- **Controle:** caixa, com encargo de oportunidade pré-fixado em **5% a.a.**; comparar também com carry incondicional, como diagnóstico.
- **Amostra:** 24 meses, ≥60 episódios; blocos temporais de 28 dias.
- **Veredito:** regra comum com **MRE = +0,20% por episódio de 14 dias**, sobre capital total, após o encargo de oportunidade. Estabilidade para entradas em 0,30% / 0,40% / 0,50%.

**Principal falso positivo:** anualizar funding excepcional, presumir sua continuidade e esquecer capital ocioso ou perdas de basis.  
**Esforço:** 5–8 dias. **Primeira escolha:** mecanismo econômico mais explícito das cinco.

### 2. Desbloqueios grandes de insiders: short do token + proteção em BTC

**Tese — duas linhas:**  
Desbloqueios grandes de equipe/investidores podem produzir oferta e antecipação de vendas maiores que a capacidade de absorção do mercado.  
Uma posição vendida no token, protegida parcialmente contra o mercado, testa esse efeito específico sem depender de acertar a direção geral das criptomoedas.

**Evidência e qualidade: `backtest do autor`, na forma de estudos de eventos.** As análises de 6th Man Ventures e Keyrock relacionam tamanho/tipo de desbloqueio a desempenho posterior. Isso sustenta a pesquisa, mas **não demonstra short executável e lucrativo após funding**. Duas análises comerciais concordantes não equivalem a replicação independente do nosso teste. [6MV](https://6thman.ventures/writing/token-unlocks), [Keyrock](https://keyrock.com/from-locked-to-liquidity-what-16000-token-unlocks-teach-us/)

**Dados.** Velas e funding têm tabelas existentes. Faltam calendário com histórico de publicações/revisões, quantidade liberada, destinatário e oferta circulante **conhecida naquele momento**. [market_data.py:33](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:33), [market_data.py:90](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:90)

**Teste pré-registrável:**

- **População:** tokens entre os 50 maiores perpétuos por volume dos 30 dias anteriores, com ≥90 dias de negociação; desbloqueios discretos de equipe/investidores anunciados ≥14 dias antes.
- **Variável:** desbloqueio / oferta circulante anterior **≥1%**. Agrupar eventos do mesmo token separados por menos de 30 dias.
- **Posição/horizonte:** vender sete dias antes; recomprar sete dias depois. Comprar BTC como proteção, com beta estimado nos 60 dias anteriores e congelado na entrada; exposição bruta limitada ao capital.
- **Controle:** carteiras equivalentes de tokens sem desbloqueio em ±30 dias, pareadas por liquidez, volatilidade e retorno anterior, na mesma data.
- **Custo:** duas posições perpétuas completas; incluir especialmente funding negativo pago pelo short.
- **Amostra:** 24 meses, ≥60 eventos e ≥15 tokens; reamostragem temporal de 28 dias e por token.
- **Veredito:** regra comum com **MRE = +0,50 ponto percentual por evento** sobre o controle. Estabilidade em 0,75% / 1% / 1,25% de desbloqueio.

**Principal falso positivo:** reconstruir calendários e oferta com informação revisada posteriormente; confundir um ciclo de queda das altcoins com efeito do desbloqueio.  
**Esforço:** 5–8 dias se existir calendário auditável; sem ele, bloqueada por dado.

### 3. Compra após cessar desmonte forçado de posições compradas

**Tese — duas linhas:**  
Liquidações de longs podem pressionar o preço por necessidade de margem, além do que a informação nova justificaria.  
A hipótese é comprar quando o fluxo forçado diminui após uma redução efetiva de posições abertas, sem exigir recuperação prévia do preço.

**Novidade.** A variável é **desalavancagem observada: liquidação + queda de OI + cessação do fluxo**. Não é repetir absorção de venda de meme, esperar um dip ou escolher um novo limiar de retorno.

**Evidência e qualidade: `estudo revisado` para o mecanismo; reversão lucrativa ainda é extrapolação.** Cheng et al. documentam liquidações materiais e alavancagem extrema em futuros de BTC. O estudo não demonstra que comprar depois delas dá lucro líquido. [Applied Economics, 2021](https://www.tandfonline.com/doi/abs/10.1080/00036846.2021.1922597)

**Dados.** Existem `liquidations` e `open_interest_history`. O parser atual usa quantidade executada `z` e preço médio `ap`; a nota que ainda o descreve como `q×p` ficou desatualizada. [market_data.py:103](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:103), [streams_liquidation.py:50](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams_liquidation.py:50)

Faltam auditar cobertura e versões históricas. Além disso, o stream público da Binance entrega uma amostra limitada de ordens: a soma recebida **não é o volume total liquidado**. [Documentação Binance](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Liquidation-Order-Streams)

**Teste pré-registrável:**

- **População:** dez maiores perpétuos por volume anterior de 30 dias, com ≥90 dias de dados.
- **Variável:** liquidações vendedoras recebidas em uma hora acima do percentil 99 dos 60 dias anteriores; OI em quantidade cai ≥5%; nos 30 minutos seguintes, fluxo recebido ≤25% da hora do choque. Lacuna de coleta invalida o evento.
- **Entrada/horizonte:** comprar na primeira execução simulável após esses 30 minutos; saída após **24 horas**, sem exigir rebound. Uma entrada por ativo a cada 48 horas.
- **Controle:** quedas comparáveis em retorno, volatilidade e liquidez, mas sem choque conjunto de liquidações/OI. Pareamento congelado antes dos desfechos.
- **Custo:** round trip perpétuo, funding e execução durante estresse.
- **Amostra:** 24 meses, ≥100 eventos em ≥30 dias distintos; blocos de sete dias, preservando moedas do mesmo choque juntas.
- **Veredito:** regra comum com **MRE = +0,30 ponto percentual** contra o controle; estabilidade em percentis 98,5 / 99 / 99,5.

**Principal falso positivo:** detectar interrupção do coletor como cessação das vendas, ou apenas redescobrir reversão após quedas grandes.  
**Esforço:** 4–6 dias, além da coleta necessária. Só depois de confirmada no Lab eu estudaria transferência para Jupiter, com resultado medido em SOL.

### 4. Fluxo vendedor anormal nos ETFs como sinal externo para short de BTC

**Tese — duas linhas:**  
Vendas a descoberto nos ETFs podem incorporar informação que demora a ser absorvida integralmente pelo BTC.  
O teste é vender o perpétuo somente depois da publicação desse fluxo e verificar se a informação acrescenta algo ao preço e ao sentimento já conhecidos.

**Evidência e qualidade: `estudo revisado`.** Onishchenko encontra poder preditivo de fluxos vendedores dos ETFs por até cinco pregões. O artigo ressalva que seu resultado de estratégia é bruto e não constitui demonstração de implementação lucrativa. A transferência de ETF para perpétuo é nossa hipótese. [Betting Against Bitcoin, 2026](https://ourarchive.otago.ac.nz/esploro/outputs/journalArticle/Betting-Against-Bitcoin-Evidence-from-Spot/9926869882101891)

**Dados.** Temos estrutura para preços e funding do BTC; faltam arquivos FINRA, ações em circulação dos ETFs, composição histórica do universo e carimbos de disponibilidade. Volume vendido a descoberto não deve ser interpretado como estoque de posições vendidas. [FINRA](https://www.finra.org/rules-guidance/notices/information-notice-051019)

**Teste pré-registrável:**

- **População:** BTC perpétuo; sinal agregado dos cinco maiores ETFs spot americanos por patrimônio do mês anterior.
- **Variável:** volume diário vendido a descoberto / ações em circulação, agregado por patrimônio anterior; entrada quando superar o percentil **90 dos 60 pregões anteriores**.
- **Entrada/horizonte:** primeira janela das **08:00 UTC após todos os arquivos necessários terem sido recebidos**; manter short até 08:00 UTC após cinco pregões americanos. Não sobrepor posições.
- **Controle:** shorts em datas pareadas por retorno anterior, volatilidade, sentimento e dia da semana, mas sem fluxo extremo.
- **Custo:** round trip do perpétuo e funding liquidado durante toda a posição.
- **Amostra:** 24 meses, ≥40 episódios; blocos de 14 dias.
- **Veredito:** regra comum com **MRE = +0,20 ponto percentual** contra o controle. Estabilidade em percentis 85 / 90 / 95.

**Principal falso positivo:** capturar atividade de intermediação dos ETFs ou efeito específico de seu preço, sem previsão incremental para BTC após a publicação.  
**Esforço:** 3–5 dias. Evidência interessante, mas efeito potencialmente pequeno diante dos custos.

### 5. Mesmo perpétuo, duas exchanges: comprar barato e vender caro

**Tese — duas linhas:**  
Fragmentação de liquidez pode produzir diferenças temporárias entre contratos economicamente equivalentes.  
Com capital previamente disponível nas duas exchanges, a convergência pode remunerar a execução das duas posições sem uma aposta direcional relevante.

**Evidência e qualidade: `estudo revisado` para segmentação e arbitragem; aplicação proposta não replicada.** Makarov e Schoar documentam diferenças persistentes e limites à arbitragem em cripto. Parte importante da evidência envolve mercados e moedas fiduciárias diferentes; ela não prova uma oportunidade atual em dois perpétuos USDT. [Trading and Arbitrage in Cryptocurrency Markets — versão dos autores](https://www.fmg.ac.uk/sites/default/files/publications/DP782.pdf)

**Dados.** `market_snapshots` registra bid/ask por minuto, mas o modelo declara que o livro bruto não é persistido. Isso não basta para demonstrar execução simultânea. Precisamos de livros sincronizados, profundidade, latência e regras dos dois contratos. [market_data.py:5](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:5), [market_data.py:64](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:64)

**Teste pré-registrável:**

- **População:** BTC e ETH, perpétuos lineares USDT equivalentes em duas exchanges previamente fixadas.
- **Variável:** diferença entre bid vendedor e ask comprador, para **500 USDT por posição**, excedendo todos os custos previstos mais **30 bps**, por ≥5 segundos.
- **Execução/horizonte:** simular ordens cinco segundos depois do sinal; se uma posição falhar, zerar a outra e contabilizar o prejuízo. Fechar quando a diferença executável cair a ≤5 bps ou após **seis horas**.
- **Controle:** caixa; atribuir capital integral às duas exchanges, sem transferência durante o episódio.
- **Custo:** quatro execuções, funding de ambos os contratos e perdas por execução incompleta. Não somar spread novamente quando já embutido no bid/ask.
- **Amostra:** 180 dias prospectivos, ≥100 episódios em ≥30 dias distintos; blocos de sete dias.
- **Veredito:** regra comum com **MRE = +0,05% do capital total por episódio**. Estabilidade em excedentes de 20 / 30 / 40 bps; lucro em nível também com atraso de 15 segundos.

**Principal falso positivo:** preços dessincronizados ou impossíveis de executar simultaneamente.  
**Esforço:** 8–12 dias, mais seis meses de coleta. Última na ordem pelo custo de instrumentação e competição.

## ARQUIVOS

Nenhum arquivo criado ou modificado.

O Lab atual exige trabalho adicional para as propostas com short ou várias posições: o sinal aceita apenas `LONG`, e o contexto valida observações de um único mercado. Portanto, proponho **simulações de pesquisa**, não ativação direta de estratégias existentes. [base.py:138](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:138), [base.py:214](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:214)

## TESTES

Não executei backtests, consultas ao banco ou testes automatizados. Fiz leitura dos arquivos e pesquisa de fontes externas. **Existência de tabela não comprova cobertura; nenhuma rentabilidade nova foi medida.**

## MUST-FIX

Antes de qualquer confirmação:

- **Disponibilidade temporal dos dados externos:** calendário revisado ou arquivo FINRA usado antes da publicação cria uma vantagem impossível de negociar.
- **Contabilidade completa de várias posições:** omitir funding pago, caixa reservado ou execução incompleta pode transformar prejuízo em lucro aparente.
- **Transferência para `spot/1`:** um ganho em BTC/USDT pode perder para simplesmente manter SOL. O teste precisa terminar em SOL e usar custo executável para 0,05 SOL; o próprio modelo distingue cotação Jupiter de fill. [spot_desk.py:177](C:/dev/project-hunter/packages/core/hunter_core/db/models/spot_desk.py:177)

## NICE-TO-HAVE

Publicar, junto ao resultado principal, concentração do lucro nos cinco melhores eventos, retorno por capital-dia e desempenho com custos dobrados. Isso ajuda a separar oportunidade recorrente de dependência de poucos episódios.

## O QUE EU FARIA DIFERENTE

Começaria pela **viabilidade do carry**, seguida da **qualidade dos calendários de desbloqueio**. São os dois testes com ligação mais clara entre mecanismo econômico e receita potencial.

Não buscaria mais cinco filtros de preço. O próximo avanço plausível está em pagamentos contratuais, oferta programada e informação externa — com dados que permitam contestar a tese.

## CONCORDO COM

A exigência de lucro em nível, controle de múltiplas tentativas e distinção entre refutação e falta de potência. Também concordo com investigar custos primeiro: a KB-0149 atribui 72% do prejuízo observado **daquela mesa de memes** aos custos; não extrapolo esse percentual para moedas grandes. [KB-0149:37](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md:37>)

## OBSIDIAN

Páginas que deveriam ser atualizadas, **sem alterações nesta rodada**:

- **Proximas Hipoteses** — acrescentar as cinco propostas, prioridade, qualidade da evidência e bloqueios.
- **Strategy Backlog** — distinguir carry de duas posições do diagnóstico de prêmio e registrar dependências do simulador.
- **Fila de Hipoteses** — reservar novos identificadores apenas após fechar os pré-registros; preservar H-027/C1.
- **Mapa de Estrategias** — incluir pagamentos de funding, eventos de oferta, desalavancagem, fluxo de ETFs e arbitragem entre venues.
- **Index** — ligar as fontes externas às novas notas, sem classificá-las como evidência de lucro nosso.
- **Proximas Hipoteses / KB-0017** — reconciliar a descrição antiga do parser de liquidações com o código atual e manter explícita a limitação de amostragem.