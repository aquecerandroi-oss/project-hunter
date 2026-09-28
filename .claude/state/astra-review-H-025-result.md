**RESUMO**

**Os quatro vereditos estão corretos para os números publicados, mas o código precisa de correções.** Encontrei quatro falhas concretas; uma delas — expiração da LTA uma vela atrasada — altera os números reais de H-026, **sem mudar os rótulos**.

Atuei como `quant-engineer`, em OPINIÃO, seguindo o pré-registro e a [emenda na Fila de Hipóteses](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:300>).

| Braço | Julgamento dos resultados publicados |
|---|---|
| H-025 primária | **NÃO CONFIRMA**: D abaixo do MRE, IC atravessa zero, Holm falha e vizinhas 0,45/0,55 negativas. |
| H-025 estrutural | **NÃO CONFIRMA**: D abaixo do MRE e IC atravessa zero. |
| H-026 A | **REFUTA o tamanho previsto**: limite superior abaixo de +1 p.p. nos dois limites; cobertura suficiente e K6 não dispara. |
| H-026 B | **NÃO CONFIRMA**: D ≥ MRE não basta; IC atravessa zero e Holm = 0,237. Patamar e corte passam. |

Fontes: [H-025 primária](/C:/dev/project-hunter/.claude/state/r85/h025_h026.txt:8), [estrutural](/C:/dev/project-hunter/.claude/state/r85/h025_h026.txt:21), [A](/C:/dev/project-hunter/.claude/state/r85/h025_h026.txt:31), [B](/C:/dev/project-hunter/.claude/state/r85/h025_h026.txt:39).

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit. As reproduções e alterações experimentais de funções ocorreram exclusivamente em memória.

**TESTES**

Executei `uv run pytest -q .claude/state/r85/`, com bytecode/cache do pytest desabilitados e `uv` sem sincronização:

```text
......................                                                   [100%]
22 passed in 4.13s
```

Também executei diagnósticos por `uv run python -`, recebendo o programa pela entrada padrão:

- Reproduzi as contagens originais e os D principais.
- Reproduzi os erros de abertura estrutural, K6, expiração e seleção estrutural.
- Conferi a precedência da abertura em todas as saídas estruturais reais: **zero operações afetadas neste painel**.
- Recalculei H-026 com somente a expiração corrigida, incluindo bootstrap de 10.000 réplicas.

Não reexecutei `run_real.py`, pois ele grava os artefatos ([run_real.py:46](/C:/dev/project-hunter/.claude/state/r85/run_real.py:46)). Li a fumaça sintética existente; não a confundo com validação estatística do estudo.

**MUST-FIX**

**1. A LTA permanece viva em `b+180`, contrariando a expiração registrada.**

O pré-registro diz que morre **180 velas depois de b**; o código usa `t - ln.b > max_age`, portanto só mata em `b+181`. Isso permite eventos e controles na vela de vencimento. ([pré-registro:15](/C:/dev/project-hunter/.claude/state/r85/prereg_with_amendment.md:15), [geom85.py:160](/C:/dev/project-hunter/.claude/state/r85/geom85.py:160))

**Cenário reproduzido:** linha com `b=50`, respeitada até o vencimento, recebe terceiro toque em `t=230`. O código emite A; com `>= max_age`, não emite.

**Impacto real medido**, corrigindo apenas essa comparação em memória:

| Braço | Resultado recalculado, otimista | Veredito |
|---|---|---|
| A | n=1.529; D **−1,085 p.p.**, IC **[−2,079; −0,021]** | REFUTA |
| B | n=323; D **+1,089 p.p.**, IC **[−0,755; +2,891]**; Holm ≈ **0,2230** | NÃO CONFIRMA |

O braço B muda mesmo sem mudar seu número de eventos porque a correção também altera controles. É necessário atualizar o resultado após corrigir a implementação, preservando a saída anterior como histórico.

**2. A mínima posterior pode substituir uma saída que já deveria ter ocorrido na abertura.**

`exit_struct` testa `low <= stop` **antes** de `open >= target`. ([study85.py:64](/C:/dev/project-hunter/.claude/state/r85/study85.py:64))

**Cenário reproduzido:** entrada 100, stop 95, alvo 130; dois dias depois abre em 140 e cai até 90. O código retorna **−5,2848%**, pelo stop, e manda o controle sair no dia seguinte. A regra registrada exige saída em 140 na abertura: **+39,5803%**, com controle na mesma abertura.

É uma violação temporal da execução: a mínima posterior muda uma decisão já determinada na abertura. **Não ocorreu nas operações estruturais deste painel**, conforme conferência realizada. Corrigir a ordem: avaliar ambas as condições de abertura antes dos extremos intradiários. ([emenda:9](/C:/dev/project-hunter/.claude/state/r85/prereg_with_amendment.md:9))

**3. K6 bloqueia CONFIRMA, mas não bloqueia REFUTA.**

A letra registrada determina **NÃO CONFIRMA** quando uma moeda concentra ≥60%. O código verifica K6 apenas para confirmar; depois pode retornar REFUTA. ([pré-registro:18](/C:/dev/project-hunter/.claude/state/r85/prereg_with_amendment.md:18), [stats85.py:70](/C:/dev/project-hunter/.claude/state/r85/stats85.py:70))

**Cenário reproduzido:** amostra suficiente, `k6=True`, IC superior abaixo do MRE nos dois limites → retorna **REFUTA**, quando deveria retornar **NÃO CONFIRMA**. K6 deve ser verificado depois do limite de dado e antes dos demais vereditos.

**Sem impacto neste resultado:** concentração máxima de A=5,9% e B=7,1%. ([resultado:36](/C:/dev/project-hunter/.claude/state/r85/h025_h026.txt:36), [resultado:44](/C:/dev/project-hunter/.claude/state/r85/h025_h026.txt:44))

**4. A população estrutural depende indevidamente da disponibilidade da saída fixa.**

A inclusão estrutural exige simultaneamente `s is not None` **e** `ex[10] is not None`. Isso mistura a análise estrutural principal com seu descritivo pareado contra a saída fixa. ([collect85.py:113](/C:/dev/project-hunter/.claude/state/r85/collect85.py:113))

**Cenário reproduzido:** o evento tem stop estrutural observado em `e+1`; depois a série ainda considerada viva fica sem abertura suficiente para observar H=10. A estrutural retorna um resultado válido, a fixa retorna `None`, e o coletor exclui ambas.

A disponibilidade futura de outro desfecho não deve apagar uma saída estrutural observada. Manter a estrutural e declarar a ausência apenas no descritivo que exige os dois retornos. **Não houve censura H=10 na reexecução deste painel**, portanto não identifiquei impacto atual.

**NICE-TO-HAVE**

- **Completar o relatório previsto:** faltam as sensibilidades estruturais de **60/180 dias**, explicitamente registradas. O relatório calcula 120 dias e depois apresenta sensibilidades apenas dos braços fixos. Também calcula descartes de réplicas vazias, mas não os imprime. São pendências de completude, mesmo sem decidir o rótulo. ([emenda:9](/C:/dev/project-hunter/.claude/state/r85/prereg_with_amendment.md:9), [analyze85.py:128](/C:/dev/project-hunter/.claude/state/r85/analyze85.py:128), [analyze85.py:174](/C:/dev/project-hunter/.claude/state/r85/analyze85.py:174), [stats85.py:51](/C:/dev/project-hunter/.claude/state/r85/stats85.py:51))
- **Explicitar o controle LTA:** o código exclui qualquer proximidade geométrica `near`, mesmo sem afastamento suficiente para constituir outro **toque distinto**. Isso corresponde à intenção de controle “fora da linha”, mas merece distinção textual entre proximidade e toque contado. Exemplo: vela imediatamente posterior ao terceiro toque, ainda junto à linha, fica fora do controle mesmo sem novo A. ([geom85.py:170](/C:/dev/project-hunter/.claude/state/r85/geom85.py:170), [geom85.py:183](/C:/dev/project-hunter/.claude/state/r85/geom85.py:183))
- Acrescentar regressões para os quatro cenários acima. Os testes atuais de K6 verificam bloqueio de confirmação, não a precedência sobre refutação. ([test_study85.py:123](/C:/dev/project-hunter/.claude/state/r85/test_study85.py:123))

**O QUE EU FARIA DIFERENTE**

**Sobre A e momentum transversal:** sim, é uma explicação compatível com o desenho. O controle exige LTA já confirmada e ausência de proximidade naquele dia; A seleciona retorno à linha e inclui a própria confirmação. Assim, o contraste pode separar moedas que mantiveram força de moedas em recuo, além de diferir na idade da estrutura. Comparar no mesmo dia não elimina essas diferenças. ([pré-registro:15](/C:/dev/project-hunter/.claude/state/r85/prereg_with_amendment.md:15), [pré-registro:16](/C:/dev/project-hunter/.claude/state/r85/prereg_with_amendment.md:16))

**Não concluiria** que a LTA causa perdas, que momentum foi identificado como mecanismo, que vender A a descoberto seria lucrativo, ou que B acrescenta informação além de um rompimento genérico.

Para A, **“efeito oposto” é uma leitura descritiva defensável deste contraste**, pois o IC principal inteiro está abaixo de zero. O rótulo formal continua **REFUTA o tamanho positivo previsto**. O Holm publicado testa superioridade positiva; não transforma essa leitura negativa numa descoberta inversa corrigida por multiplicidade. ([stats85.py:49](/C:/dev/project-hunter/.claude/state/r85/stats85.py:49), [analyze85.py:159](/C:/dev/project-hunter/.claude/state/r85/analyze85.py:159))

Para B, aceito **“pista descritiva, não confirmada”**: sinal positivo nas tolerâncias e nos cortes temporais, mas incerteza compatível com zero e com perda relativa. “Pista” não é um quarto veredito nem autorização para trocar H=10 por H=20 depois de ver o resultado. Esse uso editorial está previsto no [Mapa de Estratégias:43](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Mapa de Estrategias.md:43>); o rótulo permanece `NÃO CONFIRMA`.

**CONCORDO COM**

A implementação atende aos pontos centrais abaixo, ressalvados os achados:

- **Fibonacci:** L estritamente entre pivôs, desempate pela primeira mínima, busca desde `h`, travessia anterior consumindo a faixa e aposentadoria ao confirmar outro pivô. ([geom85.py:73](/C:/dev/project-hunter/.claude/state/r85/geom85.py:73))
- **LTA:** confirmação causal, afastamento estritamente intermediário, P congelado, pendências preservadas e deduplicação por moeda/dia/braço. ([geom85.py:146](/C:/dev/project-hunter/.claude/state/r85/geom85.py:146), [geom85.py:163](/C:/dev/project-hunter/.claude/state/r85/geom85.py:163))
- **Universo e execução fixa:** volume apenas anterior à entrada, contraste do mesmo dia e venda na primeira abertura real, aplicados também aos controles. ([data85.py:89](/C:/dev/project-hunter/.claude/state/r85/data85.py:89), [study85.py:36](/C:/dev/project-hunter/.claude/state/r85/study85.py:36), [study85.py:91](/C:/dev/project-hunter/.claude/state/r85/study85.py:91))
- **Inferência:** calendário completo, `ΣS/ΣN`, blocos móveis, cobertura não sobreposta e Holm separado por família e por limite. ([stats85.py:23](/C:/dev/project-hunter/.claude/state/r85/stats85.py:23), [stats85.py:54](/C:/dev/project-hunter/.claude/state/r85/stats85.py:54), [analyze85.py:129](/C:/dev/project-hunter/.claude/state/r85/analyze85.py:129), [analyze85.py:159](/C:/dev/project-hunter/.claude/state/r85/analyze85.py:159))
- **Relógio estrutural:** fora do erro de precedência, `m` distingue saída na abertura de saída intradiária, e o controle usa a primeira abertura real correspondente. ([study85.py:64](/C:/dev/project-hunter/.claude/state/r85/study85.py:64), [collect85.py:119](/C:/dev/project-hunter/.claude/state/r85/collect85.py:119))

**`opt` e `pes` iguais em H=10 são plausíveis — mas A não é exatamente igual.** Na reexecução original, Fibonacci e B tiveram igualdade exata nos eventos e controles. Em A houve **uma** operação diferente: LUNA, sinal de 2022-05-06, com retorno otimista `−0,9999993551085058` e pessimista `−1`. A diferença diluída em 1.531 eventos é aproximadamente **0,0000000421 p.p.**, invisível nas três casas publicadas. O código distingue corretamente saída real de término de série; a apresentação arredonda. ([study85.py:45](/C:/dev/project-hunter/.claude/state/r85/study85.py:45), [analyze85.py:69](/C:/dev/project-hunter/.claude/state/r85/analyze85.py:69))

**OBSIDIAN**

- **Fila de Hipóteses:** acrescentar o resultado revisado de H-025/H-026 e a correção de implementação, preservando pré-registro e emenda.
- **Revisões Astra — R85, resultado e código:** registrar os quatro achados, reproduções e impacto real da expiração.
- **KB-0169 — Fibonacci e LTA diária no dado:** registrar números corrigidos, limites dos controles e a diferença de LUNA escondida pelo arredondamento; o arquivo referenciado ainda não existia nesta leitura.
- **Mapa de Estratégias:** manter os vereditos formais; se B entrar em Pistas, identificá-lo como descritivo e não confirmado.
- **KB-0077 — Linhas de tendência:** documentar vencimento em `b+180` e distinguir proximidade geométrica de toque distinto.

Nenhuma página foi alterada.