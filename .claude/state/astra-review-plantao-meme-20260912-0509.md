**RESUMO**

Testaria **M-P21 primeiro entre as novas hipóteses**, após validar relógios e conclusão por programa: usa metadata já prevista e pode impedir que um sinal temporalmente instável vire filtro. Instrumentaria **M-D4 junto**, para acompanhar também os rejeitados. M-P23 vem depois: exige identificar direitos, carteiras e estoque; a diferença entre programas não isola incentivo. [Inbox:114](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:114), [116](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:116), [117](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:117).

Isso **revisa minha prioridade anterior de M-P20v2**, registrada na linha 113: coletaria rugcheck prospectivamente desde já, mas priorizaria M-P21 na análise pelo menor custo de aquisição declarado. Não confundiria essa prioridade com autorização para promover features.

**ARQUIVOS**

Somente os dois recortes solicitados foram lidos; nenhum arquivo alterado. Parecer sobre o texto fornecido, sem revalidar fontes externas ou consultar o parecer anterior.

**TESTES**

Não executados: revisão documental em modo OPINIÃO.

**MUST-FIX**

- **M-P20v2 — equivalência:** a margem própria resolve a incompatibilidade de escala, mas escreva explicitamente: **IC95% inteiro dentro de [0,67; 1,50] → equivalente; inteiro abaixo de 0,67 ou acima de 1,50 → diferença relevante; demais casos → inconclusivo**. Estimativa pontual dentro não basta. Cenário: RR=1,10 com IC=[0,40; 2,00] receber “não separa”. [Inbox:113](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:113).

- **M-P20v2 — significado e potência:** defina RR como **risco acumulado em 24 h**, não hazard ratio. A margem admite até 50% de aumento relativo; precisa justificar por que isso seria irrelevante ao funil. Os “100 avaliáveis” são piso de cobertura, não potência: dimensione por eventos esperados, precisão e blocos de dia; zero eventos não demonstra equivalência. Cenário: tercis pequenos sem conclusões encerram prematuramente uma hipótese útil. [Inbox:113](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:113).

- **M-P21 — decisão e disponibilidade dos rótulos:** a hipótese diz ≤0,55, mas só aceita refutação acima de 0,60. Separe refutação estatística de relevância operacional; IC=[0,56; 0,59] refuta a primeira sem atingir a segunda. Aguarde maturar os rótulos de 24 h antes de iniciar validação, ou retire do treino as criações ainda imaturas. Cenário: ajustar no início do dia 16 usando conclusões que só seriam conhecidas durante esse dia. [Inbox:114](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:114).

- **M-P23 — exposição e desfecho:** classifique o direito efetivo por lançamento/estado on-chain; fixe estoque imediatamente anterior à migração e tratamento de recompras/transferências. Tire **volume da primeira hora** do ajuste primário: ele inclui as próprias vendas estudadas. Cenário: controlar pelo efeito das vendas apaga a associação; carteira financiada em um salto, mas independente, infla “venda do criador”. Apresente associação entre grupos, sem atribuição causal ao incentivo. [Inbox:116](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:116).

- **M-P22/M-D4 — protocolo econômico incompleto:** congele stop, limiar X, entrada, saída e tratamento de execução impossível; M-D4 precisa desses contrafactuais para chamar rejeição de “save/miss”. Defina MFE zero e unidades de `captured_share`. A taxa “1,25% ida e volta” também precisa reconciliação com a tabela que informa 1,25% na curva. Cenário: custo subestimado transforma perda em “miss” e favorece um bracket artificialmente. [Inbox:115](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:115), [117](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:117), [Lane:140](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0509-lane4.md:140).

**NICE-TO-HAVE**

M-P20v2 compara extremos; acrescente secundário pré-fixado para relação não monotônica. Tercis extremos equivalentes podem esconder um tercil central informativo. Em M-P21, acrescente precisão no orçamento de alertas e curva precisão–recall; AUROC isolada não determina utilidade. [Inbox:113](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:113), [114](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:114).

**O QUE EU FARIA DIFERENTE**

O hype está nas extrapolações: **um modelo falhar não demonstra que features sociais universalmente falham**; “não encontramos” não autoriza “não existe” nem “T4.2 é a única fonte”; documentação de taxas não demonstra comportamento do criador. O próprio rascunho reconhece limites da busca. [Lane:42](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0509-lane4.md:42), [103](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0509-lane4.md:103), [149](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0509-lane4.md:149).

Também retiraria “fee menor ⇒ sniping, não sandwich”: comparar priority fee por transação com tip por ataque não identifica estratégia. E restringiria “a saída decide” ao experimento citado; não prova edge no nosso mercado. [Lane:159](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0509-lane4.md:159), [85](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0509-lane4.md:85).

**CONCORDO COM**

As v2 **incorporam substancialmente as correções descritas**: coorte e censura em M-P18; unidade transacional, tip local e disponibilidade em M-P19; inclusão sem exigir pool, coleta prospectiva e margem própria em M-P20. Sem reler o parecer anterior, não certifico correspondência integral. [Inbox:111](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:111), [112](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:112), [113](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:113).

Concordo também que relógio externo não reconstrói nossa disponibilidade histórica; taxas-base externas devem permanecer vinculadas à coorte e à definição de desfecho. [Lane:126](C:/dev/project-hunter/.claude/state/plantao-meme/2026-09-12-0509-lane4.md:126).

**OBSIDIAN**

- **Hipóteses do plantão** — explicitar decisões de equivalência, maturação dos rótulos e protocolos econômicos.
- **KB-0092 — O modelo pré-registrado que morreu no holdout** — limitar a conclusão ao modelo, coorte e validação relatados.
- **02-MARKET/Meme/2026-09-12** — registrar M-P21 como prioridade proposta, M-D4 como instrumento e as extrapolações rejeitadas.