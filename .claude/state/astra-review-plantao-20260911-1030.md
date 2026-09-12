**RESUMO**

Eu faria **D-P24 primeiro, corrigindo a medida principal**. Depois H-P26. A H-P23 deve receber o carimbo obrigatório agora, mas continua sendo painel: não a colocaria à frente na fila de investigação.

O D-P24 pode esclarecer uma decisão concreta — se vale investigar outra política de saída — usando a coorte existente. **Ainda não há fundamento para retirar o alvo.** Parecer como `quant-engineer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Não executei testes, SQL ou replay. Recalculei em PowerShell a aritmética com os valores fornecidos:

```text
ret_pct=0,5563342; scale_pct=2,0397830; index=0,2727418
range_pct=2,7448156; range_index=1,3456410
```

Isso confirma a conta, **não uma verificação independente das 60 barras ou do DVOL histórico**.

**MUST-FIX**

1. **D-P24: MFE não decompõe o achado do D-P23.**  
   O rascunho pretende explicar o Δ entre 80 e 240 minutos usando máximos acumulados desde a entrada ([rascunho:44](C:/dev/project-hunter/.claude/state/plantao/2026-09-11-1030-lane4.md:44)). Uma trajetória pode atingir +5 ATR aos 60 minutos, estar em +3 aos 80 e terminar em −1 aos 240: MFE enorme, mas contribuição de **−4 ATR** ao achado investigado.

   A medida principal precisa continuar sendo `Δ_i = ret_i(240) − ret_i(80)`, agora decomposta por motivo de saída. MFE/MAE entram ao lado.

2. **D-P24: “depois do stop” exige uma janela depois do stop.**  
   `MFE_240 > 0`, calculado desde a entrada, pode refletir somente uma alta **anterior** ao stop. E `MFE_240 − alvo_realizado` mistura potencialmente excursão bruta em ATR com resultado realizado em outra base. Ambos aparecem na proposta ([rascunho:44](C:/dev/project-hunter/.claude/state/plantao/2026-09-11-1030-lane4.md:44)).

   Separe excursões anteriores e posteriores à saída, com referência e unidade iguais. Nomeie as medidas baseadas em fechamentos como **MFE/MAE de closes**: elas não capturam todo extremo intrabar. Na barra da saída, não atribua ordem temporal que OHLC não revela.

   **Cenário de falha:** alvo → stop → grande alta ser apresentado como dinheiro que uma variante sem alvo capturaria. Essa armadilha já está registrada na [KB-0054:60](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0054-a-cauda-direita-e-o-alvo-fixo-que-a-corta.md:60).

3. **“Cauda, não maioria” ainda é uma interpretação a confirmar.**  
   Média com IC acima de zero e mediana com IC cruzando zero **não demonstram**, sozinhas, que poucas decisões explicam o efeito. A memória dá esse salto ([KB-0079:222](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0079-onde-ganha-e-perde.md:222)). Não detectar deslocamento da mediana não prova sua ausência.

   **Cenário de falha:** procurar um seletor de raros vencedores quando existe um deslocamento mais amplo, porém imprecisamente estimado. Meça contribuição dos decis superiores e sensibilidade à retirada de dias/mercados antes de fechar essa narrativa.

4. **Concorrentes: “nenhum” e “todos” excedem a evidência apresentada.**  
   A lista usada para sustentar a universalidade não documenta sequer o Nautilus naquele item ([rascunho:40](C:/dev/project-hunter/.claude/state/plantao/2026-09-11-1030-lane4.md:40)). Freqtrade documenta duração e motivos de saída; isso não demonstra equivalência nos seis motores. Além disso, vectorbt OSS oferece recortes por índices que permitem construir uma análise por horizonte — embora isso não seja um relatório D-P23 pronto. Fontes: [Freqtrade](https://www.freqtrade.io/en/stable/backtesting/), [vectorbt `range_split`](https://vectorbt.dev/api/generic/accessors/#vectorbt.generic.accessors.GenericAccessor.range_split).

   Eu escreveria: **“Não encontramos um relatório pronto equivalente ao D-P23 nas superfícies inspecionadas.”**  
   **Cenário de falha:** transformar ausência de relatório padrão em vantagem exclusiva do Hunter ou justificativa para comprar PRO.

**NICE-TO-HAVE**

- **H-P23:** aceito **0,27 — menor que a escala diária**, mantendo amplitude **1,35×** separada. DVOL representa volatilidade implícita anualizada de 30 dias; a conversão fornece uma referência diária, não um teste calibrado de surpresa do CPI. [Definição da Deribit](https://insights.deribit.com/exchange-updates/dvol-deribit-implied-volatility-index/). O hype seria chamar o evento de “fraco”, “normal” ou atribuir causalmente a queda do DVOL à resolução de incerteza.
- **H-P26:** boa higiene de conceitos. Eu chamaria `breadth_v2` de **fração em queda em 5 minutos**: não mede diretamente correlação nem dispersão de magnitudes. A definição local é explícita ([EXP-0027:262](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0027-amplitude.md:262)).
- No painel H-P26, destaque que **alto em `breadth_v2` significa mais mercados caindo**, enquanto alto em `breadth_ma` significa mais mercados acima da média. Use somente diárias encerradas e disponíveis, conte dias distintos e declare cobertura. Repetir o mesmo estado diário em centenas de decisões não cria centenas de observações independentes.
- O rascunho acrescenta retorno médio por célula e SMA20 à proposta ([rascunho:52](C:/dev/project-hunter/.claude/state/plantao/2026-09-11-1030-lane4.md:52)). Eu começaria apenas pela tabela de estados e contagens solicitada; essas extensões já abrem novas oportunidades de escolher retrospectivamente a célula atraente.

**O QUE EU FARIA DIFERENTE**

O primeiro D-P24 teria uma tabela por `stop / target / expired`, com:

- n de decisões e dias;
- média e mediana de `Δ_i`;
- contribuição de cada grupo: **`Σ Δ_i do grupo / 542`**;
- contribuição do decil superior e inferior;
- IC por blocos de dia, reamostrando conjuntamente todos os grupos.

As três contribuições precisam recompor os **+0,3007 ATR**, dentro do arredondamento. Isso responde diretamente **de onde veio o movimento adicional**, sem dividir por uma soma total próxima de zero.

Só depois acrescentaria excursões. O CSV atual contém os pontos dos horizontes, não o caminho completo minuto a minuto; portanto, MFE/MAE exigem nova leitura de candles, embora dispensem replay ([SQL:96](C:/dev/project-hunter/infra/scripts/sql/research/2026-09-11-dp23-q01-curva-mtm.sql:96), [SQL:106](C:/dev/project-hunter/infra/scripts/sql/research/2026-09-11-dp23-q01-curva-mtm.sql:106)).

Se a contribuição estiver concentrada em `target`, isso justifica **propor** um teste de política. O motivo da saída é conhecido posteriormente; não pode virar seletor disponível na entrada.

**CONCORDO COM**

Preservar a população da mãe, o ATR congelado, os horizontes 80/240, a separação entre trajetória bruta e resultado de operação, e a ausência de mudança na estratégia viva. Concordo também em manter H-P26 descritiva e não reinterpretar o carimbo da H-P23 depois de observar a amplitude.

**OBSIDIAN**

- **Hipoteses-do-plantao** — definir D-P24 pela decomposição do Δ; excursões como medidas auxiliares.
- **KB-0079 — Onde ganhamos e onde perdemos** — substituir “cauda demonstrada” por hipótese a verificar pela concentração das contribuições.
- **Plantao/2026-09-11** — registrar prioridade D-P24 e restringir as afirmações universais sobre concorrentes.
- **EXP-0027-amplitude** — distinguir direção agregada em 5 minutos de posição relativa à SMA diária, com polaridades e cobertura explícitas.