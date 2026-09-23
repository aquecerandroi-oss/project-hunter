## RESUMO

**Manteria o trailing no braço principal, mas corrigiria o protocolo antes de rodar.** Os bloqueios principais são: interpretação do fragmento R72, regra contraditória de refutação, seleção entre várias políticas, definição da população e instrumentação do instante de saída.

Atuei como `quant-engineer`, em modo OPINIÃO. Abaixo respondo A–F; os cenários são exemplos hipotéticos, não resultados do R74.

## ARQUIVOS

Nenhum ficheiro criado ou modificado. Nenhum commit.

## TESTES

Não executei simuladores nem testes: esta revisão é anterior à corrida. Os resultados citados do R72 são artefactos existentes, não uma reprodução nesta sessão.

## MUST-FIX

**1. A — Principal com trailing; corrigir o que se chama “fragmento do R72”.**

A leitura fiel de H-011 é **repique + trailing de 10% desde a entrada + máximo de 300 s**. A variante sem trailing deve ficar como desvio exploratório. Isso está explícito no [pré-registo:135](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:135>).

Mas retirar o trailing **não basta para reproduzir o fragmento**:

- No R72, a primeira venda ocorre quando a marca sobe X% sobre **a marca de entrada**, sem exigir queda anterior ([sim.py:136](/C:/dev/project-hunter/.claude/state/r72/sim.py:136)).
- A tua máquina exige primeiro queda da máxima e depois recuperação do fundo. É uma política diferente, compatível com o texto de H-011.
- Os +3,44 pp são a **média condicional** das 47 posições classificadas como `abandoned`; 62% é a frequência desse grupo, não a proporção de posições beneficiadas. A classificação dá prioridade a `abandoned`, mesmo quando houve ciclos anteriores ([abandon.py:18](/C:/dev/project-hunter/.claude/state/r72/abandon.py:18), [abandon.txt:1](/C:/dev/project-hunter/.claude/state/r72/abandon.txt:1)).

**Cenário de falha:** uma posição pode recomprar duas vezes e só depois abandonar; o seu resultado entra nos +3,44 pp, embora não corresponda a “vender a primeira vez e nunca voltar”.

**Correção:** manter a máquina proposta como principal; descrever R72 como **origem exploratória**, sem herdar o efeito. Se quiseres isolar literalmente a primeira venda, acrescentar um diagnóstico separado: vender a `marca_entrada × (1+X)`, nunca recomprar, avaliado em **toda a população**.

---

**2. D — Resolver a contradição do veredito antes de observar resultados.**

Literalmente, H-011 manda `REFUTA` quando o melhor fica na borda. Portanto, **1,50 vencedor dispara essa cláusula na grade ampliada**. Cientificamente, porém, isso estabelece apenas **“não localizámos um ótimo interior”**; não refuta vantagem económica.

Há um problema ainda maior: a fila diz “nenhum alvo tem **limite inferior** acima de +0,01”. Isso transforma falta de precisão em refutação e contraria [RESEARCH.md:65](/C:/dev/project-hunter/docs/RESEARCH.md:65).

**Cenário de falha:** D = +0,06 e IC [−0,02; +0,14] seria “REFUTA” pela fila, embora comporte uma vantagem grande. Com D = +0,06 e IC [+0,005; +0,12], uma célula pode satisfazer a previsão e simultaneamente disparar a refutação.

**Correção recomendada, como adenda datada sem apagar o original:**

- **Borda:** `NÃO CONFIRMA — ótimo interior não identificado`.
- **Refutação económica:** limites **superiores** abaixo do limiar económico explicitamente escolhido; se preservares o +0,01 da fila, declarar essa escolha.
- **Confirmação:** preservar D ≥ +0,05, IC inferior > 0, patamar e demais requisitos do projeto.
- Congelar o significado de “ganho desaparece a 5 s”: D ≤ 0 é diferente de IC atravessar zero.

Publicaria separadamente **“cláusula literal acionada”** e **“interpretação estatística”** se não houver adenda. Não reinterpretaria silenciosamente `REFUTA`.

A grade original termina em 1,30; 1,50 é extensão declarada. Um 1,30 interior na grade ampliada continua sendo borda na original. A regra também alcança a borda inferior, 1,08. ([Fila:135–138](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:135>))

---

**3. D/F — Patamar não substitui controlo de multiplicidade nem validação independente.**

`boot_ci` calcula IC por contraste; `perm_p` calcula um p por contraste. Nenhum deles corrige a seleção do vencedor da grade ([run.py:32](/C:/dev/project-hunter/.claude/state/r72/run.py:32), [run.py:51](/C:/dev/project-hunter/.claude/state/r72/run.py:51)).

**Cenário de falha:** duas políticas vizinhas partilham quase todas as saídas e beneficiam do mesmo acaso amostral; ambas passam em IC pontual e o “patamar” é declarado descoberta.

**Correção:**

- Congelar a família principal e aplicar **Holm aos p**, preservando também os valores brutos.
- Para afirmar que o patamar inteiro tem suporte simultâneo, usar limites simultâneos; IC pontual de cada célula não oferece essa garantia.
- Definir vizinhança **dentro de cada família**: alvos fixos e repiques são eixos diferentes. O controlo 1,15 tem D = 0 por construção e não pode integrar um par com IC inferior positivo.
- Manter a exigência de efeito ≥ +0,05 e publicar o PnL absoluto: melhorar sobre um controlo negativo não basta para declarar um braço lucrativo ([RESEARCH.md:65](/C:/dev/project-hunter/docs/RESEARCH.md:65)).

A amostra R72 já originou a hipótese. **Pré-registar agora não a transforma em amostra independente.** O R74 pode avaliar esta extensão exploratória; confirmação externa exige posições posteriores ao congelamento. Papel só funciona como replicação independente depois de verificar sobreposição de mints e períodos.

---

**4. F — Congelar a população e alinhar a unidade da inferência.**

H-011 pede uma posição por mint. O carregador real acrescenta todas as linhas recebidas, sem deduplicar; `perm_p` troca sinais por **posição**, enquanto o bootstrap agrupa por mint ([load.py:103](/C:/dev/project-hunter/.claude/state/r72/load.py:103), [run.py:58](/C:/dev/project-hunter/.claude/state/r72/run.py:58)).

**Cenário de falha:** várias entradas do mesmo mint são tratadas como evidências independentes no p, produzindo precisão excessiva.

**Correção:** verificar unicidade; se necessário, escolher uma entrada por mint com regra temporal congelada, nunca pelo resultado. Se mantiveres todas, declarar desvio e trocar sinais por **cluster inteiro**.

Publicar o funil: posições exportadas → mints únicos → elegíveis → avaliáveis. Usar a mesma população emparelhada entre políticas e sensibilidades. As 76 posições do R72 não devem ser assumidas como denominador depois dessas verificações. O artefacto original termina em 23/09; não representa automaticamente a população “17–24/09” da fila ([notes-R72.md:40](/C:/dev/project-hunter/.claude/state/notes-R72.md:40)).

---

**5. B — Formalizar o oráculo e distinguir zero de ausência de informação.**

Usaria **o lote original**, com esta definição:

\[
L_i=\frac{\max\left(0,\ \max_{t_e<t\le t_0+300}V_i^{líquido}(t)-C_i\right)}{S_i}
\]

Aqui, \(C_i\) é o caixa da **saída simulada dessa política**, não o recebimento histórico; \(S_i\) é o gasto original. O caixa recebido fica constante: fazê-lo acompanhar novamente o preço pressupõe recompra.

Nome recomendado: **“valorização posterior máxima observada do lote original — diagnóstico ex-post”**. Calculá-lo depois das decisões, sem participar de seleção, ranking decisório ou veredito.

O simulador calcula o pouso, mas descarta `_ft` no retorno de `simulate_current`; logo, o retorno atual não basta para obter \(t_e\) corretamente ([sim.py:217](/C:/dev/project-hunter/.claude/state/r72/sim.py:217)). É preciso expor um registo de gatilho, pouso, estado usado, motivo e caixa, preservando a mecânica.

**Cenários de falha:**

- Usar o timestamp da última reserva como saída alonga artificialmente a janela posterior.
- Não existir observação após uma saída aos 100 s e isso virar zero confunde falta de fita com ausência de oportunidade.
- Um `time_stop` parecer superior porque tem zero obrigatório.

O zero do `time_stop` **é estrutural, não evidência de saída excelente**. A métrica favorece mecanicamente saídas tardias quando interpretada como pontuação. Publicar média, mediana e fração > 0 juntamente com tempo restante, fração sem janela e cobertura posterior. Janela existente sem observações suficientes deve ser **indisponível**, não zero.

---

**6. F — Fechar a máquina causal e testar decisões, não apenas fills.**

Congelaria: máxima global desde a entrada; fundo corrente após abrir o mergulho; trailing ativo em ambos os estados; primeira saída irrevogável; nenhuma recompra; nenhuma reavaliação durante o pouso. Definir prioridade em coincidências e confirmar que o braço repique **substitui** o alvo fixo.

O `Guard.check` verifica índices e limite temporal do fill; não fiscaliza as leituras usadas para escolher o gatilho ([sim.py:44](/C:/dev/project-hunter/.claude/state/r72/sim.py:44)).

**Cenário de falha:** a máquina consulta o mínimo futuro para escolher o fundo, dispara uma ordem e passa pelo `Guard` porque executa dentro de gatilho + latência.

Antes da corrida, exigir testes sintéticos de:

- invariância das decisões ao alterar o sufixo futuro;
- queda que cruza simultaneamente mergulho e trailing;
- recuperação antes/depois dos 300 s;
- timestamps iguais e ordem já pendente;
- pouso terminal aos **301,6 s ou 305 s**, conforme a latência.

O teste existente de invariância exercita `simulate_scalp`, não a máquina nova ([test_r72.py:62](/C:/dev/project-hunter/.claude/state/r72/test_r72.py:62)). A liquidação terminal herdada já usa `300 + latência` ([sim.py:105](/C:/dev/project-hunter/.claude/state/r72/sim.py:105)).

---

**7. Ponto 5 — Sensibilidade emparelhada, sem trocar o vencedor.**

Rodaria o cruzamento completo **2 latências × 3 custos**, recalculando candidato e controlo nas mesmas condições. Avaliaria a sobrevivência dos mesmos limiares selecionados na condição base.

**Cenário de falha:** 1,12 vence a 1,6 s, perde a 5 s, e o relatório declara robustez porque 1,30 vence a 5 s.

Também declararia corretamente a contabilidade: com entrada histórica congelada, variar `c` muda **apenas a saída simulada**; não transforma retroativamente o custo total observado numa ida e volta exatamente igual a `c`. A venda aplica `c/2` e `per_sol` mantém o gasto original ([sim.py:80](/C:/dev/project-hunter/.claude/state/r72/sim.py:80), [sim.py:237](/C:/dev/project-hunter/.claude/state/r72/sim.py:237)).

## NICE-TO-HAVE

**C — O IC da cauda é útil, mas não certifica segurança com 76 posições.**

Não existe aqui um único “Wilson emparelhado (McNemar)”:

- **Por política:** contagem/n e IC de Wilson para a proporção de perdas ≥ 50%.
- **Contra o controlo:** tabela emparelhada, perdas graves evitadas/criadas, diferença de proporções com IC próprio para dados emparelhados; McNemar exato como teste dos discordantes.

Wilson estima uma proporção; McNemar testa a assimetria dos pares discordantes. ([NIST — Wilson](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm), [NIST — McNemar](https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/mcnemar.htm))

**Exemplo apenas ilustrativo:** mesmo 0/76 produz limite superior Wilson bilateral de 95% de aproximadamente **4,81%**, supondo unidades independentes. Publicaria o pior negócio como **mínimo observado**, nunca como limite da perda possível.

**E — O sinal do viés dos buracos não é identificável só pela duração.**

Um pico omitido seguido de queda prejudica o alvo baixo; uma subida omitida que reaparece mais alta pode favorecê-lo. Um trailing perdido também altera qual política parece melhor. Não assumiria que 1,08 é necessariamente o mais afetado: precisa ser medido.

Sem reexportar:

1. Comparar os contrastes emparelhados em estratos de cobertura congelados, incluindo `max_gap ≤ 30 s` e `> 30 s`. Isso mede heterogeneidade, não identifica causalmente o viés.
2. Nas fitas mais densas, remover artificialmente blocos contíguos, com sementes e durações congeladas, e reconstruir **ambos os braços**. Medir  
   \(D_{\text{degradado}}-D_{\text{original}}\), mudanças de gatilho e atraso de saída.
3. Remover também fotografias dentro dos blocos mascarados; preservar observações posteriores legitimamente disponíveis.
4. Publicar idade do estado usado no pouso, gatilhos na primeira observação após buraco e buracos anteriores à saída.

O diagnóstico atual inclui intervalos entre pontos e a cauda até 300 s; a elegibilidade exige apenas três trades na janela, sem certificar continuidade ([load.py:238](/C:/dev/project-hunter/.claude/state/r72/load.py:238), [load.py:256](/C:/dev/project-hunter/.claude/state/r72/load.py:256)).

Esse ensaio estima **sensibilidade à perda artificial de dados**. Não recupera os preços ausentes nem fornece uma correção garantida para os 44 casos.

## O QUE EU FARIA DIFERENTE

Congelaria uma adenda curta com população, famílias principal/exploratória, máquina de estados, critérios de veredito e tratamento da cobertura. Preservaria os helpers do R72, acrescentando o registo completo das saídas e os testes da nova máquina.

Trataria o R74 como avaliação exploratória sobre dados já vistos, com candidato congelado para avaliação posterior.

## CONCORDO COM

Mesmas entradas e lotes, contraste emparelhado, controlo congelado, custos sem recobrar a entrada, atraso explícito, venda integral sem recompra, medição da cauda e oráculo separado do simulador.

## OBSIDIAN

- **Fila de Hipóteses** — acrescentar adenda de H-011 com interpretação de refutação, famílias, população e critérios congelados.
- **KB-0152 — A oscilação existe, o giro não paga** — esclarecer que os +3,44 pp pertencem ao grupo `abandoned`, que pode incluir ciclos anteriores.
- **Revisões-Astra / R74-H-011 — desenho** — registar este parecer, decisões aceites e desvios antes da corrida.
- **Página de resultados do R74, quando criada** — separar resultados exploratórios, cobertura, diagnóstico ex-post e futura replicação.