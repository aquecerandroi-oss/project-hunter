**RESUMO**

**Eu aprovaria a H-027 como análise retrospectiva com protocolo congelado antes deste cruzamento, após as correções abaixo. Não a trataria como validação confirmatória da C1 em coorte futura.** Papel assumido: `quant-engineer`.

Respostas às seis perguntas:

1. **População e unidade: adequadas ao recorte declarado.** Uma observação por estratégia × mercado × barra evita contar versões simultâneas como evidências independentes. A média das versões estima o resultado da **mistura histórica de versões elegíveis**, não de uma estratégia única executável. O agrupamento implementa essa média em [data86.py:169](C:/dev/project-hunter/.claude/state/r86/data86.py:169). Concordo em manter `momentum v3` como sensibilidade predefinida.

   Reproduzi cegamente as **874 unidades**. A generalização deve permanecer nos 16 mercados cobertos; excluir por disponibilidade histórica não equivale a uma amostra aleatória dos 275 mercados. A `volume_anomaly` já está em limite: **66 unidades, dois dias e nenhum caso com razão ≤ 0**, conforme [blind.txt:14](C:/dev/project-hunter/.claude/state/r86/blind.txt:14).

2. **OLS conjunto: sim, é a operacionalização simples correta de “incremental conjunto”.** O coeficiente da razão mede sua associação linear com R_net após controlar simultaneamente as outras três variáveis. Não é necessário acrescentar um teste omnibus dos quatro coeficientes.

   A escala mediana/MAD é defensável, mas **padronização robusta não torna OLS robusto a observações influentes**: o ajuste continua por mínimos quadrados ([stats86.py:19](C:/dev/project-hunter/.claude/state/r86/stats86.py:19)). O MRE de **0,05 R/desvio robusto** é uma convenção legítima; não tem a mesma interpretação econômica do contraste entre tercis da H-023. Também distinguiria “estimativa ≥ MRE, significativamente positiva” de “evidência de efeito ≥ MRE”: esta última exigiria limite inferior acima de 0,05.

3. **Bootstrap por dia: aceitável como aproximação exploratória, fraco como único fundamento confirmatório.** A fórmula do p centrado tem a direção correta para testar β > 0; não encontrei inversão de cauda em [stats86.py:46](C:/dev/project-hunter/.claude/state/r86/stats86.py:46). Porém, 10.000 réplicas reduzem erro de Monte Carlo, não resolvem poucos clusters ou dependência entre eles.

   **Sim, publicaria cluster por mercado ao lado.** Two-way dia × mercado é conceitualmente pertinente quando coexistem choques comuns diários e dependência serial por mercado. Com 23 dias e 16 mercados, também precisa de cuidado de pequena amostra. Nenhum dos dois ICs unidimensionais, nem simplesmente escolher o mais largo, equivale a inferência two-way. Essas limitações estão discutidas em [Cameron e Miller, §§V–VI](https://faculty.econ.ucdavis.edu/faculty/cameron/research/Cameron_Miller_JHR_2014_July_09.pdf).

4. **Não identifiquei antecipação calendárica nas fórmulas examinadas.** `D = data_UTC(obs) − 1` está correto, inclusive à meia-noite; o código exige os 20 dias completos e verifica suas chegadas ([data86.py:66](C:/dev/project-hunter/.claude/state/r86/data86.py:66)). Os fechamentos `obs−1 min` e `obs−241 min` estão separados por quatro horas e ficam dentro da janela cuja chegada é verificada ([q_feat.sql:31](C:/dev/project-hunter/.claude/state/r86/q_feat.sql:31), [data86.py:147](C:/dev/project-hunter/.claude/state/r86/data86.py:147)).

   **Ressalva:** `received_at` é uma proxy de persistência, não prova de disponibilidade no contexto do worker. O campo usa `server_default=func.now()` ([market_data.py:61](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:61)); o caminho de persistência ignora velas não finais e não sobrescreve conflitos ([persist_rows.py:104](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:104)). Portanto, preservaria expressamente a limitação já aceita no [R83:123](C:/dev/project-hunter/.claude/state/notes-R83.md:123): **reconstrução retrospectiva causal em relação às barras, não reprodução certificada do que o scanner tinha em memória**.

   Usar ATR% do envelope é adequado. Apenas esclarecer: a grade de decisão de `volume_anomaly` é 5 min, mas seu ATR padrão é **15 min**, conforme [volume_anomaly_v1.py:72](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:72).

5. **Ordem por estratégia: correta, mas incompleta nas guardas numéricas; agregação global precisa mudar.** Limite → REFUTA por limite superior → CONFIRMA → NÃO CONFIRMA respeita a errata ([stats86.py:93](C:/dev/project-hunter/.claude/state/r86/stats86.py:93)).

   O nível positivo é uma exigência **pontual**, não demonstração estatística de lucratividade. O patamar mede estabilidade do sinal entre cortes; não prova função linear nem monotonicidade. Quatro cortes consecutivos entre os cinco propostos necessariamente incluem zero. As duas metades são estabilidade temporal interna, **não replicação independente**.

6. **A declaração é honesta; o rótulo precisa carregar essa honestidade.** O texto reconhece que não cumpre a coorte futura ([prereg_frozen.md:8](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:8)), exigida explicitamente pela [C1:128](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Proximas Hipoteses.md:128>). Não cruzar antes esta variável com R_net preserva disciplina analítica, mas não apaga o conhecimento anterior sobre os mesmos desfechos nem a seleção de controles informada pelo R83.

   Hoje: **“em curso — análise retrospectiva pré-especificada; validação futura pendente”**. Se passar todas as cláusulas, publicaria “critérios estatísticos satisfeitos nesta análise retrospectiva”, sem apresentar isso como confirmação prospectiva da C1.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Conferi que o bloco congelado consta identicamente na Fila. Não abri o arquivo de desfechos do R86.

**TESTES**

Executei:

```text
uv run pytest .claude/state/r86/test_r86.py -q
18 passed, 1 warning in 0.72s
```

Desativei cache, bytecode, sincronização de dependências e carregamento automático de plugins. O aviso foi `Unknown config option: asyncio_mode`, decorrente dos plugins desativados.

Sondas adicionais, executadas em memória via `uv run python -`, com dados exclusivamente sintéticos:

```text
SINTETICO indicador constante: [0.5474999999999998, 0.5474999999999998]
SINTETICO bootstrap singular: IndexError index -1 is out of bounds for axis 0 with size 0
SINTETICO metade 2 NaN: CONFIRMA
```

Checagem exclusivamente cega do cache:

```text
CEGO terminais fora do intervalo: 0
CEGO unidades: 874 posto X: 5
```

Nos cortes −5%, −2,5%, 0%, +2,5%, +5%, os grupos menores têm respectivamente **53, 119, 198, 249 e 342 unidades**. Portanto, o problema de indicador constante não apareceu nesses cortes atuais da momentum. O MD5 de `feat.csv` também coincide com o registrado.

Não executei a análise com R_net nem consultas à VPS.

**MUST-FIX**

1. **Aplicar e congelar a população declarada no caminho de extração.**  
   O SQL não filtra o intervalo de emissão nem explicita Binance; o carregador também não aplica o intervalo ([q_feat.sql:19](C:/dev/project-hunter/.claude/state/r86/q_feat.sql:19), [data86.py:116](C:/dev/project-hunter/.claude/state/r86/data86.py:116)).

   **Cenário:** reexecutar a consulta após novas emissões incorpora sinais posteriores ao `as_of`, alterando composição, escala robusta e coeficientes. No cache atual encontrei zero terminais fora da janela, portanto **não afirmo contaminação atual**.

   Correção: filtros explícitos, conjunto congelado de IDs elegíveis e `read_at` dos estados/desfechos. Na junção final, conferir unicidade e divergências de disponibilidade em relação ao passo cego.

2. **Falhar de forma fechada diante de ajuste não identificável ou resultado não finito.**  
   `fit()` aceita matriz singular; o bootstrap descarta réplicas singulares, mas não estabelece tolerância máxima e tenta calcular percentis mesmo sem réplicas válidas ([stats86.py:28](C:/dev/project-hunter/.claude/state/r86/stats86.py:28), [stats86.py:53](C:/dev/project-hunter/.claude/state/r86/stats86.py:53)). O uso de `min(halves)` permite passar uma segunda metade `NaN` ([stats86.py:99](C:/dev/project-hunter/.claude/state/r86/stats86.py:99)).

   **Cenários reproduzidos:** indicador constante recebe β positivo sem contraste identificável; todas as réplicas inválidas derrubam a execução; segunda metade indisponível recebe `CONFIRMA`.

   Correção: validar finitude, MAD, posto e suporte antes do ajuste; verificar as duas metades separadamente; declarar limite de réplicas inválidas antes dos resultados. Esses problemas devem bloquear **também REFUTA**. Nos cortes, uma partição sem contraste válido não pode contar como patamar.

3. **Não dar força confirmatória ao bootstrap diário sem tratar sua hipótese de independência.**  
   O procedimento reamostra dias isolados ([stats86.py:49](C:/dev/project-hunter/.claude/state/r86/stats86.py:49)).

   **Cenário:** um mercado mantém um componente residual positivo por vários dias e também permanece acima da média móvel. Reamostrar esses dias como independentes pode estreitar o IC e produzir significância excessiva.

   Para esta rodada, a solução simples é restringir formalmente a conclusão a análise exploratória, reportando mercado e sensibilidade temporal. Para a validação futura, congelar inferência compatível com dependência por mercado e tempo, com tratamento de poucos clusters. Não escolher o método depois de comparar seus p-valores.

4. **Corrigir a regra global de REFUTA.**  
   O registro permite REFUTA quando todas as estratégias **fora do limite** refutam ([prereg_frozen.md:8](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:8)).

   **Cenário concreto:** momentum refuta, volume_anomaly permanece desconhecida por falta de dados; o agregado declara H-027 refutada, embora a hipótese aceite confirmação por qualquer uma das duas.

   Eu usaria: alguma confirma → CONFIRMA; **ambas refutam** → REFUTA; ambas limitadas → LIMITE; demais combinações → NÃO CONFIRMA, sempre com os resultados individuais. Verificar “ambas limitadas” antes de qualquer `all()` sobre lista vazia.

5. **Separar o resultado mecânico da validação da C1 no título e no status, não apenas na ressalva final.**  
   A exigência de coorte futura permanece não atendida; o próprio registro reconhece reutilização da população do R83 e os 23 dias abaixo do limiar editorial ([prereg_frozen.md:7](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:7), [prereg_frozen.md:8](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:8)).

   **Cenário:** `CONFIRMA` migra sozinho para o frontmatter, mapa ou resumo posterior, perdendo a ressalva, e passa a ser citado como validação independente.

   Correção: manter a natureza retrospectiva explícita em todo resumo e deixar a validação futura pendente. Não transformar falta de coorte nova em refutação estatística da variável.

**NICE-TO-HAVE**

- **Diagnósticos cegos:** dispersão residual da razão após os controles, condicionamento da matriz, concentração por mercado/dia e suporte de cada metade. Posto completo sozinho não assegura precisão.
- **Influência:** exclusão de um mercado ou dia por vez, apenas descritiva; nenhum descarte por produzir resultado inconveniente.
- **Poder:** tratar os 0,17 R como aproximação de planejamento. O cálculo declarado não incorpora explicitamente colinearidade, distribuição da escala robusta nem a probabilidade de passar conjuntamente nível, patamar e metades ([prereg_frozen.md:8](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:8)).
- **Agregação:** explicitar que as versões entram após todas as guardas e com as quatro variáveis disponíveis. `units()` sozinho filtra apenas presença do desfecho e calcula ATR com as versões que o possuem ([data86.py:173](C:/dev/project-hunter/.claude/state/r86/data86.py:173)); o chamador precisa garantir a população completa.
- Publicar IC do nível favorável, embora a cláusula congelada exija somente sua média positiva.

**O QUE EU FARIA DIFERENTE**

Manteria **a mesma razão, os mesmos controles e o mesmo OLS**. Não acrescentaria modelos flexíveis, novos horizontes ou procura de limiares.

Usaria esta rodada para estimar o efeito condicional e avaliar o instrumento. Depois congelaria uma validação em sinais posteriores ao registro definitivo, com parada por amostra **e tempo**, maturação dos desfechos e inferência temporal definida antecipadamente. As metades atuais continuariam sendo diagnóstico de estabilidade.

Qualquer correção agora deveria entrar como **emenda datada antes da abertura de R_net**, preservando o texto original.

**CONCORDO COM**

- Horizonte de 20 dias como variável nova, sem rebatizar a pista `_low`.
- Controles simultâneos e análise por estratégia.
- Unidade por barra, evitando pseudorreplicação entre versões.
- Família Holm fixa, inclusive com `p = 1` para a estratégia limitada.
- Exigir ganho líquido em nível e não confundir imprecisão com refutação.
- Declarar a cobertura estreita e manter sensibilidades incapazes de “resgatar” o resultado.
- Exigir repetição futura antes de qualquer ativação.

**OBSIDIAN**

- **Fila de Hipóteses — H-027:** acrescentar emenda pré-desfecho com população congelada, guardas numéricas, agregação global e natureza retrospectiva.
- **Próximas Hipóteses — C1:** registrar que R86 examina a candidata, mas não cumpre sua validação em coorte futura.
- **Revisões-Astra — H-027 pré-registro:** guardar este parecer, os testes executados e os contraexemplos sintéticos.
- **KB-0163 — Perto da máxima de 24 h não separa os sinais do Lab:** ligar H-027 como análise relacionada, sem apresentá-la como replicação da pista `_low`.
- **Mapa de Estratégias:** preservar “validação futura pendente” ao resumir eventual resultado do R86.