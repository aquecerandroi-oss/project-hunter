**RESUMO**

`REQUEST_CHANGES`: o invariante de conexões está preservado nos caminhos examinados, mas o tratamento de indisponibilidade ainda tem lacunas.

**ARQUIVOS**

Nenhum arquivo criado ou modificado.

**TESTES**

Não executei testes nesta revisão somente leitura; os resultados informados não foram revalidados.

**MUST-FIX**

- **MEDIUM — timeout antes do handler ainda vira 500.** `CurrentPrincipal` resolve autenticação antes de `analysis_scope`; o resolver captura somente `OperationalError` e `OSError`. Cenário: pool ocupado por outras requisições, `_load` esgota o timeout e a requisição retorna 500, sem alcançar o novo tradutor. Ver [rbac.py:116](/C:/dev/project-hunter/apps/api/hunter_api/auth/rbac.py:116) e [principal.py:203](/C:/dev/project-hunter/apps/api/hunter_api/auth/principal.py:203). O tradutor também não captura `OSError`: uma conexão nova recusada **depois** da autenticação continua podendo virar 500 ([radar_common.py:173](/C:/dev/project-hunter/apps/api/hunter_api/repositories/radar_common.py:173)).
- **MEDIUM — contrato TypeScript desatualizado.** A lista removeu `decomposition`, mas o tipo gerado ainda o exige. Um consumidor tipado pode acessar um objeto que chega como `undefined`. Regerar antes de fechar T2.6: [api.d.ts:1465](/C:/dev/project-hunter/packages/shared-types/src/generated/api.d.ts:1465), [schemas/opportunities.py:84](/C:/dev/project-hunter/apps/api/hunter_api/schemas/opportunities.py:84).

**NICE-TO-HAVE**

- **Paginação mutável precisa de nota explícita.** Após cursor em score 80, uma linha ainda não vista que sobe de 70 para 90 desaparece da continuação; uma já vista que cai de 90 para 70 pode reaparecer. Aceitável para ranking vivo, não para exportação completa. O predicado está correto para dados estáveis ([opportunities.py:200](/C:/dev/project-hunter/apps/api/hunter_api/repositories/opportunities.py:200)).
- **Cobertura tem duas lacunas:** os dois testes `testresolve_history_limit...` não seguem o padrão padrão `test_*` de coleta ([teste:274](/C:/dev/project-hunter/apps/api/tests/unit/test_analysis_read_models.py:274)); os scores empatados ficam **na mesma página**, portanto não exercitam desempate na fronteira ([teste:184](/C:/dev/project-hunter/apps/api/tests/integration/test_opportunities_api.py:184)).
- **Escape correto, cobertura parcial:** escapa primeiro `\`, depois `%` e `_`, com `escape` explícito. Há unitário dos três caracteres, mas integração somente de `%` sem correspondência; faltam correspondências positivas e opportunities ([helper:82](/C:/dev/project-hunter/apps/api/hunter_api/repositories/radar_common.py:82), [teste:438](/C:/dev/project-hunter/apps/api/tests/integration/test_radar_api.py:438)).

**O QUE EU FARIA DIFERENTE**

Documentaria “paginação sobre ranking vivo” e acrescentaria `history_has_more`/limite efetivo ao detalhe. O default adaptativo está documentado e não altera limite explícito, mas não informa se existe histórico além da janela retornada ([router:140](/C:/dev/project-hunter/apps/api/hunter_api/routers/opportunities.py:140)).

**CONCORDO COM**

- **Uma conexão simultânea:** derivação fecha antes da sessão global; 404/422 desenrolam os contextos. Montagem posterior é segura: dados materializados e `expire_on_commit=False`, sem necessidade de nova consulta ([scope:86](/C:/dev/project-hunter/apps/api/hunter_api/routers/radar_common.py:86), [session.py:91](/C:/dev/project-hunter/packages/core/hunter_core/db/session.py:91)).
- Opportunities oferece **somente DESC**, corretamente com `<`; ASC/DESC existem no radar, com comparadores correspondentes ([radar.py:244](/C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:244)).
- Não identifiquei nova violação de Decimal, UTC, RLS ou fabricação de dados nas correções examinadas.

**OBSIDIAN**

- **System Overview** — registrar sessões sequenciais e as lacunas restantes de 503.
- **Data Flow** — registrar paginação mutável e decomposição exclusiva do detalhe.
- **Revisoes-Astra/Index** — vincular esta revisão e suas pendências.