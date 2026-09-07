**RESUMO**

**Não aprovaria a T3.6 ainda.** Há caminhos de retomada com evidência inadequada, autorização insuficiente e adoção incorreta da referência diária. A tolerância de 60 s **não prova patrimônio de meia-noite**, inclusive exatamente no limite.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Revisão estática do código, testes e DDL. Não executei testes nem reproduções no banco neste modo OPINIÃO; os cenários abaixo são deduzidos dos caminhos indicados.

**MUST-FIX**

1. **[routers/risk.py:58](C:/dev/project-hunter/apps/api/hunter_api/routers/risk.py:58) — ALTA — TRADER não equivale à identidade autorizada do Everton.**  
   **Cenário:** um TRADER convidado encontra a carteira recuperada, chama `POST …/resume` e remove BLOQUEADO. A rota registra corretamente o usuário autenticado na linha 166, mas nunca verifica se ele é a pessoa autorizada pelo contrato. O conflito já está nas notas; documentá-lo não fecha a autorização.

2. **[resume.py:113](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:113) — ALTA — fornecer `state` contorna as referências duráveis e todas as verificações do caminho de snapshots.**  
   **Cenário:** pico persistido 22.000, equity atual 20.000: drawdown de 9,09%, ainda bloqueante. O chamador fornece um `PortfolioState` com pico e abertura 20.000. `assess` calcula zero e permite retomar. Também não há conferência de `portfolio_id`, idade ou dia desse `state`. Pior: a auditoria registra o pico durável na linha 153 e o drawdown calculado com outro pico — números incompatíveis na mesma evidência.

3. **[resume.py:225](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:225) — ALTA — uma observação anterior ao bloqueio é aceita como prova de recuperação.**  
   **Cenário:** snapshot às 12:00:00 registra 20.000; avaliação às 12:00:30 encontra 19.500 e bloqueia; retomada às 12:00:31 usa o snapshot de 31 segundos atrás e destrava. Não houve recuperação. O limite de 120 s contradiz, nesse cenário, a promessa das linhas 5–14 de provar que o gatilho deixou de atuar.

4. **[resume.py:213](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:213) — ALTA — a seleção não restringe resolução nem exclui timestamps futuros.**  
   **Cenário futuro:** existe uma linha com `ts=amanhã`, equity 20.000; agora a carteira vale 19.500. Ela vence o `ORDER BY`, sua idade é negativa e passa pelo único teste, `age > 120s`, permitindo retomada.  
   **Cenário de resolução:** linhas `1m` e `1h` compartilham o mesmo `ts`, com valores divergentes. A PK permite ambas ([portfolios.py:160](C:/dev/project-hunter/packages/core/hunter_core/db/models/portfolios.py:160)); ordenar somente por `ts` não determina qual será usada. A retomada pode usar a agregação favorável em vez da observação operacional.

5. **[tables.py:104](C:/dev/project-hunter/infra/migrations/ddl/tables.py:104) — ALTA — a evidência de recuperação é regravável pelo próprio papel da API.**  
   **Cenário:** uma escrita indevida executada como `hunter_app`, dentro da organização correta, altera o snapshot recente de 19.500 para 20.000; o próximo `resume` aceita a recuperação fabricada. O grant é DML completo ([grants.py:65](C:/dev/project-hunter/infra/migrations/ddl/grants.py:65)). **RLS não protege a integridade dos números dentro do próprio tenant.** Não encontrei uma rota HTTP para editar snapshots; o caminho identificado é pelo privilégio SQL da aplicação.

6. **[daily.py:128](C:/dev/project-hunter/packages/core/hunter_core/risk/daily.py:128) — ALTA — a primeira amostra até 60 s depois da virada pode apagar uma perda diária já ocorrida.**  
   **Cenário:** patrimônio à meia-noite de São Paulo = 20.000; às 00:00:30 = 19.500. A avaliação adota 19.500 como abertura: perda diária calculada zero, embora a perda desde meia-noite seja 2,5%. Com pico 20.000, o drawdown de 2,5% também não bloqueia.  
   **Exatamente às 00:01:00:** o `<=` ainda adota. Um microssegundo depois, declara indisponibilidade. A cadência do pico não justifica essa diferença na referência diária. Persistir o instante real torna o erro visível, mas não o corrige.

7. **[kill_switch.py:111](C:/dev/project-hunter/packages/core/hunter_core/risk/kill_switch.py:111) — ALTA — a avaliação aceita equity sem validar sua atualidade ou completude.**  
   **Cenário:** o chamador conserva um estado das 23:59, equity 20.000, e o entrega com `now=00:00:30`, quando o patrimônio já caiu para 19.500. O código usa a equity antiga e grava `day_reference_observed_at=00:00:30`. Assim, até o “instante real da observação” fica incorreto. A única validação do estado recebido é o ID da carteira, na linha 106; `state.as_of` e `marks_complete` não são examinados.

8. **[kill_switch.py:118](C:/dev/project-hunter/packages/core/hunter_core/risk/kill_switch.py:118) — ALTA — a avaliação completa continua incompatível com os privilégios dos papéis implantados.**  
   **Cenário:** na virada, é necessário persistir a referência e mover AVISO para ACTIVE. `hunter_app` não pode escrever os campos da referência ([paper.py:81](C:/dev/project-hunter/infra/migrations/ddl/paper.py:81)); `hunter_worker` não recebe escrita em `portfolios` ([tables.py:121](C:/dev/project-hunter/infra/migrations/ddl/tables.py:121)). A transação aborta.  
   Além disso, a retomada usa `publish=False` por padrão ([resume.py:90](C:/dev/project-hunter/packages/core/hunter_core/risk/resume.py:90)): o desbloqueio pode ser confirmado sem produzir o `kill_switch.changed` exigido pelo contrato. As notas reconhecem esses bloqueadores, mas eles permanecem no caminho entregue.

9. **[transitions.py:127](C:/dev/project-hunter/packages/core/hunter_core/risk/transitions.py:127) — ALTA — o caminho público de transição não adquire a trava que deveria serializar movimentos e entradas.**  
   **Cenário:** sessão A executa `effective_state(lock=True)` e lê ACTIVE, mantendo a trava de `portfolio_risk_state`; sessão B chama diretamente `record_transition(ACTIVE → TRADING_DISABLED)` e commita, pois atualiza outra linha, em `portfolios`; A continua com ACTIVE e aplica a entrada. A auditoria de B pode estar perfeitamente válida sem impedir essa corrida. O helper precisa impor a disciplina de lock ou ter uma precondição verificável.

10. **[routers/risk.py:120](C:/dev/project-hunter/apps/api/hunter_api/routers/risk.py:120) — MÉDIA — a resposta pode anunciar entradas liberadas com referência diária indisponível.**  
    **Cenário:** avaliação tardia preserva a trava ACTIVE e grava abertura desconhecida; o GET retorna simultaneamente `blocks_entries=false` e `daily_reference.available=false`. Isso contradiz a promessa de “entries blocked” em [schemas/risk.py:33](C:/dev/project-hunter/apps/api/hunter_api/schemas/risk.py:33). É um erro de informação do endpoint; não é prova de que a admissão integrada aprove entradas nesse estado.

**NICE-TO-HAVE**

Nenhum adicional sem cenário de falha.

**O QUE EU FARIA DIFERENTE**

Unificaria os dois caminhos de retomada: identidade autorizada, referências duráveis e observação operacional com proveniência, instante válido e evidência posterior ao bloqueio. Separaria explicitamente a observação da meia-noite da cadência de amostragem do pico.

**CONCORDO COM**

- Não encontrei desbloqueio persistido sem transição ou sem pessoa nomeada pelas vias protegidas: a trigger exige correspondência na mesma transação, e o CHECK exige ator humano para sair do bloqueio ([paper.py:658](C:/dev/project-hunter/infra/migrations/ddl/paper.py:658), [risk.py:93](C:/dev/project-hunter/packages/core/hunter_core/db/models/risk.py:93)). **Nomeação, porém, não prova autorização.**
- O pico só sobe no cálculo; a guarda também impede sua redução e a reescrita da referência conhecida no mesmo dia ([daily.py:159](C:/dev/project-hunter/packages/core/hunter_core/risk/daily.py:159), [paper.py:474](C:/dev/project-hunter/infra/migrations/ddl/paper.py:474), [paper.py:514](C:/dev/project-hunter/infra/migrations/ddl/paper.py:514)).
- **Sobre a pergunta 5:** duas avaliações que passam por `load_locked_state` se serializam. A releitura de `portfolios` sem outro lock não cria, sozinha, uma corrida entre elas. Contudo, o resultado da organização pode ficar desatualizado, pois a avaliação usa `lock=False`; ele não substitui a leitura com locks no momento do efeito de entrada ([kill_switch.py:105](C:/dev/project-hunter/packages/core/hunter_core/risk/kill_switch.py:105), [scopes.py:140](C:/dev/project-hunter/packages/core/hunter_core/risk/scopes.py:140)).

**OBSIDIAN**

- **Risk Engine** — registrar os bloqueadores da T3.6 e os requisitos de evidência para retomada.
- **Portfolio** — distinguir referência de meia-noite, snapshot operacional e agregações da curva.
- **Open Bugs** — registrar os cenários acima com responsáveis e testes de regressão.
- **Revisoes-Astra/Index** — indexar esta revisão adversarial da T3.6.