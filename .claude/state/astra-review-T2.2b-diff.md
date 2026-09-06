**RESUMO**

Concordo em manter o `xfail strict` e deixar a decisão de memória para T2.5b. Não encontrei erro na memoização, mas a prova de equivalência precisa de correção.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executei testes nem reproduzi benchmarks nesta revisão somente de leitura. Os tempos informados são evidência sua, não medição independente minha.

**MUST-FIX**

- **Os cortes caminham para trás:** `_cuts` diminui o instante a cada passo ([test_engine_identity.py:114](/C:/dev/project-hunter/packages/indicators/tests/unit/test_engine_identity.py:114)). Isso não prova evolução contínua do ATR: um defeito ao incorporar a próxima barra poderia escapar. Ordene crescentemente e preserve os estados independentes.
- **O buffer não desliza:** são quatro cópias do mesmo `candles[-1500:]`, com estado reiniciado ([test_engine_identity.py:182](/C:/dev/project-hunter/packages/indicators/tests/unit/test_engine_identity.py:182)). Uma regressão ao remover a vela mais antiga mantendo o checkpoint não seria exercitada. Selecione as últimas 1500 disponíveis **em cada corte** e carregue estado.

**NICE-TO-HAVE**

Teste explicitamente o fallback com `close_time` fora de ordem em [_usable_for_bars](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:184).

**O QUE EU FARIA DIFERENTE**

Em T2.5b, corrigiria primeiro a fixture e exigiria `len(final_candles) == 1500` **fora do teste marcado xfail**, para essa falha não ficar mascarada.

Consideraria reutilização de velas decodificadas pertencente à instância do scanner, com comparação dos bytes para detectar correções e reconstrução do corte por avaliação. É um caminho sem estado global, mas exige memória e prova de invalidação; não é um atalho gratuito para T2.2b.

**CONCORDO COM**

- **Prefixo:** confere. A subsequência preserva ordem e o contexto proíbe `open_time` repetido; portanto a identidade do último elemento prova os índices `0..m−1` ([context.py:165](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:165)).
- **(a):** cada avaliação relê e decodifica as velas ([scanner/context.py:118](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/context.py:118)). Isso sustenta o diagnóstico; não prova que nenhuma otimização do decoder seja possível.
- **(b):** confirmado por inspeção: a fábrica fixa BTCUSDT, o seed compartilha essas linhas e `build_context` descarta símbolos estrangeiros ([builders.py:57](/C:/dev/project-hunter/services/scanner-worker/tests/builders.py:57), [test_load.py:63](/C:/dev/project-hunter/services/scanner-worker/tests/test_load.py:63), [context.py:287](/C:/dev/project-hunter/packages/indicators/hunter_indicators/features/context.py:287)). O teste não mede o motor com histórico completo.
- **(c):** `1625 × 1500 × 200 = 487,5 MB`, aproximadamente **465 MiB**, antes de outros custos. Concordo em não assumir essa retenção nesta tarefa.

**OBSIDIAN**

- **Features (Feature Engine)** — memoização e lacunas corrigíveis na prova de equivalência.
- **Workers** — fixture inválida, custo de decode e pendências de T2.5b.