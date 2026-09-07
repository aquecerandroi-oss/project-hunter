**RESUMO**

**REQUEST_CHANGES.** Concordo com as cinco decisões centrais. Não identifiquei vazamento de tenant nem bypass de RBAC nas rotas revisadas, mas corrigiria três problemas antes de aprovar: seleção ambígua de workspace, datas sem timezone e sinalização incorreta de preços indisponíveis.

**ARQUIVOS**

Revisei os sete arquivos novos indicados e o registro dos routers em `app.py`. Não alterei arquivos nem fiz commit.

Ressalva de escopo: neste workspace, `routers/risk.py` aparece como não rastreado, e o diff de `app.py` também registra esse router. A revisão considera o conteúdo disponível, sem certificar a premissa de T3.6 integralmente commitada.

**TESTES**

Não executei pytest, lint ou typecheck nesta revisão somente de leitura. Os cenários abaixo foram identificados por inspeção; não apresento resultados de execução.

**MUST-FIX**

1. **HIGH — abertura permanente pode escolher o workspace errado.** Em [open_paper_wallet.py:139](/C:/dev/project-hunter/infra/scripts/open_paper_wallet.py:139), a resolução usa nome e `session.scalar()`, aceitando a primeira correspondência. O modelo permite nomes repetidos: [identity.py:101](/C:/dev/project-hunter/packages/core/hunter_core/db/models/identity.py:101).

   **Cenário:** dois workspaces ativos da mesma organização chamados `principal`. O comando abre a carteira em um deles sem detectar ambiguidade; a recusa posterior por organização impede repetir a operação no outro. Como a abertura é permanente, exigir UUID ou recusar múltiplas correspondências é necessário.

2. **MEDIUM — datas sem timezone chegam ao banco em vez de gerar erro de validação.** O router aceita `datetime` comum em [portfolio.py:139](/C:/dev/project-hunter/apps/api/hunter_api/routers/portfolio.py:139), e o serviço passa esses valores diretamente aos filtros em [portfolio_lists.py:94](/C:/dev/project-hunter/apps/api/hunter_api/services/portfolio_lists.py:94).

   **Cenário:** `?from=2026-09-06T00:00:00` passa pela validação como datetime ingênuo e chega à comparação com `timestamptz` via asyncpg, podendo resultar em erro de bind/500. Exigir timezone na entrada e normalizar para UTC; entrada inválida deve retornar 422.

3. **MEDIUM — ausência de referência diária vira falsa ausência de preços.** [portfolio_queries.py:258](/C:/dev/project-hunter/apps/api/hunter_api/services/portfolio_queries.py:258) define `marks_complete=False` sempre que `build.state is None`. Entretanto, o builder retorna `None` por referência diária ausente ou de outro dia, independentemente das marcas: [state.py:174](/C:/dev/project-hunter/packages/core/hunter_core/portfolio/state.py:174).

   **Cenário:** carteira inteiramente em caixa, após a meia-noite de São Paulo, antes da nova referência. Não existe preço faltante, mas a API declara marcas incompletas. Derivar esse campo das lacunas de marcas/identidade, separadamente de `daily_reference`.

**NICE-TO-HAVE**

- Remover a dependência de ordem do teste de FX vencido, explicitamente reconhecida em [test_portfolio_api.py:113](/C:/dev/project-hunter/apps/api/tests/integration/test_portfolio_api.py:113). Executar primeiro um teste que insere FX fresco faz o cenário consumir outra observação. Controlar relógio e corte temporal torna a prova independente.
- Acrescentar testes com VIEWER, membership suspensa, paginação populada e mudança de câmbio entre abertura e leitura. Os testes atuais verificam listas vazias e somente o ponto inicial da curva: [test_portfolio_api.py:243](/C:/dev/project-hunter/apps/api/tests/integration/test_portfolio_api.py:243).

**O QUE EU FARIA DIFERENTE**

Explicitaria que o resumo ainda não consulta preços atuais: ele passa `marks={}` em [portfolio_queries.py:209](/C:/dev/project-hunter/apps/api/hunter_api/services/portfolio_queries.py:209). Havendo posições, o ledger usa marca persistida ou preço de entrada e sinaliza atraso: [ledger.py:98](/C:/dev/project-hunter/packages/core/hunter_core/portfolio/ledger.py:98). O câmbio pode estar fresco enquanto o patrimônio está degradado; essa diferença precisa permanecer visível ao consumidor.

**CONCORDO COM**

1. **Prefixo por organização:** correto conforme `ARCHITECTURE.md:268`. O router declara esse prefixo e VIEWER em [portfolio.py:55](/C:/dev/project-hunter/apps/api/hunter_api/routers/portfolio.py:55).

2. **VIEWER nas leituras:** coerente com `SECURITY.md:30`. A sessão depende da membership e recebe contexto do tenant: [deps.py:87](/C:/dev/project-hunter/apps/api/hunter_api/deps.py:87). A checagem de propriedade combina organização e carteira: [portfolio.py:81](/C:/dev/project-hunter/apps/api/hunter_api/routers/portfolio.py:81).

3. **FX atual global:** não contradiz a doutrina histórica. O resumo busca e valida FX disponível no corte: [portfolio_queries.py:136](/C:/dev/project-hunter/apps/api/hunter_api/services/portfolio_queries.py:136). A curva usa exclusivamente o `fx_observation_id` do ponto: [portfolio_lists.py:117](/C:/dev/project-hunter/apps/api/hunter_api/services/portfolio_lists.py:117). Uma observação nova não reprecifica o passado.

4. **Listas reais:** correto; posições, ordens e trades têm filtros explícitos por organização/carteira e paginação, respectivamente em [portfolio_lists.py:161](/C:/dev/project-hunter/apps/api/hunter_api/services/portfolio_lists.py:161), [202](/C:/dev/project-hunter/apps/api/hunter_api/services/portfolio_lists.py:202) e [244](/C:/dev/project-hunter/apps/api/hunter_api/services/portfolio_lists.py:244). Isso não comprova que o banco operacional esteja vazio.

5. **Reservas independentes da referência diária:** correto. A soma em [portfolio_queries.py:218](/C:/dev/project-hunter/apps/api/hunter_api/services/portfolio_queries.py:218) usa reservas `held`, sem liberá-las implicitamente pelo relógio: [ledger.py:139](/C:/dev/project-hunter/packages/core/hunter_core/db/repositories/ledger.py:139).

**OBSIDIAN**

- **Portfolio** — registrar o contrato de leitura, FX atual versus histórico e disponibilidade independente de preços/referência diária.
- **Revisões Astra / T3.8a** — registrar os três achados, os cenários e a ausência de execução de testes.
- **System Overview** — atualizar a API da carteira após correção e validação, preservando a distinção entre implementação e entrega.