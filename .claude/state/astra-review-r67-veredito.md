**RESUMO**

Concordo com **“não confirmado fora de amostra; permanece em sombra”**. Evitaria “refutado” e “não sobrevive” sem essa qualificação: o IC contém zero **e** efeitos relevantes ([oos.txt:12](/C:/dev/project-hunter/.claude/state/r67/oos.txt:12)). Ausência de significância não demonstra ausência de efeito ([ASA](https://www.amstat.org/asa/files/pdfs/p-valuestatement.pdf)).

**ARQUIVOS**

Nenhum criado ou modificado. Revisão como `quant-engineer`.

**TESTES**

Não reexecutei os estudos. Conferi código e saídas; cálculo independente em PowerShell pela largura do IC retornou `SE=0,049236; N=1343`.

**MUST-FIX**

- **Potência:** “o IC contém +0,082” está correto. “Precisaria de 1.280” é preciso demais: escreva **“ordem de 1,3 mil mints, sob aproximação normal, variância e proporções constantes e independência”**. Dependência temporal e caudas podem mudar bastante isso. Além disso, R65 mistura tamanhos e saídas: dividir seu efeito agregado por 0,07 produz uma referência aproximada, não uma normalização exata ([load67.py:85](/C:/dev/project-hunter/.claude/state/r67/load67.py:85)). O risco é transformar essa conta em promessa de poder.
- **Exclusões:** a sensibilidade prometida — retorno zero/pior caso e distribuição por dia — não foi entregue ([pré-registro:50](/C:/dev/project-hunter/.claude/state/r67/preregistro.md:50)). O diagnóstico pega indeterminadas de todo o CSV, sem aplicar a seleção principal ([oos.py:237](/C:/dev/project-hunter/.claude/state/r67/oos.py:237)). Percentuais semelhantes não afastam seleção por desfecho; registre a pendência.
- **Transferência:** escreva: **“Não confirmou associação sob as políticas `flow_v2`; não confirma nem refuta benefício sob 1,15×/300s.”** Nem o sinal precisa transferir. `hit15` também não replica diretamente a comparação de medianas de MFE: são métricas e janelas diferentes ([pré-registro:47](/C:/dev/project-hunter/.claude/state/r67/preregistro.md:47)).

**NICE-TO-HAVE**

O pico em **≤15 é exploratório, não prova de artefato**. Diluição ao ampliar o grupo também poderia ocorrer com efeito localizado. Mas 0,022 é fração de réplicas bootstrap, não p ajustado pela busca nem probabilidade da hipótese ([stats67.py:48](/C:/dev/project-hunter/.claude/state/r67/stats67.py:48)). Eu o deixaria no backlog; novo pré-registro só com justificativa própria, dados futuros e orçamento de testes definido.

Correções adicionais: são **5/10 dias negativos**, não quatro ([oos.txt:73](/C:/dev/project-hunter/.claude/state/r67/oos.txt:73)); mints distintos não garantem independência temporal; e este holdout é de mints, não de período futuro.

**O QUE EU FARIA DIFERENTE**

Para Everton: **“Hoje escolhemos um experimento, ainda não uma estratégia comprovada.”** Congelaria corte 25, política da mesa, custos, prazo/amostra e ganho mínimo relevante `δ`, em sombra prospectiva.

Na leitura final: limite inferior do IC acima de `δ` sustentaria benefício relevante; limite superior abaixo de `δ` excluiria esse benefício; intervalo atravessando `δ` permaneceria inconclusivo. Para excluir especificamente +0,082, o limite superior precisaria ficar abaixo disso, **no mesmo desfecho**. Sem prolongar até aparecer significância.

**CONCORDO COM**

Não ligar `max_buys_1m` no real com esta evidência. **D positivo compara dois grupos; não demonstra estratégia lucrativa** — a média selecionada está praticamente zerada ([oos.txt:12](/C:/dev/project-hunter/.claude/state/r67/oos.txt:12)).

**OBSIDIAN**

- **KB-0147 — Custo é o prejuízo:** acrescentar R67 não confirmado, limites de transferência e sensibilidade de exclusões pendente.
- **Revisões Astra — R67** (nova): registrar parecer, potência aproximada e critérios prospectivos de mudança de opinião.