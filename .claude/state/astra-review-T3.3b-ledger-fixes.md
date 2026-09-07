**RESUMO**

**REQUEST_CHANGES**, como `code-reviewer`, por duas lacunas: prova não determinística da corrida e identificação incompleta do snapshot na auditoria. A banda atende ao pedido anterior; a comparação opcional continua sendo uma pendência explicitamente documentada.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit. Revisei o diff solicitado e li os três módulos novos.

**TESTES**

Executei `git diff -- <arquivos solicitados>` e `git status --porcelain -- packages/core/hunter_core/portfolio`. Saída do status:

```text
 M packages/core/hunter_core/portfolio/ledger.py
 M packages/core/hunter_core/portfolio/opening.py
 M packages/core/hunter_core/portfolio/state.py
?? packages/core/hunter_core/portfolio/fx_policy.py
?? packages/core/hunter_core/portfolio/marking.py
?? packages/core/hunter_core/portfolio/positions.py
```

Não executei pytest nem os gates nesta revisão somente leitura. Os resultados **61/33** são os informados por você, não revalidados aqui.

**MUST-FIX**

1. **MEDIUM — `asyncio.gather` não garante que o teste exercite a tradução de `IntegrityError`.**  
   O teste verifica apenas uma vitória e um `WalletAlreadyOpen`. Se a primeira transação terminar antes do SELECT da segunda, esta sai pelo pré-check e o teste passa mesmo com o tratamento da corrida quebrado. [test_portfolio_opening.py:363](C:/dev/project-hunter/packages/core/tests/integration/test_portfolio_opening.py:363), [opening.py:140](C:/dev/project-hunter/packages/core/hunter_core/portfolio/opening.py:140), [opening.py:159](C:/dev/project-hunter/packages/core/hunter_core/portfolio/opening.py:159)

   **Correção:** colocar uma barreira depois que **ambos os SELECTs reais retornarem ausência**, antes dos INSERTs. Verificar que a exceção perdedora tem `IntegrityError` como `__cause__`. Complementar com contagens de âncora, estado de risco, snapshot inicial e auditoria da abertura.

2. **MEDIUM — a auditoria não identifica completamente o ponto degradado.**  
   A chave do snapshot inclui `(portfolio, resolution, ts)`, mas o evento conserva somente portfolio e timestamp; `resolution` não chega ao helper. [equity.py:57](C:/dev/project-hunter/packages/core/hunter_core/db/repositories/equity.py:57), [ledger.py:191](C:/dev/project-hunter/packages/core/hunter_core/portfolio/ledger.py:191), [ledger.py:218](C:/dev/project-hunter/packages/core/hunter_core/portfolio/ledger.py:218)

   **Cenário:** snapshots `1m` e `1h` no mesmo instante, um com FX recusada e outro saudável. O join sugerido nas notas não permite atribuir inequivocamente a recusa à resolução correta.

   **Correção:** persistir a chave completa no evento. Incluir também `rejected_fx_observation_id` quando houver observação recusada, preservando `fx_observation_id=NULL` no snapshot. Testar duas resoluções no mesmo instante.

**NICE-TO-HAVE**

- **FX: proteção parcial, conforme o escopo acordado.** `[1,100]` barra os exemplos originais, mas aceita `54,321` no lugar de `5,4321`. A abertura e a curva não passam `last_accepted`; portanto, não contam atualmente com a defesa de 20%. Isso já está reconhecido nas notas e **não reabro como bloqueante**. [fx_policy.py:113](C:/dev/project-hunter/packages/core/hunter_core/portfolio/fx_policy.py:113), [opening.py:135](C:/dev/project-hunter/packages/core/hunter_core/portfolio/opening.py:135), [ledger.py:119](C:/dev/project-hunter/packages/core/hunter_core/portfolio/ledger.py:119), [notes-T3.3.md:196](C:/dev/project-hunter/.claude/state/notes-T3.3.md:196)

- **Antes de integrar `last_accepted`, proteger sua causalidade.** O `abs()` aceita uma referência posterior, sem verificar sua disponibilidade em `as_of`. Um replay pode mudar de resultado ao receber a última observação aceita *hoje*. Exigir referência anterior e disponível no corte, além de par/fonte compatíveis. [fx_policy.py:119](C:/dev/project-hunter/packages/core/hunter_core/portfolio/fx_policy.py:119)

- **Falta testar auditoria de FX realmente recusada.** O teste chamado `test_a_refused_fx_observation_is_audited` passa `fx=None`: cobre ausência, mas não comprova persistência de `fx_rejected` e seu detalhe. [test_portfolio_state.py:604](C:/dev/project-hunter/packages/core/tests/integration/test_portfolio_state.py:604)

- **A garantia do AST está superdescrita.** A varredura exclui `infra/scripts` e só detecta o argumento nomeado diretamente; uma chamada via `**kwargs` escapa. Não encontrei uso indevido, mas o teste não prova “nenhum módulo de produção”. [test_no_funding_route.py:46](C:/dev/project-hunter/packages/core/tests/unit/portfolio/test_no_funding_route.py:46), [test_no_funding_route.py:174](C:/dev/project-hunter/packages/core/tests/unit/portfolio/test_no_funding_route.py:174)

**O QUE EU FARIA DIFERENTE**

Fecharia agora a barreira do teste e a chave completa da auditoria. Manteria a busca da última FX aceita como entrega explícita da integração, com teste de replay sem informação futura.

**CONCORDO COM**

O escopo por organização está alinhado ao índice; a recusa de posições não long e o contexto ampliado na acumulação dos custos atendem às correções propostas. [portfolio.py:58](C:/dev/project-hunter/packages/core/hunter_core/db/repositories/portfolio.py:58), [0006_paper_wallet.py:999](C:/dev/project-hunter/infra/migrations/versions/0006_paper_wallet.py:999), [marking.py:82](C:/dev/project-hunter/packages/core/hunter_core/portfolio/marking.py:82), [state.py:294](C:/dev/project-hunter/packages/core/hunter_core/portfolio/state.py:294)

**OBSIDIAN**

- **Portfolio** — registrar escopo por organização, limites efetivos da FX e chave completa da auditoria.
- **Paper Trading** — atualizar capital fixo e distinguir teste concorrente de prova determinística da corrida.
- **Revisoes-Astra/T3.3b** — registrar este parecer, os dois cenários e seus critérios de fechamento.