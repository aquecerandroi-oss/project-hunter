**RESUMO**

**Ainda não reportaria DONE: encontrei um must-fix reproduzido**, na formatação Decimal das duas estratégias. A lógica principal está coerente; as ressalvas restantes são sobre o alcance dos testes e as garantias que a S2 ainda precisa entregar.

Revisão como `quant-engineer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado por mim. Revisei os arquivos de produção e testes indicados, o contrato do Shadow Lab e a revisão anterior.

**TESTES**

Executei com sincronização do ambiente, bytecode e cache do pytest desabilitados:

```text
uv run pytest packages/core/tests/unit/strategies -q
126 passed in 7.89s

uv run pytest packages/core/tests/unit/test_strategies_canonical.py -q
21 passed in 0.97s
```

Também executei uma reprodução em memória com `uv run python -B -`. Não reexecutei a suíte inteira, Ruff, Pyright ou o gate de tamanho; os resultados informados desses comandos continuam sendo os seus.

**MUST-FIX**

**1. `_ratio()` depende do contexto Decimal ambiente e pode abortar uma avaliação válida.**

O `quantize()` está fora de `localcontext(CONTEXT)` em [momentum_v1.py:64](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:64) e [volume_anomaly_v1.py:56](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:56).

**Cenário reproduzido:** mesmo contexto momentum, parâmetros padrão, volume relativo `2.005`. Alterando somente o arredondamento ambiente:

```text
ROUND_DOWN → volume relativo 2.00x
ROUND_UP   → volume relativo 2.01x
```

Com precisão ambiente `2`, ambas as estratégias lançaram:

```text
InvalidOperation
```

Portanto, não é apenas uma diferença cosmética: a construção de `Decision` pode falhar depois de todas as condições terem passado.

**Correção:** controlar também o contexto da formatação e acrescentar regressão nas duas estratégias, construindo o contexto de entrada antes de alterar precisão/arredondamento. O teste atual usa precisão `6` e razão exatamente `2`, que não expõem esse defeito ([test_no_lookahead.py:198](C:/dev/project-hunter/packages/core/tests/unit/strategies/test_no_lookahead.py:198)).

**NICE-TO-HAVE**

- Distinguir ausência inicial de histórico de um buraco exatamente em `window_start`. Hoje ambos recebem `warmup`, mesmo havendo velas anteriores à janela. Continua indisponível, portanto não contamina decisões ([aggregate.py:108](C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:108)).
- Acrescentar testes do retorno do volume exatamente em `0` e em `2 × ATR%`; os operadores implementados são inclusivos, mas os testes atuais cobrem sobretudo valores fora desses limites ([volume_anomaly_v1.py:171](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:171), [test_volume_anomaly_v1.py:162](C:/dev/project-hunter/packages/core/tests/unit/strategies/test_volume_anomaly_v1.py:162)).
- Corrigir a expressão “`NOT_TRIGGERED` desarma”: ela comprova condição falsa; o contrato prevê **rearme após o término**. Deixar essa transição inequívoca para quem implementar `armed` na S2 ([base.py:74](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:74), [SHADOW-LAB.md:14](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:14)).

**O QUE EU FARIA DIFERENTE**

Antes de congelar a v1, fortaleceria a prova com histórico variável, comparando cada fechamento nas duas estratégias. Retiraria também a afirmação de que o efeito da seed é “numericamente desprezível”: o peso residual pequeno não limita o erro relativo do ATR nem impede mudança de decisão perto de um limiar ([notes-S1.md:32](C:/dev/project-hunter/.claude/state/notes-S1.md:32)).

Não trocaria silenciosamente a política escolhida por Wilder contínuo.

**CONCORDO COM**

Respostas ponto a ponto:

**1. Corte, finalização, mercado e lacunas**

No caminho normal `build_context → StrategyContext → evaluate`, não encontrei vela com fechamento posterior ao corte, não-final ou de outro mercado influenciando os números: o filtro elimina futuras/não-finais; o construtor rejeita mercado errado, duração incorreta, duplicatas e desordem ([base.py:133](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:133), [base.py:186](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:186)).

Também não encontrei janela reduzida: qualquer minuto necessário ausente devolve janela vazia com motivo ([aggregate.py:126](C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:126)).

**Limite da garantia:** isso controla tempo de mercado, não disponibilidade histórica. Uma vela antiga recebida por backfill depois da decisão passa pelo filtro, que não verifica `received_at`. Reproduzir fielmente uma decisão passada exige que a S2 preserve quais dados estavam disponíveis em `decision_at`; não basta reconstruir pelo fechamento ([base.py:188](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:188), [market.py:125](C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:125)). Essa responsabilidade já estava atribuída ao worker na revisão anterior.

**2. Último minuto ausente: concordo com `gap`**

Se o início exigido está presente e falta o último minuto, é incompletude da janela exigida, não falta de prefixo para aquecimento. A implementação e o teste específico estão corretos ([aggregate.py:132](C:/dev/project-hunter/packages/core/hunter_core/strategies/aggregate.py:132), [test_aggregate.py:83](C:/dev/project-hunter/packages/core/tests/unit/strategies/test_aggregate.py:83)).

**3. ATR: fórmula correta; política diferente do M2**

A indexação confere:

- `bars[0]` fornece o fechamento anterior;
- TRs de `bars[1]` até `bars[14]` formam a seed;
- âncora em `bars[14].open_time`;
- `bars[15]` fornece a primeira suavização;
- liberação com `period + 2` barras.

Não encontrei erro nessa implementação ([indicators.py:83](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:83)).

Há compatibilidade da **fórmula e do gate**, não identidade com a origem contínua do M2. O reseed está explicitamente declarado, como admitido na revisão anterior; mantenha essa distinção no protocolo publicado ([indicators.py:28](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:28), [diálogo M2:196](C:/dev/project-hunter/obsidian/06-DECISIONS/Dialogos/M2.md:196)).

**4. Precedência, comparações, níveis e constantes**

Concordo com disponibilidade precedendo condições: falta de entrada necessária não vira condição falsa.

Momentum: rompimento e retorno estritos; volume mínimo e faixa de ATR inclusivos; depois geometria. Stop/alvo simétricos e alvos informativos conferem ([momentum_v1.py:176](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:176), [momentum_v1.py:212](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:212)).

Volume: múltiplo inclusivo, fechamento estritamente acima do meio, retorno inclusivo nas duas pontas, stop na mínima e alvo em ATR ([volume_anomaly_v1.py:149](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:149)).

As invalidações preservam os níveis do setup ([momentum_v1.py:271](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:271), [volume_anomaly_v1.py:234](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:234)).

`_DISPLAY`, `_PERCENT` e `_TWO` **não são parâmetros experimentais escondidos**: representam apresentação, conversão de unidade e definição matemática de ponto médio. O defeito é o contexto usado na apresentação.

**5. Envelope: explica a decisão, mas não basta para recomputar tudo meses depois**

Os valores calculados permitem conferir condições e níveis junto dos parâmetros congelados. Entretanto, seed, âncora e limites temporais não permitem recalcular os TRs subsequentes sem as barras. A afirmação “reproducible from these fields alone” é excessiva ([envelope.py:76](C:/dev/project-hunter/packages/core/hunter_core/strategies/envelope.py:76)).

Faltam fontes duráveis/revisões das entradas, qualidade/disponibilidade e referência à composição histórica do universo. Também explicitaria a janela do sinal e sua barra OHLCV, especialmente no volume, cujo sinal pode terminar depois da janela do ATR ([envelope.py:60](C:/dev/project-hunter/packages/core/hunter_core/strategies/envelope.py:60), [volume_anomaly_v1.py:197](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:197)).

**Cenário:** após expirar a retenção de candles 1m, restam mediana, razão e ATR, mas não as entradas para verificar esses cálculos. Isso é uma obrigação de integração/persistência da **S2 antes da ativação**, não motivo para exigir armazenamento dentro da função pura ([DATABASE.md:46](C:/dev/project-hunter/docs/DATABASE.md:46), [SHADOW-LAB.md:18](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:18)).

**6. Bootstrap e invariância: prova parcial, corretamente útil para S1**

Reconstruir o contexto é legítimo para testar uma função sem estado. Porém, o teste compara bootstrap apenas com a última avaliação; as anteriores são verificadas como ausência de sinal. Não prova checkpoint, restart, episódios ou rearme ([test_no_lookahead.py:120](C:/dev/project-hunter/packages/core/tests/unit/strategies/test_no_lookahead.py:120)).

O teste de extensão do histórico usa um prefixo constante igual ao restante: uma regressão que usasse história demais no ATR poderia continuar passando. Usaria o mesmo corte, a mesma cauda e um prefixo antigo com volatilidade muito diferente ([test_no_lookahead.py:145](C:/dev/project-hunter/packages/core/tests/unit/strategies/test_no_lookahead.py:145)). Acrescentaria o equivalente de bootstrap para volume.

**7. Decimal, UTC, pureza e dados fictícios**

Além do must-fix da formatação, não identifiquei outro bloqueio nesses pontos nos caminhos padrão revisados. UTC é normalizado e timestamps ingênuos são rejeitados; parâmetros decimais recusam float; as séries sintéticas estão explicitamente identificadas nos testes ([types.py:47](C:/dev/project-hunter/packages/core/hunter_core/domain/types.py:47), [base.py:295](C:/dev/project-hunter/packages/core/hunter_core/strategies/base.py:295), [conftest.py:1](C:/dev/project-hunter/packages/core/tests/unit/strategies/conftest.py:1)).

Para S2, exigir round-trip real dos níveis: precisão Decimal de 28 dígitos não equivale a escala de dez casas do banco. O `stop` persistido precisa ser coerente com o nível usado após restart ([db/base.py:36](C:/dev/project-hunter/packages/core/hunter_core/db/base.py:36), [agents.py:116](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents.py:116)).

**OBSIDIAN**

- **Revisões Astra — S1: revisão do diff** — registrar o defeito reproduzido, correção e resultados desta revisão.
- **Features (Feature Engine)** — distinguir Wilder contínuo de `rolling_window_v1`, sem alegar erro desprezível.
- **Strategies** — documentar os estados de avaliação e separar determinismo da função de recuperação do worker.
- **Momentum Agent / Volume Agent** — registrar os contratos efetivamente entregues, mantendo ativação pendente da prova S2.
- **Diálogo SHADOW** — acrescentar as obrigações de proveniência, retenção das entradas e reprodução após persistência.