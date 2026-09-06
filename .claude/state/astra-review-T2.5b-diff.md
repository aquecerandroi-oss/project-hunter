**RESUMO**

**REQUEST_CHANGES.** Revisei como `backend-specialist`, em modo OPINIÃO. Há cinco correções necessárias: publicação temporal, substituição por bootstrap imaturo, isolamento de falhas por mercado, recuperação de horas perdidas e invalidação do backoff por versão.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit. Examinei os 22 arquivos indicados, os contratos das baselines e o registro da prova operacional.

**TESTES**

Não executei pytest, integrações ou benchmarks nesta revisão somente de leitura. Os números da prova fornecida não foram reproduzidos nesta rodada.

Executei `git diff`, `git status --short` e contagem física de linhas com `@(Get-Content <arquivo>).Count`. Resultados relevantes:

```text
replay.py                  328
runners.py                 316
test_bootstrap.py          354
test_persistence.py        475
```

Os 16 módulos de produção revisados estão abaixo de 350 linhas. **Há dois testes acima de 350**; o gate atual exclui testes explicitamente ([check_file_size.py:47](C:/dev/project-hunter/infra/scripts/check_file_size.py:47)). Portanto, não afirmaria “nenhum arquivo acima de 350”.

**MUST-FIX**

1. **`available_at` pode anteceder a disponibilidade real da revisão.**

   `run_bootstrap` captura `moment` antes da leitura e do replay e reutiliza esse instante em `finish_job` ([replay.py:282](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/replay.py:282), [replay.py:296](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/replay.py:296)). O runner principal melhora isso, capturando o horário depois do replay ([baseline_runner.py:122](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baseline_runner.py:122)). Porém, o refresh também reutiliza o `now` inicial em todos os lotes, inclusive nos consultados posteriormente ([refresh.py:126](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/refresh.py:126), [refresh.py:144](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/refresh.py:144)).

   **Cenário:** refresh começa às 10:00:01; uma snapshot atrasada de 09:59 é persistida às 10:00:20; seu lote é consultado às 10:00:30. A revisão incorpora essa observação, mas declara disponibilidade às 10:00:01. Uma consulta posterior com `as_of=10:00:10` passa pelos dois filtros causais, embora o dado incorporado ainda não estivesse disponível.

   **Correção:** separar horário de corte da população e horário de publicação; carimbar a publicação depois da leitura/cálculo, próximo da escrita. Testar atraso entre lotes e replay com relógio controlado.

2. **Um novo bootstrap imaturo pode retirar uma baseline utilizável.**

   A retenção existe apenas em `_admissible` do refresh. `finish_job` publica todas as revisões produzidas, sem proteção equivalente ([refresh.py:87](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/refresh.py:87), [replay.py:307](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/replay.py:307)). A seleção favorece `available_at` mais recente, independentemente da maturidade ([sql.py:88](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/sql.py:88)).

   **Cenário:** existe baseline utilizável; após perda do ledger ou vencimento das 24 horas, o bootstrap roda novamente sobre uma janela com lacunas e produz um bucket não vazio abaixo do gate. Essa revisão sobrepõe a utilizável. O reload imediato torna a perda visível imediatamente.

   **Correção:** aplicar a política provisória de proteção também à publicação de bootstrap, por bucket e versão. Testar baseline madura seguida de bootstrap incompleto.

3. **Uma falha persistente de um mercado pode monopolizar o bootstrap; uma falha no refresh descarta trabalho independente.**

   Toda exceção cai no mesmo handler, que limpa `job`. A escolha seguinte volta ao BTC ou ao primeiro pendente. O backoff só é registrado depois de `finish_job` terminar ([baseline_runner.py:227](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baseline_runner.py:227), [baseline_runner.py:235](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baseline_runner.py:235), [baseline_runner.py:122](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baseline_runner.py:122)).

   **Cenário:** uma candle do primeiro mercado falha consistentemente na conversão ou uma revisão falha na persistência. A cada cinco minutos o mesmo mercado é escolhido; os demais nunca começam. Separadamente, um erro do refresh enquanto existe replay em voo descarta esse replay, mesmo sem relação com sua entrada.

   **Correção:** separar falhas do refresh das falhas do job; preservar o job independente e registrar retentativa operacional por mercado, permitindo avançar aos demais.

4. **O agendador pula horas e não garante atraso máximo de 120 segundos.**

   O laço escolhe sempre a última hora fechada; não percorre o intervalo desde `refreshed`. Quando não há pendentes, dorme `baseline_check_s=300` ([baseline_runner.py:161](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baseline_runner.py:161), [baseline_runner.py:177](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baseline_runner.py:177), [baseline_runner.py:190](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baseline_runner.py:190), [config.py:58](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/config.py:58)).

   **Cenário:** o refresh do bucket 09 falha durante a hora 10. O serviço recupera às 11:02 e atualiza diretamente o bucket 10; o 09 fica sem atualização até a próxima passagem diária. Mesmo saudável, dormir às 10:59:59 permite iniciar o refresh quase cinco minutos depois da virada.

   **Correção:** reconciliar horas pendentes com recuperação limitada e dormir até o menor prazo entre próxima virada e próxima verificação. Os 120 segundos são orçamento do replay, não limite demonstrado do refresh inteiro.

5. **Uma mudança de roster não invalida o backoff antigo.**

   A comparação de roster protege somente o caminho `complete`. A condição de `retry_at` aceita entradas de qualquer roster ([ledger.py:208](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/ledger.py:208), [ledger.py:216](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/ledger.py:216)).

   **Cenário:** tentativa incompleta da v1 acumulou sete dias de backoff. Entra v2 com nova feature; mesmo com histórico já reparado, o mercado permanece dispensado até o prazo da v1.

   **Correção:** aplicar o backoff apenas à identidade atual e reiniciar tentativas quando ela mudar. Acrescentaria também a comparação explícita entre `entry.window_end` e a evidência arquivada: hoje o campo é registrado, mas não participa da reconciliação.

**NICE-TO-HAVE**

- **Starvation da retenção — resposta a (c):** uma revisão live que passe o gate será publicada; não há bloqueio circular. Entretanto, se a janela móvel nunca alcançar o gate, a revisão anterior pode permanecer indefinidamente: a retenção não tem limite de idade ([refresh.py:80](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/refresh.py:80)). Eu exporia idade da baseline e duração da retenção. Um prazo de expiração exigiria decisão explícita de política.
- **Métrica de desarmados:** quando o último mercado rearma, a série anterior não recebe zero e pode continuar indicando detectores desarmados ([health.py:187](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/health.py:187)).
- **Contadores “written”:** contam revisões tentadas, inclusive conflitos idempotentes, não necessariamente linhas inseridas ([replay.py:263](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/replay.py:263), [refresh.py:153](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/refresh.py:153)).
- **Configuração:** validar valores finitos, `0 < duty <= 1` e orçamento positivo. Hoje `duty=0` chega à divisão por zero ([config.py:102](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/config.py:102), [bootstrap.py:80](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/bootstrap.py:80)).
- O teste de inserção “atrás do cursor” insere `NOW−20min` depois de carregar `NOW−30min`: a segunda amostra é **mais nova**, portanto esse caso não prova a regressão anunciada ([test_deriv.py:173](C:/dev/project-hunter/services/scanner-worker/tests/test_deriv.py:173)).

**O QUE EU FARIA DIFERENTE**

Concentraria a próxima rodada em testes do próprio `baseline_loop`: erro persistente no primeiro mercado, refresh falhando com job em voo, travessia de duas viradas e mudança de roster durante backoff. O teste atual de retomada exercita `pending_markets`, não a sobrevivência do laço ([test_bootstrap.py:211](C:/dev/project-hunter/services/scanner-worker/tests/test_bootstrap.py:211)).

Manteria o consumidor de backfill como bloqueio externo já reconhecido, sem considerar a recuperação automática demonstrada pela preparação manual da prova.

**CONCORDO COM**

- **(a) Janelas e buckets:** não encontrei erro de fronteira nesses campos. O replay usa cortes de minuto em janela semiaberta; o coletor agrupa pela hora UTC, e o cálculo valida janela e hora de cada observação. A ressalva causal é o `available_at` do MF-1 ([bootstrap.py:93](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/bootstrap.py:93), [collect.py:129](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/collect.py:129), [compute.py:139](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/compute.py:139)).
- **(d) `_ROSTERS`:** seguro no desenho atual: quatro combinações booleanas, tuplas e definições congeladas, sem estado por mercado dentro delas ([deriv.py:162](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/deriv.py:162), [detectors.py:70](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/detectors.py:70)).
- **(e) `_reported`:** a correção por delta está certa. Não duplica cortes entre fatias. Uma exceção/cancelamento antes de `_report_cuts` pode deixar os últimos cortes sem contabilização; isso é subcontagem, não o defeito original ([replay.py:145](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/replay.py:145)).
- **(f) Decimal, UTC e dados:** não encontrei conversão monetária nova para `float` nem fabricação de observações. O cálculo preserva `Decimal` e normaliza UTC; candles são filtradas como finais, e settlement não é convertido em histórico amostrado ([compute.py:185](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/compute.py:185), [repo.py:125](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/repo.py:125), [repo.py:66](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/repo.py:66)). Não identifiquei acesso novo a dados de tenant; estas tabelas de análise são globais pelo contrato ([DATABASE.md:1065](C:/dev/project-hunter/docs/DATABASE.md:1065)).

**OBSIDIAN**

- **Anomalies** — registrar proteção também contra bootstrap imaturo e retenção sem limite de idade.
- **Workers** — documentar falhas por mercado, recuperação de horas perdidas e limite real do agendamento.
- **Features** — distinguir corte histórico de horário efetivo de publicação.
- **Monitoring** — esclarecer contadores de escrita, cortes e zeragem de detectores desarmados.
- **Revisões da Astra / T2.5b** — registrar estes cinco achados e os cenários exigidos para encerrá-los.