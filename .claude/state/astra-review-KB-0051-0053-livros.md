**RESUMO**

**As três notas são úteis, mas precisam de correções antes de tratá-las como protocolo.** D-CONC é calculável com o schema atual, porém não estima tamanho efetivo da amostra. C-META tem uma fórmula válida sob pareamento estrito, mas mistura estratégias. O `rvol` é uma analogia de confirmação por volume, não implementação de CANSLIM. Contração, ATR% e ER medem propriedades diferentes.

Atuei como `quant-engineer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit.

**TESTES**

Revisão estática com `Get-Content` e `rg`, mais consulta a fontes abertas. Não executei testes, SQL ou replay: confirmei contratos e caminhos de persistência, **não a cobertura nem os números atuais do banco**.

**MUST-FIX**

1. **KB-0051: retirar a interpretação de outcomes/blocos como observações independentes.**

   Em [KB-0051:68](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente.md:68), `N_outcomes/N_blocos` mede **outcomes por bloco**, não tamanho efetivo. A expressão “limite superior grosseiro da informação”, na linha 86, também não tem sustentação sem hipóteses adicionais.

   **Falha concreta:** aumentar a concentração de 100 outcomes em 100 blocos para 100 outcomes em 10 blocos faz a razão subir de 1 para 10. Interpretá-la como quantidade de observações independentes inverte o significado.

   Sua conclusão **“100 outcomes podem conter muito menos informação que 100 observações independentes” é fundamentada como possibilidade**, mas não como resultado já medido. D-CONC identifica concentração; não identifica correlação nem quantifica essa perda de informação.

   Há também um problema no exemplo de [KB-0051:73](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0051-tres-barreiras-mais-uma-e-a-amostra-que-nao-e-independente.md:73): 100 outcomes concentrados em apenas 12 blocos horários não satisfazem simultaneamente 30 dias distintos de observações. E o contrato já exige incerteza por blocos **depois** do limiar; ultrapassá-lo nunca significou independência. [SHADOW-LAB.md:19](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:19)

2. **KB-0052: separar filtro, meta-rótulo e estratégia-base.**

   As seis candidatas são filtros binários possíveis; **não são, por isso, meta-rótulos**. O meta-rótulo é o resultado usado como alvo do modelo secundário; o filtro produz uma decisão ou previsão. Essa distinção aparece na [documentação de implementação do mlfinlab](https://random-docs.readthedocs.io/en/latest/implementations/tb_meta_labeling.html). A ressalva da própria nota, na linha 100, não corrige a classificação categórica da tabela.

   Além disso, “todas sobre sinais da `momentum_v1`”, em [KB-0052:50](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0052-meta-rotulagem-o-formato-de-todo-filtro-que-propusemos.md:50), está errado:

   - **#6, #7, #8 e ER-A:** filtros propostos sobre momentum.
   - **#11:** explicitamente sobre `volume_anomaly` em [KB-0014:126](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0014-taker-buy-volume-o-que-temos-medido.md:126).
   - **#12:** teto além do piso 4, sobre `volume_ratio_5m`. [Strategy Backlog:58](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Strategy Backlog.md:58>) O padrão correspondente pertence à estratégia de 5 minutos. [volume_anomaly_v1.py:64](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:64)

   **Falha concreta:** avaliar #11/#12 contra momentum compara populações, cadências e gatilhos diferentes, atribuindo ao filtro uma diferença entre estratégias.

3. **C-META: a fórmula está correta, mas o contrato dos denominadores está incompleto.**

   As definições de [KB-0052:84](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0052-meta-rotulagem-o-formato-de-todo-filtro-que-propusemos.md:84) funcionam tomando uma base fixa `B` de entradas encerradas avaliáveis e um subconjunto aceito `A ⊆ B`, com os mesmos resultados hipotéticos:

   | Métrica | Definição |
   |---|---|
   | Retenção | `q = |A| / |B|` |
   | Delta por aceito | `μ_A − μ_B` |
   | Delta por oportunidade | `q·μ_A − μ_B = −Σ R_rejeitados / |B|` |
   | Precisão positiva | `nº(R>0 em A)/|A|`, acompanhada da taxa em `B` |

   Portanto, **não há erro algébrico em `delta_por_oportunidade`**: rejeitar equivale a contribuição zero, sem reinvestimento. No exemplo sintético da nota, resulta em `0,1×0,20−0,10 = −0,08 R` por oportunidade, apesar do ganho de `+0,10 R` por aceito.

   Falta exigir população maturada, cobertura das features, `R_net` conhecido, mesma coorte e tratamento de denominadores vazios. `r_multiple` pode ser nulo por funding indeterminado. [settle.py:5](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:5)

   **Falha concreta:** `SUM` ignora outcomes nulos enquanto o denominador conta todos os sinais, produzindo um delta aparentemente completo sobre resultados parcialmente desconhecidos.

   Para braços independentes, **declarar o despareamento não basta**: deixa de ser efeito de seleção sobre `B`. A ocupação e o rearme alteram oportunidades futuras. [episodes.py:57](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/episodes.py:57)

4. **KB-0052: retirar “as métricas certas […] não expectancy”.**

   Essa oposição, em [KB-0052:19](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0052-meta-rotulagem-o-formato-de-todo-filtro-que-propusemos.md:19), contradiz os próprios deltas financeiros propostos depois.

   **Falha concreta, sintética:** nove ganhos de `+0,1 R` e uma perda de `−2 R` dão 90% de precisão e expectativa de `−0,11 R`. Classificação e resultado financeiro precisam coexistir. Retenção também não é revocação: revocação mede a parcela dos positivos da base preservada.

5. **KB-0053: substituir “literalmente CANSLIM” por analogia limitada.**

   Os números locais estão corretos: `rvol_min=1,5`, janela 96 e barras de 15 minutos. [momentum_v1.py:74](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:74) A referência é a **mediana das 96 barras anteriores**, excluindo a atual. [indicators.py:124](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:124)

   O [material primário do IBD, página 6](https://shop.investors.com/images/promotional/flat-b-b_112408.pdf) descreve volume diário de rompimento 40–50% acima da média diária. Isso sustenta a analogia “rompimento confirmado por volume”, **não equivalência de estatística, janela ou mercado**.

   **Falha concreta:** numa distribuição assimétrica, volume 1,5× a mediana pode continuar abaixo da média. O filtro local aprovaria um sinal que não satisfaz nem a ideia literal de “acima da média”. A afirmação de [KB-0053:40](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel.md:40) transfere indevidamente a identidade do método.

6. **KB-0053: fechar o estimador e o corte temporal antes de executar D-CONTR.**

   [KB-0053:48](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel.md:48) não distingue período do ATR, quantidade de barras para inicialização e janelas sobrepostas versus consecutivas. O ATR existente usa Wilder, origem explícita e exige pelo menos `period+2` barras. [indicators.py:70](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:70)

   **Falha concreta:** passar exatamente 8 barras para ATR de período 8 retorna indisponível; usar uma média de oito TRs produz outro estimador.

   Também falta decidir se a barra do rompimento participa. Incluí-la é temporalmente permitido após seu fechamento, mas mede contração **incluindo o rompimento**. Um rompimento amplo pode apagar a contração anterior e inverter a seleção. Para a tese “contração antes do rompimento”, eu encerraria as duas medidas em `t−1`.

**NICE-TO-HAVE**

- **D-CONC é viável hoje no nível do schema**, com `entry_ts` e `exit_ts` persistidos. Mercados e versões vêm do join `signal_outcomes.signal_id = agent_signals.id`. [agents.py:108](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents.py:108), [agents.py:153](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents.py:153), [tracking_repo.py:213](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/tracking_repo.py:213). Especificaria intervalo `[entry_ts, exit_ts)`, minutos vazios incluídos ou excluídos e blocos atribuídos pela entrada. Saídas intrabar recebem `candle.close_time`: é ocupação convencional por barras, não cronologia exata de negócios. [walker.py:104](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:104)

- **Fontes e números:** `14.400 s`, `20`, `96`, `1,5` e `0,003` conferem com os parâmetros padrão, não necessariamente com versões ativadas no banco. [momentum_v1.py:76](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:76) `8/32`, blocos de `1/4 h` e `θ` são escolhas experimentais. Os `17%→63%` de [KB-0052:27](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0052-meta-rotulagem-o-formato-de-todo-filtro-que-propusemos.md:27) ficaram **não verificados** nesta revisão; removeria os números ou daria a fonte exata, mesmo usados como contraexemplo.

- Rebaixaria `evidencia: estudo revisado` da KB-0051 para descrição de método com fontes identificadas. Na KB-0053, substituiria “nenhum estudo”, “nada foi mostrado”, “metade” e “único pedaço formalizável” por afirmações delimitadas ao material consultado. [KB-0053:22](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel.md:22)

**O QUE EU FARIA DIFERENTE**

Chamaria D-CONC de **diagnóstico de concentração temporal**, mantendo qualquer estimativa de tamanho efetivo separada. Na C-META, publicaria explicitamente a estratégia-base, a população avaliável e a cobertura antes das quatro métricas.

Para D-CONTR, congelaria primeiro fórmula, inicialização, janelas e exclusão da barra do rompimento. Só depois examinaria associação e utilidade incremental.

**CONCORDO COM**

**Contração é distinguível de ATR% e ER por construção.** ATR% mede amplitude relativa ao preço; contração compara amplitudes em horizontes diferentes; ER mede deslocamento líquido dividido pelo caminho entre fechamentos. [indicators.py:104](C:/dev/project-hunter/packages/core/hunter_core/strategies/indicators.py:104), [KB-0047:20](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0047-razao-de-eficiencia-de-kaufman.md:20)

É possível preservar todos os fechamentos e mudar os pavios: ER permanece igual, mas os TRs e a contração podem mudar. Correlação empírica alta não torna as fórmulas equivalentes; correlação baixa também não demonstra vantagem incremental.

Concordo ainda com publicar cobertura, preservar janela futura, não chamar o braço de VCP e distinguir purga de independência. A ausência de sobreposição no mesmo slot está sustentada pela máquina de episódios. [episodes.py:62](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/episodes.py:62)

**OBSIDIAN**

- **KB-0051 — Três barreiras mais uma:** separar concentração de tamanho efetivo e corrigir o exemplo dos 12 blocos.
- **KB-0052 — Meta-rotulagem:** corrigir estratégias-base, terminologia e contrato dos quatro denominadores.
- **KB-0053 — Contração de volatilidade:** qualificar CANSLIM, fixar estimador e corte anterior ao rompimento.
- **Strategy Backlog / Registro de Tentativas:** registrar população-base e escolhas experimentais de cada diagnóstico.
- **Revisões da Astra:** guardar esta revisão com os cenários sintéticos e limites de verificação.