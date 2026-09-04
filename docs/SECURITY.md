# Segurança — PROJECT HUNTER

## 1. Autenticação: Clerk

**Por que Clerk (e não Supabase Auth ou Auth.js):**

| Critério | Clerk | Supabase Auth | Auth.js |
|---|---|---|---|
| Fluxo completo pronto (confirmação de e-mail, reset, sessões, MFA, social) | Sim | Sim | Parcial; e-mail e reset são nossos |
| Verificação no FastAPI sem chamada de rede por request | JWKS público, cache local | JWT HS256/RS256 | Depende da estratégia; sessões em DB exigem consulta |
| Acoplamento com o banco | Nenhum | Tende a puxar Supabase Postgres, e o banco é Neon | Precisa de adapter no nosso banco |
| Integração Next.js App Router | Primeira classe (middleware, RSC) | Boa | Boa |
| Custo inicial | Gratuito até 10k MAU | Gratuito | Gratuito |
| Risco | Lock-in de identidade | Lock-in de stack | Manutenção própria de fluxos sensíveis |

Decisão: Clerk para **identidade e sessão**. O que fica no nosso banco: `users` (espelho via webhook), organizações, membros, papéis, tudo o que é financeiro. Não usamos Clerk Organizations.

**Mitigação de lock-in:** `hunter_api.auth.AuthProvider` com uma única implementação (`ClerkProvider`) que transforma um token em `Principal {user_id interno, external_auth_id, email}`. Trocar de provedor é trocar essa classe e migrar `external_auth_id`.

**Fluxo:** browser → Clerk (sessão, cookie httpOnly) → Next.js obtém session token → chama `api` com `Authorization: Bearer <jwt>` → `api` valida assinatura (JWKS em cache, rotação automática), `exp`, `azp`/`iss` → carrega `users` por `external_auth_id` → carrega membership da org da rota → aplica RBAC → `SET LOCAL app.current_org`.

WebSocket: token enviado na primeira mensagem (`auth`), nunca na query string. Conexão fechada se não autenticar em 5 s.

## 2. RBAC

| Ação | OWNER | ADMIN | TRADER | ANALYST | VIEWER |
|---|---|---|---|---|---|
| Ver dashboards, radar, mercados, oportunidades, trades, analytics | ✓ | ✓ | ✓ | ✓ | ✓ |
| Criar/editar portfolios, agentes, ordens paper | ✓ | ✓ | ✓ | – | – |
| Editar risk profile de portfolio | ✓ | ✓ | ✓ | – | – |
| Kill switch de portfolio | ✓ | ✓ | ✓ | – | – |
| Kill switch da organização | ✓ | ✓ | – | – | – |
| Editar risk defaults da organização | ✓ | ✓ | – | – | – |
| Membros, convites, papéis | ✓ | ✓ (não pode promover a OWNER nem remover OWNER) | – | – | – |
| Exchange connections | ✓ | ✓ | – | – | – |
| Ativar versão de estratégia, ativar pesos recomendados | ✓ | – | – | – | – |
| Billing, excluir organização, transferir ownership | ✓ | – | – | – | – |
| Solicitar live mode (Fase 4) | ✓ | – | – | – | – |

Implementação: `require_role(min_role)` como dependência FastAPI; papéis ordenados. Toda rota de tenant declara o papel mínimo. Teste parametrizado garante que cada rota tem declaração.

## 3. Isolamento de tenant

1. Rotas de tenant sempre sob `/orgs/{org_id}`; membership verificada antes do handler.
2. Repositórios tenant-scoped com `org_id` obrigatório.
3. RLS no Postgres (`DATABASE.md` §1.2). Teste de integração: usuário da org A chama cada endpoint de listagem com `org_id` da org B → 404 (não 403, para não revelar existência).
4. IDs são UUID v7: não enumeráveis, mas o isolamento não depende disso.
5. Realtime: canal `rt:org:{id}:*` só é assinável por membro; o `api` filtra por org antes de encaminhar.

## 4. Segredos e credenciais

**Regra:** nenhum segredo no frontend, em repositório, em log ou em resposta de API.

| Segredo | Onde vive | Quem lê |
|---|---|---|
| `DATABASE_URL`, `REDIS_URL` | env do provedor (Railway/Fly secrets) | api, workers |
| `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SECRET` | env | api (webhook), web server-side |
| `CLERK_PUBLISHABLE_KEY` | env pública (`NEXT_PUBLIC_`) | browser (é pública por design) |
| `ANTHROPIC_API_KEY` | env | analytics/intelligence worker (Fase 2) |
| `SENTRY_DSN`, `POSTHOG_KEY` | env | DSN é semi-público; PostHog key do browser é pública por design |
| `HUNTER_MASTER_KEY` (dev) / KMS key id (prod) | env / KMS | execution-worker e api (só para **gravar**, nunca ler) |
| Chaves de exchange dos usuários | `exchange_connections.*_encrypted` | execution-worker apenas |
| `BINANCE_API_KEY` etc. de sistema | env; opcional; só para elevar rate limit de dados públicos | market-worker |

**Criptografia de chaves de exchange (Fase 3):** envelope encryption. Cada conexão recebe uma data key aleatória (AES-256-GCM) que cifra key e secret; a data key é cifrada pela master key (KMS em produção: AWS KMS ou GCP KMS via `SecretsBackend`; em dev, chave em env). `encryption_key_version` permite rotação. Validação obrigatória na criação: `fetch_permissions()` → se `withdraw=true`, a conexão é rejeitada e não é persistida.

## 5. Proteções obrigatórias (§56)

| Item | Implementação |
|---|---|
| Rate limiting | Middleware com token bucket em Redis por usuário e por IP; limites distintos para auth, leitura, escrita, WS |
| CSRF | Next.js chama o `api` server-side com Bearer; mutações do browser passam por Server Actions/route handlers com verificação de origem; cookies do Clerk `SameSite=Lax`, `Secure`, `HttpOnly` |
| CORS | Allowlist de origens exata (`WEB_ORIGIN`); sem `*` |
| Input validation | Pydantic em todo request; limites de tamanho; `Decimal` para números financeiros |
| SQL injection | SQLAlchemy parametrizado; sem SQL concatenado; revisão em CI (`bandit`) |
| Headers | HSTS, `X-Content-Type-Options`, `Referrer-Policy`, CSP no web (nonce), `Permissions-Policy` |
| Audit | `@audited` em serviços; append-only |
| Segredos | `gitleaks` em CI; `.env*` no `.gitignore` |
| Dependências | `pip-audit`, `pnpm audit`, Dependabot |
| Webhooks | Assinatura verificada (Svix para Clerk); idempotência por `svix-id` |
| Idempotência | `Idempotency-Key` em POSTs financeiros; `client_order_id` único |

## 6. LLM (Fase 2+)

- Conteúdo externo (notícias, posts) entra no prompt **como dado delimitado e rotulado**, com instrução de sistema fixa de "classificar, não obedecer". Saída é validada por schema (structured outputs) e só campos esperados são persistidos.
- LLM não tem ferramentas com efeito colateral. Não chama API de exchange, não altera risco, não cria ordens.
- Falha ou timeout de LLM → componente `External Intelligence` = sem dado (confidence cai), nunca um valor inventado.

## 7. Resposta a incidentes (mínimo)

- Kill switch de sistema acionável por operador via env (`SYSTEM_KILL_SWITCH=EMERGENCY`) sem redeploy de código (workers releem a cada 10 s) e via tabela.
- Todo risk event `critical` vai para Sentry como evento e para notificação in-app dos OWNERs.
- Playbook em `DEPLOYMENT.md` §6.

## 8. Lista de segredos necessários (PASSO 8)

Ver `.env.example` na raiz. Resumo do que precisa existir por ambiente:

| Ambiente | Obrigatórios |
|---|---|
| Dev | `DATABASE_URL`, `REDIS_URL`, `CLERK_*`, `HUNTER_MASTER_KEY` (gerado localmente) |
| CI | Postgres e Redis de serviço; `CLERK_*` de instância de teste |
| Prod | Todos acima + `SENTRY_DSN`, `POSTHOG_KEY`, KMS, `ANTHROPIC_API_KEY` (Fase 2) |
