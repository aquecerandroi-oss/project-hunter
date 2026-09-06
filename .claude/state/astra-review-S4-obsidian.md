## RESUMO

**As taxas de alvo e lucro têm nomes e denominadores corretos.** Encontrei correções necessárias no PF sem ganhos, no recorte de coorte, na maturação e na descrição da reprodutibilidade/cobertura. A leitura de v1 × v2 como sucessão técnica está suficientemente explícita.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO, como `quant-engineer`.

## TESTES

Não executei SQL no banco nem suítes. Fiz revisão estática contra o schema/worker e recalculei os agregados publicados usando `[decimal]` no PowerShell. Saída real:

```text
momentum v1: alvo=0,8500; lucro=0,7083; media_R=0,305274; PF=2,3973
momentum v2: alvo=0,5000; lucro=0,2222; media_R=-0,436204; PF=0,2460
volume v1: alvo=0,6327; lucro=0,4848; media_R=0,077965; PF=1,1367
volume v2: alvo=0,0000; lucro=0,0000; media_R=-1,281367; PF=0,0000
```

Isso verifica consistência aritmética, **não autentica a extração histórica**. A revisão independente não iniciou por falha da ferramenta de agentes; concluí a conferência diretamente.

## MUST-FIX

1. **PF de volume v2: zero, não desconhecido.**  
   Os seis encerrados avaliáveis têm perdas conhecidas, soma negativa de −7,688202 e nenhum ganho. Portanto, `0 / 7,688202 = 0`. O SQL produz `NULL` porque `SUM(...) FILTER (WHERE r_multiple>0)` recebe conjunto vazio; isso não torna desconhecida a soma dos ganhos dessa população. A explicação “zero inventado” em [EXP-0002:128](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0002-volume-anomaly-v1.md:128) está errada e foi generalizada em [Strategy Performance:38](</C:/dev/project-hunter/obsidian/10-PERFORMANCE/Strategy Performance.md:38>). O [item 9:19](/C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:19) exige nulo **sem perdas**.  
   **Cenário:** uma população inteiramente perdedora aparece como “PF indisponível”, escondendo um resultado conhecido. Usaria `COALESCE` no numerador e manteria proteção do denominador; população sem avaliáveis continua nula.

2. **O SQL não impõe a coorte declarada.**  
   Os filtros de [EXP-0001:93](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:93), [118](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:118) e [167](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:167) não restringem `supporting_features->>'cohort' = 'prospective'` nem `purpose = research_only`.  
   **Cenário:** ao usar o mesmo SQL no próximo plantão após inserir replay, resultados prospectivos e retrospectivos entram juntos. Não há evidência de contaminação nesta extração; há um erro concreto no protocolo reutilizável. Aplicaria ambos os filtros em todas as consultas.

3. **Falta a população com horizonte maturado exigida pelo item 9.**  
   A seleção de avaliáveis considera apenas `terminal AND r_multiple IS NOT NULL`, sem maturação, em [EXP-0001:120](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:120). Isso corresponde ao nome da métrica, mas não satisfaz integralmente o [item 9:19](/C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:19).  
   **Cenário:** encerramentos rápidos entram na média enquanto acompanhamentos mais lentos ainda estão ativos; a composição muda com o tempo de observação. Pelos horários publicados, nenhuma entrada de momentum poderia ter completado quatro horas nessa leitura.  
   Acrescentaria contagens de **maturados/não maturados**, com estados e avaliabilidade dentro desses grupos, usando o horizonte congelado — `expires_at` é persistido como abertura planejada + horizonte em [persist.py:65](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/persist.py:65). Não confundiria “encerrou cedo” com “teve todo o horizonte disponível”.

4. **`read_at` documenta a leitura, mas não permite reproduzi-la.**  
   A ressalva em [EXP-0001:72](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:72) é honesta, porém precisa dizer explicitamente: **“não é uma reconstrução dos estados em `as_of`; os resultados históricos não são recuperáveis por este SQL sem snapshot/histórico preservado”**. Além disso, os comandos colados não estabelecem uma transação com snapshot compartilhado.  
   **Cenário:** um acompanhamento termina entre a consulta de cobertura e a de métricas; ambas recebem o mesmo `read_at` editorial, mas descrevem estados diferentes. Para próximas extrações, usaria uma transação `REPEATABLE READ READ ONLY`. Isso garante consistência durante a leitura; não garante reprodução futura.

5. **A cobertura está declarada como completa, mas a evidência apresentada é parcial.**  
   `LIKE 'late%'` em [EXP-0001:100](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:100) não demonstra que todos os casos sejam `late:delay`. É necessário agrupar pelo motivo exato, conforme [notes-S2:152](/C:/dev/project-hunter/.claude/state/notes-S2.md:152).  
   O heartbeat citado em [EXP-0001:209](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:209) também não representa uma “passada recente” por experimento: os contadores acumulam em memória e recebem avaliações de cada versão em [consumer.py:79](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/consumer.py:79) e [133](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/consumer.py:133).  
   **Cenário:** o leitor atribui as mesmas 400 avaliações indisponíveis a cada estratégia ou interpreta o contador como cobertura da janela inteira. Identificaria esse dado como agregado operacional desde a inicialização do contador, sem quebra por estratégia/motivo; cobertura histórica não medida deve constar como indisponível.

## NICE-TO-HAVE

- Corrigir o resumo do índice: “48 + 66” omite v2; as próprias linhas posteriores mostram 57 e 72 avaliáveis por experimento. [Experiments Index:18](</C:/dev/project-hunter/obsidian/05-EXPERIMENTS/Experiments Index.md:18>)
- Retirar precisão inferencial não calculada: “tamanho amostral efetivo perto de um” e “indistinguível de zero” deveriam virar “dependência não estimada” e “evidência insuficiente para concluir”. [EXP-0001:223](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:223), [EXP-0002:153](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0002-volume-anomaly-v1.md:153)
- A soma escalar de R não depende da ordem; o SQL não produz uma trajetória ordenada por `exit_ts`. Ajustaria essa descrição ou acrescentaria uma consulta cumulativa se houver intenção de mostrar trajetória. [EXP-0001:129](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:129)

## O QUE EU FARIA DIFERENTE

Manteria as avaliações originais e acrescentaria uma errata datada. Na próxima leitura, usaria uma população comum explicitamente filtrada, snapshot transacional único, motivos completos e dois recortes: todos os acompanhamentos e aqueles cujo horizonte já maturou. Preservaria também a evidência necessária para recomputar os agregados históricos.

## CONCORDO COM

- **JOIN sem multiplicação:** `signal_outcomes.signal_id` é chave primária, sustentando a relação 1:1. [agents.py:153](/C:/dev/project-hunter/packages/core/hunter_core/db/models/agents.py:153)
- **Censurados podem contar como entradas:** a censura preserva a entrada já ocorrida. Assim, 67 entradas de momentum v1 incluem dois censurados; 80 de volume v1 incluem um. Isso é correto, desde que “Entradas” seja entendido como contagem histórica sobreposta aos estados. [progress.py:136](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/progress.py:136)
- **Expired/invalidated não foram excluídos dos avaliáveis:** o filtro aceita qualquer terminal com R conhecido; censurados ficam fora. [EXP-0001:120](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0001-momentum-v1.md:120)
- **v1 × v2 não é comparação de variantes de pesquisa:** a sucessão técnica está bem explicada e corresponde ao registro do `--supersede`. Mesmo `params_hash`, isoladamente, não provaria igualdade de código; a justificativa depende também da proveniência registrada. [Experiments Index:75](</C:/dev/project-hunter/obsidian/05-EXPERIMENTS/Experiments Index.md:75>), [notes-S2:238](/C:/dev/project-hunter/.claude/state/notes-S2.md:238)
- Manter `inconclusivo`, custos assumidos explícitos e carteira/PnL/drawdown como não aplicáveis.

## OBSIDIAN

- **EXP-0001 — momentum:** acrescentar errata sobre recorte, maturação, snapshot e cobertura.
- **EXP-0002 — volume_anomaly:** acrescentar correção do PF e as mesmas limitações metodológicas.
- **Experiments Index:** corrigir totais e explicitar requisitos das próximas extrações.
- **Strategy Performance:** corrigir PF sem ganhos e incluir maturação/reprodutibilidade nas definições.
- **Revisões-Astra — avaliação Shadow Lab:** registrar esta revisão e vincular às quatro páginas.