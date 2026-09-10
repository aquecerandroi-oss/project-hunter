**RESUMO**
Testaria **D-P9 primeiro; H-P4 seria o primeiro teste formal**, com H-P2 instrumentada em paralelo. Papel: `quant-engineer`, modo OPINIÃO.
D-P9 resolve a pergunta imediata: perda disseminada, concentração em ZEC, repetição entre versões ou custo? Uma manchete não distingue essas causas.

**ARQUIVOS**
Nenhum criado ou modificado.

**TESTES**
Não executei SQL nem testes do Lab; consultei memória, código e fontes oficiais. Os −31/−34 R são os números fornecidos, não uma medição minha.

**MUST-FIX**

- **Relógio e denominador:** decompor por mercado × versão × episódio, com N, soma e média de R, bruto/custos/funding; separar horário da decisão, entrada e saída. Cenário: stops realizados às 21h de entradas anteriores levam a proibir a hora errada.
- **Direção não discrimina esta implementação:** ela emite `LONG` ([mean_reversion_v1.py:315](/C:/dev/project-hunter/packages/core/hunter_core/strategies/mean_reversion_v1.py:315)). “Tudo perdeu comprado” não identifica ZEC; uma queda comum pode atingir os 16.
- **H-P4 nasceu após observar a pior hora:** 09/09 é descoberta, não confirmação. Congelar janela e contraste, testar período reservado, reamostrar dias conjuntamente entre mercados/versões e controlar multiplicidade; 420 operações não equivalem a 420 observações independentes.
- **A janela está mal nomeada:** em setembro, ações fecham às **20:00Z**; `[20,22)` cobre duas horas após o fechamento. Fixar UTC testa relógio UTC; ancorar em Nova York testa sessão e exige ajuste sazonal. [NYSE](https://www.nyse.com/markets/hours-calendars)
- **H-P5 tem mecanismo presumido errado:** comprar recuo em tendência ascendente não implica perder numa alta parabólica; o perigo plausível é comprar durante sua reversão. A regra exige tendência de alta ([mean_reversion_v1.py:201](/C:/dev/project-hunter/packages/core/hunter_core/strategies/mean_reversion_v1.py:201)). Banir ZEC pela manchete pode retirar vencedores.
- **US$ 1.240,92 não está comprovado como preço das 16:53:** aparece num widget separado do texto na [KuCoin](https://www.kucoin.com/news/flash/zcash-surges-above-1-000-amid-short-liquidations-and-grayscale-etf-growth). Calcular retorno de sete dias em candles Binance anteriores a cada decisão; “só ZEC qualifica” permanece por verificar.

**NICE-TO-HAVE**

- **Binance:** funding padrão em 00/08/16Z; cadência de quatro horas inclui 20Z, e cadência horária inclui **21Z**. Conferir settlements históricos por símbolo; configuração atual não prova a de ontem. [Regras oficiais](https://www.binance.com/en/support/faq/detail/360033525031)
- Não encontrei fechamento geral/rebalanceamento Binance às 21Z para esses contratos; o **ALL Index rebalanceia às 08:01Z**. [Binance](https://www.binance.com/en/support/announcement/detail/743a662924474669ba16c368722b3c64)
- **Mecanismo externo relevante:** CME cripto tem manutenção **16:00–16:02 Chicago = 21:00–21:02Z** nesta data. Menor capacidade de hedge pode afetar liquidez Binance — hipótese, não causa demonstrada. Comparar spread, profundidade, basis e fluxo antes/depois, em vários dias. [CME](https://www.cmegroup.com/articles/faqs/frequently-asked-questions-cryptocurrency-futures.html)

**O QUE EU FARIA DIFERENTE**
H-P5 começa como sensibilidade com/sem ZEC e retirada de cada mercado; três episódios não garantem potência. H-P6 fica por último: volatilidade baixa não implica reversão lucrativa, e janelas móveis de 30 dias têm forte dependência; separar ganho bruto de pedágio.
O pano macro continua contexto: a [Crypto Times](https://www.cryptotimes.io/2026/09/10/bitcoin-gives-up-gains-as-yields-rise-after-6b-treasury-buyback/) situa a aceleração perto de **15Z**, chama US$ 77.600 de mínima de **24h** e informa recompra em **10/09**, liquidação em 11/09. Isso não estabelece queda máxima→mínima nem causalidade às 21Z.

**CONCORDO COM**
Carimbar H-P2 prospectivamente, sem mudar decisão: **PPI 10/09 e CPI 11/09, ambos 12:30Z/09:30 BRT**. [BLS](https://www.bls.gov/schedule/2026/09_sched.htm)
**FOMC 16/09: decisão/projeções 18Z; coletiva 18:30Z**; registrar eventos separadamente, fonte e versão do calendário. [Calendário](https://www.federalreserve.gov/newsevents/2026-september.htm), [projeções](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)

**OBSIDIAN**

- **Fila de hipóteses do plantão de mercado** — registrar prioridade, relógios, período reservado e limitações de H-P5/H-P6.
- **Plantão de mercado — 2026-09-10** — registrar correções BLS/Tesouro/KuCoin e manutenção CME como hipótese.
- **Funding em memes — a cadência antes do sentimento** — acrescentar verificação histórica por símbolo às 21Z.