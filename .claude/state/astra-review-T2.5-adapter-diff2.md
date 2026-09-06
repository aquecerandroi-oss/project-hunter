**RESUMO**

**BLOQUEADO.** A correção 1 está fechada; a 3 detecta a mudança de geração, mas a correção 2 ainda falha quando **reconexão é seguida de backlog antes da retomada**.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Executei o `git -C C:/dev/project-hunter diff -- packages/exchange-adapters services/market-worker`: saída com o diff, código `0`.

Não executei pytest nesta rodada. O cenário abaixo é dedução direta do código; os resultados informados por você não foram revalidados.

**MUST-FIX**

**HIGH — O backlog pode apagar a ruptura já detectada.** Em [coverage.py:296](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:296), `_break_reason = reason` substitui `"reconnect"` por `"queue_backlog"`. A retomada só reinicia a sessão quando o motivo preservado é `"reconnect"`: [coverage.py:283](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:283).

Cenário concreto, sem drops e sem escrita em voo:

| Stamp | Estado observado | Efeito |
|---|---|---|
| 12:00:01 | Conectado, geração 0, fila drenada | Sessão iniciada às 12:00:00 |
| 12:01:00 | Reconexão detectada por estado ou geração | Guarda `"reconnect"` |
| 12:02:00 | Conectado, geração estabilizada, fila `(7,5,0)` | Sobrescreve com `"queue_backlog"` |
| 12:02:01 | Conectado, fila `(7,7,0)` | Mantém a sessão antiga e avança `covered_until` para 12:02:00.5 |

O último avanço ocorre em [coverage.py:301](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:301), declarando continuidade através da lacuna.

**Correção necessária:** preservar `"reconnect"` até a retomada confirmada; backlog posterior não pode rebaixar esse motivo. Testar a sequência acima nas duas variantes: ruptura observada por `ws_state` e ruptura detectada somente pela geração.

**NICE-TO-HAVE**

Ainda há comentário dizendo que a geração não é consultada pelo tracker e é apenas logada: [ws.py:133](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:133). Isso contradiz a nova implementação em [coverage.py:264](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:264).

**O QUE EU FARIA DIFERENTE**

Preservaria o motivo mais forte durante todo o período interrompido: qualquer reconexão exige nova sessão; somente backlog, sem reconexão durante esse período, permite continuar a anterior.

**CONCORDO COM**

- **Correção 1 fechada:** ambos os ramos marcam `reconnecting` antes do fechamento — [connection.py:211](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:211) e [connection.py:223](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:223).
- **Detecção da correção 3 implementada:** housekeeping fornece a geração e o tracker compara com a anterior — [streaming.py:77](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:77), [coverage.py:267](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:267). Falta preservar essa ruptura no cenário combinado acima.

**OBSIDIAN**

- **Market Collector** — registrar que reconexão permanece invalidante mesmo quando seguida de backlog.
- **Revisões-Astra / T2.5 — cobertura** — registrar correção 1 fechada e bloqueio restante na transição reconexão → backlog → retomada.