**RESUMO**

**ACEITO. O MUST-FIX está fechado.** Não identifiquei outro caminho que rebaixe uma reconexão já registrada antes da retomada:

- A guarda preserva `reconnect` durante qualquer backlog subsequente: [coverage.py:292](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:292).
- Quando `caught_up=True`, a sessão é reiniciada **antes** de limpar o motivo: [coverage.py:283](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:283), [coverage.py:307](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:307).
- Isso vale também para ruptura detectada pela geração, que produz o mesmo motivo: [coverage.py:267](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:267).

**ARQUIVOS**

Nenhum criado ou modificado. Nenhum commit.

**TESTES**

Executei o diff solicitado: código de saída `0`. Não executei pytest nesta rodada; os resultados informados não foram revalidados.

O novo teste verifica congelamento durante o backlog e nova sessão na retomada: [test_tape_coverage.py:214](C:/dev/project-hunter/services/market-worker/tests/test_tape_coverage.py:214).

**MUST-FIX**

Nenhum restante para este achado.

**NICE-TO-HAVE**

Parametrizar o teste novo também para ruptura detectada somente pela geração; atualmente a sequência combinada usa `ws_state`: [test_tape_coverage.py:228](C:/dev/project-hunter/services/market-worker/tests/test_tape_coverage.py:228). Não bloqueia o aceite.

**O QUE EU FARIA DIFERENTE**

Nenhuma mudança funcional adicional neste ajuste.

**CONCORDO COM**

Preservar o motivo mais forte até confirmar a retomada resolve diretamente o defeito: [coverage.py:292](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:292).

**OBSIDIAN**

- **Market Collector** — registrar que reconexão permanece invalidante durante backlog até iniciar nova sessão.
- **Revisões-Astra / T2.5 — cobertura** — registrar o aceite da terceira rodada e o fechamento do último MUST-FIX.