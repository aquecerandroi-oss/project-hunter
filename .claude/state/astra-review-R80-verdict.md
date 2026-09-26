**RESUMO**

**Manteria NÃO CONFIRMA.** Reproduzi integralmente `h020.txt`. O cálculo sustenta o rótulo; as correções necessárias estão principalmente na interpretação da observabilidade e do mecanismo.

**(1) Regra congelada:** pela cláusula (a) **isolada**, daria REFUTA. Mas o protocolo efetivo já incorporava a errata do R76 **antes dos desfechos**: (a) sozinha não refuta; a refutação pelo intervalo exige `IC inf > −0,01`. Isso está explícito em [notes-R80.md:37](C:/dev/project-hunter/.claude/state/notes-R80.md:37), com precedente em [notes-R76.md:123](C:/dev/project-hunter/.claude/state/notes-R76.md:123).

O IC `[−0,1229; +0,0161]` contém zero **e −0,05**. Portanto, não confirma nem exclui o efeito previsto. As demais cláusulas também não refutam: cobertura 70,3%, 173 expostas e 25,5% das vencedoras na população primária bloqueadas. Confirmação falha também por Holm, golpe e vencedoras reais sacrificadas. [notes-R80.md:79](C:/dev/project-hunter/.claude/state/notes-R80.md:79)

Publicaria: **“NÃO CONFIRMA pelo protocolo emendado antes dos desfechos; a cláusula (a) original, lida literalmente, acionaria REFUTA.”**

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit. Revisão no papel de `quant-engineer`.

**TESTES**

Executei com escrita de bytecode/cache e sincronização do ambiente desabilitadas:

```text
uv run pytest .claude/state/r80/test_r80.py -q
...........................                                              [100%]
27 passed in 1.20s
```

Também executei `h020.main()` e diagnósticos dos CSVs em memória, via `uv run python -`:

```text
h020_saved_exact_match True
s1c_missing_reasons {(True, False): 184}
s1c_own_read_after_exit 58
real_rows_unique_bet_ids_unique_mints 161 161 145
KODA_rows_unique_ids_unique_mints 2 2 1
golpe_edge_A_10pct_B_0pct actual= False frozen_expected= True
```

A chave `(True, False)` significa: identidade própria indisponível em T, **sem** insuficiência da cobertura histórica. Nenhuma das 184 observações ocorreu exatamente em T: todas foram posteriores. Não consultei produção; a interrupção do REST é o fato registrado nas notas, não uma verificação operacional nova.

**MUST-FIX**

1. **Corrigir a explicação do s1c e registrar seleção informativa como possibilidade concreta.**

   **(2)** Nos dados congelados, as **184 exclusões são por identidade própria observada depois de T**; nenhuma decorre de cobertura `known_only < 60%`. Em **58/184**, a primeira observação ocorreu depois da saída. O filtro permite distinguir precisamente essas causas. [h020.py:34](C:/dev/project-hunter/.claude/state/r80/h020.py:34), [h020.py:100](C:/dev/project-hunter/.claude/state/r80/h020.py:100), [r80.py:122](C:/dev/project-hunter/.claude/state/r80/r80.py:122)

   Existe mecanismo de seleção no coletor:

   - Apostas **de papel abertas** recebem prioridade no REST. [repo_tape.py:146](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/repo_tape.py:146), [collect.py:182](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/collect.py:182)
   - Posições reais e apostas abertas, com exceções explícitas, protegem o mint contra expulsão do rastreamento. [tracker_pins.py:52](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/tracker_pins.py:52)
   - A seleção REST depende dessa prioridade, de leituras anteriores e do orçamento disponível. [tracker.py:271](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/tracker.py:271), [tracker.py:317](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/tracker.py:317)

   **Cenário de falha:** duas moedas entram sem identidade disponível. Uma encerra rapidamente e perde prioridade; outra permanece aberta e consegue leitura REST. A inclusão retrospectiva passa a depender da trajetória que também produz o desfecho. Isso pode distorcer D mesmo com link imutável.

   **Não está demonstrado que esse mecanismo explica o D negativo.** Sua existência está demonstrada no código atual; atribuir-lhe o resultado exige conferir versões históricas e a sequência de rastreamento/leitura. Registrar s1b/s1c como **diagnóstico pós-hoc de observabilidade**, com todos os números, sem alterar população, limiar ou rótulo. O IC do s1c excluir zero e seu p ser 0,054 não é contradição: são procedimentos diferentes, e nenhum autoriza promovê-lo a descoberta confirmatória.

2. **Retirar duas conclusões mais fortes que a evidência: “atenua rumo a zero” e “o mecanismo falha”.**

   As notas afirmam ambas. [notes-R80.md:44](C:/dev/project-hunter/.claude/state/notes-R80.md:44), [notes-R80.md:80](C:/dev/project-hunter/.claude/state/notes-R80.md:80)

   **Cenário de falha:** se reusos de moedas vencedoras forem menos observados, essas vencedoras migram para B; A parece pior e o contraste se afasta de zero. Cobertura incompleta com seleção dependente da trajetória não garante atenuação.

   Redação defensável: **“A previsão de duplicação do golpe não foi corroborada: razão observada 1,02×. O contraste de retorno é sensível à observabilidade temporal; a direção do viés é desconhecida.”** Uma condição confirmatória falhar não demonstra inexistência do mecanismo.

3. **Não apresentar a guarda do moinho como certificação de disponibilidade em T.**

   O adaptador usa `created_at` das correspondências como proveniência e atribui `computed_at=T`; descarta os horários de observação ao montar esses campos. [h020_mill.py:21](C:/dev/project-hunter/.claude/state/r80/h020_mill.py:21)

   **Cenário de falha:** moeda criada ontem, link conhecido amanhã, decisão hoje. A guarda aceita porque recebe o horário da criação. “Zero recusadas” não demonstra ausência de antecipação operacional.

   Para publicar o R80, basta explicitar essa limitação: **associação retrospectiva sob a premissa de metadado da criação**. Para um filtro executável, será necessário preservar a proveniência do **valor**. `COALESCE` independente permite preencher o link posteriormente mantendo um `social_observed_at` anterior; `known_only` continua aproximação, como o próprio adendo reconhece. [repo_token_sql.py:85](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/repo_token_sql.py:85), [notes-R80.md:43](C:/dev/project-hunter/.claude/state/notes-R80.md:43)

4. **Corrigir o caso `golpe B=0, A>0` antes de reutilizar o julgador.**

   `g_ok` exige `gb > 0`, embora o adendo só tenha excluído **ambas as taxas zero**. [h020.py:139](C:/dev/project-hunter/.claude/state/r80/h020.py:139), [notes-R80.md:45](C:/dev/project-hunter/.claude/state/notes-R80.md:45)

   **Cenário reproduzido:** A=10%, B=0%, restantes condições satisfeitas. A regra congelada de taxas passa; o código devolve falso e impede CONFIRMA. Usaria taxas finitas, `ga > 0` e `ga >= 2*gb`, sem calcular razão quando B=0. **Não muda o R80 atual.**

**NICE-TO-HAVE**

**(4) Demais pontos do `h020.py`:**

| Ponto | Parecer |
|---|---|
| `sellers` desconhecido | Correto para a definição congelada: perda sem fita e sem `creator_dump` permanece desconhecida; ganho já é não-golpe porque a definição exige perda. `rate()` exclui `None`. [r80.py:184](C:/dev/project-hunter/.claude/state/r80/r80.py:184), [h020.py:50](C:/dev/project-hunter/.claude/state/r80/h020.py:50) |
| Vendas ausentes com compras presentes | O zero é coerente com a extração: nenhuma venda registrada, embora existam trocas. Isso não certifica completude da fita. [q_pop.sql:19](C:/dev/project-hunter/.claude/state/r80/q_pop.sql:19), [h020.py:17](C:/dev/project-hunter/.claude/state/r80/h020.py:17) |
| `legible` | Implementa os dois pisos congelados; `legible_k` usa cobertura e reuso sob o mesmo corte temporal. [h020.py:29](C:/dev/project-hunter/.claude/state/r80/h020.py:29) |
| `enrich` no contrafactual | Correto: recalcula por posição e pelo respectivo `decided_at`, sem herdar a classificação da primeira entrada. [h020.py:24](C:/dev/project-hunter/.claude/state/r80/h020.py:24), [h020.py:119](C:/dev/project-hunter/.claude/state/r80/h020.py:119) |
| Holm | Correto: família de duas hipóteses, ajustes ≈0,366 e exigência no CONFIRMA. As sensibilidades não passam a integrar essa família retrospectivamente. [h020.py:88](C:/dev/project-hunter/.claude/state/r80/h020.py:88), [h020.py:150](C:/dev/project-hunter/.claude/state/r80/h020.py:150) |

Corrigiria ainda a legenda temporal: `a <= day < b` exclui 22/09 na primeira janela, embora a tabela diga “16–22”. [h020.py:111](C:/dev/project-hunter/.claude/state/r80/h020.py:111)

**O QUE EU FARIA DIFERENTE**

**(5) Próximo passo honesto: fechar este resultado e reparar o instrumento antes de acumular outra amostra.**

1. Publicar R80 como **NÃO CONFIRMA**, preservando o protocolo, a errata e o caráter exploratório do s1c.
2. Investigar a parada de **25/09 17:13:16Z**: erros da fonte, execução do loop, orçamento e seleção. O RPC continuar funcionando não recompõe identidade: somente o REST marca a observação social nesse caminho. [notes-R80.md:24](C:/dev/project-hunter/.claude/state/notes-R80.md:24), [curve_rows.py:71](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/curve_rows.py:71)
3. Recomendar captura de identidade com valor, fonte e horário próprios, ausência explícita separada de falha e coleta independente da duração da posição.
4. Depois da recuperação, reservar **população nova**, com 24 horas anteriores de cobertura verificável, protocolo e regra de parada fixados antes dos resultados. Recuperar dados antigos pode melhorar a descrição histórica; não os torna conhecidos em T.

Não escolheria perfil, horário ou atraso REST pelo melhor D encontrado no R80.

**CONCORDO COM**

**(3) KODA duas vezes não é erro na soma.** Conferi: duas posições distintas, dois `bet_id`, um mint. O contrafactual congelado usa **todas as posições reais**, enquanto a primária usa a primeira decisão por mint. [notes-R80.md:36](C:/dev/project-hunter/.claude/state/notes-R80.md:36), [h020.py:119](C:/dev/project-hunter/.claude/state/r80/h020.py:119)

O nome correto é **“contrafactual contábil sobre as posições históricas”**: +0,1513 SOL e 13/53 vencedoras sacrificadas. Não é uma simulação integral da carteira: bloquear a primeira entrada pode mudar recompras, pausas, capital e coleta posterior. Para eventual inferência, posições do mesmo mint não seriam independentes.

Concordo, portanto, com o rótulo proposto e com não transformar esse saldo positivo isolado em filtro aprovado.

**OBSIDIAN**

- **Fila de Hipoteses — H-020:** concluir como NÃO CONFIRMA, explicitando a errata prévia e os critérios que falharam.
- **Dicionario de Variaveis:** registrar reuso detectado, diferença entre observação retrospectiva e disponibilidade em T, e interrupção da fonte.
- **golpe_do_criador:** acrescentar H-020 como tentativa não confirmada, sem afirmar ausência do mecanismo.
- **Revisoes-Astra — R80/H-020:** registrar reprodução, diagnóstico 184/184 e 58 pós-saída, limites do contrafactual e bug `B=0`.
- **Diario/2026-09-26:** registrar a investigação pendente da coleta REST e os requisitos para uma coorte prospectiva válida.