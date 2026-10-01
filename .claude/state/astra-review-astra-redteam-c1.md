**RESUMO**

**Eu não aceitaria um eventual CONFIRMA da H-027 como confirmação da C1 ainda.** O pré-registro cobre boa parte da antecipação e da escolha oportunista de parâmetros, mas deixa abertas formas concretas de confundir tendência diária com moeda, regime, dependência temporal e custo.

A H-027 reconhece que usa sinais históricos prospectivos do Lab, **não uma coorte emitida depois do registro**. Também declara 874 unidades de `momentum`, mas apenas 23 dias e 16 mercados; `volume_anomaly` tem 66 unidades em dois dias. Esses números são do registro existente, não uma medição minha. [Pré-registro:6](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:6)

Revisão no papel de `quant-engineer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Li o pré-registro, os arquivos disponíveis de R86, as notas solicitadas e os caminhos relevantes de cálculo de outcomes.

**TESTES**

Não executei testes nem abri os valores dos desfechos. Fiz inspeção estática com `Get-Content` e `rg`. Os testes citados abaixo **existem, mas não foram validados nesta revisão**.

**MUST-FIX**

As guardas adicionais abaixo são recomendações para congelar antes da análise confirmatória; não são critérios que já constam integralmente da H-027.

**1. Momentum entre moedas aparecer como estado temporal — cobertura parcial.**

- **Falha concreta:** moedas permanentemente mais fortes têm razão diária maior e melhores outcomes. O modelo dá β positivo mesmo que, dentro de cada moeda, mudar de estado não melhore nada. Um choque comum favorável também pode produzir a associação.
- **Já coberto:** ajuste conjunto por `_low`, ATR% e `return_4h`. Isso trata essas covariáveis, mas não identifica separadamente efeitos de moeda e de dia. O modelo registrado é uma OLS agrupada. [Pré-registro:7](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:7)
- **Guarda:** congelar um contraste adicional com efeitos fixos de mercado e dia, ou decompor explicitamente o efeito entre moedas e dentro da mesma moeda. Para afirmar “estado temporal”, exigir sinal positivo no componente dentro da moeda, com variação residual identificável.
- **Verificação:** fixture em que `R` depende somente de moeda/dia e a razão acompanha esses fatores deve perder o aparente efeito após o controle. `fit()` hoje aceita a matriz recebida, sem impor essa composição. [stats86.py:28](C:/dev/project-hunter/.claude/state/r86/stats86.py:28)

**2. Um único regime de setembro virar evidência sobre “2022+” — cobertura parcial.**

- **Falha concreta:** as duas metades passam porque ambas pertencem ao mesmo movimento de mercado. Isso não demonstra estabilidade entre regimes.
- **Já coberto:** β positivo nas duas metades cronológicas. Mas a janela registrada é setembro de 2026; estar depois de 2022 não equivale a testar o período pós-2022. [Pré-registro:6](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:6)
- **Guarda:** restringir expressamente a conclusão ao recorte observado. Para generalizar, exigir replicação futura com calendário e regra de encerramento congelados; se houver estratos de regime, defini-los por informação disponível antes da decisão, sem selecionar depois o regime vencedor.
- **Verificação:** imprimir datas e composição de cada metade/estrato; manter todos no relatório, inclusive negativos. Não importar como validação o painel diário **à vista** das H-025/H-026.

**3. Sobreposição e persistência entre dias estreitarem artificialmente o IC — cobertura parcial.**

- **Falha concreta:** vários sinais capturam o mesmo impulso; posições atravessam a meia-noite; uma moeda mantém resíduos correlacionados durante dias. Reamostrar dias isolados quebra essa dependência.
- **Já coberto:** versões na mesma barra são agregadas e todos os mercados de um dia são reamostrados juntos. Isso é útil, mas `cluster_boot()` sorteia dias independentemente. [data86.py:169](C:/dev/project-hunter/.claude/state/r86/data86.py:169), [stats86.py:42](C:/dev/project-hunter/.claude/state/r86/stats86.py:42)
- **Guarda:** congelar inferência em blocos consecutivos de calendário, carregando conjuntamente os mercados, e uma sensibilidade à dependência por mercado. Definir previamente os comprimentos de bloco e o que acontece quando restam poucos blocos. No corte temporal, purgar outcomes que atravessam a fronteira.
- **Verificação:** teste sintético com choques compartilhados e persistentes entre dias; contar intervalos de outcome sobrepostos e blocos efetivamente disponíveis. Ter janela móvel de 20 dias não determina sozinho o comprimento correto do bloco.

**4. Muitas linhas, mas poucos dias informativos em um braço — cobertura parcial.**

- **Falha concreta:** existem 23 dias totais e 30 observações negativas, mas quase todas as negativas vêm de um único dia. O portão atual passa.
- **Já coberto:** mínimo de 150 unidades, 15 dias totais e 30 unidades por grupo. **Não há mínimo de dias por grupo ou por corte do patamar.** [stats86.py:93](C:/dev/project-hunter/.claude/state/r86/stats86.py:93)
- **Guarda proposta:** exigir, para cada contraste que decide, pelo menos 15 datas distintas em cada braço, além dos mínimos de unidades; exigir suporte nas duas metades e declarar a quantidade de blocos independentes. Esse piso é uma convenção conservadora a registrar, não garantia de potência.
- **Verificação:** fixture com 30 negativos em uma única data deve impedir CONFIRMA. Para publicação como evidência do Lab, respeitar também o limiar editorial de 30 dias; a própria H-027 reconhece que ainda não o atinge. [Pré-registro:8](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:8)

**5. Uma ou duas moedas carregarem todo o efeito — falta guarda decisória.**

- **Falha concreta:** uma moeda dispara repetidamente, domina a OLS e aparece em quase todos os dias. O bootstrap por dia preserva sua dominância.
- **Já coberto:** descrição da restrição a 16 mercados e bootstrap por mercado **descritivo**. Não foi congelado um veto por concentração. [Pré-registro:6](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:6), [Pré-registro:7](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:7)
- **Guarda:** publicar pesos, contribuição e influência por mercado; recalcular retirando cada mercado. Minha proposta é exigir que β e nível favorável mantenham sinal positivo em todas essas exclusões para uma conclusão generalizada. Não exigir significância em cada exclusão.
- **Verificação:** fixture cujo único efeito esteja em uma moeda deve bloquear a generalização; comparar também pesos iguais por mercado-dia com o estimador original.

**6. R líquido hipotético virar lucro executável — cobertura parcial.**

- **Falha concreta:** o grupo favorável opera justamente quando spread e slippage aumentam. O custo fixo deixa sua média ligeiramente positiva, mas o custo executável a torna negativa.
- **Já coberto:** `r_multiple` inclui funding; funding não apurável produz nulo. Contudo, os preços do Lab são explicitamente sintéticos, baseados em custos assumidos. [settle.py:82](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/settle.py:82), [pricing.py:1](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:1)
- **Guarda:** congelar cenários de custo e atraso; reconstruir cada outcome com custos por perna e risco inicial, sem descontar uma constante arbitrária em R. Exigir nível positivo sob o cenário conservador escolhido antes. Para sustentar lucratividade, exigir também IC inferior do nível acima de zero; hoje basta a média pontual positiva.
- **Verificação:** reconciliar entrada, saída, taxas, funding e denominador por sinal; aumentar custo deve reduzir o resultado econômico correspondente. O portão atual verifica somente `level_pos > 0`. [stats86.py:99](C:/dev/project-hunter/.claude/state/r86/stats86.py:99)

**7. Look-ahead diário — núcleo coberto; falta fechar a prova integrada.**

- **Falha concreta:** usar o fechamento do próprio dia, aceitar um dia incompleto ou incluir backfill recebido depois da emissão.
- **Já coberto:** janela termina no dia UTC anterior; exige 1.440 velas finais e fechamento das 23:59; chegada posterior à emissão é recusada. Há testes de meia-noite, perturbação do futuro, incompletude e chegada tardia. [data86.py:66](C:/dev/project-hunter/.claude/state/r86/data86.py:66), [test_r86.py:42](C:/dev/project-hunter/.claude/state/r86/test_r86.py:42)
- **Guarda restante:** provar SQL → CSV → população final, incluindo unicidade/alinhamento dos 1.440 minutos e aplicação obrigatória de `guard_window()`. As funções separadas não provam que o executor as chama na ordem correta. [q_daily_09.sql:6](C:/dev/project-hunter/.claude/state/r86/q_daily_09.sql:6), [data86.py:147](C:/dev/project-hunter/.claude/state/r86/data86.py:147)
- **Verificação:** reconstruir amostras truncadas no instante permitido e exigir igualdade; inserir uma vela atrasada deve excluir a unidade. `emitted_at` prova disponibilidade até a emissão, não necessariamente que a feature já estava calculada no início da decisão.

**8. População mudar ao repetir a consulta — defeito concreto no caminho R86.**

- **Falha concreta:** repetir a extração amanhã acrescenta sinais novos e permite parar quando o resultado confirmar; mercados de outra exchange também podem entrar.
- **Já coberto no texto:** Binance, início em 06/09 e corte exclusivo em `2026-10-01 00:00Z`.
- **Falta no código:** `q_feat.sql` filtra direção, coorte e estratégia, mas não datas nem exchange; `feature_rows()` filtra perpétuo e terminal, sem completar esses filtros. [q_feat.sql:19](C:/dev/project-hunter/.claude/state/r86/q_feat.sql:19), [data86.py:112](C:/dev/project-hunter/.claude/state/r86/data86.py:112)
- **Guarda/verificação:** predicados explícitos na extração e assertions no carregador; congelar IDs e hashes dos insumos. Inserir sinal posterior ao corte ou de outra exchange não pode alterar nenhuma estatística. Congelar também a regra de maturação dos outcomes para não favorecer operações que encerram rapidamente.

**9. Escolha de limiar e reutilização dos mesmos outcomes — bem cobertas no texto, parcialmente na proteção experimental.**

- **Falha concreta:** olhar cinco cortes, duas estratégias, versões e sensibilidades, depois destacar apenas o vencedor; chamar de validação nova uma população já investigada no R83.
- **Já coberto:** janela, MRE, grade, semente, família Holm de duas estratégias, secundárias descritivas e proibição de recalibrar. O pré-registro também reconhece a reutilização e exige repetição posterior. [Pré-registro:7](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:7), [Pré-registro:8](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:8)
- **Guarda:** um único julgamento com término congelado; preservar histórico de emendas; nenhuma sensibilidade pode resgatar uma primária negativa. Na replicação, estimar transformações no conjunto autorizado e congelá-las.
- **Verificação:** Holm deve receber sempre as duas estratégias, inclusive `p=1` para a sem dados; o relatório deve imprimir todas as cláusulas. Hash prova integridade de um conteúdo, não prova sozinho que ele precedeu a leitura dos resultados.

**10. Censura e mistura de versões fabricarem a associação — cobertura parcial.**

- **Falha concreta:** mercados com histórico completo são mais líquidos; funding ausente remove operações desfavoráveis; versões com saídas diferentes predominam em períodos diferentes. A razão diária acompanha essas mudanças.
- **Já coberto:** exclusões contadas, restrição da conclusão ao recorte e média de versões na mesma barra. Porém, `units()` ignora versões sem outcome e faz média das restantes: a composição da unidade pode variar. [data86.py:169](C:/dev/project-hunter/.claude/state/r86/data86.py:169)
- **Guarda:** congelar elegibilidade por informação prévia, tabela de perdas por mercado/dia/versão/estado e política para componentes ausentes. Para sustentar uma estratégia implementável, exigir replicação em versão congelada; a média entre versões descreve uma mistura.
- **Verificação:** conciliar emitidos → elegíveis → maturados → completos → unidades, sem desaparecimentos silenciosos. Declarar falta de dados não demonstra que a censura seja independente do retorno.

**11. Confirmar inclinação contínua e vender isso como aprovação do filtro `> 0` — falta alinhamento.**

- **Falha concreta:** β contínuo é positivo, mas a associação muda de forma perto de zero; o grupo positivo é lucrativo, porém rende menos que o negativo. O filtro proposto não melhora a seleção.
- **Já coberto:** a H-027 torna a razão contínua primária e o contraste binário secundário. O patamar exige quatro de cinco cortes positivos, portanto não obriga que o corte zero seja positivo. [Pré-registro:7](C:/dev/project-hunter/.claude/state/r86/prereg_frozen.md:7), [stats86.py:75](C:/dev/project-hunter/.claude/state/r86/stats86.py:75)
- **Guarda/verificação:** ou limitar a conclusão à associação contínua, ou pré-registrar o contraste específico do filtro como requisito adicional. Fixture com β contínuo positivo e β do corte zero negativo não pode autorizar esse filtro.

**12. Inferência numericamente válida apenas nas réplicas sobreviventes — falta guarda.**

- **Falha concreta:** colinearidade e poucos grupos tornam grande parte das réplicas singular; descartar essas réplicas seleciona uma distribuição que parece precisa.
- **Código:** o bootstrap descarta matrizes sem posto completo e devolve `bad`; o veredito não recebe esse número. [stats86.py:53](C:/dev/project-hunter/.claude/state/r86/stats86.py:53), [stats86.py:93](C:/dev/project-hunter/.claude/state/r86/stats86.py:93)
- **Guarda:** validar finitude, posto e suporte residual da amostra original; congelar limite de réplicas inválidas — proponho 1% — acima do qual não há confirmação nem refutação.
- **Verificação:** testar colinearidade, MAD zero, valores não finitos e nulos sintéticos com dependência semelhante à população. Recuperar coeficientes de uma OLS sintética simples não calibra a taxa de falso CONFIRMA desse protocolo. [test_r86.py:145](C:/dev/project-hunter/.claude/state/r86/test_r86.py:145)

**NICE-TO-HAVE**

Publicar um quadro único com unidades, dias por braço, mercados, blocos, exclusões, custos de equilíbrio e resultados sem cada moeda. Isso torna as limitações auditáveis sem escolher diagnósticos depois.

**O QUE EU FARIA DIFERENTE**

Preservaria a H-027 como análise histórica registrada, com conclusão restrita. Usaria esta revisão para congelar uma replicação futura que separe efeito temporal de composição por moeda, trate dependência entre dias e teste o filtro realmente pretendido.

Se os desfechos já tiverem sido abertos, novas guardas não devem ser apresentadas como parte do registro original: são emenda posterior ou protocolo da replicação.

**CONCORDO COM**

A fórmula causal, a exigência de dias completos, o ajuste conjunto, a separação por estratégia, o funding indisponível como nulo, a família Holm fixa e a proibição de transformar “perde menos” em “lucra”. Também concordo com a restrição explícita de que um resultado histórico não autoriza ativação.

**OBSIDIAN**

- **Fila de Hipóteses — H-027:** registrar esta revisão e separar guardas originais, emendas e requisitos da replicação.
- **Próximas Hipóteses:** atualizar C1 para apontar à H-027, preservando a exigência de coorte futura.
- **KB-0167 — Análise gráfica:** distinguir associação contínua, filtro operacional e efeito dentro da mesma moeda.
- **Revisões-Astra — H-027/C1 pré-mortem:** registrar cenários, controles e verificações acima.
- **Mapa de Estratégias:** manter C1 sem promoção a evidência confirmada enquanto faltar replicação adequada.