**RESUMO**

A solução garante a sequência proposta, com uma condição: `optional_org_derivation` deve **retornar**, sem manter sessão aberta via `yield`. Eu preferiria `async with` no corpo pela simplicidade e preservação das validações.

**ARQUIVOS**

Nenhum criado ou modificado. Revisão no escopo de `backend-specialist`.

**TESTES**

Não executados; análise estática e consulta às fontes oficiais.

**MUST-FIX**

- **Envolver também todo o `user_session` de `analysis_session` no tradutor 503**, incluindo entrada e saída. Cenário: sem `org_id`, pool esgotado falha no primeiro `SET LOCAL`, antes do corpo da rota, continuando como 500. A sessão executa SQL antes de entregar o controle ([session.py:160](C:/dev/project-hunter/packages/core/hunter_core/db/session.py:160)); o tradutor atual reconhece explicitamente essa lacuna ([radar_common.py:131](C:/dev/project-hunter/apps/api/hunter_api/repositories/radar_common.py:131)).
- **O teste com pool 1 deve cobrir radar, lista e detalhe de oportunidades**, com organização autorizada e oportunidade existente. Cenário: corrigir a lista e esquecer o detalhe mantém a aquisição aninhada em [opportunities.py:102](C:/dev/project-hunter/apps/api/hunter_api/routers/opportunities.py:102).

**NICE-TO-HAVE**

Teste `TimeoutError → 503`, mantendo `IntegrityError → 500`, e fixe a precedência para `limit=0` junto de organização inacessível.

**O QUE EU FARIA DIFERENTE**

**(c)** Removeria `PrincipalSession` dessas rotas e usaria a sequência explícita no corpo: resolver organização → carregar derivação → `async with user_session(...)`. Um `postgres_failures_as_503()` externo envolve tudo. Evita duas novas dependências e preserva a validação declarativa antes da derivação.

**(d)** Sim, sua proposta muda precedência: as dependências são resolvidas antes dos parâmetros próprios da rota. Assim, `limit=0` com org inacessível pode passar de 422 para 404. Isso decorre do [resolvedor do FastAPI](https://raw.githubusercontent.com/fastapi/fastapi/master/fastapi/dependencies/utils.py). **Cursor inválido não é um exemplo novo dessa regressão**: hoje a organização já é resolvida antes da decodificação do cursor ([opportunities.py:71](C:/dev/project-hunter/apps/api/hunter_api/routers/opportunities.py:71), [opportunities.py:79](C:/dev/project-hunter/apps/api/hunter_api/routers/opportunities.py:79)).

**CONCORDO COM**

**(a)** A dependência explícita garante a ordem; a devolução vem do `async with` encerrado em [radar_org_derivation.py:86](C:/dev/project-hunter/apps/api/hunter_api/services/radar_org_derivation.py:86), antes do retorno. Reutilizando o mesmo alias/callable com cache padrão, a derivação executa uma vez. `scope="function"` encerra generators **depois do handler**, não antes da dependência seguinte; portanto não substitui esse fechamento explícito. [FastAPI](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/)

**(b)** `sqlalchemy.exc.TimeoutError → 503` é correto: representa indisponibilidade de capacidade, mesmo quando causada por bug. O status não absolve a causa; mantenha log/métrica para investigar retenção excessiva de conexões. [SQLAlchemy](https://docs.sqlalchemy.org/en/20/errors.html#queuepool-limit-of-size-x-overflow-y-reached-connection-timed-out-timeout-z)

Limite: isso não cobre timeout durante autenticação, cujo tratamento continua restrito a `OperationalError/OSError` ([principal.py:203](C:/dev/project-hunter/apps/api/hunter_api/auth/principal.py:203)).

**OBSIDIAN**

- **System Overview** — registrar sessões sequenciais de análise e alcance do tratamento 503.
- **Revisoes-Astra/Index** — vincular esta revisão de T2.6 e a decisão sobre precedência das validações.