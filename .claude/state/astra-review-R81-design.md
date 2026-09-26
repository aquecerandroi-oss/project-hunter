**RESUMO**

**(a) Concordo: H-021 concluída — NÃO CONFIRMA por limite de dado.** A cláusula congelada exige 150 decisões resolvidas com cinco minutos de fita; a contagem apresentada encontra apenas uma. Não é preciso abrir desfechos. Isso segue os precedentes H-010/H-013 e a distinção entre insuficiência de dados e refutação em [RESEARCH.md:63](/C:/dev/project-hunter/docs/RESEARCH.md:63).

Eu retiraria apenas **“permanente enquanto `max_age_s = 300`”**. Há seis decisões com idade ≥300 s porque o relógio das features precede a decisão. Logo, existe incompatibilidade estrutural com a população pretendida, mas não impossibilidade matemática de acumular exceções. Não justificaria manter a hipótese aberta esperando atrasos produzirem elegibilidade. [notes-R81.md:22](/C:/dev/project-hunter/.claude/state/notes-R81.md:22)

**(b) Minha recomendação é não abrir os desfechos da E agora.** O diagnóstico cego já fornece o necessário para redesenhar a medição. A E proposta acrescentaria muitas leituras sobre uma variável com problemas de identificação ainda abertos. Priorizaria uma H-021b prospectiva, depois de verificar cegamente a viabilidade do instrumento.

Rodar E não “inutiliza” os dados: transforma essa amostra em desenvolvimento para as escolhas informadas pelos resultados. Entretanto, congelar agora não transforma uma exploração adaptada em confirmação da H-021. Mesmo sem rodar E, uma coorte prospectiva precisará começar depois do novo pré-registro, com mints novos e regra de encerramento fixa.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Li os scripts, testes, contagens cegas e o bloco no commit `11663e51`. Não abri os CSVs de desfechos nem executei a E.

**TESTES**

Não executados nesta revisão estática em modo OPINIÃO. Os testes existentes foram inspecionados; não afirmo que passaram.

**MUST-FIX**

Os itens abaixo bloqueiam a interpretação proposta da E, **não o encerramento da H-021**.

1. **Primeira troca arquivada não identifica necessariamente o slot de criação.**

   O export busca a primeira troca disponível; a E aceita até cinco segundos após `created_at` e usa seu slot como criação. Isso é uma aproximação, não uma identidade comprovada. [q_first.sql:5](/C:/dev/project-hunter/.claude/state/r81/q_first.sql:5), [h021.py:22](/C:/dev/project-hunter/.claude/state/r81/h021.py:22)

   **Falha concreta:** a criação ocorreu no slot S, mas a primeira troca arquivada é uma venda em S+8, quatro segundos depois. A E exclui essa venda como “criação”; se ela era o mínimo, altera distância, tercil e rompimento.

   **Correção:** usar o slot de criação comprovado. Quando indisponível, marcar desconhecido ou assumir explicitamente outra variável: “excluído o primeiro slot arquivado”, com sensibilidade incluindo-o. A tolerância de cinco segundos não comprova cobertura desde o nascimento.

2. **Começo antigo do arquivo não comprova cobertura da janela; s1 também precisa dessa distinção.**

   `covered()` verifica somente a data da primeira troca. A elegibilidade E também olha apenas o começo do arquivo. Já s1 filtra as trocas usadas, mas herda a elegibilidade e o slot obtidos retrospectivamente. [r81.py:82](/C:/dev/project-hunter/.claude/state/r81/r81.py:82), [h021.py:31](/C:/dev/project-hunter/.claude/state/r81/h021.py:31)

   **Falha concreta:** há uma troca no nascimento, falta um poll que continha a mínima, e existem trocas recentes. A janela passa como coberta, mas a mínima observada é maior que a verdadeira. Em s1, uma única troca disponível pode produzir `dist = 0`, parecendo proximidade do suporte quando significa falta de histórico.

   **Correção:** separar “arquivo começa suficientemente cedo” de “janela reconciliada/completa”; publicar lacunas e frescor da última troca. Para s1, recalcular a evidência de cobertura com a informação disponível antes de T. Sem comprovação, chamar a medida de **mínima observada no arquivo**, não suporte de toda a vida.

   O corte estrito `block_time < T` está correto para a reconstrução retrospectiva. Ele não prova disponibilidade ao vivo. O próprio contrato distingue `meme_trades` de `meme_decision_tapes`. [r81.py:61](/C:/dev/project-hunter/.claude/state/r81/r81.py:61), [RESEARCH.md:98](/C:/dev/project-hunter/docs/RESEARCH.md:98)

3. **O desempate atual não determina a última transação do slot.**

   A ordenação termina em índices locais e assinatura. O repositório documenta que `event_index` é ordinal **dentro da transação**, não posição da transação no bloco; os índices de instrução podem ser nulos. [r81.py:139](/C:/dev/project-hunter/.claude/state/r81/r81.py:139), [repo_tape.py:6](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/repo_tape.py:6)

   **Falha concreta:** duas transações no último slot têm preços 1 e 2. A assinatura lexicograficamente maior decide `price_t`; trocar apenas as assinaturas muda distância e rompimento, sem mudar a trajetória econômica.

   **Correção:** recuperar ordem verificável ou declarar o fechamento do slot ambíguo. Uma alternativa descritiva é calcular os resultados possíveis usando os preços mínimo/máximo do último slot e marcar classificações instáveis. Excluir o último slot da referência do rompimento evita autorreferência, mas não resolve a escolha do preço final. [r81.py:67](/C:/dev/project-hunter/.claude/state/r81/r81.py:67)

4. **Preço de fill misturando compras e vendas não pode ser interpretado diretamente como estrutura marginal.**

   O adaptador diferencia `fillPriceSol` de `priceSol`, o preço marginal após o fill. O objeto `Trade` da análise conserva o preço, mas descarta o lado. [board_models.py:194](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/pumpfun/board_models.py:194), [r81.py:30](/C:/dev/project-hunter/.claude/state/r81/r81.py:30)

   **Falha concreta, sintética:** com marginal aproximadamente estável em 1, uma venda a 0,98 e uma compra a 1,02 produzem distância de aproximadamente 4,08% e podem produzir rompimento. A variável está respondendo ao lado/custo do fill, sem alta equivalente do marginal.

   **Correção:** é legítimo estudar fills, mas nomear essa medida e congelar um diagnóstico por lado antes dos resultados. Para H-021b sobre estrutura, preferiria uma série marginal comparável e observável. Não basta descontar uma taxa constante: impacto e tamanho do negócio também podem importar. Não recobrar custos nos retornos já líquidos.

5. **Corrigir três divergências concretas no script exploratório antes de congelá-lo.**

   - **Razões sem denominador:** `tertiles()` devolve infinito quando a taxa baixa é zero **ou ausente**. Assim, zero casos em ambos os grupos satisfaz artificialmente “≥1,5×”. Também apresenta zero vencedoras como fração zero por usar `max(1, denominador)`. Esses casos precisam ser “não avaliável”; ambos os grupos com taxa zero não atendem à concentração. [h021.py:64](/C:/dev/project-hunter/.claude/state/r81/h021.py:64)
   - **s4 remove também o controle:** `startswith("recuo")` exclui `recuo_ctrl_v1`, embora o desenho diga “sem `recuo_v1`”. **Falha:** o contraste muda pela retirada do controle de entrada imediata. Usar identificação exata do braço. [h021.py:163](/C:/dev/project-hunter/.claude/state/r81/h021.py:163)
   - **O spec do moinho ainda anuncia CONFIRMA/H-021:** ele contém regra confirmatória e compara selecionados `dist ≤ c2` contra bloqueados — contraste diferente de baixo contra alto. **Falha:** um relatório automático pode aparecer como confirmação da hipótese encerrada. Identificar como E e impedir que o rótulo mecânico seja promovido a veredito; conservar proveniência real e declarar qualquer dispensa de observabilidade. [mill.py:12](/C:/dev/project-hunter/.claude/state/r81/mill.py:12), [RESEARCH.md:95](/C:/dev/project-hunter/docs/RESEARCH.md:95)

**NICE-TO-HAVE**

- **Preço em tercis é controle grosseiro de progresso.** Persistência dentro dos tercis não demonstra informação incremental; pode restar associação com preço, idade e política de saída. Tratar s2 como diagnóstico, não prova de independência.
- **Fundos mais altos têm outra população:** são 175 observações com valor, contra 623 na distância. Publicar denominadores e composição por idade; não comparar os efeitos como se viessem da mesma população. [blind_e.txt:6](/C:/dev/project-hunter/.claude/state/r81/blind_e.txt:6)
- **Spearman com empates:** o duplo `argsort` atribui postos distintos aos valores iguais. Usar postos médios antes de tomar 0,60 como medida exata. [blind_e.py:26](/C:/dev/project-hunter/.claude/state/r81/blind_e.py:26)
- **Separar duas frações de vencedoras:** alto/todas em P_E e bloqueadas/todas nas posições reais são diagnósticos distintos. A cláusula original refere-se ao contrafactual real. Tampouco `−ΣPnL bloqueado` simula capital liberado, novas entradas ou reentradas.

**O QUE EU FARIA DIFERENTE**

Fecharia a H-021 agora e faria primeiro uma auditoria cega de **criação, continuidade, ordem, preço e disponibilidade em T**. Depois pré-registraria a H-021b com uma única definição operacional, mínimo de histórico compatível com a idade da porta e política explícita para dado ausente.

Não condicionaria a existência da H-021b a “E mostrou algo”. Isso torna a exploração um seletor de hipóteses sem resolver o instrumento.

Também não transportaria o corte da E para `max_distance_to_support_pct`: a produção projeta a reta pelos dois últimos mínimos locais; a E usa uma mínima de negócios. Além disso, o portão recusa linha ausente. São medidas e mecanismos de seleção diferentes. [lines.py:244](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/lines.py:244), [rules_criteria.py:166](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/rules_criteria.py:166)

**CONCORDO COM**

O encerramento sem desfechos; a separação formal entre H-021 e E; ausente diferente de zero; deduplicação antes da censura; limiares congelados; Holm; e exigir nova coorte antes de qualquer confirmação ou braço. A disciplina é coerente com [KB-0149:72](/C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md:72).

**OBSIDIAN**

- **Fila de Hipóteses** — registrar H-021 concluída, NÃO CONFIRMA por limite de dado, preservando o bloco congelado.
- **Dicionário de Variáveis** — distinguir distância à mínima de fills, distância à reta de suporte e disponibilidade de cada medida.
- **Perdas/comprou_no_topo** — acrescentar H-021 como encerramento por dados, sem evidência contra o mecanismo.
- **Revisões-Astra / R81 — desenho da H-021** — registrar este parecer cego, a recomendação de não abrir E agora e os requisitos da H-021b.