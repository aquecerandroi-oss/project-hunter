## RESUMO

**REQUEST_CHANGES: corrigir a equivalência do tape, a definição de publicação bem-sucedida na métrica e as conclusões excessivas da prova.**

Aceito o cache por bytes e o transporte restrito do memo. Aceito suspender o bootstrap sob sobrecarga contínua. Para o consumidor, **defendo primeiro processamento em lote**, preservando a semântica atual.

Papel adotado: `code-reviewer`; modo OPINIÃO.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Não executei testes nem reproduzi a prova operacional nesta revisão. Os achados abaixo vêm da leitura do diff, dos testes e dos registros fornecidos; os números operacionais são os registrados em `t25-proof.md`.

## MUST-FIX

**1. MEDIUM — A: `_NEVER` muda quais entradas o loader aceita.**

Em [hotcache.py:257](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/hotcache.py:257), o cache decodifica o trade com corte máximo. No loader original, `ts > as_of` descarta a linha **antes** de acessar e validar `side`: [hotstate.py:231](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:231).

**Cenário:** linha com timestamp posterior ao corte, preço/quantidade válidos e `side="INVALID"` — ou sem `side`. O loader original retorna normalmente, ignorando-a; o cache levanta `ValueError`/`KeyError`. Isso pode interromper o ciclo inteiro, cujo tratamento abandona o restante da passada: [runners.py:109](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:109).

**Correção sugerida, dentro do escopo:** quando a decodificação antecipada falhar, consultar o loader de produção com o corte real. Se ele aceitar a linha naquele corte, não guardar uma recusa definitiva; tentar novamente em cortes futuros. Se também falhar, propagar. Assim você preserva a ordem de validação sem criar outro decodificador.

Acrescente esse cruzamento **futuro + corrupção**, comparando retorno e exceção antes, exatamente no timestamp e depois dele. Os casos atuais testam futuro e corrupção separadamente: [test_hotcache.py:187](C:/dev/project-hunter/services/scanner-worker/tests/test_hotcache.py:187).

**2. HIGH — D: `scored` não prova que uma oportunidade foi publicada.**

O runner observa o histograma quando `evaluation.scored` é verdadeiro: [runners.py:87](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:87). Entretanto, `publish_radar`:

- retorna sem escrever quando não há score/status utilizável: [publish.py:93](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/publish.py:93);
- absorve exceções de publicação: [publish.py:117](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/publish.py:117).

**Cenário:** Redis recusa a atualização do Radar; a função retorna e o histograma registra uma oportunidade “publicada” em poucos segundos, embora o usuário continue vendo a anterior.

Eu manteria `scored` para medir **avaliações do scorer**, mas faria a publicação devolver um resultado explícito: publicada, sem projeção ou falhou. A latência até o Radar só recebe amostra após sucesso; falhas precisam de contagem própria.

O teste atual espiona `publish_features` e deliberadamente usa um cenário sem score publicável. Portanto, prova a ordem da tentativa, não a conclusão da publicação: [test_load.py:278](C:/dev/project-hunter/services/scanner-worker/tests/test_load.py:278).

E delimite o destino: o evento durável `opportunities.updated` passa pelo outbox; esta medição ocorre antes do flush. Ela pode ser **tick→Radar**, mas ainda não é tick→entrega do evento durável: [publish.py:5](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/publish.py:5), [runners.py:99](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:99).

**3. MEDIUM — A prova afirma mais do que demonstra.**

Há dois pontos a corrigir antes de usá-la como aceite:

- **“6.400 = nenhum minuto perdido” não decorre da contagem.** O próprio registro informa **201 mercados distintos**, embora o universo nominal seja 200: [t25-proof.md:590](C:/dev/project-hunter/.claude/state/t25-proof.md:590). Cenário: faltam combinações mercado/minuto, compensadas por outras combinações durante uma troca de universo. Exija comparação entre pares esperados e gravados, considerando a elegibilidade por minuto.
- **“O consumidor é o dono do p99” ainda é hipótese causal.** `last_input_ts` guarda o maior timestamp recebido entre os gatilhos, não exclusivamente o de ticks: [state.py:129](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/state.py:129), [main.py:184](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:184). Um fechamento recente pode substituir o timestamp de um tick atrasado. Portanto, “tick atrasado dez minutos necessariamente entra como 600 s” não vale para toda amostra, como afirma [t25-proof.md:573](C:/dev/project-hunter/.claude/state/t25-proof.md:573).

Aceito os sintomas registrados; retiraria a atribuição exclusiva até medir as etapas separadamente.

## NICE-TO-HAVE

- **B — ampliar o teste de contrato:** manter minutos iguais e atravessar fronteiras de 15 minutos com `as_of`, incluindo vazio, warm-up e gaps. O teste atual varia apenas dois instantes dentro do mesmo minuto; é uma regressão útil, não uma prova universal de pureza: [test_hotcache.py:273](C:/dev/project-hunter/services/scanner-worker/tests/test_hotcache.py:273).
- **C — testar pressão surgindo dentro da mesma chamada.** O teste chamado “between slices” altera a pressão entre duas chamadas de `run_slice`; remover a checagem interna poderia deixá-lo verde: [test_pressure.py:125](C:/dev/project-hunter/services/scanner-worker/tests/test_pressure.py:125).
- **Contador de decode:** somar contadores dos mercados presentes perde incrementos quando um mercado sai. Exemplo: total anterior 1.000; saem 500 e outros decodificam 100; o delta negativo vira zero. Prefira contabilizar no ponto da decodificação: [health.py:204](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/health.py:204).
- **Thresholds:** `1 s` coincide com o padrão, mas não está ligado dinamicamente ao config. `LivePressure(scanner.state)` usa constantes próprias: [main.py:128](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:128), [pressure.py:52](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/pressure.py:52).

## O QUE EU FARIA DIFERENTE

**Consumo: escolheria (a), com lote de verdade.**

`consume` já faz `XREADGROUP count=batch`; aumentar apenas esse número não elimina as verificações sequenciais de deduplicação: [consume.py:189](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:189). Para eventos novos, a guarda consulta os dois conjuntos diários, e o scanner ainda aguarda um ACK por mensagem: [consume.py:135](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:135), [consumers.py:160](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/consumers.py:160).

Eu agruparia consultas de pertença e ACKs elegíveis, com orçamento cooperativo. **Uma ida ao Redis por lote, mantendo uma decisão por `event_id`.**

O que pode quebrar numa implementação ingênua: ACK antecipado dos fechamentos, deduplicação na virada UTC, duplicatas dentro do lote e monopolização do event loop. Os fechamentos devem continuar aguardando persistência; isso já é contrato explícito: [consumers.py:14](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/consumers.py:14).

**Não escolheria `XGROUP SETID $` como primeira correção.** O comando avança o cursor do grupo para o último registro; não é uma política completa de reconciliação. [Documentação Redis](https://redis.io/docs/latest/commands/xgroup-setid/).

Perder dezenove notificações quando uma vigésima marca o mercado não equivale a perder **todas**. Cenário: um mercado pouco ativo tem sua única notificação no trecho pulado; nenhum tick seguinte garante avaliação imediata. Além disso, o consumidor existente recupera pendências via `XAUTOCLAIM`, caminho que precisa ser tratado separadamente: [consume.py:173](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:173).

Se futuramente adotarmos descarte, eu exigiria: grupo exclusivo de notificações, reconciliação de todos os mercados afetados, tratamento das pendências e contador de descartes. Nunca aplicar aos fechamentos.

**Diagnóstico:** aceito leitura cara e consumo insuficiente como gargalos candidatos. Não aceito atribuir os 16–21 ms integralmente ao parser: `read_hot_state` mede o pipeline inteiro, incluindo transporte e espera no loop: [hotstate.py:85](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:85). A própria nota reconhece que o ganho com hiredis não foi medido: [notes-T2.5.md:740](C:/dev/project-hunter/.claude/state/notes-T2.5.md:740).

Mediria separadamente atraso por stream, espera no dirty set, leitura, cálculo e publicação. A comparação com hiredis e com consumo em lote deveria usar carga equivalente.

## CONCORDO COM

**A:** reconstruir a sequência a partir de todas as linhas recebidas resolve os contraexemplos de remoção e reescrita histórica. Não encontrei divergência na montagem normal dos `SourceEntry`; a ressalva concreta é a validação antecipada do trade: [hotcache.py:94](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/hotcache.py:94).

**B:** aceito o acoplamento local, declarado e restrito. Hoje `_index` depende de `final_candles`, e `_bars_15m` ancora em `last_final`, também derivado dessa tupla: [windows.py:102](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:102), [windows.py:208](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:208). O comentário sobre morrer com o contexto ficou incompatível com o uso atual, mas isso não constitui, sozinho, um bug. Com `packages/**` fora do escopo, manteria o adaptador; depois formalizaria a interface no pacote.

**C:** suspensão permanente sob sobrecarga é **starvation deliberada do trabalho secundário**, sem evidência de deadlock circular. O replay preserva o job e cede execução enquanto há pressão: [replay.py:161](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/replay.py:161). Não imporia progresso mínimo por hora sacrificando o live. Exporia também tempo suspenso e idade do último progresso; zero cortes significa bootstrap pendente, não concluído.

**D:** não colocaria todo vetor no histograma de oportunidade. Usaria métricas distintas para vetor publicado, scorer executado e Radar publicado. Mover a observação para depois do publish foi correto; falta comprovar qual publicação realmente aconteceu.

## OBSIDIAN

- **Features (Feature Engine)** — registrar o cache por bytes, o contrato restrito do memo e o caso futuro + `side` inválido.
- **Workers** — documentar starvation intencional do bootstrap e as fronteiras das métricas.
- **Data Flow** — distinguir coalescência de notificações, descarte de backlog e ACK após efeito durável.
- **Revisoes-Astra/T2.5c — diff** — registrar os três bloqueios, a preferência por lotes e os limites causais da prova.