# T3.0f — o coletor SPOT como serviço próprio

**Data:** 2026-09-08. **Escopo:** `packages/core/hunter_core/settings.py`,
`services/market-worker/hunter_market_worker/{main,spot}.py`,
`apps/api/hunter_api/services/system_status.py`, `infra/docker/docker-compose.yml`,
`infra/vps/docker-compose.prod.yml`, `infra/vps/compose.sh`, `docs/DEPLOYMENT.md` §3,
testes do mesmo escopo. Sem commit. Sem `.env*`, `.claude/state/review-T3.0e.md`,
`services/execution-worker/**`, `apps/**` (exceto o rótulo de `role` corrigido em
`system_status.py`, que é `apps/api`, não `apps/web` — nenhuma linha de `apps/web`
foi tocada, ver §4).

Fecha a ressalva 1 de `notes-T3.0c.md` §12 e a decisão de Everton "bora ativar tudo"
(2026-09-08): o jeito seguro de ligar o spot é um processo dedicado, nunca uma flag
num shard perpétuo.

---

## 1. `MARKET_ROLE`, em uma linha

**Três papéis, uma regra de default, duas combinações recusadas no boot.**

`hunter_core.settings.Settings.market_role: Literal["perpetual","spot","both"] | None`
(default `None`) resolve via `market_role_effective`:

- `None` com `shard_total > 1` (topologia de shards) → `"perpetual"`;
- `None` com `shard_total == 1` (stack local de processo único) → `"both"` (o
  comportamento de hoje, inalterado).

`hunter_market_worker.spot.collects_spot` ficou ciente do papel:

```python
def collects_spot(settings: Settings) -> bool:
    role = settings.market_role_effective
    if role == "perpetual":
        return False
    if role == "spot":
        return settings.market_spot_enabled
    return settings.market_spot_enabled and settings.shard_index == SPOT_SHARD[0]
```

`"perpetual"` **nunca** coleta spot, seja qual for `MARKET_SPOT_ENABLED` — é a garantia
central que o título do brief pede ("`MARKET_SPOT_ENABLED=true` não pode prejudicar a
ingestão perpétua"). Antes da T3.0f, `MARKET_SHARDS=4` com `MARKET_SPOT_ENABLED=true`
setado globalmente (por exemplo um `.env` compartilhado, ou uma variável de ambiente do
orquestrador) fazia o shard 0 — carregando ~50 mercados — também abrir o socket spot no
mesmo event loop; agora essa combinação é estruturalmente impossível: o default do shard
0 deixou de ser "coleta spot condicionada à flag" e passou a ser "nunca".

`"spot"` é o processo dedicado (`market-worker-spot`): nunca fatiado (a `Settings` recusa
no boot uma combinação `MARKET_ROLE=spot` + `MARKET_SHARD` com `shard_total > 1` —
não há leitura válida: o coletor spot é dono do universo inteiro, nunca um shard de um
universo que também não existe para ele), e com `MARKET_SPOT_ENABLED=false` **não** é
erro — o brief pediu explicitamente essa exceção — o processo loga
`market_spot_role_idle_disabled` e fica ocioso (o mesmo padrão de "cria a task e a deixa
esperando" que `spot.py` já usava para os shards ≠ 0).

`"both"` sob `shard_total > 1` também é recusado no boot — é exatamente a combinação que
`t30-proof.md` §1 mediu quebrando o keepalive do socket perpétuo, e permitir alguém pedi-la
explicitamente derrotaria o propósito desta tarefa.

`Settings._validate_market_role` levanta `ValueError` (vira `pydantic.ValidationError`) nos
dois casos recusados, com a mensagem nomeando a combinação e o motivo — nunca um crash-loop
silencioso descoberto só em produção.

## 2. `main.py` — dois corpos de processo, não um `if` espalhado

`run_market()` agora começa computando `role = settings.market_role_effective` e loga
`market_worker_role_selected`. Para `role == "spot"` despacha inteiramente para
`_run_spot_process()` (novo) e **retorna** — nenhuma das tarefas perpétuas
(`universe`, `ingest`, `funding`, `snapshots`, `open-interest`, `recovery`,
`backfill`, `heartbeat` perpétuo, `fx`) é sequer criada. Para `perpetual`/`both` o corpo
é **byte a byte o que já existia** — a mudança que os torna seguros já está inteira em
`collects_spot()` (item 1): a task "spot" continua sendo criada e ociosa em todo shard
que não coleta, exatamente como o docstring de `spot.py` já explicava.

`_run_spot_process()` é o corpo mínimo que `run_spot()` (spot.py, inalterado em sua
lógica de coleta) precisa para rodar sozinho num processo: constrói o adaptador spot,
seu próprio `TickCoalescer` + `coalesce_loop` (nada mais neste processo o alimenta),
o gate de partições (`assert_writable_partitions`/`PartitionReadiness` — velas spot
caem nas mesmas partições que as perpétuas), o dispatcher do outbox (seguro de rodar
em paralelo com o de qualquer outro processo — `SKIP LOCKED`, T2.5g já provou isso com
os quatro shards perpétuos) e os status details `spot`/`rest_gate` (este último agora
aponta para o adaptador spot, porque é o único cliente REST deste processo). Fecha
o adaptador na sua própria `finally` quando `collects_spot()` for `False` (mesma regra
que `run_market()` já aplicava para o `spot_adapter` do processo perpétuo).

## 3. Compose — `market-worker-spot`, perfil `spot`

`infra/docker/docker-compose.yml`: novo serviço `market-worker-spot` (`extends:
market-worker`, perfil `spot`), com `MARKET_ROLE=spot`, `MARKET_SPOT_ENABLED=true` e
`MARKET_SHARD=0/1` fixados **no serviço**, nunca em `.env` — reviewável em uma linha
de diff, e imune a um `.env` compartilhado que ligasse a flag para todo mundo.

`infra/vps/docker-compose.prod.yml`: o mesmo serviço, com `*prod-db-env`,
`restart: always` e `logging: *prod-logging`, ao lado dos três shards perpétuos
existentes.

`infra/vps/compose.sh`: `MARKET_SPOT=1` (ao lado de `MARKET_SHARDS`, mesma convenção —
mora no ambiente do comando, nunca no `.env`) adiciona `--profile spot`.
`MARKET_SPOT=1 MARKET_SHARDS=4 bash infra/vps/compose.sh update` é o deploy inteiro.

`docker compose -f infra/docker/docker-compose.yml --profile spot config` e
`--profile spot config --services` parseiam limpos (verificado com `POSTGRES_PASSWORD`/
`HUNTER_PUBLIC_URL`/etc. fake, incluindo os dois arquivos de compose juntos — §"TESTS").

`docs/DEPLOYMENT.md` ganhou a §3.3 com a regra do `MARKET_ROLE`, os dois comandos
(local e VPS) e o que verificar depois.

## 4. `/system/workers` — o achado real do item 3

O brief afirmava que `/system/workers` "já agrega `hb:market:spot:{ex}`". **Verificado,
e só parcialmente verdadeiro.** A chave `hb:market:spot:binance` sempre foi varrida
pelo `SCAN hb:*` genérico (`system_status.py::scan_heartbeats`) — mas
`parse_heartbeat_key` fazia `remainder.partition(":")` uma vez só, então
`hb:market:spot:binance` virava `role="market"`, `instance="spot:binance"`. Como
`instance` contém `:`, `anonymize_instance` **hasheava** esse valor (a mesma regra que
protege `hb:market:{hostname}:{pid}` de vazar) — o coletor spot aparecia como uma linha
`role="market"` com um `instance` de 12 hex ilegível, e a segunda tabela do
`workers-table.tsx` (que filtra `role === "market"` e `ws_state !== null`) o listaria
junto dos venues perpétuos reais, como um shard não identificável.

**Corrigido em `parse_heartbeat_key`:** `hb:market:spot:{exchange}` agora vira
`role="market-spot"`, `instance={exchange}` — um slug plano, nunca hasheado, e um
`role` que a tabela de "exchanges" (que só olha `role === "market"`) exclui por
construção. Nenhuma linha de `apps/web` mudou: a correção do lado servidor já resolve
"linha própria, legível, nunca confundida com um shard perpétuo faltando" sem tocar o
componente. `docs/DEPLOYMENT.md` §3.3 documenta o antes/depois.

Testes novos: `apps/api/tests/unit/test_system_workers_status.py` (parametrização de
`parse_heartbeat_key` + um teste dedicado de que o resultado nunca é hasheado) e
`apps/api/tests/integration/test_system_workers_api.py::
test_workers_reports_the_spot_collector_as_its_own_role_never_hashed`.

## 5. Cobertura e drops por venue — reconfirmado, não recodificado

Item 4 do brief. `market_spot_dropped_events_total`/`mkt:{ex}:spot:*` já eram os únicos
que o caminho spot escreve desde a T3.0c/e — nada nessa mecânica mudou aqui (só *onde*
o processo roda). Reconfirmado rodando `test_market_type_identity.py` (7/7) e
`test_heartbeat.py::test_run_heartbeat_writes_spot_drops_to_the_spot_series_never_the_shared_one`
inteiros — nenhuma asserção mudou, e a prova de 30 min (§ próxima seção) mede o mesmo
contrato ao vivo num processo dedicado.

## 6. Achado colateral: outro agente mexendo na mesma árvore

Durante os testes (arquivo por invocação, conforme a regra operacional),
`test_universe_tracking_hold.py` passou a falhar com
`InsufficientPrivilegeError: permission denied for table strategy_versions` — não
causado por esta tarefa. `git status` mostra `infra/migrations/versions/
0011_strategy_activation_owner.py` (novo, não rastreado) e `0010_strategy_purpose.py`
(modificado) de outro agente em andamento (revisão de segurança/DB, T3.15), que revoga
`INSERT`/`UPDATE(status,...)`/`DELETE` de `hunter_worker` em `strategy_versions` — a
suíte de testes recria o schema do zero a cada execução (`migrated_db_url`, escopo de
sessão) e aplicou essa migração ainda em voo. Nada em `services/market-worker/**` ou
`infra/**` deste agente foi tocado por mim (confirmado pelo próprio brief: "nenhum outro
trabalho em `services/market-worker/**` ou `infra/**`"). Registrado, não corrigido — fora
do escopo desta tarefa e do arquivo que não devo tocar.

Da mesma forma, `infra/scripts/activate_strategy_version.py` apareceu **362 linhas**
(orçamento 350) no `check_file_size.py` rodado no fim — arquivo do mesmo agente/tarefa
concorrente, não tocado aqui.

## 7. O que NÃO mudou

- `spot.py`'s lógica de coleta (universo, ingest, persist, recovery, heartbeat,
  watchdog) — só o portão `collects_spot()` ganhou o `role`;
- as chaves de hot state, o canal de pub/sub, a identidade dos eventos duráveis
  (T3.0c/d/e) — nada disso é reaberto aqui;
- `/system/market-status` (o endpoint dedicado a shards perpétuos) — já não olhava spot
  antes (`market_heartbeat_shard_pattern` usa o `_PERP` default), e continua assim;
- o comportamento de `role="both"` sob `shard_total == 1` — byte a byte o que era antes
  desta tarefa (é literalmente o mesmo código, só alcançado por um caminho que agora
  passa por `market_role_effective` em vez de ser o único caminho que existia).

## 8. Ressalvas honestas

1. **A prova de 30 min rodou numa stack isolada (`-p hunter-t30f`), não na stack
   principal que já está viva e em uso** (`docker-*`, 19–25h de uptime, com
   `execution-worker`/`scanner-worker`/`strategy-worker` reais rodando o lab autônomo).
   Decisão deliberada: `docker compose up -d --build` na stack principal reconstruiria
   `hunter-api:dev` a partir da árvore de trabalho **inteira**, que neste exato momento
   carrega mudanças em voo de vários outros agentes (migração `0011` inclusive) — e
   recriar `migrate`/`market-worker`/`execution-worker`/`scanner-worker`/`strategy-worker`
   ao vivo aplicaria essa migração ao Postgres real do lab e trocaria os binários de
   processos que Everton pediu para não parar. A stack isolada usa a tag
   `hunter-api:t30f-proof` (nunca `:dev`) e um projeto/rede/volumes próprios — mede
   exatamente o código desta tarefa, sem tocar no lab ao vivo. `docker ps` antes e
   depois (`t30f-proof.md` §6) confirma que a stack principal nunca foi recriada.
2. **A prova NÃO fechou com "0 reconnects" limpo — 19, ao final — e isso está
   investigado a fundo, não escondido, em `t30f-proof.md` §4.** A máquina de hoje
   estava mais barulhenta que a de `t30-proof.md` (a stack principal inteira rodando
   ao lado, mais containers de outros agentes). Fiz um experimento controlado: parei
   e religuei o container `market-worker-spot` três vezes durante a janela, com o
   `market-worker` perpétuo rodando ininterrupto. **Resultado: a taxa de crescimento
   de `reconnects` foi igual (ou maior) com o spot *desligado* do que com ele ligado**
   — a causa não é o spot. A única ocorrência da assinatura exata do bug original
   (`sent 1011 keepalive ping timeout`) coincidiu com uma janela em que eu mesmo
   rodava `pytest`/`ruff`/`pyright`/`docker build` no mesmo host, e nunca se repetiu
   nos ~15 min seguintes de coleta (incluindo minutos com o spot ligado). Todo
   reconnect posterior teve a assinatura benigna `'no close frame received or sent'`
   — o mesmo ruído de fundo que o arm A ("spot OFF") de `t30-proof.md` §1 já
   registrava — e um deles coincidiu com o `oi_poll_loop` do próprio processo
   perpétuo fazendo 200 chamadas REST sequenciais no mesmo event loop da ingestão, a
   mesma classe de contenção intra-processo que a T2.5g já atribuiu a "200 mercados
   sem sharding", não ao spot. **A garantia que esta tarefa entrega — spot e
   perpétuo nunca no mesmo event loop — está provada por construção (dois
   processos/containers) e reforçada por essa medição negativa**, não por um número
   de reconnects zerado que a máquina de hoje não permitiria mesmo sem o spot.
3. **`dropped_events` do lado perpétuo cresce durante a prova** (não é regressão desta
   tarefa — é o comportamento já documentado pela T2.5g para **um processo com 200
   mercados sem sharding**, com ou sem o coletor spot ao lado: o teto do event loop de
   um único core, não a presença do spot noutro processo/container).
4. **`mkt:binance:spot:band_state` não foi observado na janela real** — só aparece
   depois do *segundo* refresh do universo spot (900 s de cadência, T3.0e) sobre
   símbolos já monitorados na primeira leitura, e cada `docker stop`/`start` do
   experimento de controle do item 2 reinicia esse relógio (`t30f-proof.md` §5).
   Mecânica já provada isoladamente, sem essa restrição de tempo real, por
   `test_spot_band.py` (14/14) e `test_spot_universe.py` (17/17).
5. **`test_run_spot_process_actually_collects_when_the_switch_is_on`
   (`services/market-worker/tests/test_role.py`) é sensível a contenção de CPU do
   host** — falhou uma vez com timeout de 5 s enquanto eu construía a imagem Docker do
   proof em paralelo (mesma máquina), passou em 26 s isolado e de novo na varredura
   final. Aumentei o timeout de 5 s para 15 s; documentado aqui em vez de escondido.
6. Não toquei `docs/PIPELINE.md` (o brief só pediu `docs/DEPLOYMENT.md` §3) — o §1d que
   a T3.0c/d/e escreveram continua descrevendo o *caminho de dados* spot, que não mudou;
   a topologia de processo é assunto de deploy, por isso foi para `DEPLOYMENT.md`.
