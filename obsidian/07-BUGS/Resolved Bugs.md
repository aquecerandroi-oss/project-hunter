---
tags: [bugs, resolvidos]
updated: 2026-09-05
---

# Resolved Bugs

Correções reais extraídas do `git log`, todas dentro do Milestone 0. A maioria veio de rodadas de revisão de segurança/qualidade (T04–T10 no plano `docs/plans/M0.md`), não de bugs reportados em produção — não houve produção ainda.

## Market worker (T1.3, commit `b8c4766`)

CRITICAL e HIGH levantados pelo `database-architect` (duas passadas), pelo `code-reviewer` e pela Astra adversarial, todos com cenário de falha medido antes da correção. Uma linha cada.

- **CRITICAL-1** — `market_snapshots` e `open_interest_history` gravavam uma linha por `INSERT`; 400 inserts levavam 19,85 s contra 83 ms em lote, estourando o timeout de flush e descartando a fila inteira por idade. Corrigido: um `INSERT ... ON CONFLICT DO NOTHING` multi-linha por tabela por flush.
- **CRITICAL D1 (convenção de porcentagem)** — o snapshot gravava fração (correto, `NUMERIC(9,6)`), mas o fix-brief original mandava multiplicar por 100; a instrução errada foi rejeitada e o banco continua em fração. Divergência dos helpers de domínio virou o follow-up T1.1c.
- **CRITICAL D2** — `PersistQueues.drop()` levantava `RuntimeError` ao encher a fila de perdas; com Postgres fora, o processo morria ~9 min depois. Corrigido: `deque(maxlen=...)` que evicta e conta, nunca levanta.
- **HIGH-2** — a detecção de gaps fazia 1005 statements e 202 transações por passada (60,6 s com 200 mercados num ciclo de 60 s), segurando `ACCESS SHARE` em `candles` por ~40 s/min. Corrigido: três consultas set-based sobre o universo inteiro.
- **HIGH-3** — nada garantia que existisse partição para a data corrente; em 2027-01 o primeiro insert derrubaria o flush inteiro em silêncio. Corrigido: `assert_writable_partitions` fatal no startup para *agora*, `/ready` falso e `system_event` critical para o lookahead de +1 dia.
- **HIGH-4** — o ranking do universo fazia ~500 `UPDATE`s numa transação depois de zerar `is_monitored` de todos, travando linhas de `markets` por segundos. Corrigido: um único `UPDATE ... FROM (VALUES ...)`.
- **HIGH D3** — sem `command_timeout`/`statement_timeout`, um flush cancelado deixava o `drain_loop` preso para sempre num socket morto, com `/ready` falso e nada reiniciando. Corrigido: `command_timeout=30` no engine e `SET LOCAL statement_timeout = '15s'` nas sessões `hunter_worker`.
- **HIGH D5** — a detecção terminava em `align(now) - 1 min` e disputava com a fila de persistência, registrando até 200 gaps falsos por ciclo e disparando 200 backfills REST contra o banco já lento. Corrigido: graça de 2 min, maior que a tolerância de atraso da fila.
- **HIGH H1** — falha em `report_losses` sem `try/except` matava o processo num blip do Postgres; corrigido, e as perdas só saem da fila depois do commit.
- **HIGH H2..H10** — série de correções de hot state e coalescência: `event_ts` propagado, `HDEL` do campo opcional ausente na mesma transação do `HSET`, staleness por componente (`mark_ts`/`oi_ts`/`funding_ts` independentes), dedupe de trades em janela de 50, candles em janela rápida de 16, final substituindo parcial mesmo com `event_ts` igual, e `price_ts`/`book_ts` separados no payload.
- **D8 (caminho de produção)** — o bucket de open interest por ciclo só existia no caminho sem fila, morto em produção; um poll de 200 mercados atravessando o limite de 5 min espalhava as leituras por dois buckets, com o corte mudando a cada ciclo. Corrigido: `OpenInterestSample` carrega o `bucket_ts` do ciclo pela fila.
- **Staleness dos campos de ticker no snapshot** — `price`, `bid`, `ask`, `spread_pct` e volumes eram gravados por mais velho que estivesse o hash, republicando preço congelado como observação nova. Corrigido: gate pelo `ts` do próprio ticker, medido contra o instante real de coleta (não o minuto alinhado, que dava até 59 s de folga), com contador por campo; se tudo é descartado, a linha não é escrita.

## Infraestrutura de dev

- **`b2e48b5`** — `setup_env.ps1` juntava todas as variáveis numa única linha: em PowerShell 5.1 a vírgula liga mais forte que `+`, então a concatenação de linhas do `.env` colapsava tudo. Corrigido parenteizando cada linha.
- **`4e7e878`** — `setup_env.ps1` extraía a chave errada de entradas `NAME=value` ou de colagens multi-linha; corrigido, e passou a imprimir o tamanho da chave para conferência sem expor o valor.
- **`43ee7c3`** — `setup_env.ps1` tinha caracteres fora de ASCII que o PowerShell 5.1 não parseava; reescrito ASCII-only.
- **`cd1c2d3`** — instalação canônica corrigida para `uv sync --all-packages` (o root é um projeto uv virtual; sem essa flag os pacotes `hunter_*` não eram instalados).
- **`1a15013`** — `noqa` não utilizado no healthcheck do Docker removido (ruff `RUF100`).
- **`46993a0`** — comentário sobre loopback ajustado para passar no gate `forbidden-patterns`; porta padrão de `/health` corrigida para 8001; `DEPLOYMENT.md` atualizado para descrever o entrypoint real.

## Frontend

- **`541ef78`** — o registro de navegação (`nav-registry`) carregava referências a componentes React, que não serializam entre Server e Client Components; corrigido para ser dado puro (segmento + chave de ícone), permitindo que o layout server-side passe a sidebar para o client.
- **`4988645`** — formatação de dinheiro corrigida para ser segura com `Decimal` (não `float`); backoff de reconexão do WebSocket ganhou jitter; itens de navegação ainda não disponíveis (`Disponível a partir de: M<n>`) passaram a ser acessíveis (não só visualmente desabilitados).
- **`f48da11`** — a prévia de desenvolvimento `/_design` foi excluída do matcher do middleware do Clerk (estava sendo protegida por engano).

## Backend / API

- **`c6eb407`** — rodada de revisão T05 (CRITICAL/HIGH/MEDIUM): erros de validação passaram a nunca ecoar o input do usuário; timeouts adicionados a `/ready`; modelo de confiança de IP de proxy corrigido; `/metrics` passou a exigir token; `request_id` limitado em tamanho.
- **`149c542`** — ponte Redis→WebSocket unificada num único dispatcher roteado por canal de mensagem; broadcast passou a expulsar conexões mortas.
- **`94b26a4`** e **`8a454f4`** — endurecimento de auth/tenancy da revisão de segurança T06: cap no corpo de streaming, staleness máxima do JWKS, limites por-principal e por-WebSocket, claims de webhook em duas fases (evita processar duas vezes um evento entregue de novo no meio de um crash).
- **`a900926`**, **`ca3cab3`**, **`a9da9ea`** — correções de pyright strict e cobertura de teste (ponte Redis expõe `is_running`; branch de banco fora do ar em `/ready`; auditoria em exceção; liberação de lock verificada por token).

## Banco de dados

- **`c28c1bc`** — endurecimento de schema da cross-review T04 (a migração `0001` foi emendada no lugar, nunca sucedida por uma `0002`, porque o schema nunca tinha sido aplicado em lugar nenhum além de CI/testcontainers): políticas por comando (não `FOR ALL`) em `organizations`/`users`, classe de grant sem `DELETE`, verificação de existência dos papéis antes de prosseguir.
- **`720102f`** — política de `users` para colegas de organização tornada somente-leitura (`FOR SELECT`; antes permitia `UPDATE`/`DELETE` na linha de um colega); `organizations` perdeu `DELETE` para o papel da aplicação; contagem real de linhas semeadas por `seed.py` (antes reportava a contagem de entrada, não o que de fato foi gravado sob RLS).
- **`154ecea`** — schema inicial, RLS, partições, papéis e seeds (T04), base sobre a qual as duas correções acima foram aplicadas.

## Segurança / CI

- **`9b7afe8`** — revisão T10: allowlist do `gitleaks` baseada em valor (não em padrão frouxo), regra para senha de URI de banco, actions do GitHub fixadas por SHA, isenções por segmento de caminho.
- **`4035cd4`**, **`7d25f8a`** — senha de fixture de teste marcada conforme a convenção de allowlist do gitleaks, para não ser confundida com segredo real.

## Testes de integração

- **`744fdf8`** — suíte de integração T11: isolamento entre organizações, matriz de RBAC, mutações, webhook, rate limits, WebSocket, casos-limite de autenticação. Não corrige um bug específico; fecha a cobertura de teste que valida as correções acima.

## Relacionadas

[[Open Bugs]] · [[Changelog]]

## Fontes

`git log` (M0, commits acima), `docs/plans/M0.md` (rodadas T04–T11), `.claude/state/milestone.json`

## Resolvidos em 2026-09-05 (fechamento do M0 / início do M1)
- `3c31ef0` **Imagem web não construía**: `Dockerfile.web` não copiava `packages/shared-types`, então `@hunter/shared-types` virava `any` e o `next build` falhava dentro da imagem. Encontrado pelo agente de fechamento do M0.
- `560c94c` **`pnpm test` rodava o Playwright** porque `tests/e2e` expunha `test`; renomeado para `e2e` (CI ajustado).
- `d76a0cf` **`worker` do compose saía com 0 sem fazer nada**; substituído por `market-worker` com `restart: unless-stopped` e healthcheck; papéis sem pacote falham explicitamente (implementado pela Astra).
- `b2e48b5` **`setup_env.ps1` gravava o `.env` numa linha só** (precedência da vírgula sobre `+` no PowerShell).
- `541ef78` **500 em toda rota `/[orgSlug]`**: menu passava função e componente do servidor para o cliente.
- `744fdf8` **8 testes dependentes de ordem** por balde de rate limit compartilhado entre TestClients.
