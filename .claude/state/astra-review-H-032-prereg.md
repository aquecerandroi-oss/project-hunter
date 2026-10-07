**RESUMO**

**Recomendo emendar o pré-registro antes de abrir os desfechos.** A H-032 pode medir uma associação entre Mayhem e retorno **simulado nas recusadas do estrato B**. Como está, não demonstra que o veto Mayhem acrescenta valor à mesa, nem separa suficientemente comportamento econômico de efeito do instrumento.

Revisão como `quant-engineer`, em modo OPINIÃO. Não consultei desfechos.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisei o bloco da [Fila de Hipóteses:359](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:359>), a [cópia congelada:2](/C:/dev/project-hunter/.claude/state/r89/prereg_frozen.md:2), o desenho do EXP-M23, as consultas de disponibilidade e os caminhos de seleção, compra, marca e venda.

**TESTES**

Não executei testes nem consultas SQL. Fiz inspeção estática com `Get-Content` e `rg`; não há resultado de execução do simulador a declarar.

**MUST-FIX**

1. **Separar “diferença entre grupos” de “a exclusão paga”.**

   O primário é `média(não-Mayhem) − média(Mayhem)`, mas a interpretação prevista diz que confirmar coloca a exclusão “do lado certo”. [Pré-registro:5](/C:/dev/project-hunter/.claude/state/r89/prereg_frozen.md:5), [pré-registro:7](/C:/dev/project-hunter/.claude/state/r89/prereg_frozen.md:7).

   **Cenário de falha:** Mayhem tem retorno positivo, porém inferior ao não-Mayhem. D é positivo, mas excluir Mayhem e deixar o capital parado elimina ganhos. Se o capital for realocado, é preciso definir para quais oportunidades e sob quais restrições. Além disso, retirar somente o veto não admite moedas que continuam falhando em outros critérios.

   **Correção:** chamar o primário de **contraste descritivo de retorno da sonda**, sem interpretação de ganho marginal da política. A pergunta operacional exige quem passaria no restante do portão, exatamente a população reservada pelo EXP-M23 ao teste por critério. [EXP-M23:51](</C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md:51>).

   Probabilidades iguais dispensam pesos diferenciados **nessa amostra**; não randomizam Mayhem nem corrigem a seleção anterior pelo portão.

2. **Redefinir `n_outras` e congelar o tratamento de comparabilidade e suporte comum.**

   **Sim: eu excluiria da contagem usada como ajuste de comparabilidade as famílias cuja medida é mecanicamente alterada pelo Mayhem**, mediante lista justificada e congelada antes dos desfechos. Aplicaria a mesma exclusão aos dois grupos, preservando a contagem original como descrição.

   Há evidência anterior de top10 com denominador inadequado e progresso não comparável em Mayhem. [KB-0111:64](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0111-top10-share-maior-que-1-no-retrato-de-risco.md:64>), [KB-0115:54](</C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0115-volta-ao-piso-e-real-ou-artefato.md:54>). O código transforma top10 ausente em recusa com motivo e progresso abaixo do piso em outra recusa. [rules_criteria.py:229](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/rules_criteria.py:229), [rules_criteria.py:78](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/rules_criteria.py:78).

   **Cenário de falha:** a mesma contagem representa, em Mayhem, falhas do denominador; no controle, concentração ou fluxo efetivamente ruins. O tercil aproxima quantidades iguais de coisas diferentes. Condicionar em consequências do Mayhem também pode apagar parte do mecanismo ou induzir associação artificial.

   Entretanto, **retirar esses motivos não resolve causalidade**. Não presumiria que toda recusa `top10_*` ou `progress_*` de uma moeda Mayhem foi causada pelo agente. Congelaria uma classificação de famílias potencialmente contaminadas e faria a sensibilidade simétrica.

   Também falta considerar composição dos motivos, `refused_by`, versão do portão, horário intradiário e cobertura disponível na decisão. A sonda reúne recusas de diferentes conjuntos no mesmo instante; portanto, sua contagem também depende de quantos conjuntos julgaram a moeda. [refused_probe.py:151](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe.py:151).

   Antes de olhar: fixar covariáveis, tratamento de empates nos tercis e critérios mínimos de sobreposição. Publicar a parcela descartada por ausência de controle. O peso `n_M·n_N/n` estima uma população de sobreposição; não é automaticamente o mesmo alvo do contraste bruto.

3. **Pré-registrar uma auditoria do instrumento Mayhem, além da frequência do teto na saída.**

   Usar reservas virtuais para comprar **não é, por si, um erro**. O problema é assumir que limitar a venda ao SOL real demonstra execução válida. `quote_sell` calcula a venda pela curva, corta o recebimento e continua tratando a quantidade inteira como vendida. [curve.py:292](/C:/dev/project-hunter/packages/indicators/hunter_indicators/meme/curve.py:292).

   Há outra assimetria relevante: a primeira marca usa as reservas **depois da compra hipotética**, enquanto as marcas seguintes usam os snapshots observados, com o SOL real observado como teto. [paper_fill.py:171](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:171), [paper_engine.py:123](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:123).

   **Cenário de falha:** numa curva quase vazia, a compra simulada acrescenta SOL apenas no estado hipotético inicial. O snapshot seguinte não contém esse aporte; o teto comprime a marca e dispara perda, mesmo sem deterioração econômica equivalente. No sentido oposto, se a venda integral seria rejeitada por insuficiência de saldo, contabilizar uma venda integral pelo teto pode superestimar a execução. Não determinei nesta revisão qual comportamento o programa on-chain efetivamente aplica.

   **Checagens a congelar:**

   - Round-trip sem movimento externo: compra, atualização consistente das reservas virtuais **e reais**, venda; perda explicada por taxas e arredondamentos.
   - Confronto com execução de referência para a versão do programa, incluindo insuficiência de SOL, quantidade vendida, eventual rejeição e taxas Mayhem.
   - Por grupo: aporte/tamanho da reserva real na entrada, atraso e fonte dos snapshots, discrepância entre marca inicial e próxima marca, teto acionado **durante toda a trajetória**, inclusive no gatilho de saída.
   - Regra explícita: sem validar essas condições, o resultado é sobre o **simulador**, com `NÃO CONFIRMA por instrumento` para a interpretação econômica.

   Tirar apenas as saídas com teto não resolve: o teto pode ter antecipado o stop antes da fotografia final. Também não eliminaria essas moedas do primário depois de observar o resultado.

4. **Alinhar inferência, dependência temporal e estimador.**

   O bootstrap de 60 minutos é um ponto de partida razoável para dependência curta. **A permutação individual dentro do dia não fica validada por ele.** O protocolo usa ambos, mas somente exige repetição do sinal no contraste ajustado. [Pré-registro:7](/C:/dev/project-hunter/.claude/state/r89/prereg_frozen.md:7).

   **Cenário de falha:** Mayhem concentra-se em certas horas com condições comuns de mercado ou coleta. Permutar moedas ao longo do dia destrói essa estrutura e produz um p pequeno para uma diferença explicada pelo horário. Blocos de uma hora também podem subestimar dependência entre horas do mesmo dia.

   **Correção:** congelar um estimador principal e calcular sua incerteza com a mesma estrutura de pesos e ajuste. Pré-registrar sensibilidade por blocos de dia, mínimos de blocos efetivos e tratamento de réplicas sem ambos os grupos. Não usaria a permutação individual como portão confirmatório sem justificar permutabilidade; adotaria inferência que preserve os blocos, explicitando suas próprias hipóteses.

   Exigir apenas “mesmo sinal” no ajustado permite que um contraste bruto grande passe acompanhado de uma diferença ajustada desprezível.

5. **Fechar censura e precedência dos vereditos nos dois sentidos.**

   Os cenários `−1/0` são **sensibilidades**, não limites de pior e melhor caso. Zero não limita ganhos possíveis. E o próprio simulador pode retornar abaixo de −1: desconta a prioridade de saída antes de subtrair todo o gasto de entrada. [paper_engine.py:223](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:223).

   **Cenário de falha:** os não-Mayhem ausentes eram grandes vencedores; o contraste das resolvidas fica artificialmente pequeno e o IC superior cai abaixo do MRE. Hoje a cláusula permite `REFUTA`, porque a sobrevivência ao estresse é exigida para confirmar, não para refutar. [Pré-registro:7](/C:/dev/project-hunter/.claude/state/r89/prereg_frozen.md:7), [pré-registro:8](/C:/dev/project-hunter/.claude/state/r89/prereg_frozen.md:8).

   **Correção:**

   - Fixar primeiro os portões de instrumento, disponibilidade e suporte; falhar neles resulta em `NÃO CONFIRMA`, com motivo.
   - Exigir robustez da **refutação** às sensibilidades: limite superior abaixo do MRE em todos os cenários exigidos.
   - Acrescentar análise de ponto de inversão: qual retorno médio dos ausentes altera a conclusão?
   - Congelar acompanhamento e corte de maturação; contabilizar `unfilled`, nulos e falhas de execução separadamente. A execução pode recusar preenchimento por cobertura, reservas ou limites da carteira. [paper_fill.py:92](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_fill.py:92).

   Os 94 casos informados tornam essa proteção especialmente relevante, mas suas contagens precisam ser reapuradas **na janela e no estrato finais**. `LIMITE DE DADO` deve ser motivo de `NÃO CONFIRMA`, preservando os três rótulos. [RESEARCH.md:61](/C:/dev/project-hunter/docs/RESEARCH.md:61).

6. **Resolver a diferença entre a regra da H-032 e `docs/RESEARCH.md`.**

   A regra normativa exige nível lucrativo do braço selecionado; a H-032 não o exige. [RESEARCH.md:65](/C:/dev/project-hunter/docs/RESEARCH.md:65), [pré-registro:7](/C:/dev/project-hunter/.claude/state/r89/prereg_frozen.md:7).

   **Cenário de falha:** ambos perdem, não-Mayhem perde menos e sai `CONFIRMA` com interpretação de vantagem econômica.

   Eu preferiria definir explicitamente esta hipótese como **contraste descritivo**, justificando antes dos resultados qualquer adaptação da regra de nível. Sendo variável binária, “planalto de limiares” também precisa ser declarado não aplicável. Não deixar essas decisões para o relatório.

**NICE-TO-HAVE**

- Rebaixar a conta de poder a **cenário ilustrativo sob suposições**. Alvo e trailing não truncam matematicamente a cauda: a venda acontece na fotografia posterior ao gatilho. [paper_engine.py:215](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/paper_engine.py:215).
- Auditar a afirmação “primeira oportunidade, uma vez para sempre”: decisões de sorteio sem proposta ficam em memória temporária; a consulta durável recupera propostas. Um reinício com mudança de estrato/probabilidade merece checagem, embora não demonstre viés nesta coorte. [refused_probe_step.py:84](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe_step.py:84), [refused_probe_step.py:101](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/refused_probe_step.py:101).
- Definir denominador da discordância do bit, tratamento de nulos e conflitos. O cadastro atual deve servir à auditoria, sem substituir silenciosamente a classificação disponível na decisão.

**O QUE EU FARIA DIFERENTE**

Separaria dois objetivos:

1. **H-032 atual:** associação descritiva na sonda B, com auditoria do simulador, custos explicitamente modelados e sensibilidades congeladas.
2. **Hipótese futura:** valor incremental do veto em oportunidades que passariam no restante do portão, sob regras compatíveis com a mecânica Mayhem.

**O reaproveitamento do EXP-M23 é aceitável com a declaração**, tomando como premissa que seus desfechos não foram analisados. É uma análise pré-especificada de dados existentes, não uma nova coleta prospectiva nem replicação independente.

Preservaria a família e a parada originais do EXP-M23: sua regra é 14 dias de mesa ativa ou 700 mints medidos, o que ocorrer primeiro. A janela da H-032 não deve redefinir isso. [EXP-M23:67](</C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md:67>). O contraste global do M23 inclui B, portanto compartilhará observações e informação com esta leitura. [EXP-M23:112](</C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md:112>).

**CONCORDO COM**

- Fixar exposição pelas recusas gravadas na decisão e separar `mayhem_unknown`.
- Congelar janela, MRE, semente, secundárias e ausência de mudanças na mesa.
- Declarar a taxa Mayhem ainda não verificada; chamá-la de custo **modelado**, não validado como real.
- Refutar somente o tamanho previsto quando houver precisão e instrumento válidos; imprecisão continua sendo `NÃO CONFIRMA`.
- Declarar antecipadamente a perda de cegamento parcial do EXP-M23.

**OBSIDIAN**

- **Fila de Hipóteses — H-032:** acrescentar emenda anterior aos desfechos com alvo descritivo, auditoria do instrumento, ajuste e decisão simétrica sob censura.
- **EXP-M23 — Desfecho das recusadas:** registrar o compartilhamento de dados com H-032, preservando família, parada e interpretação originais.
- **Revisões-Astra — H-032/R89:** registrar este parecer e a resolução de cada must-fix.
- **Mapa de Estratégias:** distinguir estudo descritivo de Mayhem de evidência sobre o valor incremental do veto.