**RESUMO**

**Sua suspeita é pertinente, mas a afirmação central está forte demais.** O código combina volume com **dois filtros direcionais de preço**; a literatura citada não prova que volume só informa magnitude. H-KB0011 é útil como diagnóstico condicionado à estratégia, mas suas regras atuais de “confirmação/refutação” não sustentam as conclusões propostas.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO, como `quant-engineer`.

**TESTES**

Não executei testes, SQL nem recalculei resultados. Fiz leitura estática e conferência bibliográfica: resumo original de Karpoff reproduzido no RePEc, resumo publicado de Gervais et al. e versão de trabalho disponibilizada pela Wharton. Os números da VPS abaixo são registros do Obsidian, não uma nova medição.

**MUST-FIX**

**1. Corrigir “apenas `close > bar_mid`” e “hipótese não declarada”.**

Sobre o nosso código:

- O fechamento deve superar `(high + low)/2`: [volume_anomaly_v1.py:152](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:152) e [linha 162](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:162).
- Também exige retorno entre o piso parametrizado e o teto em ATR%: [linha 172](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:172). Os padrões são **zero e duas vezes ATR%**: [linha 74](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:74).
- Esse retorno é **fechamento contra fechamento anterior**, não fechamento contra abertura: [indicators.py:156](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:156).
- A decisão é explicitamente LONG: [linha 236](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:236).

Portanto, há **posição dentro da amplitude + retorno não negativo**, além do volume. Podem ser insuficientes para prever continuação; o código, sozinho, não demonstra essa insuficiência.

A hipótese de continuação já está declarada no [EXP-0002:13](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0002-volume-anomaly-v1.md:13). O que falta demonstrar é a contribuição incremental de cada filtro.

**Cenário de falha:** desenhar uma comparação ou interpretar os resultados como se retornos negativos também integrassem a coorte, atribuindo ao volume uma seleção que já foi feita pelo filtro de preço.

**2. Separar associação contemporânea, previsão futura e retorno da estratégia.**

Karpoff relata associação com magnitude **e**, em ações, com variação assinada. Isso não equivale a uma lei “volume não contém direção”. Tampouco permite trocar associação preço-volume por previsão da magnitude **posterior**. [Resumo de Karpoff](https://ideas.repec.org/a/cup/jfinqa/v22y1987i01p109-126_01.html).

Gervais et al. estudam justamente informação sobre retornos futuros; seu resumo publicado apresenta visibilidade como explicação **compatível com os resultados**, não mecanismo causal comprovado. [Artigo publicado](https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00349).

**Cenário de falha:** volume acompanha um movimento já ocorrido, mas os retornos seguintes são independentes dele. H-KB0011 não encontra dispersão futura crescente e você interpreta isso como refutação de uma relação contemporânea que continua verdadeira.

**3. `dispersão(R_net)` não identifica magnitude do movimento.**

O denominador de `R_net` é `entrada − stop`; o numerador desconta taxas e funding: [pricing.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:74). Nesta estratégia, stop é a mínima da barra e alvo depende do ATR: [volume_anomaly_v1.py:183](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:183).

Logo, a distribuição mistura movimento, geometria, normalização, custos e regra de saída. Ter `R_net` observado resolve a ausência daquela medida; **não transforma o payoff encerrado em retorno de preço a horizonte fixo**.

**Cenário de falha:** barras de maior volume têm stops proporcionalmente mais distantes. Movimentos posteriores maiores em preço podem produzir dispersão igual ou menor em R. No sentido inverso, custos menores em R podem elevar expectancy sem melhorar previsão direcional.

Por isso, cortaria as conclusões da [KB-0011:75](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0011-volume-confirma-magnitude-nao-direcao.md:75): nem dispersão crescente prova “só volatilidade”, nem expectancy crescente prova transferência de Karpoff ou indica automaticamente alterar `volume_mult`.

**4. Explicitar o que a seleção da coorte permite concluir.**

**A análise não é inútil.** Ela estima diferenças entre sinais emitidos pela regra existente. Não estima o efeito isolado do volume nem compara a estratégia com ausência do filtro: o próprio código exclui razões abaixo do limiar e aplica os filtros de preço antes de emitir: [volume_anomaly_v1.py:155](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:155).

Há ainda seleção por disponibilidade de resultado. A avaliação registra **352 avaliáveis, dos quais 36 sem `R_net`**, restando 316; os excluídos têm composição diferente no proxy sem funding: [EXP-0002:364](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0002-volume-anomaly-v1.md:364).

**Cenário de falha:** o quartil superior concentra outro conjunto de mercados, horários ou exclusões de funding. Sua expectancy sobe mesmo sem relação incremental entre volume e direção. Isso pode inverter a conclusão agregada.

Defina quartis antes de excluir resultados ausentes, explicite maturação e apresente cobertura por quartil. `target/(target+stop)` e taxa de invalidação são diagnósticos da regra; não identificam, sozinhos, continuação ou exaustão.

**5. Substituir “short custa o mesmo que long”.**

Não depender do empréstimo da ação não implica simetria de custo total. Funding positivo transfere de longs para shorts; negativo faz o contrário. [Documentação da Bybit](https://www.bybit.com/en/help-center/article/Funding-fee-calculation).

**Cenário de falha:** descartar antecipadamente qualquer mecanismo direcional porque “a assimetria não existe”, ou avaliar uma candidata short pressupondo custos idênticos apesar de atravessar funding.

**NICE-TO-HAVE**

Sobre **Gervais/Kaniel/Mingelgrin**, você está certo quanto à distância de aplicação e exagera no “não diz nada”. O resultado em ações, com formação diária/semanal e avaliação posterior mensal, **não valida** uma entrada de duas horas com barreiras em perpétuos. Serve como motivação para investigar; não prova nem impede transferência. A versão de trabalho distingue explicitamente seu estudo preditivo das relações contemporâneas anteriores. [Wharton, introdução](https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2014/04/9901.pdf).

Eu também cortaria ou qualificaria:

- **“0,53% e 0,68%”**: retirar até identificar tabela, carteira e versão exatas. Não confirmei essa atribuição na versão publicada.
- **“Quartis medem hora do dia tanto quanto volume”**: substituir por “podem confundir volume com horário e mercado”; a intensidade não foi medida.
- **“Invalidação no quartil superior demonstra exaustão”**: manter apenas como hipótese entre explicações concorrentes.
- **Taker imbalance como solução sugerida pelo resultado**: manter como candidata independente. Fracasso de um filtro não valida outro.
- Corrigir a referência do envelope: `volume_ratio_5m` está na [linha 212](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:212), não 214.

**O QUE EU FARIA DIFERENTE**

Manteria H-KB0011, renomeada para **“Associação entre volume relativo e resultados dentro da coorte emitida”**.

Faria duas leituras separadas:

1. **Diagnóstico operacional:** quartis com contagens, exclusões, geometria alvo/risco, custos em R, expectancy, dispersão e modos de saída. Sem interpretação causal.
2. **Hipótese de preço:** retorno assinado e absoluto até um horizonte fixo posterior à decisão, independentemente da saída da estratégia, verificando cobertura das velas. Para medir contribuição incremental do volume, incluir também oportunidades elegíveis que não passaram pelo limiar.

Congelaria cortes e hipótese antes da janela futura; trataria mercados simultâneos e sinais próximos como dependentes. Um único dia permite descrição, não confirmação robusta.

**CONCORDO COM**

Concordo em questionar a ponte entre pico de atividade e continuação compradora, investigar a coorte existente e não ativar variantes automaticamente. Minha correção central seria:

> **Volume associado à magnitude não basta para justificar continuação. Nossa estratégia acrescenta dois filtros de preço, cuja contribuição preditiva ainda precisa ser isolada e testada.**

**OBSIDIAN**

- **KB-0011 — Volume confirma magnitude, não direção:** corrigir a tese, as afirmações bibliográficas e os critérios de confirmação/refutação.
- **EXP-0002 — volume_anomaly em modo sombra:** acrescentar o diagnóstico condicionado à seleção, geometria e cobertura, preservando hipótese e protocolo congelados.
- **Revisões Astra — KB-0011:** registrar a distinção entre associação contemporânea, previsão futura e distribuição de payoff.