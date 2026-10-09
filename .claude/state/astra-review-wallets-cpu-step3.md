**RESUMO**

**REQUEST_CHANGES**, por três pontos: interrupção durante o shutdown, contagem da janela de densidade e interpretação das medições. **Não encontrei divergência contábil entre serial e paralelo sob o contrato da fonte.**

Revisão como `code-reviewer`, considerando o [plano compartilhado](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md) e o [parecer de desenho](C:/dev/project-hunter/.claude/state/astra-review-wallets-cpu-step3-design.md).

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit. Captura de rede não executada.

**TESTES**

Executei, com sincronização e caches de teste/bytecode desabilitados:

```text
uv run pytest packages/indicators/tests/meme/test_wallets_stream_parallel.py -q
21 passed in 257.25s (0:04:17)
```

Sondas adicionais em memória, via `uv run python -c`:

```text
initializer: BrokenProcessPool children: 0
emit KeyboardInterrupt: propagated; children: 0
interrupt during normal shutdown; children at caller: 1
probe explicit cleanup; children: 0

empty source equal: True children: 0
stream_snapshot repeated_mint children: 0
stream_snapshot_parallel repeated_mint children: 0

61min_peak_crossing_bins 0
60min_empty run shorter than 60 min
3599.6s_rounded 1
```

A interrupção no shutdown foi **injeção de falha no `join`**, não um Ctrl+C manual. A própria sonda encerrou o processo restante. Não repeti a suíte completa nem os 17 mutantes.

**MUST-FIX**

1. **HIGH — O shutdown normal está fora da proteção contra `KeyboardInterrupt`.**

   O `try/except BaseException` fica **dentro** do `with`; portanto, não captura uma interrupção no `ProcessPoolExecutor.__exit__`. Veja [stream_parallel.py:157](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:157).

   **Cenário reproduzido:** todos os resultados chegaram; o worker está encerrando, com um finalizador finito ainda em execução; o `join` recebe `KeyboardInterrupt`. O chamador recebe a exceção com **um filho vivo**. Isso contraria a garantia declarada em [stream_parallel.py:25](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:25). O encerramento do executor efetivamente aguarda uma thread por `join`, conforme a [implementação do CPython 3.12](https://github.com/python/cpython/blob/v3.12.14/Lib/concurrent/futures/process.py).

   Eu protegeria **todo o ciclo de encerramento**, preservando a interrupção para relançá-la após concluir a limpeza. Acrescentaria teste específico de interrupção durante o shutdown, além do teste no `emit`.

   A falha no initializer funcionou: resultou em `BrokenProcessPool`, com zero filhos. O cancelamento atual continua sendo “cancelar pendentes e aguardar iniciados”; não interrompe um `fetch` bloqueado.

2. **MEDIUM — A densidade publicada não é o máximo de qualquer janela móvel de 60 minutos.**

   [density-probe.py:74](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallet-tape-density-probe.py:74) considera somente janelas alinhadas aos buckets de minuto.

   **Cenário reproduzido:** corrida de 61 minutos, com 500 eventos em `t=59,9 s` e outros 500 em `t=3600,1 s`. Os 1.000 cabem em **3.540,2 segundos**, mas nenhuma janela examinada contém ambos os buckets: o resultado é **zero chaves**.

   Há mais dois casos no mesmo contrato:

   - Uma corrida vazia de 60 minutos informa “run shorter than 60 min”, porque [density-probe.py:97](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallet-tape-density-probe.py:97) testa se `rolling` tem elementos, em vez da duração.
   - A duração vem de `curve[-1]["t"]`, já arredondada; **3.599,6 s viram 3.600 s**, liberando a métrica antes de uma hora completa. Veja [density-probe.py:116](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallet-tape-density-probe.py:116) e [probe_stats.py:306](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_stats.py:306).

   Usaria duração não arredondada e deslizamento por timestamps. Se mantiver os buckets, o resultado precisa ser identificado como **máximo entre janelas alinhadas ao minuto**, com possibilidade de subcontagem.

3. **MEDIUM — Corrigir a instrumentação e os rótulos antes de publicar `f`, `k` e a extrapolação.**

   `plan_s` e `finish_s` medem **parede**, via `perf_counter`; o total do serial mede CPU via `process_time`. Não existe medição da CPU do replay serial isolado. Veja [workers.py:194](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-workers.py:194) e [workers.py:223](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-workers.py:223). A [nota:273](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:273) trata essas parcelas como CPU.

   **Cenário de falha:** o coordenador fica desagendado durante o plano. Esse atraso entra como trabalho serial e é subtraído da CPU total para estimar replay; `f` e `k` mudam sem mudança correspondente no trabalho.

   A fórmula `f + (1−f)·k/2` está correta **como modelo idealizado**, mas não inclui explicitamente a CPU do coordenador durante submissão, desserialização e redução. Dois workers mais esse coordenador também disputam os dois núcleos.

   **Os 0,4–2,1 h são um cenário composto**, combinando frações atuais com tempos do passo 2; não são a extrapolação direta do coordenador medido. Recalculando as linhas `best` da run 2 com eventos:

   | Parcela extrapolada linearmente para 217 M fills | Faixa |
   |---|---:|
   | Parede de `plan+finish` | 1,63–2,58 h |
   | CPU total do coordenador | 3,56–6,35 h |

   Essas faixas **também não são previsões de produção**: incluem efeitos do benchmark e custos que não escalam necessariamente por fill. Servem para mostrar que as parcelas são diferentes. [Log da run 2](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/workers-2026-10-06-step3-run2.txt:5)

   Finalmente, [workers.py:291](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-workers.py:291) não produz um limite inferior rigoroso: soma o maior startup à metade do trabalho, embora um worker possa executar enquanto outro ainda inicia; também usa o replay isolado medido em outra execução. Eu o chamaria de **estimativa idealizada**, retirando `T2 >=`.

**NICE-TO-HAVE**

- **Limitar também a quantidade de mints por chunk.** Dez mil mints de custo zero viraram um único chunk na sonda. Carries contendo apenas `create` têm custo zero, mas não são vazios. Veja [stream.py:89](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:89), [carry.py:142](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/carry.py:142) e [stream_parallel.py:82](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:82).
- Liberar futures consumidos de `done` imediatamente: o conjunto mantém os resultados durante os yields, aumentando a memória transitória. [stream_parallel.py:65](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:65)
- Fonte vazia **não inicia filhos**, confirmado; contudo, ainda constrói o executor. Um retorno antecipado atenderia literalmente “sem pool”. [stream_parallel.py:153](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:153)
- Identificar separadamente as chaves de compras PumpSwap inferidas: `inferred_pool` é uma inferência de layout, não o resultado de um decoder confirmado. [probe_core.py:174](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_core.py:174)

**O QUE EU FARIA DIFERENTE**

Mediria CPU **e** parede de plano, replay e fecho no serial; nos workers, separaria fetch, replay e transporte. Calcularia cada razão com observações identificadas, mantendo a projeção idealizada separada do tempo total esperado.

**CONCORDO COM**

- **Equivalência:** apostas recebem o teto global antes da distribuição; `replace` troca apenas apostas e sementes do mint. Os demais dados da noite permanecem comuns. [stream.py:137](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:137), [stream_parallel.py:119](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:119)
- **Redução:** somas inteiras, uniões, máximo preservando ausência e holds completos; métricas finais depois da fusão. Books, cópias e W-PnL têm suas chaves unidas separadamente. [stream_metrics.py:108](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_metrics.py:108), [stream_mint.py:100](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:100)
- **Casos-limite:** mint só com carry é processado; repetição é recusada; carries sem `emit` são reconstruídos pela ordem registrada da fonte. [stream_parallel.py:115](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:115), [stream_source.py:112](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_source.py:112), [stream_parallel.py:174](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:174)
- Os dois must-fix do desenho foram absorvidos: transporte de `ContractViolation` e contrato explícito de fonte imutável. [carry.py:38](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/carry.py:38), [carry.py:98](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/carry.py:98)
- A chave de densidade está correta para o escopo declarado: **mint da curva ou pool**, sem junção. [density-probe.py:54](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallet-tape-density-probe.py:54)
- O diagnóstico de desempenho é honesto: nas configurações **com eventos**, dois workers vencem um worker, mas perdem para o serial. Na janela vazia com carry grande, também perdem para um worker: **0,75×**. [Log:36](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/workers-2026-10-06-step3-run2.txt:36)

**OBSIDIAN**

- **CPU do motor de carteiras: medir antes de reescrever** — corrigir unidades, proveniência das razões e limites da extrapolação.
- **Revisão da Astra: CPU do motor de carteiras, passo 3** — registrar os três must-fix e as provas executadas nesta revisão.
- **Revisão da Astra: motor de carteiras em memória limitada** — registrar o orçamento por chunk e a lacuna de interrupção no shutdown.