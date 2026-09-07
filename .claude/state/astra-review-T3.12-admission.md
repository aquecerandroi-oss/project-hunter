**RESUMO**

Concordo com o contador durável, a fórmula de participação e a transação única. Manteria `status=approved` na expiração, atribuiria FIFO também às recusadas e persistiria a recusa por estado inconstruível — mas não marcaria indiscriminadamente todos os checks como `unavailable`.

Há **dois bloqueios de privilégios** para a admissão pela API: o UPDATE do contador e o INSERT na outbox. Parecer como `risk-engine-guardian`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Não executei testes nem migrações. As conclusões abaixo vêm da leitura do working tree; os testes existentes citados não foram executados nesta análise.

**MUST-FIX**

**1. Papel/trigger: concordo com a exceção restrita para o contador.**

O bloqueio está efetivamente em [paper.py:448](C:/dev/project-hunter/infra/migrations/ddl/paper.py:448). Ele conflita com a admissão manual compartilhada exigida em [M3.md:65](C:/dev/project-hunter/docs/plans/M3.md:65).

Recomendo permitir a `hunter_app` alterar **somente o contador**, preservando todas as proteções de identidade, referência diária e pico. A monotonicidade atual apenas impede diminuição; o serviço deve fazer exatamente `n → n+1` por proposta nova, sob a trava ([paper.py:479](C:/dev/project-hunter/infra/migrations/ddl/paper.py:479)).

Cuidado mecânico: `PortfolioRiskState` usa `TimestampMixin`, cujo `updated_at` recebe `onupdate=func.now()`. Uma comparação de todas as colunas exceto `last_admission_seq` pode bloquear o UPDATE gerado pelo ORM. Combinem explicitamente o tratamento desse timestamp técnico ([paper_wallet.py:106](C:/dev/project-hunter/packages/core/hunter_core/db/models/paper_wallet.py:106), [base.py:52](C:/dev/project-hunter/packages/core/hunter_core/db/base.py:52)).

**Cenário:** proposta manual aprovada é inserida, o incremento encontra a trigger e toda a transação aborta. Implemente o incremento contratual e reporte o acoplamento como bloqueante para integração T3.1b/T3.8. `max(admission_seq)` não cumpre o contrato do contador de linha; trocar a rota para worker elimina a segunda barreira de isolamento ([DATABASE.md:1905](C:/dev/project-hunter/docs/DATABASE.md:1905), [DATABASE.md:38](C:/dev/project-hunter/docs/DATABASE.md:38)).

**2. Há outro bloqueio: a outbox.**

`hunter_app` recebe somente SELECT em `outbox_events`; INSERT e uso da sequência ficam com `hunter_worker` ([analysis.py:59](C:/dev/project-hunter/infra/migrations/ddl/analysis.py:59), [analysis.py:326](C:/dev/project-hunter/infra/migrations/ddl/analysis.py:326)).

**Cenário:** corrigido o contador, a admissão chega ao `enqueue` e aborta por falta de privilégio. Existe inclusive um teste que espera essa recusa ([test_risk_kill_switch.py:674](C:/dev/project-hunter/packages/core/tests/integration/test_risk_kill_switch.py:674)).

Registre também esse acoplamento. É necessário definir uma capacidade de enfileiramento autorizada para a API, com revisão de segurança; não deslocar a publicação para uma segunda transação nem executar toda a rota como worker.

**3. Estado inconstruível: persistir a recusa, preservando os fatos avaliáveis.**

`build_portfolio_state` devolve `None` quando a referência diária falta ou pertence a outro dia ([state.py:174](C:/dev/project-hunter/packages/core/hunter_core/portfolio/state.py:174)). Isso merece proposta recusada com motivo, sem sizing nem reserva.

Discordo apenas de **TODOS indisponíveis**. O contrato exige registrar todos os checks avaliáveis, mesmo depois de reprovar ([RISK_ENGINE.md:90](C:/dev/project-hunter/docs/RISK_ENGINE.md:90)).

**Cenário:** referência diária ausente, kill switch durável em `TRADING_DISABLED` e proposta de modalidade proibida. O fallback uniforme registra ambos como desconhecidos e o painel perde duas reprovações conhecidas.

Preserve `ENTRY_CHECKS` e sua ordem; avalie o que os insumos disponíveis permitem, marcando o restante com o motivo da dependência ausente. Não invente um `PortfolioState` para conseguir chamar `evaluate`. Preencha também `effective_kill_switch`, `cancel_pending` e `shadow_only` coerentemente — são campos obrigatórios da decisão ([decision.py:161](C:/dev/project-hunter/packages/risk-core/hunter_risk/decision.py:161)). Erro de banco, tenant incorreto ou carteira nunca aberta continuam sendo erros, não indisponibilidade de referência ([state.py:120](C:/dev/project-hunter/packages/core/hunter_core/portfolio/state.py:120)).

**4. Na transação, falta explicitar a persistência de um bloqueio automático detectado.**

`evaluate` calcula o assessment e devolve a decisão; é puro. O contrato diz que reprovação por perda diária/drawdown também aciona a transição durável ([evaluate.py:143](C:/dev/project-hunter/packages/risk-core/hunter_risk/evaluate.py:143), [RISK_ENGINE.md:117](C:/dev/project-hunter/docs/RISK_ENGINE.md:117)).

**Cenário:** admissão observa perda de 2%, rejeita, mas não persiste o latch; o patrimônio recupera antes do próximo ciclo do worker e nenhuma transição bloqueada fica registrada.

Fechem esse acoplamento com T3.6/T3.5. Não basta gravar `effective_kill_switch` no JSON. Também não encaixaria cegamente `evaluate_and_persist`: ele pode escrever referência e pico, justamente campos proibidos à API ([kill_switch.py:113](C:/dev/project-hunter/packages/core/hunter_core/risk/kill_switch.py:113)).

**NICE-TO-HAVE**

Consolidar as divergências documentais num registro de integração T3.12, distinguindo contrato pretendido de permissões atualmente implementadas.

**O QUE EU FARIA DIFERENTE**

**(2) Expiração:** manteria **`status=approved`**, mudando `reservation_state=expired`, retirando `reserved_slot` e registrando a liberação do saldo não executado na mesma transação. Preservaria os valores originais da reserva como histórico.

Aqui prevalece a definição específica dos dois eixos em **DATABASE §18.3**, também prevista na T3.1; `PIPELINE.md:216` precisa ser corrigido. Não é uma precedência universal de DATABASE sobre PIPELINE ([DATABASE.md:1870](C:/dev/project-hunter/docs/DATABASE.md:1870), [DATABASE.md:1897](C:/dev/project-hunter/docs/DATABASE.md:1897), [PIPELINE.md:216](C:/dev/project-hunter/docs/PIPELINE.md:216)).

**(6) Ordem transacional:** a ordem proposta é adequada, com estas condições:

- **Antes do dedupe:** identidade autenticada, organização e acesso à carteira resolvidos. A chave única é **`(organization_id, idempotency_key)`**, não por carteira. Reutilização da chave com outra carteira ou conteúdo deve produzir conflito explícito, não devolver silenciosamente outra decisão ([execution.py:90](C:/dev/project-hunter/packages/core/hunter_core/db/models/execution.py:90)).
- **Depois das travas:** reler estado, contador e participação; fixar o instante efetivo da avaliação e revalidar idade/validade dos insumos obtidos previamente. Esperar pela trava não pode conservar artificialmente a juventude do book.
- **Savepoint:** executar efetivamente o INSERT dentro dele; capturar somente a violação de `uq_trade_proposals_idem`. Se perdeu a disputa, recuperar e conferir a proposta existente e retornar antes de incrementar, reservar, auditar ou enfileirar. Outras violações precisam continuar sendo erros.
- **Publicação:** auditoria e INSERT da outbox permanecem dentro; Redis, rede e ACK ficam depois do commit. Isso corresponde aos contratos de [audit.py:144](C:/dev/project-hunter/packages/core/hunter_core/audit.py:144) e [outbox_store.py:107](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:107).

Ressalva: hoje `effective_state(lock=True)` trava organização e carteira, mas **sistema é configuração do processo, sem trava durável**. Não declare serialização entre processos desse escopo ([scopes.py:121](C:/dev/project-hunter/packages/core/hunter_core/risk/scopes.py:121)).

**CONCORDO COM**

**(3) FIFO também para recusadas.** Minha interpretação do contrato é: toda proposta nova que chega à decisão persistida recebe sequência, aprovada ou recusada. Recusada fica com `reservation_state=none`, sem compromissos. Retry recupera identidade, sequência e resultado originais; não reavalia nem recicla a recusa. Requisições inválidas ou não autorizadas barradas antes desse estágio não precisam virar propostas ([M3.md:148](C:/dev/project-hunter/docs/plans/M3.md:148)).

**(4) A soma correta é exatamente:**

```text
executado nos últimos 60 s
+ Σ por reserva held max(0, reservado − executado − liberado)
```

O executado de uma reserva ainda held participa **positivamente apenas do primeiro termo**; no segundo, reduz o compromisso ainda executável. Use o histórico inteiro de cada reserva no segundo termo, sem corte de 60 s e sem compensação entre reservas ([DATABASE.md:2026](C:/dev/project-hunter/docs/DATABASE.md:2026), [DATABASE.md:2066](C:/dev/project-hunter/docs/DATABASE.md:2066)).

No exemplo, com tudo dentro da janela:

| Momento | Executado | Saldo held | Usado |
|---|---:|---:|---:|
| Reserva 80 | 0 | 80 | 80 |
| Fill 30 | 30 | 50 | 80 |
| Cancelamento 50 | 30 | 0 | 30 |
| Nova reserva 70 | 30 | 70 | 100 |

Não exclua uma reserva apenas porque `reserved_until` venceu: a transição de expiração precisa ocorrer sob a trava. O repositório atual também conta `held` independentemente do timestamp ([ledger.py:139](C:/dev/project-hunter/packages/core/hunter_core/db/repositories/ledger.py:139)).

**OBSIDIAN**

- **Risk Engine** — registrar fallback parcial, FIFO das recusadas e acoplamento com transições duráveis.
- **Portfolio** — documentar contador permitido à API, com referência diária e pico protegidos.
- **Execution Engine** — esclarecer expiração da reserva, preservação da decisão e liberação apenas do saldo.
- **Revisoes-Astra/Index** — vincular este parecer da T3.12 e os bloqueios de contador/outbox.