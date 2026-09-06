**RESUMO**

Ainda não aprovaria: há uma brecha na falha parcial do Redis e duas violações da promessa de sobreviver à queda.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados; revisão estática dos caminhos e testes indicados.

**MUST-FIX**

1. **Falha na consulta do bloqueio pode admitir REST.** Se `IP_WAIT_SCRIPT` falhar sem espelho local, `wait_s()` devolve zero; se o consumo seguinte funcionar, `acquire()` admite sem conhecer o cooldown compartilhado. Cenário: timeout na leitura do bloqueio, reconexão bem-sucedida no consumo, outro shard já recebeu 429. É preciso exigir sucesso das duas verificações. [rate_limit_gate.py:163](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit_gate.py:163), [rate_limit.py:158](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit.py:158).

2. **Redis totalmente fora ainda mata o worker pelo heartbeat.** As escritas Redis escapam sem tratamento; a tarefa pertence ao `TaskGroup`, que cancela inclusive a ingestão. Portanto, proteger apenas o limiter não garante “WS continua”. [heartbeat.py:231](C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:231), [main.py:119](C:/dev/project-hunter/services/market-worker/hunter_market_worker/main.py:119).

3. **Queda durante um ciclo de recovery ainda gasta tentativas.** A suspensão só é verificada antes de `check_gaps`. Se Redis cair durante um backfill, o timeout/erro chega a `recover_registered`, que incrementa `attempts`; um gap com quatro tentativas vira `failed`. Revalidar durante o ciclo e não contabilizar indisponibilidade de coordenação. [recovery.py:325](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:325), [recovery.py:194](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:194), [recovery.py:121](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:121).

**NICE-TO-HAVE**

Proteger colisões de nomes em `status_details`: hoje um diagnóstico chamado `redis` sobrescreve o booleano no corpo, embora não altere o HTTP. [runtime.py:142](C:/dev/project-hunter/packages/core/hunter_core/runtime.py:142).

**O QUE EU FARIA DIFERENTE**

Exigiria testes dos três cenários acima e de retomada com limiter real, sem trocar manualmente o status. O recovery apenas consulta o estado: sem outra chamada que reprobe cada limiter suspenso, pode esperar indefinidamente. O teste atual força `adapter.status = "ok"` e não prova essa retomada. [recovery.py:325](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:325), [test_recovery_gate.py:104](C:/dev/project-hunter/services/market-worker/tests/test_recovery_gate.py:104).

**CONCORDO COM**

- `status_details` separa corretamente diagnóstico e veredito. **Redis fora continua produzindo 503 pelo check existente**; corrigir a promessa de “prontidão verde” no parágrafo 7. [runtime.py:129](C:/dev/project-hunter/packages/core/hunter_core/runtime.py:129), [PIPELINE.md:51](C:/dev/project-hunter/docs/PIPELINE.md:51).
- Com Redis configurado, falhas de consumo/reconciliação não ativam `LocalBuckets`; cooldown preserva primeiro o bloqueio local. Porém, **`redis=None` admite deliberadamente**: a garantia é condicional, não universal. O worker fornece `runtime.redis`. [rate_limit.py:111](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit.py:111), [rate_limit.py:275](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit.py:275), [rate_limit.py:334](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit.py:334), [main.py:43](C:/dev/project-hunter/services/market-worker/hunter_market_worker/main.py:43).

**OBSIDIAN**

- **Exchange Adapters** — registrar falha parcial do gate e exceção explícita de `redis=None`.
- **Market Collector** — registrar sobrevivência do heartbeat, tentativas durante queda e mecanismo de retomada.
- **Workers** — esclarecer diagnóstico `rest_gate` versus veredito HTTP.