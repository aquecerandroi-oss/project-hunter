---
tags: [operacoes, deploy, vps]
updated: 2026-09-06
status: parcial
---

# Deployment

## O que existe hoje

**Dev local** — funcional: `docker compose -f infra/docker/docker-compose.yml up -d --build` sobe `postgres:16-alpine`, `redis:7-alpine`, roda `migrate` uma vez, depois `api` (porta 8000 + 8001 de health), `worker` (sai com 0 — ver [[Workers]]) e `web` (porta 3000). Verificado end-to-end em 2026-09-05 (`.claude/state/milestone.json`): stack sobe, `/health` e `/ready` respondem 200.

**CI** — GitHub Actions (`ci.yml`) roda em todo PR e push na `main`: lint, typecheck, testes Python/web, verificação de migrações (`alembic check`), geração de tipos, scans de segurança, build de imagem Docker, e2e (Playwright, condicional), `forbidden-patterns`. Ver [[Infrastructure]].

## O que é planejado, ainda não configurado de fato

| Ambiente | Web | API + workers | Postgres | Redis |
|---|---|---|---|---|
| Preview (PR) | Vercel preview | Railway PR environment (opcional) | Neon branch | Upstash dev |
| Staging | Vercel | Railway | Neon branch `staging` | Redis Railway |
| Produção | Vercel | Railway ou Fly.io | Neon `main` (pooler) | Redis Railway / Upstash fixo |

Nenhum desses ambientes remotos está provisionado ainda — o M0 entrega "deploy manual em Railway + Vercel documentado e testado uma vez" como critério de saída, mas o foco deste levantamento é o estado do código, não a infraestrutura externa provisionada.

**Deploy automatizado planejado:** `deploy-api.yml` (`railway up` por serviço ou `fly deploy`) e `deploy-web.yml` (integração nativa Vercel) só rodam se as 8 primeiras etapas do CI passarem. Migrações rodam como job separado antes dos serviços novos subirem, com lock em Redis.

## Playbook de incidente (especificado; sem produção real para exercitar ainda)

| Sintoma | Ação prevista |
|---|---|
| Exchange offline | `data_degraded`; entradas bloqueadas; posições geridas com último preço |
| Redis fora | Workers pausam consumo com buffer de 60 s; api serve REST do Postgres |
| Postgres lento | Escritas em lote com fila limitada; propostas não decididas sem persistir |
| Execution-worker morto | Nenhuma ordem nova; reconstrói posições ao subir |
| Perda súbita anormal | OWNER aciona kill switch da org; operador pode acionar o de sistema |
| Suspeita de vazamento de tenant | Revogar sessão no Clerk; auditar `audit_logs`; RLS é a barreira final |

## VPS (Contabo) — operação 24/7

**Estado (2026-09-06):** VPS **no ar**, `vmi3483069`, rodando `hunter-api:75fc59c` e
`hunter-web:75fc59c`. Sete containers `healthy`: `api`, `web`, `caddy`, `postgres`, `redis`,
`market-worker` e — desde 2026-09-06 03:36 UTC — o **`strategy-worker` do Shadow Lab**, com
`momentum v1` e `volume_anomaly v1` ativadas pelo script auditado. Migração em `0003_analysis`.
Prova operacional em `.claude/state/vps-lab-proof.md`; resultado em [[Experiments Index]].

**Duas armadilhas de deploy descobertas ao subir o Lab** (as duas em [[Open Bugs]]):

1. **Todo serviço novo que fala com o Postgres precisa do seu bloco em
   `infra/vps/docker-compose.prod.yml`.** O override **não** herda o que não menciona: o
   `strategy-worker` existia só no compose base, herdou o `x-api-env` de desenvolvimento e morreu em
   loop com `InvalidPasswordError`. Corrigido em `75fc59c`.
2. **O `seed` é de bootstrap, não de deploy — e hoje não pode ser repetido.** `compose.sh update`
   roda `migrate` e nunca `seed`; a VPS coletava mercado havia horas (526 mercados, 367 mil velas)
   com **zero** linhas em `strategies`, `strategy_versions` e `feature_definitions`. Rodado à mão
   uma vez, com
   `bash infra/vps/compose.sh run --rm -e HUNTER_COMMAND=seed --entrypoint /app/infra/docker/entrypoint.sh migrate`.
   **Não o coloque no `update` como está:** depois da primeira ativação de uma `strategy_version`, o
   seed tenta sobrescrever o `code_ref` congelado, a trigger recusa e **a transação inteira reverte**
   — as oito tabelas. Reproduzido nesta VPS em 2026-09-06. Antes de automatizar, o seed precisa
   preservar versões ativadas, com teste `seed → ativação → seed`. Ver [[Open Bugs]].

Uma VPS Ubuntu 22.04/24.04 roda a mesma stack do compose de dev mais um override de produção, para o `market-worker` coletar mercado sem o PC ligado e para sessões de desenvolvimento por SSH (Claude Code e Codex funcionam melhor em Linux — o sandbox do Codex só funciona lá).

| Arquivo | O que faz |
|---|---|
| `infra/scripts/bootstrap_vps.sh` | prepara a máquina (Docker, Node 22, pnpm, uv, ufw, fail2ban, unattended-upgrades, swap 4 GB, usuário de deploy, clone, cron do backup). Idempotente. |
| `infra/scripts/setup_env.sh` | cria o `.env` com digitação oculta (`--vps`). Versão bash do `setup_env.ps1`. |
| `infra/vps/docker-compose.prod.yml` | `restart: always`, portas fechadas, `HUNTER_ENV=staging`, Caddy, logs com rotação. |
| `infra/vps/Caddyfile` | `/api/*` e `/ws` → api; resto → web; TLS automático com domínio. |
| `infra/vps/compose.sh` | atalho do `docker compose` (dois `-f`, `--env-file`, nome de projeto). |
| `infra/vps/backup_postgres.sh` | `pg_dump -Fc` diário em `/opt/backups`, retenção 7 dias, dump validado antes da retenção. |

Decisões: `HUNTER_ENV=staging` (não `production` — Clerk ainda é instância de dev e `ENABLE_LIVE_TRADING=false`); Caddy em vez de nginx (TLS automático, 40 linhas de config); origem única para o navegador (sem CORS; `/health`, `/ready` e `/metrics` inalcançáveis de fora); só 22/80/443 públicas, api e web em `127.0.0.1`, Postgres e Redis sem porta publicada — **portas publicadas pelo Docker furam o ufw**, então a defesa é não publicar. Detalhe completo em `docs/DEPLOYMENT.md` §9 e `infra/vps/README.md`.

Limitações: uma máquina só (sem HA, sem réplica, sem backup fora do host), Clerk em instância de desenvolvimento, sem monitoramento externo (nada avisa se a VPS inteira cair).

## Relacionadas

[[Infrastructure]] · [[Environment Variables]] · [[Monitoring]] · [[Workers]] · [[Experiments Index]] · [[Open Bugs]]

## Fontes

`docs/DEPLOYMENT.md`, `infra/vps/README.md`, `.claude/state/vps.md`, `.claude/state/milestone.json`
