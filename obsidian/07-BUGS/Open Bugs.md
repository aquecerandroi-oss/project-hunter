---
tags: [bugs, abertos]
updated: 2026-09-06
---

# Open Bugs

Levantado de `.claude/state/milestone.json` (histórico de M0) e `docs/SECURITY.md`. Nenhum destes bloqueia o fechamento do M0 — foram conscientemente registrados como conhecidos em vez de resolvidos, mas continuam abertos.

## Abertos pela quinta rodada de conhecimento (2026-09-06) — achado da Sexta-feira, confirmado pela Astra

- **[CORRIGIDO NA ÁRVORE, AGUARDANDO COMMIT] HIGH (qualidade de dado) — conflito de propriedade de campos entre o ticker REST e o `bookTicker`: `volume_24h` e `bid`/`ask` quase nunca coexistiam no mesmo hash quente.** Achado em [[KB-0044-o-que-morre-em-dez-segundos]] (rodada 5 de conhecimento), com o mecanismo confirmado por leitura de código depois do apontamento da Astra. O refresh de universo busca o ticker de 24h da Binance (`universe.py:107` → `GET /fapi/v1/ticker/24hr`, `binance/rest.py:270`), cujo parser nunca preenche `bid`/`ask` (`binance/normalize.py:212`, docstring explícito), e escreve no hash `mkt:{exchange}:{symbol}:ticker` (`universe.py:181`). O stream `bookTicker` produz `bid`/`ask`/quantidades e nunca volume (`binance/streams.py:168`) e o coalescer escreve **no mesmo hash** (`coalesce.py:158`). Antes da correção os dois escritores declaravam `owned=TICKER_FIELDS` — o conjunto **inteiro** de campos do ticker — e a regra do Lua de `hot_state.py` apaga com `HDEL`, no mesmo `MULTI` do `HSET`, todo campo de propriedade que vier ausente (H4, para não deixar valor velho ao lado de timestamp fresco). Com dois produtores complementares isso faz cada escrita apagar os campos do outro: um refresh REST aceito grava `volume_24h` e apaga `bid`/`ask`; o próximo `bookTicker` aceito grava `bid`/`ask` e apaga `volume_24h` de volta. **Evidência em produção:** de 55.709 linhas em `market_snapshots`, só **6** têm `volume_24h`/`quote_volume_24h` preenchidos — o `HGETALL` que alimenta o snapshot (`sampling.py::write_snapshots`) herda o hash como estiver no instante da leitura, então herdou a perda sem precisar de mudança própria. Refina a entrada LOW mais antiga desta mesma lista ("`volume_24h`... vêm `null` na API") — a causa **não é só o TTL de 30 s**, é a disputa de escritores; aumentar o TTL não resolveria nada.

  **Correção aplicada:** propriedade de campo por produtor em vez de um conjunto único. `hot_state.py` agora tem `TICKER_REST_FIELDS` (o que o ticker de 24h realmente manda: `last`, `volume_24h`, `quote_volume_24h`, `high_24h`, `low_24h`, `change_24h_pct`, `ts`) e `TICKER_WS_FIELDS` (o que o `bookTicker` realmente manda: `last`, `bid`, `ask`, `bid_qty`, `ask_qty`, `ts`), e `write_ticker`/`queue_ticker_hash` exigem um `source: Literal["rest", "ws"]` explícito que escolhe qual conjunto é usado para decidir o que fica "ausente, deve ser apagado" — nunca mais o outro produtor. `universe.py` chama com `source="rest"`; o coalescer (`coalesce.py`), com `source="ws"`. Nenhuma mudança em `sampling.py`: como os dois conjuntos de campos agora convivem no mesmo hash, o snapshot volta a ver `volume_24h` **e** `bid`/`ask`/`spread_pct` juntos sem precisar de alteração própria — confirmado por teste (`test_snapshot_carries_both_rest_volume_and_ws_spread_together`, `services/market-worker/tests/test_persist.py`). Testes de reprodução e regressão em `services/market-worker/tests/test_hot_state.py`: `test_shared_ownership_reproduces_the_kb_0044_bug` fixa o mecanismo exato (um `owned` compartilhado ainda apaga `volume_24h` na próxima escrita `bookTicker`) para que ninguém reintroduza um conjunto único por engano; `test_rest_ticker_and_ws_ticker_coexist_in_same_hash` e `test_rest_ticker_after_ws_ticker_does_not_delete_bid_ask` provam a convivência nos dois sentidos de chegada; os testes H4 (`test_write_ticker_rest_drops_stale_optional_field_under_fresh_ts`, `test_write_ticker_ws_drops_stale_optional_field_under_fresh_ts`) confirmam que a propriedade por produtor não perdeu a proteção original contra campo obsoleto — cada um só apaga o que é seu. `TradeMemory`/`push_trade` foram extraídos para `hot_state_trades.py` (mesmo padrão de `hot_state_candles.py`) para o `hot_state.py` caber no orçamento de 350 linhas depois da correção.

  228 testes de `services/market-worker` verdes, `ruff check`/`ruff format --check`/`pyright` limpos no escopo tocado, `check_file_size.py` sem novos itens acima do orçamento. **Aguardando commit** — dono: `exchange-integration-specialist`.

## Abertos pela subida do Shadow Lab na VPS (S4, 2026-09-06)

Prova completa em `.claude/state/vps-lab-proof.md`.

- **[RESOLVIDA em 2026-09-06 por `98c15bc` — ver [[Resolved Bugs]]] HIGH — o `code_ref` não é portável entre a máquina do Everton e a VPS.** Os digests do mesmo
  commit divergem: `momentum_v1` é `...@sha256:c012f75cdd8492d3...` no dev box e
  `...@sha256:6ccbe8b6c8ac18f3...` na VPS. Investigado até a causa, com os dois lados em `75fc59c` e
  `git status` limpo em `packages/core/hunter_core/strategies/`: `git hash-object` devolve o **mesmo**
  blob nos dois (`core.autocrlf=true` + `.gitattributes` normalizam na entrada), mas os **bytes em
  disco** diferem — `base.py` tem 14.095 bytes no Windows e 13.757 na VPS, e a diferença é
  exatamente 338, o número de linhas do arquivo: quatro módulos do fecho de imports (`base.py`,
  `aggregate.py`, `indicators.py`, `envelope.py`) estão em **CRLF** na árvore de trabalho do Windows
  e em LF na VPS (`tr -cd '\r' < base.py | wc -c` → 338). O `code_ref` é o digest desses bytes.
  **Cenário:** ativar uma versão a partir do dev box contra o banco de produção — ou restaurar um
  dump com versões congeladas no Windows e rodá-las na VPS — faz `load_active_versions` recusar
  **todas** com `shadow_version_code_ref_mismatch`. Graças à correção da S2 o `/ready` fica vermelho
  em vez de mentir, mas o Lab não roda, e campo congelado não se corrige no lugar: só `--supersede`,
  encerrando a coorte anterior. Não morde hoje porque cada ambiente ativou as suas próprias linhas.
  Confirmado independentemente pela Astra, que reproduziu a composição do digest em memória:
  converter só CRLF → LF nos arquivos locais devolve **exatamente** os hashes da VPS, que são iguais
  aos dos blobs do commit (`raw c012f75c… → lf 6ccbe8b6… = git_blob 6ccbe8b6…`). `git ls-files --eol`
  mostra os quatro arquivos como `i/lf, w/crlf` **apesar** de `eol=lf` no `.gitattributes` — a
  normalização vale para o que entra no repositório, não para o que já está na árvore de trabalho.
  **Correção certa:** normalização **mínima** de quebras de linha antes do digest, mantendo nomes,
  ordem e separadores; **não** AST nem bytecode (AST exige inventar uma canonicalização nova,
  bytecode não é estável entre versões do Python — os dois ampliariam o contrato em vez de consertar
  o incidente). Com teste que compare o digest do mesmo módulo em CRLF e em LF. **E a correção
  precisa vir com um plano para as versões já congeladas:** publicá-la muda os digests do lado
  Windows, e as coortes locais de [[EXP-0001-momentum-v1]] e [[EXP-0002-volume-anomaly-v1]] deixam de
  rodar sem `--supersede` auditado; os da VPS, já em LF, não mudam. Dono: quem tocar
  `hunter_strategy_worker/code_ref.py` a seguir.
- **[RESOLVIDA em 2026-09-06 por `2587b9f` — ver [[Resolved Bugs]]] HIGH (deploy) — o `seed` não é idempotente depois da primeira ativação, e não pode entrar no
  fluxo de deploy como está.** Dois problemas encadeados. (a) `compose.sh update` roda `migrate` e
  nunca `seed`: medido antes de ativar o Lab, a VPS tinha 526 mercados e **367.256 velas** coletados
  e **zero** linhas em `strategies`, `strategy_versions` e `feature_definitions` — coletava mercado
  havia horas sem uma única estratégia cadastrada. Só apareceu porque o script de ativação recusou
  com a mensagem certa. (b) A correção óbvia — pôr o `seed` no `update` — **quebraria o próximo
  deploy**, achado da revisão da Astra e reproduzido por mim na própria VPS depois da ativação:

  ```
  $ bash infra/vps/compose.sh run --rm -e HUNTER_COMMAND=seed --entrypoint /app/infra/docker/entrypoint.sh migrate
  sqlalchemy.exc.DBAPIError: asyncpg.exceptions.RaiseError:
    strategy_versions 01a074c5-8f1d-7a75-a88b-2badb6a5dd67 is frozen after activation: code_ref cannot change
  [SQL: INSERT INTO strategy_versions (...) ON CONFLICT (strategy_id, version)
        DO UPDATE SET code_ref = excluded.code_ref ...]
  [parameters: (..., 'v1', 'draft', 'hunter_indicators.strategies.momentum_v1', ...)]
  ```

  `seed.py` sobrescreve `code_ref` com um placeholder; a trigger de congelamento recusa em qualquer
  linha já ativada; e o seed roda numa transação só, então **as oito tabelas revertem juntas**. O
  rollback funcionou (8 estratégias, 8 versões, 28 features, versões ativas intactas), mas um deploy
  que falha inteiro por causa disso é pior que o buraco original. **Correção:** o seed tem de
  **preservar** o `code_ref` de versões já ativadas, com teste `seed → ativação → seed`, **antes** de
  entrar em qualquer fluxo automático. Dono: `devops-engineer` + `database-architect`.
- **MEDIUM (sob investigação) — 18 outcomes na VPS podem ter `funding_missing` falso.** 19 de 70
  acompanhamentos encerrados têm `R_net = NULL` (18 `funding_missing:2026-09-06T04:00:00+00:00`, 1
  `funding_ambiguous_exit`), todos preservando `meta.r_ex_funding` — o comportamento conservador
  está certo. Mas a Astra apontou que `hunter_strategy_worker/funding.py` trunca o intervalo para
  segundos, projeta uma grade de liquidações e exige **correspondência exata de timestamp**, e o
  histórico desta VPS tem `max(funding_time) = 2026-09-06 04:00:00.005+00`. **Cenário:** a liquidação
  real existe cinco milissegundos depois da grade, a busca exata falha, e o outcome é rotulado como
  funding ausente quando o dado está lá. Não cruzei outcome a outcome, então não está provado — mas
  **não dá para classificar esses 18 como ausência legítima de dado**. Correção: identidade de
  liquidação que preserve o timestamp original em vez de exigir igualdade com uma grade calculada.
  Toda avaliação datada sobre a VPS conta os 19 fora dos "encerrados avaliáveis" de qualquer forma.

  **Investigação fechada em 2026-09-06 (turno da tarde) — censo completo em
  [[EXP-0001-momentum-v1]], seção "Hipóteses de falha".** Sobre os 73 outcomes com
  `funding_missing:*` da coorte da VPS (`as_of = 13:00Z`), com evidência graduada: **69** têm linha
  em `funding_rates` do **mesmo mercado** a menos de 2 s do instante pedido mas não no instante
  exato; **3** têm casamento exato na leitura de hoje e causa histórica por demonstrar; **1** não tem
  candidato em ±60 s (o vizinho está a 2 h). Deltas observados: +5 ms (22), −5 ms (18), +1 ms (25),
  +995 ms (1), +1001 ms (3), 0 ms (3). `funding_rates` tem 1883 linhas em 221 mercados e **851 delas
  têm parte de segundos diferente de zero** — a grade real da corretora não é redonda. Por
  liquidação em vez de por outcome: **66 liquidações distintas, 57 mercados, 7 instantes.** A
  hipótese está confirmada como mecanismo dominante; ela deixa de ser "sob investigação" e vira o
  item MEDIUM abaixo, com a proibição explícita da correção ingênua.

## Abertos no plantão da tarde de 2026-09-06 (coorte da VPS)

- **HIGH (operacional, VPS) — o backup do Postgres da VPS nunca rodou; não existe um único dump.**
  `/opt/backups` contém apenas `backup.log`, com uma linha: `/bin/bash: line 1:
  /opt/project-hunter/infra/vps/backup_postgres.sh: Permission denied`. Causa: o arquivo é rastreado
  no git como `100644` (`git ls-files -s infra/vps/backup_postgres.sh`) e a linha instalada pelo
  bootstrap em `/etc/cron.d/hunter-backup` invoca o caminho **diretamente**
  (`infra/scripts/bootstrap_vps.sh:346`), em vez de `bash <caminho>` — que é como o próprio
  cabeçalho do script manda rodá-lo e como todo o resto do repositório invoca esses scripts
  (`compose.sh`, `astra.sh`). Sem bit de execução, o cron falha todo dia às 03:17 e escreve a mesma
  linha no log. **Cenário:** perder o volume do Postgres da VPS apaga a pesquisa inteira do Shadow
  Lab, e ela é **irrecuperável por construção** — `signal_outcomes` avança no lugar, não há
  histórico de estados, e nenhuma avaliação datada passada pode ser reconstruída a partir dos
  sinais. É o único dado do projeto que não se refaz coletando de novo. **Fix (uma linha, duas
  opções):** trocar a linha do cron para `bash <script>` no bootstrap, **ou** marcar o arquivo
  executável no índice (`git update-index --chmod=+x`) e refazer o deploy. **Bloqueado neste turno:**
  tentei as duas coisas na VPS e o gate de permissão da sessão recusou (escrita em `/etc/cron.d` via
  `sudo` e execução do script). Precisa do Everton ou de uma tarefa `devops-engineer` com permissão.
  Dono: `devops-engineer`.
- **MEDIUM (pesquisa/instrumento) — o funding é casado por igualdade exata de timestamp contra uma
  grade calculada, e a corretora não usa grade redonda.** Detalhe e censo acima. **O efeito medido é
  pequeno e isso importa para a prioridade:** entre os outcomes que têm `R_net`, **nenhum** dos 173
  de momentum atravessou uma liquidação e só **9** dos 394 de volume atravessaram, com efeito médio
  de −0,000195 R e extremos −0,027742 / +0,000036. Não é a causa de uma expectancy de −0,2 R; é
  cobertura de pesquisa perdida em silêncio (50 outcomes fora do `R_net` na coorte avaliável).
  **A correção ingênua é proibida** (revisão da Astra em [[S4-hipoteses]], must-fix 5): dar
  tolerância de ±2 s ao `known.get()` permite **cobrar a mesma liquidação duas vezes**, porque
  `strategy-worker/funding.py:126` faz a união da grade calculada com o observado (a grade tem
  `08:00:00` e o observado tem `08:00:00.005`); e uma janela larga passa a cobrar funding
  **posterior** à saída, enquanto o recorte atual termina em `exit_ts` (`settle.py:60`). O protocolo
  correto precisa validar a cadência vigente, exigir associação **única** sem reutilizar liquidação,
  preservar o timestamp original separando identidade de incidência, recusar ambiguidades nas
  fronteiras e usar tolerância muito menor que metade do espaçamento mínimo validado. Dono:
  `quant-engineer` + `exchange-integration-specialist`.
- **LOW (observabilidade) — a hipótese de chegada tardia do funding não é demonstrável com o schema
  de hoje.** Três outcomes têm casamento exato de timestamp e ainda assim foram rotulados
  `funding_missing`, o que só se explica se a linha ficou visível depois da avaliação. Mas
  `FundingRate` não registra horário de ingestão e `SignalOutcome.updated_at` não registra o
  snapshot da consulta de funding, então não há como datar a visibilidade. Enquanto isso não
  existir, "corrida de leitura" fica como hipótese plausível e **não** como diagnóstico.
- **MEDIUM (teste intermitente) — `packages/exchange-adapters/tests/unit/test_ws_client.py::test_quiet_socket_rotates_cleanly_at_the_rotation_deadline`.**
  Apontado pela T2.9 (`.claude/state/notes-T2.9.md`): em execução isolada passou, passou, falhou
  (`assert 3 == 2` no número de conexões). O teste crava a **contagem exata** de reconexões com
  `max_connection_age_s=0.02` — um prazo real de 20 ms numa máquina carregada rende uma rotação a
  mais. `ws_client.py` e `test_ws_client.py` **não** são tocados pelo diff da T2.9, então não é
  regressão dela. **Cenário:** um teste que falha por carga da máquina treina a equipe a reexecutar
  a suíte até passar, e é assim que uma falha real vira ruído aceito. **Fix:** asserção `>= 2`, ou
  prazo vindo de um relógio injetado em vez do relógio real. Dono:
  `exchange-integration-specialist`.
- **Observação (capacidade, não bug) — `dropped_events = 7.073.659` no `hb:market:binance` da VPS**
  em ~14 h, com o `market-worker` a 98,97% de um core (de 12 na máquina, carga 1,32). Por contrato o
  `BoundedEventQueue` **nunca** descarta kline final (`binance/event_queue.py`), e a evidência bate:
  `ingestion_gaps` com 1590 `recovered`, 2 `open`, 2 `failed`, e a última vela de 1 min às 13:27Z. O
  que se perde é evento parcial (hot state), não série durável. Fica registrado em
  [[Market Collector]] como consumo de margem: a folga que hoje absorve 200 mercados é a mesma que o
  scanner do M2 vai querer.

## Abertos pela primeira avaliação do Shadow Lab (S4, 2026-09-06)

- **HIGH (operacional, local) — o `market-worker` do stack local está `unhealthy` e o Lab parou de
  avaliar.** `docker compose ps` às 02:57 UTC: `market-worker  Up 9 minutes (unhealthy)`; o hash de
  heartbeat `hb:market:binance` estava **vazio** (expirado); a última vela persistida era
  `2026-09-06 02:50:00+00` com `now() = 02:57:32`; `ingestion_gaps` acumulou **773 linhas `open`**
  com `gap_start` a partir de 02:04. Consequência medida no Lab: o heartbeat
  `hb:strategy:shadow` às 02:56:38 devolveu `evaluations_by_state = {"unavailable":400,
  "ineligible":1}` sobre `evaluated_bars = 401` — **100% das avaliações recusadas**, porque a
  agregação exige a janela contígua inteira e um minuto perdido custa até ~24 h de avaliações
  naquele mercado. **Não é defeito do Lab**: é a recusa correta de agregar sobre buraco. Causa
  provável: contenção da máquina com a T2.9 em prova mais o Postgres. **Registrado e não
  consertado por instrução** — os arquivos do `market-worker` estão em voo na T2.9. Dono: quem
  fechar a T2.9. Ver [[EXP-0001-momentum-v1]], [[EXP-0002-volume-anomaly-v1]] e [[Market Collector]].
  **Estado em 2026-09-06 13:23Z:** não observável — o Docker Desktop desta máquina está fora
  (`open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`), então não há
  stack local nenhum de pé. O bug continua **aberto** e não verificado; a coleta e o Lab que
  importam agora estão na VPS, onde `open_gaps = 0` e a última vela é das 13:27Z. Reabrir a
  verificação quando o Everton subir o Docker de novo.
- **HIGH (latente, todo o projeto) — o default de `hunter_core.events.consume()` mata qualquer
  consumidor num stream ocioso.** `consume()` bloqueia o `XREADGROUP` por 5000 ms e
  `hunter_core/redis.py` define `socket_timeout = 5.0`: os dois vencem no mesmo instante e o
  processo morre com `redis.exceptions.TimeoutError` **sempre que o mercado fica quieto**. Medido
  na primeira tentativa da prova da S2 (23:18–23:21 UTC de 2026-09-05,
  `hunter_core/events/consume.py:85`). O `strategy-worker` foi blindado no seu próprio consumidor
  (`CONSUME_BLOCK_MS = 2000` + backoff, com regressão em `tests/test_consumer_supervision.py`),
  **mas o default continua perigoso para todo consumidor futuro** — e a T2.9 está editando
  exatamente `packages/core/hunter_core/events/consume.py` agora. Cenário: o próximo worker que
  usar o default morre em silêncio no primeiro fim de semana quieto. Dono: T2.9 / M2.
- **MEDIUM (observabilidade de pesquisa) — a quebra de `unavailable` por motivo não é persistida em
  lugar nenhum.** O heartbeat `hb:strategy:shadow` agrega só por *estado*
  (`{"unavailable":400,"ineligible":1}`); o motivo (`gap`, `warmup`, `stale`, universo mudado) só
  aparece numa sonda ad-hoc dentro do container. Cenário: uma avaliação datada não consegue dizer
  **por que** perdeu 400 barras sem alguém entrar no container na hora — e depois que a janela
  passa, a informação não existe mais. É requisito de cobertura da S3
  (`.claude/state/notes-S2.md` §14 já pede separar `late:delay`, `late:missed_open`,
  `late:unconfirmed`, `geometry`, `gap:*` e `blocked:*`); esta linha acrescenta que o mesmo vale
  para o lado das avaliações recusadas. Dono: S3.
- **LOW (retenção × pesquisa) — a retenção não conhece o `tracking_hold`.** `tracking_hold` mantém
  a *coleta* de um mercado segurado, mas a poda de 90 dias de `candles_1m`
  (`infra/scripts/prune_partitions.py`) apaga por partição sem olhar `shadow_episodes`. Com
  horizontes de 2–4 h isso não morde hoje; um replay antigo ou uma versão de horizonte longo
  morderia, e o efeito seria censura silenciosa de acompanhamentos. Dono: schema/retention.

## Abertos pela prova operacional da T1.6b (2026-09-05, sharding)

- **HIGH (operacional, encontrado no fecho do M1) — o override do Compose não é aplicado quando o
  `docker compose` é chamado só com o arquivo base, e o worker volta silenciosamente para 200
  mercados.** `infra/docker/docker-compose.override.yml` é carregado automaticamente apenas na
  descoberta padrão de arquivos; com `-f infra/docker/docker-compose.yml` (que é como o
  `CLAUDE.md` documenta o comando) ele **não** entra, e `MARKET_UNIVERSE_SIZE` cai no padrão do
  código, que é 200. Medido na noite de 2026-09-05, minutos depois da aprovação do M1: o container
  foi recriado por outro fluxo, `docker inspect` não mostrava nenhuma das duas variáveis, e a sonda
  devolveu `markets_monitored: 200`, `markets_degraded: 200`, `markets_ok: 0`, hot state completo em
  **7,0%** — exatamente o colapso que a prova da T1.6b mediu para um processo com 200 mercados.
  Cenário: qualquer `docker compose -f infra/docker/docker-compose.yml up -d` devolve a máquina à
  configuração que não se sustenta, sem aviso, e a tela do Everton volta a ficar toda `degraded`.
  **Correção certa:** mover o padrão honesto (`MARKET_UNIVERSE_SIZE: "50"`) para o próprio
  `docker-compose.yml`, em vez de depender do override; o override passa a servir só para
  *aumentar* o universo. Não foi feito agora porque `infra/docker/docker-compose.yml` está sendo
  editado pela tarefa S2 neste momento. Container restaurado à mão em 23:39 UTC com os dois
  arquivos explícitos. **Dono: primeiro item do M2, junto do heartbeat por shard.**
Todos medidos. Prova em `.claude/state/t16b-proof.md`. A HIGH-1 da T1.6 abaixo está
**resolvida** por esta prova: com 4 shards × 50 mercados, `markets_ok` = 198/200 (99,0%),
0 stale, 0 unavailable, 200/200 velas finais por minuto e CPU média por shard entre 36,6% e
64,2% de um core. Ver [[Resolved Bugs]] e [[Market Collector]].

- **HIGH — os shards compartilham a mesma chave de heartbeat.** Todos escrevem
  `hb:market:{exchange}`. Medido na corrida de 2 shards: `/system/market-status` devolveu
  `subscriptions: 636` (assinaturas de **um** shard) com `markets_monitored: 200`. Cenário: um
  shard morre, o outro continua reescrevendo a chave, e o painel do operador segue verde — a
  métrica que existe para detectar worker morto fica cega exatamente na topologia que a T1.6b
  introduziu. **Dono: M2.** Correção: chave por shard (`hb:market:{exchange}:{shard}`) e
  agregação na API, com o total de shards esperado vindo da configuração.
- **MEDIUM — gaps de mercados não monitorados nunca fecham.** `run_recovery` itera
  `universe.symbols`; um mercado que sai do top-N com gap aberto fica `open` para sempre e
  continua contado em `open_gaps`. Medido: no fim da prova restaram **95 gaps abertos, e os 95
  são de mercados não monitorados**. Efeito: o número que o operador acompanha nunca chega a
  zero. **Dono: M2.** (A decisão SHADOW já exige o oposto para o Lab: `tracking_hold` mantém a
  coleta de um mercado excluído enquanto houver acompanhamento aberto.)
- **MEDIUM — a morte de um shard não é rebalanceada.** A fatia `crc32(symbol) % N == i` simplesmente
  deixa de ser coletada até o processo voltar; nada redistribui. `restart: unless-stopped` cobre o
  caso normal, mas não há prova de um shard morto com os outros vivos. **Dono: M2.**
- **MEDIUM — `tests/integration/test_market_invariants.py::test_a_fresh_open_interest_write_never_rejuvenates_a_stale_mark`
  tem orçamento de 2 s de relógio.** Falhou com `assert 2323 < 2000` com a máquina rodando quatro
  shards a ~100% de CPU. Não é defeito de produto; é um teste que assume folga de CPU e vai piscar
  na CI. **Dono: M2.**
- **MEDIUM — `markets_ok` mistura capacidade com backlog de recovery.** Um `ingestion_gap` aberto
  força `degraded` qualquer que seja o frescor do hot state, então a métrica do plano ficou em 0
  durante horas enquanto 122 mercados tinham book fresco. É honesta (há buraco na série), mas não
  serve sozinha como meta de capacidade — por isso a prova mede também "mercados com os três
  componentes `ok`". **Dono: M2** (separar os dois eixos na API e na tela).
- **LOW (follow-up de performance, com número) — `model_construct` do pydantic é o maior custo de
  aplicação restante.** py-spy no shard de 100 mercados (11.110 amostras): `model_construct` 15,0%
  cumulativo, com `resolve_default_value` 2,49% e `inspect._signature_from_callable` 2,75%
  pendurados — ele percorre `model_fields` e resolve defaults **a cada evento**. Trocar os tipos
  normalizados do caminho quente por `dataclass(slots=True)` é o próximo ganho. **Dono: M2.**

## Abertos pela prova operacional da T1.6 (2026-09-05)

Todos medidos, não suspeitados. Prova em `.claude/state/t16-proof.md`.

- **[RESOLVIDA em 2026-09-05 pela prova da T1.6b — ver acima] HIGH-1 — o worker satura um core e o hot state de alta frequência não se sustenta com 200 mercados.** Medido: `docker stats` 100 % de CPU no `market-worker` enquanto o Redis fica em 0,9 % e 103 ops/s e o Postgres em 25 %; `ss -tn` com 769 KB parados no buffer de recepção do socket da Binance; `mkt:*:ticker` e `mkt:*:book` chegando a **zero chave viva** de 200; **1,15 milhão** de eventos descartados. Consequência para o produto: a tela mostra `markets_ok = 0`, tudo `degraded`, sem preço ao vivo. A série durável **não** é afetada (o `BoundedEventQueue` nunca descarta kline final, por contrato — 200/200 mercados por minuto, valores idênticos ao REST). **Dono: M2** (perfilagem primeiro; candidatos são o `LRANGE` de 50 itens com desserialização msgpack a cada trade em `push_trade`, a ausência de pipeline nas escritas de hot state, e a falta de prioridade entre ingestão ao vivo e backfill). **Mitigação disponível hoje, decisão do dono:** reduzir `MARKET_UNIVERSE_SIZE` de 200 para 20–50.
- **MEDIUM — o backlog de recovery não tem prazo nem freio.** Ao fim da corrida havia 4.729 gaps abertos e 2.324 recuperados, com teto de `MAX_GAPS_PER_CYCLE = 50` por ciclo de 60 s e cada busca REST em série. Quanto maior o backlog, mais REST, mais CPU, menos hot state, mais buracos — laço de realimentação sem amortecimento. Ressalva: esse backlog foi inflado por ~10 apagões que eu mesma provoquei em 1h50, não é o de uma operação normal. Falta definir um prazo de convergência aceito e medir contra ele.
- **MEDIUM — a prontidão regride de 503 para 200 sem nenhum dado ter chegado.** `ReadinessState.observe_adapter` zera `connect_timed_out` a cada observação e o rededuz do relógio da tentativa de conexão; quando o adaptador desiste de uma tentativa e abre outra, o relógio reinicia e a prontidão volta ao ramo tolerado. Medido no corte de rede: 503 em T+30s, **200 em T+45s**, com a Binance inalcançável. A tolerância de 120 s acumulados é contrato fechado na decisão conjunta, então responder 200 durante ela não é bug — a **regressão** é, e existe um teste (`test_readiness_grace_is_monotonic_and_not_reset_by_flapping`) cuja intenção ela contraria. Recomendação da Astra, absorvida: exigir *progresso recente* nas conexões, não apenas uma tentativa em curso. **Dono: M2** (mexe em contrato acordado).
- **MEDIUM — apagão de Redis agora vira crash-loop, e o cooldown de rate limit não sobrevive ao restart.** Depois da correção da HIGH-4 o worker morre alto em vez de congelar, o que é o comportamento desejado; mas foram **8 reinícios em 81 s** de apagão. O `IpRateGate` é local ao processo (limitação já registrada do M1), então cada reinício perde o `Retry-After` da Binance, o que pode escalar um `429` para `418` (ban de IP). **Fix já previsto no plano:** persistir `blocked_until` em Redis — com a ironia de que é justamente o Redis que está fora. Alternativa: teto de reinícios ou backoff no supervisor.
- **MEDIUM — nada age quando o worker fica vivo-e-parado.** `restart: unless-stopped` só cobre morte de processo, e o Docker Compose puro **não** reinicia por healthcheck. O healthcheck detectou o zumbi corretamente durante 19 minutos e ninguém escutou. **Dono: T1.7/ops** — `autoheal` no Compose, ou um watchdog interno que mate o processo depois de N minutos de `/ready` reprovado.
- **LOW — `/api/v1/system/workers` mostra dois "workers" para um processo só.** O heartbeat genérico do runtime (chaveado por hostname) e o heartbeat de mercado (chaveado por exchange) aparecem como duas linhas de `role=market`. Não é dado falso, mas induz o operador a contar errado.
- **LOW — `dropped_events` está no Redis mas não na API.** O campo entrou no hash `hb:market:{exchange}` e em métrica; `scan_heartbeats` continua com uma allowlist de campos, então não quebra, mas o número não chega a `WorkerHeartbeatOut` nem à tela. Falta uma mudança aditiva em `apps/api/hunter_api/services/system_status.py` e no schema.
- **LOW — `volume_24h`, `quote_volume_24h` e `price_change_24h_pct` vêm `null` na API.** O refresh de universo grava `quote_volume_24h` no hash do ticker, mas o hash tem TTL de 30 s e é reescrito pela ingestão sem esses campos, então some entre refreshes (15 min). **Causa raiz mais precisa achada em 2026-09-06:** não é (só) o TTL — é a disputa de propriedade de campos entre o refresh REST e o `bookTicker` no mesmo hash, corrigida na árvore. Ver a entrada HIGH no topo desta lista e [[KB-0044-o-que-morre-em-dez-segundos]].

## Rastreados desde o fechamento do M0

- **`packages/core/tests/unit/test_logging.py` — erros de pyright strict.** Ficou pendente depois da onda 5; `.claude/state/milestone.json` registra que passou a ser tratado como KNOWN ISSUE em vez de item de resume-checklist. Não corrigido até 2026-09-05.
- **Isenções em `forbidden_patterns.sh`** (o gate de CI que falha em `sqlite`, `localhost` fora de dev/teste, escrita de JSON de estado, `print(` em produção) — mesma origem, ainda não revisado.
- **Isenção de nome de arquivo "bare" em `enums.py`** — mesma origem, ainda não revisado.

## Limitação de segurança aceita conscientemente (M0), a resolver no M1

- **JWT sem claim `azp` é aceito sem verificação de origem** (`auth/clerk.py`, `JwtAuthProvider.verify`). A allowlist de origem só compara quando o token traz `azp`; um token sem esse claim passa sem checagem. No M0 há um único cliente (`apps/web`), então a exposição prática é baixa, mas a decisão foi registrada como aceita apenas para o M0 — `docs/SECURITY.md` §1 marca isso explicitamente "rastreado para o M1", quando `azp` passa a ser obrigatório.

## Contradição encontrada durante a escrita desta base

`.claude/state/milestone.json` (wave 6, T13) afirma que `docs/reports/M0.md` foi escrito e que "Everton approves the close" com base nele — mas **o arquivo `docs/reports/M0.md` não existe no repositório**. O relatório de fechamento do M0 (formato §77) parece não ter sido persistido, apesar de o estado do milestone dizer que foi. Vale confirmar com quem fechou o M0 se o relatório existe em outro lugar ou se precisa ser reescrito.

## Adiados na revisão de T1.5b (2026-09-05) — nenhum bloqueia o commit

Achados reais, com cenário, que ficaram fora do escopo de polimento de UI e foram empurrados para o **M2**. Origem: `.claude/state/review-T1.5b.md` (duas rodadas: `code-reviewer`, `security-reviewer`, Astra/GPT-6 e QA visual).

- **Testes de hidratação de verdade não existem.** `tests/appearance-form.test.tsx` e `tests/motion-showcase.test.tsx` só afirmam o estado **depois** dos efeitos, então **passariam com o bug antigo** (Astra verificou linha a linha). Os mismatches H1/M1/S2 foram corrigidos no código e `tests/use-density.test.tsx` registra o primeiro render — mas cobrir a família toda exige um harness de SSR + hidratação no Vitest. **Dono:** infraestrutura de teste, M2.
- **jsdom não faz layout, então "visível" nunca é medido.** `use-arrow-key-row-selection` e `use-virtualized-rows` provam a aritmética, não a visibilidade física da linha. Fica para o E2E de Playwright do M2.
- **Sem tier de rate limit próprio para o servidor web na API.** Toda a renderização SSR compartilha o balde de 120/min por IP; o lado cliente foi contido (mínimo de 2 caracteres, debounce de 250 ms, `q` limitado a 64), o lado servidor não. **Dono:** `apps/api`, M2. Origem: `security-reviewer`.
- **Tooltip por componente no badge de qualidade** ("qual componente está atrasado") e **explicação do ponto de status acessível por toque no mobile** — as duas precisam de uma superfície de tooltip acessível por toque que a UI ainda não tem. M2.
- **Frescor vs conexão no Live Status:** a tela pode dizer `CONNECTED` com eventos velhos. Depende de um campo de idade por exchange que a API ainda não expõe. M2.
- **Reestruturar o modelo de scroll do `thead` fixo / adotar biblioteca de virtualização.** O sintoma concreto (H4) era aritmética e foi corrigido; a reestruturação é mudança de arquitetura. M2.
- **Layout dos trades a 1024 px com a sidebar aberta** — suspeita da Astra por inferência, sem medição em navegador. Sem cenário provado, sem correção. M2, junto do E2E.
- **QA interativo do command palette nunca rodou.** Dois dev servers concorrentes sobre o mesmo `apps/web/.next` deixaram a página da 3000 sem carregar JavaScript nenhum (`/_next/static/chunks/main-app.js` → 404); encerrar processos era bloqueado pela política daquela sessão. O comportamento está provado por Vitest e por screenshots estáticos, **não** por interação real. Vale repetir num ambiente limpo.

### Aprendizado de processo registrado

`pnpm lint` + `typecheck` + Vitest **não substituem o build de produção**. A T1.5b passou nos três com o `next build` quebrado (`Only async functions are allowed to be exported in a "use server" file`), porque o Vitest não aplica as restrições do Next App Router. **`docker compose -f infra/docker/docker-compose.yml build web` é obrigatório no aceite de qualquer tarefa de `apps/web`.**

## Relacionadas

[[Resolved Bugs]] · [[System Overview]]

## Fontes

`.claude/state/milestone.json`, `docs/SECURITY.md` §1

## Abertos em 2026-09-05
- ~~Banco local com coluna antiga em `processed_events`~~ — corrigido em 2026-09-05 (rename `processed_at → claimed_at`, `completed_at` criada, índices renomeados) a pedido do dono.
- **Codex (Astra) no Windows não funciona com sandbox**: `read-only`/`workspace-write` bloqueiam até leitura de arquivos ("blocked by policy"). Decisão do dono: rodar sem sandbox com controles compensatórios (`infra/scripts/astra.sh`).
- **Limite mensal de gasto da Anthropic** derruba especialistas no meio da tarefa (429). Mitigação: Astra assume tarefas mecânicas; dono avalia aumentar o limite.
- **Agentes personalizados e MCP do Obsidian só carregam em sessão aberta dentro de `C:\dev\project-hunter`**; sessão nascida fora não os vê.

## Abertos na revisão de T1.4/T1.5 (2026-09-05)

- **`last_price` no hash quente carrega o timestamp do `bookTicker`, não o do último trade.** `parse_book_ticker` (`packages/exchange-adapters/hunter_exchanges/binance/streams.py`) carimba o preço do último `aggTrade` em cache com o horário de evento do `bookTicker`, e `write_ticker` (`services/market-worker/hunter_market_worker/hot_state.py`) grava um único `ts` no hash `mkt:*:ticker`. Cenário de falha: o canal de trades para, book e `bookTicker` continuam; `GET /api/v1/markets` devolve o preço antigo com `last_update` recente e o mercado fica `ok`. O payload de tempo real **já** separa `price_ts` e `book_ts` (`ingest.py::build_tick_payload`) e a tela de T1.5 usa `price_ts` corretamente — o buraco é só no caminho REST/hot state. **Dono:** T1.2/T1.3. **Fix:** levar `price_ts` para o hash e expor a idade do preço separada da idade da cotação em `components.ticker`.
- **`apps/api/tests/integration/test_webhook.py::test_a_crash_where_even_the_release_never_runs_still_recovers_after_the_stale_window` falha.** A suíte de `apps/api` estava 428/0 e passou a 445/1 depois que a T1.3 acrescentou `command_timeout: 30` engine-wide em `packages/core/hunter_core/db/session.py`. Falha também isolada (`uv run pytest apps/api/tests/integration/test_webhook.py -q` → 1 failed, 16 passed), então não é ordem de teste. **Dono:** T1.3 (`packages/core`). Nenhum arquivo de T1.4/T1.5 está envolvido.
- **Índice do git compartilhado entre duas sessões.** Com duas instâncias trabalhando no mesmo repositório, `git add` de uma aparece no `git diff --cached` da outra; um `git commit` sem pathspec varreria trabalho alheio. Contorno usado: `git commit -- <caminhos>`, que commita a árvore de trabalho só daqueles caminhos e não toca o resto do índice.
