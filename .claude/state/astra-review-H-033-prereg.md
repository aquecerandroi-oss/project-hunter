**RESUMO**

**Eu emendaria o pré-registro antes de abrir os desfechos.** O desenho estatístico é razoável para associação retrospectiva, mas ainda há brechas na comprovação temporal e na implementação da falha fechada. `oi_rel7d` também precisa ser interpretada como **desvio do OI em relação à semana**, sem equipará-la diretamente a “lotação de comprados”.

Atuei como `quant-engineer`. Não li desfechos do R90; li o material do R86 expressamente indicado como comparação.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. O bloco H-033 e a cópia congelada não apresentaram diferenças de conteúdo na comparação, ignorando linhas vazias.

**TESTES**

Revisão estática; não executei pytest, consultas ao banco nem scripts de análise. Portanto, não afirmo que os testes passam.

**MUST-FIX**

**1. A folga de 15 minutos é uma hipótese operacional, não uma garantia contra antecipação.**

O coletor fixa o bucket antes de percorrer os símbolos sequencialmente, sem limite total explícito para a rodada ([sampling.py:289](C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:289)). O próprio contrato documenta que nenhuma folga finita prova disponibilidade ([derivatives.py:25](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/derivatives.py:25)).

**Cenário:** bucket 11:45, rodada atrasada, leitura real às 12:01 e sinal com `obs=12:00`. Sem outbox retido, o instrumento aceita a leitura: o bucket satisfaz os 15 minutos e `created=None` não recusa ([data90.py:64](C:/dev/project-hunter/.claude/state/r90/data90.py:64)).

Os **325,422642 s** são o máximo observado no intervalo exportado, não um teto histórico ([lag.txt:5](C:/dev/project-hunter/.claude/state/r90/lag.txt:5)). Antes de 26/09, considero 15 minutos defensáveis **para uma análise exploratória explicitamente condicionada a essa suposição**; não para declarar “sem antecipação comprovada”.

Exigiria congelar agora:

- sensibilidades de **30 e 60 minutos**, mantendo a tolerância de envelhecimento de 10 minutos relativamente ao novo corte;
- resultados na interseção das unidades elegíveis, além das respectivas populações completas;
- análise com proveniência temporal comprovada, separada da população com disponibilidade presumida;
- regra explícita de que estabilidade entre folgas **não elimina** a ausência de prova histórica.

**2. “Verificado no outbox” não verifica a variável inteira — nem representa necessariamente disponibilidade após commit.**

A mediana semanal usa todas as linhas pelo bucket; o outbox é associado apenas a `cur.ts` ([q_feat.sql:57](C:/dev/project-hunter/.claude/state/r90/q_feat.sql:57)). Assim, as 252 unidades verificadas são unidades com **leitura corrente** verificada, não com toda a janela certificada.

**Cenário:** uma amostra anterior da semana chega atrasada, depois do sinal, enquanto a corrente já estava disponível. A reconstrução incorpora essa amostra à mediana e à cobertura; perto do mínimo de cobertura ou de um corte, isso pode mudar elegibilidade ou grupo.

Há outra distinção: `created_at` usa `now()` da transação, e `received_at` das velas também ([system.py:171](C:/dev/project-hunter/packages/core/hunter_core/db/models/system.py:171), [market_data.py:61](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:61)). O repositório documenta expressamente que esse horário não é o commit ([outbox.py:223](C:/dev/project-hunter/packages/core/hunter_core/events/outbox.py:223)).

**Cenário:** transação começa antes da decisão, fica bloqueada e só publica uma vela antiga recuperada depois dela. `received_at <= emitted_at` passa, embora aquela linha não estivesse disponível no banco no instante da decisão.

**Correção exigida:** definir separadamente instante da observação, disponibilidade e bucket; verificar a janela inteira quando houver evidência; usar prova posterior ao commit, como despacho anterior ao corte, quando aplicável. Ausência de prova deve continuar explícita. A réplica atual também não resolve isso: `Oi` contém apenas bucket e valor ([data90.py:35](C:/dev/project-hunter/.claude/state/r90/data90.py:35)).

Para as covariáveis, **não vejo uso direto de velas futuras**: a consulta exige finais e janela anterior a `obs`. Usar chegada até `emitted_at` é coerente com disponibilidade na decisão, pois esse campo recebe `decision_at` ([q_feat.sql:43](C:/dev/project-hunter/.claude/state/r90/q_feat.sql:43), [persist.py:93](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/persist.py:93)). A ressalva é a semântica transacional acima.

**3. Congelar o tratamento do confundimento por dia antes do resultado.**

O modelo primário não controla dia; efeito fixo de mercado aparece apenas como descritivo ([pré-registro:7](C:/dev/project-hunter/.claude/state/r90/prereg_frozen.md:7)). Bootstrap por dia altera a incerteza, **não remove confundimento por dia**.

**Cenário:** durante determinados dias, o OI sobe no mercado inteiro e os rompimentos rendem menos por outro motivo. O coeficiente atribui essa associação a “lotação”, mesmo sem efeito próprio dentro do dia.

Eu exigiria pré-registrar **FE de dia e FE de mercado+dia**, com escala da variável mantida, e declarar sua consequência interpretativa. Se forem apenas sensibilidades, um resultado positivo no modelo principal continua sendo associação agregada; não demonstra mecanismo de lotação. Se forem condição para a manchete, essa condição precisa ser congelada agora.

Isso é especialmente pertinente porque o R86 já registrou mudança na conclusão sobre o MRE ao controlar dia ([KB-0170:91](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab.md:91)).

**4. Fechar o caminho completo entre identificação e veredito.**

`verdict()` recebe apenas `plateau: bool`; não recebe a identificação de cada corte. Logo, sozinho, não distingue “cortes válidos sem patamar” de “corte singular”. E verifica `REFUTA` antes de consultar o patamar ([stats90.py:107](C:/dev/project-hunter/.claude/state/r90/stats90.py:107)).

**Cenário:** um corte é singular, os dois ICs superiores ficam abaixo de 0,05 e o chamador passa `plateau=False`. Sem transmitir também a falha de identificação, sai `REFUTA`, contrariando o registro.

O R86 tinha uma ligação explícita para bloquear isso ([analysis86.py:123](C:/dev/project-hunter/.claude/state/r86/analysis86.py:123)). Exigiria revisar e testar essa ligação no R90 **antes da abertura**, incluindo MAD zero, posto e finitude nas metades e cortes.

Há também divergência literal: o registro diz “as duas em limite”, mas `global_label()` reconhece apenas duas ocorrências de `LIMITE DE DADO`; uma combinação com `LIMITE (instrumento)` resulta em `NÃO CONFIRMA` ([stats90.py:133](C:/dev/project-hunter/.claude/state/r90/stats90.py:133)). É preciso escolher uma regra inequívoca e preservar a causa instrumental no relatório.

**5. Fazer a seleção e a junção corresponderem integralmente à população congelada.**

A consulta declara Binance, mas não filtra exchange; o outbox é agrupado por símbolo e bucket, sem exchange ([q_feat.sql:18](C:/dev/project-hunter/.claude/state/r90/q_feat.sql:18), [q_feat.sql:29](C:/dev/project-hunter/.claude/state/r90/q_feat.sql:29)).

**Cenário:** surge um perpétuo homônimo em outra exchange. Ele pode entrar na população ou fornecer o horário usado como prova de chegada. Não constatei essa contaminação atual; a seleção, porém, não impede o cenário.

Além disso, `check_join()` transforma as features em dicionário e não rejeita IDs duplicados nessa entrada ([data90.py:164](C:/dev/project-hunter/.claude/state/r90/data90.py:164)). **Cenário:** uma linha duplicada pesa duas vezes na média entre versões, sem mudar o conjunto de IDs.

Exigiria filtro explícito de exchange, identidade completa no vínculo do evento e validação de unicidade dos dois lados. O caminho executável deve verificar hash, restringir aos IDs congelados e publicar divergências — não depender apenas da promessa no texto.

**NICE-TO-HAVE**

- **Dependência temporal:** pré-registrar blocos de calendário de 3/5/7 dias. A janela móvel semanal torna plausível persistência entre dias; exigir dois bootstraps separados não equivale a inferência conjunta por dia e mercado.
- **Precisão econômica:** publicar IC da média favorável. Média pontual positiva cumpre o registro, mas não demonstra expectativa positiva com precisão.
- **Listagem e unlocks:** cobertura semanal não equivale a maturidade de listagem. Eu registraria idade, mudanças de especificação e eventos conhecidos antecipadamente. Não exigiria uma coleção de controles sem fonte temporal confiável; tampouco excluiria eventos depois de observar perdas.
- **Custos:** manter `R_net` do Lab, incluindo funding, é correto. Chamaria o resultado de líquido dos **custos assumidos do Lab**, sem equipará-lo a execução real: o contrato faz essa distinção ([SHADOW-LAB.md:6](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:6)).

**O QUE EU FARIA DIFERENTE**

Usaria o nome **“OI relativo à mediana semanal”**. Contratos são uma escolha adequada para evitar que uma alta de preço, sozinha, aumente o OI nocional. Um multiplicador contratual constante cancela na diferença de logs.

Mas a normalização não separa nível de tendência: numa trajetória monotônica de `ln(OI)`, a mediana fica aproximadamente no meio da semana; a variável se comporta como uma mudança acumulada de cerca de meia semana. Isso decorre diretamente da fórmula congelada ([pré-registro:5](C:/dev/project-hunter/.claude/state/r90/prereg_frozen.md:5)). Ela também não identifica qual lado está “lotado”: todo contrato aberto tem contraparte comprada e vendida.

Quanto à sobreposição, **773/869 não cria antecipação nas features**, mas impede tratar esta leitura como validação independente. OI não ter sido cruzado anteriormente preserva novidade da associação; não apaga o conhecimento dos desfechos e do período. Os 96 sinais pós-R86 em quatro dias não são uma réplica suficiente pelos próprios pisos declarados ([blind2.txt:8](C:/dev/project-hunter/.claude/state/r90/blind2.txt:8)).

Manteria a classificação retrospectiva e reservaria a confirmação independente para sinais posteriores ao registro. Holm entre duas estratégias não corrige a sequência inteira de hipóteses pesquisadas sobre desfechos reutilizados.

**CONCORDO COM**

- **MRE 0,05:** coerente como tamanho escolhido previamente. `β̂ ≥ 0,05` junto de IC inferior positivo não prova que o efeito verdadeiro excede 0,05; essa distinção deve acompanhar a manchete.
- **Holm com `volume_anomaly` em limite:** manter `p=1` preserva a família. Com duas estratégias, o p bruto de momentum precisa ser inferior a 0,025.
- **Cortes e metades:** bons requisitos de estabilidade interna, sem equivaler a replicações. A inversão `x=-oi_rel7d` preserva o conjunto simétrico dos cinco cortes ([stats90.py:16](C:/dev/project-hunter/.claude/state/r90/stats90.py:16)).
- **Refutação restrita ao tamanho**, indisponível diferente de zero, grupo favorável positivo, réplica independente e nenhuma ativação automática: são escolhas corretas do registro ([pré-registro:8](C:/dev/project-hunter/.claude/state/r90/prereg_frozen.md:8)).

**OBSIDIAN**

- **Fila de Hipóteses — H-033:** acrescentar emenda datada sobre temporalidade, controles, população e falha fechada, preservando o original.
- **H-033-prereg — Revisões Astra:** registrar este parecer e a resolução de cada achado antes dos desfechos.
- **Market Collector:** distinguir bucket, instante da leitura, início da transação e disponibilidade após commit.
- **KB-0170:** vincular a lição reutilizada sobre FE de dia e reaproveitamento de desfechos, sem alterar o veredito histórico.
- **Mapa de Estratégias:** manter H-033 como análise retrospectiva em revisão, sem antecipar resultado.