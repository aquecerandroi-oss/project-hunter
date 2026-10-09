**RESUMO**

**APPROVE.** Os três must-fix estão fechados no escopo desta rodada. Não encontrei cenário concreto restante que justifique bloquear.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit.

**TESTES**

Executei com bytecode, sincronização e plugins automáticos desabilitados, sem cache do pytest:

```text
uv run pytest packages/indicators/tests/meme/test_wallets_stream_parallel_units.py -q -p no:cacheprovider
10 passed, 1 warning in 14.62s
```

Aviso: `Unknown config option: asyncio_mode`, decorrente dos plugins desabilitados. Não executei a suíte completa.

**MUST-FIX**

Nenhum pendente:

- **Limpeza:** SIGINT adiado durante os laços; `terminate`, espera, escalada para `kill` e erro explícito com PIDs sobreviventes em [stream_parallel.py:134](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:134). Os caminhos de falha preservam `shutdown(wait=False)` em `finally` em [stream_parallel.py:178](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:178).
- **Bases e denominadores:** projeções separadas, envelope e distância da meta corrigidos em [wallets-cpu.md:358](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:358); percentuais corrigidos em [KB-0187:72](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0187-a-densidade-por-mint-mora-em-poucas-pools.md:72).
- **Evento versus cópia:** distinção explícita em [wallets-cpu.md:347](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:347), com possibilidade de erro para ambos os lados também no [leitor:12](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallet-tape-density-read.py:12).

**NICE-TO-HAVE**

Ajustar a promessa absoluta de “processos encerrados ao levantar exceção” em [stream_parallel.py:25](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:25): o contrato agora admite corretamente `RuntimeError` denunciando sobreviventes.

**O QUE EU FARIA DIFERENTE**

Retiro a exigência implícita da revisão anterior de resistir a exceções arbitrárias injetadas por tracing em qualquer linha. Isso não constitui um critério razoável de aceite desta limpeza.

**CONCORDO COM**

O teste de SIGINT real verifica a ameaça relevante: sinal durante `terminate`, encerramento dos filhos e interrupção entregue ao final — [teste:202](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_stream_parallel_units.py:202).

**OBSIDIAN**

- **wallets-cpu-step3** — acrescentar APPROVE desta rodada, resultado dos testes e correção do critério baseado em tracing.
- **KB-0187 — A densidade por mint mora em poucas pools** — atualizar o campo `astra` para registrar a aprovação das correções, preservando os limites do cenário.