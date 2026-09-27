**RESUMO**

**Não executaria a §6 como está.** A direção de reduzir escrita e instalar retenção faz sentido, mas há erros operacionais e uma promessa incorreta de recuperação da outbox. A conclusão “só 30 dias cabem” também é mais forte que os resultados apresentados.

Revisão como `database-architect`, em modo OPINIÃO. Os números da VPS foram tratados como medições fornecidas pelo documento; não os medi novamente.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit, acesso à VPS ou leitura de `.env`.

**TESTES**

Revisão estática com `Get-Content` e `rg`, conferida contra a documentação oficial do PostgreSQL 16 e GNU Findutils. Não executei pytest, restore, poda ou comandos da §6.

Conferência aritmética em PowerShell, com horários ilustrativos de término de dumps:

```text
mtime_floor=2; match_plus_2=False
arquivo_5_meses_GiB=35
```

O simulador mencionado fora do repositório não foi acessado; portanto, não reproduzi as datas da previsão.

**MUST-FIX**

1. **O `VACUUM FULL` falha na forma proposta.**  
   Na [proposta:259](/C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:259), `SET ...; VACUUM ...` está dentro de um único `psql -c`. O servidor trata essa chamada como uma transação; `VACUUM` não pode executar nela. Resultado esperado: `VACUUM cannot run inside a transaction block`. [Documentação do psql](https://www.postgresql.org/docs/16/app-psql.html), [VACUUM](https://www.postgresql.org/docs/16/sql-vacuum.html).

   **Cenário:** os workers são parados, mas a compactação falha e nenhum dos ~29 GiB previstos é devolvido. A forma corrigida, apenas como recomendação, é:

   ```bash
   bash infra/vps/compose.sh exec -T postgres \
     psql -X -v ON_ERROR_STOP=1 -U hunter -d hunter \
     -c "SET lock_timeout='5s'" \
     -c "VACUUM (FULL, VERBOSE, ANALYZE) public.outbox_events"
   ```

   `lock_timeout` limita a espera para adquirir locks, **não a duração da compactação**. [Documentação](https://www.postgresql.org/docs/16/runtime-config-client.html#GUC-LOCK-TIMEOUT).

2. **A retomada proposta pode fazer um deploy e afetar a mesa meme.**  
   O `compose.sh up -d` da [proposta:260](/C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:260) executa `up -d --build --remove-orphans`, conforme [compose.sh:220](/C:/dev/project-hunter/infra/vps/compose.sh:220). Os perfis dependem de variáveis da chamada, incluindo `MEME`, `MEME_LIVE` e `MARKET_SPOT`; o próprio wrapper documenta o risco de desligamento quando omitidos em [compose.sh:126](/C:/dev/project-hunter/infra/vps/compose.sh:126).

   **Cenário:** terminar uma manutenção da outbox reconstruindo serviços, alterando a topologia ou deixando o coletor spot parado, contrariando “meme segue rodando”. Registrar os serviços inicialmente ativos e retomar **esses mesmos containers**, sem build nem recriação. Isso também evita religar o scanner escolhido como desligado no passo 3.

3. **Excluir toda a outbox não permite recuperá-la com `reconcile`.**  
   A afirmação da [proposta:151](/C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:151) está errada: `replay_rows` consulta a própria `OutboxEvent`, e `replay_since` republica seus payloads; não reconstrói eventos das tabelas de negócio. Ver [outbox_store.py:217](/C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:217) e [outbox_recovery.py:74](/C:/dev/project-hunter/packages/core/hunter_core/events/outbox_recovery.py:74).

   **Cenário:** o snapshot contém uma alteração de negócio e seu evento ainda pendente; o dump exclui o evento. Após desastre e restore, o estado existe, mas sua obrigação de publicação desapareceu. Mesmo eventos despachados deixam de poder recompor um Redis perdido.

   Para a primeira redução de backup, eu excluiria apenas `opportunity_history`. Excluir as filas exige aceitar explicitamente essa perda ou desenhar uma preservação consistente das pendências; medir “zero pendentes” antes do dump, com produtores ativos, não basta.

4. **`-mtime +N` não garante exatamente N+1 dumps nem as liberações anunciadas.**  
   O predicado significa idade arredondada para baixo **maior que N**, isto é, pelo menos N+1 períodos completos de 24 horas. A retenção usa o horário de modificação, não o timestamp no nome. [GNU Findutils](https://www.gnu.org/software/findutils/manual/html_node/find_html/Age-Ranges.html). O script só poda depois de terminar e validar o novo dump: [backup_postgres.sh:60](/C:/dev/project-hunter/infra/vps/backup_postgres.sh:60), [linha 87](/C:/dev/project-hunter/infra/vps/backup_postgres.sh:87).

   **Cenário:** dump antigo terminou às 02:38Z; três dias depois, o novo termina às 01:37Z. O antigo ainda tem apenas dois dias completos para `find` e sobrevive a `+2`. A redução de duração proposta torna esse caso especialmente relevante. A promessa de retirar dois dumps “na primeira noite” na [proposta:205](/C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:205) não se sustenta sem conferir seus `mtime`.

   Modelar por timestamps reais ou implementar retenção por quantidade, preservando backups válidos até validar o substituto.

5. **O cron novo pode bloquear ingestão esperando DDL indefinidamente.**  
   A [proposta:224](/C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:224) agenda um script que executa todos os `DETACH`/`DROP` numa transação, sem configurar timeout: [prune_partitions.py:111](/C:/dev/project-hunter/infra/scripts/prune_partitions.py:111). O `DETACH` é convencional, sem `CONCURRENTLY`: [_partitions.py:126](/C:/dev/project-hunter/packages/core/hunter_core/db/models/_partitions.py:126).

   **Cenário:** pesquisa longa ou backup segura lock compartilhado; o `DETACH` espera lock exclusivo na tabela pai e novas consultas/escritas ficam atrás dele. `flock` só impede outra execução do cron, não esse bloqueio PostgreSQL.

   Antes de agendar, acrescentar limites de espera/duração e tratamento observável da falha. Preferiria transações por partição para liberar locks já adquiridos.

6. **A §5 precisa mudar de conclusão e incorporar os picos operacionais.**  
   A [tabela:178](/C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:178) diz que **30, 45 e 60 dias cabem no cenário-base**. A [sensibilidade:183](/C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:183) diz que **30 dias também falham no backup** a 1,5×. Portanto, demonstra preferência conservadora por 30 dias, não suficiência operacional nem impossibilidade de 45 dias.

   **Cenário:** escolher O5 como solução definitiva e repetir a falha de backup em novembro, já prevista pelo próprio estudo.

   A revisão do modelo precisa explicitar:

   - **Arquivos mensais acumulados:** a proposta acrescenta ~7 GiB/mês, mas não declara claramente sua inclusão no forecast. Cinco arquivos mensais representam ~35 GiB. O padrão `hunter-*.dump` não remove `archive-*.dump` ([proposta:274](/C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:274), [backup_postgres.sh:87](/C:/dev/project-hunter/infra/vps/backup_postgres.sh:87)).
   - **WAL, bloat e atraso de vacuum:** os 721 MiB de WAL medidos são um instante, não uma reserva de pico. O reuso da outbox depende da limpeza efetiva; um snapshot longo pode atrasá-la.
   - **Compactação:** “precisa de ~4 GiB livres” não é um limite seguro; reservar também reconstrução de índices, temporários e WAL. O arquivo antigo continua existindo durante a reescrita. [VACUUM](https://www.postgresql.org/docs/16/sql-vacuum.html).
   - **Dump em andamento e crescimento concorrente:** a limpeza ocorre depois dele; não basta o livre cobrir apenas seu tamanho final.
   - **Horizonte:** substituir “nunca” por “nenhuma falha nos 150 dias simulados”. Arquivo local sem retenção impede concluir estabilidade indefinida.

   **Índices e TOAST não foram esquecidos no tamanho atual:** a [proposta:38](/C:/dev/project-hunter/docs/design/retencao-e-disco-2026-09-27.md:38) usa `pg_total_relation_size`. Não os somaria novamente. Também não reservaria uma segunda cópia integral descomprimida para esse `pg_dump -Fc > arquivo`: a saída é transmitida diretamente.

**NICE-TO-HAVE**

- Versionar o simulador e suas entradas agregadas, tornando verificáveis as datas e a margem de ±15%.
- No arquivamento, exigir sucesso e validação antes do `DROP`, usar arquivo temporário e publicação por rename. Um `pg_dump -t partição` não inclui automaticamente todas as dependências necessárias para restaurá-la isoladamente. [Documentação](https://www.postgresql.org/docs/16/app-pgdump.html).
- Corrigir “o leitor mais longo usa ~2 h”: o endpoint aceita até **500 pontos**, e sua consulta não impõe janela temporal — [schemas/opportunities.py:38](/C:/dev/project-hunter/apps/api/hunter_api/schemas/opportunities.py:38), [repositories/opportunities.py:323](/C:/dev/project-hunter/apps/api/hunter_api/repositories/opportunities.py:323). Cem pontos recentes não definem o alcance histórico máximo.

**O QUE EU FARIA DIFERENTE**

Separaria a emergência da mudança definitiva de retenção: reduziria primeiro o dump de histórico, instalaria a poda existente com os cuidados acima e mediria novamente crescimento, duração e menor espaço livre. Depois compararia 30/45/60 dias usando uma reserva operacional explícita e arquivos mensais incluídos.

Para reduzir escrita, começaria diminuindo a frequência, mantendo **cada amostra preservada autocontida**. Tornar `envelope` nulo precisa definir como recuperar a explicação após podar a amostra anterior; hoje ele existe justamente para reproduzir o score depois de mudanças nas baselines — [analysis.py:282](/C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:282).

**CONCORDO COM**

- **Flags:** `--exclude-table-data-and-children` e `-Z zstd:3` são válidas no PostgreSQL 16. Não são must-fix. O suporte compilado informado pela proposta não foi verificado por mim na VPS. [pg_dump 16](https://www.postgresql.org/docs/16/app-pgdump.html).
- **Restore estrutural:** não encontrei FKs apontando para `opportunity_history` nas definições/migrações consultadas. A FK existente sai dela para `opportunities` — [analysis.py:268](/C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:268). Excluir seus dados preserva schema e não cria órfãos nessa relação. Excluir dados da outbox tampouco exige reiniciar sua sequência: no dump completo, a sequência é objeto separado; o ID é ordem de drenagem, não identidade de evento — [system.py:139](/C:/dev/project-hunter/packages/core/hunter_core/db/models/system.py:139). O problema é a perda funcional descrita acima.
- **`TRUNCATE`:** o SQL com `BEGIN` e `SET LOCAL lock_timeout` é válido. Libera espaço após commit e mantém a partição. Exige lock exclusivo; os três segundos limitam a espera, não toda a operação. [Documentação](https://www.postgresql.org/docs/16/sql-truncate.html).
- **Leitores após `TRUNCATE`:** não encontrei quebra por tabela vazia. A API retorna lista vazia ([opportunities.py:323](/C:/dev/project-hunter/apps/api/hunter_api/repositories/opportunities.py:323)); a variação do radar cai para zero sem amostra ([radar.py:95](/C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:95)); `radar_coverage` aceita máximo nulo ([radar_coverage.py:61](/C:/dev/project-hunter/apps/api/hunter_api/repositories/radar_coverage.py:61)).
- **Ponte:** aceita ausência e mantém o corte temporal. Porém, **parar o scanner não garante `None`**: a consulta também aceita scores antigos de `opportunities`, sem limite de idade. Pode preservar um score obsoleto ou mudar a ordenação dos sinais após apagar o histórico — [bridge_universe.py:294](/C:/dev/project-hunter/services/execution-worker/hunter_execution_worker/bridge_universe.py:294).
- **Retenção mensal e viés:** a sobra de até aproximadamente um mês está corretamente identificada ([partition_retention.py:99](/C:/dev/project-hunter/infra/scripts/partition_retention.py:99)); aplicar o mesmo prazo a graduadas e não graduadas preserva a regra contra seleção pelo desfecho ([DATABASE.md:5759](/C:/dev/project-hunter/docs/DATABASE.md:5759)).

**OBSIDIAN**

- **Infrastructure** — registrar backup parcial, recuperação da outbox e limites operacionais da manutenção.
- **Open Bugs** — atualizar o incidente de disco e os bloqueios encontrados nesta proposta.
- **Execution Engine** — registrar os efeitos de apagar histórico e a possibilidade de score antigo com scanner parado.
- **Revisoes-Astra/2026-09-27-retencao-e-disco** — guardar este parecer e as condições para revisar a previsão.
- **Diario/2026-09-27** — registrar que houve somente revisão; nenhuma retenção ou operação foi aplicada.