## RESUMO

**REQUEST_CHANGES — ainda não reportaria DONE.** O desenho principal está correto, mas encontrei falhas de recuperação, isolamento de eventos inválidos e preservação do cooldown. Revisão como `code-reviewer`, em modo OPINIÃO.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit. Revisei os arquivos indicados e os caminhos relacionados necessários para conferir seu comportamento.

## TESTES

Não executei pytest, lint ou typecheck nesta rodada. Os resultados apresentados são os seus; os achados abaixo vêm da inspeção do código e dos testes, sem reprodução dinâmica.

## MUST-FIX

**1. HIGH — A paginação do replay pode perder eventos.**

O filtro usa `id > after_id`, mas a ordenação é `(created_at, id)` em [outbox_store.py:227](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:227); o cursor seguinte recebe somente o último `id` em [outbox.py:268](C:/dev/project-hunter/packages/core/hunter_core/events/outbox.py:268).

**Cenário:** uma transação começa antes, mas insere depois e recebe IDs maiores. A primeira página contém esses IDs maiores por terem `created_at` anterior; a página seguinte exclui eventos posteriores com IDs menores, mesmo que todos já estejam commitados.

**Correção:** cursor composto consistente com a ordenação e uma fronteira explícita para o replay. Testar mais de 20 linhas com ordem de `created_at` diferente da ordem de `id`.

**2. HIGH — Um micro-lote cheio de eventos inválidos impede o despacho dos seguintes.**

O `continue` pula a linha apenas dentro do lote, mantendo-a pendente em [outbox.py:163](C:/dev/project-hunter/packages/core/hunter_core/events/outbox.py:163). A consulta seguinte seleciona novamente as mesmas primeiras pendências em [outbox_store.py:204](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:204).

**Cenário:** as primeiras 20 linhas têm payload inválido; a 21ª é válida. Cada transação tenta novamente as mesmas 20, incrementando erros até consumir o orçamento. Todas as varreduras seguintes repetem isso; a linha válida nunca sai.

**Correção:** avançar sobre as linhas já examinadas durante a varredura, preservando as inválidas para diagnóstico e retentativa posterior. Testar 20 inválidas seguidas de uma válida.

**3. HIGH — Os 5 segundos não são um limite efetivo de publicação.**

A verificação acontece antes do `await publish`, sem limitar sua duração em [outbox.py:158](C:/dev/project-hunter/packages/core/hunter_core/events/outbox.py:158) e [outbox.py:172](C:/dev/project-hunter/packages/core/hunter_core/events/outbox.py:172).

**Cenário:** o `XADD` começa quando faltam 100 ms; Redis deixa de responder. O cliente possui timeout de 5 s e três retentativas, mantendo a transação e seus locks além do orçamento anunciado — configuração em [redis.py:55](C:/dev/project-hunter/packages/core/hunter_core/redis.py:55) e [redis.py:89](C:/dev/project-hunter/packages/core/hunter_core/redis.py:89).

**Correção:** limitar o `await` ao tempo restante, tratar o resultado como publicação possivelmente realizada e preservar a semântica de retentativa. Testar publicação bloqueada; revisar também a promessa documental de transação curta.

**4. HIGH — A correção de `cooldown()` ainda é contornada pelo chamador REST.**

O bloqueio agora precede a reconciliação dentro de [rate_limit.py:295](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit.py:295), mas o REST já chama `record_used_weight()` **antes** de examinar 429/418 em [rest.py:161](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/rest.py:161).

**Cenário:** chega 429 com header de peso; o `EVAL` dessa reconciliação falha. A execução nunca alcança `cooldown()`, e nenhum deadline local é registrado. Redis recupera antes do `Retry-After`; o próximo pedido pode sair durante a proibição.

**Correção:** tratar o bloqueio 429/418 antes dessa reconciliação falível. Esse caminho é preexistente, mas impede considerar encerrada a correção anunciada. Requer ajuste coordenado em `rest.py` e teste pelo cliente REST.

**5. HIGH — Um bloqueio preservado apenas localmente não volta à coordenação quando Redis recupera.**

`block_for()` preserva o deadline local quando a escrita falha em [rate_limit_gate.py:128](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit_gate.py:128). Entretanto, `wait_s()` apenas lê Redis e já limpa `degraded` após uma resposta em [rate_limit_gate.py:152](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit_gate.py:152).

**Cenário:** A recebe um bloqueio de 60 s durante a queda; a escrita compartilhada falha. Redis volta após 10 s sem a chave. A continua bloqueado localmente, mas B encontra zero e admite pedidos pelos 50 s restantes.

**Correção:** republicar o restante de um bloqueio local ainda válido quando a coordenação retornar. Testar escrita falha → Redis recuperado sem chave → segundo processo tentando adquirir.

## NICE-TO-HAVE

- **O teste de bytes não simula todo o JSONB.** Ele embaralha somente o envelope externo em [test_events_outbox.py:106](C:/dev/project-hunter/packages/core/tests/unit/test_events_outbox.py:106). O payload continua um `dict`, e a serialização não ordena suas chaves em [envelope.py:30](C:/dev/project-hunter/packages/core/hunter_core/events/envelope.py:30). Testar reordenação recursiva ou round-trip real. Isso não invalida a identidade por `event_id`, mas a promessa de bytes idênticos precisa ser precisa.
- **Readiness deve expirar observações antigas.** `last_sweep_at` é atualizado, mas não participa do veredito em [outbox.py:119](C:/dev/project-hunter/packages/core/hunter_core/events/outbox.py:119). Uma falha persistente da consulta da outbox pode conservar o último estado verde.
- **Corrigir as notas sobre fallback:** com Redis configurado, `_try_consume()` não passa para o bucket local após falha; propaga o erro em [rate_limit.py:152](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit.py:152). Portanto, a implementação não corresponde à descrição de “N budgets locais durante a queda”. Não recomendo introduzir isso apenas para alinhar a documentação.

## O QUE EU FARIA DIFERENTE

**(a) Custo e laço:** `refresh_health()` não cria recursão. Entretanto, não é necessariamente uma consulta por segundo: cada passagem da reconciliação e cada despertar podem executá-la. Além disso, `COUNT` e `MIN` percorrem as pendências; índice não torna essa agregação constante ([outbox_store.py:254](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:254)).

Com backlog finito e válido, a reconciliação termina. Com produtores continuamente repondo trabalho, pode nunca observar `sent == 0`; isso é drenagem produtiva, não necessariamente um spin. Eu delimitaria a fase inicial e deixaria a continuidade para o dispatcher. O spin sobre inválidos é o achado 2 ([outbox.py:236](C:/dev/project-hunter/packages/core/hunter_core/events/outbox.py:236)).

**(c) Espelhamento:** concordo em preservar o deadline de outro processo, mas existe sobreespera por latência: o restante calculado no Redis é somado ao relógio local **depois** da resposta. Uma resposta atrasada estende o espelho por esse atraso; Redis posteriormente devolver zero não encurta o valor ([rate_limit_gate.py:101](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit_gate.py:101)). Sem novos bloqueios, não vejo prisão infinita nesse mecanismo. Eu testaria atraso de resposta e documentaria a margem conservadora.

## CONCORDO COM

- **(b) Rollback após publicação:** aceitável para entrega pelo menos uma vez. Não exigiria transação separada para eliminar duplicatas: ela não elimina a janela entre Redis e Postgres. A marcação atual ocorre depois da publicação em [outbox.py:182](C:/dev/project-hunter/packages/core/hunter_core/events/outbox.py:182). Uma transação separada pode ajudar a registrar diagnóstico após rollback, mas não deve marcar como entregue uma publicação incerta.
- **(d) Identidade do OI:** sim, o bucket é a identidade correta para a linha persistida. O conflito é `(market_id, ts)` usando o bucket; o evento preserva também `oi.ts` como instante da observação ([persist_rows.py:289](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:289), [durable.py:178](C:/dev/project-hunter/services/market-worker/hunter_market_worker/durable.py:178)). Bucket não deve virar instante de disponibilidade do dado.
- **Enqueue compartilhado e wake após commit:** escolhas corretas. O `RETURNING` completo associa a vela efetivamente inserida ao evento, e o drain apenas acorda o dispatcher ([persist_rows.py:141](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:141), [persist.py:223](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist.py:223)).
- **(e) Invariantes:** não identifiquei nova violação concreta de Decimal/UTC, look-ahead, isolamento de tenant ou dado fabricado no escopo revisado. Candles não finais são filtrados, valores derivados são serializados como strings e a identidade temporal normaliza UTC ([persist_rows.py:109](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:109), [durable.py:127](C:/dev/project-hunter/services/market-worker/hunter_market_worker/durable.py:127), [outbox_store.py:74](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:74)).
- **Universo fora desta edição:** concordo com respeitar a restrição; permanece uma pendência explícita, não uma migração concluída ([notes-T2.9.md:8](C:/dev/project-hunter/.claude/state/notes-T2.9.md:8)).

## OBSIDIAN

- **Revisoes-Astra/T2.9-outbox** — registrar REQUEST_CHANGES, os cinco cenários e os testes necessários para encerrá-los.
- **Data Flow** — esclarecer paginação do replay, duplicação física permitida e efeito transacional idempotente.
- **Exchange Adapters** — registrar preservação e recomposição do cooldown compartilhado; corrigir a descrição do fallback.
- **Market Collector** — registrar a migração dos produtores e manter `market.universe.changed` como pendência explícita.