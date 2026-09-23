## RESUMO

**Manteria “NÃO CONFIRMA” como conclusão científica, mas não homologaria o veredito como aplicação inequívoca da regra pré-fixada.** Há uma ambiguidade em (b), uma divergência numérica nas análises secundárias e uma limitação concreta das fitas 0062.

**1. O “pico” obriga REFUTA?** Se (b) significava literalmente `plateau_or_spike(...).form == "pico"`, **sim**: a errata preservou esse gatilho. Não há nela exceção explícita para três partições. [notes-R76.md:110](C:/dev/project-hunter/.claude/state/notes-R76.md:110)

Entretanto, o classificador chama de “pico” qualquer sequência positiva que não satisfaça **quatro pontos positivos e dois ICs acima de zero**. Portanto, três efeitos positivos semelhantes, todos imprecisos, recebem esse nome sem demonstrar um pico isolado. [stats.py:236](C:/dev/project-hunter/infra/research/stats.py:236)

Minha recomendação: registrar **“NÃO CONFIRMA; diagnóstico de forma insuficiente, com interpretação pós-execução explicitada”**. Não apresentar “(b) não avaliável” como uma exceção já congelada. O diagnóstico interno dos tercis, feito com um único limiar, tampouco serve para decidir a forma da curva. [run.py:106](C:/dev/project-hunter/.claude/state/r76/run.py:106)

**2. A secundária muda o rótulo global?** **Não automaticamente.** Holm corrige multiplicidade; não determina que uma falha da secundária refute a primária. Os tetos do criador são operacionalmente desfavoráveis: matam 31–48% das vencedoras e bloqueiam somente duas das seis piores. Mas existe ainda uma ambiguidade textual: nenhum alcança as três piores exigidas para sucesso, logo “o teto que bloqueia as piores” precisa ser interpretado explicitamente. [report.md:227](C:/dev/project-hunter/.claude/state/r76/report.md:227), [run.py:31](C:/dev/project-hunter/.claude/state/r76/run.py:31)

**3. Há bug que muda números?** **Sim, nas análises secundárias e no patamar; a primária reproduziu exatamente.** Detalhes abaixo.

**4. A recomendação é razoável?** **Sim, como decisão de não implementar agora.** Uma nova hipótese sobre SOL no slot de criação deve ser independente da medida de financiador, pré-registrada e avaliada numa população nova. Porém **0062, sozinha, não fornece essa variável**.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO, papel `quant-engineer`; sem commit.

## TESTES

Executei verificações em memória por `uv run --no-sync python -B -`, sem chamar os geradores que escrevem arquivos.

Saídas reais:

```text
12 passed in 1.21s
rebuilt rows 686 network/outcome mismatches {}
```

Reprodução da primária, tanto com os cortes dos elegíveis quanto com os cortes recalculados nos resolvidos:

```text
n: 91 91
D: 0.05352658102071071
CI: -0.005017971113091529 0.11618354893767445
dump: 12 8
```

A reconstrução conferiu rede e desfecho contra `rows.json`; não repetiu consultas à Helius. Uma impressão intermediária falhou por codificação do terminal; a repetição em UTF-8 terminou normalmente.

## MUST-FIX

**1. Resolver a contradição editorial de (b), preservando o histórico.**

Cenário concreto: um leitor aplica “pico → REFUTA” à saída publicada e chega ao contrário do veredito proposto. O código externo aceita três partições para prosseguir, mas chama um classificador cujo mínimo é quatro. [run.py:132](C:/dev/project-hunter/.claude/state/r76/run.py:132), [stats.py:261](C:/dev/project-hunter/infra/research/stats.py:261)

Publique separadamente: saída mecânica, insuficiência desse diagnóstico para demonstrar pico e interpretação adotada depois da execução. **Não basta apagar “pico” nem dizer que a exceção estava pré-registrada.**

**2. Fixar cortes antes de filtrar pela disponibilidade do desfecho.**

O desenho define tercis na população elegível; o código remove desfechos ausentes antes de calcular tercis e grelha. [notes-R76.md:64](C:/dev/project-hunter/.claude/state/notes-R76.md:64), [run.py:61](C:/dev/project-hunter/.claude/state/r76/run.py:61), [run.py:119](C:/dev/project-hunter/.claude/state/r76/run.py:119)

Cenário observado: a censura altera as fronteiras e muda os comparadores.

| Resultado | Publicado | Cortes nos elegíveis |
|---|---:|---:|
| Primária D | +0,05353 | **igual** |
| Secundária: baixo/alto | 149/91 | **149/89** |
| Secundária D | +0,04479 | **+0,04793** |
| Patamar: ponto intermediário D | +0,04627 | **+0,05033** |

Na secundária corrigida, reproduzi IC **[−0,0099; +0,1079]**; Holm permanece **0,166** para ambos. Portanto, essa correção **não produz confirmação**, mas precisa entrar na versão final dos números.

**3. Não prometer medir bundle de criação apenas com 0062.**

A serialização não inclui `slot`; a captura guarda uma fatia das trocas recentes da janela. [decision_tape.py:116](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/decision_tape.py:116), [decision_tape.py:281](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/decision_tape.py:281)

Cenário concreto: decisão aos 120 segundos; as compras da criação já saíram da janela de 60 segundos. Mesmo uma fatia completa não permite agrupá-las pelo slot ausente. Antes do experimento, é necessário garantir a observação persistida do agregado de criação e sua disponibilidade temporal.

## NICE-TO-HAVE

- **Publicar a diferença de taxas de despejo com bootstrap**, prometida no desenho: atualmente o relatório entrega Wilson por braço e razão, sem esse intervalo. [notes-R76.md:70](C:/dev/project-hunter/.claude/state/notes-R76.md:70), [report.py:85](C:/dev/project-hunter/.claude/state/r76/report.py:85)
- Corrigir a legenda do corte alto: ela imprime `> mínimo observado no alto`, embora esse mínimo pertença ao grupo. [run.py:70](C:/dev/project-hunter/.claude/state/r76/run.py:70), [run.py:89](C:/dev/project-hunter/.claude/state/r76/run.py:89)
- Explicitar que o contrafactual **deixa passar desconhecidos** e representa supressão de posições históricas, sem simular novas oportunidades decorrentes do capital liberado. [report.py:117](C:/dev/project-hunter/.claude/state/r76/report.py:117)

## O QUE EU FARIA DIFERENTE

Escreveria: **“A medida de primeiro financiador comum não sustentou a previsão de despejo simultâneo nesta população.”** Evitaria “o mecanismo não existe” ou “não há associação”: AUC 0,468 é uma estimativa, não teste de equivalência. Há inclusive despejos com grupos compartilhados relevantes, como RUNPEPE; os maiores casos de origem é que apresentam financiadores predominantemente distintos entre as vendedoras resolvidas. [report.md:247](C:/dev/project-hunter/.claude/state/r76/report.md:247), [dumpmech.out:6](C:/dev/project-hunter/.claude/state/r76/dumpmech.out:6), [dumpmech.out:32](C:/dev/project-hunter/.claude/state/r76/dumpmech.out:32)

Para bundle SOL, exigiria valor incremental sobre dev share/snipers, incluindo definição prévia da participação do criador. O resultado exploratório é motivo para formular uma hipótese, não para escolher agora um teto vencedor. [explore.out:7](C:/dev/project-hunter/.claude/state/r76/explore.out:7)

## CONCORDO COM

Não construir agora a medida de financiador nem uma aproximação dela. A inversão em s1, a falha na previsão de despejo e o contrafactual fraco sustentam essa decisão de engenharia. [report.md:30](C:/dev/project-hunter/.claude/state/r76/report.md:30), [report.md:59](C:/dev/project-hunter/.claude/state/r76/report.md:59), [report.md:222](C:/dev/project-hunter/.claude/state/r76/report.md:222)

Não encontrei alteração comprovada da primária por censura, resolvedor ou classificação temporal de exchange. Conferi os cortes do cache para grupos compartilhados: nenhum insuficiente; truncar a decisão para segundos não mudou classificações nesta amostra. Isso não elimina a natureza retrospectiva das identidades Helius, já declarada no desenho.

## OBSIDIAN

- **Fila de Hipóteses — H-014:** registrar resultado, ambiguidade de (b) e números corrigidos, preservando o pré-registro.
- **Ficha de 2026-09-23 — mesa real:** substituir a inferência de controle comum por descrição do despejo simultâneo observado.
- **Revisões-Astra — R76/H-014:** registrar esta auditoria, reprodução da primária e divergência nos cortes.
- **Registro de Tentativas:** registrar a decisão de não implementar e a exigência de instrumentação para eventual hipótese de bundle.

Nenhuma página foi alterada.