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
