# Kit de revisão — T1.6 · Operação contínua (Docker, docs, base Obsidian)

**Owner:** `devops-engineer` + `documentation-writer` (Claude, sonnet) · **Estado:** T1.6a (compose + entrypoint) **já commitado** em `d76a0cf` pela Astra; o resto (T1.6b) não começou — onda 2
**Files (do plano):** `infra/docker/**`, `docs/DEPLOYMENT.md`, `README.md`, `obsidian/**`
**Depends-on:** T1.3
**Commit esperado:** `feat(ops): market-worker service running continuously`

> Metade da tarefa já está na árvore: `d76a0cf feat(ops): market-worker compose service (restart unless-stopped, /ready healthcheck); entrypoint dispatches worker roles honestly (T1.6a, implemented by Astra)`. A revisão abaixo cobre **o commit já feito** (validação operacional pendente) **e** o que falta: docs, README, `obsidian/`.

---

## (a) Checklist da decisão conjunta Claude ⇄ Astra que se aplica a T1.6
Copiada literalmente de `.claude/state/dialogue-M1.md` → `## Astra (rodada 4)`.

- [ ] T1.6 — Executar no Compose os cenários operacionais de exceção e retorno inesperado de tarefa principal/filha, silêncio somente na public, conexão presa, persistência bloqueada com fila pendente e shutdown normal; comprovar 503 quando devido, reconexão limitada, saída não zero em falha fatal e restart real do container por `restart: unless-stopped`, sem falso fatal no shutdown. Declaração de healthcheck/restart no arquivo não substitui essa evidência.

Itens de T1.3 cuja **evidência operacional** é cobrada aqui (o contrato é de T1.3, a prova no Compose é de T1.6):

- [ ] T1.3 — Supervisionar tarefas permanentes e filhas ... exceção ou retorno inesperado é fatal e resulta em saída não zero, enquanto cancelamento coordenado de shutdown é normal. Validar falhas de tarefa principal e filha.
- [ ] T1.3 — Aplicar watchdog por conexão public/market ... 30 s sem dado aceito gera warning e reinicia aquela conexão; três reinícios seguidos sem progresso são fatais ... Validar public silenciosa enquanto market continua ativa.
- [ ] T1.3 — Acrescentar `readiness_checks` ao runtime ... vencida a tolerância, retornar 503. Fila pendente sem flush concluído há 30 s também reprova readiness; testar tentativa presa e persistência bloqueada.

## (b) Critérios da linha da tarefa em `docs/plans/M1.md`
- [ ] `infra/docker/entrypoint.sh`: papéis (`market`, etc.) despacham `python -m hunter_market_worker` — sem papel inventado, sem `sleep infinity` disfarçado de worker.
- [ ] `docker-compose.yml`: serviço `market-worker` com `restart: unless-stopped`, `HUNTER_ROLE=market`, healthcheck em `:8001/ready`.
- [ ] `Dockerfile.api-workers` instala os pacotes de worker (`hunter_market_worker` e dependências) — a imagem tem de subir de fato.
- [ ] `docs/DEPLOYMENT.md`: variáveis novas de T1.3 na tabela (`MARKET_UNIVERSE_*`, `MARKET_STALE_AFTER_S`, `MARKET_OI_POLL_S`) e como rodar o worker.
- [ ] `README.md`: quickstart inclui subir o `market-worker`.
- [ ] `obsidian/02-MARKET/*` e `obsidian/01-ARCHITECTURE/Workers.md` atualizados com o que **passou a existir** (status `planejado` → `implementado` só onde há código commitado e verificado).
- [ ] `obsidian/08-CHANGELOG`: uma entrada por commit do M1.
- [ ] Verificação da linha: `docker compose up -d market-worker` + `docker compose logs market-worker` mostram eventos reais; `curl :8000/api/v1/system/workers` lista `market`.

## (c) Regras do `CLAUDE.md` que mais pegam aqui
- [ ] **Sem segredo no repositório nem na imagem:** `.env` não entra no build, nenhuma chave em `docker-compose.yml`, `.env.example` só com placeholders. **Nunca ler `.env`.**
- [ ] **Sem dado falso na documentação:** `obsidian/00-HOME.md` e as páginas de módulo só marcam `implementado` o que tem commit e comando de prova; o resto continua `planejado` com o milestone.
- [ ] `structlog` também no container: log JSON, sem `print`, sem eco de variável sensível na saída de boot.
- [ ] Sem estado local: nenhum volume novo guardando estado de aplicação (Postgres/Redis são os únicos).
- [ ] `check_forbidden_patterns` do CI continua verde.
- [ ] Todo "feito" acompanha o comando e a saída real — declaração em YAML não é prova.

## (d) Comandos de verificação exatos
```bash
export PATH="/c/Program Files/nodejs:/c/Users/evert/AppData/Roaming/npm:/c/Users/evert/AppData/Local/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe:/c/Users/evert/.local/bin:/c/Users/evert/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"
cd /c/dev/project-hunter
docker compose -f infra/docker/docker-compose.yml build market-worker
docker compose -f infra/docker/docker-compose.yml up -d postgres redis api market-worker
docker compose -f infra/docker/docker-compose.yml ps
docker compose -f infra/docker/docker-compose.yml logs --tail=80 market-worker
curl -s localhost:8000/api/v1/system/workers
docker compose -f infra/docker/docker-compose.yml exec market-worker curl -s -o /dev/null -w '%{http_code}\n' localhost:8001/ready
bash infra/scripts/check_forbidden_patterns.sh
```
Cenários operacionais (evidência exigida pela decisão conjunta — cada um com log/saída colada):
1. exceção em tarefa principal → saída **não zero** e restart real do container;
2. exceção em tarefa filha → mesmo comportamento;
3. silêncio só na conexão public (market ativa) → warning + reinício daquela conexão, sem derrubar o processo;
4. conexão presa → readiness `503` depois da tolerância de 120 s monotônicos;
5. persistência bloqueada com fila pendente > 30 s → readiness `503`;
6. `docker compose stop market-worker` → shutdown limpo, **sem** falso fatal e sem saída não zero.

## (e) Revisores a despachar (em paralelo)
| Revisor | Escopo |
|---|---|
| `code-reviewer` | conformidade com a linha T1.6, entrypoint honesto, docs batendo com o código, changelog completo |
| `security-reviewer` | **obrigatório** — imagem e compose: segredo em build arg/env, usuário não-root, portas expostas, `/metrics` protegido, base image e CVEs, `.dockerignore` cobrindo `.env` |
| `devops-engineer` | é o autor da parte de infra; se T1.6a (já commitado) precisar de correção, é ele quem corrige |
| `database-architect` | não se aplica |
| `risk-engine-guardian` | não se aplica no M1 |

## (f) Segunda opinião da Astra (obrigatória, depois do `code-reviewer`)
```bash
bash infra/scripts/astra.sh ask review-T1.6 "Review infra/docker/** (docker-compose.yml, entrypoint.sh, Dockerfile.api-workers), docs/DEPLOYMENT.md, README.md e obsidian/** against docs/plans/M1.md (linha T1.6) e o item T1.6 da DECISÃO CONJUNTA em .claude/state/dialogue-M1.md. Você implementou o T1.6a no commit d76a0cf: seja adversarial com o próprio trabalho. Confira: entrypoint despacha papéis de verdade sem falso worker; restart unless-stopped e healthcheck em :8001/ready realmente exercitados e não só declarados; imagem instala hunter_market_worker; nenhum segredo em build arg, env ou imagem e .dockerignore cobrindo .env; usuario nao-root; documentacao e paginas obsidian marcando implementado somente o que tem commit e prova. Must-fix com cenário de falha, nice-to-have, concordâncias. Não modifique arquivos."
```

## (g) Commit esperado
```
feat(ops): market-worker service running continuously

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```
T1.6a já saiu em `d76a0cf`. O restante (docs + `obsidian/`) pode sair como `docs(m1): deployment, README and obsidian updated for the market pipeline` se ficar separado da infra.
`git -c commit.gpgsign=false commit` · `git push origin main`.

## Decisão do orquestrador sobre o HIGH-1 (worker satura um core, 2026-09-05)
- **Aceite do M1** pode ser com universo reduzido (`MARKET_UNIVERSE_SIZE` = 100, ou o maior valor em que `markets_ok` >= 95% por 10 min sem `market_persist_lag` > 10 s), desde que a API/UI mostrem o número real monitorado. Registrar o número medido.
- **T1.6b (performance do market-worker)**, nova tarefa antes do fechamento do M1: perfilar (py-spy/cProfile no container) e atacar por ordem: parse com `orjson` e sem `pydantic` por evento no caminho quente (validar só na borda), pipelines Redis por lote/coalescência (uma ida por símbolo por ciclo, não por evento), `@depth20@500ms` em vez de 250 ms se o book dominar, `uvloop`/`winloop`, e **sharding** por grupos de símbolos em N processos (`HUNTER_ROLE=market` com `MARKET_SHARD=i/N`) como saída definitiva. Meta: 200 mercados com `markets_ok` >= 95% e CPU < 70% de um core por shard. Métrica nova: `market_ws_backlog_bytes` (Recv-Q) ou idade do último frame lido vs recebido, para o operador ver a saturação.
- Sem isso, nada de M2 sobre dados degradados: o scanner só liga com `markets_ok` estável.

---

# VEREDITO — 2026-09-05, depois da prova operacional

**T1.6: `parcial`.** Prova completa em `.claude/state/t16-proof.md` (1000 linhas, cada item com
comando e saída real). Segunda opinião da Astra em `.claude/state/astra-review-t16-proof.md` —
chegou ao mesmo veredito, de forma independente.

## (a) Checklist da decisão conjunta — situação item a item

- [x] **T1.6 — cenários operacionais no Compose.** Executados: reinício do container, corte
  seletivo de rede só para a Binance (sidecar `NET_ADMIN` no namespace do worker), apagão de
  Postgres, apagão de Redis, e o caminho fatal do watchdog. `503` quando devido: provado.
  Reconexão limitada: provada. Saída não-zero em falha fatal: provada (traceback no topo do
  interpretador; entrypoint devolve 1/0/64). **Restart real do container por `restart:
  unless-stopped`: provado** (`RestartCount` 0 → 1 sozinho). Sem falso fatal no shutdown:
  provado (`Exit=0` no `docker compose restart`). *A declaração no arquivo deixou de ser a
  evidência.*
- [x] **T1.3 — supervisão de tarefas permanentes.** Exceção em tarefa dentro do `TaskGroup` é
  fatal e sai não-zero: provado com traceback real. Cancelamento coordenado é normal: provado.
- [x] **T1.3 — watchdog por conexão.** 30 s sem dado reinicia a conexão; 3 sem progresso é fatal:
  provado no corte de rede, com as duas rotas (`key=public:0`, `key=market:0`) no log.
  *Ressalva:* "só a public silenciosa" **não** foi isolável no nível de rede — as duas rotas
  usam o mesmo host e o mesmo IP (`13.159.59.76:443`). Continua coberto pelo unitário
  `test_watchdog_restarts_only_silent_connection`.
- [x] **T1.3 — `readiness_checks` e 503.** Provado nos três caminhos (`ingestion`, `persistence`,
  `database`). *Achado:* a prontidão **regride** de 503 para 200 sem dado ter chegado
  (MEDIUM, registrado em [[Open Bugs]] e no §MEDIUM-2 da prova).

## (b) Critérios da linha da tarefa em `docs/plans/M1.md`

- [x] `entrypoint.sh` despacha papéis de verdade — e ganhou a ação `partitions`.
- [x] `docker-compose.yml`: `market-worker` com `restart: unless-stopped`, `HUNTER_ROLE=market`,
  healthcheck em `:8001/ready` — agora com orçamentos **medidos** (`timeout: 30s`, `retries: 5`),
  porque os 3 s anteriores davam quatro falsos negativos seguidos.
- [x] `Dockerfile.api-workers` instala os pacotes de worker — a imagem sobe e coleta de verdade.
- [x] `docs/DEPLOYMENT.md` — comando manual de partições documentado.
- [x] `infra/vps/README.md` — cron diário de partições documentado.
- [x] `obsidian/` — [[Market Collector]], [[Monitoring]], [[Changelog]], [[Open Bugs]],
  [[Resolved Bugs]] atualizados com o que passou a ser verdade **e** com o que continua aberto.
- [x] Verificação da linha: `docker compose logs market-worker` mostra eventos reais;
  `/api/v1/system/workers` lista `market` (provado pelo serviço, ver §3 da prova).

## (c) Regras do `CLAUDE.md`

- [x] Nenhum segredo no repositório, na imagem, no compose ou no log. `.env` nunca lido.
- [x] Nenhum dado falso na documentação — o que não foi provado está escrito como não provado.
- [x] `structlog` no container, log JSON, sem `print`.
- [x] Nenhum volume novo de estado de aplicação.
- [x] `forbidden_patterns.sh` → `forbidden-patterns: clean`.
- [x] Todo "feito" acompanha comando e saída real.

## (d) O que **falta** para virar `implementado`

1. Capacidade: o processo satura um core com 200 mercados; hot state de alta frequência não se
   sustenta (HIGH-1, M2).
2. Convergência do backlog de recovery dentro de um prazo definido **antes** do teste.
3. Corrida de 24–48 h atravessando a virada UTC e a rotação de conexão de ~23,5 h da Binance.
4. Apagão externo longo atravessando vários reinícios (proxy fora do worker).
5. Morte abrupta sem chance de limpeza (OOM controlado).
6. HTTP autenticado ponta a ponta com token Clerk.

## (e) Revisores despachados

`code-reviewer` (escopo completo do diff) e `security-reviewer` (obrigatório: imagem, compose,
cron da VPS, segredos, cardinalidade de labels, DoS do retry). Astra respondida e registrada.
