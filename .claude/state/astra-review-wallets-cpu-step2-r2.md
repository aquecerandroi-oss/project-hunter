**RESUMO**

**REQUEST_CHANGES — pelos registros de medição. Os dois must-fix de código da rodada 1 estão fechados.** Os ajustes adicionais solicitados também estão presentes; os 217 testes de `meme` passaram nesta sessão.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit.

| Item conferido | Resultado |
|---|---|
| Carteiras repetidas | **Fechado.** `set(wallets)` elimina carteiras repetidas, preservando os eventos e sua ordem: [pricing.py:200](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:200). O teste compara com a subsequência filtrada: [test_wallets_cpu.py:141](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_cpu.py:141). |
| RSS no Windows | **Fechado.** `HANDLE`, argumentos e retorno estão declarados; retorno falso produz `None`: [profile.py:113](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-profile.py:113). Confirmei a chamada real e uma falha simulada. |
| Piso do stop e comentário A | **Absorvidos.** O piso nasce depois da guarda de término, no primeiro evento efetivamente avaliado; o comentário foi corrigido: [policy.py:153](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:153). Teste com sNaN: [test_wallets_cpu.py:255](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_cpu.py:255). |
| Memo | **Absorvido.** `cache_clear()` seguido de `len(made) == 1`: [test_wallets_cpu.py:100](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_cpu.py:100). |
| Instrumento de medição | **Absorvido no script.** Rodada nua, memo frio antes de cada chamada medida e contagem total: [profile.py:240](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-profile.py:240), [profile.py:259](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-profile.py:259). `--repeat`: [profile.py:327](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-profile.py:327). |

**TESTES**

Executados com bytecode, cache do pytest e sincronização do ambiente desabilitados:

| Comando | Saída real |
|---|---|
| `uv run pytest packages/indicators/tests/meme/test_wallets_cpu.py packages/indicators/tests/meme/test_wallets_golden.py -q` | `13 passed in 10.67s` |
| `uv run pytest packages/indicators/tests/meme -q` | `217 passed in 39.20s` |
| `uv run python -` — sondagem em memória da função RSS e das contas | `Windows real peak_rss_mb: 18.173952` · `Windows simulated API failure: None` |

Não rerodei a matriz de benchmarks, lint ou typecheck.

**MUST-FIX**

**1. MEDIUM — Há resultados publicados sem suporte nos artefatos citados.**

- A nota afirma **duas rodadas, 5,4–7,9 s e 140–205 µs/fill** em [wallets-cpu.md:135](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:135). O arquivo citado contém somente um par HEAD/TREE: **14,922 → 7,891 s**, com 38.456 fills, ou **388,03 → 205,20 µs/fill**. Não contém a rodada de 5,4 s: [benchmark:8](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/run-2026-10-06-head-vs-tree.txt:8), [benchmark:21](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/run-2026-10-06-head-vs-tree.txt:21).
- O HOT de 4.000 eventos é publicado como **11,0–14,7 → 2,7 s**, inclusive para orientar o passo 3: [wallets-cpu.md:133](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:133), [wallets-cpu.md:163](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:163). Os `top_mints` dos arquivos before/after mostram **11,049 → 7,134 s de relógio**: [before:392](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/profile-2026-10-06-step1-before.txt:392), [after:392](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/profile-2026-10-06-step1-after.txt:392). O arquivo de estágios não fornece esse tempo por mint.

**Cenário concreto:** dimensionar o processamento usando 140 µs/fill ou um maior mint de 2,7 s, embora essas medições não sejam recuperáveis das fontes indicadas.

**Correção:** anexar e citar as rodadas correspondentes ou retirar esses números e suas extrapolações derivadas.

**2. MEDIUM — A síntese precisa distinguir as rodadas e corrigir as conclusões sobre ruído.**

A tabela de [wallets-cpu.md:118](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:118) combina **tempos da Pass 3** com **contagens da Pass 4**. Os números individuais batem, mas precisam dessa identificação explícita. A Pass 4 documenta rodada nua, três repetições e memo frio, com resultados diferentes:

| Configuração | Pass 3: HEAD → G2 | Pass 4: HEAD → G2 |
|---|---:|---:|
| base | 10,05 → 3,62 s | 11,80 → 5,14 s |
| hot_4k | 15,42 → 5,39 s | 31,91 → 6,27 s |
| fills_16k | 13,34 → 5,97 s | 12,56 → 5,64 s |

Fontes: [estágios:23](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/profile-2026-10-06-step2-stages.txt:23), [estágios:33](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/profile-2026-10-06-step2-stages.txt:33).

Além disso:

- A faixa de **20–40%** não descreve a dispersão registrada: base HEAD vai de 10,05 a 21,78 s, **+117%**; hot_4k G2, de 5,39 a 15,36 s, **+185%**.
- “G2 faz menos chamadas que F em toda configuração contada” é falso: na janela vazia ambos têm exatamente **4.260.799 chamadas**: [estágios:104](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/profile-2026-10-06-step2-stages.txt:104).
- Atribuir o resultado de `burst_120` à carga é **hipótese**; essa configuração não consta na contagem da Pass 4. A afirmação está em [wallets-cpu.md:131](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:131).

**Cenário concreto:** tratar os mínimos da Pass 3 como resultado dos controles documentados na Pass 4 e descartar uma diferença como ruído já explicado, superestimando a certeza do ganho.

**Correção:** separar as passadas, publicar a dispersão observada e marcar a explicação por carga como hipótese.

**NICE-TO-HAVE**

- Identificar expressamente que os **389 µs/fill de `fills_16k`** vêm do rerun. O original registra 559,9 µs/fill e uma interrupção enorme no relógio; o rerun tem outro hash e `pricing.py` dirty. Fontes: [before:177](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/profile-2026-10-06-step1-before.txt:177), [rerun:2](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/profile-2026-10-06-step1-before-fills16k-rerun.txt:2).
- Na [nota da revisão:26](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/wallets-cpu-step2.md:26), distinguir teste de regressão persistido de sondagem de RSS. Confirmei a correção atual; esta rodada não comprova retrospectivamente que ambos tiveram teste vermelho antes.
- A faixa pós-otimização de **17–73% em cópias** exclui a janela vazia, cujo valor é zero. Explicitar isso em [wallets-cpu.md:165](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:165).

**O QUE EU FARIA DIFERENTE**

Publicaria cada tabela com passada, instrumentação, estado do cache e número de repetições. Manteria as medições anteriores como histórico, sem misturar seus resultados numa única faixa sem origem explícita.

**CONCORDO COM**

**A aritmética da extrapolação está correta**, condicionada às faixas de entrada:

| Faixa | Horas para 200–217 M fills, um núcleo |
|---|---:|
| 243–675 µs/fill | 13,50–40,69 h |
| 129–265 µs/fill | 7,17–15,97 h |
| 140–205 µs/fill | 7,78–12,36 h |

Fórmula: `horas = µs/fill × fills ÷ 1.000.000 ÷ 3.600`. O problema da terceira linha é a evidência dos **140**, não a multiplicação.

A meta também confere: `2 × 2 × 3.600 × 1.000.000 ÷ 217.000.000 = 66,3594 µs/fill`. Portanto, **≤66 µs/fill** é um arredondamento conservador para o orçamento ideal. A 200 M, o limite é 72 µs/fill para exatamente duas horas; para **menos** de duas horas, precisa ficar abaixo disso. Os aproximadamente **2–4×** adicionais são coerentes com 129–265 µs/fill, antes dos custos excluídos. [wallets-cpu.md:156](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/wallets-cpu.md:156)

**OBSIDIAN**

- **CPU do motor de carteiras: medir antes de reescrever — wallets-cpu:** corrigir a proveniência dos números, separar Pass 3/4 e revisar as afirmações sobre ruído.
- **Revisão da Astra: CPU do motor de carteiras, passos 1–2 — wallets-cpu-step2:** registrar os dois defeitos de código fechados, os 217 testes desta rodada e o REQUEST_CHANGES restrito à documentação das medições.