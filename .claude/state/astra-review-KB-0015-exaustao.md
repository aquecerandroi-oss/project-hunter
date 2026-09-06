**RESUMO**

Como `quant-engineer`: **exaustão é uma explicação compatível, mas não identificada pelos resultados; o teto faz sentido como hipótese, porém 12 não tem sustentação apresentada; as duas métricas são distintas, com uma precisão importante sobre suas janelas.**

Não diria que as explicações são “igualmente prováveis”: os dados apresentados não permitem ordená-las.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Não executei testes nem consultas ao banco. Conferi os documentos, as fórmulas e o processamento de outcomes por leitura estática. Os números são os registrados no EXP-0002, não uma reprodução independente nesta sessão.

**MUST-FIX**

**1. Trocar “exatamente a assinatura de exaustão” por “compatível com exaustão”.**

A afirmação está em [KB-0015:49](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0015-volume-relativo-e-o-pico-como-exaustao.md:49). Há três problemas:

- O grupo foi selecionado pelo próprio evento de recuo: a estratégia exige fechamento acima do meio da barra e define invalidação abaixo desse mesmo nível. Isso favorece perdas nesse grupo, sem provar um mecanismo de exaustão ([entrada:162](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:162), [invalidação:241](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:241)).
- A invalidação observada no fechamento é executada na abertura seguinte; encerrado o acompanhamento, as barras posteriores não entram na observação ([walker.py:136](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:136), [walker.py:77](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:77), [walker.py:170](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:170)).
- O MFE médio cobre esse período interrompido. O próprio experimento registra duração média de 1.035,8 segundos e MFE indeterminado para todos os targets, impedindo uma comparação direta das médias entre invalidados e alvos ([EXP-0002:311](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0002-volume-anomaly-v1.md:311)).

**Cenário de falha:** o preço recua abaixo do meio da barra, invalida e depois retoma a alta antes das duas horas. Os números publicados continuam iguais, mas “o pico marcou o fim do movimento” seria falso. Recuo transitório, regime adverso comum e geometria da saída também são compatíveis.

Eu escreveria: “35% dos acompanhamentos resolvidos terminaram por invalidação, com MFE médio observado até a saída de 0,3806 R. Isso motiva investigar falha de continuação, sem identificar exaustão.”

**2. H-KB0015a não confirma nem refuta exaustão como está formulada.**

Comparar `volume_ratio_5m` entre `invalidated` e `target` é um diagnóstico útil de associação. Mas “concentração confirma” e “distribuições indistinguíveis refutam” excedem o que esse diagnóstico responde ([KB-0015:76](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0015-volume-relativo-e-o-pico-como-exaustao.md:76)).

**Cenário de falha:** os maiores ratios pertencem principalmente a mercados ou horários que tiveram pior resultado naquele dia. Surge associação agregada sem mecanismo de exaustão. Na direção contrária, efeitos distintos entre mercados podem se compensar e produzir distribuições agregadas parecidas. Ausência de diferença detectada também não demonstra equivalência.

Reformularia para: **“Investigar se a magnitude do ratio está associada ao resultado sob a regra atual.”** Incluiria stop e expiração, contagens por faixa, geometria entrada–stop–alvo e agrupamento temporal. O próprio EXP registra apenas um dia de observação ([EXP-0002:269](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0002-volume-anomaly-v1.md:269)).

**3. Separar a plausibilidade do teto da justificativa do número 12 e do critério de sucesso.**

Mecanicamente, faz sentido testar uma faixa `4 ≤ volume_ratio_5m ≤ 12`: o código atual calcula o ratio e rejeita somente valores abaixo do piso, sem teto de volume ([volume_anomaly_v1.py:139](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:139)).

**Mas 12 é um parâmetro exploratório arbitrário na evidência apresentada.** Declarar antes da distribuição condicionada reduz liberdade de ajuste posterior; não demonstra que 12 separa continuação de exaustão. Pode ser pré-registrado como escolha não calibrada, sem ser chamado de limiar sustentado pelo mecanismo ([KB-0015:81](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0015-volume-relativo-e-o-pico-como-exaustao.md:81)).

**Cenário de falha:** o teto elimina muitos invalidados, mas também poucos vencedores de grande magnitude. A taxa de invalidação melhora e a expectancy piora. Portanto, reduzir invalidações preservando “taxa de alvo” não basta; é preciso definir denominadores e medir resultado líquido, cobertura e frequência. A queda da taxa de alvo, isoladamente, também não refuta benefício econômico.

Cortaria ainda **“sem gastar uma tentativa”**: um diagnóstico usado para selecionar a próxima hipótese deve constar do histórico de pesquisa, mesmo sem ativação de variante ([KB-0015:97](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0015-volume-relativo-e-o-pico-como-exaustao.md:97)).

**4. Dar denominador explícito a “zero invalidados com lucro”.**

A tabela apresenta 156 invalidados, MFE determinado nos 156 e zero com lucro, mas não explicita quantos desses 156 tinham `R_net` conhecido. Já a decomposição financeira usa **112 invalidados entre 316 avaliáveis com `R_net`** ([EXP-0002:260](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0002-volume-anomaly-v1.md:260), [EXP-0002:314](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0002-volume-anomaly-v1.md:314)).

**Cenário de falha:** uma contagem `R_net > 0` retorna zero ignorando valores nulos; o leitor interpreta “156 perdas verificadas”. Publicaria separadamente total, maturados, `R_net` conhecido, ausentes e positivos. O MFE determinado não resolve a disponibilidade do resultado líquido.

**5. Cortar a generalização bibliográfica sobre reversão em seis meses.**

A passagem afirma inversão do sinal e atribui sua determinação à janela e ao horizonte, sem identificar o estudo específico ([KB-0015:24](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0015-volume-relativo-e-o-pico-como-exaustao.md:24)).

No PDF vinculado, os autores distinguem **volume habitual entre ações** de **choques de volume na própria ação** ao discutir resultados aparentemente contrários. Isso não sustenta tratar ambos como o mesmo indicador cujo sinal simplesmente inverte ao alongar a janela. O arquivo também é uma versão de dezembro de 1998, não a versão publicada de 2001. [Fonte consultada, identificação e introdução](https://rodneywhitecenter.wharton.upenn.edu/wp-content/uploads/2014/04/9901.pdf).

**Cenário de falha:** um efeito associado a diferenças persistentes de liquidez entre ações vira justificativa para filtrar choques intradiários em perpétuos. Cortaria a frase até haver referência e definição operacional verificadas.

**NICE-TO-HAVE**

Sobre a pergunta **(3), sua afirmação está correta**, entendendo “grandezas diferentes” como **indicadores diferentes**, ambos adimensionais:

| Indicador | Denominador padrão | Evidência |
|---|---|---|
| `volume_ratio_5m` | Mediana das 288 barras anteriores de 5 min: **24 h**, excluindo a atual | [parâmetros:68](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:68), [cálculo:137](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:137) |
| `relative_volume_5m` | Mediana das 23 janelas anteriores de 5 min: **115 min**, excluindo a atual | [padrão:36](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/volume.py:36), [cálculo:69](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/volume.py:69) |

A precisão: **ambas usam intervalos consecutivos e sem sobreposição dentro de cada cálculo**. “Contíguas versus disjuntas” não é a diferença; são principalmente **288 versus 23** observações. A feature também usa os últimos minutos disponíveis, enquanto a estratégia exige alinhamento ao fechamento de 5 minutos ([windows.py:77](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:77), [aggregate.py:103](C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:103)).

A baseline sazonal da T2.3 é outra camada, aplicada às leituras da feature; não simplesmente um terceiro denominador intercambiável de volume bruto ([volume.py:3](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/volume.py:3)).

**O QUE EU FARIA DIFERENTE**

Separaria duas perguntas: **o ratio ajuda a selecionar entradas?** e **a invalidação encerra operações que depois recuperariam?** A primeira pede análise de resultados por ratio; a segunda, acompanhamento/replay até horizonte fixo com cobertura verificada. Nenhuma exige declarar exaustão previamente.

**CONCORDO COM**

Manter o experimento inconclusivo, preservar o protocolo, distinguir decomposição de contrafactual e registrar qualquer teto como nova hipótese. Também concordo integralmente em não aplicar o mesmo limiar às duas métricas de volume.

**OBSIDIAN**

- **Volume relativo e o pico como exaustão** — substituir diagnóstico causal por hipótese, reformular H-KB0015a/b e corrigir a sustentação bibliográfica.
- **EXP-0002 — volume_anomaly em modo sombra** — acrescentar esclarecimento datado dos denominadores e limites da interpretação, preservando avaliações anteriores.
- **Features (Feature Engine)** — explicitar 115 minutos versus 24 horas e a diferença de alinhamento.
- **Registro de Tentativas** — registrar o diagnóstico e o teto 12 como escolhas exploratórias, caso a pesquisa prossiga.