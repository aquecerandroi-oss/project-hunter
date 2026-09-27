**RESUMO**

**REQUEST_CHANGES.** O diff corrige o `KeyError` informado, e não encontrei um segundo `TypeError` causado pelos três campos opcionais. Contudo, `_goal` transforma capital desconhecido em exclusão silenciosa e pode publicar um retorno medido incorreto.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisei o diff dos três arquivos e rastreei os consumidores no repositório.

**TESTES**

Não executei pytest, pyright ou integração; esta conclusão é de revisão estática.

Executei `git --no-pager diff --check --` nos três arquivos: nenhuma ocorrência de whitespace; apenas avisos de conversão CRLF→LF.

Contagem por leitura: `meme_diary.py`: **350** linhas; `meme_diary_render.py`: **339**; `test_meme_diary.py`: **325**.

**MUST-FIX**

1. **HIGH — capital incompleto apresentado como total; retorno medido mistura populações.**  
   Em [meme_diary_render.py:240](/C:/dev/project-hunter/infra/scripts/meme_diary_render.py:240), saldos `None` desaparecem da soma. Entretanto, em [meme_diary_render.py:265](/C:/dev/project-hunter/infra/scripts/meme_diary_render.py:265), o PnL desses mesmos conjuntos continua entrando no numerador e na reconstrução do saldo inicial.

   **Cenário concreto, hipotético:** conjunto A termina com 2 SOL e PnL diário zero; conjunto B, sem teto declarado, fecha apostas com lucro de 0,1 SOL. O código publica capital total de 2 SOL e retorno medido de `0,1 / (2 − 0,1)`, aproximadamente **5,26%**. Não há capital inicial conhecido de B que sustente esse percentual. Com apenas conjuntos sem teto, publica **0 SOL**, embora o capital seja desconhecido.

   Isso viola expressamente a regra de desconhecidos em [meme_diary_render.py:8](/C:/dev/project-hunter/infra/scripts/meme_diary_render.py:8). O teste novo renderiza esse caso, mas verifica somente a célula do teto, em [test_meme_diary.py:324](/C:/dev/project-hunter/infra/scripts/tests/test_meme_diary.py:324).

   **Correção mínima:** havendo saldo desconhecido na população agregada, apresentar capital total, retorno exigido e retorno medido como `— (capital incompleto: conjunto sem teto declarado)`. Preservar os PnLs observados. Um subtotal conhecido pode aparecer separado, explicitamente identificado.

2. **MEDIUM — os novos testes passam um objeto incompatível com a assinatura tipada.**  
   [test_meme_diary.py:290](/C:/dev/project-hunter/infra/scripts/tests/test_meme_diary.py:290) e [test_meme_diary.py:301](/C:/dev/project-hunter/infra/scripts/tests/test_meme_diary.py:301) passam `_RuleSetDaySession` onde [meme_diary.py:146](/C:/dev/project-hunter/infra/scripts/meme_diary.py:146) exige `AsyncSession`. O dublê não herda dessa classe.

   **Cenário:** a verificação estática estrita, configurada em [pyproject.toml:73](/C:/dev/project-hunter/pyproject.toml:73), rejeita os argumentos mesmo que pytest execute normalmente. É uma incompatibilidade identificada estaticamente; não apresento diagnóstico de pyright como executado. Resolver a fronteira tipada do dublê e confirmar com o comando canônico.

**NICE-TO-HAVE**

O dublê **é útil para a regressão original**: chama `_rule_set_day` real com os parâmetros sem a chave; restaurar o acesso direto faria esse teste falhar antes das consultas ([test_meme_diary.py:286](/C:/dev/project-hunter/infra/scripts/tests/test_meme_diary.py:286)).

Mas **não verifica o contrato SQL**. O despacho por identidade devolve mappings fixos e ignora parâmetros ([test_meme_diary.py:256](/C:/dev/project-hunter/infra/scripts/tests/test_meme_diary.py:256)). Renomear `AS realized` no SQL, mantendo o consumidor, deixaria esses testes verdes e quebraria produção; mudar apenas o acesso Python para uma chave inexistente no mapping falso seria detectado.

Portanto, ele tem a mesma **cegueira na fronteira da dependência** registrada em [Architecture Decisions:71](</C:/dev/project-hunter/obsidian/06-DECISIONS/Architecture Decisions.md:71>), embora não reimplemente o cálculo SQL. Recomendo integração contra PostgreSQL, com os statements reais e saldos inicial/final distintos. Não considero essa lacuna prova de SQL atualmente quebrado.

**O QUE EU FARIA DIFERENTE**

Manteria o ajuste localizado e acrescentaria testes da seção 4 para população mista e população inteiramente sem teto, incluindo PnL não zero.

Também corrigiria o rótulo “conjuntos ativos”: `_RULE_SETS` não filtra status ([meme_diary.py:54](/C:/dev/project-hunter/infra/scripts/meme_diary.py:54)). Essa inconsistência é anterior ao diff; não justificaria remover conjuntos aposentados do histórico.

**CONCORDO COM**

- A ausência vira `None`, sem fabricar teto; `_wallet_balance` retorna antes da aritmética ([meme_diary.py:139](/C:/dev/project-hunter/infra/scripts/meme_diary.py:139)).
- Os três campos são formatados por `_n`, que trata `None` antes da formatação numérica ([meme_diary_render.py:110](/C:/dev/project-hunter/infra/scripts/meme_diary_render.py:110)).
- `meme_close_day` encaminha o diário ao renderer; não calcula com esses campos ([meme_close_day.py:239](/C:/dev/project-hunter/infra/scripts/meme_close_day.py:239)). **Descarto o achado de segundo `TypeError`: não encontrei cenário que o sustente.**
- O diff mantém `Decimal`, não acrescenta `float`, `print` nem alterações temporais. Existem `print` anteriores em [meme_diary.py:314](/C:/dev/project-hunter/infra/scripts/meme_diary.py:314); portanto, não afirmo conformidade integral do arquivo com “nenhum print”.

**OBSIDIAN**

- **Diário Meme — README:** registrar como capital incompleto afeta total e percentuais.
- **Open Bugs:** registrar que T4.98 corrige o acesso ausente, mas precisa corrigir a agregação antes do aceite.
- **Architecture Decisions:** distinguir regressão unitária válida de comprovação do contrato SQL.
- **Revisões-Astra — T4.98:** guardar este parecer e, posteriormente, os resultados reais de validação.