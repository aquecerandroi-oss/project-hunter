**RESUMO**

**DONE_WITH_CONCERNS:** sobrou um caminho concreto em **(b)**. Não encontrei novo cenário de **(a)** ou **(c)** no núcleo revisado; isso não comprova a integração que persiste decisões e cria ordens.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

`uv run pytest packages/risk-core/tests/unit/test_review_findings.py packages/risk-core/tests/unit/test_exposure.py packages/risk-core/tests/unit/test_evaluate.py packages/risk-core/tests/unit/test_sizing.py -q`

```text
153 passed in 2.95s
```

Cache e bytecode desabilitados. Reprodução adicional em memória via `uv run python -B -`.

**MUST-FIX**

**HIGH — (b): âncora diária indisponível ainda impede proteção.** `day_start_equity` permanece obrigatório em [exposure.py:117](C:/dev/project-hunter/packages/risk-core/hunter_risk/exposure.py:117), e uma âncora do dia anterior provoca exceção em [exposure.py:150](C:/dev/project-hunter/packages/risk-core/hunter_risk/exposure.py:150). A saída exige esse estado em [evaluate.py:194](C:/dev/project-hunter/packages/risk-core/hunter_risk/evaluate.py:194).

**Cenário:** restart após a meia-noite de São Paulo; posição e quantidade recuperadas, stop acionado, mas referência diária ainda indisponível. Mesmo com `marks_complete=False`, não se consegue construir o estado para autorizar a saída. Reproduzi ambas as variantes:

```text
missing_day_anchor blocked_before_exit ('day_start_equity',)
previous_day_anchor blocked_before_exit ()
```

A segunda lança explicitamente `day_start_utc ... is not the Sao Paulo day of as_of`. A proteção fica dependente da recuperação de um dado usado para limitar entradas.

**NICE-TO-HAVE**

Nenhum.

**O QUE EU FARIA DIFERENTE**

Faria a saída depender apenas da identidade da carteira/posição e quantidade vendável; indisponibilidade da âncora diária deve bloquear entradas, sem exigir valores inventados para proteger posições.

**CONCORDO COM**

As duas correções anteriores estão fechadas: divergência virou diagnóstico em [exposure.py:158](C:/dev/project-hunter/packages/risk-core/hunter_risk/exposure.py:158), e o caixa desconta o compromisso próprio das reservas em [exposure.py:261](C:/dev/project-hunter/packages/risk-core/hunter_risk/exposure.py:261). A aprovação de entrada continua exigindo todos os checks em [evaluate.py:180](C:/dev/project-hunter/packages/risk-core/hunter_risk/evaluate.py:180).

**OBSIDIAN**

- **Risk Engine** — registrar as correções confirmadas e o bloqueio residual por âncora diária.
- **Execution Engine** — registrar o cenário de proteção durante recuperação da referência diária.
- **Revisoes-Astra/Index** — indexar esta segunda rodada e os 153 testes executados.