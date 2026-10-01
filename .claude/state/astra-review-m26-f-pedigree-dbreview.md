**RESUMO**

`DONE_WITH_CONCERNS`: favorável à via leve. Há duas correções documentais e uma condição operacional antes de ativar `1m` com reincidência.

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Revisão estática; testes não executados. Os tempos e logs da VPS são os que você forneceu.

**MUST-FIX**

- **(1) A frase está errada.** A §66 mediu 3,3 s **sem `symbol_dup_24h`, mas incluindo dump/dead** ([DATABASE.md:8334](C:/dev/project-hunter/docs/DATABASE.md:8334)). Corrigir [a §69:8622](C:/dev/project-hunter/docs/DATABASE.md:8622) para: “Os ~3 s incluíam dump/dead, sem decompor seus custos; a medição excluía `symbol_dup_24h`.” Cenário: usar a narrativa atual para aprovar capacidade de uma pista completa com uma comparação falsa.

- **(3) Sim, documentar a leitura parcial nos dois destinos.** A [§68:8471](C:/dev/project-hunter/docs/DATABASE.md:8471) precisa distinguir pedigree inteiro ausente de objeto presente com dois campos JSON `null`. Estes significam **não lidos**, não zero, e não implicam falha da consulta. A persistência conserva esses campos em [proposals_reasons.py:134](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/proposals_reasons.py:134) e [lab_opportunities.py:138](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_opportunities.py:138). Cenário: análise classificar como instrumento indisponível uma oportunidade válida, ou interpretar diagnóstico não lido como ausência de dumps.

- **(4) Antes de ativar `1m` com reincidência, exigir prova de capacidade sob carga.** Um único conjunto assim força a completa para toda a pista ([lab_repo_e2b.py:206](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_e2b.py:206)). Cenário: reproduzir os 6–14 s medidos, atingir o timeout e perder pedigree de todo o lote. É condição de ativação; não bloqueia a leve atual.

**NICE-TO-HAVE**

**(2) Não identifiquei defeito concreto de tipagem ou seq scan na leve.** Seu plano confirma índices para aquela amostra; não garante todos os planos futuros. `ANY(:mints)` recebe lista e tem o tipo inferido pela comparação; os segundos inteiros são compatíveis com `make_interval`, cujo argumento é `double precision` ([SQL:55](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_pedigree.py:55), [parâmetros:139](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_pedigree.py:139), [PostgreSQL](https://www.postgresql.org/docs/16/functions-datetime.html)).

`statement_cache_size=0` sozinho não desliga o cache do dialeto SQLAlchemy; o projeto desliga **ambos** ([session.py:101](C:/dev/project-hunter/packages/core/hunter_core/db/session.py:101), [documentação](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#prepared-statement-cache)). Complementaria a medição literal com execução parametrizada pelo mesmo caminho do worker.

**O QUE EU FARIA DIFERENTE**

Trataria os timeouts atuais de **15 s como problema separado**, ainda aberto. Avaliaria o índice parcial sugerido com `EXPLAIN ANALYZE`: ele pode ajudar o primeiro `EXISTS`, mas não resolve os outros dois nem o agregado dead ([lab_repo_pedigree.py:75](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_pedigree.py:75)). Não exigiria esse índice sem medir.

**CONCORDO COM**

Leitura leve restrita à pista elegível, diagnósticos `None`, completa preservada e testes de equivalência. O teste de plano verifica tabelas acessadas, **não ausência de seq scan** ([test_pedigree_light_integration.py:103](C:/dev/project-hunter/services/meme-worker/tests/test_pedigree_light_integration.py:103)).

**OBSIDIAN**

- **EXP-M26-pedigree-fix** — acrescentar correção histórica e contrato de leitura parcial.
- **EXP-M26-grafico-em-moedas-maduras** — registrar prova parametrizada pendente e condição para `1m` com reincidência.
- **Open Bugs** — registrar os timeouts observados na pista de 15 s separadamente.