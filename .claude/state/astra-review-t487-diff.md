**RESUMO**

**BLOCKED para DONE.** Os 83 testes passam, mas reproduzi vereditos conclusivos indevidos. Parecer como `quant-engineer`, em modo OPINIÃO.

Walk-forward com várias dobras e baseline “sempre dentro” **podem ficar para depois**, desde que o escopo seja explicitamente limitado. Não são os bloqueios principais abaixo; tampouco permitem apresentar esta versão como reprodução integral do R68 ([RESEARCH.md:105](C:/dev/project-hunter/docs/RESEARCH.md:105)).

**ARQUIVOS**

Nenhum criado ou modificado. Revisei os arquivos indicados e confrontei os resultados com R65/R67, o pré-registro do R68 e a KB-0149.

**TESTES**

Executei `uv run pytest infra/research/tests -q`, com bytecode e cache do pytest desabilitados e sem sincronizar dependências:

```text
83 passed in 8.23s
```

Executei também sondas sintéticas em memória com `uv run python -`. Os resultados relevantes aparecem abaixo. Não executei lint nem typecheck global.

**MUST-FIX**

1. **Split declarado pode desaparecer; linhas purgadas continuam sustentando o veredito.**

   O contraste principal é calculado antes da divisão. Teste vazio vira `None`, e `decide` só exige repetição quando recebe um contraste OOS ([protocol.py:204](C:/dev/project-hunter/infra/research/protocol.py:204), [protocol.py:233](C:/dev/project-hunter/infra/research/protocol.py:233), [verdict.py:67](C:/dev/project-hunter/infra/research/verdict.py:67)).

   Reproduzi:

   ```text
   SPLIT_EMPTY CONFIRMA oos=None
   TINY_OOS CONFIRMA oos n=1/1 D=0.001 groups=2
   PURGED_MAIN CONFIRMA purged=200 main_n=202 oos_d=0.001
   ```

   No último caso, as 200 linhas que sustentavam o efeito estavam na purga; sobravam duas no teste. Exigir elegibilidade do teste quando há split e definir qual população sustenta a conclusão. Purga não pode valer apenas para a tabela auxiliar.

   A comparação textual também falha: `2026-09-01 23:00:00+00:00` entrou no treino com fronteira `2026-09-01T12:00:00Z`. Ambas representam UTC, mas a ordenação textual diverge. Normalizar timestamps; purga por valores distintos só representa duração quando a cadência é garantida ([protocol.py:176](C:/dev/project-hunter/infra/research/protocol.py:176)). Com eventos por segundo, `purge=60` não garante 60 minutos.

2. **A guarda ainda aceita antecipação por caminhos concretos.**

   `_opt` transforma qualquer valor que não seja `datetime` em `None`, desativando a checagem da fita mesmo quando a coluna foi declarada ([protocol.py:110](C:/dev/project-hunter/infra/research/protocol.py:110)). Reproduzi timestamp da fita **um dia no futuro**, em string ISO:

   ```text
   FUTURE_TAPE_STRING CONFIRMA refused=0
   ```

   Também reproduzi `CONFIRMA` com feature futura e `lag=-2 segundos`: subtrair atraso negativo adianta o corte ([guards.py:100](C:/dev/project-hunter/infra/research/guards.py:100)). Recusar tipos inválidos e atraso negativo.

   Vincular a decisão à coluna melhorou o protocolo, mas **não fechou `GuardedSeries`**: `values` continua público e `take` recebe `decision_idx` do chamador ([guards.py:62](C:/dev/project-hunter/infra/research/guards.py:62), [guards.py:72](C:/dev/project-hunter/infra/research/guards.py:72)). Ler `values[i+1]` ou fornecer também uma decisão futura contorna a promessa de “único acesso pela guarda”.

3. **NaN pode produzir REFUTA; p ausente pode sobreviver ao BH.**

   `_num(float("nan"))` devolve NaN, que passa pela seleção `is not None`. Depois, o bootstrap elimina réplicas não finitas, condicionando o IC às amostras que evitaram a linha problemática ([protocol.py:63](C:/dev/project-hunter/infra/research/protocol.py:63), [protocol.py:198](C:/dev/project-hunter/infra/research/protocol.py:198), [resampling.py:70](C:/dev/project-hunter/infra/research/resampling.py:70)).

   Sonda com um desfecho NaN:

   ```text
   NAN_OUTCOME REFUTA D=nan censored=0
   ```

   Separadamente, `adjust_family([NaN, 0.001])` devolveu `bh_adjusted=(0.001, 0.001)` e **dois sobreviventes** ([stats.py:134](C:/dev/project-hunter/infra/research/stats.py:134)).

   Validar finitude na entrada, definir tratamento de ausentes na família e impedir conclusão com estimativa ou limites inválidos. Hoje a guarda inferencial verifica apenas `ci.lo` ([verdict.py:41](C:/dev/project-hunter/infra/research/verdict.py:41)).

4. **O mínimo de clusters total não protege um braço sustentado por um único episódio.**

   Reproduzi oito clusters, 25 linhas por cluster, apenas um cluster selecionado:

   ```text
   ONE_SELECTED_CLUSTER CONFIRMA
   IC=[1.0, 1.0]; réplicas inválidas=689/2000
   ```

   O portão aceita oito clusters totais, enquanto a reamostragem descarta todas as réplicas sem aquele único cluster selecionado ([verdict.py:41](C:/dev/project-hunter/infra/research/verdict.py:41), [resampling.py:62](C:/dev/project-hunter/infra/research/resampling.py:62)).

   Portanto, **sim: descartar réplicas inválidas pode mudar materialmente a distribuição inferencial**. Não implica viés sempre para o mesmo lado, mas neste cenário produz certeza artificial. Exigir suporte independente por braço, registrar réplicas válidas/descartadas e bloquear inferência quando esse suporte não existe.

5. **O método inferencial primário continua universal, apesar de haver dependência temporal declarada.**

   `ci_block` é calculado, mas `decide` usa exclusivamente o IC por cluster e a permutação de linhas ([protocol.py:148](C:/dev/project-hunter/infra/research/protocol.py:148), [verdict.py:46](C:/dev/project-hunter/infra/research/verdict.py:46)).

   Sonda com dez blocos, efeito positivo concentrado em apenas um:

   ```text
   CONFIRMA
   IC por cluster=[0.72665, 1.10569]
   IC por bloco=[-0.10, 2.93]
   ```

   A permutação preserva estratos, mas quebra a dependência entre linhas dentro deles ([resampling.py:144](C:/dev/project-hunter/infra/research/resampling.py:144)). Duplicar cada observação 25 vezes, sem acrescentar informação independente, mudou o p de **0,4745 para 0,0002** na sonda.

   O próprio R68 já resolveu isso: blocos temporais primários e bootstrap centrado substituindo permutação ([preregistro.md:140](C:/dev/project-hunter/.claude/state/r68/preregistro.md:140)). Tornar método primário parte do plano ou recusar esses estudos nesta versão. A distinção entre permutações depende da estrutura amostral, como documenta o [SciPy](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html).

6. **O fingerprint não congela escolhas que mudam a conclusão.**

   Não inclui split, cluster, estrato, bloco, observabilidade nem suposições ([spec.py:183](C:/dev/project-hunter/infra/research/spec.py:183)).

   Reproduzi fingerprint idêntico ao acrescentar split e ao trocar cluster de mint para dia e remover estratificação. Cenário: o operador muda a inferência depois de ver resultados, mantendo a mesma identidade publicada. Incluir serialização canônica dos campos relevantes do protocolo; proveniência dos dados pode ser um hash separado.

7. **Quatro repetições do mesmo limiar passam por planalto.**

   `plateau_or_spike` conta posições na sequência, sem exigir limiares distintos ([stats.py:218](C:/dev/project-hunter/infra/research/stats.py:218)). Sonda:

   ```text
   thresholds=(50,50,50,50)
   CONFIRMA; planalto; longest_run=4; ci_clear=4
   ```

   Isso satisfaz o portão sem testar nenhum vizinho. Validar grelha estritamente crescente e distinta antes da análise.

8. **Documentação e fila voltam a confundir ausência de confirmação com refutação.**

   “13 variáveis já refutadas” aparece em [RESEARCH.md:82](C:/dev/project-hunter/docs/RESEARCH.md:82) e na [Fila:16](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:16>). A KB diz “nenhuma sobrevive” e explicita **não confirmado ≠ refutado** ([KB-0149:43](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md:43)).

   O exemplo também chama “IC cobrindo zero” de refutação ([RESEARCH.md:41](C:/dev/project-hunter/docs/RESEARCH.md:41)); várias hipóteses repetem isso, como [H-002:46](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:46>).

   Cenário: IC largo contendo zero **e o efeito previsto** leva ao abandono como hipótese refutada. Separar critérios de **não confirmação**, **refutação do tamanho previsto** e **abandono operacional**.

**NICE-TO-HAVE**

- **Censura da variável:** sim, remover ausentes muda o estimando para a população com variável observada ([protocol.py:199](C:/dev/project-hunter/infra/research/protocol.py:199)). Isso pode ser válido se pré-registrado. Porém, a premissa sobre o R67 precisa de correção: embora `lo()` ponha `None` no resto, o carregador já excluía `buys_1m` vazio ([load67.py:53](C:/dev/project-hunter/.claude/state/r67/load67.py:53)). **Não identifiquei mudança da população principal publicada do R67 por esse motivo.** Acrescentaria política explícita de ausência, cobertura por braço e sensibilidades.
- A regressão R67 ainda usa os portões adicionais padrão, apesar de o texto congelado listar outra regra ([test_reproduz_r65_r67.py:198](C:/dev/project-hunter/infra/research/tests/test_reproduz_r65_r67.py:198)). O resultado atual coincide; separaria “reproduz R67” de “aplica política nova aos dados R67”.
- As tolerâncias atuais servem como regressão desses resultados distantes da fronteira decisória; não demonstram equivalência geral entre protocolos.

**O QUE EU FARIA DIFERENTE**

Fecharia primeiro validade numérica, observabilidade, população inferencial e método primário. Depois ampliaria para múltiplas dobras e baseline. É aceitável entregar um moinho menor, com hipóteses suportadas explicitamente delimitadas.

**CONCORDO COM**

- **BH e Holm estão corretos para p finitos válidos**, incluindo mínimos/máximos acumulados ([stats.py:139](C:/dev/project-hunter/infra/research/stats.py:139)); a distinção FDR versus erro familiar está de acordo com a [documentação do R](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html).
- Conferi diretamente os 13 p publicados em [stats.txt:144](C:/dev/project-hunter/.claude/state/r65/stats.txt:144): primeiro limiar **0,0076923**, menor p ajustado **0,6019** em ambos, **zero sobreviventes**.
- Planalto configurável, exigência de nível positivo e texto “vantagem desse tamanho” são melhorias pertinentes ([spec.py:108](C:/dev/project-hunter/infra/research/spec.py:108), [verdict.py:81](C:/dev/project-hunter/infra/research/verdict.py:81)).

**OBSIDIAN**

- **Fila de Hipóteses:** corrigir “refutadas” e separar não confirmação, refutação e abandono operacional.
- **KB-0149 — O que a mesa real ensinou:** preservar a distinção estatística e registrar os limites de aplicação do moinho.
- **Revisões Astra — T4.87 (nova):** registrar os contraexemplos reproduzidos, os 83 testes aprovados e os bloqueios de DONE.