**RESUMO**

**REQUEST_CHANGES.** Li todos os arquivos indicados, como `code-reviewer`, aplicando também os critérios de risco e segurança.

A dedupe é incompleta; a espera ainda pode conservar um book vencido; e a admissão continua sem persistir o bloqueio automático que detecta. Os privilégios são um bloqueio de integração adicional. **Não recomendo reproduzir as regras do motor em `admission.inputs`: recomendo reutilizá-las no núcleo puro.**

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Não executei testes, migrações ou linters nesta revisão. Os resultados verdes informados são contexto fornecido por você, não execução minha.

Li as suítes integralmente. Duas limitações relevantes:

- O teste de participação concorrente exige apenas uma aprovação e soma abaixo do teto; pode continuar verde se a participação acumulada for ignorada, porque a posição pendente duplicada já barra a segunda proposta. É a armadilha de motivo errado do §12.9. [test_admission_concurrency.py:157](C:/dev/project-hunter/packages/core/tests/integration/test_admission_concurrency.py:157)
- O teste chamado “fill consumes … without returning the budget” não grava execução nem consulta o orçamento final. Com as linhas que ele cria, o cálculo passa a contar zero depois de `consumed`. Ele prova a transição e a ausência de `released`, não a preservação do consumo executado. [test_admission_reservation.py:234](C:/dev/project-hunter/packages/core/tests/integration/test_admission_reservation.py:234), [participation.py:76](C:/dev/project-hunter/packages/core/hunter_core/admission/participation.py:76)

**MUST-FIX**

1. **HIGH — dedupe aceita outra instrução econômica como replay.**

   Compara somente carteira, mercado, direção e origem. **Cenário:** primeira solicitação aprovada com teto de 1.000; cliente reutiliza a chave com teto de 100 e stop diferente. Recebe a aprovação anterior, potencialmente maior que o novo teto, sem conflito. Não duplica reserva, mas responde a uma solicitação diferente como se fosse repetição. [dedupe.py:108](C:/dev/project-hunter/packages/core/hunter_core/admission/dedupe.py:108), [service.py:161](C:/dev/project-hunter/packages/core/hunter_core/admission/service.py:161)

   Persista uma identidade canônica versionada da solicitação, incluindo preços, tetos, custos e identidade de agente/sinal. Compare-a nos três caminhos de replay. Dados de mercado obtidos novamente não devem alterar essa identidade.

   **A ausência de colunas não justifica ignorar os campos:** `entry_ref` e `stop` já existem em `risk_decision.sizing` quando há sizing. Isso permite uma correção parcial, mas não cobre recusas sem sizing nem todos os demais campos. [decision.py:115](C:/dev/project-hunter/packages/risk-core/hunter_risk/decision.py:115)

2. **HIGH — `_lock_wait_s` ainda permite usar livro vencido.**

   **Cenário:** book com 9,8 s no instante recebido; espera de 0,4 s pela trava. O ajuste vira zero, e o motor avalia 9,8 s quando o livro já tem 10,2 s, acima do limite de 10 s. [service.py:119](C:/dev/project-hunter/packages/core/hunter_core/admission/service.py:119), [service.py:169](C:/dev/project-hunter/packages/core/hunter_core/admission/service.py:169), [checks.py:264](C:/dev/project-hunter/packages/risk-core/hunter_risk/checks.py:264)

   Preserve a duração completa, usando relógio injetável e medição monotônica do tempo decorrido. Inclua também o tempo gasto antes da trava desde o instante-base declarado. Truncar para manter testes reproduzíveis não resolve os dois requisitos; a injeção de relógio resolve. O relógio de parede no código sob teste também contraria expressamente o §12.2. [spec-T3.9-verificacoes.md:650](C:/dev/project-hunter/.claude/state/spec-T3.9-verificacoes.md:650)

3. **HIGH — bloqueio automático detectado não vira trava durável.**

   O serviço declara explicitamente que deixa a transição para o loop e chama apenas a avaliação pura. **Cenário:** admissão observa perda diária de 2%, rejeita e commita; patrimônio recupera antes do próximo ciclo; outra admissão encontra a trava ainda `ACTIVE` e pode aprovar sem retomada autorizada. O contrato exige que esse check acione a transição. [service.py:16](C:/dev/project-hunter/packages/core/hunter_core/admission/service.py:16), [service.py:204](C:/dev/project-hunter/packages/core/hunter_core/admission/service.py:204), [RISK_ENGINE.md:117](C:/dev/project-hunter/docs/RISK_ENGINE.md:117)

   Integre a persistência da escalada automática à mesma transação. Não copie indiscriminadamente o estado efetivo da organização para a carteira; a implementação durável existente distingue essas causas. [kill_switch.py:232](C:/dev/project-hunter/packages/core/hunter_core/risk/kill_switch.py:232)

4. **HIGH — bloqueio de integração: a entrega ainda depende de privilégios externos às migrações.**

   O fixture concede ao worker a permissão pendente; o serviço incrementa uma coluna que `hunter_app` não pode atualizar; o adaptador registra também o impedimento da outbox. **Cenário:** banco provisionado somente pelas migrações não reproduz o caminho verde do worker; a chamada manual com `hunter_app` aborta no contador, como o próprio teste espera. [admission_fixtures.py:134](C:/dev/project-hunter/packages/core/tests/integration/admission_fixtures.py:134), [record.py:163](C:/dev/project-hunter/packages/core/hunter_core/admission/record.py:163), [test_admission_concurrency.py:212](C:/dev/project-hunter/packages/core/tests/integration/test_admission_concurrency.py:212), [admission.py:22](C:/dev/project-hunter/apps/api/hunter_api/services/admission.py:22)

   Isso precisa ser resolvido antes do aceite integrado T3.12/T3.8. Trocar a transação da API para `hunter_worker` elimina a barreira de RLS exigida para ela; não é uma correção equivalente. [DATABASE.md:38](C:/dev/project-hunter/docs/DATABASE.md:38)

5. **MEDIUM — `ProposalRequest` permite conversão silenciosa de float monetário.**

   Herda diretamente de `BaseModel`, sem a validação anterior à conversão existente em `RiskModel`. **Cenário:** `entry_ref=0.1 + 0.2` entra como float, é convertido para Decimal e chega ao núcleo já convertido; a proteção do núcleo não detecta sua origem. O mesmo vale para stop e tetos. [sources.py:74](C:/dev/project-hunter/packages/core/hunter_core/admission/sources.py:74), [sources.py:97](C:/dev/project-hunter/packages/core/hunter_core/admission/sources.py:97), [base.py:33](C:/dev/project-hunter/packages/risk-core/hunter_risk/base.py:33)

   Recuse float na fronteira antes da coerção e teste os campos monetários.

6. **MEDIUM — fallback perde reprovações que continuam avaliáveis.**

   **Cenário:** referência diária ausente e proposta SHORT, ou mercado explicitamente degradado. Ambos aparecem como `unavailable` por falta de estado da carteira, embora a modalidade e a degradação sejam conhecidas. A rejeição permanece segura, mas a explicação viola o contrato. [inputs.py:109](C:/dev/project-hunter/packages/core/hunter_core/admission/inputs.py:109), [checks.py:79](C:/dev/project-hunter/packages/risk-core/hunter_risk/checks.py:79), [RISK_ENGINE.md:90](C:/dev/project-hunter/docs/RISK_ENGINE.md:90)

   **Concordo com sua objeção à duplicação.** Extraia/reutilize checks independentes dentro de `hunter_risk`, compartilhados pelo caminho completo e pelo parcial. Não invente `PortfolioState` nem mantenha uma segunda implementação em `hunter_core`.

7. **MEDIUM — carteira não aberta pode escapar da tradução para 409.**

   O lock é adquirido antes de `build_portfolio_state`. Sem linha de risco, `effective_state` lança `RiskStateMissing`; o adaptador captura apenas `WalletNotOpen`. **Cenário:** carteira existente ainda sem abertura produz exceção não traduzida em vez do 409 prometido. O teste atual injeta diretamente a exceção que o adaptador sabe capturar. [service.py:168](C:/dev/project-hunter/packages/core/hunter_core/admission/service.py:168), [scopes.py:96](C:/dev/project-hunter/packages/core/hunter_core/risk/scopes.py:96), [admission.py:179](C:/dev/project-hunter/apps/api/hunter_api/services/admission.py:179)

   Diferencie carteira invisível/inexistente de carteira visível não aberta antes de mapear a resposta.

**NICE-TO-HAVE**

- Fortalecer os testes citados com consumo executado real e asserções sobre o check específico; no teste da organização, produzir sobreposição real entre transações. Atualmente ele termina o bloqueio antes de iniciar a admissão. [test_admission_concurrency.py:148](C:/dev/project-hunter/packages/core/tests/integration/test_admission_concurrency.py:148)
- Preservar no replay os motivos de `AdmissionResult.unavailable`; hoje o resultado original os preenche, mas `_replay` deixa o padrão vazio. [service.py:99](C:/dev/project-hunter/packages/core/hunter_core/admission/service.py:99), [service.py:292](C:/dev/project-hunter/packages/core/hunter_core/admission/service.py:292)

**O QUE EU FARIA DIFERENTE**

**Sobre o GRANT pendente:** aceito como experimento explicitamente condicionado: “o serviço funciona sob estes privilégios adicionais”. Não aceito como prova de integração com o schema entregue. O rótulo evita esconder a hipótese; não torna a hipótese verdadeira em produção.

Prefiro corrigir a migração, testar os privilégios positivos e negativos e remover o GRANT do fixture compartilhado. Enquanto isso não ocorrer, mantenha uma prova separada do bloqueio no schema intacto. O §12 não menciona GRANT especificamente, mas seu princípio é impedir que o teste passe por uma proteção ou condição que a entrega não possui. [spec-T3.9-verificacoes.md:641](C:/dev/project-hunter/.claude/state/spec-T3.9-verificacoes.md:641)

**CONCORDO COM**

- Expiração preservar `approved`, encerrar a reserva e liberar apenas o saldo não executado. [reservation.py:193](C:/dev/project-hunter/packages/core/hunter_core/admission/reservation.py:193), [reservation.py:251](C:/dev/project-hunter/packages/core/hunter_core/admission/reservation.py:251)
- FIFO também para recusadas, com reserva condicionada à aprovação. [service.py:251](C:/dev/project-hunter/packages/core/hunter_core/admission/service.py:251)
- A álgebra de participação: executado na janela mais saldo não negativo por reserva held, usando seu histórico inteiro. [participation.py:68](C:/dev/project-hunter/packages/core/hunter_core/admission/participation.py:68)

Quanto a **tenant/RLS e atomicidade**, não identifiquei um caminho confirmado que commite decisão e reserva separadamente quando o chamador mantém a transação e propaga falhas. Dedupe verifica o contexto do tenant; as escritas usam organização explícita; auditoria e outbox usam a mesma sessão. Isso não equivale a uma prova dinâmica de isolamento. [dedupe.py:99](C:/dev/project-hunter/packages/core/hunter_core/admission/dedupe.py:99), [record.py:113](C:/dev/project-hunter/packages/core/hunter_core/admission/record.py:113), [record.py:278](C:/dev/project-hunter/packages/core/hunter_core/admission/record.py:278)

UTC é normalizado na entrada; o problema temporal encontrado é a idade efetiva, não o fuso. [service.py:156](C:/dev/project-hunter/packages/core/hunter_core/admission/service.py:156)

**OBSIDIAN**

- **Risk Engine** — registrar escalada durável na admissão, avaliação parcial compartilhada e relógio injetável.
- **Portfolio** — documentar os privilégios necessários ao contador e o bloqueio atual da via manual.
- **Execution Engine** — registrar dedupe por conteúdo e provas do ciclo reserva → execução → liberação.
- **Revisoes-Astra/Index** — vincular este parecer e separar aceite condicionado de integração com migrações reais.