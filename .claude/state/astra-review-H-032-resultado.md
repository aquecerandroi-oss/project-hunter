**RESUMO**

**O rótulo “NÃO CONFIRMA — instrumento” está correto.** Não encontrei erro no estimador que altere o resultado atual. O problema do teto de SOL merece registro em **07-BUGS** e compromete a interpretação econômica do contraste global do EXP-M23.

Revisão como `quant-engineer`, em modo OPINIÃO.

- **I1:** falha pela regra congelada “nulo = discordância”; não encontrei conflito entre os bits não nulos.
- **I2:** 463/731 saídas Mayhem com teto, **63,34%**, excedem o limite de 10%.
- Esses portões precedem qualquer confirmação ou refutação; o código respeita essa ordem. Mesmo desconsiderando I1, I2 mantém o rótulo. [Emenda:1](/C:/dev/project-hunter/.claude/state/r89/emenda1.md:1), [h032.py:246](/C:/dev/project-hunter/.claude/state/r89/h032.py:246), [resultado:20](/C:/dev/project-hunter/.claude/state/r89/h032.txt:20).

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisei pré-registro, emenda, errata, análise, testes, SQL, CSV congelado e os caminhos de compra, marca e venda.

**TESTES**

Não reexecutei pytest, bootstrap ou SQL no servidor; **não certifico nesta revisão os “14 testes passam”**. Inspecionei os testes e fiz uma recomputação independente, somente em memória, por PowerShell sobre o CSV. Saída real:

```text
D_adj=0,5352830488; strata=137; kept_M=714; kept_N=1621
mayhem=True; resolved=731; mean=-0,5971145859; capped=463
mayhem=False; resolved=1643; mean=-0,0493716658; capped=0
null_snapshot_flags=239; nonnull_conflicts=0
```

Os pontos conferem com o relatório. A estratificação, os pesos `n_M·n_N/n`, a recomputação dos pesos no bootstrap e o p centrado correspondem à emenda. Não encontrei discrepância material nessa implementação. Isso **não equivale a uma réplica independente dos intervalos**. [h032.py:134](/C:/dev/project-hunter/.claude/state/r89/h032.py:134), [h032.py:183](/C:/dev/project-hunter/.claude/state/r89/h032.py:183), [h032.py:219](/C:/dev/project-hunter/.claude/state/r89/h032.py:219).

**MUST-FIX**

**1. Registrar o defeito do simulador antes de usar esses retornos como evidência econômica.**

A leitura está correta:

- A marca inicial vende contra as reservas **pós-compra hipotética**, sem teto.
- As marcas seguintes e o fechamento usam as reservas do snapshot observado e seu SOL real como teto.
- Esse caminho não acrescenta o aporte hipotético da compra ao saldo usado para limitar a venda. [paper_fill.py:171](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:171), [lab_values.py:84](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_values.py:84), [paper_engine.py:123](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:123), [paper_engine.py:216](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:216).

**Cenário de falha:** reserva real observada zero, compra hipotética de 0,07 SOL e nenhum movimento externo. A compra aportaria `curve_cost_sol` à curva; porém, na fotografia seguinte idêntica, o simulador limita o recebimento a zero, desconta prioridade e pode disparar perda máxima. O dinheiro hipotético sai do custo da aposta, mas desaparece do saldo disponível para vendê-la. O gatilho recebe essa marca limitada. [paper_engine.py:189](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:189).

Título sugerido: **“Paper Mayhem: marcas e saídas limitadas ao saldo observado omitem o aporte da compra hipotética”**.

**Não considero `real_sol + curve_cost` uma correção validada para toda a trajetória.** Ela exige modelagem consistente das reservas e dos eventos posteriores. Também permanece aberta a validade de representar insuficiência de SOL como venda integral com recebimento truncado: é o que `quote_sell` faz, mas isso não demonstra o comportamento on-chain. [curve.py:307](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/curve.py:307).

**2. Avisar explicitamente o EXP-M23 sobre a contaminação diferencial.**

O contraste global inclui **A+B ponderados pelo inverso da probabilidade**; portanto, a parcela Mayhem de B pode fazer as recusadas parecerem artificialmente piores e favorecer a conclusão de que o portão seleciona. Usar o mesmo simulador nos dois braços não elimina erro que incide diferentemente sobre sua composição. [EXP-M23:62](</C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md:62>), [EXP-M23:112](</C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md:112>).

**Cenário de falha:** admitidas sem Mayhem versus recusadas com muitas Mayhem; a perda criada pelo teto aparece como vantagem do portão.

A redação correta é **“o contraste global está comprometido por erro de instrumento na parcela Mayhem das recusadas”**. Os aproximadamente 30% são participação em contagem nessa amostra, não necessariamente participação ponderada no estimador global.

Isso não invalida automaticamente cada contraste restrito a A. Também não autoriza remover Mayhem/B e manter o mesmo alvo confirmatório: a população mudaria.

**3. Corrigir a apresentação do “ponto de inversão”.**

O código imprime sete imputações e seus estimadores pontuais; não encontra um limiar nem recalcula o rótulo para elas. [h032_run.py:119](/C:/dev/project-hunter/.claude/state/r89/h032_run.py:119).

**Cenário de falha:** publicar essa grade como cumprimento da exigência de determinar “qual média dos ausentes muda o rótulo”, embora ela não responda isso.

Para esta execução, a resposta literal é: **nenhum valor imputado muda o rótulo enquanto I1/I2 falharem**. Se quiser um limiar condicionado a instrumento válido, deverá identificá-lo como tal e distinguir cruzamento de zero, MRE e critérios de intervalo. Essa lacuna não muda o veredito atual.

**NICE-TO-HAVE**

- **Precisar os denominadores.** I1 usa 2.468 registros da população, incluindo uma proposta sem aposta. Portanto, “239 fotos discordantes” é impreciso: são 239 registros sem o bit na entrada, incluindo essa ausência. I3 pula entradas sem foto/tokens; o “100%” é entre avaliáveis. Nenhuma dessas diferenças altera os portões aqui. [h032_run.py:23](/C:/dev/project-hunter/.claude/state/r89/h032_run.py:23), [h032_run.py:49](/C:/dev/project-hunter/.claude/state/r89/h032_run.py:49).
- **Explicitar a limitação de I3:** sua aprovação verifica tokens da compra; não valida a execução da venda Mayhem. O retorno “com teto observado” reproduz deliberadamente o mecanismo suspeito. [h032.py:266](/C:/dev/project-hunter/.claude/state/r89/h032.py:266).
- **Preservar a errata temporal.** Os hashes conferem com os prefixos registrados. Carimbos locais apoiam a sequência declarada, mas não constituem prova independente de ausência de consulta anterior. [Fila:370](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:370>).

**O QUE EU FARIA DIFERENTE**

Publicaria assim:

> **H-032: NÃO CONFIRMA — instrumento.** O contraste ajustado registrado favorece não-Mayhem em +0,5353 por SOL no simulador. Entretanto, falharam os portões pré-registrados de completude/concordância do bit e de incidência do teto. O resultado não permite concluir qual grupo renderia mais em execução válida.

Os números pós-hoc informados — −0,854 registrado, −0,027 sem teto e −0,091 com aporte adicional — demonstram **forte sensibilidade da precificação na mesma foto de saída**. O SQL mantém tokens, fotografia e saída selecionada pela trajetória original; não refaz reservas virtuais, gatilhos ou tempo de saída. Portanto, não são retornos de uma estratégia corrigida. [q_capdiag.sql:6](/C:/dev/project-hunter/.claude/state/r89/q_capdiag.sql:6), [q_capdiag.sql:16](/C:/dev/project-hunter/.claude/state/r89/q_capdiag.sql:16).

**Você não pode afirmar:**

- Que Mayhem é pior, melhor ou equivalente **de verdade**.
- Que o veto Mayhem paga, ou que deveria ser removido.
- Que o teto explica **toda** a diferença observada.
- Que retirar o teto recuperaria aqueles retornos na prática.
- Que as saídas sem teto estão livres do problema: marcas anteriores podem ter alterado o gatilho.
- Que a réplica SQL valida o simulador ou replica independentemente a hipótese econômica.

**CONCORDO COM**

Preservar o rótulo, os dados congelados e o diagnóstico como pós-hoc declarado. Não suavizar I1 depois do resultado. Não promover a fatia sem teto a novo primário. Registrar o defeito e a consequência para M23, mantendo família e parada originais.

**OBSIDIAN**

- **Fila de Hipóteses — H-032:** acrescentar resultado, falhas I1/I2, limitação de I3 e alcance estritamente instrumental.
- **Open Bugs:** registrar a omissão do aporte hipotético nas marcas/vendas Mayhem, com cenário sem movimento externo.
- **EXP-M23 — Desfecho das recusadas:** registrar contaminação do contraste global e compartilhamento dos dados com H-032.
- **Revisões-Astra — H-032/R89:** guardar este parecer e distinguir veredito correto de instrumento econômico inválido.
- **Mapa de Estratégias:** classificar H-032 como não confirmada por instrumento, sem conclusão econômica sobre Mayhem.