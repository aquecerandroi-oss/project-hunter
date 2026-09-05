---
tags: [bugs, resolvidos]
updated: 2026-09-05
---

# Resolved Bugs

Correções reais extraídas do `git log`, todas dentro do Milestone 0. A maioria veio de rodadas de revisão de segurança/qualidade (T04–T10 no plano `docs/plans/M0.md`), não de bugs reportados em produção — não houve produção ainda.

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
