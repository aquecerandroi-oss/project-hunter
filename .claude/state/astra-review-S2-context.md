**RESUMO**

**Sim, fecha o must-fix 1.** Não identifiquei outro bloqueio na correção final:

- O hot state é consultado incondicionalmente com o corte da avaliação: [derivatives.py:174](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/derivatives.py:174).
- A leitura filtra `oi_ts <= cut` antes de entregar o valor ao resolver: [hot_state.py:151](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/hot_state.py:151).
- O resolver aceita esse hot state e, sem ele, recusa a linha durável com valor usando `timestamp_unprovable`, sem depender da idade: [derivatives.py:146](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/derivatives.py:146).

**ARQUIVOS**

Revisão como `quant-engineer`, em modo OPINIÃO. Nenhum arquivo criado ou modificado; nenhum commit.

**TESTES**

Não executei pytest, ruff ou pyright nesta revisão. Os **205 passed** e demais resultados são os informados por você.

Conferi os testes de durável com um dia de idade e hot state com durável presente: [test_context_derivatives.py:222](C:/dev/project-hunter/services/strategy-worker/tests/test_context_derivatives.py:222) e [test_context_derivatives.py:245](C:/dev/project-hunter/services/strategy-worker/tests/test_context_derivatives.py:245).

**MUST-FIX**

Nenhum remanescente para o item 1.

**NICE-TO-HAVE**

Atualizar a abertura da documentação: “durável primeiro, hot state como fallback” ainda descreve os dois derivativos genericamente, embora OI agora tenha uma exceção obrigatória. Apenas clareza documental: [derivatives.py:1](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/derivatives.py:1), [hot_state.py:6](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/hot_state.py:6).

**O QUE EU FARIA DIFERENTE**

Nada na lógica desta correção. A prova com momentum realmente disparando pode permanecer como pendência explícita, conforme [notes-S2.md:594](C:/dev/project-hunter/.claude/state/notes-S2.md:594); ela não reabre o must-fix do OI.

**CONCORDO COM**

Os acréscimos cobrem os casos pedidos: funding elegível com mark futuro e OI independente, `UNKNOWN` e fronteiras exatas de regime. [test_context_derivatives.py:177](C:/dev/project-hunter/services/strategy-worker/tests/test_context_derivatives.py:177), [test_regime_stamp.py:127](C:/dev/project-hunter/services/strategy-worker/tests/test_regime_stamp.py:127), [test_regime_stamp.py:185](C:/dev/project-hunter/services/strategy-worker/tests/test_regime_stamp.py:185).

**OBSIDIAN**

- **Revisoes-Astra/S2-context** — registrar o fechamento do must-fix 1 e a pendência de momentum.
- **Workers** — documentar que OI exige hot state temporalmente elegível.
- **Market Collector** — manter como pendência preservar o timestamp real no histórico durável de OI.