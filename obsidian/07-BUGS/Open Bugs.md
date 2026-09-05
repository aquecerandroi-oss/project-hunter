---
tags: [bugs, abertos]
updated: 2026-09-05
---

# Open Bugs

Levantado de `.claude/state/milestone.json` (histórico de M0) e `docs/SECURITY.md`. Nenhum destes bloqueia o fechamento do M0 — foram conscientemente registrados como conhecidos em vez de resolvidos, mas continuam abertos.

## Abertos pela prova operacional da T1.6 (2026-09-05)

Todos medidos, não suspeitados. Prova em `.claude/state/t16-proof.md`.

- **HIGH-1 — o worker satura um core e o hot state de alta frequência não se sustenta com 200 mercados.** Medido: `docker stats` 100 % de CPU no `market-worker` enquanto o Redis fica em 0,9 % e 103 ops/s e o Postgres em 25 %; `ss -tn` com 769 KB parados no buffer de recepção do socket da Binance; `mkt:*:ticker` e `mkt:*:book` chegando a **zero chave viva** de 200; **1,15 milhão** de eventos descartados. Consequência para o produto: a tela mostra `markets_ok = 0`, tudo `degraded`, sem preço ao vivo. A série durável **não** é afetada (o `BoundedEventQueue` nunca descarta kline final, por contrato — 200/200 mercados por minuto, valores idênticos ao REST). **Dono: M2** (perfilagem primeiro; candidatos são o `LRANGE` de 50 itens com desserialização msgpack a cada trade em `push_trade`, a ausência de pipeline nas escritas de hot state, e a falta de prioridade entre ingestão ao vivo e backfill). **Mitigação disponível hoje, decisão do dono:** reduzir `MARKET_UNIVERSE_SIZE` de 200 para 20–50.
- **MEDIUM — o backlog de recovery não tem prazo nem freio.** Ao fim da corrida havia 4.729 gaps abertos e 2.324 recuperados, com teto de `MAX_GAPS_PER_CYCLE = 50` por ciclo de 60 s e cada busca REST em série. Quanto maior o backlog, mais REST, mais CPU, menos hot state, mais buracos — laço de realimentação sem amortecimento. Ressalva: esse backlog foi inflado por ~10 apagões que eu mesma provoquei em 1h50, não é o de uma operação normal. Falta definir um prazo de convergência aceito e medir contra ele.
- **MEDIUM — a prontidão regride de 503 para 200 sem nenhum dado ter chegado.** `ReadinessState.observe_adapter` zera `connect_timed_out` a cada observação e o rededuz do relógio da tentativa de conexão; quando o adaptador desiste de uma tentativa e abre outra, o relógio reinicia e a prontidão volta ao ramo tolerado. Medido no corte de rede: 503 em T+30s, **200 em T+45s**, com a Binance inalcançável. A tolerância de 120 s acumulados é contrato fechado na decisão conjunta, então responder 200 durante ela não é bug — a **regressão** é, e existe um teste (`test_readiness_grace_is_monotonic_and_not_reset_by_flapping`) cuja intenção ela contraria. Recomendação da Astra, absorvida: exigir *progresso recente* nas conexões, não apenas uma tentativa em curso. **Dono: M2** (mexe em contrato acordado).
- **MEDIUM — apagão de Redis agora vira crash-loop, e o cooldown de rate limit não sobrevive ao restart.** Depois da correção da HIGH-4 o worker morre alto em vez de congelar, o que é o comportamento desejado; mas foram **8 reinícios em 81 s** de apagão. O `IpRateGate` é local ao processo (limitação já registrada do M1), então cada reinício perde o `Retry-After` da Binance, o que pode escalar um `429` para `418` (ban de IP). **Fix já previsto no plano:** persistir `blocked_until` em Redis — com a ironia de que é justamente o Redis que está fora. Alternativa: teto de reinícios ou backoff no supervisor.
- **MEDIUM — nada age quando o worker fica vivo-e-parado.** `restart: unless-stopped` só cobre morte de processo, e o Docker Compose puro **não** reinicia por healthcheck. O healthcheck detectou o zumbi corretamente durante 19 minutos e ninguém escutou. **Dono: T1.7/ops** — `autoheal` no Compose, ou um watchdog interno que mate o processo depois de N minutos de `/ready` reprovado.
- **LOW — `/api/v1/system/workers` mostra dois "workers" para um processo só.** O heartbeat genérico do runtime (chaveado por hostname) e o heartbeat de mercado (chaveado por exchange) aparecem como duas linhas de `role=market`. Não é dado falso, mas induz o operador a contar errado.
- **LOW — `dropped_events` está no Redis mas não na API.** O campo entrou no hash `hb:market:{exchange}` e em métrica; `scan_heartbeats` continua com uma allowlist de campos, então não quebra, mas o número não chega a `WorkerHeartbeatOut` nem à tela. Falta uma mudança aditiva em `apps/api/hunter_api/services/system_status.py` e no schema.
- **LOW — `volume_24h`, `quote_volume_24h` e `price_change_24h_pct` vêm `null` na API.** O refresh de universo grava `quote_volume_24h` no hash do ticker, mas o hash tem TTL de 30 s e é reescrito pela ingestão sem esses campos, então some entre refreshes (15 min).

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
