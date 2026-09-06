**RESUMO**

**DONE_WITH_CONCERNS.** Concordo com o tratamento de `B=1`, mas ainda não aprovaria a prova do R1: há vazamento além de `as_of`, reprodução circular de recusas por geometria e uma atribuição ao funding que os artefatos não demonstram integralmente.

**ARQUIVOS**

Revisei os arquivos listados e as dependências relevantes. Nenhum arquivo foi alterado; nenhum commit foi feito. O workspace contém outras alterações, que não atribuí ao R1.

**TESTES**

Executei, com sincronização do uv, bytecode e cache do pytest desativados:

```text
uv run pytest packages/indicators/tests/unit/test_replay_policies.py packages/indicators/tests/unit/test_replay_stats.py services/strategy-worker/tests/test_replay_arms.py -q
44 passed in 1.90s
```

Não executei integração, que cria/altera dados, nem refiz a consulta ao banco. A conferência do JSON existente retornou:

```text
total                  : 352
comparable             : 327
reproduced             : 314
diverged               : 13
funding_missing_fields : 12
trajectory_fields      : 0
```

**MUST-FIX**

1. **`as_of` não corta as velas do replay.**

   `load_series` carrega até `horizon + MINUTE` e constrói o prefixo até o horizonte. Usa `as_of` apenas para nomear uma truncagem quando faltam barras; não impede consumir barras posteriores ao corte. [engine.py:90](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/engine.py:90)

   **Cenário:** entrada às 16h, horizonte às 20h, execução hoje com `as_of=17h`. Se o banco já contém uma barra das 18h que toca o alvo, o replay resolve usando esse futuro. Portanto, **o corte das 17h não demonstra maturidade nem ausência de look-ahead**.

   Limitar as barras ao último minuto fechado no corte, preservando a barra de expiração quando elegível. Teste decisivo: acrescentar/modificar velas posteriores ao corte não pode alterar resultado ou cobertura daquela execução.

2. **Parte da “reprodução” compara o registro com uma cópia dele.**

   Todo `NO_ENTRY`, inclusive `geometry`, retorna diretamente como herdado, com zero barras reexecutadas. A auditoria exclui apenas `late`; para geometria, compara estado e motivo copiados e declara reprodução. [engine.py:312](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/engine.py:312), [reproduce.py:95](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/reproduce.py:95)

   **Cenário:** um bug original recusou uma entrada cuja geometria era válida. A auditoria atual confirma essa recusa sem verificá-la. No artefato, **nove recusas entram assim nos comparáveis**: 327 comparáveis contra 318 terminais. [r1-proof.md:20](C:/dev/project-hunter/.claude/state/r1-proof.md:20), [r1-proof.md:29](C:/dev/project-hunter/.claude/state/r1-proof.md:29)

   Reexecutar geometria separadamente para auditoria ou classificá-la como herdada/não verificada. A admissão dos braços pode continuar congelada.

   Além disso, falta comparar **`exit_at_open` e `exit_bar_open`**: os checks não os incluem. Uma diferença abertura/intrabar pode alterar a incidência de funding e aparecer indevidamente como “só liquidação”. [reproduce.py:117](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/reproduce.py:117)

3. **A causa das 13 divergências não está demonstrada; o gate também não é aplicado.**

   **Resposta a (a): falta evidência decisiva.** O artefato mostra **12**, não 13, razões `funding_missing`. O caso `5b027f70…` já tinha `R_net=-0.8112908472` e passou a `-0.8263601960`, sem divergência de motivo. [r1-proof.md:50](C:/dev/project-hunter/.claude/state/r1-proof.md:50)

   **Cenário:** esse caso decorre de mudança no resolvedor, na cadência inferida ou nos dados, enquanto os outros decorrem de ingestão tardia. Atribuir todos à mesma causa esconderia a exceção.

   Para decidir:
   
   - Reconciliar cada linha: trajetória completa, funding persistido, eventos cobrados agora e diferença exata em R.
   - Cruzar o instante de ingestão disponível em evidência histórica com o instante de processamento da liquidação — **`exit_ts` não prova quando o worker liquidou**.
   - Manter dados fixos ao comparar resolvedores; manter código fixo ao comparar históricos.

   Retirar o settlement atual e reproduzir o valor antigo demonstra que sua ausência **explica aritmeticamente** a diferença; não prova que ele estava ausente naquele momento. Sem histórico/log suficiente, escrever **“compatível com ingestão tardia; causa histórica não comprovada”**.

   O CLI calcula todos os braços antes da auditoria e publica contrastes independentemente dela. **Cenário:** reprodução de 80% por bug ainda gera relatório completo. Aplicar o gate antes dos contrastes. [replay_exits.py:118](C:/dev/project-hunter/infra/scripts/replay_exits.py:118), [replay_exits.py:129](C:/dev/project-hunter/infra/scripts/replay_exits.py:129)

4. **`READ ONLY` não garante snapshot consistente entre braços.**

   A sessão pede somente `READ ONLY`, sem garantir `REPEATABLE READ`. [load.py:53](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/load.py:53)

   **Cenário:** sob `READ COMMITTED`, a base é liquidada antes da chegada de funding e outro braço depois. Mesmo com trajetória idêntica, cobertura ou diferença muda por ordem de execução.

   Garantir snapshot único e registrar `read_at`, identidade do código e identificação dos insumos. Isso também separa o corte econômico da disponibilidade dos dados na leitura.

5. **O relatório oculta denominadores e pode chamar deterioração de efeito relevante.**

   O Markdown mostra resolvidos, mas omite os avaliáveis líquidos e os indisponíveis por funding. Por exemplo, `TGT-3` tem 125 resolvidos, mas sua expectancy usa 123; a diferença só fica recuperável no JSON. [render.py:95](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/render.py:95), [r1-proof.json:1](C:/dev/project-hunter/.claude/state/r1-proof.json:1)

   Também calcula `above_min_effect` com `abs(estimate)`: **Δ = −0,10 R recebe “sim” em “≥ efeito mín.”**. [contrast.py:182](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/contrast.py:182)

   **Cenário:** um leitor interpreta cobertura parcial como total ou deterioração relevante como melhoria. Publicar os denominadores, exclusões e direção; rotular explicitamente “magnitude absoluta” caso essa seja a intenção.

**NICE-TO-HAVE**

- Rejeitar `--as-of` sem timezone: atualmente `astimezone(UTC)` interpreta datetime ingênuo no fuso da máquina. O mesmo argumento pode selecionar cortes diferentes. [replay_exits.py:57](C:/dev/project-hunter/infra/scripts/replay_exits.py:57)
- No ramo amostrado de inversão de sinais, usar correção Monte Carlo que evite `p=0` quando nenhum sorteio excede o observado. Hoje retorna diretamente `hits/draws`. [stats.py:102](C:/dev/project-hunter/packages/indicators/hunter_indicators/replay/stats.py:102)
- Completar o motivo do PF nulo quando não há avaliáveis: atualmente também fica nulo. [metrics.py:78](C:/dev/project-hunter/packages/indicators/hunter_indicators/replay/metrics.py:78)

**O QUE EU FARIA DIFERENTE**

Separaria explicitamente **auditoria histórica**, **replay com dados reconstruídos** e **contrastes condicionados à cobertura**.

Congelaria uma execução identificada, com corte, snapshot, versões e código. A prova atual contém **318 entradas**, gatilho nativo da base **113**, e EXIT-CHAN **17/133**, diferentes dos números da pergunta. Isso não demonstra fabricação; exige identificar qual execução sustenta cada afirmação. [r1-proof.md:68](C:/dev/project-hunter/.claude/state/r1-proof.md:68)

**CONCORDO COM**

- **(b)** Não encontrei preço, custo ou PnL calculado em `float` nos módulos novos. A conversão para NumPy ocorre na inferência sobre diferenças em R. Há, porém, o look-ahead do corte descrito acima. [stats.py:79](C:/dev/project-hunter/packages/indicators/hunter_indicators/replay/stats.py:79)
- O fold começa em `Progress.start()`; o observador roda depois do walker, somente ativo e sem sobrescrever invalidação pendente. [engine.py:168](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/engine.py:168)
- **(c)** Sim: média por entrada, bootstrap de blocos e **IC indisponível com `single_block`** são coerentes. No teste **bilateral contra zero** implementado, `B=1` produz `p=1` por construção; isso não demonstra equivalência. Tampouco testa melhoria superior a `0,05 R`. [stats.py:102](C:/dev/project-hunter/packages/indicators/hunter_indicators/replay/stats.py:102), [stats.py:157](C:/dev/project-hunter/packages/indicators/hunter_indicators/replay/stats.py:157)
- **(d)** “Não confirmação” está corretamente escrito. Mas “o replay reproduz o acompanhamento real” é afirmação incondicional demais enquanto o gate e a auditoria acima estiverem incompletos. [render.py:239](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/render.py:239)

**OBSIDIAN**

- **EXP-0004 — Políticas de saída:** registrar execução identificada, cobertura e atribuições comprovadas versus pendentes.
- **Revisão Astra — R1:** registrar os bloqueios, cenários de falha e os 44 testes unitários aprovados.
- **Strategy Performance:** distinguir reprodução verificada, herança de estado e reconstrução com dados posteriores.
- **KB-0006 — Valor incremental da invalidação:** ligar o piloto à revisão, mantendo resultado exploratório e condicionado à cobertura.