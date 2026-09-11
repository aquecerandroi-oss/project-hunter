**MUST-FIX**

- **D-P19 precisa converter R em dinheiro corretamente.** Expectancy em R não determina notional sem distância do stop. Cenário de falha: dimensionar pela meta, aumentar impacto e destruir a própria expectancy usada na conta. Se a expectancy líquida for ≤ 0, não existe tamanho positivo que resolva.
- **D-P20 mistura etapas.** `E − fechamento` mede emissão pela exchange; `recepção − E` mede transporte + processamento até a recepção registrada. O indicador atual mede **barra→decisão**, não decisão→ordem ([decide.py:255](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/decide.py:255)). Confundir os dois pode declarar execução rápida sem medir ordem alguma.
- **D-P18 não pode escolher b pelo primeiro afastamento de 50.** Isso seleciona o nulo pelo resultado observado. Cenário: encontrar um bloco favorável por tentativa e produzir significância artificial. Permutar os mesmos R continua preservando a média, qualquer que seja b; a separação A/B já está registrada em [Hipoteses-do-plantao.md:33](/C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:33).
- **Os custos do Sentinel não fecham como decomposição aditiva:** +0,035→−0,091 implica taxa de 0,126 R; −0,091→−0,243 implica slippage incremental de 0,152 R, não 0,187 R. Sem reconciliar população/denominador, não importar esses coeficientes. A inconsistência está na própria [metodologia](https://github.com/blitzcrieg1/sentinel-trader-research/blob/main/docs/METHODOLOGY.md).

**RESUMO**

Eu faria **D-P19 primeiro**, D-P20 como diagnóstico operacional seguinte e H-P19 como primeiro experimento de seleção. Papel: `quant-engineer`, OPINIÃO.
D-P19 responde diretamente se a meta cabe economicamente; H-P19 pode escolher melhor entre candidatos e ainda assim escolher perdedores.

**O QUE EU FARIA DIFERENTE**

Para D-P19, calcularia `lucro esperado/dia = câmbio × Σ E[Nᵢ × distância_stopᵢ × R_líquidoᵢ(Nᵢ)]`, com apostas únicas, ocupação, custos dependentes do tamanho e capital simultâneo.
Compararia **giro diário de entradas e saídas** com volume diário; ordem com liquidez no horizonte de execução. **5% é hipótese de cenário**, não capacidade comprovada. A KB-0070 cobre somente ask, durante 11 segundos ([KB-0070:37]( /C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0070-a-tabela-de-capacidade-quantos-mercados-suportam-cada-tamanho.md:37)).
Para D-P20: finais `x=true`, fechamento exclusivo, emissão, recepção, decisão e ordem separados; p50/p95, n e conexão por mercado. O parser já distingue esses timestamps ([streams.py:258](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:258)). Os 16 mercados de pesquisa não demonstram 16 assinaturas nem uma conexão única.
**H-P19 é testável nos 90 dias como exploração; não como confirmação limpa**, se esse histórico já orientou as versões. Dez versões correlacionadas × poucas janelas não viram dezenas de replicações independentes.
Congelaria seleção por PF versus robustez, mesmo orçamento/número de escolhidas, opção de não selecionar nenhuma e contraste primário de Δexpectancy líquida na janela seguinte; seleção só no treino, fronteiras sem operações vazando e confirmação prospectiva.
Perturbação de entrada exige reexecutar preço, geometria, ocupação e saída; +1 barra é estresse severo de timing, não reprodução de atraso de 2 s.
**b em operações não transfere para dias**, nem dividindo pela média de trades/dia. Mediria dependência temporal conjunta dos resultados, perdas e exposição; escolheria blocos no treino e declararia sensibilidade em dias, preservando simultaneidade entre mercados.
Rank de MDD depende da convenção de comparação: 43–44 e 56–58% abaixo de 50 não identificam duração da dependência nem demonstram capacidade preditiva.

**CONCORDO COM**

Robustez a custos merece prioridade sobre mais um gate de regime. Mas maior **fração de configurações lucrativas** não demonstra maior **R médio**; essa passagem é precisamente a hipótese nova.
O [pacote Gatto](https://github.com/DaruFinance/Monte-Carlo-paper) não inclui dados brutos nem as configurações: tabelas publicadas não são reprodução independente; 437 mil configurações também não são 437 mil observações independentes.
O [Sentinel](https://github.com/blitzcrieg1/sentinel-trader-research/) declara backtest/paper, sem histórico live longo. Transfere o método de falsificação; não transfere automaticamente yield, capacidade MEXC, custos ou carry spot+perp para nossa estratégia direcional.
Relatos de 1–3 s justificam medir. Os [250 ms da Binance](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Kline-Candlestick-Streams) são cadência de atualização, não garantia de entrega do fechamento; “200 streams” de fórum não deve virar limite atual sem conferir endpoint e documentação.

**NICE-TO-HAVE**

Publicar cobertura, incerteza e cenários de custo por mercado; nenhuma contagem dos 16 acima do teto pode ser inferida só das fontes.

**ARQUIVOS / TESTES**

Nenhum arquivo alterado; testes/replay não executados. Rascunho indicado ausente neste checkout; tabelas detalhadas e threads não puderam ser reconferidas integralmente.

**OBSIDIAN**

- **Hipoteses-do-plantao** — registrar prioridade, protocolo exploratório da H-P19 e correção do b da D-P18.
- **KB-0070 / KB-0087** — distinguir giro, capacidade e capital; separar emissão, recepção, decisão e ordem.
- **Plantao/2026-09-11** — registrar limites de transferência, inconsistência dos custos e fontes ainda não verificadas.