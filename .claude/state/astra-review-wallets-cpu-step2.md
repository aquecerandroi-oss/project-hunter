**RESUMO**

**REQUEST_CHANGES**, por dois pontos concretos: o contrato de `of_wallets` com carteiras repetidas e a medição inválida de RSS no Windows.

Não encontrei regressão econômica nas sete mudanças **com os parâmetros e entradas normais do H-030**. Porém, “equivalente em qualquer entrada aceita pelo Python” é uma afirmação forte demais: reproduzi duas diferenças adicionais em entradas patológicas, detalhadas abaixo.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisei os quatro módulos, os testes, o gerador e os artefatos de medição.

**TESTES**

Execuções nesta sessão, com bytecode, cache do pytest e sincronização do ambiente desabilitados:

| Verificação | Saída real |
|---|---|
| `uv run pytest packages/indicators/tests/meme/test_wallets_cpu.py packages/indicators/tests/meme/test_wallets_golden.py -q` | `11 passed in 7.64s` |
| `uv run pytest packages/indicators/tests/meme -q` | `215 passed in 49.57s` |
| `uv run python infra/scripts/check_file_size.py` | `scanned 1176 files; 0 over budget, 0 grandfathered` |

Também carreguei **wallets e curve do commit `84704fa1` diretamente do Git em memória**, sem checkout:

- Todos os digests congelados coincidiram.
- Os testes de CPU contra o motor antigo produziram **`7 failed, 2 passed in 6.10s`**: falharam exatamente os sete testes das remoções de trabalho.
- Sondagens diferenciais adicionais: **60 combinações** de delay/timer/empates e **20 vendas** com contexto Decimal externo alterado, átomos até `10**100` e reservas reais negativas/zeradas preservaram o comportamento.

Não executei novamente o benchmark intercalado nem lint/typecheck.

**MUST-FIX**

**1. MEDIUM — `of_wallets` não cumpre seu contrato para carteiras repetidas.**  
[pricing.py:193](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:193) aceita `Iterable[str]` e promete a mesma subsequência de um filtro, mas a expansão na linha 200 repete posições.

Cenário reproduzido:

```text
carteiras: ['A', 'A', 'B']
filtro antigo: ['A', 'B']
of_wallets:    ['A', 'A', 'B']
```

Isso pode duplicar compras de A e impedir o disparo de “líder vendeu mais da metade”. **O caminho atual do motor está protegido**, porque [entities.py:50](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/entities.py:50) fornece `frozenset`. Mesmo assim, corrigiria o helper recém-introduzido para deduplicar as carteiras antes de reunir as posições; não deduplicaria os eventos da fita.

**2. MEDIUM — RSS inválido está sendo publicado como zero.**  
[2026-10-06-wallets-engine-profile.py:115](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-profile.py:115) chama as APIs Windows sem declarar suas assinaturas e ignora o retorno de `GetProcessMemoryInfo`.

Reprodução nesta máquina:

```text
current signature: success=0 last_error=6 peak_rss_mb=0.0
declared signature: success=1 peak_rss_mb=13.983744
```

Cenário de falha: comparar configurações ou dimensionar dois workers com uma métrica que informa zero apesar de a consulta ter falhado. Declarar `HANDLE`/argumentos/retorno e tratar falha como medição indisponível. Mesmo corrigido, o pico é **do processo inteiro**, incluindo geração, noites anteriores e profiler; não é memória incremental da última noite.

**NICE-TO-HAVE**

**1. Equivalência das sete mudanças e bordas**

| Mudança | Parecer |
|---|---|
| **A — bisect** | Correta. A justificativa “todo landing fica após a entrada” não vale para todos os delays/timers, mas é desnecessária: se `best.landing_slot <= entry_slot`, nenhum evento posterior à entrada passa pelo `break`; os anteriores nunca avaliavam stop. Corrigir apenas a explicação. [policy.py:145](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:145) |
| **B — venda simplificada** | Mesmas operações relevantes, piso, teto e recusas explícitas no domínio econômico. Curva completa retorna antes; `real_sol=0` permanece zero. Há uma diferença extrema de exceção abaixo. [pricing.py:132](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:132) |
| **C — identidades** | Preserva presença/ausência, incluindo programa e ordinal; não modifica a fita nem sua ordem. [pricing.py:203](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:203), [tape.py:127](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/tape.py:127) |
| **D — carteira/posições** | Com carteiras únicas, ordenar posições restaura exatamente a ordem da fita. A ordenação estável posterior preserva empates, inclusive programas diferentes com a mesma chave. Ressalva: MUST-FIX 1. [pricing.py:193](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:193), [policy.py:110](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:110) |
| **E — flows** | Preserva inclusive “última linha vence” no dicionário e multiplicidade do argumento `wallets`; apenas reutiliza o índice do mesmo carry. [carry.py:135](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/carry.py:135), [stream_mint.py:193](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_mint.py:193) |
| **F — memoização** | Preserva valores enquanto o `CONTEXT` do motor permanece fixo. Alterar o contexto ambiente do chamador não altera a conversão. [pricing.py:84](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:84) |
| **G — piso antecipado** | Correta para o piso finito normal: conversão de inteiro e comparação não arredondam. Antecipar a multiplicação, porém, muda quando parâmetros excepcionais falham. [policy.py:60](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:60) |

Duas diferenças **reproduzidas**, que impedem uma promessa irrestrita:

- **G:** fita contendo apenas o gatilho e `stop_fraction=Decimal("sNaN")`: antes retornava `closed/time_cap`; agora lança `InvalidOperation`, porque calcula o piso mesmo sem evento de stop. O ponto é [policy.py:153](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:153).
- **B:** `Reserves("curve", 10**1000008, 1, 0)`, venda de um átomo, taxa zero: antes lançava `Overflow` no preço marginal descartado; agora retorna `0`. O caminho removido calculava esse preço em [curve.py:334](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/curve.py:334).

Essas entradas estão fora do domínio econômico do H-030; **não as usaria para bloquear sua otimização nem introduziria novas recusas no protocolo**. Registraria explicitamente o limite da equivalência.

**2. Cache global versus memo por fita**

Manteria o LRU por enquanto. Ele muda estado interno de desempenho, mas não o resultado econômico: chave de dois inteiros, valor imutável e conversão sob contexto fixo. Não introduz look-ahead. [pricing.py:84](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:84)

Em threads, chamadas concorrentes podem repetir um cálculo antes de ele entrar no cache; isso não muda seu valor. Em processos, cada worker mantém seu próprio cache. Portanto, os **8,1 MB medidos não são um orçamento compartilhado** nem substituem RSS total.

Memo por fita oferece descarte previsível, mas pode crescer com o maior mint. Eu só trocaria após medir misses, evicções e RSS por worker. Para o passo 3, cada processo deve possuir sua fita; o índice lazy publica `_by_wallet` antes de terminar sua construção, portanto compartilhar a mesma fita entre threads exigiria revisão própria. [pricing.py:196](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/pricing.py:196)

**3. Referência congelada**

É independente o bastante para esta refatoração: confirmei os digests usando o código antigo. Isso fecha o risco de batch e stream mudarem juntos.

Ela não prova universalidade. As cópias cobrem **duas políticas, cada uma em duas formas de chamada**, não todas as políticas possíveis; a grade não cobre exceções extremas, e o retrato compara a projeção de `fingerprint`, não todo atributo de todo objeto. [wallets_golden.py:130](C:/dev/project-hunter/packages/indicators/tests/meme/wallets_golden.py:130), [leakage.py:42](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/leakage.py:42)

A função `_frozen_curve_sale` também usa o `curve_mod` corrente: é independente da alteração em `pricing`, mas deixaria de ser referência congelada completa se `curve.py` mudasse. [test_wallets_cpu.py:44](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_cpu.py:44)

**4. Testes de contagem**

**Têm dentes**, confirmado pelas sete falhas contra o baseline. Os limites de leituras/conversões verificam a remoção do trabalho pretendido sem depender de tempo de máquina.

Há acoplamento deliberado em monkeypatches de `quote_sell` e `localcontext`; aceitável para este passo, mas esses testes precisam acompanhar uma futura arquitetura diferente. Melhoraria o teste do cache: limpar o LRU e exigir exatamente uma conversão, pois `<=1` também aceita zero por cache previamente aquecido. [test_wallets_cpu.py:88](C:/dev/project-hunter/packages/indicators/tests/meme/test_wallets_cpu.py:88)

**O QUE EU FARIA DIFERENTE**

**5. Medição: manteria o método, corrigindo estes limites.**

- **Tempo sem cProfile ainda é instrumentado.** Há wrappers e chamadas a dois relógios por cópia. Acrescentaria uma execução totalmente sem wrappers para confirmar o ganho total, especialmente após as otimizações. [profile.py:135](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-profile.py:135), [profile.py:236](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-profile.py:236)
- **Declararia cache frio/aquecido.** As noites anteriores aquecem o LRU; o cProfile roda depois do timing e pode observar outro estado de cache. Isso é válido como cenário, mas precisa ser controlado igualmente entre estágios. [profile.py:225](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-profile.py:225)
- **Intercalar ajuda, mas não elimina ruído.** Usaria repetições pareadas, ordem alternada e dispersão; ganhos próximos dos 20% de ruído ficam inconclusivos.
- **A matriz não isola perfeitamente cada variável.** `wallet_scale` compartilha RNG com outras escolhas. Nos artefatos, base tem 18.852 fills, enquanto `entities_x0.5` tem 14.116: não é apenas “menos entidades com fills fixos”. Separaria RNGs ou reutilizaria uma fita-base. [gen.py:68](C:/dev/project-hunter/infra/scripts/research/2026-10-06-wallets-engine-gen.py:68), [before.txt:221](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/profile-2026-10-06-step1-before.txt:221)
- **Resolveria a proveniência do rerun.** O original teve `wall=28255.582s`; o substituto registra `pricing.py` dirty e outro hash. Isso não prova mudança semântica, mas impede assumir baseline idêntico sem conferir. [before.txt:178](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/profile-2026-10-06-step1-before.txt:178), [rerun.txt:2](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/profile-2026-10-06-step1-before-fills16k-rerun.txt:2)

Os percentuais também variam mais que a faixa citada: `history_5d` mostra **28,9% copies e 48,0% window_books**. Não escolheria o próximo algoritmo usando apenas 57–88%/7–30%. [before.txt:570](C:/dev/project-hunter/.claude/state/carteiras-lucro/bench/profile-2026-10-06-step1-before.txt:570)

**6. Próximos passos**

**Passo 3:** medir novamente o perfil após A–G; implementar primeiro a fusão exata dos acumuladores. Somar inteiros/vetores, unir conjuntos, preservar holds para mediana exata e máximo com ausência. Manter entidades, teto diário e sementes de taxas globais antes de distribuir mints inteiros. Comparar um/dois workers e ordens diferentes de conclusão, incluindo carry. [stream_metrics.py:50](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream_metrics.py:50), [stream.py:280](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/stream.py:280)

Dois workers não resolvem um único mint dominante. Mediria fila limitada, serialização, redução e RSS agregado; o coordenador também entra no orçamento de dois núcleos.

**Passo 4:** escolher kernels pelo novo perfil. Há trabalho sequencial restante em ordenação/varredura do líder e stops por cópia; no carry grande, `atoms()` soma os lotes novamente nas avaliações de fronteira. Antes de vetorizar, mediria se manter esse total incrementalmente já remove custo relevante. [policy.py:110](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/policy.py:110), [episodes.py:122](C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/wallets/episodes.py:122)

Não substituiria Decimal por aritmética inteira apenas por equivalência algébrica: é necessário preservar também o arredondamento intermediário existente. Inteiros de largura fixa exigem prova de ausência de overflow.

**CONCORDO COM**

A sequência acordada está correta: perfil, remoções individuais, referência congelada, fusão exata e só então paralelismo/vetorização. Os testes atuais sustentam as remoções; não demonstram ainda o aceite operacional de duas horas. Essa distinção está explícita na [decisão conjunta, item 6](C:/dev/project-hunter/.claude/state/dialogue-wallets-cpu.md:98).

**OBSIDIAN**

- **CPU do motor de carteiras: medir antes de reescrever — wallets-cpu:** incorporar a decisão conjunta já existente no bruto e esta revisão; a síntese ainda diz que a rodada 2 está pendente.
- **Revisão da Astra: motor de carteiras em memória limitada — wallets-1c-bis:** registrar os 215 testes, a reprodução dos digests antigos e os limites da equivalência.
- **KB-0183 — O que custa coletar o programa inteiro:** registrar RSS inválido, controles pendentes do benchmark e ausência de capacidade operacional demonstrada.
- **EXP-M15 — carteiras vencedoras:** acrescentar somente o avanço de infraestrutura do H-030, sem resultado de estratégia.