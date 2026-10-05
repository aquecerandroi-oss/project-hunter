**RESUMO**

**REQUEST_CHANGES no alarme.** A hipótese é consistente com a evidência fornecida, mas **não exige uma exceção anterior**: a invalidação de baseline também pode perder o fechamento de X sem erro de transação.

Os logs retidos comprovam o veto por `uq_opportunities_open_per_market` naquele intervalo; não identificam o gatilho inicial de 02/10 às 10:12Z. Baselines continuarem sendo gravadas distingue essa parada da morte do processo. Não atribuiria a primeira falha ao congelamento posterior da VPS.

Revisão no papel de `code-reviewer`, considerando [Scanner-lag-2026-10-01](</C:/dev/project-hunter/obsidian/10-PERFORMANCE/Scanner-lag-2026-10-01.md>) e a [revisão anterior](</C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/2026-10-01-scanner-lag.md>).

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisei os quatro arquivos indicados e os caminhos de coleta, persistência, watchdog e reidratação. Nenhum commit.

**TESTES**

Não executei pytest nem os gates nesta revisão; não há resultado de execução a declarar.

Uma limitação concreta dos testes novos: `_run_loop` termina em **0,8 s**, enquanto o tratamento de falha dorme **1 s**. Portanto, o teste de falha não observa a tentativa seguinte — justamente onde um flush vazio pode apagar o alarme. Além disso, o mock recusa qualquer lote, sem reproduzir o retorno imediato do flush vazio. Ver [test_commit_alarm.py:263](/C:/dev/project-hunter/services/scanner-worker/tests/test_commit_alarm.py:263), [runners.py:127](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:127) e [persist.py:161](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/persist.py:161).

**MUST-FIX**

1. **HIGH — o alarme pode continuar verde mesmo quando todos os lotes com dados falham.**

   Cenário: chegam candles, o scanner avalia, o flush falha e o lote é descartado. Na volta seguinte, sem novos mercados devidos ou ACKs, `flush_batch` retorna sem abrir transação. Mesmo assim, `cycle.committed()` atualiza `last_commit_at`, limpa `pending_since` e zera as falhas. Isso pode repetir a cada minuto, sem a pendência jamais alcançar 120 s.

   O descarte está em [runners.py:126](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:126); o retorno vazio, em [persist.py:161](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/persist.py:161); a confirmação incondicional, em [runners.py:110](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:110); o reset, em [health.py:135](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/health.py:135).

   **Correção necessária:** confirmar o trabalho efetivamente persistido. Flush vazio, transação contendo só ACKs ou sucesso de trabalho posterior não comprovam a persistência do lote perdido. Apenas testar `not batch.empty` elimina um caso, mas não resolve o contrato inteiro.

2. **HIGH — trabalho produzido antes de uma exceção pode nunca entrar no relógio do alarme.**

   Cenário: A produz uma expiração; ao processar B, `build_market_context` falha por timeout. A memória de A já avançou, mas o loop não chegou a `cycle.touch(evaluated)`; o lote inteiro é descartado. Se depois houver ciclos vazios, o estado volta a parecer saudável.

   A coleta precede o retorno de `advance` em [scanner.py:191](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/scanner.py:191); `touch` só ocorre depois de todos os mercados e publicações em [runners.py:106](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:106).

   **Correção necessária:** registrar a pendência quando o primeiro efeito entra no lote, antes do próximo `await` que possa falhar. Separar essa marca da atualização de liveness. Falhas exclusivamente no watchdog também ficam fora desse contador, pois ele usa lote e tratamento próprios: [runners.py:250](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:250).

3. **HIGH, preexistente — `_drop_invalidated` produz a divergência sem falha prévia.**

   Sequência concreta:

   - X está aberto no banco.
   - A avaliação expira X e imediatamente limpa `opportunity_id` e `episode`.
   - Uma baseline referenciada pelo mercado desapareceu; `_drop_invalidated` remove a linha EXPIRE e seu evento.
   - A transação termina normalmente. O runner apenas marca o mercado como sujo.
   - Uma avaliação posterior elegível abre Y, enquanto X permanece aberto no banco.

   A identidade é esquecida em [collect.py:166](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/collect.py:166); o descarte acontece em [persist.py:133](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/persist.py:133); a reação limita-se a `state.touch("baseline_vanished")` em [runners.py:112](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:112).

   **Consequência:** reter lotes apenas no `except` não basta. A invalidação precisa restaurar/reconciliar o estado especulativo do mercado antes de nova avaliação, mantendo a rejeição da evidência inválida.

4. **HIGH — `failure_summary` reduz o log, mas não garante ausência de parâmetros ou SQL.**

   `detail` é copiado diretamente; uma violação NOT NULL pode conter a linha recusada, e uma violação de unicidade pode conter os valores da chave. A mensagem de um erro de conversão também pode incorporar o valor rejeitado. Sem `orig`, uma exceção comum contendo SQL ou um segredo na primeira linha será registrada pelo fallback `str(root)`. Limitar a 240 caracteres não elimina o conteúdo sensível.

   Os caminhos estão em [failure_summary.py:79](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/failure_summary.py:79).

   **Correção necessária:** usar campos permitidos, como classe, SQLSTATE, constraint conhecida e frames; mensagem fixa para classes conhecidas; não registrar `detail` arbitrário nem mensagens genéricas sem sanitização. Se desejarem o `market_id`, extraí-lo somente para a constraint esperada e validar seu formato.

   Para exceções normais sem `orig`, **o código funciona**: há fallback para causa/contexto e para a própria exceção, com cadeia limitada. O problema demonstrável é confidencialidade, não a ausência de `orig`: [failure_summary.py:35](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/failure_summary.py:35).

**NICE-TO-HAVE**

- **120 s é um ponto inicial razoável**, não um limiar validado por distribuição de latência. A cadência configurada de flush é 1 s, mas isso não garante um commit por segundo sob carga: [config.py:56](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/config.py:56). Corrigiria primeiro a medição, sem baixar o limiar.
- Com probes rápidas, cinco falhas espaçadas em 15 s acrescentam aproximadamente **60–75 s** após ultrapassar o limiar: cerca de **180–195 s** desde a primeira pendência. Probes lentas ampliam isso. A promessa de “dentro dos primeiros três minutos” está excessiva em [health.py:84](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/health.py:84); configuração em [docker-compose.yml:381](/C:/dev/project-hunter/infra/docker/docker-compose.yml:381).
- Há também **falso positivo semântico de persistência**: o banco já commitou, mas `flush_batch` ainda executa callbacks e ACKs. ACKs suficientemente demorados mantêm o relógio aberto apesar da escrita durável. Separaria confirmação de commit e conclusão dos ACKs: [persist.py:180](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/persist.py:180).
- Usaria relógio monotônico para duração e UTC para `last_commit_at`; hoje a duração depende da diferença entre relógios UTC: [health.py:148](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/health.py:148).

**O QUE EU FARIA DIFERENTE**

**Sobre a ordem X/Y:** não encontrei na avaliação sequencial um caminho normal que gere Y antes do fechamento de X no mesmo lote. A coleta acrescenta EXPIRE(X) antes de esquecer X; só depois pode nascer Y. `dedupe` mantém a posição da primeira ocorrência de cada identidade, portanto não inverte essa sequência. Ver [collect.py:136](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/collect.py:136) e [writers.py:131](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:131).

O writer de oportunidades realmente não ordena fechamentos primeiro: [writers.py:255](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:255). Acrescentaria essa defesa e seu teste, mas **não a declararia causa comprovada nem cura para um EXPIRE ausente**.

**Menor correção segura da causa:** retenção do lote com um único responsável pela sequência mutação → persistência, incluindo avaliação e watchdog, mais tratamento explícito da invalidação de baseline.

`take()/restore()` só é suficiente se preservar:

- linhas, eventos com os mesmos IDs, ACKs e callbacks;
- a precedência do lote antigo sobre novas transições;
- a exclusão entre os produtores enquanto houver trabalho pendente;
- o estado necessário para desfazer avaliações invalidadas.

Um lock apenas ao redor do SQL chega tarde: a identidade já foi esquecida antes dele, e o watchdog também modifica memória antes do flush próprio. Ver [collect.py:166](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/collect.py:166) e [runners.py:250](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:250).

Reidratação seria complementar, não minha primeira opção para toda falha: o helper atual não é um rollback completo; inclusive, quando não encontra episódio no banco, apenas dá `continue`, preservando eventual estado especulativo existente. Ver [runners.py:332](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:332).

Também não escolheria supersession de oportunidades como correção principal. Uma reconciliação no writer precisaria produzir a expiração e seu evento na mesma transação; o evento normal hoje nasce na coleta, portanto um UPDATE isolado não o reproduz: [collect.py:149](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/collect.py:149).

**Primeiro teste sem Docker para a causa raiz:** X previamente durável; coleta real produz EXPIRE(X); um segundo mercado falha antes do flush; na retomada, exigir que EXPIRE(X) e seu evento continuem disponíveis e sejam persistidos antes de qualquer OPEN(Y). Usaria falha injetada e sincronização por eventos, sem depender de sleeps. O descarte atual deve fazê-lo falhar.

Depois, três regressões indispensáveis:

1. Baseline desaparecida durante EXPIRE(X): após invalidar, não pode haver memória livre para Y com X ainda aberto.
2. Lote com dados falha, seguido de flush vazio: o alarme não pode limpar a pendência nem avançar `last_commit_at`.
3. Mensagem/detail com sentinela sensível: nenhuma sentinela aparece no resumo.

Esses testes verificam os contratos sem Docker; a garantia do índice e da transação ainda exige posteriormente Postgres real.

**CONCORDO COM**

- Medir idade do trabalho pendente é superior a consultar `dirty > 0` naquele instante — desde que a pendência acompanhe o trabalho até sua resolução.
- O mecanismo “memória avança → lote perdido → identidade nova contra identidade antiga aberta” continua consistente.
- Os avisos `scanner_anomalies_superseded` não comprovam reconciliação durável: são emitidos antes do commit, e a escrita de oportunidades vem depois na mesma transação. Isso explica a evidência fornecida de avisos sem `metadata.superseded_by` persistido: [writers.py:211](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:211), [persist.py:172](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/persist.py:172).
- Resumir exceções é necessário para preservar evidência operacional; falta tornar verdadeira a promessa de não expor parâmetros.

**OBSIDIAN**

- **Scanner-lag-2026-10-01** — acrescentar o incidente de 02/10, separando veto comprovado, gatilho desconhecido e invalidação sem exceção.
- **Revisão da Astra — scanner, parada de 02/10 e alarme** — registrar os bloqueantes do diff e os testes propostos.
- **Workers** — documentar a diferença entre ciclo vivo, trabalho pendente, commit efetivo e ACK.
- **Open Bugs** — manter aberta a divergência de oportunidades até cobrir perda de lote e invalidação de baseline.