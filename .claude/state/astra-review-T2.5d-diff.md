**RESUMO**

**APPROVE_WITH_NITS para o diff; throughput ainda depende da medição planejada.** Papel: `code-reviewer`, modo OPINIÃO. Não encontrei must-fix funcional introduzido pela T2.5d.

**ARQUIVOS**

Nenhum arquivo criado ou modificado por mim; nenhum commit. Revisão restrita à tarefa indicada.

Na árvore consultada, `uv.lock` já estava no HEAD, sem diff pendente. O conteúdo confirma hiredis 3.4.1 e Redis 8.1.0: [uv.lock:424](C:/dev/project-hunter/uv.lock:424), [uv.lock:1407](C:/dev/project-hunter/uv.lock:1407).

**TESTES**

Não executei pytest nem benchmarks. As contagens e medidas informadas são evidência relatada por você, não revalidada nesta revisão.

Executei `git diff --check -- <arquivos rastreados da T2.5d>`: sem erros de whitespace; somente avisos de conversão CRLF→LF em `config.py` e `main.py`. Isso não verifica os arquivos novos ainda não rastreados.

**MUST-FIX**

Nenhum com cenário concreto de falha nova. Respondendo às perguntas:

1. **`consume()` preserva o comportamento operacional examinado.** O `_read_loop` fica suspenso no `yield entries` enquanto o wrapper percorre aquela página. Só depois da última mensagem o cursor avança: portanto, não há antecipação da próxima chamada de reclaim. O guard continua imediatamente antes de cada entrega. [consume.py:178](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:178), [consume.py:253](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:253).

   O contador continua abrangendo somente timeouts de `XREADGROUP`; uma resposta bem-sucedida, inclusive vazia, o zera. Erros de reclaim, guard, decodificação e ACK não entram nesse orçamento e continuam propagando. [consume.py:189](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:189).

   **Ressalva preexistente:** `not entries` interrompe a varredura mesmo com cursor diferente de zero. A refatoração preservou essa condição; não a classifico como regressão desta tarefa. [consume.py:186](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:186).

2. **ACK integral correto para os três streams atuais.** Todos usam o mesmo handler, que coalesce e aplica `touch`, sem `await` entre mercados. Mercado ausente continua sendo ignorado, como anteriormente. [main.py:142](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:142), [main.py:188](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:188), [state.py:177](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/state.py:177).

   **Pode haver sucesso parcial antes de uma exceção**, mas isso não torna o ACK incorreto: nenhuma entrada é confirmada nesse caminho, e repetir os `touch` é seguro — conjunto de motivos e timestamp máximo. Corrigiria apenas a explicação “nothing was applied”: o contrato verdadeiro é “nem tudo concluiu”. [consumers.py:255](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/consumers.py:255), [consumers.py:275](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/consumers.py:275), [state.py:129](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/state.py:129).

3. **A virada UTC não é bloqueadora nesse contrato.** O guard consulta D e D−1; se o ACK acontece em D+1, grava em D+1, pois calcula sua própria chave naquele momento. Uma reentrega posterior encontra essa marca. [processed.py:120](C:/dev/project-hunter/packages/core/hunter_core/events/processed.py:120), [processed.py:185](C:/dev/project-hunter/packages/core/hunter_core/events/processed.py:185).

   O guard antecipado não é uma reserva: outro consumidor pode concluir o evento depois da consulta e antes do handler, permitindo execução redundante. Isso é aceitável para esses `touch` idempotentes; não constitui garantia de execução única.

4. **O split é por responsabilidade.** O runner escolhe mercado, prioriza refresh e fornece orçamento; `baseline_jobs` inicia e encerra tentativas, incluindo ledger e atualização de estado. A fronteira é coerente, mesmo motivada pelo limite de linhas. [baseline_runner.py:147](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baseline_runner.py:147), [baseline_jobs.py:52](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baseline_jobs.py:52).

   O ramo vazio preserva `gaps` e `requested`, registra resultado incompleto, atualiza `baseline_note` e libera o slot antes de continuar. [baseline_jobs.py:134](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baseline_jobs.py:134), [baseline_runner.py:201](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/baseline_runner.py:201).

**NICE-TO-HAVE**

Para a pergunta **5**, acrescentaria:

- **Reclaim com várias páginas:** verificar cursor, ordem, guard entre yields e envelope inválido entre válidos recuperados. O teste novo cobre apenas uma página terminada em `0-0`. [test_events_consume_batch.py:234](C:/dev/project-hunter/packages/core/tests/unit/test_events_consume_batch.py:234).
- **Virada UTC:** ler antes da meia-noite, confirmar depois e reentregar; incluir conclusão concorrente após o guard.
- **Falha parcial e falha no ACK:** aplicar o primeiro `touch`, falhar no segundo, recuperar o lote; também simular marca gravada com XACK não concluído. O teste atual falha antes de qualquer efeito. [test_consumers.py:129](C:/dev/project-hunter/services/scanner-worker/tests/test_consumers.py:129).
- **Bootstrap:** testar `gaps` e `requested` não vazios e a seleção pelo `pending_markets` real. O harness substitui essa seleção e sempre retorna zero solicitações. [test_baseline_loop.py:134](C:/dev/project-hunter/services/scanner-worker/tests/test_baseline_loop.py:134).
- **Métrica:** verificar a observação efetiva no histograma. Ela representa máximos de idade **por lote**, não a distribuição por mensagem. [consumers.py:297](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/consumers.py:297).

**O QUE EU FARIA DIFERENTE**

Seu benchmark sintético é a próxima prova adequada. Usaria envelopes e distribuição de mercados iguais, grupos independentes e mediria **leitura→handler→ACK**, taxa de dreno, PEL final e duração dos lotes.

Os números relatados sustentam ganho naquela leitura de hot state; lag zero a aproximadamente 28 mensagens/s não demonstra capacidade a 151 mensagens/s. Também não fecha o p99 de avaliação sob carga exigido pelo plano: [M2.md:58](C:/dev/project-hunter/docs/plans/M2.md:58).

**CONCORDO COM**

Guard por mensagem preservado; lote entregando duplicatas ainda não processadas; ACK de todas as entradas absorvidas; timestamp máximo acompanhado da idade mais antiga; bootstrap vazio tratado no loop operacional.

**OBSIDIAN**

- **Workers** — registrar consumo em lote, ACK integral e repetição segura após falha parcial.
- **Data Flow** — documentar guard antecipado como filtro, não reserva de execução.
- **Features** — distinguir atraso máximo por lote do p99 por mensagem e da conclusão da avaliação.
- **Infrastructure** — registrar benchmark completo, parser utilizado e limites da evidência.
- **Revisoes-Astra/T2.5d — diff** — registrar aprovação com ressalvas e testes adicionais recomendados.