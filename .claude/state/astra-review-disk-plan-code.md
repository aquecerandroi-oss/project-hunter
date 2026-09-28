**RESUMO**

**REQUEST_CHANGES**: encontrei dois bloqueios no backup/roteiro. A mudança de `history_v2` está coerente; a premissa documentada sobre o pedigree precisa ser corrigida.

**ARQUIVOS**

Revisei o diff solicitado, os cinco testes novos e os leitores relacionados. Nenhum arquivo criado/modificado; nenhum comando executado na VPS.

**TESTES**

Verificações somente leitura executadas:

- `bash -n infra/vps/backup_postgres.sh`: saída vazia, código **0**.
- Parser PowerShell: **13 blocos**, sem erros.
- Comandos SSH extraídos, analisados com `bash -n`: código **0**.
- Contagem dos oito módulos Python do escopo: **148–350 linhas**.

Não executei pytest: as suítes criam arquivos temporários ou alteram banco. Não considero a análise sintática prova de execução remota.

**MUST-FIX**

1. **HIGH — zero posições não garante uma janela sem exposição.**  
   O [roteiro:408](C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:408) exige três contagens zeradas, mas mantém o `meme-executor` ativo e apenas imprime o kill switch, sem exigir um estado bloqueante. Esse executor pode admitir spot a cada 15 segundos ([spot_entries.py:68](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_entries.py:68)).

   **Cenário:** a consulta retorna zero; uma entrada acontece antes da parada do coletor spot. Mesmo com novas entradas bloqueadas, uma compra já enviada pode confirmar depois: o reconciliador abre a posição ([spot_reconcile.py:278](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/spot_reconcile.py:278)). A manutenção prossegue sem cumprir sua própria pré-condição.

   **Correção:** exigir bloqueio confirmado de novas entradas, ausência de compras pendentes/confirmações sem posição e, depois disso, repetir a contagem antes de parar a alimentação.

2. **MEDIUM — a retenção conta arquivos finais, não dumps antigos validados.**  
   Em [backup_postgres.sh:64](C:/dev/project-hunter/infra/vps/backup_postgres.sh:64), qualquer `hunter-*.dump` ocupa uma vaga. Só o arquivo recém-produzido passa pela checagem.

   **Cenário:** a versão anterior escrevia diretamente no nome final; um reboot durante o dump deixou um arquivo truncado. Após o deploy, com retenção 3, dois bons antigos + um truncado + o novo bom viram **dois bons e um truncado**: um backup bom foi descartado para preservar lixo.

   **Correção:** validar o conjunto legado antes da primeira poda por contagem e retirar arquivos inválidos da contagem. Para truncamentos posteriores ao índice, `--list` é insuficiente — limitação já reconhecida em [backup_postgres.sh:129](C:/dev/project-hunter/infra/vps/backup_postgres.sh:129).

   **Resposta direta à pergunta 1:** no fluxo serial normal, com arquivos íntegros, não encontrei caminho que apague o último dump recém-validado. A garantia absoluta de “N dumps bons”, porém, não existe.

**NICE-TO-HAVE**

- **Serializar também as execuções manuais do backup.** Os nomes têm precisão de segundos ([backup_postgres.sh:87](C:/dev/project-hunter/infra/vps/backup_postgres.sh:87)). Duas execuções no mesmo segundo compartilham `.partial`; uma pode promovê-lo enquanto a outra ainda escreve. Um lock dentro do script também impediria a limpeza de uma sobra que pertença a outra execução ainda viva.

- **Não confiar em `set -euo pipefail` para detectar falha da listagem.** A pipeline está dentro de substituição de processo ([backup_postgres.sh:64](C:/dev/project-hunter/infra/vps/backup_postgres.sh:64)); seu erro não é propagado como erro do `while`. Pode anunciar sucesso sem aplicar a retenção.

- **Corrigir a consequência declarada do pedigree.** [DATABASE.md:5831](C:/dev/project-hunter/docs/DATABASE.md:5831) diz “qualquer janela”, mas o SQL limita os antecedentes a **7 dias**, com parâmetro efetivamente passado pela função ([lab_repo_fast.py:82](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_fast.py:82), [linha 251](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_repo_fast.py:251)). Para moedas jovens avaliadas ao vivo, **90 → 30 dias não reduz esse horizonte**.

- **Há outros leitores afetados por `meme_tokens`:**
  - Fichas antigas continuam existindo, mas perdem nome/símbolo quando o token é podado ([meme_tests.py:266](C:/dev/project-hunter/apps/api/hunter_api/services/meme_tests.py:266)).
  - Condicionalmente, uma posição ainda aberta após 30 dias perde a vigilância do criador: a poda não protege posições/apostas abertas ([repo.py:221](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/repo.py:221)), enquanto o watcher depende de `JOIN meme_tokens` ([creator_watch.py:68](C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/creator_watch.py:68)). É uma fragilidade existente, antecipada de 90 para 30 dias; merece proteção explícita dos tokens ainda necessários.

**O QUE EU FARIA DIFERENTE**

Acrescentaria testes para dump legado inválido, execuções concorrentes e recuperação real do scanner após commit/restart. O teste atual confere a marca produzida na linha, mas não percorre a reidratação ([test_history_rate.py:190](C:/dev/project-hunter/services/scanner-worker/tests/test_history_rate.py:190)).

**CONCORDO COM**

- **Roteiro:** não encontrei erro sintático PowerShell/bash. Dois `-c`, timeout numérico e `TRUNCATE` antes da compactação estão corretos ([roteiro:380](C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:380), [linha 430](C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:430)).
- **Backup:** `.partial` promovido somente depois da checagem é uma melhora real. A exclusão incluindo filhas mantém o esquema e omite os dados, conforme a [documentação do PostgreSQL 16](https://www.postgresql.org/docs/16/app-pgdump.html).
- **Histórico:** a última marca persistida acompanha a linha histórica na mesma transação; a memória avança depois do commit ([collect.py:134](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/collect.py:134), [persist.py:185](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/persist.py:185)). Não identifiquei regressão adicional de reinício introduzida pela troca.
- **Explicabilidade:** a perda entre amostras está declarada; as amostras preservadas mantêm envelope e decomposição ([DATABASE.md:1392](C:/dev/project-hunter/docs/DATABASE.md:1392)). A ponte continua impondo `ts <= at`, sem antecipação ([bridge_universe.py:314](C:/dev/project-hunter/services/execution-worker/hunter_execution_worker/bridge_universe.py:314)).
- **Risco meme:** a leitura de snapshots usa frescor de 600 segundos; retenção de 30 dias não encurta essa janela ([repo_context.py:62](C:/dev/project-hunter/services/meme-executor/hunter_meme_executor/repo_context.py:62)).

**OBSIDIAN**

- **Decisão — retenção de dados e backup para o disco da VPS:** registrar os bloqueios operacionais e corrigir o horizonte do pedigree para 7 dias.
- **Infrastructure:** documentar a validação dos dumps legados e a exclusão mútua do backup.
- **Workers:** registrar `history_v2` e a recuperação pela última marca persistida.
- **Meme — o que uma “estratégia” é aqui:** declarar o efeito da poda nas fichas antigas e nos tokens ainda usados por posições abertas.