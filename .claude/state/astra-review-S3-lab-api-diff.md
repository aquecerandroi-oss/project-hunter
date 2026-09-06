**RESUMO**

**REQUEST_CHANGES — três must-fix.** O gate de maturação está aplicado consistentemente. Os problemas estão no arredondamento intermediário do PF, na abrangência do tratamento de indisponibilidade e na validação de `as_of`.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO, como `code-reviewer`.

**TESTES**

`uv run pytest apps/api -q -k lab` **não executado**, conforme seu pedido de simulação mental. Li os cenários; os “40 verdes” são informação sua, não resultado verificado nesta rodada.

**MUST-FIX**

1. **HIGH — PF calcula sobre somas já arredondadas.**  
   Em [lab_summary_metrics.py:135](C:/dev/project-hunter/apps/api/hunter_api/services/lab_summary_metrics.py:135), numerador e denominador passam por `quantize4` **antes** de verificar perdas e dividir.

   **Cenário sintético:** `[Decimal("1"), Decimal("-0.00004")]` deveria produzir PF `25000.0000`; produz `null/no_losses`. Com apenas `-0.00004`, deveria produzir PF zero, mas também produz nulo. Tudo continua sendo `Decimal`; o defeito é a ordem das operações.

   **Correção:** somar, verificar denominador e dividir com precisão integral; quantizar apenas os valores de saída. Os testes atuais não incluem perdas abaixo da resolução de apresentação ([test_lab_metrics.py:150](C:/dev/project-hunter/apps/api/tests/unit/test_lab_metrics.py:150)).

2. **MEDIUM — Postgres realmente indisponível pode escapar do 503.**  
   `lab_session` recebe `CurrentPrincipal` antes de executar seu `try` ([lab.py:59](C:/dev/project-hunter/apps/api/hunter_api/routers/lab.py:59)). Essa dependência resolve o usuário ([rbac.py:116](C:/dev/project-hunter/apps/api/hunter_api/auth/rbac.py:116)), consultando Postgres ([principal.py:189](C:/dev/project-hunter/apps/api/hunter_api/auth/principal.py:189)).

   **Cenário:** token válido, Postgres indisponível antes da requisição. A resolução do principal falha antes de entrar em `lab_session`; seu `except` nunca é alcançado. Além disso, capturar somente `OperationalError` não cobre necessariamente recusa de conexão do `asyncpg`, que pode emergir como `OSError`.

   **Correção:** colocar a tradução de indisponibilidade numa fronteira que envolva também a resolução das dependências, reconhecendo as exceções reais de conexão. Acrescentar teste de falha nesse caminho. O monkeypatch atual injeta a exceção somente no repositório ([test_lab_api.py:80](C:/dev/project-hunter/apps/api/tests/integration/test_lab_api.py:80)); não precisa desligar o container compartilhado.

3. **MEDIUM — `as_of` sem fuso é aceito e pode quebrar o summary.**  
   A rota usa `datetime` sem validação de timezone nem normalização UTC ([lab.py:89](C:/dev/project-hunter/apps/api/hunter_api/routers/lab.py:89)); o gate compara diretamente com `exit_ts` ([lab_summary_metrics.py:81](C:/dev/project-hunter/apps/api/hunter_api/services/lab_summary_metrics.py:81)).

   **Cenário:** `?window=all&as_of=2026-09-06T12:00:00`, com outcome terminal selecionado. A comparação entre datetime sem fuso e com fuso lança `TypeError`. Com catálogo vazio, pode responder sem respeitar o UTC declarado.

   **Correção:** exigir timestamp com fuso, retornar 422 para entrada sem fuso e converter offsets válidos para UTC antes das consultas.

**NICE-TO-HAVE**

- **Validar coorte conforme o contrato:** hoje ambos os endpoints aceitam qualquer `str`; `cohort=prospectve` vira vazio honesto na forma, mas enganoso diante de um erro de digitação. Validar `prospective | replay:<uuid>` ([lab.py:90](C:/dev/project-hunter/apps/api/hunter_api/routers/lab.py:90), [lab.py:112](C:/dev/project-hunter/apps/api/hunter_api/routers/lab.py:112)).
- **Fortalecer os testes financeiros:** o teste do gate verifica apenas maturidade e taxa líquida; deveria conferir também alvo, expectancy, PF, soma e todo `r_ex_funding`, com funding não apurável e fronteiras exatamente iguais a `as_of` ([test_lab_api.py:257](C:/dev/project-hunter/apps/api/tests/integration/test_lab_api.py:257)).
- **Cobrir janela e cursor:** testar limites de 7d/30d e desempate por UUID com `decision_at` idêntico. A paginação atual usa horários diferentes ([test_lab_api.py:327](C:/dev/project-hunter/apps/api/tests/integration/test_lab_api.py:327)).
- **Fixar a definição de dias:** maturidade conta dias de saída; cobertura conta dias de decisão. Documentar essa escolha explicitamente ([lab_summary.py:185](C:/dev/project-hunter/apps/api/hunter_api/services/lab_summary.py:185), [lab_summary.py:211](C:/dev/project-hunter/apps/api/hunter_api/services/lab_summary.py:211)).

**O QUE EU FARIA DIFERENTE**

Manteria a estrutura atual. Corrigiria os três pontos e adicionaria regressões específicas. Para JSONB, aceito a ausência de índice **sob a premissa informada de centenas de linhas**; não medi volume nem plano de execução. Antes de otimizar as expressões de [lab_common.py:27](C:/dev/project-hunter/apps/api/hunter_api/repositories/lab_common.py:27), mediria as consultas com `EXPLAIN ANALYZE`.

**CONCORDO COM**

- **Gate único:** `terminal`, `exit_ts <= as_of` e horizonte maturado estão corretos; a lista `evaluable` alimenta ambos os blocos financeiros ([lab_summary_metrics.py:79](C:/dev/project-hunter/apps/api/hunter_api/services/lab_summary_metrics.py:79), [lab_summary.py:219](C:/dev/project-hunter/apps/api/hunter_api/services/lab_summary.py:219)).
- **Semântica do `yield`: sim.** FastAPI usa context managers internamente; a exceção lançada no corpo da rota retorna ao gerador no ponto do `yield`. Portanto, uma `OperationalError` nesse ponto cai no seu `except` ([lab.py:68](C:/dev/project-hunter/apps/api/hunter_api/routers/lab.py:68); [documentação oficial](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/#a-dependency-with-yield-and-try)). O teste é válido para esse comportamento.
- **Censura legada:** `gap:<minuto>` cai em `gap:unknown`, preservando a contagem ([lab_summary_metrics.py:61](C:/dev/project-hunter/apps/api/hunter_api/services/lab_summary_metrics.py:61)).
- **Decimal:** `sum_of` soma antes de quantizar e usa `ROUND_HALF_UP`; está correto. PF também não usa float, mas precisa da correção acima ([lab_summary_metrics.py:46](C:/dev/project-hunter/apps/api/hunter_api/services/lab_summary_metrics.py:46), [lab_summary_metrics.py:117](C:/dev/project-hunter/apps/api/hunter_api/services/lab_summary_metrics.py:117)).

**OBSIDIAN**

- **Strategy Performance** — atualizar população madura, UTC e regra de calcular PF antes de arredondar.
- **Open Bugs** — registrar os três defeitos até suas regressões serem verificadas.
- **Revisões da Astra — Index** — vincular esta revisão da implementação S3 e seu resultado.