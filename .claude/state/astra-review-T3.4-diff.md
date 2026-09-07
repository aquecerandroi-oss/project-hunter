**RESUMO**

Como `risk-engine-guardian`: **DONE_WITH_CONCERNS — não aprovaria a T3.4 ainda.** Confirmei falhas na autorização representada pelo construtor, nos gatilhos e nas transições de intenção. Não atribuo ao adaptador a implementação das travas da T3.5.

**ARQUIVOS**

Li integralmente os arquivos solicitados. Nenhum arquivo criado ou modificado; nenhum commit.

**TESTES**

Executei sondas em memória com `uv run python -B -`, sem gravar bytecode. Saída real selecionada:

```text
manual_approval_without_decision: filled 3
target_then_stop_first_and_replay: ('target', '101') ('target', '101')
trade_not_yet_received: triggered
watermark_100_bad_id_then_99: None triggered 99
voided_no_fill_reopens_with_closed_at: open True
missing_avg_and_book: rejected avg_price_unavailable False False 10
```

Não reexecutei pytest, ruff ou pyright; os 84+6 verdes são o resultado informado por você.

**MUST-FIX**

1. **Q1 — HIGH: o booleano substitui a decisão.** [intents.py:98](C:/dev/project-hunter/packages/core/hunter_core/execution/intents.py:98) aceita construção direta com `risk_approved=True`; somente `from_decision` examina `RiskDecision`. **Cenário:** um consumidor monta a ordem de uma proposta recusada, informa `True` e obtém fill — reproduzido sem construir decisão alguma. A própria fixture usa esse caminho ([test_paper_entry.py:36](C:/dev/project-hunter/packages/core/tests/unit/execution/test_paper_entry.py:36)). Exigir a decisão correspondente, validando identidade e quantidade; a comprovação de persistência continua responsabilidade do escritor transacional. **Teste decisivo:** proposta recusada + booleano verdadeiro não pode produzir entrada.

2. **Q3 — HIGH: primeiro cruzamento pode esconder o stop remanescente.** [triggers.py:153](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:153) aceita igualdade com a watermark; [triggers.py:176](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:176) retorna imediatamente. **Cenário:** posição de 10, alvo parcial de 4; negócios `101@110 → 102@94`. Primeira chamada devolve alvo/101; repetir com watermark 101 devolve **o mesmo alvo**, deixando o stop das unidades restantes sem notificação. Cronologia é correta; **gatilho não equivale a liquidação**. A justificativa do [teste atual:66](C:/dev/project-hunter/packages/core/tests/unit/execution/test_triggers.py:66) confunde essas coisas. Separar observação ainda utilizável de cruzamento já processado e garantir processamento do restante do lote. **Teste:** alvo parcial ou sem fill, seguido de stop, inclusive após restart.

   Há outras duas falhas temporais reproduzidas: o código verifica `ts`, mas ignora `received_at > now`; e ID inválido retorna watermark `None`, permitindo depois aceitar 99 quando já havia aceitado 100 ([triggers.py:145](C:/dev/project-hunter/packages/core/hunter_core/execution/triggers.py:145)). Recusar observação ainda indisponível e preservar watermark em toda saída.

3. **Q4 — HIGH: terminal pode reabrir e violar CHECK.** [apply_attempt:266](C:/dev/project-hunter/packages/core/hunter_core/execution/intents.py:266) não exige intenção viva; recalcula estado sem limpar ou validar `closed_at`. **Cenário reproduzido:** `voided` recebe tentativa sem fill e vira `open` com `closed_at` preenchido. O banco recusa pelo CHECK [terminal_states_are_closed:133](C:/dev/project-hunter/packages/core/hunter_core/db/models/paper_execution.py:133). O modelo também aceita `fulfilled` sem fechamento. Espelhar a bicondicional e impedir tentativa/aplicação em terminais. **Teste:** transições de todos os terminais com zero e algum fill, confrontadas com o banco.

4. **Q1/Q2 — HIGH: ausência de referência esconde degradação.** [paper.py:179](C:/dev/project-hunter/packages/core/hunter_core/execution/paper.py:179) transforma qualquer recusa de filtro em resíduo e retorna antes de avaliar o livro. **Cenário reproduzido:** saída de 10 unidades, sem média nem livro → `rejected/avg_price_unavailable`, sem degradação nem alerta, resíduo de 10. Falta de referência não demonstra dust. Separar indisponibilidade de dados, mínimos e máximos; preservar intenção e alerta. **Teste:** livro ausente combinado com média ausente deve continuar explicitamente degradado.

5. **Q5 — HIGH: falta preservar a evidência causadora.** [paper.py:170](C:/dev/project-hunter/packages/core/hunter_core/execution/paper.py:170) grava como `trigger_trade_id` o negócio da **tentativa**, não necessariamente o gatilho. **Cenário:** stop dispara em 95, falta livro, nova tentativa recebe negócio em 100; o relatório atribui o disparo ao negócio errado. Acrescentar observação causadora imutável — preço, ID, evento, disponibilidade e `triggered_at` — separada da observação atual.

   Para a T3.5, completar também o relatório ou seu envelope obrigatório com identidade de mercado/escopo, vínculo à decisão, referência de filtro com janela/disponibilidade e parâmetros efetivos das políticas ([adapter.py:125](C:/dev/project-hunter/packages/core/hunter_core/execution/adapter.py:125)). Sem isso, replay não distingue referências temporalmente válidas nem identifica sozinho o namespace do consumo do livro.

**NICE-TO-HAVE**

O `ExecutionAdapter` público deve expor os argumentos de consumo, sequência e watermark disponíveis nas implementações; hoje o contrato omite essas entradas necessárias à integração ([adapter.py:290](C:/dev/project-hunter/packages/core/hunter_core/execution/adapter.py:290)).

**O QUE EU FARIA DIFERENTE**

Na T3.5: reler estado sob trava, calcular e persistir relatório **inclusive sem fill**, consumo, ledger, intenção e outbox na mesma transação. Replay retorna o resultado persistido antes de aplicar novamente. `allocate_sellable` limita uma chamada; duas chamadas sobre saldo antigo continuam podendo alocar a mesma unidade — isso exige a trava, não outra fórmula ([intents.py:234](C:/dev/project-hunter/packages/core/hunter_core/execution/intents.py:234)).

**CONCORDO COM**

- **Q1:** não encontrei trava de entrada bloqueando diretamente proteção; a saída tem caminho separado ([paper.py:141](C:/dev/project-hunter/packages/core/hunter_core/execution/paper.py:141)).
- **Q2:** a ordem interna dos vereditos esconde motivos secundários, mas não torna livro inválido elegível. `received_at` é honesto como disponibilidade local, sem provar formação na exchange nem seleção do primeiro snapshot ([book_walk.py:89](C:/dev/project-hunter/packages/core/hunter_core/execution/book_walk.py:89)).
- Fee em base, deltas separados e slippage adverso sem correção estão coerentes ([paper.py:131](C:/dev/project-hunter/packages/core/hunter_core/execution/paper.py:131), [pricing.py:143](C:/dev/project-hunter/packages/core/hunter_core/execution/pricing.py:143)).

**OBSIDIAN**

- **Execution Engine** — registrar bloqueantes e fronteira transacional da T3.5.
- **Paper Trading** — distinguir cronologia de gatilho, fill efetivo e indisponibilidade.
- **Portfolio** — documentar terminais irreversíveis e CHECK de fechamento.
- **Revisões Astra / T3.4** — registrar cenários reproduzidos e testes de fechamento.