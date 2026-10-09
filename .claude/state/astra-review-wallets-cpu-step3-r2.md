**RESUMO**

**REQUEST_CHANGES.** Dos três must-fix: **1 continua aberto; 2 foi parcialmente resolvido; 3 está fechado.** As extrapolações principais conferem. Restam dois cenários concretos de falha e pequenas correções no registro.

Revisão como `code-reviewer`, considerando a memória compartilhada em [wallets-cpu.md](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:186).

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Executei com sincronização, cache do pytest e escrita de bytecode desabilitados:

```text
uv run pytest packages/indicators/tests/meme/test_wallets_stream_parallel.py -q
24 passed in 296.03s (0:04:56)
```

Sondas adicionais em memória, sem captura de rede:

```text
crossing bins: 1
empty full hour: 0
short 3599.6: run of 3599.6 s, shorter than 3 600 s
half open boundary: 1

interrupt propagated
seconds= 0.002 children_alive= 1
probe_cleanup_children= 0

cancel before hour, cleanup after: 3600.0 0
```

Não repeti a suíte completa, os mutantes nem o benchmark.

**MUST-FIX**

1. **HIGH — Repetir `shutdown` ainda pode devolver o controle com um filho vivo.**

   [stream_parallel.py:118](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:118) presume que a segunda chamada retoma a espera. No CPython 3.12, uma interrupção durante a aquisição do lock interno de `Thread.join` pode marcar a thread como encerrada; o próximo `join` retorna imediatamente. O executor então fecha recursos que a thread de gerenciamento ainda usa. Veja [Thread._wait_for_tstate_lock](https://github.com/python/cpython/blob/v3.12.14/Lib/threading.py#L1139) e [ProcessPoolExecutor.shutdown](https://github.com/python/cpython/blob/v3.12.14/Lib/concurrent/futures/process.py#L851).

   **Reprodução:** executor real com `spawn`, tarefa finita em andamento e `KeyboardInterrupt` injetado na aquisição desse lock. `close_pool` relançou em **0,002 s com um filho vivo**; a thread de gerenciamento também apresentou `WinError 6`. A sonda precisou encerrar explicitamente o filho restante.

   Foi **injeção de falha**, não Ctrl+C manual. O [stub atual:319](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_stream_parallel.py:319) comprova duas chamadas, mas não reproduz essa alteração do estado interno. É necessário proteger a conclusão efetiva do encerramento e acrescentar regressão com executor real.

2. **MEDIUM — O portão de uma hora ainda inclui tempo de limpeza após interrupção.**

   [density-probe.py:136](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallet-tape-density-probe.py:136) calcula a duração **depois** de `run` terminar sua limpeza. Esse caminho primeiro cancela os leitores e depois pode aguardar até 60 segundos para drenar filas. [wallet_tape_probe_net.py:218](C:/dev/project-hunter/infra/scripts/wallet_tape_probe_net.py:218)

   **Cenário:** pedido de 3.600 s, captura interrompida em **3.599,6 s**, limpeza concluída em **3.601 s**. O `min` publica **3.600 s** e libera a estatística, embora a captura tenha terminado antes da hora. Reproduzi o caminho com relógio e execução simulados, mantendo a saída em memória.

   Registrar o instante em que a recepção termina, antes da drenagem, resolve a duração. **Os dois ponteiros, a fronteira semiaberta e os três exemplos anteriores estão corretos.**

**NICE-TO-HAVE**

Correções de registro, sem um terceiro bloqueio independente:

- A [faixa histórica:279](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:279) precisa dizer **“configurações com eventos”**. Incluindo a janela vazia, runs 1–2 dão **0,75–1,52×** para 1w/2w e **0,35–1,00×** para serial/2w. A exceção está na [run 2:37](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/workers-2026-10-06-step3-run2.txt:37).
- O [startup de 1,2–2,9 s:282](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:282) não cobre todas as rodadas: a base da [run 3:5](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/workers-2026-10-06-step3-run3.txt:5) registra **3,1875 s por worker**. Para todas as observações, usar **1,2–3,2 s**.
- Não encontrei nos artefatos conferidos a medição isolada que sustenta **1,05/0,22 s de pickle**, **1,16 s de desempacotamento** e **1,5 s de imports**. Acrescentar fonte reproduzível às [linhas 197](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:197) e [282](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:282); os totais dos benchmarks não demonstram essas parcelas.

**O QUE EU FARIA DIFERENTE**

Testaria o encerramento no executor real, verificando os processos após a exceção. Na sonda, separaria explicitamente **fim da captura** e **fim da limpeza**.

**CONCORDO COM**

- **Must-fix 3 fechado:** plano e fecho medem parede e CPU da thread; `f` e `k` usam CPU/CPU, e a expressão foi corretamente reclassificada como estimativa idealizada. [workers.py:199](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-workers.py:199), [workers.py:292](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-workers.py:292).
- Recalculando as linhas `ROW`, obtive **0,571066–0,841151 Ts** pelo modelo e **0,607868–0,845416 Ts** pela vazão. As faixas **0,57–0,84**, **0,61–0,85**, o cenário composto **0,3–2,2 h** e o envelope linear **1,3–3,3 h** estão sustentados. [Registro:293](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:293)
- A tabela da run 3 e as cinco linhas de eventos/cópias/cotações/CPU do mint quente conferem com os respectivos brutos. [Run 3:5](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/workers-2026-10-06-step3-run3.txt:5), [hot-mint-sweep:2](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/hot-mint-sweep-2026-10-06-step3.txt:2).
- Entraram o teto de 256 mints, o consumo dos futures com `pop` e o retorno sem construir pool para fonte vazia. [stream_parallel.py:50](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:50), [67](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:67), [176](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:176).

**OBSIDIAN**

- **Revisão da Astra: CPU do motor de carteiras, passo 3** — registrar esta rodada e retirar o fechamento antecipado dos três must-fix.
- **CPU do motor de carteiras: medir antes de reescrever** — corrigir as faixas históricas/startup, vincular as medições isoladas e registrar os dois problemas restantes.