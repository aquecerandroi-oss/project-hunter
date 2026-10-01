**RESUMO**

**A síntese precisa de correções antes de orientar a interpretação da H-027.** A aritmética está correta como ilustração de **deriva constante**, mas não sustenta o teto proposto para β nem a classificação automática de resultados maiores como suspeitos.

Concordo que **β negativo é compatível com a literatura**. Isso significa “não contradiz os estudos”, não “os estudos preveem esse sinal na H-027”.

Papel assumido: `quant-engineer`. Revisão somente de leitura, sem consultar novos desfechos.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Fila preservada; nenhum commit.

**TESTES**

Não executei testes de código nem medições. Recalculei apenas os três cenários publicados, em PowerShell, pela expressão `Δμ × (h/24)/(1,5 × ATR%)`:

```text
baixo: 0,001389 R
central: 0,016667 R
generoso: 0,111111 R
```

**MUST-FIX**

**1. Incorporar a emenda do pré-registro à leitura da síntese.**

A [Fila:324](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:324>) exige **dois bootstraps**, por dia e por mercado; usa o maior p antes de Holm; exige os dois ICs para confirmar/refutar; acrescenta `LIMITE (instrumento)` e altera a regra global. Também exige chamar o estudo de **análise retrospectiva pré-especificada**.

A [KB-0179:75](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer.md:75) apresenta `REFUTA` com um único limite superior, sem distinguir estratégia de resultado global.

**Cenário de falha:** momentum refuta e volume_anomaly fica em limite. Pela emenda, o global é **NÃO CONFIRMA**, não REFUTA. Outro: IC por dia passa, por mercado não; a leitura centrada apenas nos 23 dias superestima a evidência.

Incluir também a precedência de `LIMITE (instrumento)`: falha de identificação não permite refutação econômica.

**2. Manter a conta como cenário ilustrativo, retirando sua função de teto empírico.**

Há quatro problemas na [KB-0179:49](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer.md:49):

- **Média incondicional não limita contraste condicional.** De `μ = pμ₊ + (1−p)μ₋` não decorre que `μ₊−μ₋ ≤ μ`. Estados positivos e negativos podem se compensar. Portanto, chamar uma diferença igual à média de “já generosa” não tem sustentação.
- **A própria fonte diverge:** a linha `Mean` da tabela 2 traz **0,248%**, enquanto a legenda usa **0,263%**. Registrar a inconsistência, sem apresentar 0,263% como valor inequívoco da tabela. Isso não altera a ordem de grandeza. [Deprez & Frömmel, tabela 2](https://biblio.ugent.be/publication/01HY3C3S169G1N6QNYR55NZMFB/file/01HY60XZGZYHNQ6188MSVJT0SG.pdf).
- **Stop/alvo não são apenas um desconto adicional universal.** Sob deriva constante e demais condições iguais, saídas antecipadas reduzem exposição e podem fazer a conta com quatro horas superestimar esse canal. Mas a H-027 também pode captar diferenças na probabilidade de tocar alvo antes do stop, duração, reversão e custos. A conta não limita esses canais.
- **1 R é nominalmente 1,5 ATR na referência.** O código explicita que isso difere do risco na entrada posterior ([momentum_v1.py:7](C:/dev/project-hunter/packages/core/hunter_core/strategies/momentum_v1.py:7)); o denominador efetivo é `entry − stop` ([pricing.py:74](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:74)).

**Cenário de falha:** o estado diário altera a frequência de rompimentos que alcançam o alvo, produzindo efeito maior que o cenário central. A síntese o chama de suspeito porque comparou esse efeito com uma conta que contempla somente deriva uniforme.

**Resposta à pergunta sobre direção do erro:** a conta pode **superestimar o canal de deriva** e **subestimar outros canais**. Não há viés de direção conhecido para o efeito total da H-027.

**3. Não converter contraste binário em β ajustado sem conhecer a distribuição conjunta.**

A afirmação “β contínuo […] da mesma ordem ou menor” da [KB-0179:65](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer.md:65) não é garantida.

Mesmo num modelo linear simples, o contraste depende de `β × diferença média de z entre grupos`. Com controles, entram também diferenças nas covariáveis. O β da H-027 depende da associação entre **razão residualizada e resultado residualizado**; MAD não resolve essa diferença de estimando.

Pelo mesmo motivo, **β negativo não implica que a média bruta do grupo ≤ 0 seja maior**, como sugere a linha 74.

**Cenário de falha:** diferenças de ATR e `return_4h` fazem o grupo > 0 ganhar mais em média, enquanto o coeficiente parcial da razão é negativo. A tabela relata uma inversão dos grupos que não ocorreu.

A correlação entre mercados afeta sobretudo **precisão e identificação**, não fornece um multiplicador conhecido para β. Tampouco os ±0,12 R e 80% para 0,17 R são precisão/poder medidos: são aproximações do registro, que não demonstram 80% de probabilidade de satisfazer **todas** as cláusulas de `CONFIRMA`.

**4. Separar lucro em nível de superioridade sobre benchmark.**

A equivalência feita na [KB-0174:77](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0174-o-filtro-de-tendencia-corta-queda-nao-acrescenta-alta.md:77) é incorreta. Uma estratégia pode lucrar e ainda perder para comprar e segurar.

A própria [KB-0166:41](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0166-evitar-as-moedas-em-queda-nao-bate-a-cesta.md:41) relata nível positivo e ausência de confirmação do ganho incremental. Seu IC também não exclui o MRE; isso não constitui evidência conclusiva de “só corta queda”.

**Cenário de falha:** o grupo > 0 apresenta lucro pontual distribuído pela coorte. A síntese o trata como contrário à literatura porque os estudos não demonstraram superioridade sobre benchmark.

Na [KB-0179:79](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer.md:79), substituiria “suspeito” por **“compatível; insuficiente para demonstrar alfa ou lucro futuro”**. O histórico negativo do Lab justifica conferir estabilidade, não atribuir antecipadamente o resultado à alta do mercado.

**5. Restringir a atribuição a Cameron, Gelbach & Miller.**

O resumo sustenta que testes assintóticos usuais podem rejeitar demais com poucos clusters e que procedimentos bootstrap-t melhoraram suas simulações. **Não demonstra que o IC percentil de pares da H-027, com exatamente 23 dias, necessariamente tende a ser estreito.** A [KB-0178:63](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0178-data-snooping-e-poucos-clusters-o-que-vale-para-a-h-027.md:63) ultrapassa esse alcance. [Resumo publicado](https://econpapers.repec.org/article/tprrestat/v_3a90_3ay_3a2008_3ai_3a3_3ap_3a414-427.htm).

**Cenário de falha:** descartar um resultado marginal com base numa alegada demonstração de subcobertura deste desenho, sem que ela exista.

**Wild cluster bootstrap-t é adequado como sensibilidade**, preservando o rótulo registrado. Especificaria hipótese nula, studentização, pesos e obtenção do IC, mantendo a escala do coeficiente comparável. Avaliaria dia e mercado separadamente; isso continua sem equivaler a inferência two-way. Dependência entre clusters e concentração da informação podem prejudicar também o wild. Esses cuidados têm apoio no [guia aberto de Cameron & Miller, §§V–VI](https://cameron.econ.ucdavis.edu/research/Cameron_Miller_JHR_2015_February.pdf), consultado nesta revisão, além do resumo de 2008.

**6. Retirar identificação de mecanismo da tabela “compatível × suspeito”.**

Na [KB-0179:82](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer.md:82) e [KB-0176:75](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto.md:75), efeito restrito a ATR alto **não identifica** “volatilidade, não tendência”.

**Cenário de falha:** existe interação entre tendência e volatilidade, ou os tercis diferem em mercados e dias. A análise atribui o resultado exclusivamente ao canal de Gao/Li.

Também ajustaria:

| Item | Leitura adequada |
|---|---|
| β ≥ 0,15 R | Não calibrado pela literatura consultada; investigar influência, sem tratar o tamanho sozinho como anomalia. |
| Contínua passa; patamar/metades falham | Não satisfaz o protocolo; pode ser instabilidade, não linearidade ou imprecisão. Não prova “pico”. |
| β perto de zero, IC amplo | Compatível; ainda exige os diagnósticos de qualidade. Retirar “nada” da coluna de checagem. |
| Estado do BTC reproduz associação | Sugere componente comum; substituir o regressor não demonstra ausência de informação incremental nem identifica causalidade. |

**7. Corrigir extrapolações e inconsistências sobre o alcance das leituras.**

Há exemplos verificáveis:

- [KB-0175:47](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0175-estado-de-mercado-condiciona-momentum-mas-em-que-direcao.md:47): **“robusto entre estados” não significa “não depende do estado”**. O resumo de CTREND não afirma igualdade de efeitos. [Resumo dos autores](https://unipub.lib.uni-corvinus.hu/11621/).
- [KB-0179:101](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer.md:101): chama Li de leitura integral, enquanto a [KB-0176:4](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto.md:4) declara seções 1–3.
- [KB-0179:103](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0179-o-que-um-resultado-da-c1-pode-e-nao-pode-dizer.md:103): “nada deles entrou” inclui Fieberg e Zarattini, cujos resumos alimentam as notas e a síntese. Escrever “não usei os textos integrais”.
- [KB-0175:87](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0175-estado-de-mercado-condiciona-momentum-mas-em-que-direcao.md:87): “no máximo um ou dois estados” e predominância da variação entre mercados não foram estabelecidos pela contagem cega.

**Cenário de falha:** um leitor futuro toma invariância entre estados, leitura integral ou decomposição da variação como fatos conferidos e fundamenta outra hipótese neles.

**NICE-TO-HAVE**

- Trocar “baixo/central/generoso” por **cenários ilustrativos**, sem probabilidade atribuída.
- Distinguir sensibilidade a extremos do resultado de **alavancagem nas covariáveis**: aparar R_net não resolve a segunda.
- Tratar `t > 3` como contexto da literatura de multiplicidade, sem transformá-lo em limiar alternativo da H-027.
- Evitar “espere metade” na KB-0177: a magnitude de decaimento em ações não calibra esta população.

**O QUE EU FARIA DIFERENTE**

Organizaria a síntese em três partes: **o que os artigos estimaram; quais mecanismos são analogias nossas; como ler os critérios congelados da H-027**.

A conta permaneceria, com esta conclusão: “Sob hipóteses ilustrativas de deriva constante, o canal pode ser pequeno. Isso não estima o β ajustado, seu limite superior nem a probabilidade do veredito.”

Não mudaria a Fila nem acrescentaria critérios decisórios.

**CONCORDO COM**

- Não encontrei justificativa para transferir diretamente regras diárias para sinais intradiários com barreiras.
- Concordo com a distinção entre custo de equilíbrio, retorno bruto e resultado líquido preservada na KB-0167.
- Concordo com repetição futura pré-registrada e diagnósticos sem trocar janela, MRE ou rótulo.
- **Não discordo da compatibilidade de β negativo.** Daniel & Moskowitz oferecem uma analogia sobre crashes durante repiques; Gao/Li mostram condicionamento do momentum intradiário por outras condições. Isso deixa o sinal da H-027 em aberto. A frase “o repique continua no curto prazo” deve aparecer como **mecanismo hipotético nosso**, não como resultado demonstrado para estas entradas. O [resumo de Gao](https://ideas.repec.org/a/eee/jfinec/v129y2018i2p394-414.html) não testa razão à MM20, perpétuos ou esta política de saída.

**OBSIDIAN**

- **KB-0179 — O que um resultado da C1 pode e não pode dizer:** incorporar a emenda, limitar a conta e corrigir a tabela.
- **KB-0173 — Tendência diária em cripto: o tamanho publicado:** retirar a apresentação dos centésimos de R como tamanho esperado empiricamente estabelecido.
- **KB-0174 — O filtro de tendência corta queda; não acrescenta alta:** separar lucro absoluto, ganho incremental e ausência de significância.
- **KB-0175 — Estado de mercado condiciona momentum, mas em que direção?:** distinguir analogia, robustez entre estados e invariância.
- **KB-0176 — Momento intradiário condicionado: o vizinho mais perto:** retirar a identificação causal por tercis de ATR.
- **KB-0177 — Decaimento e regime:** qualificar transferência de magnitudes e quantidade de regimes.
- **KB-0178 — Data snooping e poucos clusters:** corrigir o alcance do resumo e incluir a inferência por mercado.
- **Revisões-Astra — revisão da síntese C1/H-027:** registrar este parecer e as divergências resolvidas. **Fila de Hipóteses: nenhuma alteração proposta.**