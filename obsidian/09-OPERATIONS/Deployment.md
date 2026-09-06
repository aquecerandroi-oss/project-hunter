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

**Estado (2026-09-06 13:29 UTC):** VPS **no ar** na imagem `88bac0b`, `vmi3483069`. Sete containers,
os seis com healthcheck em `healthy`: `api`, `web`, `caddy`, `postgres`, `redis`, `market-worker` e
— desde 2026-09-06 03:36 UTC — o **`strategy-worker` do Shadow Lab**, com `momentum v1` e
`volume_anomaly v1` ativadas pelo script auditado. Migração em `0003_analysis`. `/ready` responde
**200**. Zero exceção nos logs das últimas 24 h nos dois workers. Disco 32 GB de 348 (10%), memória
2,1 GB de 47. Prova operacional em `.claude/state/vps-lab-proof.md`; resultado em
[[Experiments Index]] e nas avaliações datadas de [[EXP-0001-momentum-v1]] e
[[EXP-0002-volume-anomaly-v1]].

### HTTPS no IP puro, com certificado interno (`7e00f3b`, `88bac0b`)

Ainda não há domínio, então a VPS é acessada pelo endereço IP — e isso exigiu duas correções que
não são óbvias:

1. **HTTP puro não serve.** Os cookies de sessão do Clerk são `Secure`, então o navegador
   simplesmente não os guardava e o sign-in entrava em **laço infinito** de redirecionamento. O
   Caddy passou a emitir um certificado com a **CA interna** dele (`tls internal`). O navegador
   mostra um aviso de certificado não confiável — **isso é esperado** enquanto não houver domínio;
   quem for entrar tem de aceitar o aviso uma vez.
2. **Navegador não manda SNI quando o destino é um IP.** Sem SNI o Caddy não sabia qual site servir
   e respondia o handshake TLS com `internal error`; o Chrome mostrava `ERR_SSL_PROTOCOL_ERROR` e
   nada carregava. Corrigido com `default_sni`, que o `compose.sh` deriva de `HUNTER_SITE_ADDRESS`
   (a variável do compose de produção; `HUNTER_TLS_ARG` seleciona `internal` ou o e-mail do ACME
   quando houver domínio). Depois disso o Everton **abriu e viu** o `/ever/lab` em
   `https://169.58.116.99`.

### Incidente resolvido — uma chave do Clerk colada no prompt errado

O `setup_env.sh` perguntava por `CLERK_ISSUER` aceitando qualquer texto. Um `sk_test_` digitado ali
virou "issuer", quebrou o JWKS em silêncio e derrubou **toda** a autenticação da VPS — o sintoma
apareceu longe da causa. Resolvido em duas frentes, nesta ordem: **o Everton trocou a chave** (a
antiga está revogada; o valor nunca foi registrado no repositório, nesta base ou em log), e
`bf1c382` fez o script **recusar** um `CLERK_ISSUER` que não seja URL. A regra que fica é
operacional, não de disciplina: **nenhuma chave é digitada em prompt que não seja o da própria
chave** — e agora o script impede. Ver [[Resolved Bugs]].

### O backup nunca rodou — HIGH aberto em 2026-09-06

A tabela abaixo diz que `backup_postgres.sh` faz um dump diário. **Ele nunca fez nenhum.**
`/opt/backups` contém só `backup.log`, com uma linha: `Permission denied`. O arquivo é rastreado no
git como `100644` (sem bit de execução) e a linha do cron instalada por
`infra/scripts/bootstrap_vps.sh:346` invoca o caminho **diretamente**, em vez de `bash <caminho>` —
que é como o cabeçalho do próprio script manda rodá-lo e como `compose.sh` e `astra.sh` são sempre
invocados. Não existe um único dump desta VPS. Detalhe, cenário e as duas opções de correção em
[[Open Bugs]]. **Enquanto isso não for corrigido, a pesquisa do Shadow Lab está sem rede** — e ela
é a única coisa aqui que não se refaz coletando de novo, porque `signal_outcomes` avança no lugar.

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
   preservar versões ativadas, com teste `seed → ativação → seed`. **Corrigido em `2587b9f`** (o seed nunca mais toca uma `strategy_version` ativada, com o teste `seed → ativação → seed`); ver [[Resolved Bugs]].

Uma VPS Ubuntu 22.04/24.04 roda a mesma stack do compose de dev mais um override de produção, para o `market-worker` coletar mercado sem o PC ligado e para sessões de desenvolvimento por SSH (Claude Code e Codex funcionam melhor em Linux — o sandbox do Codex só funciona lá).

| Arquivo | O que faz |
|---|---|
| `infra/scripts/bootstrap_vps.sh` | prepara a máquina (Docker, Node 22, pnpm, uv, ufw, fail2ban, unattended-upgrades, swap 4 GB, usuário de deploy, clone, cron do backup). Idempotente. |
| `infra/scripts/setup_env.sh` | cria o `.env` com digitação oculta (`--vps`). Versão bash do `setup_env.ps1`. |
| `infra/vps/docker-compose.prod.yml` | `restart: always`, portas fechadas, `HUNTER_ENV=staging`, Caddy, logs com rotação. |
| `infra/vps/Caddyfile` | `/api/*` e `/ws` → api; resto → web; TLS automático com domínio. |
| `infra/vps/compose.sh` | atalho do `docker compose` (dois `-f`, `--env-file`, nome de projeto). |
| `infra/vps/backup_postgres.sh` | `pg_dump -Fc` diário em `/opt/backups`, retenção 7 dias, dump validado antes da retenção. **Nunca executou** — ver o HIGH acima. |

Decisões: `HUNTER_ENV=staging` (não `production` — Clerk ainda é instância de dev e `ENABLE_LIVE_TRADING=false`); Caddy em vez de nginx (TLS automático, 40 linhas de config); origem única para o navegador (sem CORS; `/health`, `/ready` e `/metrics` inalcançáveis de fora); só 22/80/443 públicas, api e web em `127.0.0.1`, Postgres e Redis sem porta publicada — **portas publicadas pelo Docker furam o ufw**, então a defesa é não publicar. Detalhe completo em `docs/DEPLOYMENT.md` §9 e `infra/vps/README.md`.

Limitações: uma máquina só (sem HA, sem réplica, sem backup fora do host), Clerk em instância de desenvolvimento, sem monitoramento externo (nada avisa se a VPS inteira cair).

## Relacionadas

[[Infrastructure]] · [[Environment Variables]] · [[Monitoring]] · [[Workers]] · [[Experiments Index]] · [[Open Bugs]]

## Fontes

`docs/DEPLOYMENT.md`, `infra/vps/README.md`, `.claude/state/vps.md`, `.claude/state/milestone.json`
