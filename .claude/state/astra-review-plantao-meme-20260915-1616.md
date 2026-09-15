## RESUMO

**Testaria primeiro o item 2, M-D8:** a nova fronteira exige verificar se continuamos interpretando corretamente contas e eventos. Depois, validaria HR; Mayhem entra como atualização de M-D11. **A coleta bruta de HR pode começar em paralelo**, sem esperar sua validação como exposição.

**M-D13:** prefiro ampliar **M-D9**, cujo objeto já é validar fontes substitutas contra a cadeia, com cobertura, atraso e custo. REST, board e imc acrescentam fontes ao mesmo diagnóstico. [Fila:135](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:135)

**M-P39:** os controles são obrigatórios em **M-P34**. Uma linha própria só se justifica pela pergunta diferente: **previsão aos cinco minutos**, com exposição REST disponível naquele momento. M-P34 congela exposição na criação; não devemos substituir silenciosamente esse marco. [Fila:134](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:134)

## ARQUIVOS

Nenhum modificado. Na versão consultada, M-D13 e M-P39 **já constam da fila**; as correções abaixo também se aplicam a essas linhas.

## TESTES

Revisão documental e inspeção de brutos locais. Não executei testes, consultas externas nem recalculei todas as estatísticas.

## MUST-FIX

1. **Corrigir a cronologia da novidade.** Escrever “flag observado pela primeira vez em 15/09; introdução situada entre as leituras de 12/09 e 15/09”. Não sabemos que apareceu **no mesmo dia** do deploy. `ProgramData.slot` informa o último deploy observado; não exclui upgrades intermediários. Duas fronteiras conhecidas delimitam pelo menos três períodos, não “dois valores” históricos completos. **Falha:** atribuir a REST ao upgrade errado e misturar versões. [Rascunho:53](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1616-lane3.md:53)

2. **Separar presença da chave, positivos e concordância.** Temos positivos na lista e nos boards; imc apresentou **seis respostas válidas, todas falsas, e quatro 404**; detalhes eram dez Mayhem negativas. Isso não valida concordância positiva entre fontes. Exigir mesmos mints, referência on-chain com decoder validado, tolerância temporal e classes ausente/erro/valor desconhecido distintas. Concordância entre APIs pode refletir origem compartilhada. **Falha:** um caminho que sempre devolve `false` passar na validação. [Rascunho:25](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1616-lane3.md:25)

3. **Corrigir o desfecho de M-P39 no marco L.** Prever conclusão em **(L, criação + 24 h]**, entre as ainda não concluídas em L; publicar as anteriores separadamente, mantendo a contabilidade da coorte inteira. Retenção precisa de referência e horizonte próprios; migração anterior a L não pode fornecer informação futura ao preditor. **Falha:** premiar HR por “prever” graduação já ocorrida. A própria M-P37 já explicita essa distinção. [Fila:140](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:140)

4. **Rebaixar “HR nasce clone” à observação exata.** São **cinco BARRON entre sete positivos REST, com sete identificadores de criador distintos no conjunto**. Repetição de símbolo neste recorte não mede `symbol_dup_24h`, identidade econômica nem estado na criação. Controlar quote pelo mint, com sobreposição entre braços; agrupar clones/criadores na avaliação e confirmar em período posterior. **Falha:** aprender uma campanha BARRON e chamá-la de efeito HR. [Rascunho:26](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1616-lane3.md:26)

5. **Manter “21,7% versus 5,2%” estritamente descritivo.** São **10 versus 34 pump-nativas**, selecionadas por graduação, com composições diferentes de velocidade de graduação. Declarar idade na medição, validade e denominador de `t10`; não usar concentração atual como evidência de retenção causada por HR. **Falha:** seleção e composição produzirem uma aparente vantagem ou risco de HR. [Rascunho:35](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1616-lane3.md:35)

6. **Remover causalidade das taxas.** “Valores diários reportados aumentaram em relação a 11/09” é defensável. “Subiram com o upgrade” não é: 12/09 mistura antes/depois, o adaptador não foi inspecionado e taxas/volume podem cobrir universos diferentes. **Falha:** concluir aumento da taxa efetiva dividindo agregados incompatíveis. [Rascunho:119](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1616-lane3.md:119)

7. **Eliminar diagnósticos não demonstrados.** `active` numa lista e `paused` depois num detalhe continuam observações divergentes; `buy_zero_amount` é um valor recém-observado, sem mecanismo comprovado. Da mesma forma, **“zero de evicção” é hipótese**, não conclusão do contraste 0 versus 622 holders. **Falha:** registrar transições ou causas de indisponibilidade falsas e contaminar features. [Rascunho:72](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1616-lane3.md:72), [rascunho:105](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-15-1616-lane3.md:105)

## NICE-TO-HAVE

Publicar cobertura e atraso por fonte, incluindo moedas nunca servidas. Medir apenas respostas disponíveis favorece artificialmente a fonte.

## O QUE EU FARIA DIFERENTE

Registraria a KB-0096 agora, após as correções textuais, como **novidade observada de contrato e último deploy observado**. A validação prospectiva fica explicitamente pendente.

## CONCORDO COM

Nenhuma vantagem negociável demonstrada; nenhuma linha nova para o deploy ou para Mayhem; “sem ganho detectável” não significa equivalência.

## OBSIDIAN

- **Hipóteses do plantão** — consolidar M-D9/M-D13 e corrigir o marco e os desfechos de M-P39.
- **KB-0096** — separar observações, intervalo de introdução e validações pendentes.
- **KB-0094** — acrescentar a nova fronteira observada, sem presumir conteúdo.
- **KB-0095** — acrescentar `buy_zero_amount` e ausência do objeto `mayhem`, por endpoint.
- **Meme / 2026-09-15** — incorporar este parecer e retirar inferências causais não demonstradas.