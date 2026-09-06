# Shadow Lab na VPS — prova operacional (2026-09-06)

**Janela:** 2026-09-06 03:29 → 04:47 UTC (≈ 1 h 18 min), VPS `vmi3483069`, stack
`infra/vps/compose.sh` (`docker-compose.yml` + `docker-compose.prod.yml`), imagem
`hunter-api:75fc59c`, contra a Binance real.

Tudo abaixo é saída real de comando. Nada aqui é estimativa.

## 0. Dois bloqueios encontrados no caminho (e o que cada um significa)

### 0.1 O `strategy-worker` subia com a senha de desenvolvimento — corrigido (`75fc59c`)

Na primeira `compose.sh update` o serviço subiu e entrou em loop de restart:

```
$ docker logs hunter-strategy-worker-1 --tail 40
...
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "hunter"

$ docker exec hunter-strategy-worker-1 python infra/scripts/activate_strategy_version.py --help
Error response from daemon: Container 49dd1f4e... is restarting, wait until the container is running
```

**Causa.** A S2 acrescentou o serviço a `infra/docker/docker-compose.yml`, mas **não** a
`infra/vps/docker-compose.prod.yml`, e o override não herda o que não menciona: na VPS o
`strategy-worker` ficava com o `x-api-env` de desenvolvimento em vez do `*prod-db-env`. `api`,
`migrate` e `market-worker` não mostravam nada porque cada um tem o seu bloco lá — o Lab era o
único serviço novo sem o dele.

**Correção** (commit `75fc59c`): bloco `strategy-worker` no override, com `<<: *prod-db-env`,
`HUNTER_ROLE: strategy`, `HEALTH_PORT: "8001"`, `restart: always` e `logging: *prod-logging`.

### 0.2 A VPS nunca tinha rodado o seed de dados de referência

```
$ docker exec hunter-strategy-worker-1 python infra/scripts/activate_strategy_version.py momentum v1 --dry-run
REFUSED: no strategy_version for momentum v1 (run infra/scripts/seed.py first)

$ psql -c "select (select count(*) from exchanges) exchanges, (select count(*) from strategies) strategies,
           (select count(*) from strategy_versions) versions, (select count(*) from feature_definitions) features,
           (select count(*) from markets) markets, (select count(*) from candles) candles;"
 exchanges | strategies | versions | features | markets | candles
-----------+------------+----------+----------+---------+---------
         1 |          0 |        0 |        0 |     526 |  367256
```

O bootstrap da VPS roda `migrate` e nunca `seed`: 526 mercados e 367 mil velas coletados, e **zero**
linhas de `strategies`, `strategy_versions` e `feature_definitions`. Rodado com o comando de
imagem já existente no entrypoint (`HUNTER_COMMAND=seed`), que é idempotente e só escreve dado de
referência:

```
$ bash infra/vps/compose.sh run --rm -e HUNTER_COMMAND=seed --entrypoint /app/infra/docker/entrypoint.sh migrate
seeded   2 row(s) into exchanges
seeded   8 row(s) into strategies
seeded   8 row(s) into strategy_versions
seeded  36 row(s) into plan_entitlements
seeded   7 row(s) into feature_flags
seeded   3 row(s) into risk_profiles
seeded  28 row(s) into feature_definitions
seeded   2 row(s) into opportunity_weights
```

**E aqui a revisão da Astra derrubou a minha recomendação óbvia.** Eu ia pedir para pôr o `seed` no
`compose.sh update`. Ela apontou que `seed.py` faz `on_conflict_do_update(set_={"code_ref": ...})`
em `strategy_versions`, substituindo o `code_ref` pelo placeholder — e a trigger de congelamento
recusa isso em qualquer linha já ativada, com o seed inteiro numa transação só. Testei o cenário na
própria VPS, depois da ativação:

```
$ bash infra/vps/compose.sh run --rm -e HUNTER_COMMAND=seed --entrypoint /app/infra/docker/entrypoint.sh migrate
sqlalchemy.exc.DBAPIError: asyncpg.exceptions.RaiseError:
  strategy_versions 01a074c5-8f1d-7a75-a88b-2badb6a5dd67 is frozen after activation: code_ref cannot change
HINT:  create a new strategy_version; status, changelog and deprecated_at stay mutable
[SQL: INSERT INTO strategy_versions (strategy_id, version, status, code_ref, id) VALUES (...)
      ON CONFLICT (strategy_id, version) DO UPDATE SET code_ref = excluded.code_ref RETURNING strategy_versions.id]
[parameters: (..., 'v1', 'draft', 'hunter_indicators.strategies.momentum_v1', ...)]
```

**O `seed` não é idempotente depois da primeira ativação: ele falha e reverte a transação inteira**
— todas as oito tabelas. Colocá-lo no `compose.sh update` quebraria o próximo deploy desta VPS.
O rollback funcionou (nada corrompido):

```
      key       | version | status |         activated_at          | code_ref
----------------+---------+--------+-------------------------------+-----------------------------------
 momentum       | v1      | active | 2026-09-06 03:36:36.988581+00 | hunter_core.strategies.momentum_v1@sha256:6ccbe8b6c8ac1
 volume_anomaly | v1      | active | 2026-09-06 03:36:47.845595+00 | hunter_core.strategies.volume_anomaly_v1@sha256:a03d18f

 strategies | versions | features | weights | weights_ativos
------------+----------+----------+---------+----------------
          8 |        8 |       28 |       2 |              1
```

**Fica aberto, com a correção certa agora conhecida:** o `seed` precisa **preservar** o `code_ref` de
versões já ativadas (não sobrescrever), com teste `seed → ativação → seed`, **antes** de entrar em
qualquer fluxo de deploy. Registrado como HIGH em `obsidian/07-BUGS/Open Bugs.md`.

**Uma ressalva de honestidade sobre este seed:** não medi `opportunity_weights` antes de rodar. O
código insere o que falta, verifica o que existe e recusa divergência, mas promove `is_active` na
corrida que **cria** o perfil da release — como não há contagem anterior, não posso afirmar que
nenhuma linha preexistente mudou de estado. A leitura de depois é `weights = 2`, `is_active = 1`.

## 1. `compose.sh update` — migração 0003 aplicada e o Lab no ar

```
$ cd /opt/project-hunter && bash infra/vps/compose.sh update
 Image hunter-api:75fc59c Built
 Image hunter-web:75fc59c Built
 Container hunter-migrate-1 Exited
 Container hunter-strategy-worker-1 Started
NAME                       IMAGE                SERVICE           STATUS
hunter-api-1               hunter-api:75fc59c   api               Up (healthy)
hunter-caddy-1             caddy:2-alpine       caddy             Up 5 hours
hunter-market-worker-1     hunter-api:75fc59c   market-worker     Up (healthy)
hunter-postgres-1          postgres:16-alpine   postgres          Up (healthy)
hunter-redis-1             redis:7-alpine       redis             Up (healthy)
hunter-strategy-worker-1   hunter-api:75fc59c   strategy-worker   Up (healthy)
hunter-web-1               hunter-web:75fc59c   web               Up (healthy)

$ psql -c "select version_num from alembic_version;"
  version_num
---------------
 0003_analysis
```

## 2. Ativação auditada (sem `--supersede`: não havia linha ativada antes)

Ensaio primeiro, nada escrito:

```
$ docker exec hunter-strategy-worker-1 python infra/scripts/activate_strategy_version.py momentum v1 --changelog "S4 dry run VPS" --dry-run
would activate momentum v1 with code_ref hunter_core.strategies.momentum_v1@sha256:6ccbe8b6c8ac18f32e93a6d44e71e0045155646479907b2b1944f39c3cdf4c95 (19 parameters)

$ ... volume_anomaly v1 ... --dry-run
would activate volume_anomaly v1 with code_ref hunter_core.strategies.volume_anomaly_v1@sha256:a03d18fece9e0052756aadd16a60d9af8d97de279bdf79804d2cbde098fc496a (14 parameters)
```

Ativação real:

```
$ ... activate_strategy_version.py momentum v1 --changelog "S4: primeira ativacao do Shadow Lab na VPS (2026-09-06)"
activated momentum v1 at 2026-09-06T03:36:36.988581+00:00 with code_ref hunter_core.strategies.momentum_v1@sha256:6ccbe8b6c8ac18f32e93a6d44e71e0045155646479907b2b1944f39c3cdf4c95

$ ... activate_strategy_version.py volume_anomaly v1 --changelog "S4: primeira ativacao do Shadow Lab na VPS (2026-09-06)"
activated volume_anomaly v1 at 2026-09-06T03:36:47.845595+00:00 with code_ref hunter_core.strategies.volume_anomaly_v1@sha256:a03d18fece9e0052756aadd16a60d9af8d97de279bdf79804d2cbde098fc496a
```

```
      key       | version | status |         activated_at          | params_format |                                     code_ref
----------------+---------+--------+-------------------------------+---------------+------------------------------------------------------------------------------
 momentum       | v1      | active | 2026-09-06 03:36:36.988581+00 |             1 | hunter_core.strategies.momentum_v1@sha256:6ccbe8b6c8ac18f32e93a6d44e71e00451...
 volume_anomaly | v1      | active | 2026-09-06 03:36:47.845595+00 |             1 | hunter_core.strategies.volume_anomaly_v1@sha256:a03d18fece9e0052756aadd16a60...
(2 rows)
```

Trilha de auditoria em `system_events` — inclusive a **recusa**, que é o ponto do script
("an experiment whose start nobody can date is not an experiment"):

```
          created_at           |  level  |                event                |  message
-------------------------------+---------+-------------------------------------+----------------------------------------------------------------
 2026-09-06 03:36:47.845595+00 | info    | strategy_version_activated          | volume_anomaly v1 activated with code_ref=...a03d18fe... params_format=1: S4: primeira ativacao do Shadow Lab na VPS (2026-09-06)
 2026-09-06 03:36:36.988581+00 | info    | strategy_version_activated          | momentum v1 activated with code_ref=...6ccbe8b6... params_format=1: S4: primeira ativacao do Shadow Lab na VPS (2026-09-06)
 2026-09-06 03:30:09.078298+00 | warning | strategy_version_activation_refused | no strategy_version for momentum v1 (run infra/scripts/seed.py first)
```

O worker reconheceu as duas sem reinício (cache de versões, TTL 60 s):

```
{"versions": ["momentum:v1", "volume_anomaly:v1"], "event": "shadow_active_versions",
 "role": "strategy", "level": "info", "timestamp": "2026-09-06T03:37:01.639039Z"}
```

## 3. `/ready` — 200 com as seis checagens

```
$ docker exec hunter-strategy-worker-1 python -c "import urllib.request,sys; r=urllib.request.urlopen(sys.argv[1],timeout=25); print(r.status, r.read().decode())" http://localhost:8001/ready
200 {"database":true,"redis":true,"shadow_migration":true,"shadow_versions":true,"shadow_consumer":true,"shadow_outbox":true}
```

Quatro delas são as do Lab (`shadow_migration`, `shadow_versions`, `shadow_consumer`,
`shadow_outbox`); `database` e `redis` são do runtime base.

**Cuidado com o que `shadow_versions` verde significa** (correção da revisão da Astra): a checagem
fica falsa quando existem linhas `active` e **nenhuma** executável — ela pega o caso do `code_ref`
quebrado, que era o objetivo. Mas verde **não** prova catálogo executável não vazio (zero versões
ativas também passa) nem que *todas* as versões ativas rodam: uma válida esconde outra recusada.
Cenário: um deploy perde uma estratégia e o `/ready` continua verde. A evidência boa de que as duas
estão rodando são os **sinais por estratégia** da seção 5, não esta checagem.

## 4. Heartbeat e primeiras avaliações

Primeira passada, minutos depois da ativação (fechamento de 5 min das 03:40):

```
$ docker exec hunter-redis-1 redis-cli HGETALL hb:strategy:shadow
ts                    2026-09-06T03:40:11.196912+00:00
instance              42244c7e039c:1
cohort                prospective
evaluated_bars        85
evaluations_by_state  {"not_triggered":77,"triggered":8}
errors                0
outbox_pending        0
outbox_lag_s          0.0
open_trackings        8
last_iteration        2026-09-06T03:40:11.124979+00:00
```

Cinco minutos depois, já com o fechamento de 15 min do `momentum`:

```
ts                    2026-09-06T03:45:11.408335+00:00
evaluated_bars        315
evaluations_by_state  {"not_triggered":286,"triggered":29}
errors                0
open_trackings        25
```

**Zero `unavailable`** — a diferença mais importante em relação à máquina local, onde o buraco de
coleta de 02:04 a 02:47 UTC deixou 400 de 401 avaliações recusadas. Aqui o `market-worker` está de
pé há horas e a janela contígua existe, então a estratégia consegue agregar.

Chaves de heartbeat presentes: `hb:strategy:shadow`, `hb:strategy:42244c7e039c:1`,
`hb:market:binance`, `hb:market:4b6ad9f1238c:1`.

## 5. `shadow_episodes` avançando, sinais e acompanhamentos (snapshot de 04:46:50 UTC)

```
--- sinais por versao ---
      key       | version | sinais | research_only | prospective | mercados |           primeiro            |            ultimo
----------------+---------+--------+---------------+-------------+----------+-------------------------------+-------------------------------
 momentum       | v1      |     42 |            42 |          42 |       42 | 2026-09-06 03:45:01.540802+00 | 2026-09-06 04:45:31.341635+00
 volume_anomaly | v1      |     67 |            67 |          67 |       49 | 2026-09-06 03:40:04.45381+00  | 2026-09-06 04:45:34.193302+00
(2 rows)
```

**109 sinais, 109 com `purpose = research_only` e `cohort = prospective` — sem exceção.**

```
--- acompanhamentos ---
      key       | tracking_state |   result    | count | com_entrada | com_r
----------------+----------------+-------------+-------+-------------+-------
 momentum       | pending_entry  | open        |     7 |           0 |     0
 momentum       | active         | open        |     8 |           8 |     0
 momentum       | terminal       | target      |     7 |           7 |     5
 momentum       | terminal       | stop        |    12 |          12 |    10
 momentum       | terminal       | invalidated |     8 |           8 |     4
 volume_anomaly | pending_entry  | open        |    12 |           0 |     0
 volume_anomaly | active         | open        |    11 |          11 |     0
 volume_anomaly | terminal       | target      |    10 |          10 |     6
 volume_anomaly | terminal       | stop        |    15 |          15 |    14
 volume_anomaly | terminal       | invalidated |    18 |          18 |    12
 volume_anomaly | no_entry       | open        |     1 |           0 |     0
(11 rows)

--- motivos de exclusao ---
  motivo  | count
----------+-------
 geometry |     1
(1 row)

--- episodios (slots) ---
      key       | slots | armados | segurando
----------------+-------+---------+-----------
 momentum       |   203 |     186 |        15
 volume_anomaly |   203 |     177 |        23
(2 rows)
```

Os slots avançam: 203 por estratégia (mercados avaliados), 15 e 23 segurando um acompanhamento
aberto — exatamente os `open_trackings` do heartbeat. Nenhuma censura por gap nesta janela.

## 6. Outbox e stream

```
$ psql -c "select count(*) total, count(dispatched_at) dispatched, count(*) filter (where dispatched_at is null) pending, max(attempts), count(last_error) from shadow_outbox;"
 total | dispatched | pending | max_attempts | erros
-------+------------+---------+--------------+-------
   109 |        109 |       0 |            1 |     0

$ docker exec hunter-redis-1 redis-cli XLEN shadow.signals.emitted
41      (medido às 03:45, quando havia 41 sinais; a contagem acompanha os sinais um a um)
```

Uma tentativa por evento, nenhum erro, nenhuma pendência.

**O que isto prova e o que não prova** (correção da revisão da Astra): prova que o despachante
esvaziou a fila sem reter nada e sem erro. **Não** prova "nada perdido" — o `XLEN` foi lido às 03:45,
com 41 sinais, e os 109 despachos são do snapshot de 04:46; contagens iguais em instantes diferentes
também poderiam esconder um evento duplicado e outro ausente. Para afirmar entrega exata seria
preciso reconciliar as **identidades** (sinal, linha de outbox, evento) de uma população delimitada
— e a entrega é idempotente por desenho justamente porque pode repetir depois de um crash.

## 7. `R_net` nulo com motivo — e um motivo que pode estar errado

```
$ psql -c "select (meta->>'r_net_reason') as r_net_reason, (meta->'funding'->>'reason') as funding_reason,
           count(*) as outcomes, count(*) filter (where meta->>'r_ex_funding' is not null) as com_r_ex_funding
           from signal_outcomes where tracking_state='terminal' group by 1,2 order by 3 desc;"
               r_net_reason                |              funding_reason               | outcomes | com_r_ex_funding
-------------------------------------------+-------------------------------------------+----------+------------------
                                           |                                           |       51 |               51
 funding_missing:2026-09-06T04:00:00+00:00 | funding_missing:2026-09-06T04:00:00+00:00 |       18 |               18
 funding_ambiguous_exit                    | funding_ambiguous_exit                    |        1 |                1

$ psql -c "select count(*) linhas, count(distinct market_id) mercados, min(funding_time), max(funding_time) from funding_rates;"
 linhas | mercados |            min             |            max
--------+----------+----------------------------+----------------------------
   1472 |      208 | 2026-09-04 23:00:00.007+00 | 2026-09-06 04:00:00.005+00
```

**19 dos 70 acompanhamentos encerrados têm `R_net = NULL`, cada um com o motivo escrito**, e em todos
os 19 `meta.r_ex_funding` está preservado como métrica separada. O comportamento conservador está
certo — **nunca zero inventado**, item 3 da decisão conjunta — e é uma população que a janela local
(com funding completo e horizontes curtos) não produziu. Qualquer avaliação datada sobre a VPS tem
de contar essas 19 fora dos "encerrados avaliáveis".

**Mas o motivo pode estar errado, e isso é um achado, não uma nota de rodapé.** A revisão da Astra
apontou que `hunter_strategy_worker/funding.py` trunca o intervalo para segundos inteiros, projeta
uma grade de liquidações e exige **correspondência exata de timestamp**. O histórico desta VPS tem
`max(funding_time) = 2026-09-06 04:00:00.005+00` — cinco milissegundos depois da grade. Cenário
concreto: histórico às 02:00:00, 03:00:00 e 04:00:00.005; entrada às 03:30, saída às 04:30; a
cadência calculada é 3600 s, a grade exige `04:00:00`, a liquidação real **existe** em
`04:00:00.005`, a busca exata falha e o outcome recebe `funding_missing:04:00:00`.

Isso **não prova** que explica os 18 casos — não cruzei outcome a outcome com o histórico por
mercado. Mas impede classificá-los como ausência legítima de dado. Enquanto não houver esse
cruzamento, a leitura correta é: **19 outcomes com `R_net` desconhecido, dos quais 18 podem ser
falso `funding_missing` por identidade de liquidação frágil**. Registrado em
`obsidian/07-BUGS/Open Bugs.md`; a correção passa por definir a identidade da liquidação preservando
o timestamp original, em vez de exigir igualdade com uma grade calculada.

## 8. Saúde da máquina

```
$ docker ps --format "{{.Names}}\t{{.Status}}"
hunter-strategy-worker-1	Up About an hour (healthy)
hunter-market-worker-1	Up About an hour (healthy)
hunter-api-1	Up About an hour (healthy)
hunter-web-1	Up About an hour (healthy)
hunter-postgres-1	Up 6 hours (healthy)
hunter-redis-1	Up 6 hours (healthy)
hunter-caddy-1	Up 6 hours

$ docker stats --no-stream --format "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
hunter-strategy-worker-1	0.66%	80.89MiB / 47.05GiB
hunter-market-worker-1	100.56%	289MiB / 47.05GiB
hunter-api-1	0.09%	98.01MiB / 47.05GiB
hunter-postgres-1	0.20%	175.4MiB / 47.05GiB
hunter-redis-1	0.40%	188.7MiB / 47.05GiB

$ docker logs hunter-strategy-worker-1 2>&1 | grep -cE "Traceback|Exception|\[error"
0

$ psql -c "select (select count(*) from markets) mercados, (select count(*) from candles) velas,
           (select max(open_time) from candles) ultima_vela,
           (select count(*) from ingestion_gaps where status='open') gaps_abertos, now();"
 mercados | velas  |      ultima_vela       | gaps_abertos |             agora
----------+--------+------------------------+--------------+-------------------------------
      526 | 385372 | 2026-09-06 04:45:00+00 |            2 | 2026-09-06 04:46:50.331621+00

$ uptime; df -h /
 05:10:31 up  4:02,  1 user,  load average: 1.13, 1.16, 1.15
/dev/sda1       348G   18G  330G   6% /
```

**O custo do Lab é desprezível: 0,66% de um core e 81 MB.** O que consome a máquina é o
`market-worker` a 100,56% de um core — é a saturação já medida no M1 com o universo padrão de 200
mercados (a VPS não usa o override de 50 do dev box). Vela atual, 2 gaps abertos, disco em 6%.

## 9. O que esta prova NÃO mostra

- **Nenhuma avaliação datada de experimento foi escrita sobre a VPS.** `EXP-0001` e `EXP-0002`
  descrevem a população **local**, com o `params_hash` local e os `code_ref` locais. A VPS é uma
  **terceira e quarta coorte de versão** (`momentum v1` e `volume_anomaly v1` com `code_ref`
  diferente e `activated_at` próprio) e vai virar avaliação datada no próximo plantão, com o mesmo
  SQL e as 19 exclusões de funding contadas.
- **Censura por gap** não ocorreu nesta janela (2 gaps abertos, nenhum tocando um acompanhamento).
- **`tracking_hold`** não foi exercitado: nenhum mercado com acompanhamento aberto saiu do universo
  em 1 h 18 min.
- **1 h 18 min e 70 outcomes encerrados** estão muito abaixo do limiar editorial (100 outcomes
  avaliáveis **E** 30 dias distintos). Nada aqui é performance de estratégia: são contagens de
  funcionamento.

## 10. Achado grave levantado por esta subida — o `code_ref` não é portável entre Windows e Linux

Os digests da VPS **não** batem com os locais para o mesmo commit:

| | local (Windows) | VPS (Linux) |
|---|---|---|
| `momentum_v1` | `...@sha256:c012f75cdd8492d3...` | `...@sha256:6ccbe8b6c8ac18f3...` |
| `volume_anomaly_v1` | `...@sha256:d8275427c958743b...` | `...@sha256:a03d18fece9e0052...` |

Investigado até a causa, com os dois lados no mesmo commit e ambos com `git status` limpo em
`packages/core/hunter_core/strategies/`:

```
$ git hash-object packages/core/hunter_core/strategies/base.py    # local  -> 53a7b1bf0e7b7ae1...
$ ssh hunter-vps 'git hash-object .../base.py'                    # VPS    -> 53a7b1bf0e7b7ae1...   (IGUAL)

$ wc -c .../base.py           # local 14095   VPS 13757   (diferença: 338)
$ wc -l .../base.py           # 338 linhas
$ tr -cd '\r' < .../base.py | wc -c    # local: 338   (CRLF em todas as linhas)
```

O blob do Git é idêntico (`core.autocrlf=true` + `.gitattributes` normalizam na entrada), mas os
**bytes em disco** diferem: quatro arquivos do fecho de imports (`base.py`, `aggregate.py`,
`indicators.py`, `envelope.py`) estão em CRLF na árvore de trabalho do Windows e em LF na VPS.
O `code_ref` é o digest desses bytes.

**Cenário de falha:** ativar uma versão a partir do dev box contra o banco de produção (ou restaurar
um dump com versões congeladas no Windows e rodá-las na VPS) faz `load_active_versions` recusar
**todas** com `shadow_version_code_ref_mismatch`. Com a correção da S2 o `/ready` fica vermelho em
vez de mentir — mas **readiness falsa não reinicia container nenhum**: `restart: always` reage à
*saída* do processo, e neste caminho o worker continua de pé, consumindo e recusando avaliar (a
afirmação anterior, de que o container entraria em restart, era minha e estava errada; correção da
revisão da Astra). Ou seja: não é silencioso para quem olha o `/ready`, mas é silencioso para quem
espera autocura. E campo congelado não se corrige no lugar: só `--supersede`, encerrando a coorte.

Hoje não morde porque cada ambiente ativou as suas próprias linhas. Registrado como HIGH em
`obsidian/07-BUGS/Open Bugs.md`.

**Confirmação independente (Astra, `.claude/state/astra-review-S4-vps-lab.md`).** Ela reproduziu a
composição do digest em memória e fechou o diagnóstico: converter só CRLF → LF nos arquivos locais
devolve **exatamente** os hashes da VPS, que por sua vez são iguais aos dos blobs do commit.

```
momentum_v1        raw: c012f75cdd8492d3...   lf: 6ccbe8b6c8ac18f3...   git_blob: 6ccbe8b6c8ac18f3...
volume_anomaly_v1  raw: d8275427c958743b...   lf: a03d18fece9e0052...   git_blob: a03d18fece9e0052...
```

`git ls-files --eol` mostra os quatro arquivos como `i/lf, w/crlf` **apesar** de `eol=lf` no
`.gitattributes` — a normalização vale para o que entra no repositório, não para o que já está na
árvore de trabalho.

**Correção certa, com o preço declarado.** Normalização mínima de quebras de linha antes do digest,
mantendo nomes, ordem e separadores atuais. **Não** AST nem bytecode: AST exige inventar uma
representação canônica nova, e bytecode não tem estabilidade garantida entre versões do Python —
os dois ampliariam o contrato em vez de consertar o incidente. E a correção **precisa de um plano
para as versões já congeladas**: publicá-la muda os digests do lado Windows de `c012…/d827…` para
`6ccb…/a03d…`, e as coortes locais de `EXP-0001`/`EXP-0002` deixam de rodar sem `--supersede`
auditado. Os digests da VPS, por já serem LF, **não** mudam.
