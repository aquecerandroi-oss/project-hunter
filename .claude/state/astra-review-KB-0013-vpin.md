**RESUMO**

**Manter “DISPUTADA” é justo. Não construir VPIN agora é defensável. A H-KB0013 é parcialmente executável, mas suas conclusões atuais excedem o que as medições demonstrariam.** Eu aprovaria a decisão de prioridade e pediria revisão da justificativa e do protocolo.

Revisão como `quant-engineer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Não executei testes nem consultas ao banco. Conferi código, schema, memória compartilhada e fontes primárias acessíveis. Portanto, confirmo a viabilidade estrutural das medições abaixo, **não a cobertura atual dos dados nem resultados empíricos**.

**MUST-FIX**

1. **“DISPUTADA” está correto; “já sabemos que replica nossas features” não está.**

   Na [KB-0013:24](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0013-vpin-e-a-disputa-sobre-toxicidade.md:24), você transforma resultados de implementações e amostras específicas em conclusão geral. Andersen–Bondarenko sustentam a crítica de ausência de ganho incremental sobre volatilidade futura após controles, mas também enfatizam dependência da classificação e implementação. Isso não demonstra redundância com nossas features em perpétuos. [Reflecting on the VPIN Dispute](https://repec.econ.au.dk/repec/creates/rp/13/rp13_42.pdf).

   A réplica também é mais substantiva que “toxicidade tem componente de volatilidade”: contesta metodologia, interpretação dos resultados e classificação de negócios, além de invocar outras pesquisas. É preciso registrar esses argumentos, mesmo sem considerá-los convincentes. [Rejoinder dos autores](https://www.sciencedirect.com/science/article/pii/S1386418113000293).

   **Correção:** “Literatura revisada por pares, com resultados e interpretação disputados; ganho incremental não demonstrado no nosso contexto.” Revisão por pares e grau de contestação são dois atributos diferentes.

   **Cenário de falha:** uma pesquisa futura de desequilíbrio observado é descartada como redundante sem teste, porque a base registrou como fato uma extrapolação para cripto.

2. **A fração de barras quase vazias não identifica, sozinha, um denominador artificialmente baixo.**

   A implementação usa a mediana das **288 barras anteriores**, exclui a atual e devolve `volume_baseline_unavailable` quando a mediana é zero — [volume_anomaly_v1.py:139](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:139).

   Há três problemas na [hipótese (a):63](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0013-vpin-e-a-disputa-sobre-toxicidade.md:63):

   - “Mediana do mercado” não define período, unidade ou corte temporal.
   - Se for a própria mediana positiva da janela, mais da metade das observações não pode estar abaixo de 1% dela. Essa medida captura a cauda inferior, não prova “dominação”.
   - Volume absoluto baixo não implica razão alta: multiplicar todos os volumes por uma constante positiva preserva `volume/mediana`.

   Além disso, 288 barras contíguas cobrem 24 horas: cada hora UTC contribui com 12 barras. A madrugada não recebe mais observações por ser madrugada.

   **Cenário de falha:** com 145 barras zeradas, a mediana é zero e a estratégia fica indisponível; o relatório conclui justamente o contrário, que o gatilho ficou mais fácil.

   **Correção:** medir separadamente zeros, volumes pequenos, mediana absoluta e razão atual/mediana. Tratar “baixo volume absoluto” e “anomalia relativa” como propriedades que podem coexistir.

3. **Sinais por hora contra volume por hora não explica causalmente o gatilho.**

   A [hipótese (b):69](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0013-vpin-e-a-disputa-sobre-toxicidade.md:69) não sustenta “denominador pequeno, não anomalia”, nem a proporcionalidade ao volume constitui refutação.

   O sinal depende também de fechamento, retorno e ATR — [volume_anomaly_v1.py:155](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:155). E um gatilho verdadeiro só gera emissão quando o episódio está armado e sem acompanhamento aberto — [episodes.py:53](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/episodes.py:53).

   **Cenário de falha:** uma hora movimentada contém vários gatilhos durante um acompanhamento aberto e produz apenas uma emissão. Outra hora, tranquila, contém um novo episódio. O histograma sugere preferência por baixa liquidez, embora o efeito seja bloqueio por episódio.

   **Correção:** distinguir três populações: barras avaliáveis, gatilhos matemáticos e sinais efetivamente emitidos. A distribuição de volume é uma comparação descritiva; o denominador para frequência de gatilhos é o número de oportunidades avaliáveis.

4. **Candles e sinais permitem reconstrução parcial, não a história operacional completa.**

   O schema oferece OHLCV, `quote_volume`, `trade_count`, `taker_buy_volume`, `is_final` e `received_at` — [market_data.py:46](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:46). O envelope dos sinais preserva volume, mediana e razão — [volume_anomaly_v1.py:198](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:198).

   Porém, o contexto combina Postgres com a cauda do Redis, e a elegibilidade usa o universo observado naquele momento — [context.py:59](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/context.py:59). O próprio registro alerta que uma vela recuperada depois passa pelo corte de tempo de mercado, sem provar disponibilidade na decisão — [record.py:49](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/record.py:49).

   **Cenário de falha:** um backfill completa hoje uma janela indisponível ontem. O diagnóstico conta aquela barra como oportunidade perdida pelo gatilho, embora o worker não pudesse avaliá-la.

   **Correção:** separar “reconstruído com dados disponíveis hoje” de “comprovadamente disponível na decisão”. Minuto ausente é lacuna, nunca volume zero; o agregador existente recusa janelas incompletas — [aggregate.py:135](C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:135).

5. **A análise proposta não usa relógio de volume; uma substituição literal destruiria o gatilho.**

   Contar barras de 5 minutos e agrupar por hora UTC continua sendo análise em relógio de tempo, apesar do anúncio na [KB-0013:60](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0013-vpin-e-a-disputa-sobre-toxicidade.md:60).

   **Cenário de falha:** substituir as barras por baldes de volume fixo e manter `volume ≥ 4 × mediana`. Todos os baldes completos têm volume igual; a razão vira 1. Seria necessário estudar outra variável, como duração do balde.

   Também não há reconstrução exata de fronteiras intraminuto com OHLCV: os negócios brutos não são persistidos — [market_data.py:5](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:5). Dividir uma vela proporcionalmente seria aproximação declarada.

**NICE-TO-HAVE**

- Completar a definição: VPIN agrega desequilíbrios absolutos numa janela de baldes; a razão de um balde isolado é apenas um componente. A interpretação como toxicidade exige hipóteses adicionais.
- Acrescentar *Reflecting on the VPIN Dispute*, a resposta de Andersen–Bondarenko à réplica. A controvérsia não termina no terceiro texto.
- Manter a vantagem observacional da Binance: o adaptador preserva o lado agressor e o volume comprador — [streams.py:152](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:152), [streams.py:251](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:251). Isso reduz um problema de classificação; **não identifica quem estava informado**.

**O QUE EU FARIA DIFERENTE**

Renomearia H-KB0013 para **“Composição temporal e escala do denominador da volume_anomaly”**, com duas entregas:

| Medição | Execução e conclusão permitida |
|---|---|
| Composição da janela de cada sinal | Usar `observation_ts`, reconstruir as 288 barras anteriores completas, calcular zeros/quase zeros e comparar mediana e razão com o envelope. Descreve os denominadores dos sinais emitidos. |
| Composição por mercado/hora | Comparar sinais, volume e quantidade de barras completas no mesmo intervalo, separando versão/coorte. Descreve concentração; não explica sua causa. |

Para a primeira, sendo `t` o fechamento da barra do sinal, a janela do denominador é **`[t − 24h − 5min, t − 5min)`**. A barra do sinal fica fora. O envelope usa esse fechamento como `observation_ts` — [volume_anomaly_v1.py:199](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:199).

Fixaria `as_of`, registraria `read_at` e usaria a hora de observação para estudar mercado, deixando a hora de emissão como medida operacional. Versão, coorte e proveniência estão preservadas no registro — [record.py:138](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/record.py:138).

Para comparar mercados, usaria volume em moeda de cotação, com cobertura e unidade explícitas. Somar quantidades de ativos diferentes não produz volume econômico comparável; `quote_volume` é nullable e exige verificação — [market_data.py:55](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:55).

**Cortaria ou reescreveria por falta de sustentação:**

- “Já sabemos que replica” e “qualquer índice herdaria”: extrapolações.
- “O relógio de volume corrige”: troca a amostragem; benefício ainda precisa ser demonstrado.
- “A execução é pior”: não demonstrável apenas com candles e sinais; baixo volume é indicador indireto.
- “Proporcionalidade refuta”: não é consequência necessária da hipótese.
- “Hora e dia perfeitamente confundidos”: com um único dia falta repetição para separar sazonalidade de acontecimentos específicos; essa é a limitação correta.
- “Muda necessariamente ATR, horizonte e expiração”: esses contratos podem permanecer em tempo cronológico. Só mudam se a nova especificação decidir alterá-los.

**CONCORDO COM**

Não construir VPIN agora é uma decisão razoável de prioridade: benefício incremental incerto e custo de validação relevante. Eu preservaria o relógio de volume como ideia de pesquisa, sem assumir que já é a solução. Também concordo em exigir registro de tentativa e janela futura para qualquer variante.

**OBSIDIAN**

- **VPIN e a disputa sobre toxicidade** — manter “DISPUTADA”, delimitar as conclusões bibliográficas e corrigir H-KB0013.
- **Strategy Backlog** — registrar VPIN como não priorizado por benefício incremental incerto; separar o diagnóstico temporal da pesquisa de relógio de volume.
- **EXP-0002 — volume_anomaly em modo sombra** — vincular eventual diagnóstico, com cobertura e limites, sem alterar o protocolo congelado.
- **Revisões da Astra** — registrar este parecer e os cinco must-fix antes da execução da hipótese.