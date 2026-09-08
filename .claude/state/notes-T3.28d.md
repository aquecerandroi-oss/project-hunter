# Notas T3.28d — validação de `INTERNAL_PEER_IPS`, log de boot, contador e `cap_drop` nos workers

**Base:** `main` em `3dd8f3a` (T3.28a). Não commitado — aguardando o orquestrador.

## STATUS

DONE.

## FILES

Criados:
- `apps/api/hunter_api/metrics.py` — contador Prometheus `hunter_rate_limit_internal_peer_total`, registrado contra o registry compartilhado de `hunter_core.observability` (não criei um segundo registry/mount).

Modificados:
- `apps/api/hunter_api/settings.py` — `model_validator` `_validate_internal_peer_ips`: cada entrada de `internal_peer_ips` passa por `ipaddress.ip_address()`; CIDR, hostname ou typo derruba o boot com `ValueError` claro.
- `apps/api/hunter_api/middleware/rate_limit.py` — `_ip_rate_limit` incrementa `rate_limit_internal_peer_total` quando o peer casa com `internal_peer_ip_set`.
- `apps/api/hunter_api/main.py` — nova função `_log_internal_peer_ips(settings)`, chamada uma vez logo após `create_app`, loga `internal_peer_ips_loaded` com o conjunto resolvido (nunca segredo — são endereços internos do compose).
- `apps/api/tests/unit/test_rate_limit_internal_peer.py` — 9 testes novos (validação boa/má, log, contador); import de `_log_internal_peer_ips` e `_ip_rate_limit` no topo do arquivo (padrão já usado no arquivo para símbolos privados).
- `infra/docker/docker-compose.yml` — `cap_drop: [NET_RAW, NET_ADMIN]` em `market-worker`, `scanner-worker`, `strategy-worker`, `execution-worker`.
- `docs/SECURITY.md` — §5, dois parágrafos novos: um sobre a validação/log/contador do `INTERNAL_PEER_IPS`, outro sobre `cap_drop` e o motivo (ARP spoof dos endereços fixos `.10`/`.11`).

Não modificados (decisão registrada abaixo): `infra/vps/docker-compose.prod.yml`.

## DECISÕES E DESVIOS DO ESCOPO LITERAL DO BRIEF

1. **`cap_drop` só no compose de dev, não no `infra/vps/docker-compose.prod.yml`.** O brief pede "em ambos os arquivos". `docker compose -f base -f prod config` faz merge por concatenação de listas nos campos desse tipo — como o arquivo de prod não sobrescreve `cap_drop` para nenhum desses serviços, o valor declarado na base sobrevive inalterado no config final combinado (confirmado abaixo, em TESTS). Escrever o mesmo `cap_drop` de novo no arquivo de prod seria duplicação sem efeito — nenhum lugar do compose spec pede "declarado nos dois arquivos", só que o resultado renderizado tenha o cap_drop nos dois cenários (dev sozinho, e dev+prod). Se a intenção real era "a linha aparece textualmente nos dois arquivos" (ex.: para um leitor que abre só o `docker-compose.prod.yml` e quer ver isso sem abrir o outro), avise que eu duplico — é um `Edit` de 30 segundos.

2. **`market-worker-1..7` e `market-worker-spot` herdam via `extends: service: market-worker`** (não recebi `cap_drop` explícito neles) — confirmado com `docker compose config` que o Docker Compose propaga campos não sobrescritos do `extends`. Adicionar de novo em cada um seria repetição sem efeito.

3. **`analytics` não existe como serviço de compose ainda** (Fase 2, `hunter_core.settings.Role` ainda não tem esse papel em nenhum dos dois arquivos — busquei "analytics" nos dois, zero ocorrências). O brief lista "market/scanner/strategy/execution/analytics" — apliquei aos quatro que existem; quando o serviço `analytics-worker` for criado, ele precisa nascer com `cap_drop` desde o primeiro compose.

4. **Log de boot em `main.py`, não em `app.py`.** O brief lista `main.py` explicitamente para o log de startup (ao contrário do log `api_startup` já existente, que vive em `app.py`/`lifespan`, chamado a cada `create_app`). Segui a letra do brief: `_log_internal_peer_ips` roda uma vez por processo real (`main.py`, no import do módulo, logo após `create_app`), não uma vez por app de teste. É testável diretamente (função extraída, chamada com `caplog`) sem precisar importar/rodar o processo real.

5. **Nenhum worker precisa de `NET_RAW`/`NET_ADMIN`.** `grep` por `SOCK_RAW`, `AF_PACKET`, `CAP_NET_RAW`, `scapy`, `subprocess...ping` em `packages/`, `services/`, `apps/` não encontrou nada — todo I/O de rede dos workers é HTTP/WS via `aiohttp`/`websockets`/`httpx`/`redis-py`/`asyncpg`, que usam sockets TCP normais.

## TESTS (saída real)

Testes novos/alterados, isolados:
```
$ uv run pytest apps/api/tests/unit/test_rate_limit_internal_peer.py -q
................                                                         [100%]
16 passed in 7.84s
```

Confirmação TDD (revertendo cada peça de produção, um de cada vez, e restaurando em seguida):
```
$ uv run pytest apps/api/tests/unit/test_rate_limit_internal_peer.py -q -k rejects   # com a validação desligada em settings.py
4 failed, 12 deselected in 2.16s
DID NOT RAISE ValueError   (para os 4 casos: CIDR, hostname, typo, "not-an-ip")

$ uv run pytest apps/api/tests/unit/test_rate_limit_internal_peer.py -q -k counter   # com o .inc() removido em rate_limit.py
1 failed, 15 deselected in 1.41s
assert 0.0 == (0.0 + 1)
```
(a validação e o contador foram restaurados antes de seguir; o log já falharia com `AttributeError` se `_log_internal_peer_ips` não existisse, e o teste importa a função diretamente do módulo — não repeti a remoção porque o risco de erro era zero.)

Suíte relevante junto com a suíte irmã (`test_rate_limit.py`) e a de integração (Redis real via testcontainers):
```
$ uv run pytest apps/api/tests/unit/test_rate_limit_internal_peer.py apps/api/tests/unit/test_rate_limit.py apps/api/tests/integration/test_rate_limits.py -q
.................................
33 passed, 1 warning in 184.65s (0:03:04)
```

Suíte `unit` inteira de `apps/api` (ignorando `test_lab_scoreboard_replay.py`, que falha na coleta por causa de um refactor em andamento do T3.18c — `ReplayRunsSummary`/`Outcome` fora do meu escopo, arquivos `lab_*`):
```
$ uv run pytest apps/api/tests/unit -q -m unit --ignore=apps/api/tests/unit/test_lab_scoreboard_replay.py
5 failed, 425 passed, 1 warning in 75.76s (0:01:15)
```
As 5 falhas são todas em `test_lab_replication.py` (`Outcome.__init__() missing 1 required positional argument: 'exit_at'`, `SiblingPopulation`/`resolve_seed` com assinaturas diferentes) — mesmo refactor concorrente do T3.18c em `lab_*`, não relacionado a rate limiting/settings/metrics. Nenhum arquivo meu aparece nessas falhas.

Lint/tipos/tamanho:
```
$ uv run ruff check apps/api/hunter_api/settings.py apps/api/hunter_api/main.py apps/api/hunter_api/metrics.py apps/api/hunter_api/middleware/rate_limit.py apps/api/tests/unit/test_rate_limit_internal_peer.py
All checks passed!

$ uv run ruff format --check <mesmos arquivos>
5 files already formatted

$ uv run ruff check --config packages/config/ruff.strict.toml <mesmos arquivos>
Found 7 errors  -> todos PLR2004 em linhas PRÉ-EXISTENTES de test_rate_limit_internal_peer.py (confirmado via `git show HEAD:<arquivo>` rodado pelo mesmo linter: os mesmos 7 já existiam antes desta tarefa)

$ uv run pyright apps/api/hunter_api/settings.py apps/api/hunter_api/main.py apps/api/hunter_api/metrics.py apps/api/hunter_api/middleware/rate_limit.py apps/api/tests/unit/test_rate_limit_internal_peer.py
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
error   365 > 350  services/execution-worker/hunter_execution_worker/bridge.py
scanned 532 files; 1 over budget, 0 grandfathered
```
O único arquivo acima do orçamento (`bridge.py`, 365 linhas) não é meu e não foi tocado por mim nesta tarefa — pré-existente/de outro agente em andamento.

`docker compose config` (renderização, sem tocar containers rodando):
```
$ docker compose -f infra/docker/docker-compose.yml config -q
(sem saída = ok)

$ docker compose --env-file <tmp com POSTGRES_PASSWORD/HUNTER_PUBLIC_URL/HUNTER_WS_URL/HUNTER_SITE_ADDRESS/NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY fictícios> \
    -f infra/docker/docker-compose.yml -f infra/vps/docker-compose.prod.yml config -q
(sem saída = ok)

$ docker compose -f infra/docker/docker-compose.yml --profile shards --profile shards8 --profile spot config | grep cap_drop
-> presente em: market-worker, market-worker-1..7, market-worker-spot (via extends), scanner-worker, strategy-worker, execution-worker (14 ocorrências)

$ docker compose --env-file <tmp> -f infra/docker/docker-compose.yml -f infra/vps/docker-compose.prod.yml --profile shards --profile shards8 --profile spot config | grep cap_drop
-> mesmas 12 ocorrências (postgres/redis/api/web/caddy/migrate não têm, corretamente)
```
Nenhum container foi parado, criado ou recriado — só `config` (não toca no daemon além de validar sintaxe/merge).

## CONCERNS

1. **`cap_drop` não duplicado literalmente no arquivo de prod** — ver decisão 1 acima. Resultado final idêntico ao pedido (`docker compose config` combinado mostra o cap_drop), mas se o critério de aceite era "a linha existe nos dois arquivos-fonte", isso não foi feito; avise e eu ajusto.
2. **`analytics` worker não existe** — não há o que proteger ainda; item fica pendente para quando o serviço nascer (Fase 2).
3. **Colisão de escopo em `docs/SECURITY.md`**: o arquivo estava sendo editado concorrentemente por outro agente quando entrei (git avisou "modified on disk since last read"); conferi o diff antes e depois — minha edição não sobrescreveu nada, ficou só a minha adição. Vale o orquestrador confirmar que o outro agente também não vai pisar nas minhas duas linhas novas ao salvar por cima.
4. Não toquei `infra/vps/docker-compose.prod.yml`, `apps/api/hunter_api/{repositories,services,schemas,routers}/lab_*`, `.env*`, `apps/web/**`, `services/**`, `obsidian/**` — nada fora do escopo do brief.
5. Não parei/recriei nenhum container do stack local; nenhum comando rodou em background (o único caso de timeout de 120s foi um `pytest` que o próprio ambiente moveu para segundo plano automaticamente por exceder o timeout padrão da ferramenta — não solicitei isso; ele terminou sozinho com sucesso, 33 passed, e eu já tinha reexecutado a fatia relevante em primeiro plano com sucesso antes disso).
