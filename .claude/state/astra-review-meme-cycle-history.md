## RESUMO

**REQUEST_CHANGES:** o ack está correto, mas há duplicação possível após commit ambíguo e o orçamento de encerramento não é de 3 s no total. Para usar a série como guarda, também falta fechar o contrato de deduplicação, janelas e cobertura.

Revisão como `code-reviewer`, seguindo a decisão de instrumentar antes do seed em [EXP-M26:530](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M26-grafico-em-moedas-maduras.md:530).

## ARQUIVOS

Nenhum arquivo criado ou modificado; nenhum commit. Inspecionei os oito arquivos pedidos, o diff de `main.py`, as revisões anteriores e os caminhos relacionados de transação, retenção e leitura.

Contagem por leitura: os oito arquivos estão abaixo de 350 linhas; o maior é `main.py`, com 332.

## TESTES

**Não executei pytest, lint ou integração**, respeitando a revisão sem escritas. Os **“3 passed contra Postgres real” são o resultado informado por você**, não uma execução minha.

A cobertura inspecionada ainda deixa estas lacunas:

- O fake falha em `execute` ou suspende **antes** de entregar a sessão; não simula commit aplicado com confirmação perdida nem limpeza lenta após cancelamento: [test_cycle_history.py:40](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_history.py:40).
- O teste de ack acrescenta uma amostra durante a escrita, mas não força overflow durante o lote: [test_cycle_history.py:131](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_history.py:131).
- A integração cobre persistência, leitura e negação de `DELETE`; o terceiro teste não verifica `UPDATE`, embora a docstring mencione ambos: [test_cycle_history_integration.py:88](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_history_integration.py:88).

## MUST-FIX

**1. HIGH — retry pode duplicar ciclos já confirmados no banco.**

O INSERT gera outro UUID e outro `created_at` em cada tentativa; não há deduplicação por `(loop, run_id, seq)`. O ack só ocorre depois de sair da sessão: [cycle_history.py:69](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:69), [cycle_history.py:155](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:155).

**Cenário:** Postgres aplica o COMMIT, mas a conexão perde a resposta. A sessão lança exceção, o lote permanece na fila e a próxima tentativa grava tudo novamente. Isso pode ponderar algumas durações duas vezes e alterar o p95.

**Sim, é executemany dentro de uma transação:** `execute` recebe a lista de parâmetros e `role_session` envolve tudo em `session.begin()`. Uma falha seguida de rollback confirmado não deixa metade do lote; isso não resolve a ambiguidade da confirmação do commit: [session.py:232](/C:/dev/project-hunter/packages/core/hunter_core/db/session.py:232).

**Correção:** definir e testar o contrato. Sem migração, a solução mínima para a guarda é deduplicar por identidade lógica **antes** do percentil e rejeitar conteúdos divergentes para a mesma identidade. Nesse caso, retirar a promessa de “uma linha física por ciclo”. UUID determinístico sozinho não basta: a PK inclui `created_at`, que hoje muda entre tentativas: [system.py:60](/C:/dev/project-hunter/packages/core/hunter_core/db/models/system.py:60).

**2. MEDIUM — o encerramento pode ultrapassar o orçamento anunciado e atrasar a limpeza.**

Há dois timeouts consecutivos de `budget_s`: banco e publicação. Portanto, são aproximadamente **20 s por flush** e **6 s no close**, antes de considerar cancelamento/limpeza do driver: [cycle_history.py:156](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:156), [cycle_history.py:169](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:169), [cycle_wiring.py:62](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_wiring.py:62).

**Cenário:** banco indisponível consome 3 s; o contador de falha muda; Redis indisponível consome outros 3 s. Só depois começa `close_clients`. Um novo cancelamento durante `cycles.close()` também pode impedir os fechamentos seguintes: [main.py:324](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:324).

**Correção:** orçamento único para a operação completa, fechamento dos clientes protegido por `finally` próprio e teste com banco e publisher lentos. O timeout continua cooperativo: o próprio módulo de sessão documenta que rollback/fechamento podem prolongar o cancelamento; existe um limite de comando de 30 s, não uma garantia de término em 3 s: [session.py:11](/C:/dev/project-hunter/packages/core/hunter_core/db/session.py:11), [session.py:103](/C:/dev/project-hunter/packages/core/hunter_core/db/session.py:103).

**3. HIGH, bloqueante da guarda antes do seed — sequência contínua não comprova cobertura completa.**

O payload permite calcular a distribuição dos ciclos recebidos, mas não contém um total final durável da geração: [cycle_history.py:126](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:126).

**Cenário:** persistem os ciclos 1–100; 101–110 ficam na fila; o processo morre. A geração seguinte usa outro UUID. A série antiga termina perfeitamente contínua em 100: nenhum salto revela a cauda perdida. Uma geração inteiramente perdida também fica invisível.

Além disso, a consulta publicada como exemplo usa `created_at >= :t0`, enquanto o INSERT define `created_at = now()`. Um ciclo anterior ao seed, represado durante falha do banco, pode entrar no “depois” por horário de persistência: [Meme README:205](/C:/dev/project-hunter/obsidian/03-TRADING/Meme/README.md:205), [cycle_history.py:71](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:71).

**Correção antes do aceite da guarda:** congelar janelas por `ended_at`, deduplicação, cobertura mínima e tratamento de reinícios/caudas desconhecidas. Usar evidência operacional adicional para cobertura; ausência dessa prova deve produzir **não mensurável**. A própria EXP reconhece que intervalo e cobertura ainda estão pendentes: [EXP-M26:539](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M26-grafico-em-moedas-maduras.md:539).

## NICE-TO-HAVE

- **Contadores não equivalem exatamente a perdas:** uma amostra removida por overflow pode continuar no lote em voo e ser persistida com sucesso. Nesse caso, `dropped_total` aumenta sem perda durável. Também `_queued` não participa da detecção de mudança, e os contadores zerados não são anunciados no boot, permitindo valores antigos no hash até a primeira publicação: [cycle_history.py:89](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:89), [cycle_history.py:109](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:109), [cycle_history.py:167](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:167).
- **Close não drena a fila:** grava no máximo 500 das 4.096 amostras. Pode perder backlog mesmo num encerramento normal; documentar e contar o restante: [cycle_history.py:62](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:62), [cycle_wiring.py:64](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_wiring.py:64).
- **Proveniência por geração:** persistiria `code_ref`/deploy, configuração nominal e início da geração em um registro associado. Não precisam ser repetidos em cada ciclo. `enabled` por amostra acrescenta pouco; um evento de geração desabilitada explica a ausência de amostras. Hoje esses dados não estão no payload durável: [cycle_history.py:126](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:126).

## O QUE EU FARIA DIFERENTE

**Fila e ordem.** Manteria o token monotônico. `offer` não aguarda I/O; o ack remove somente tokens até o final do snapshot, preservando os posteriores mesmo com overflow. Não encontrei erro nessa lógica: [cycle_history.py:89](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:89), [cycle_history.py:104](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:104). No banco, ordenaria explicitamente por geração e `seq`; `created_at` é compartilhado pelo lote e não representa ordem de conclusão.

**TaskGroup.** Falhas ordinárias de banco/publicação são absorvidas; cancelamento externo propaga. A fiação atual tem um escritor periódico e executa o close após sair do grupo, evitando dois flushes simultâneos nesse caminho: [cycle_history.py:163](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:163), [main.py:320](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:320). Contudo, “a cada 5 s” significa **flush + sleep de 5 s**, não período fixo: [collect.py:340](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/collect.py:340).

**Prune/dump e leitores.** Não vejo bloqueante pelo volume nominal isoladamente:

- 7.200/dia corresponde a 216.000 linhas em 30 dias; é estimativa nominal, não medição.
- A poda descarta meses inteiros somente quando todo o mês expirou; portanto, a quantidade retida pode exceder 30 dias de linhas: [partition_retention.py:106](/C:/dev/project-hunter/infra/scripts/partition_retention.py:106).
- O dump inclui essas linhas; a exclusão configurada é de `opportunity_history`: [backup_postgres.sh:122](/C:/dev/project-hunter/infra/vps/backup_postgres.sh:122). Não estimei bytes ou duração sem medir.
- Os leitores inspecionados separam por componente ou evento específico, evitando mistura semântica: [obsidian_strategy_queries.py:120](/C:/dev/project-hunter/infra/scripts/obsidian_strategy_queries.py:120), [replication_stats.py:157](/C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replication_stats.py:157).
- Sem partição do mês da **escrita**, o lote falha, permanece pendente e eventualmente sofre overflow. Isso degrada a evidência, sem exceção ordinária derrubar os laços: [cycle_history.py:155](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_history.py:155).

**Discordo de “sem mudança de comportamento” como afirmação absoluta.** O hook da fila não espera banco, mas o wrapper ainda aguarda publicação Redis após medir; esse tempo altera a cadência e fica fora de `duration_ms`: [cycle_metrics.py:227](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:227), [cycle_metrics.py:258](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:258).

## CONCORDO COM

O histórico individual resolve a limitação fundamental do p95 móvel. `duration_ms` basta para calcular p95; `nominal_ms` só é necessário para reconstruir overruns/contexto, não para a fórmula.

As correções anteriores estão presentes: anúncio dos dois laços antes do ramo desabilitado, validação UTC do início e testes que cancelam durante a publicação: [main.py:178](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:178), [cycle_metrics.py:119](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:119), [test_cycle_metrics_review.py:32](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics_review.py:32). O anúncio continua sendo uma tentativa: falha de Redis não comprova substituição dos campos antigos.

## OBSIDIAN

- **EXP-M26 — gráfico em moedas maduras:** fixar janelas, deduplicação e critérios de cobertura, incluindo caudas e gerações ausentes.
- **Meme — README:** corrigir garantias de unicidade, orçamento total, drenagem no close e consulta por horário de conclusão.
- **Revisões Astra — meme-cycle-metrics:** registrar commit ambíguo, limites do cancelamento e correções anteriores verificadas por inspeção.

Nenhuma página foi modificada.