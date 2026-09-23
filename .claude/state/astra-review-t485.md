**RESUMO**

**Não aprovaria a T4.85 ainda.** O hash não é o problema principal. Há falhas na persistência da primeira decisão, na independência do backlog, no isolamento operacional e na simetria do controle.

Revisão no papel de `quant-engineer`, complementada pela inspeção dos caminhos de banco e execução.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei `pytest`, migrações ou testes com banco nesta revisão somente leitura; os cenários abaixo decorrem da inspeção do código.

Contagem física dos cinco módulos de implementação: **335, 252, 186, 169 e 66 linhas**, respectivamente — dentro do limite. Os testes de invariância existentes verificam acréscimo de linhas, mas não reinício, rollback, repartição do backlog ou atualização das fontes auxiliares. [test_refused_probe.py:204](C:/dev/project-hunter/services/meme-worker/tests/test_refused_probe.py:204), [test_refused_probe_step.py:242](C:/dev/project-hunter/services/meme-worker/tests/test_refused_probe_step.py:242).

**MUST-FIX**

1. **A decisão negativa não é durável: um reinício permite nova comparação contra outra probabilidade.**

   A consulta durável encontra somente propostas; os não selecionados ficam exclusivamente em `drawn`, com retenção de uma hora. [refused_probe_step.py:89](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe_step.py:89), [refused_probe_step.py:110](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe_step.py:110).

   **Cenário:** mint com `u = 0,08`, inicialmente B/base (`p = 0,001`), não entra. O worker reinicia; a primeira linha disponível agora é A/base (`p = 0,10`), e ele entra. O número aleatório é o mesmo, mas houve uma segunda oportunidade de inclusão e o estrato original foi perdido.

   Isso também quebra os pesos: numa população hipotética que toda percorresse B→A após reinício, a contribuição esperada ao total ponderado seria `0,001/0,001 + 0,099/0,10 = 1,99` por mint, em vez de 1.

   **Correção:** persistir a primeira decisão **positiva ou negativa**, com instante, motivos, estrato e probabilidade, sob unicidade por experimento/mint. Atualizar a memória somente após confirmação da transação. Hoje ela é atualizada antes do insert. [refused_probe_step.py:220](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe_step.py:220).

2. **Uma falha do experimento pode desfazer propostas da mesa e perder o tique.**

   Os inserts da mesa e `run_refused_probe` estão dentro da mesma `role_session`; essa sessão representa uma única transação. O checkpoint só avança depois. [lab_fast.py:114](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_fast.py:114), [lab_fast.py:163](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_fast.py:163), [session.py:232](C:/dev/project-hunter/packages/core/hunter_core/db/session.py:232).

   **Cenário:** timeout na consulta `_PROBED` ou erro no insert experimental provoca rollback também das propostas de operator/5 e operator/6. Portanto, “rodar depois dos inserts” não significa rodar depois do commit.

   Além disso, **não é um insert por tique**: `insert_proposals` executa um statement por draft. Um tique com N selecionados acrescenta N inserts sequenciais. [lab_repo.py:252](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo.py:252).

   **Correção:** separar a transação experimental, conter suas falhas e impor orçamento de tempo compatível com a pista rápida.

3. **A elegibilidade depende de como o backlog é agrupado.**

   `admitted` é um conjunto de mints acumulado sobre **todas** as linhas do lote; não é indexado pelo instante. A exclusão ocorre antes de escolher a primeira recusa. [lab_fast.py:148](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_fast.py:148), [refused_probe.py:264](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe.py:264).

   **Cenário:** às 12:00:00 o mint é recusado; às 12:00:15 passa. Processando dois tiques, pode ser sorteado na primeira recusa. Processando ambos após uma pausa, a aprovação posterior elimina a recusa anterior. Ampliar a janela também pode recuperar uma primeira linha com outro estrato; `fast_window` apenas corta pelo backlog disponível. [lab_repo_fast.py:273](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_fast.py:273).

   **Correção:** congelar elegibilidade por `(mint, instante)` e processar os instantes cronologicamente. Se “tique” significar deliberadamente lote de processamento, é necessário declarar que a população depende da disponibilidade do worker; ela não será invariável ao backlog.

4. **A guarda temporal não cobre todas as features gravadas.**

   Os quatro checks protegem os timestamps de `RefusedRow`. Entretanto, a proposta também recebe pedigree, E2-b, identidade e eventos, sem que esses dados sejam abrangidos pela guarda. [refused_probe.py:223](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe.py:223), [refused_probe_step.py:165](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe_step.py:165).

   **Cenário:** um trade antigo chega atrasado. A consulta E2-b limita `block_time`, mas não `received_at`; reprocessar a mesma linha pode mudar concentração, motivos e estrato. O join de eventos também não limita o instante de observação/matching à linha julgada. [lab_repo_e2b.py:86](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_e2b.py:86), [lab_repo_fast.py:38](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_fast.py:38).

   **Correção:** congelar a proveniência de todos os insumos no corte declarado e testar a invariância desde a leitura até o envelope persistido. **Não acrescentaria cegamente `computed_at <= as_of`**: computar depois do fechamento pode ser legítimo; é preciso distinguir tempo da feature, disponibilidade dos insumos e tempo da decisão.

5. **O operator/6 atual não garante a simetria exigida pelo experimento.**

   O probe nasce aprovado com `decided_at = now`; operator nasce `proposed`, e sua aprovação posterior escreve outro `decided_at`. O fill usa a primeira foto posterior a esse horário. [proposals.py:314](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals.py:314), [auto_approve.py:200](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/auto_approve.py:200), [lab_bets.py:107](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_bets.py:107).

   **Cenário:** uma foto chega entre a decisão do Lab e a aprovação da mesa. O probe usa essa foto; o controle usa a seguinte. Além disso, com duas posições abertas ou perda diária atingida, o controle deixa de preencher enquanto o probe continua. Esses limites efetivamente participam da admissão paper. [paper_fill.py:109](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:109).

   **Resposta sobre os três tetos:** aumentá-los é defensável para reduzir censura experimental. **Não invalida toda comparação descritiva**, mas comparar apenas apostas preenchidas deixa de medir somente a seleção do portão. `1/p` não corrige essa seleção adicional.

   **Correção recomendada:** controle exclusivamente de pesquisa, com o mesmo relógio de decisão, política de aprovação e tetos experimentais; preservar a mesa real. Essa escolha precisa constar do protocolo.

6. **A ausência de foto é excluída silenciosamente antes da amostragem.**

   `snapshot_observed_at = None` torna a linha inelegível; não nasce proposta nem resultado explícito de impossibilidade. [refused_probe.py:240](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe.py:240).

   **Cenário:** um mint recusado por falta de informação nunca recebe foto utilizável. Desaparece da população medida, justamente onde o pré-registro exige observar censura e impossibilidade de execução. Se recebe foto depois, sua “primeira oportunidade” passa a representar outro estado.

   **Correção:** separar elegibilidade experimental de possibilidade de cotação; registrar a seleção e o impedimento, mesmo quando não houver aposta preenchível.

7. **Existe interferência indireta nas decisões da mesa real através do pedigree.**

   A consulta de reincidência considera `creator_sold_seen_at` e saídas `creator_dump` de **qualquer** `meme_paper_bets`, sem excluir o probe. Essa evidência alimenta `evaluate_repeat_dumper`. [lab_repo_fast.py:109](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_fast.py:109), [proposals.py:250](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals.py:250).

   **Cenário:** somente o probe acompanha uma moeda recusada; o acompanhamento registra venda do criador. Uma moeda posterior desse criador passa a receber `creator_repeat_dumper` na mesa, quando antes não haveria essa evidência. O watcher inclui apostas paper abertas. [creator_watch.py:72](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/creator_watch.py:72).

   Portanto, **não encontrei encaminhamento direto deste braço para compra real, mas não há isolamento comportamental completo**. É preciso impedir essa realimentação experimental ou obter uma decisão explícita sobre ela.

**NICE-TO-HAVE**

- **Comprovar a classificação de “raro”.** Ausência no censo de quase-falhas não demonstra `<30 mints/semana` na população ampla; quantidade de recusas também não equivale a mints distintos. A implementação usa precisamente essa equivalência. Congelaria uma tabela de contagens distintas e sua origem. [refused_probe.py:124](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe.py:124).
- Testar duplicatas do mesmo instante com proveniências diferentes: a união dos motivos é independente da ordem, mas os outros campos vêm da primeira linha recebida. No caminho atual, ambos os operadores reutilizam a mesma `GateRow`; a função pura, isoladamente, não garante essa igualdade. [refused_probe.py:274](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe.py:274).

**O QUE EU FARIA DIFERENTE**

Usaria um registro durável de decisões experimentais, incluindo não selecionados e impedidos, separado das propostas. Acrescentaria testes de reinício com B→A, rollback, processamento do mesmo histórico em lotes diferentes e chegada tardia de insumos. Mediria também a duração adicional do probe e a censura por braço.

**CONCORDO COM**

- **O hash de 64 bits é adequado.** Sob a hipótese de hash uniforme, a probabilidade efetiva é `ceil(p × 2^64)/2^64`; a diferença para `p` é menor que `2^-64 ≈ 5,42 × 10^-20`. Colisões não eliminam mints nem criam viés marginal relevante, pois a identidade continua sendo o mint. O contexto Decimal de 28 dígitos não altera os limiares usados aqui. [refused_probe.py:206](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe.py:206).
- Sortear uma única vez, guardar todos os motivos e registrar `p` como string são escolhas corretas; falta completar a garantia durável. [refused_probe.py:319](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe.py:319).
- A semente é `research_only`; a seleção automática da mesa exige `operator`, e o executor geral exige `mode = live`. Isso protege o encaminhamento direto inspecionado. [meme_refused_probe_arm.py:108](C:/dev/project-hunter/infra/migrations/ddl/meme_refused_probe_arm.py:108), [auto_approve.py:98](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/auto_approve.py:98), [repo.py:113](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/repo.py:113).

**OBSIDIAN**

- **EXP-M23 — desfecho das recusadas:** registrar os bloqueios e esclarecer corte temporal, controle, sorteios negativos e ausência de cotação.
- **Mesa operator/6:** explicitar seleção por aprovação, latência e tetos na utilização como controle.
- **Revisões Astra — T4.85:** registrar este parecer e os testes necessários para encerrar cada achado.