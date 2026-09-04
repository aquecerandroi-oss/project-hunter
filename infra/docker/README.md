# docker

Conteúdo definido em `docs/ARCHITECTURE.md` §7; comandos de uso em `README.md` ("Docker") e detalhes de deploy em `docs/DEPLOYMENT.md` §2–§3.

- `Dockerfile.api-workers` — imagem única para `api` + todos os workers; `HUNTER_ROLE` escolhe o processo em `entrypoint.sh`.
- `Dockerfile.web` — build standalone do Next.js.
- `entrypoint.sh` — dispatch por `HUNTER_ROLE`/`HUNTER_COMMAND` (ver comentários no arquivo — `migrate`/`seed` não são valores válidos de `Settings.hunter_role`, por isso usam `HUNTER_COMMAND`).
- `healthcheck.py` / `healthcheck-web.mjs` — probes usados pelo `HEALTHCHECK` de cada imagem (sem `curl` nas imagens slim).
- `docker-compose.yml` — stack de desenvolvimento (postgres, redis, migrate, api, worker, web).
- `docker-compose.test.yml` — só postgres/redis efêmeros, para rodar testes de integração locais sem testcontainers.
