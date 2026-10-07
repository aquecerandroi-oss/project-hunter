**RESUMO**

**DONE_WITH_CONCERNS — eu emendaria o pré-registro antes de iniciar a coorte.** A interação I está correta, e CONFIRMA/REFUTA são alcançáveis. Os problemas principais são a população selecionada pelos tetos, a interferência dos pinos na mesa e uma pré-condição de instrumento que hoje pode aprovar uma vigia sem cobertura.

Respostas diretas: **(1)** desenho estatístico aproveitável, com correções abaixo; **(2)** tetos idênticos permitem apenas conclusão condicionada aos pares admitidos pelos dois lados; alargá-los não garante, sozinho, um superconjunto; **(3)** preservar as fotos, sim; pino ordinário mais exclusão por ID, insuficiente; **(4)** 5 pp/10% não sustentam a garantia pretendida; **(5)** gravar sempre o booleano é a escolha correta, preservando ausência histórica como `True`.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Parecer sobre o [pré-registro congelado](/C:/dev/project-hunter/.claude/state/h031b/prereg_frozen.md:2) e os caminhos indicados; sem consulta a desfechos da coorte.

**TESTES**

Não executei pytest, lint ou migrações nesta revisão de desenho. Conferi a conta de erro-padrão com aritmética em PowerShell:

```text
sd=0,15; SE_iid=0,009387; z_effect_005=5,327
sd=0,30; SE_iid=0,018773; z_effect_005=2,663
```

Esses números são cálculos sob as suposições do pré-registro, não resultados da coorte.

**MUST-FIX**

1. **Declarar exatamente qual população o pareamento identifica. Só contar a censura não corrige a seleção.**

   O preenchimento recusa por perda diária, posições abertas, exposição por mint e saldo disponível: [paper_fill.py:110](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:110). Portanto, parâmetros iguais não produzem admissões iguais.

   **Falha com tetos idênticos:** três originais saem por `creator_dump`; os gêmeos continuam abertos. As próximas oportunidades entram apenas no original. Se chegam em rajadas do mesmo regime, o subconjunto pareado perde justamente episódios relevantes para I. No sentido inverso, perdas realizadas pelo original podem bloquear suas entradas enquanto o gêmeo ainda carrega perdas não realizadas. S1 não recupera apostas que nunca nasceram.

   **Falha com tetos alargados:** o gêmeo aceita oportunidades extras, acumula posições/perdas e depois recusa uma oportunidade aceita pelo original. Tetos maiores, mas finitos, **não provam superconjunto**. A exposição por mint também continua podendo bloquear uma tentativa posterior. Além disso, a coleta adicional pode interferir na mesa.

   **Minha recomendação:** para medir o mecanismo nas entradas efetivamente aceitas pelo original, prefiro um contrafactual vinculado a cada preenchimento original, com mesma entrada e capacidade de pesquisa independente. Isso é uma proposta de alteração de desenho, sujeita ao Everton. Mantendo o que ele aprovou, escrever explicitamente: **I nos primeiros pares admitidos por ambas as políticas**, sem extrapolar para todas as propostas do original. A limitação precisa alcançar também o texto de CONFIRMA/REFUTA, não apenas uma tabela de censura.

2. **Proteger a cauda sem alimentar indiretamente o pedigree da mesa.**

   Concordo com excluir o gêmeo por ID dos dois ramos de apostas em [lab_repo_pedigree.py:77](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_pedigree.py:77). Mas o primeiro ramo lê diretamente `meme_features_1m.creator_sold`, sem identidade de conjunto: [lab_repo_pedigree.py:75](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_pedigree.py:75).

   **Falha concreta:** original fecha por trailing, gêmeo continua fixando a mint; o criador vende depois. A coleta prolongada grava `creator_sold`, e uma moeda posterior desse criador ganha evidência de dump no pedigree da mesa, mesmo com todas as apostas do gêmeo excluídas. O próprio precedente documenta esse caminho: [tracker_pins.py:18](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/tracker_pins.py:18).

   Há ainda interferência por capacidade: pinos ordinários reduzem o espaço das mints não fixadas em [tracker.py:247](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/tracker.py:247).

   **Correção:** garantir fotos até o encerramento, mas com isolamento da capacidade ordinária **e da evidência adicional usada no pedigree**. O pino separado do EXP-M26 oferece precedente para capacidade, não resolve sozinho a proveniência das features. Sem isolamento, não afirmar “não muda recusas do `operator/5`”. Sem fotos, a censura pode crescer precisamente depois do dump que queremos medir.

3. **Substituir “reason nulo” por cobertura comprovada e definir o que a latência mede.**

   `creator_balance_reason IS NULL` significa ausência de motivo gravado, não leitura válida comprovada. A vigia pode retornar por fonte indisponível sem marcar cada aposta: [creator_watch.py:211](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/creator_watch.py:211). Após reinício, ela precisa reconstruir o saldo anterior: [creator_watch.py:112](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/creator_watch.py:112).

   **Falha concreta:** vigia indisponível nos dois lados, campos nulos, “cobertura” de 100%, diferença de 0 pp. O instrumento passa mesmo sem observar quedas.

   A latência também mistura eventos: a vigia detecta **queda de saldo**, enquanto o denominador temporal proposto é a primeira **venda** após a entrada. Uma transferência pode gerar carimbo sem venda correspondente; uma venda anterior à primeira leitura pode não ser detectada.

   Congelaria: denominador, janela comum de observação, leituras válidas necessárias, vendas não detectadas, transferências/sem correspondência e disponibilidade da fita. Comparar cobertura no período comum dos dois lados; a cauda extra do gêmeo é outro diagnóstico. **5 pp pode servir como alarme operacional escolhido a priori, mas precisa de piso absoluto de cobertura.** Latência hoje é descritiva: não há limiar para reprovar o instrumento.

4. **Não tolerar divergência mecânica relevante apenas porque ocorre em menos de 10% dos pares.**

   A regra permite quase 10% dos pares sem `creator_dump` original com erro arbitrariamente grande, desde que os demais coincidam: [pré-registro:7](/C:/dev/project-hunter/.claude/state/h031b/prereg_frozen.md:7).

   **Falha hipotética:** 9% dos pares altos sem dump apresentam Δ espúrio de +0,60; os baixos coincidem. Isso pode fabricar aproximadamente +0,054 na média alta e ainda passar pelo limiar de frequência.

   Além disso, `(mint, features_end_time)` não prova entrada idêntica: o preenchimento usa a primeira foto estritamente posterior a `decided_at`: [paper_fill.py:72](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:72). Decisões separadas por uma foto podem produzir entradas diferentes.

   Exigiria identidade dos parâmetros efetivos, foto de entrada, quantidade e custos, além de diagnóstico de divergência por braço e sua contribuição para I. **0,001 é uma tolerância econômica; 10% não é uma garantia de fidelidade.** Divergências inexplicadas devem bloquear a interpretação mecânica.

   Também corrigiria a ordem: fidelidade usa `exit` e Δ, logo não pode ser publicada “antes de olhar Δ”. Pode ser calculada automaticamente na leitura final, com a regra de bloqueio congelada antes.

5. **Corrigir o poder declarado e completar a especificação inferencial.**

   O IC bilateral de 98,75% deixa 0,625% em cada cauda; portanto combina numericamente com α unilateral de 0,00625. Usar `max(p_mint, p_dia)` exige concordância dos dois testes; não demanda dividir α novamente entre eles.

   Entretanto, **~99%/~56% é aproximadamente o poder de rejeitar I ≤ 0 sob independência**, não o poder de obter CONFIRMA. A regra também exige **Î ≥ 0,05**. Se o verdadeiro I for exatamente 0,05, numa aproximação normal centrada essa cláusula passa em cerca de 50% das amostras, antes de metades, planalto, S1 e instrumento.

   **Falha concreta:** planejar 1.400 pares esperando 99% de chance de confirmação do efeito mínimo e interpretar NÃO CONFIRMA como surpresa. Corrigir a descrição; não relaxar a regra depois.

   Faltam congelar o tipo de IC e o algoritmo dos blocos. O p centrado combina naturalmente com IC básico:
   ` [2Î − q0,99375(I*), 2Î − q0,00625(I*)]`.
   IC percentil pode ser mantido como exigência adicional, mas não é automaticamente equivalente ao p centrado quando há assimetria. Essa distinção é a inversão descrita nas [notas de bootstrap da CMU](https://www.stat.cmu.edu/~cshalizi/dst/18/lectures/18/lecture-18.html).

   Aplicaria **IC finito e ≤1% de réplicas inválidas também ao CONFIRMA**, por cenário. Os mínimos de amostra/dias precisam valer no primário efetivamente medido. Enumeraria ainda as oito hipóteses da família: sem membros ou orçamento explícito, `k=8` não é auditável.

6. **Congelar seleção, maturação e congelamento operacional da coorte.**

   O texto seleciona o “par mais antigo”, conta pares fechados para parar e exclui abertas na leitura: [pré-registro:6](/C:/dev/project-hunter/.claude/state/h031b/prereg_frozen.md:6).

   **Falha concreta:** duas implementações escolhem, respectivamente, a primeira tentativa original ou a primeira tentativa que conseguiu formar par; produzem populações diferentes. Outra divergência surge se uma lê imediatamente ao atingir a contagem e outra espera as apostas recentes fecharem.

   Definir antes: tentativa-âncora por mint, desempate, contagem de **unidades únicas elegíveis**, instante de encerramento de entradas e prazo fixo de maturação. Parar por alteração de parâmetros deve interromper admissões à coorte, não obrigar descarte imediato dos desfechos pendentes.

   O hash de `params` também não cobre mudança do motor. **Falha:** um deploy altera saída ou cotação sem `--set-param`, e a coorte atravessa duas mecânicas com hashes iguais. Registrar versão executada e regra para mudanças relevantes.

**NICE-TO-HAVE**

- **S1:** correto como cenário decisório, mas não como limite conservador de I. Substituir um lado por −1 pode elevar ou reduzir Δ; substituir ambos produz Δ=0. Declarar isso expressamente, como já fez a emenda da H-031.
- **Metades e planalto:** coerentes como requisitos adicionais de estabilidade. Aplicá-los explicitamente no primário e em S1, com fronteira temporal comum. Quatro sinais positivos consecutivos representam estabilidade de sinal, não quatro confirmações independentes.
- **Blocos temporais:** a carteira apura perda no dia de Brasília, conforme [lab_values.py:158](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_values.py:158), enquanto o protocolo usa dias UTC. Consideraria sensibilidade pré-fixada por dia operacional/blocos adjacentes; o máximo dos dois p não elimina dependência temporal não modelada.
- **Monte Carlo:** 10.000 réplicas deixam aproximadamente 62,5 observações na cauda decisória. Aumentar o número antes da análise melhora a estabilidade perto do corte; nunca repetir sementes até passar.

**O QUE EU FARIA DIFERENTE**

Usaria o original como âncora de admissão e preenchimento, com duas trajetórias de saída sobre a mesma evidência, mantendo coleta suficiente e isolada. Isso responde diretamente à pergunta “quanto essa saída mudou esta aposta?” e evita que a carteira do contrafactual escolha quais apostas conseguimos comparar.

Sobre **gravar sempre `exit_on_creator_dump`**: faria isso. Não encontrei leitor de produção inspecionado que exija ausência da chave. Há três detalhes concretos:

- O percurso precisa cobrir `RuleSetSpec → effective_params → as_json/from_json → exit_rules`; hoje a conversão não transmite esse parâmetro: [lab_params.py:148](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_params.py:148). Acrescentá-lo apenas em `from_params` não basta.
- Os dois caminhos de saída precisam respeitá-lo: [lab_bets.py:213](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_bets.py:213) e [exits.py:265](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/exits.py:265). Testar também recarga de aposta após reinício.
- **Quebra observável em teste:** existe comparação exata do JSON antigo em [test_lab_params_moonshot.py:105](/C:/dev/project-hunter/services/meme-worker/tests/test_lab_params_moonshot.py:105); ela precisará mudar intencionalmente. A API atualmente projeta campos conhecidos e não exporá o novo booleano automaticamente: [meme_desk_out.py:103](/C:/dev/project-hunter/apps/api/hunter_api/services/meme_desk_out.py:103).

Usaria booleanos JSON reais; ausência histórica continua `True`, sem reescrever apostas antigas.

**CONCORDO COM**

- **I = D_semdump − D_orig**, desde que os quatro termos usem exatamente os mesmos pares e pesos. Não prova que concentração causa golpe; mede associação entre F e benefício diferencial da saída.
- Dispensar “lucrativo em nível” nesta hipótese de mecanismo, publicando os quatro níveis.
- REFUTA significar “exclui efeito de +0,05 nesta população”, nunca “nenhuma absorção existe”.
- Copiar o `params` vivo, com validação da origem, seguindo [meme_pullback_control_arm.py:78](/C:/dev/project-hunter/infra/migrations/ddl/meme_pullback_control_arm.py:78), em vez de reconstruir o conjunto pelo seed histórico.
- Coorte futura, leitura única, limiar congelado, nenhum resgate do R88 e nenhuma mudança automática na mesa.

**OBSIDIAN**

Nenhuma página foi alterada neste modo OPINIÃO. Deveriam receber:

- **Fila de Hipóteses — H-031b:** emenda pré-coorte sobre população, capacidade, instrumento, inferência, poder e maturação.
- **EXP-M27 — Gêmeo sem creator_dump:** contrato de pareamento, isolamento da coleta e critérios de aceite operacional.
- **KB-0188 — A concentração do maior comprador não separa o retorno:** delimitar o que a nova interação poderá concluir, preservando o resultado do R88.
- **Revisões-Astra — H-031b-prereg:** registrar este parecer e a resolução de cada must-fix.