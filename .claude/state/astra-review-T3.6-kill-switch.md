**RESUMO**

Parecer como `risk-engine-guardian`: o desenho pode avançar com os ajustes abaixo. O achado principal é que **a trigger atual não garante “transição escrita na mesma transação”** — apenas existência de uma correspondência no histórico. [paper.py:492](C:/dev/project-hunter/infra/migrations/ddl/paper.py:492)

**ARQUIVOS**

Nenhum criado ou modificado. Nenhum `.env` lido; nenhum commit.

**TESTES**

Não executados: análise estática e consulta à documentação oficial de PostgreSQL/SQLAlchemy. Os cenários abaixo são deduções do código, não reproduções executadas.

**MUST-FIX**

**1. ESCOPOS — falta a linha durável global, mas existe configuração de sistema.**

Confirmo a ausência de uma linha dedicada ao **estado atual global** no schema consultado. Há três peças distintas:

- `Settings.system_kill_switch`, com padrão `ACTIVE`; `get_settings()` é cacheado por processo. Portanto, **não fixe `system=ACTIVE` ignorando essa configuração**. [settings.py:125](C:/dev/project-hunter/packages/core/hunter_core/settings.py:125), [settings.py:234](C:/dev/project-hunter/packages/core/hunter_core/settings.py:234)
- Histórico persistível com `scope='system'` em `kill_switch_transitions`; isso não fornece, sozinho, uma linha global para disputar lock. [risk.py:70](C:/dev/project-hunter/packages/core/hunter_core/db/models/risk.py:70)
- `system_events` registra eventos operacionais, sem contrato de autoridade para o kill switch. [system.py:50](C:/dev/project-hunter/packages/core/hunter_core/db/models/system.py:50)

**Recomendação:** compor configuração de sistema + organização + portfolio, declarando que **a persistência global mutável e sua sincronização transacional continuam pendentes**. Isso permite implementar a parte da T3.6 disponível, mas não declarar cumprida a garantia integral dos três escopos exigida pelo contrato. [RISK_ENGINE.md:357](C:/dev/project-hunter/docs/RISK_ENGINE.md:357)

**Cenário de falha:** configuração `EMERGENCY`, organização e carteira `ACTIVE`; substituir sistema por `ACTIVE` libera entradas que deveriam estar bloqueadas.

**2. TRANSIÇÃO AUDITADA — duas etapas distintas funcionam; reutilizar histórico é o furo real.**

`ACTIVE→WARNING→TRADING_DISABLED`, com duas atualizações e duas transições correspondentes, **não confunde os pares**: cada disparo usa seu `OLD`/`NEW`; o predicado compara ambos. O adiamento muda quando ocorre a verificação, não transforma todas as atualizações numa única mudança inicial→final. [paper.py:494](C:/dev/project-hunter/infra/migrations/ddl/paper.py:494), [paper.py:512](C:/dev/project-hunter/infra/migrations/ddl/paper.py:512), [PostgreSQL — CREATE TRIGGER](https://www.postgresql.org/docs/16/sql-createtrigger.html)

Porém, o `EXISTS` **não filtra identidade da transação nem identifica uma ocorrência específica**. Uma transição histórica serve novamente; repetir o mesmo par dentro da mesma transação também não exige duas linhas pelo mecanismo atual. [paper.py:492](C:/dev/project-hunter/infra/migrations/ddl/paper.py:492)

**Cenário crítico:** houve uma retomada autorizada `TRADING_DISABLED→ACTIVE`; depois a carteira bloqueia novamente. Um novo `UPDATE ... ACTIVE`, sem nova transição, encontra a autorização histórica e satisfaz a trigger. O teste existente termina na primeira retomada válida, sem exercitar esse segundo ciclo. [test_schema_paper.py:1242](C:/dev/project-hunter/packages/core/tests/integration/test_schema_paper.py:1242)

Sem alterar migrações, recomendo um único caminho de escrita:

`locks → releitura → cálculo → INSERT transition + flush → UPDATE condicionado ao estado lido → outbox`

Se o `UPDATE` não afetar exatamente uma carteira, **rollback integral**, incluindo a transição. Seu `UPDATE→INSERT` também funciona enquanto a constraint permanecer adiada; prefiro inserir primeiro para funcionar igualmente caso o chamador tenha tornado a constraint imediata.

Cada mudança real recebe uma linha nova; estado inalterado não gera transição. Não deduplicar por `(portfolio, from_state, to_state)`, pois esse par pode reaparecer legitimamente.

**Limite explícito:** isso protege o caminho da aplicação; **não corrige a garantia no banco contra escritores que o contornem**. Registrar o defeito da migração para correção separada.

**3. VIRADA DO DIA — pico preservado; referência desconhecida não vira bloqueio permanente.**

Sim: com pico `100` e equity `96`, drawdown continua em `4%` depois da virada. Para eliminar esse gatilho, precisa cair **estritamente abaixo de 4%**; recuperar durante o dia não autoriza saída automática imediata — ela espera a próxima virada elegível. Além disso, **AVISO manual não sai automaticamente**. Essa regra está explícita no plano; o contrato define pico monotônico e os limiares. [M3.md:142](C:/dev/project-hunter/docs/plans/M3.md:142), [RISK_ENGINE.md:296](C:/dev/project-hunter/docs/RISK_ENGINE.md:296), [kill_switch.py:102](C:/dev/project-hunter/packages/risk-core/hunter_risk/kill_switch.py:102)

Há uma correção na proposta de referência: **equity atual só serve se representar legitimamente a referência da virada**. Detectar o novo dia após restart não permite substituir a abertura pelo primeiro equity encontrado. Registrar `day_reference_observed_at=now` torna o atraso visível, mas não transforma aquele patrimônio em patrimônio da meia-noite. [RISK_ENGINE.md:285](C:/dev/project-hunter/docs/RISK_ENGINE.md:285), [paper_wallet.py:167](C:/dev/project-hunter/packages/core/hunter_core/db/models/paper_wallet.py:167)

**Cenário:** abertura `100`, restart às 03:17 UTC com equity `97,5`; gravar `97,5` como abertura apaga uma perda diária de `2,5%`.

Se `equity_day_start IS NULL`: **preservar o kill switch persistido, bloquear entradas por insumo `unavailable`, registrar o motivo e preservar saídas**. Não criar `TRADING_DISABLED` apenas pela referência ausente; isso converteria indisponibilidade recuperável em bloqueio que exige retomada manual. O schema representa essa ausência expressamente. [paper_wallet.py:116](C:/dev/project-hunter/packages/core/hunter_core/db/models/paper_wallet.py:116), [RISK_ENGINE.md:320](C:/dev/project-hunter/docs/RISK_ENGINE.md:320)

Também não inventar `PortfolioState` para chamar `assess`: na recuperação, saídas têm caminho independente desse estado. [RISK_ENGINE.md:334](C:/dev/project-hunter/docs/RISK_ENGINE.md:334)

**4. CONCORRÊNCIA — sim para a mesma carteira, com condições.**

Em **READ COMMITTED**, um **novo statement** que lê `portfolios` depois de adquirir o lock enxerga o commit da primeira sessão. Portanto, duas avaliações que pedem a mesma mudança produzem uma transição se a segunda reler e reconhecer que não há mudança. A linha escolhida é justamente a trava prevista pelo modelo. [paper_wallet.py:141](C:/dev/project-hunter/packages/core/hunter_core/db/models/paper_wallet.py:141), [PostgreSQL — Read Committed](https://www.postgresql.org/docs/16/transaction-iso.html#XACT-READ-COMMITTED)

Os furos a fechar são:

- **Cache ORM:** não confiar em `session.get()` ou entidade já carregada. Buscar colunas escalares ou usar `populate_existing=True` na releitura, inclusive do estado de risco. A fábrica mantém `expire_on_commit=False`. Cenário: segunda sessão conserva `ACTIVE` em memória e repete a transição apesar do banco atualizado. [session.py:91](C:/dev/project-hunter/packages/core/hunter_core/db/session.py:91), [SQLAlchemy — Refreshing](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#expiring-refreshing)
- **Linha ausente:** `FOR UPDATE` sem resultado não trava a carteira. Exigir a linha existente e recusar processamento se faltar; não continuar com defaults. A PK garante unicidade, não existência para toda carteira. [paper_wallet.py:141](C:/dev/project-hunter/packages/core/hunter_core/db/models/paper_wallet.py:141)
- **Escopos superiores:** esse lock sozinho não impede uma organização de bloquear entre a leitura e o fill. Todos os escritores relevantes precisam compartilhar o protocolo, na ordem **sistema→organização→portfolio**, mantendo as travas até o efeito. Esse cenário consta expressamente do contrato. [RISK_ENGINE.md:357](C:/dev/project-hunter/docs/RISK_ENGINE.md:357)

**NICE-TO-HAVE**

Nenhum adicional; priorizaria transformar os cenários acima em testes de integração.

**O QUE EU FARIA DIFERENTE**

Separaria estado local persistido de estado efetivo: `assessment.automatic` alimenta a escalada local; `assessment.effective` governa entradas. Copiar indiscriminadamente `effective` para a carteira pode perpetuar nela um bloqueio herdado da organização. O núcleo entrega os dois valores separadamente. [kill_switch.py:118](C:/dev/project-hunter/packages/risk-core/hunter_risk/kill_switch.py:118)

**CONCORDO COM**

Usar `portfolio_risk_state` como trava comum, preservar o pico e concentrar mudança de estado, auditoria e outbox na mesma transação corresponde à decisão conjunta. [M3.md:140](C:/dev/project-hunter/docs/plans/M3.md:140)

**OBSIDIAN**

- **Risk Engine** — distinguir configuração global de estado durável; registrar o furo de reutilização histórica na trigger.
- **Portfolio** — documentar referência diária desconhecida e releitura sob lock sem cache ORM obsoleto.
- **Open Bugs** — registrar o segundo desbloqueio sem nova autorização que a trigger permite.
- **Revisões da Astra / T3.6** — guardar este parecer e os cenários de aceitação; nenhuma página alterada neste modo.