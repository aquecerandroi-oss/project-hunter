## RESUMO

**Pode escrever “REFUTA pela cláusula literal” nas duas hipóteses**, com a interpretação estatística ao lado. Para H-011 nas reais: **“não confirma vantagem; +5 pp não excluídos a 1,6 s”**. Não publicaria `REFUTA` sozinho. Isso preserva a distinção recomendada na [revisão anterior:49](/C:/dev/project-hunter/.claude/state/r74/astra-pre-sessao-anterior.md:49).

Atuei como `quant-engineer`.

## ARQUIVOS

Nenhum criado ou modificado.

## TESTES

Não reexecutei os 47 testes nem as simulações. Conferi código e saídas existentes; não validei independentemente os cinco contributos individuais nem o limite inferior não arredondado de +0,003%.

## MUST-FIX

**De redação/interpretação antes de publicar:**

1. **“Morre a 5 s” está errado nas reais.** Cai de +3,05 para **+0,78 pp**, IC [−2,31; +4,50]. Escrever “atenua fortemente”; a cláusula (c), D ≤ 0, **não dispara**. Cenário de falha: atribuir às reais uma terceira condição de refutação que não ocorreu. [out.txt:59](/C:/dev/project-hunter/.claude/state/r74/out.txt:59)

2. **“Encurtar o tempo não apanha as perdas” é excessivo.** A 30 s, as perdas ≥50% passam de **2 para 1 nas reais** e **12 para 7 no papel**, enquanto corta 14/23 e 57/141 saídas por alvo. Escrever: **“reduz parte da cauda, mas deixa as quedas precoces e sacrifica alvos; o D médio fica negativo”**. Cenário: descartar um efeito observado sobre a cauda por confundi-lo com ausência de vantagem média. [hold.txt:10](/C:/dev/project-hunter/.claude/state/r74/hold.txt:10), [hold.txt:40](/C:/dev/project-hunter/.claude/state/r74/hold.txt:40)

3. **“O alvo não é sistematicamente cedo” ultrapassa esse diagnóstico.** Os números sustentam **“substituir essas saídas por segurar até ao fim piorou, em média e mediana”**. Não testam toda saída intermediária possível. São 300 s **desde a entrada**, mais latência, não outros 300 s após o pouso. Cenário: um pico posterior seguido de queda torna segurar até ao fim ruim, embora outra saída anterior pudesse melhorar. [out.txt:26](/C:/dev/project-hunter/.claude/state/r74/out.txt:26), [policies.py:134](/C:/dev/project-hunter/.claude/state/r74/policies.py:134)

## NICE-TO-HAVE

- **1,20 não é descoberta estatística:** o IC marginal mal positivo acompanha p bruto 0,0703 e Holm 0,5623. [out.txt:46](/C:/dev/project-hunter/.claude/state/r74/out.txt:46)
- No papel, **+1,11 pp inclui a extensão 1,50**; na grade principal, o maior limite superior é +0,96 pp. Ambos ficam abaixo de +5 pp, sob o modelo e a amostra analisados. [out.txt:130](/C:/dev/project-hunter/.claude/state/r74/out.txt:130)
- Publicar os cinco contributos com unidade explícita: diferença individual em SOL/SOL ou contribuição em pp para a média.

## O QUE EU FARIA DIFERENTE

**Colocaria cobertura e observabilidade juntas como ressalva principal**, antes do tamanho amostral. O dado mais forte é a inversão do 1,08: **−3,06 pp nos 30 casos com buraco ≤30 s; +8,15 pp nos 36 restantes**. Isso não prova viés causal, mas mostra que o ganho agregado depende do estrato com pior cobertura. [out.txt:54](/C:/dev/project-hunter/.claude/state/r74/out.txt:54)

Sua ressalva sobre chegada está correta com um ajuste: **~44 s é atraso do arquivo, não latência medida da mesa WS**. E os 5 s simulados atrasam o pouso depois do gatilho; **não simulam atraso de observação**, que pode alterar ou suprimir gatilhos. O modelo usa o último estado disponível até o pouso, inclusive através de lacunas. [KB-0153:29](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0153-o-maior-comprador-nao-estava-no-arquivo.md:29>), [sim.py:64](/C:/dev/project-hunter/.claude/state/r72/sim.py:64)

## CONCORDO COM

**H-011: (a)+(b) nas duas, (c) somente no papel. H-012: (a) nas duas.** Mantenha esses rótulos literais separados da inferência econômica. Os resultados incondicionais do fragmento R72 também batem: −0,31 pp reais e +0,34 pp papel. [out.txt:69](/C:/dev/project-hunter/.claude/state/r74/out.txt:69), [out.txt:156](/C:/dev/project-hunter/.claude/state/r74/out.txt:156), [hold.txt:28](/C:/dev/project-hunter/.claude/state/r74/hold.txt:28), [hold.txt:58](/C:/dev/project-hunter/.claude/state/r74/hold.txt:58)

## OBSIDIAN

- **Fila de Hipóteses** — acrescentar os vereditos literais e a interpretação estatística separada.
- **KB-0152 — A oscilação existe; o giro não paga** — acrescentar a avaliação incondicional do fragmento.
- **Revisões-Astra / R74** — registrar as correções de linguagem e a dependência da cobertura/observabilidade.