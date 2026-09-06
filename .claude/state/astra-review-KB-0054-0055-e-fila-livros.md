**RESUMO**

Eu manteria **T-005 → L1 → L2 → L3 → L4** como ordem de experimentos. **D-NULL ficaria como diagnóstico metodológico separado**, sem bloquear os primeiros testes.

T-005, L1 e L2 fazem perguntas distintas sobre a **mesma família de políticas de saída**. Se forem avaliadas na mesma janela para escolher uma política, recomendo uma família confirmatória conjunta. Nenhuma das quatro candidatas precisa ser descartada por impossibilidade estrutural.

Sobre as notas: o encerramento do acompanhamento está confirmado; “MFE nunca ajuda” é excessivo; **quatro horas podem limitar a cauda, mas ainda não foram demonstradas como o gargalo**.

Atuei como `quant-engineer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Revisão estática com `Get-Content` e `rg`, incluindo os testes existentes. **Não executei pytest, SQL ou replay**; não confirmei cobertura atual nem resultados empíricos das variantes. Consultei também a fonte primária de Clenow e a documentação estatística de Holm.

**MUST-FIX**

**1. KB-0054: “para de consumir barras” precisa virar “para de incorporar barras ao resultado”.**

O walker primeiro executa `list(bars)` e somente depois verifica `progress.finished` dentro do laço. Portanto, consome/materializa o iterável inteiro, mas não aplica novas transições depois do término. [walker.py:169](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:169)

No fluxo operacional, acompanhamentos encerrados não são selecionados pelo carregamento de abertos; há também retorno imediato antes de carregar velas quando `progress.finished`. [tracking_repo.py:161](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/tracking_repo.py:161), [outcomes.py:177](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/outcomes.py:177)

**Cenário:** um gerador entrega alvo na segunda barra e milhares depois. Todas são materializadas, embora nenhuma posterior altere o outcome. A conclusão sobre ausência de acompanhamento pós-saída está certa; a descrição literal do consumo, inclusive no meu parecer anterior, estava imprecisa.

Está confirmado também que os três alvos são gravados, mas o plano reconstruído usa somente `virtual_targets[0]`. [record.py:137](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/record.py:137), [persist.py:59](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/persist.py:59), [tracking_repo.py:102](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/tracking_repo.py:102)

**2. MFE/MAE: insuficientes para o contrafactual completo, mas não inúteis nem sempre nulos juntos.**

A implementação determina cada extremo separadamente, comparando seu limite inferior com o superior. Pode haver **MFE conhecido e MAE desconhecido**, com `ambiguous=true`. [excursions.py:135](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/excursions.py:135)

Existe um teste escrito exatamente para esse caso: espera MAE nulo, MFE numérico e ambiguidade verdadeira. Não o executei nesta rodada. [test_shadow_outcomes.py:199](C:/dev/project-hunter/services/strategy-worker/tests/test_shadow_outcomes.py:199)

Além disso, uma saída na abertura incorpora `exit_observed`: um gap favorável pode produzir MFE acima do alvo creditado. [excursions.py:116](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/excursions.py:116)

Eu substituiria as linhas 55–57 da nota por:

> Os MFE/MAE atuais descrevem o acompanhamento sob a política vigente. Podem demonstrar excursões e impor limites, inclusive além do alvo em gaps, mas não identificam a distribuição de resultados de políticas que continuariam depois da saída.

**Cenário:** alvo 1 → stop → alvo 3. A máxima posterior não identifica sucesso do braço de alvo 3. Mesmo extremos completos até quatro horas não substituem a ordem das saídas concorrentes.

**3. Quatro horas limitam duração; não provam qual regra está destruindo valor.**

O padrão é `horizon_s=14400`; o prazo começa na abertura de entrada. Na abertura do horizonte, stop e alvo têm precedência sobre o rótulo `expired`. [momentum_v1.py:90](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:90), [progress.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/progress.py:74), [walker.py:71](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:71)

Logo:

- **Bem fundamentado:** “o horizonte pode limitar a captura de movimentos mais demorados”.
- **Retiraria:** “qualquer cauda é truncada em quatro horas”, se significar teto de magnitude do retorno.
- **Retiraria:** “o resultado seria sobre o horizonte, não sobre o alvo”, nas linhas 81–82. Variar somente o alvo mede seu efeito **condicionado ao horizonte de quatro horas**.
- **Não concluiria:** “alongar resolveria”. Isso exige outro contraste.

**Cenário:** aumentar o alvo converte um ganho em expiração com perda. Esse é um efeito válido da mudança de alvo sob quatro horas. Nada informa se, na quinta hora, haveria recuperação ou mais perda.

Para identificar interação entre alvo e prazo, seria necessário posteriormente cruzar ambos, com alternativas pré-declaradas. **Não acrescentaria esse cruzamento ao primeiro lote.**

**4. Retiraria a associação de Clenow com piramidação e a certeza de que alvo fixo remove “a parte que paga”.**

As linhas 29 e 89 atribuem papel central à piramidação. Nas regras públicas, Clenow apresenta dimensionamento por ATR, diversificação e saída móvel; nos comentários assinados, rejeita explicitamente piramidação. [Regras e respostas do próprio Clenow](https://www.followingthetrend.com/the-trading-system/trading-system-rules/)

**Cenário:** usar essa atribuição para adiar toda investigação de cauda até existir piramidação cria uma dependência que a fonte não sustenta.

“Qualquer alvo remove exatamente a parte que paga” também antecipa o resultado: realizar antes de uma reversão pode melhorar o resultado. Eu escreveria **“um alvo fixo pode impedir a captura de grandes movimentos; seu efeito líquido precisa ser medido”**.

**5. A métrica de cauda e o critério de refutação precisam ser operacionais.**

A nota propõe contribuição do decil superior dividida pelo `R_net` total e refutação por ausência de “cauda mais longa”. [KB-0054:69](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0054-a-cauda-direita-e-o-alvo-fixo-que-a-corta.md:69)

**Cenário:** soma total próxima de zero gera percentuais enormes; soma negativa produz uma “contribuição” negativa dos melhores ganhos. Uma cauda direita maior também pode coexistir com média pior.

Eu usaria:

- **Primária:** diferença média pareada de `R_net`, com efeito mínimo relevante declarado.
- **Secundárias:** quantis, média do decil superior, soma desse decil dividida pelo número total de entradas, pior decil e duração.
- **Conclusão:** ausência de evidência de melhora não equivale a refutação; é preciso incerteza suficiente para excluir o benefício definido.

**6. KB-0055: manter a conclusão, retirar as justificativas excessivas.**

Concordo em não criar um braço “Douglas”. Mas retiraria:

- “o livro não apresenta medições” e “não há teste”, quando a própria nota declara que o livro não foi lido;
- “experiência clínica”, sem fonte que sustente essa caracterização;
- “as regras já existem, o que é a melhor evidência de que valem” — existência não valida eficácia;
- a proibição indistinta de “avaliação antes do fim”: **monitoramento descritivo diário pode continuar**; conclusão inferencial antecipada ou parada oportunista é outra coisa.

Essas passagens estão em [KB-0055:22](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0055-douglas-o-livro-que-nao-vira-hipotese.md:22) e [KB-0055:38](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0055-douglas-o-livro-que-nao-vira-hipotese.md:38).

**Cenário:** chamar o relatório diário de tentativa inválida contradiz o protocolo da T-005, que permite leituras descritivas e reserva a inferência para o fechamento. [KB-0006:100](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo.md:100)

**NICE-TO-HAVE**

A fila pode ficar assim:

| Item | Meu parecer |
|---|---|
| **T-005** | Primeiro. Já tem pergunta, quatro braços e contrastes definidos. |
| **L1** | Segundo. Incremento pequeno sobre a infraestrutura de replay da T-005. |
| **L2** | Terceiro. Avaliável, mas exige saída móvel e semântica explícita para ausência de alvo. |
| **L3** | Depois de D-ER; congelar um limiar antes da validação. |
| **L4** | Depois de D-CONTR; fechar o estimador antes de chamá-la “especificada”. |
| **D-NULL** | Diagnóstico separado; útil, mas não requisito para comparar saídas nas mesmas entradas. |

**L2 não é totalmente redundante com a invalidação.** O contraexemplo da KB-0045 funciona: depois de a janela móvel eliminar os fechamentos anteriores ao rompimento, seu mínimo pode superar o nível fixo de invalidação. Isso cabe nas quatro horas. [KB-0045:92](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao.md:92)

**L4 ainda contém uma ambiguidade importante:** ATR de Wilder com períodos 8/32 não significa calcular sobre apenas 8/32 barras. O helper exige `period+2` e o resultado depende da origem e do histórico de suavização. Fixaria períodos, histórico utilizado, seed e término em `t−1`. [indicators.py:70](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:70)

**D-NULL é avaliável como benchmark reconstruído, não como prova limpa de habilidade da entrada.** Um controle que nasce abaixo do nível de rompimento pode ser invalidado quase imediatamente; isso mistura seleção e invalidação. A própria nota reconhece essa limitação e a ausência de intercambialidade demonstrada. [KB-0049:71](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0049-walk-forward-que-nao-temos-e-o-nulo-que-nunca-calculamos.md:71)

**O QUE EU FARIA DIFERENTE**

**Declararia um bloco de saídas, preservando os contrastes distintos.**

Compartilhar entradas, sozinho, não determina a família estatística. Aqui, porém, a finalidade proposta é procurar uma política melhor dentro do mesmo conjunto de alternativas. Para essa finalidade, recomendo:

| Pergunta | Contrastes primários |
|---|---|
| T-005 | INV-B − base; INV-C − base; INV-E − base |
| L1 | alvo 3 − base; alvo 4,5 − base |
| L2 | NOTGT − base; CHAN − NOTGT |

São **oito políticas únicas, incluindo uma base compartilhada, e sete contrastes**, sem cruzar todas as combinações.

`INV-B` não duplica `EXIT-NOTGT`: o primeiro remove invalidação e conserva alvo; o segundo remove alvo e conserva invalidação. [KB-0006:70](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo.md:70), [KB-0045:75](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0045-turtles-a-entrada-que-ja-temos-e-a-saida-que-nao.md:75)

Aplicaria **Holm a 5% sobre os sete testes**, com p-valores válidos para a dependência temporal. Holm aceita dependência entre testes; não conserta p-valores calculados tratando entradas correlacionadas como independentes. [Documentação de Holm no R](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html)

Esse conjunto não autoriza automaticamente declarar CHAN superior à base nem combinar o vencedor da T-005 com o vencedor de L1. Essas seriam comparações adicionais.

**Separar em três famílias é defensável somente com objetivos confirmatórios e orçamento de erro previamente delimitados.** Dar nomes diferentes ou usar janelas diferentes não garante, por si só, controle de erro da busca inteira.

**Para começar mais rápido:**

1. **Reproduzir a base** a partir dos registros, conferindo saída, preço e R.
2. Fazer o primeiro piloto técnico **INV-A versus INV-B**, sobre entradas efetivas da base. É o menor contraste que responde se a invalidação acrescenta valor.
3. Para executar **a T-005 como está proposta**, completar INV-C/E: são quatro braços, não dois.
4. Acrescentar L1 depois; manter D-ER/D-CONTR como observação, sem filtros ativos.

Se Everton preferir confirmar apenas A/B primeiro, isso precisa ser declarado **antes da nova janela**, como redução explícita do escopo; não se eliminam C/E depois de olhar resultados.

As entradas devem permanecer efetivamente idênticas. Aumentar o alvo altera a própria validação `stop < entrada < alvo`, podendo admitir entradas que a base recusaria. Rodar versões independentes também altera ocupação e rearme. [walker.py:45](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:45), [episodes.py:57](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/episodes.py:57)

O primeiro replay pode produzir aprendizado operacional rapidamente. **Confirmação continua exigindo janela futura, maturação e cobertura**, sem converter funding desconhecido em zero. O piso de 100 outcomes e 30 dias não substitui cálculo de potência. [KB-0006:104](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0006-invalidacao-stop-por-atr-ou-saida-por-tempo.md:104)

**CONCORDO COM**

- T-005 permanece prioritária.
- L1 e D-TAIL são a mesma tentativa.
- D-ER e D-CONTR precedem os filtros.
- Douglas fica como nota de processo.
- O horizonte merece uma hipótese posterior, sem antecipar que seja o culpado.

**OBSIDIAN**

- **KB-0054 — A cauda direita:** corrigir consumo de barras, nulidade das excursões, causalidade do horizonte, piramidação e métricas de cauda.
- **KB-0055 — Douglas:** limitar afirmações às fontes consultadas e distinguir monitoramento de inferência antecipada.
- **Strategy Backlog:** preservar T-005 primeiro; declarar o bloco de saídas e separar diagnósticos de variantes.
- **Registro de Tentativas:** explicitar família, contrastes, calendário e eventual piloto A/B antes da coleta.
- **KB-0045 — Turtles:** vincular os dois contrastes de L2 à família conjunta, mantendo sua contribuição possível dentro de quatro horas.
- **KB-0053 — Contração:** fechar períodos, seed e histórico dos ATRs antes da especificação do braço.