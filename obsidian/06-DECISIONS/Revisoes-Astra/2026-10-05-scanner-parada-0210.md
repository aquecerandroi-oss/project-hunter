---
tags: [astra, revisao, scanner, radar, persistencia, alarme, incidente]
status: fechada
owner: backend-specialist
updated: 2026-10-05
decided_on: 2026-10-05
by: Astra + backend-specialist
---

# Revisão da Astra — a segunda parada do `scanner-worker` (02/10/2026 10:12Z) e o alarme

Pedido: diagnosticar, só com evidência durável, por que o scanner parou de persistir de novo em 02/10 10:12Z (~21,5 h depois do deploy `9622f087`, que levou a mitigação das anomalias) e implementar o alarme que a [[Scanner-lag-2026-10-01]] propôs. Diagnóstico completo e comandos: seção 7 daquela nota. Bruto (a fonte, não o registro): `.claude/state/astra-review-scanner-stop-0210.md`. Ela declarou não ter executado testes nem gates.

**Aceitos (must-fix) — todos viraram código ou texto:**
- **O alarme da primeira versão podia continuar verde com todos os lotes com dados falhando.** Cenário dela: o lote com dados falha e é descartado; o ciclo seguinte não tem mercado devido, `flush_batch` retorna sem abrir transação (`persist.py:161`) e o `cycle.committed()` incondicional zerava o relógio, a cada ciclo quieto. **Corrigido:** só conta como commit o flush que escreveu linhas (`not batch.empty`); flush vazio ou só de ACKs não limpa nem inicia nada. Teste novo, **falha por mutação** se o commit voltar a ser incondicional (rodei a mutação).
- **Trabalho produzido antes de uma exceção podia nunca entrar no relógio** (a coleta de A precede a falha de B em `advance`; o `touch` só ocorre depois do laço inteiro). **Resolvido mudando o desenho:** o relógio deixou de depender de "avaliações pendentes" e passou a ser o da **sequência de falhas** (`failing_since`, iniciada por `cycle.failed(error)` no `except`), que não depende do `touch`.
- **`failure_summary` não garantia ausência de dados:** `detail` copiado cru (uma violação NOT NULL traz `Failing row contains (...)`) e mensagens de erro de conversão (classe SQLSTATE 22) ecoam o valor. **Corrigido com lista de permissão:** `detail` só sobrevive como `Key (cols)=(uuids)` de violação única; a mensagem do servidor só para as classes `08/23/40/53/55/57`; o resto vira frase fixa. Três testes com sentinelas.
- **Lacuna que a Astra nomeou e que fica registrada, não corrigida:** o `scanner_persistence` cobre só o laço de avaliação; falhas exclusivas do watchdog (lote próprio, `runners.py` ~250) ficam fora do contador (o resumo curto de log, sim, vale para ele e para o regime).
- **`_drop_invalidated` produz a divergência sem falha prévia** (a linha `EXPIRE` de X e seu evento somem depois de a memória esquecer X e a transação termina bem). Pré-existente e **latente**: medi que nenhuma baseline foi deletada (arquivo desde 06/09 intacto), então não foi o gatilho de 02/10 — mas reter o lote só no `except` não basta; entra como regressão exigida da cura.

**Aceitos (nice-to-have):** a promessa "vermelho nos primeiros 3 minutos" estava exagerada — com `interval 15 s × retries 5` o `unhealthy` do Docker chega ~3 min depois da primeira falha e `/ready` fica vermelho em 2 (texto corrigido); 120 s é ponto de partida, não distribuição medida (calibrar por `failing_for_s`). `_run_loop` do teste de falha terminava em 0,8 s, antes da espera de 1 s — o teste novo do flush vazio roda 2,4 s para observar a tentativa seguinte.

**Divergências / não adotado (escritas):**
- **Duração por relógio monotônico (nice-to-have dela):** não adotei; as durações usam a diferença de dois `utcnow()` como o resto do `health.py` e os testes controlam o tempo por atribuição. Risco aceito: um salto de NTP de segundos não muda um limiar de 120 s.
- **Separar "commit confirmado" de "ACKs concluídos"** (`persist.py:180`): não mexi — o relógio só se mantém aberto numa sequência de falhas, e o ACK lento só atrasa o *fim* da sequência; mexer pede alterar `flush_batch`, fora do escopo de 3 arquivos.
- **Causa raiz:** ela concorda com a hipótese como consistente com a evidência e **não** com "supersede de oportunidades no writer" como conserto principal (a expiração teria de gerar o evento `opportunities.updated`, que nasce na coleta). Prefere reter o lote com um único dono da sequência mutação → persistência (avaliação **e** watchdog); reidratar do banco é complementar, não rollback completo. Concordo; **não implementei** a cura (exige extrair o laço de `runners.py`, 348 linhas, e desenho) e deixei o teste que falha hoje como `xfail` estrito.

**Concordâncias absorvidas:** medir a duração da falha/pendência é superior a consultar `dirty > 0` no instante; o mecanismo "memória avança → lote perdido → id novo contra id antigo aberto" continua consistente; os 726 `scanner_anomalies_superseded` sem `metadata.superseded_by` no banco se explicam porque o aviso sai **antes** do commit e a escrita de oportunidades vem depois na mesma transação (rollback).

## Segunda rodada — a cura (retenção do lote), `REQUEST_CHANGES` e o que foi feito

Pedido: revisar o diff da cura (`FlushLane`, lock único para avaliação e watchdog, retenção limitada, resync das invalidações). Bruto: `.claude/state/astra-review-scanner-batch-retention.md`. Ela rodou 20 testes e quatro sondas em memória (passaram) e **não** rodou `test_flush_retry.py`, Docker nem gates completos. Veredito **`REQUEST_CHANGES`**, cinco bloqueadores; **todos aceitos e corrigidos**, cada um com teste que falha sem a correção (mutação executada):

1. **Resync antes de qualquer nova mutação** (cenário: `EXPIRE(X)` descartado, reload falha uma vez, o ciclo seguinte abre Y com X aberto e o flush é vetado pelo índice que o resync devia proteger; e, com o lote esvaziado por `_drop_invalidated` e a transação falhando, o `flush()` vazio esquecia os mercados). **Feito:** o resync é a primeira coisa do ciclo de avaliação e da varredura do watchdog, e o lote guarda `invalidated` (sobrevive à falha).
2. **Reidratação do universo fora da exclusão mútua** (meu `authoritative` apagaria um `OPEN(Y)` já coletado de um mercado que acabou de entrar). **Feito de outro jeito que ela sugeriu:** o caminho do universo voltou a ser **não destrutivo**; só o resync, sob o lock, é autoritativo. A corrida de reidratação do universo em si (pré-existente) fica registrada como aberta.
3. **Regime pode envenenar a lane** (`scanner.regime_id` publicado antes do flush; oportunidade que cita regime inexistente é recusada pela FK e, **com retenção, segura todos os commits** — a retenção piorava um caso que antes só perdia o lote). **Feito:** o id só é exposto depois do commit. **Não resolvido (escrito):** o classificador já avançou, então a linha do novo regime só nasce na próxima troca.
4. **Toque velho do watchdog sobrescreve avaliação nova** (`persist` grava oportunidades e depois `episode_touches`). **Feito:** `touch_episodes` só aplica a linha que não seja mais nova (`last_updated_at <=`); também evita reabrir um episódio já expirado. Teste de SQL local; o teste contra Postgres real está escrito e **não rodou**.
5. **ACKs ultrapassam a avaliação com a lane bloqueada.** **Feito:** bloqueada, os ACKs novos ficam no estado e não entram no lote.

**Nice-to-have aceitos:** o teste de resync falho agora exige que nenhuma avaliação ocorra antes do reload bem-sucedido; falha da própria varredura do watchdog também alimenta `cycle.failed`; o limite de 60 s é checado na próxima falha (documentado); reiniciar abandona o lote (dito na linha CRITICAL e na nota). **Não feito:** teste de integração de rollback de **oportunidades** e de falha pós-commit (só anomalias, e sem Docker aqui).

**Concordâncias absorvidas:** lock amplo em vez de `take()/restore()`; **pausar é melhor que descartar depois de N tentativas** (descartar perde o fechamento que evita a próxima violação; bissecção pode separar fechamento, abertura, histórico e evento do mesmo mercado) — para veneno determinístico será preciso intervenção humana; idempotência da repetição conferida (`(market_id, ts)`, `id`, `(opportunity_id, ts)`, `event_id`), valendo só para o **mesmo** conteúdo; falha de ACK individual não provoca retry do lote. **Divergência:** nenhuma de fundo; não pedi uma terceira rodada depois das correções.

## Relacionado
[[Scanner-lag-2026-10-01]] · [[2026-10-01-scanner-lag]] · [[Anomalies]] · [[Workers]]

## Fontes
`.claude/state/astra-review-scanner-stop-0210.md` · `services/scanner-worker/hunter_scanner_worker/{health,runners,failure_summary,persist,collect}.py` · `services/scanner-worker/tests/{test_commit_alarm,test_failure_summary,test_batch_retention}.py`
