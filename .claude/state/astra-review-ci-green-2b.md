## RESUMO

**REQUEST_CHANGES por um defeito operacional encoberto pela troca de data.** Nos quatro pontos destacados — `received_at`, `isolate_catalogue`, relógio do replay e `operator/5+6` — não encontrei defeito atual de produção demonstrável sendo escondido.

**A matriz RBAC corresponde aos routers.** Não confirmei o CI Linux verde: esta revisão foi estática.

## ARQUIVOS

Nenhum arquivo criado ou modificado.

## TESTES

- Contagem estática: `RBAC_ENTRIES=48`, `ISOLATION_ENTRIES=48`, `TENANT_OPERATIONS=48` no OpenAPI versionado.
- `git diff --check -- <arquivos revisados>`: sem erros; somente avisos de CRLF.
- **Pytest, lint e typecheck não executados**, preservando o modo somente leitura. Não estou ratificando os resultados da reprodução Linux.

## MUST-FIX

**MEDIUM — escolher um dia sem diário contorna uma colisão real do fechamento operacional.**

A mudança para 29/09 evita expressamente o caso em que já existe `Diario/<dia>.md` ([teste:55](C:/dev/project-hunter/infra/scripts/tests/test_meme_close_day_integration.py:55)).

**Cenário concreto:** já existe `Diario/2026-10-05.md`, referenciado por `[[2026-10-05]]` em [REA.md:42](C:/dev/project-hunter/obsidian/04-AGENTS/REA.md:42). Fechar esse mesmo dia cria `Diario-Meme/2026-10-05.md`; o fechamento verifica apenas seu próprio destino ([meme_close_day.py:118](C:/dev/project-hunter/infra/scripts/meme_close_day.py:118)). O link passa a ter dois candidatos, classificados como ambíguos pelo [resolvedor:87](C:/dev/project-hunter/infra/scripts/obsidian_lint_links.py:87), e o [linter:127](C:/dev/project-hunter/infra/scripts/obsidian_lint.py:127) retorna erro.

Isso foi conferido estruturalmente, sem criar o segundo arquivo. **É um defeito da ferramenta/base operacional, não do motor de negociação.** Corrigiria os links de diário para caminhos qualificados e preservaria um teste de coexistência dos dois diários. A data nova pode servir ao cenário básico, mas não demonstra que a falha anterior era exclusivamente de teste.

## NICE-TO-HAVE

- **Restringir a fixture de snapshots aos testes que precisam dela.** O `autouse` substitui integralmente o SQL real ([conftest.py:142](C:/dev/project-hunter/services/meme-worker/tests/conftest.py:142)), inclusive no teste que pretende verificar persistência e idempotência ([test_persistence.py:171](C:/dev/project-hunter/services/meme-worker/tests/test_persistence.py:171)). Não encontrei divergência atual, mas uma regressão futura no `INSERT` real poderia escapar.
- **Comparar conjuntos de método+caminho nas matrizes.** Hoje os guardas comparam apenas quantidades ([RBAC:396](C:/dev/project-hunter/apps/api/tests/integration/test_rbac_matrix.py:396), [isolamento:169](C:/dev/project-hunter/apps/api/tests/integration/test_isolation.py:169)); uma duplicação compensando uma omissão manteria a contagem verde.

## O QUE EU FARIA DIFERENTE

Separaria o conserto determinístico das fixtures da regressão operacional dos diários. Também manteria pelo menos um teste de persistência de snapshot executando o SQL original, sem a fixture global.

## CONCORDO COM

- **`received_at = observed_at` para dados plantados:** coerente com o cenário histórico. A proteção contra chegada tardia continua testada por inserção explícita, com exclusão antes e inclusão depois do recebimento ([test_lab_fast.py:230](C:/dev/project-hunter/services/meme-worker/tests/test_lab_fast.py:230)).
- **`isolate_catalogue`:** prepara o catálogo esperado; não substitui o carregador nem seus filtros. Altera os estados das versões no banco de teste ([builders.py:674](C:/dev/project-hunter/services/strategy-worker/tests/builders.py:674)).
- **Relógio de `replay_io`:** o patch fica limitado ao bootstrap ([test_m2_pipeline.py:267](C:/dev/project-hunter/tests/integration/test_m2_pipeline.py:267)); produção continua usando `max(now, utcnow())` ([replay_io.py:127](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/replay_io.py:127)).
- **`operator/5` e `operator/6`:** corresponde à migração, que acrescenta a segunda mesa e preserva a primeira ([meme_operator_6.py:141](C:/dev/project-hunter/infra/migrations/ddl/meme_operator_6.py:141)).
- **RBAC:** as 19 entradas novas seguem leitura `VIEWER` e seis escritas `TRADER`, conforme [meme_desk.py:60](C:/dev/project-hunter/apps/api/hunter_api/routers/meme_desk.py:60), [meme_live.py:51](C:/dev/project-hunter/apps/api/hunter_api/routers/meme_live.py:51) e [lab_daily_goal.py:40](C:/dev/project-hunter/apps/api/hunter_api/routers/lab_daily_goal.py:40).

Não identifiquei outra falha Linux demonstrável nas alterações examinadas; isso não substitui uma execução integral.

## OBSIDIAN

- **CI-verde-2026-10-05** — registrar esta revisão e distinguir verificações estáticas de resultados executados.
- **Open Bugs** — registrar a ambiguidade criada pela coexistência dos diários operacional e meme.
- **Infrastructure** — atualizar as causas do `python-test` e acrescentar o resultado da próxima execução Linux completa.