**RESUMO**

**REQUEST_CHANGES:** os itens 1 e 2 fecham os buracos apontados; o item 3 ainda perde tentativas por outro caminho. Revisão como `code-reviewer`.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados; revisão estática do código e dos testes indicados.

**MUST-FIX**

- **HIGH — timeout ainda queima tentativa durante queda de coordenação.** O recovery limita o fetch a **20 s**, enquanto `acquire()` usa **30 s**. Se Redis cair durante o backfill e permanecer fora, o `wait_for` produz `TimeoutError` antes de surgir `RateLimited(reason="redis_unavailable")`. O predicado não reconhece esse erro: um gap com quatro tentativas vai para `failed`. O teste novo injeta diretamente a exceção esperada e não cobre essa composição. Referências: [recovery.py:201](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:201), [rate_limit.py:131](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit.py:131), [rest.py:163](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/rest.py:163), [recovery.py:166](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:166), [test_recovery_gate.py:145](C:/dev/project-hunter/services/market-worker/tests/test_recovery_gate.py:145).

**NICE-TO-HAVE**

- **Colisão parcialmente resolvida:** `redis` agora fica protegido, mas, se existir também um check chamado `redis_detail`, o diagnóstico `redis` sobrescreve esse segundo booleano. Procurar uma chave realmente livre ou separar os diagnósticos. [runtime.py:147](C:/dev/project-hunter/packages/core/hunter_core/runtime.py:147).

**O QUE EU FARIA DIFERENTE**

Acrescentaria um teste com limiter real, Redis indisponível durante o fetch e gap começando em quatro tentativas, cobrindo o timeout externo e a retomada.

**CONCORDO COM**

1. **`degraded` não fica preso por uma falha antiga de `block_for`.** Cada leitura bem-sucedida limpa o flag; se a republicação do bloqueio falhar, ele volta a indicar uma falha atual. `_gate_wait_s` então suspende corretamente. [rate_limit_gate.py:163](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit_gate.py:163), [rate_limit.py:197](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit.py:197).

2. **Heartbeat sobrevive e o estado atual volta a ser publicado:** o intervalo força nova tentativa mesmo com `previous_ws_state` atualizado. **Uma transição transitória durante a queda pode desaparecer do pub/sub**, mas a transição WS observada ainda é enviada ao Postgres independentemente do sucesso Redis. Não há garantia de replay; a frase “nothing is permanently lost” está ampla demais. [heartbeat.py:202](C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:202), [heartbeat.py:251](C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:251), [heartbeat.py:272](C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:272).

3. **O `-= 1` está correto:** desfaz exatamente o incremento desta chamada, preservando tentativas anteriores. Erros comuns continuam contando; indisponibilidade persistente mantém o gap aberto intencionalmente. O problema é reconhecer a causa quando ocorre timeout. [recovery.py:121](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:121), [recovery.py:167](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:167).

4. **Documentação honesta sobre `/ready`:** Redis fora produz 503 pelo check existente. Porém, a promessa absoluta de não gastar tentativas ainda depende do must-fix acima. [PIPELINE.md:51](C:/dev/project-hunter/docs/PIPELINE.md:51), [runtime.py:129](C:/dev/project-hunter/packages/core/hunter_core/runtime.py:129).

**OBSIDIAN**

- **Exchange Adapters** — registrar recuperação do flag `degraded` após leitura/republicação.
- **Market Collector** — registrar o timeout externo ainda contabilizado como tentativa.
- **Workers** — distinguir republicação do estado atual de replay de transições.