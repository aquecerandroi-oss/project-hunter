**RESUMO**

**Sim: `REFUTA` está correto pela regra congelada, nas duas populações. Eu manteria esse rótulo e escreveria ao lado que ele não demonstra ausência de qualquer vantagem.** Reproduzi as simulações em memória e os contrastes principais.

**1. Veredito mecânico e leitura estatística**

| População | Melhor célula | D contra controle, em pontos percentuais | Leitura |
|---|---|---|---|
| Reais, n=65 | X=3%, W=60 s | **+1,99 pp**, IC95% **[−3,60; +7,48]** | Não distingue prejuízo, efeito zero ou melhora relevante; **+5 pp não está excluído**. |
| Papel, n=486 | X=3%, W=60 s | **+2,28 pp**, IC95% **[+0,69; +3,89]** | Sinal de melhora pequena no modelo; **+5 pp está fora do IC da análise principal**. |

Fontes: [report.txt:13](C:/dev/project-hunter/.claude/state/r77/report.txt:13), [report.txt:182](C:/dev/project-hunter/.claude/state/r77/report.txt:182).

Em ambas, **(a)** dispara porque nenhum limite inferior ultrapassa +1 pp; **(b)** dispara porque X=3% é borda. **(c)** não dispara: D a 5 s permanece positivo. **(d)** também não: o nível pontual da política é positivo. Essa precedência está implementada em [rule.py:90](C:/dev/project-hunter/.claude/state/r77/rule.py:90).

Minha redação seria:

> **H-016: REFUTA pelos critérios pré-especificados (a) e (b).** No papel, a análise principal sugere melhora relativa pequena e seu IC exclui o ganho de +5 pp previsto. Nas reais, a incerteza permanece ampla e não exclui +5 pp. Isso não prova que esperar qualquer recuo seja inútil.

Duas qualificações:

- Os ICs são **marginais**, não simultâneos; imprimir Holm não os transforma. Holm **0,052** não passa 5%, mas não existe ruptura científica entre 0,049 e 0,052. Essa cautela acompanha a [declaração da ASA](https://doi.org/10.1080/00031305.2016.1154108).
- A exclusão de +5 pp **não é robusta à definição de cobertura**: no papel com horizonte fixo, X=3%, W=60 s dá **+2,94 pp [ +0,61; +5,38 ]**. Portanto, escreva “excluído na análise principal”, não “descartado em todas as análises”. [report.txt:257](C:/dev/project-hunter/.claude/state/r77/report.txt:257).

**2. Emenda 9**

**Aceitável como emenda feita após inspecionar cobertura, sem olhar os retornos — conforme a cronologia informada.** Há justificativa substantiva: exigir dados depois de todas as saídas pode excluir decisões cujo resultado já era observável. A interseção dos braços principais, incluindo 5 s e a espera das não entradas, preserva uma população comum. [notes-R77.md:125](C:/dev/project-hunter/.claude/state/notes-R77.md:125), [report.py:25](C:/dev/project-hunter/.claude/state/r77/report.py:25).

Mas **uniformidade não elimina seleção pelo desfecho**. Cenário: uma trajetória sai cedo e passa; outra permanece exposta até um buraco e sai da amostra inteira. A duração depende dos preços. A análise estima, portanto, o efeito **entre decisões observáveis sob toda a grade**, não entre todas as decisões da porta.

A documentação contém motivo, cronologia declarada, regra nova e sensibilidade antiga: é suficiente para entender a escolha. Eu melhoraria duas frases:

- O título da §9 diz “antes de simular qualquer célula”, enquanto a emenda 9 tem condição diferente: **antes de examinar retornos**.
- As contagens e os tempos dos buracos não demonstram, sozinhos, que eles vieram depois das saídas contrafactuais do R77; a referência ao hold do R74 sustenta uma **justificativa**, não essa prova.

**3. O efeito pequeno: pista ou pesca?**

**Pista exploratória legítima para uma hipótese nova; não confirmação da H-016.** Viraria pesca se procurássemos X menor nestes mesmos dados e apresentássemos o vencedor como validação independente.

Na melhor célula do papel, o controle rende **−2,21%**, e a política **+0,08%**, com IC contra nada **[−1,70%; +1,87%]**. Há melhora relativa, mas **rentabilidade positiva não está demonstrada**. [report.txt:176](C:/dev/project-hunter/.claude/state/r77/report.txt:176), [report.txt:182](C:/dev/project-hunter/.claude/state/r77/report.txt:182).

Também conferi a decomposição: dos **+2,285 pp** de D, aproximadamente **+2,184 pp** vêm das decisões em que a política comprou; **+0,101 pp** vêm das não entradas. Portanto, o ganho não nasce principalmente de ficar de fora.

Uma sucessora deveria congelar parâmetros e critérios antes de uma **coorte futura sem os mints usados aqui**, comparar também com uma espera simples e exigir resultado líquido economicamente útil contra não comprar. X menor é uma direção de pesquisa, não uma recomendação para produção.

**4. A fração de perdas que nunca passaram do custo**

A previsão específica de queda dessa fração **falhou**. Contudo, subir a fração não significa automaticamente criar mais perdas desse tipo.

Na melhor célula real:

- Controle: **16/35 = 46%**.
- Política: **16/26 = 62%**.

O numerador permanece **16**; o denominador cai de **35 para 26**. Entre as 65 decisões, a incidência é a mesma: **16/65**. A composição das perdas mudou. Isso é compatível com menos perdas totais e maior proporção de perdas que nunca recuperaram o custo. [report.txt:45](C:/dev/project-hunter/.claude/state/r77/report.txt:45).

Não concluiria “esperar recuo piora tudo”, nem “resolvemos comprar no topo”. O mecanismo prometido não apareceu nessa métrica.

**6. Para dizer ao Everton**

> “Esperar o recuo não entregou a melhora que exigimos. No papel, a melhor combinação melhora cerca de dois pontos percentuais contra comprar imediatamente, mas termina praticamente no zero. Nas operações reais, a amostra ainda permite tanto piora quanto melhora relevante. Este estudo não sustenta mudar a entrada da mesa nem aumentar exposição. O próximo passo justificável é uma hipótese nova, congelada e acompanhada em dados futuros.”

A distância entre modelo e operação reforça esse limite: nas mesmas 65 reais, o histórico médio é **−5,42%**, contra **+0,41%** no controle R77. A decomposição de fidelidade ajuda a separar efeitos de gasto e regra de saída, mas não transforma o modelo em reprodução fiel da execução. [fidelity.txt:1](C:/dev/project-hunter/.claude/state/r77/fidelity.txt:1).

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão como `quant-engineer`, em modo OPINIÃO.

**TESTES**

Executei `uv run pytest .claude/state/r77/test_r77.py -q`, com sincronização, bytecode, cache do pytest e carregamento automático de plugins desativados:

```text
45 passed, 1 warning in 7.85s
```

O aviso foi `Unknown config option: asyncio_mode`, decorrente dos plugins desativados.

Também executei verificações via `uv run python -`, sem gravar arquivos:

```text
Recomputacao em memoria: {'paper': 596, 'real': 85}
Divergencias de censura/bracos/elegibilidade: {}
```

Recalcular os contrastes confirmou `REFUTA` em ambas; no papel, Holm **0,051994800519948**. Não refiz a extração da VPS.

**MUST-FIX**

**5. Não encontrei um defeito demonstrado que altere o veredito principal. Encontrei uma falha concreta na sensibilidade `slotfinal`, que precisa ser corrigida antes de apresentá-la como avaliação do estado final de cada slot.**

`build_chain` marca como último ponto a foto, quando ela vem depois dos trades no mesmo slot. `Dip.step` então rejeita o trade por não ser último e rejeita a foto por ser foto. O slot inteiro desaparece da regra de entrada. [chain.py:97](C:/dev/project-hunter/.claude/state/r77/chain.py:97), [entry.py:82](C:/dev/project-hunter/.claude/state/r77/entry.py:82).

**Cenário reproduzido:** preço inicial 100; no slot seguinte, trade a 96 e foto a 96. Com X=3%:

```text
main=1 slotfinal=None
```

O estado final confirma o recuo, mas a sensibilidade não compra. É necessário definir e testar como tratar slots com trade e foto. **Esse achado afeta a sensibilidade; não muda, por si, o `REFUTA` principal.**

**NICE-TO-HAVE**

- Esclarecer que `slotfinal` altera a **entrada**: o caminho entregue à saída continua trade a trade. Um pico e uma queda intrasslot ainda podem determinar alvo ou trailing. [sim_all.py:109](C:/dev/project-hunter/.claude/state/r77/sim_all.py:109), [entry.py:150](C:/dev/project-hunter/.claude/state/r77/entry.py:150).
- Separar falhas das sensibilidades da elegibilidade principal. Hoje qualquer `ok=False` exclui a decisão. O único caso observado falhou em dois braços `photos`; conferi que ele também viola o limite de gap principal, portanto isso **não altera n nesta execução**. [sim_all.py:117](C:/dev/project-hunter/.claude/state/r77/sim_all.py:117).
- Acrescentar sensibilidade por blocos temporais: um mint por decisão não elimina dependência entre moedas negociadas sob o mesmo choque de mercado.
- Publicar a decomposição de D entre entradas e não entradas, junto do nível absoluto.

**O QUE EU FARIA DIFERENTE**

Fecharia a H-016 com **`REFUTA operacional; evidência estatística distinta por população`**. Preservaria a emenda e todas as sensibilidades, sem reajustar agora o critério para aproveitar o +2 pp.

Trataria a disponibilidade instantânea por `block_time` como hipótese do replay. A guarda impede consulta a pontos futuros da cadeia modelada, mas não prova que o WS real entregaria aquela informação naquele instante. Essa suposição já está declarada em [notes-R77.md:34](C:/dev/project-hunter/.claude/state/notes-R77.md:34).

**CONCORDO COM**

- Controle também simulado, relógio da compra materializado e caminho iniciado no pouso. [entry.py:139](C:/dev/project-hunter/.claude/state/r77/entry.py:139).
- Zero para o retorno da não entrada, preservando a diferença contra o controle; bootstrap emparelhado por mint. [rule.py:48](C:/dev/project-hunter/.claude/state/r77/rule.py:48).
- Injetar fills próprios comprovadamente ausentes e conservar `report_v0.txt`. A correção preservou população e rótulo; o melhor D real mudou de **0,0198 para 0,0199**. [report_v0.txt:13](C:/dev/project-hunter/.claude/state/r77/report_v0.txt:13), [report.txt:13](C:/dev/project-hunter/.claude/state/r77/report.txt:13).
- Não chamar reais e papel de replicações independentes, pois compartilham mints. [notes-R77.md:118](C:/dev/project-hunter/.claude/state/notes-R77.md:118).

**OBSIDIAN**

- **Fila de Hipóteses — H-016:** registrar `REFUTA` por (a)/(b), separando o rótulo da interpretação estatística e preservando o congelado.
- **Revisões da Astra — R77 / H-016:** registrar reprodução, avaliação da emenda 9 e falha da sensibilidade `slotfinal`.
- **KB-0149 — O que a mesa real ensinou:** acrescentar que melhora relativa de aproximadamente 2 pp não demonstrou rentabilidade positiva.
- **Ficha do dia — 23/09/2026 · mesa real de memes:** ligar o resultado à investigação das perdas, sem apresentá-lo como estratégia pronta para a mesa.