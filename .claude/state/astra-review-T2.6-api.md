**RESUMO**

Concordo com `org_id` opcional e Postgres como fonte das oportunidades. Não usaria kill switch como avaliação completa de risco nem decomposição como medida de volatilidade. Para nomenclatura, seguiria **`RISK_BLOCKED`**, conforme o contrato vigente. O scanner presente já cabe no endpoint existente.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão como `backend-specialist`, em modo OPINIÃO.

**TESTES**

Não executei testes; conclusões baseadas em leitura do código e dos contratos.

**MUST-FIX**

**1) Organização opcional: concordo, com ajustes.**

- Declare `org_id: UUID | None` explicitamente como query parameter. Quando informado, reutilize `get_org_context(org_id, request, principal)` antes da leitura tenant. A função recebe o UUID diretamente; não acessa `request.path_params`. A dependência atual é obrigatória, mas sua lógica pode ser chamada pelo adaptador opcional. Membership ausente gera 404; convidados e suspensos também ficam excluídos. [rbac.py:125](C:/dev/project-hunter/apps/api/hunter_api/auth/rbac.py:125), [principal.py:139](C:/dev/project-hunter/apps/api/hunter_api/auth/principal.py:139).
- Abra `tenant_session(factory, org_id, principal.user_id)` e mantenha o predicado explícito `organization_id = org_id` no repositório. **É o padrão de `/me`**, que abre transações tenant separadas após obter memberships. [me.py:89](C:/dev/project-hunter/apps/api/hunter_api/routers/me.py:89), [session.py:162](C:/dev/project-hunter/packages/core/hunter_core/db/session.py:162).
- Sem organização, prefiro campos **explicitamente `null`**, com motivo, preservando o status global. Com organização, `in_position=false` exige leitura concluída sem exposição. Eu incluiria `closing` com quantidade positiva: consultar apenas `open` pode esconder posição ainda em fechamento. [execution.py:192](C:/dev/project-hunter/packages/core/hunter_core/db/models/execution.py:192), [enums.py:558](C:/dev/project-hunter/packages/core/hunter_core/domain/enums.py:558).

**Risco exige contrato próprio.** Há estado atual na organização e no portfolio, além de decisões persistidas em propostas; `kill_switch_transitions` é histórico de transições. [identity.py:45](C:/dev/project-hunter/packages/core/hunter_core/db/models/identity.py:45), [portfolios.py:106](C:/dev/project-hunter/packages/core/hunter_core/db/models/portfolios.py:106), [execution.py:96](C:/dev/project-hunter/packages/core/hunter_core/db/models/execution.py:96), [risk.py:59](C:/dev/project-hunter/packages/core/hunter_core/db/models/risk.py:59).

Eu retornaria risco desconhecido quando não houver avaliação aplicável. Kill switch efetivo bloqueante pode comprovar `true`, considerando sistema/org/portfolio; estado liberado **não comprova `false`**, pois existem outros checks. Cenário: kill switch `ACTIVE`, mas limite de exposição excedido — o Radar informaria ausência de bloqueio incorretamente. Também não agregaria “qualquer portfolio bloqueado” como bloqueio da organização inteira. [RISK_ENGINE.md:57](C:/dev/project-hunter/docs/RISK_ENGINE.md:57), [RISK_ENGINE.md:96](C:/dev/project-hunter/docs/RISK_ENGINE.md:96).

**2) Enum: não confirmo `BLOCKED_BY_RISK` como escolha automática.**

Eu escreveria **`RISK_BLOCKED` no contrato derivado da API**, porque a decisão conjunta e o brief vigente usam esse nome. Registraria a divergência em `notes-T2.6.md`; adotar `BLOCKED_BY_RISK` exige reconciliação explícita do contrato, não apenas contar ocorrências. [M2.md:55](C:/dev/project-hunter/docs/plans/M2.md:55), [brief-T2.6:9](C:/dev/project-hunter/.claude/state/brief-T2.6-radar-api.md:9).

A evidência citada do frontend é comentário de vocabulário e label de showcase, não um consumidor tipado desse enum da API. [badge.tsx:6](C:/dev/project-hunter/apps/web/components/ui/badge.tsx:6), [badges-showcase.tsx:9](C:/dev/project-hunter/apps/web/components/design/badges-showcase.tsx:9).

Mantenha ambos os estados derivados **fora de `OpportunityStatus` persistido**. Cenário: acrescentá-los ao status global faz uma organização receber o estado de outra. [enums.py:268](C:/dev/project-hunter/packages/core/hunter_core/domain/enums.py:268).

**3) Postgres: concordo para oportunidades, com três correções.**

**Volatilidade:** não existe componente “Volatility” na composição especificada. Usá-lo produziria filtro sem fonte definida. Recomendo uma faixa explicitamente denominada **`atr_14_pct`**, disponível na calculadora como ATR Wilder(14) de barras de 15 minutos dividido pelo fechamento, em fração. Se o produto quer desvio de retornos em 1 h, isso é outra medida e deve ser contratado como `volatility_1h`. [PIPELINE.md:104](C:/dev/project-hunter/docs/PIPELINE.md:104), [trend.py:69](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/trend.py:69), [PIPELINE.md:68](C:/dev/project-hunter/docs/PIPELINE.md:68).

Leia a feature do **envelope da oportunidade**, com qualidade/disponibilidade; congele o caminho JSON com o produtor. Aceito extração JSONB com cast numérico e sem índice dedicado inicialmente; ausente não vira zero. O modelo reserva esse envelope, mas não define sozinho sua estrutura interna completa. [analysis.py:241](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:241).

**Paginação:** ordene por `(valor, id)`, defina nulos e vincule cursor aos filtros/ordenação/org. Isso resolve empates, mas **não congela dados mutáveis**: score 90 já visto que cai para 70 pode reaparecer após cursor 80. Um `as_of` sozinho não recupera valores anteriores da projeção atual. Documente paginação sobre dados vivos ou implemente snapshot se “estável” exigir ausência de repetição/omissão entre requisições. [analysis.py:204](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:204), [analysis.py:250](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:250).

Se `status` aceitar estados derivados, filtre **antes do `LIMIT`**; enriquecer apenas os IDs da página não resolve esse filtro. Cenário: primeira página global sem posições, mas segunda com posições — filtrar depois retorna uma página vazia indevida. O brief exige filtro no servidor. [brief-T2.6:9](C:/dev/project-hunter/.claude/state/brief-T2.6-radar-api.md:9).

**Cobertura:** existe divergência adicional: o diálogo fechado prevê NORMAL sem episódio via projeção transitória. Uma leitura exclusivamente de `opportunities` não cobre isso. Registre a reconciliação; não declare cobertura integral desse aceite apenas com Postgres. [Diálogo M2:258](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/M2.md:258).

**4) Scanner: concordo para heartbeat presente; ausência ainda precisa tratamento.**

Não vejo mudança necessária em `routers/system.py` para retornar `hb:scanner:*`: o handler delega ao scan genérico. Acrescente teste HTTP com hash válido e `ts`, não somente teste do parser. [system.py:64](C:/dev/project-hunter/apps/api/hunter_api/routers/system.py:64), [system_status.py:216](C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:216).

Porém, scanner ausente **simplesmente não aparece**. A tabela atual percorre os workers retornados; não cria “scanner — sem verificação”. Cenário: market presente e scanner ausente deixa o scanner invisível, contrariando essa parte do brief. Eu resolveria a apresentação em T2.7, sem fabricar heartbeat nem alterar o router apenas para cadastrar um role. [workers-table.tsx:50](C:/dev/project-hunter/apps/web/components/system/workers-table.tsx:50), [brief-T2.6:11](C:/dev/project-hunter/.claude/state/brief-T2.6-radar-api.md:11).

**NICE-TO-HAVE**

Adiar índice JSONB até medir o plano da consulta. Nos testes, cobrir membership suspensa, posição `closing`, múltiplos portfolios e heartbeat ausente versus Redis indisponível.

**O QUE EU FARIA DIFERENTE**

Fecharia em `notes-T2.6.md` a semântica de risco, a medida de volatilidade, a garantia de paginação e as duas divergências documentais antes de congelar os schemas.

**CONCORDO COM**

Organização opcional com validação; transação tenant separada; nulos honestos; Postgres para filtros; `EXISTS` para evitar multiplicar oportunidades; teste de contrato do scanner.

**OBSIDIAN**

- **System Overview** — contexto organizacional opcional e isolamento da leitura derivada.
- **Data Flow** — fontes do Radar, cobertura de NORMAL e limites da paginação.
- **Features** — medida e unidade escolhidas para o filtro de volatilidade.
- **Risk Engine** — diferença entre kill switch bloqueante e avaliação completa de risco.
- **Workers** — descoberta genérica e apresentação de scanner sem heartbeat.
- **Dialogos/M2** — reconciliar nomenclatura e projeção transitória com o brief T2.6.