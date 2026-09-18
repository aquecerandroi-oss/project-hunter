# Revisão de risco — T4.52a (commit 51914d02), somente leitura

**Escopo:** executor de memes que assina transações REAIS na mainnet (0,05 SOL/op).
**Veredito: SAFE_WITH_FLAG** — subir só depois do conserto de uma linha em
`services/meme-executor/hunter_meme_executor/wake.py:76` (ou com um jeito de desligar o listener
por env). O resto são ressalvas; nenhuma delas cria ordem duplicada nem afrouxa a admissão.

## Achados (`arquivo:linha — severidade — afirmação — cenário concreto`)

### F1 — `services/meme-executor/hunter_meme_executor/wake.py:76` — ALTA

`await asyncio.sleep(self._backoff.compute(failures))` com `failures` sem teto.
`ExponentialWithJitterBackoff.compute` (redis-py 8.1) é `min(cap, random()*base*2**failures)` — o
Python avalia `0.25 * 2**failures` **antes** do `min`, então a partir de `failures = 1024` levanta
`OverflowError: int too large to convert to float`. A exceção nasce **dentro** do
`except Exception:` e escapa de `run()`, que não tem try externo.

Cenário: Redis inalcançável por ~85 min (container travado na VPS, rede do host). Cada volta é uma
falha de `subscribe` mais um sleep que satura em 5 s, ou seja ~1024 voltas ≈ 85 min. Aí `run()`
levanta `OverflowError`, o `asyncio.TaskGroup` de `main.py:236-253` cancela **todos** os irmãos
(`entries`, `exits`, `kill_switch`, `reconcile`, `heartbeat`) e o processo morre com posições reais
abertas — a perna de saída para de rodar até o Docker reerguer
(`infra/docker/docker-compose.yml:716`, `restart: unless-stopped`), e o ciclo se repete a cada
~85 min enquanto o Redis não voltar. O docstring da classe promete "Never raises"; ela levanta.

Agrava: `failures = 0` (wake.py:71) só executa quando `_listen_once` **retorna normalmente**, o que
uma assinatura viva nunca faz. O contador é cumulativo pela vida do processo — 1024 reconexões
somadas ao longo de dias de blips (deploy do Redis, quedas curtas) chegam no mesmo lugar sem
nenhuma queda longa.

Reprodução real (script descartável no scratchpad, `asyncio.sleep` neutralizado):

```
A) run() raised: OverflowError - int too large to convert to float
```

Conserto: `self._backoff.compute(min(failures, 20))` (20 já satura o cap de 5 s) e/ou envolver o
corpo do `while` num `except Exception` que apenas loga.

### F2 — `wake.py:70-71` (retorno limpo do `_listen_once`) — MÉDIA

O caminho de sucesso não tem atraso nenhum. Em redis-py 8.1, `PubSub.listen()` é
`while self.subscribed:` — ele **termina sem erro** assim que o canal sai de `self.channels`, isto
é, quando o servidor/proxy empurra um `unsubscribe` em vez de fechar o socket. Nesse caso
`_listen_once` retorna, `failures` zera e o `while True` reassina na mesma hora, sem backoff e (no
limite) sem devolver o controle ao event loop.

Cenário: o Redis auto-hospedado de hoje não faz isso, mas um endpoint gerenciado ou atrás de proxy
que desassina assinantes ociosos (prática comum nesses serviços) vira laço quente: medi 50 000
`SUBSCRIBE` em 0,14 s, com os laços de entradas e de saídas famintos no mesmo event loop — no
processo que precisa vender posição aberta. É mina para o dia em que o Redis mudar de endereço.

```
B) 50000 SUBSCRIBE attempts with zero delay and zero yields to the event loop
   elapsed 0.14s
```

Conserto: um `await asyncio.sleep(_BACKOFF_BASE_S)` antes de reassinar também no caminho limpo.

### F3 — `services/meme-worker/hunter_meme_worker/wake.py:34` — MÉDIA-BAIXA

`await runtime.redis.publish(...)` sem timeout próprio, chamado de `lab.py:277-278`, **dentro** do
`lab_tick` e **antes** de `fill_approved`. O orçamento de retry do cliente está documentado no
próprio repo (`packages/core/hunter_core/redis.py:76-84`): teto de ~(4 × 5 s) + 1,5 s ≈ 21 s por
comando.

Cenário: Redis com SYN em buraco negro (rede da VPS, não "connection refused"). Todo tick do radar
que gravou proposta trava ~21 s dentro do `lab_tick`, atrasando os fills e as saídas de papel do
mesmo tick e o próximo ciclo da pista rápida de 15 s. O `try/except` pega o erro, mas só depois dos
21 s. Conserto: `async with asyncio.timeout(1.0):` em volta do publish.

### F4 — `services/meme-executor/hunter_meme_executor/entries.py:339` + `context.py:90-95` — BAIXA (métrica)

A afirmação "uma amostra por proposta, nunca duas — `live_candidates` nunca reoferece uma proposta
que já tem `meme_live_orders`" é falsa no caminho de adiamento: quando a leitura de cadeia falha
(`entries.py:141-148`, `rpc_unreachable`), `handle_candidate` volta **sem escrever linha nenhuma**,
então `_CANDIDATES` (`repo.py:101-108`) reoferece a mesma proposta no tick seguinte e `pickup_lags`
ganha uma amostra nova, cada vez maior.

Cenário: RPC fora por 60 s com um candidato na fila, com o laço em 1 s: ~60 amostras de 1 s a 60 s
dominam a janela de 200 e o heartbeat publica `proposal_pickup_lag_s_p50` ≈ 30 s e `_max` = 60 s,
enquanto a captação real foi instantânea. O operador lê a métrica nova como regressão do T4.52a e
caça fantasma. Conserto: amostrar só quando a proposta vira linha, ou guardar o id já amostrado.

### F5 — expectativa de ganho — `services/meme-executor/hunter_meme_executor/config.py:76` — INFORMATIVO

`loop_s = 1.0` por padrão (e `MEME_LIVE_LOOP_S` não aparece no bloco do serviço em
`infra/docker/docker-compose.yml:679-703`; não li `.env`, por instrução). Com 1 s de tique, a espera
no temporizador só pode responder por ≤ 1 s dos 4,8 s medidos pelo R55. O resto está **dentro** do
`entries_once` (auto-aprovação mais leituras de cadeia serializadas por candidato) e o wake não mexe
nisso: o evento ligado no meio de um passo só é consumido quando o passo termina (`main.py:95-98`,
o laço é serial). Ou seja, "76 % da latência" (mensagem do commit e `docs/RISK_ENGINE_MEME.md` §9)
dificilmente vira 76 % de ganho; o campo novo do heartbeat é justamente quem fecha essa conta depois
do deploy. Não é defeito, é ajuste de expectativa.

### F6 — `wake.py:83` — INFORMATIVO

A leitura bloqueante do pub/sub **opta por sair** do `socket_timeout` de 5 s do cliente (redis-py
8.1 passa `math.inf` em `parse_response(block=True)` — conferido no fonte instalado). Um TCP
meio-aberto (o cenário HIGH-4 que motivou os timeouts em `redis.py:24-60`) deixa o listener
estacionado para sempre, sem exceção e sem reconexão. Não quebra correção (o tique de 1 s segue),
mas o wake morre em silêncio e nenhum campo do heartbeat diz que o listener está vivo.

## Respostas diretas

**1. Duplicidade, dupla admissão ou contexto velho — não.**

- Laço serial: só existe uma task `meme-entries` e `forever` (`main.py:82-98`) só volta a esperar
  depois que `step` terminou; dois wakes não se sobrepõem ao mesmo `entries_once` (o
  `asyncio.Event` colapsa N mensagens em uma).
- Sem wake perdido: `clear()` acontece **depois** da espera e **antes** do passo seguinte
  (`main.py:95-98`), sem ponto de await entre os dois — toda publicação feita durante um passo é
  consumida pelo passo imediatamente seguinte, que refaz a consulta do zero.
- Chave de ordem intacta: `order_key(proposal_id, side='buy')` mais
  `ON CONFLICT (client_order_id) DO NOTHING RETURNING id` (`repo.py:110-117`); `None` faz voltar
  sem assinar (`entries.py:230-231`). `_CANDIDATES` exclui qualquer proposta que já tenha linha de
  compra (`repo.py:105-107`).
- Contexto velho: nada da mensagem vira dado. O payload (`b"1"`) é ignorado; cada tique recompõe
  `now`, refaz `kill.refresh()` e reconsulta o banco. O TTL de 30 s (`MEME_LIVE_APPROVAL_TTL_S`)
  continua sendo a primeira recusa, antes de qualquer leitura de cadeia (`entries.py:113-117`).
- Duas réplicas do executor acordariam juntas, mas essa disputa já existia com o poll de 1 s e o
  guarda continua sendo o `ON CONFLICT` mais o re-check do kill switch antes de assinar.
- Chegar mais cedo não queima proposta: a auto-aprovação já se recusa a abrir sem
  `bundled_share` medido (`risk_snapshot_pending`, T4.28g) e deixa a proposta em `proposed` para o
  tique seguinte, em vez de gravar recusa definitiva.

**2. Falha do listener.** Trava e gira, sim, nos dois caminhos acima (F1 e F2). O temporizador de
reserva em si é garantido (`asyncio.wait_for(..., timeout=interval_s)`, independente do Redis),
**menos** no caso F1, em que o listener derruba o TaskGroup e leva o laço de entradas junto.
Nenhuma fila sem limite: `asyncio.Event` colapsa, `pickup_lags` é `deque(maxlen=200)` e não há
buffer entre listener e laço.

**3. Admissão, kill switch, sizing e simulação: nada muda.** O tique de 10 s do kill switch segue no
seu próprio `forever` sem `wake_event` (`main.py:243-246`), e `entries_once` continua chamando
`kill.refresh()` no topo e de novo antes de assinar. Nenhuma consulta nova por tique: `proposed_at`
entrou no `SELECT` que já existia (`repo.py:98-108`), mesmo `WHERE`, mesmo índice. O custo extra é
um punhado de tiques a mais por minuto (limitado pela cadência do radar), cada um idêntico aos que
já rodavam 1×/s; as leituras sob demanda (`risk_read.py`) seguem com o teto de 1 por mint por 600 s.

**4. `lab_scale_step.py` e `redis_lock.py` são mudanças puras.** Diff mecânico dos corpos contra
`51914d02^`: idênticos (`SCALE_STEP: identical`, `ACQUIRE_LOCK: identical`); a única diferença é o
nome `_scale_step` → `scale_step`. O script Lua de liberação do lock é o mesmo byte a byte.
`acquire_lock` deixou de existir em `hunter_core.redis`; um `grep` no repo inteiro não achou
importador remanescente, então não há `ImportError` de boot em nenhum serviço.

**5. Veredito: SAFE_WITH_FLAG.** Subir com o conserto de F1 (`wake.py:76`, uma linha) — sem ele, um
Redis fora por ~1,5 h derruba o processo que assina e vende na mainnet. F2 e F3 antes do próximo
deploy; F4 antes de confiar no número novo do heartbeat.

## Comandos (saída real)

```
$ uv run pytest services/meme-executor/tests/test_wake.py \
    services/meme-executor/tests/test_forever_wake.py \
    packages/core/tests/unit/test_redis_keys.py -q
14 passed in 3.35s

$ uv run pytest services/meme-executor/tests -q -m unit
144 passed, 59 deselected in 4.84s

$ uv run python <repro do listener, scratchpad>
A) run() raised: OverflowError - int too large to convert to float
B) 50000 SUBSCRIBE attempts with zero delay and zero yields to the event loop
   elapsed 0.14s
```

Os testes de integração (testcontainers) não foram rodados: revisão somente leitura e o Docker desta
máquina já derrubou sessão antes. Nada foi editado no código, nada foi commitado, VPS e `.env*`
intocados.
