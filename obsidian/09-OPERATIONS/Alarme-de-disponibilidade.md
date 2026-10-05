---
tags: [operacoes, alarme, vps, github-actions, monitoramento, incidente]
updated: 2026-10-05
status: parcial
owner: devops-engineer
---

# Alarme externo de disponibilidade da VPS

> **Estado em 05/10/2026: escrito e testado à mão contra a VPS viva; ainda não commitado nem executado pelo GitHub.** Só passa a valer depois do commit na `main` e da prova de entrega do e-mail (passo em `docs/DEPLOYMENT.md`, "Alarme externo de disponibilidade").

## Por que existe

A VPS travou em 04/10 ~09:15Z e ficou ~29 h fora sem que ninguém soubesse ([[Open Bugs]] → "A VPS travou em 04/10", [[2026-10-05]]). Antes disso o `scanner-worker` parou de gravar duas vezes (30/09 e 02/10) com `/ready` e heartbeat verdes ([[Scanner-lag-2026-10-01]]). Nada que roda dentro da VPS avisa que a VPS morreu: a sonda precisa ficar fora.

## O que é

Um workflow do GitHub Actions (`.github/workflows/uptime.yml`, cron `3-59/10 * * * *`) que chama `infra/scripts/uptime_check.sh`. Repo público = minutos agendados grátis; nenhum serviço novo, nenhum segredo (só o `GITHUB_TOKEN` padrão, com `issues: write`).

| Checagem | O que prova | O que não prova |
|---|---|---|
| `GET /` → 200–399 (hoje 307) | Caddy e `web` respondendo | dados, banco |
| `GET /api/v1/system/info` → 200 com `git_sha` | Caddy → processo da api | Postgres, Redis, workers (a rota não os toca) |

Três tentativas (30 s e 60 s de espera) antes de declarar falha. Falha = job vermelho (e-mail de run agendada falha para quem editou o `cron` por último) **e** uma issue única "VPS fora do ar" (label `uptime-alarm`), editada no lugar a cada execução vermelha e fechada com comentário na recuperação.

## O que o ensaio de 05/10 mostrou (comandos reais)

- Raiz responde **307** (para `/sign-in`); `/api/ready`, `/api/health`, `/health` e `/ready` dão **404** pelo Caddy: **de propósito**, o `infra/vps/Caddyfile` só encaminha `/api/*` e `/ws`, e `/health`/`/ready` existem só na rede interna (apps/api/hunter_api/health.py). A única rota pública da api é `/api/v1/system/info` (200, `git_sha = 9622f087` em 05/10 15:16Z).
- As demais rotas com carimbo de dado (`/api/v1/system/workers`, `/markets`, `/radar`) dão **401** sem token Clerk.
- Sem `-k` o curl falha com `SEC_E_UNTRUSTED_ROOT`: o certificado do IP é da CA interna do Caddy. Com `-k` a sonda passa; falha simulada (porta fechada, 404 na api) devolve código 1 e relatório.

## Lacuna conhecida: frescor dos dados

**Não existe endpoint público com o carimbo do último dado** (candle, commit do scanner) e nada foi inventado. Sem ele a sonda não pega o caso "scanner parado com `/ready` verde" (30/09, 02/10). O mínimo proposto (revisão da Astra, [[Alarme-de-disponibilidade-astra|a síntese]]): `GET /api/v1/system/freshness`, público, `no-store`, sem símbolos/tenants/posições, com `status`, `observed_at`, `market.final_candle_at` (por universo esperado, não `MAX` global), `scanner.last_commit_at`, `scanner.oldest_uncommitted_at` e `reason_codes`; `503` quando degradado. É mudança de API: tarefa à parte, e a terceira checagem da sonda entra depois. O código local do scanner já tem `scanner_persistence` e `last_commit_at` em `services/scanner-worker/hunter_scanner_worker/health.py` (árvore de trabalho; **não verifiquei se está no deploy da VPS**).

## Limites

Agendador *best effort*; 60 dias sem atividade desativa o cron em repo público; um monitor parado não avisa de si mesmo; `-k` não prova a identidade do servidor (endurecimento: `--cacert` com a raiz pública do Caddy ou domínio com Let's Encrypt). Detalhes e como silenciar em manutenção (`UPTIME_PAUSED=true`): `docs/DEPLOYMENT.md`.

## Relacionadas

[[Monitoring]] · [[Deployment]] · [[Infrastructure]] · [[Open Bugs]] · [[2026-10-05]] · [[Scanner-lag-2026-10-01]] · [[Alarme-de-disponibilidade-astra]]
