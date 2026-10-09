**RESUMO**

**REQUEST_CHANGES.** A prova de concorrência foi corrigida, mas ainda reproduzi workers vivos após `abort_pool`. Os números centrais da densidade conferem; há erros na descrição das extrapolações e uma inferência indevida sobre cópias.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Executei com bytecode, cache e plugins automáticos desabilitados:

```text
uv run pytest packages/indicators/tests/meme/test_wallets_stream_parallel_units.py -q -p no:cacheprovider
8 passed, 1 warning in 2.16s
```

O aviso foi `Unknown config option: asyncio_mode`, pela desativação dos plugins.

Duas sondas em memória, com executor real de dois workers:

```text
BETWEEN_LOOP_ABORT_RETURNED [(9300, True), (6292, True)]
EXHAUSTED_ABORT_RETURNED 3 30.0 [(42124, True), (21944, False)]
```

Todos os processos dessas sondas foram encerrados depois.

Executei também o leitor de densidade e recalculei independentemente os JSONs e a curva sintética. Não executei o teste `Rendezvous`, pois ele cria arquivos; fiz sua revisão estática.

**MUST-FIX**

1. **HIGH — a limpeza ainda pode devolver o controle com workers vivos.**

   Em [stream_parallel.py:140](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:140), o `try` protege `act(proc)`, mas não o laço inteiro.

   **Cenário reproduzido:** injetei `KeyboardInterrupt` por tracing na linha 140, antes da primeira tentativa. O `finally` executou `shutdown(wait=False)`, mas `abort_pool` escapou com **dois workers vivos**.

   Há uma segunda saída: três interrupções antes de efetivar `terminate` esgotam as tentativas; o `join(30)` retorna por timeout e ninguém verifica se o processo morreu ([stream_parallel.py:131](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_parallel.py:131)). Reproduzi **um worker vivo após 30 segundos**.

   É necessário proteger a limpeza inteira contra interrupções adiáveis e tratar explicitamente sobreviventes após o timeout. As três tentativas não sustentam a garantia de ausência de workers vivos.

2. **MEDIUM — corrigir os números e os denominadores do registro.**

   Em [wallets-cpu.md:358](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:358), **23–96 h** mistura duas bases:

   - passo 2 × M × fator dos workers: **23,28–90,45 h**;
   - projeção direta × fator dos workers: **55,06–96,25 h**.

   **23–96 h pode ser chamado de envelope das duas projeções**, explicitando isso. Não é o resultado de uma única multiplicação. Também não corresponde integralmente à distância de **25–50×** da meta: esse envelope dá aproximadamente **12–48×**.

   As cinco chaves extrapoladas representam **49,98–57,84%** do custo, não 40–50% ([KB-0187:72](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0187-a-densidade-por-mint-mora-em-poucas-pools.md:72)). **39,5% refere-se aos swaps com chave**, não à proporção de chaves de pool, como aparece em [wallets-cpu.md:371](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:371).

   **Cenário:** usar esses resumos para dimensionar CPU subestima a participação da região não medida e apresenta como uma faixa homogênea resultados de bases distintas.

3. **MEDIUM — densidade ponderada por eventos não demonstra a densidade de uma cópia típica.**

   A passagem em [wallets-cpu.md:347](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:347) faz essa equivalência; o leitor ainda afirma que a estimativa tende para baixo ([density-read.py:12](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallet-tape-density-read.py:12)).

   **Cenário concreto:** uma pool concentra 124 mil swaps de poucos robôs, com compras abaixo do piso. Ela pesa muito em Σn²/Σn, mas pode gerar zero apostas elegíveis: o motor filtra compras pelo piso e pela entidade já vista ([stream.py:128](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:128)). O custo sintético pode então **superestimar**, não necessariamente subestimar.

   Manter os números como cenário condicionado à distribuição sintética de cópias. Retirar a afirmação de viés necessariamente para baixo e a identificação com a cópia típica.

**NICE-TO-HAVE**

Em [KB-0187:31](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0187-a-densidade-por-mint-mora-em-poucas-pools.md:31), esclarecer que “todas pools” se refere apenas às cinco acima de 16 mil/h: existem **34 curvas ≥1 mil/h e uma ≥4 mil/h**.

**O QUE EU FARIA DIFERENTE**

Publicaria separadamente: contagens observadas, projeção direta e cenário composto. A média por cópia exige medir apostas elegíveis por chave e seus horizontes efetivos.

**CONCORDO COM**

A barreira corrigiu o falso positivo anterior: registra PID, espera dois processos e retém o primeiro mint até outro ser emitido ([stream_fetch.py:91](C:/dev/project-hunter/packages/indicators/tests/meme/stream_fetch.py:91)). O teste exige explicitamente dois PIDs e inversão ([test_wallets_stream_parallel.py:253](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_stream_parallel.py:253)). **Não encontrei caminho para passar sem essas condições na fixture atual.**

Conferência dos números publicados em [density-read.md:19](C:/dev/project-hunter/.claude/state/carteiras-lucro/density/run1/density-read.md:19) e [wallets-cpu.md:354](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:354):

| Métrica | Recalculado |
|---|---:|
| Σn²/Σn, total | 22.134.993.551 / 1.297.301 = **17.062,342** |
| Curva / pool | **738,051 / 20.904,294** |
| Chaves ≥1 mil / ≥4 mil | **235 / 58** |
| Maior chave | **Bnf84yYNCo…: 124.069** |
| M | **5,673–6,730×** |
| Projeção direta, 168 horas | **96,60–114,59 h** |
| M × passo 2 | **40,85–107,67 h** |
| Caminho crítico condicionado | **38,21–55,71 h** |

Os limites de **uma captura curta, curva sintética, extrapolação além de 16 mil/h e pools inferidas** estão declarados ([KB-0187:68](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0187-a-densidade-por-mint-mora-em-poucas-pools.md:68)). Isso é correto; faltam os ajustes acima.

**OBSIDIAN**

- **wallets-cpu-step3** — reabrir o encerramento: interrupção fora do `try` e sobrevivência após esgotar tentativas.
- **wallets-cpu** — separar projeções, corrigir percentuais e qualificar a média por cópia.
- **KB-0187 — A densidade por mint mora em poucas pools** — registrar esta revisão e corrigir participação extrapolada e interpretação.
- **Open Bugs** — registrar os dois cenários reproduzidos de workers vivos após `abort_pool`.