**RESUMO**

**Eu revisaria o pré-registro antes de executar a etapa confirmatória.** A fórmula proposta não representa o equilíbrio da estratégia real; o filtro de 70% pode eliminar oportunidades válidas; e bootstrap/permutação, como definidos, podem produzir confiança excessiva.

O R68 pode investigar previsibilidade nos perpétuos. Para concluir que essa previsibilidade paga a execução spot na Solana, faltam definição do retorno executável, moeda de referência e custo integral.

Revisão no papel de `quant-engineer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Referência principal: [preregistro.md](C:/dev/project-hunter/.claude/state/r68/preregistro.md:1).

**TESTES**

Não executei o estudo, consultas à VPS ou testes de implementação. Os números de cobertura são os declarados no pré-registro, não uma medição independente desta revisão.

**MUST-FIX**

**1. Substituir o break-even de payoff simétrico pela expectativa condicional da operação.**

A expressão das [linhas 49–52](C:/dev/project-hunter/.claude/state/r68/preregistro.md:49) é correta **para uma aposta que paga exatamente `+m` ou `−m`**, descontado `c`. Usar a mediana incondicional de `|r|` como esse payoff é enganador para saída por tempo.

Se `S=1` significa entrada, a condição correta, sob custo aditivo, é:

\[
\mu_{\text{líquida}}=E[r_h-C\mid S=1]>0.
\]

Sem retornos exatamente zero, definindo:

\[
p=P(r_h>0\mid S=1),\quad
a=E[r_h\mid r_h>0,S=1],\quad
b=-E[r_h\mid r_h<0,S=1],
\]

temos:

\[
\mu_{\text{líquida}}=pa-(1-p)b-c,
\qquad
p^*=\frac{b+c}{a+b}.
\]

Aqui, `a` e `b` são **médias condicionadas às entradas**, não medianas de todas as barras. Com retornos zero, inclua sua probabilidade explicitamente; a primeira equação continua válida. Com custos variáveis, use os custos de cada operação.

Além disso, `p*` é uma identidade contábil mantendo `a,b,c` fixos: mudar o limiar pode mudar todos eles.

**Cenário de falha:** uma regra acerta frequentemente movimentos pequenos, mas perde muito nos erros. O `p*` calculado com a mediana parece alcançável, embora a expectativa seja negativa. No sentido inverso, uma regra seletiva pode ganhar com menos de 50% de acerto.

A frase “nenhuma taxa de acerto empata” também precisa ficar limitada ao modelo `±m`; em `p*=1`, 100% de acerto **empata**, e não há lucro.

---

**2. Retirar `p*<0,70` como portão econômico da parte B.**

O filtro está nas [linhas 58–60](C:/dev/project-hunter/.claude/state/r68/preregistro.md:58). Pré-fixar um número evita escolhê-lo depois do resultado, mas não lhe dá fundamento econômico.

Com `c=0,54%`, esse filtro equivale algebricamente a exigir **mediana de `|r|` superior a 1,35%**. Isso seleciona amplitude típica, não previsibilidade nem rentabilidade condicional.

**Cenário de falha:** um horizonte tem movimentos habitualmente pequenos, mas o sinal identifica episódios raros com retorno suficiente para pagar o custo. A mediana elimina o horizonte antes de testar justamente essa seleção.

Minha recomendação: **parte A descritiva; testar os cinco horizontes em B**. Mostrar distribuição de retornos assinados, `P(r>c)`, caudas e MFE, sem chamar nenhum desses números de prova de vantagem. MFE descreve uma oportunidade retrospectiva; não é uma saída realizável.

Se houver restrição computacional, o filtro pode ser administrativo, com conclusão limitada a “não investigado”, nunca “economicamente inviável”.

---

**3. Trocar o bootstrap exclusivamente por mercado por reamostragem temporal conjunta.**

As [linhas 93–94](C:/dev/project-hunter/.claude/state/r68/preregistro.md:93) reconhecem poucos clusters, mas a ressalva não resolve a validade.

**Dezesseis clusters não tornam todo método automaticamente inválido.** Contudo, o bootstrap simples de mercados depende de independência entre clusters, além de ter aproximação frágil com poucos grupos. A literatura documenta problemas de inferência com poucos clusters: [Cameron, Gelbach e Miller](https://www.nber.org/papers/t0344).

**Cenário de falha:** uma única alta generalizada beneficia sinais em todos os 16 ativos. Reamostrar mercados trata as exposições ao mesmo choque como replicações independentes e pode estreitar indevidamente o IC.

Eu definiria o alvo como **desempenho futuro nesse painel fixo** e usaria blocos temporais contíguos, carregando **todos os mercados juntos** em cada bloco. Reamostrar conjuntamente soma de retornos e contagem de operações preserva o estimador por operação; não trocar inadvertidamente pela média simples das médias diárias.

**Mercado-dia como clusters independentes não resolve:** quebra dependência entre mercados no mesmo dia e entre dias do mesmo mercado. Clustering bidimensional é outra técnica, não equivalente a criar milhares de células independentes.

O comprimento do bloco deve ser escolhido por procedimento congelado, sem consultar o desempenho final, considerando persistência de sinais, retornos e ajuste rolante. Um dia não é automaticamente suficiente. Com poucos blocos efetivos, o resultado será inconclusivo; 5.000 reamostragens não criam informação.

---

**4. Não usar o embaralhamento intradiário como teste de permutação validado.**

As [linhas 95–96](C:/dev/project-hunter/.claude/state/r68/preregistro.md:95) não estabelecem a intercambialidade necessária.

**Cenário de falha:** o sinal dispara em sequências durante episódios de tendência ou volatilidade. Embaralhá-lo dentro do dia transforma sequências em entradas dispersas, alterando a distribuição do nulo. O observado pode parecer excepcional apenas porque o controle perdeu essa estrutura.

Manter a contagem diária não preserva autocorrelação, dependência entre mercados ou composição horária — especialmente relevante para P5.

Minha recomendação é testar diretamente os contrastes de expectativa com **bootstrap temporal conjunto, centrado sob o nulo**, sob hipóteses explícitas de dependência fraca/estabilidade. Manter seleção aleatória como diagnóstico, sem atribuir-lhe automaticamente um p-valor válido.

Deslocamentos circulares ou permutações de blocos também exigem justificativa: não são consertos universais. Podem preservar certas dependências e destruir sazonalidade ou alinhamento com regimes.

---

**5. Congelar o algoritmo de seleção dos limiares, não apenas a grade.**

A otimização das [linhas 76–85](C:/dev/project-hunter/.claude/state/r68/preregistro.md:76) é frágil, **mas ajustar exclusivamente no treino não invalida um teste futuro intacto**. Não é obrigatório abandonar o ajuste.

**Cenário de falha:** um limiar gera duas operações, uma excepcionalmente positiva, e vence pela média. Outro gera centenas de operações mais estáveis. Sem regras adicionais, o treino escolhe ruído e o resultado depende de detalhes decididos durante a execução.

Faltam definições prévias:

- Limiar comum ao painel ou específico por mercado.
- Janela e população usadas para `σ`.
- Mínimo de operações e de blocos temporais com entradas.
- Desempate, ausência de candidato elegível e caso de zero operações.
- Ordenação das horas de P5 e tratamento das horas ausentes.
- Warm-up e tratamento de denominadores nulos.

Em 240 minutos, 14 dias contêm só **84 barras por mercado**, antes de lacunas e warm-up. P3 pede 60 barras anteriores. P5 encontra apenas **seis horários distintos** na grade de quatro horas; `k=12` precisa de definição explícita. Isso decorre da grade e regras nas [linhas 28, 71 e 77](C:/dev/project-hunter/.claude/state/r68/preregistro.md:28).

Para esta primeira investigação, eu prefiro **um limiar fixo por preditor como análise primária**, com a seleção adaptativa como análise secundária previamente especificada. Se mantiver a adaptativa como primária, o objeto testado é o algoritmo inteiro de treinamento e seleção.

Subtrair o mesmo custo constante de todas as operações não muda o ranking dos limiares pela média; o principal problema aqui é variância e seleção, não o `0,14%` usado no treino.

---

**6. Fechar antecipação nos rótulos e distinguir fechamento de disponibilidade e execução.**

O guarda das [linhas 33–41](C:/dev/project-hunter/.claude/state/r68/preregistro.md:33) cobre timestamps das features. Não cobre sozinho o treinamento nem garante compra ao preço de fechamento.

**Cenário de falha:** uma decisão de treino ocorre antes da fronteira, mas seu retorno futuro termina dentro do teste. A seleção de `θ` incorpora parte do período que deveria avaliar.

Exigir que **todo rótulo usado no ajuste tenha terminado e esteja disponível antes do ajuste**. Features podem usar histórico anterior à fronteira; o problema é usar resultados ainda futuros.

Outro cenário: a estratégia usa a vela final para decidir e recebe execução no fechamento que acabou de observar. Uma vantagem curta desaparece durante publicação, cálculo e envio.

Definir entrada e saída posteriores à disponibilidade do sinal, com atraso e preço de execução explícitos. Se só houver candles históricos, chamar close-to-close de **proxy de retorno**, não execução demonstrada. `is_final` hoje também não prova que uma vela recuperada posteriormente estava disponível naquele instante.

---

**7. Alinhar universo, moeda e custo com a pergunta sobre a mesa.**

U2 contém perpétuos e apenas oito componentes de U1, conforme as [linhas 16–24](C:/dev/project-hunter/.claude/state/r68/preregistro.md:16). A confirmação exige lucro a 0,14%; 0,54% fica fora do aceite nas [linhas 102–108](C:/dev/project-hunter/.claude/state/r68/preregistro.md:102).

**Cenário de falha:** retorno bruto médio entre 0,30% e 0,54% passa pelos custos de 0,14% e 0,30%, mas perde dinheiro no bilhete cujo custo integral é 0,54%. Ainda assim recebe “confirma”.

Para responder à mesa de 0,05 SOL, o custo integral aplicável deve integrar o teste primário; custos menores podem responder a cenários separados. A hipótese de custo fixo das [linhas 53–56](C:/dev/project-hunter/.claude/state/r68/preregistro.md:53) precisa permanecer identificada como hipótese, incluindo tratamento de falhas, impacto e despesas recuperáveis.

Também é indispensável escolher o **numerário**. Se o objetivo é terminar com mais SOL, retorno token/USDT não basta:

\[
1+r_{\text{token/SOL}}
=\frac{1+r_{\text{token/USDT}}}{1+r_{\text{SOL/USDT}}}.
\]

**Cenário de falha:** o token sobe em dólares, mas menos que SOL. O estudo registra ganho, enquanto comprar e vender o token reduz o saldo em SOL.

Conclusão possível com os dados propostos: “vantagem no proxy de perpétuos sob custos assumidos”. Transferência para spot exige validação da população e dos preços executáveis. Definir fluxos monetários em `Decimal`, UTC e custos sem dupla contagem.

---

**8. Corrigir seleção da família e multiplicidade antes de chamar uma célula de confirmada.**

BH incide apenas sobre horizontes sobreviventes nas [linhas 97–98](C:/dev/project-hunter/.claude/state/r68/preregistro.md:97). Mas A usa a distribuição dos mesmos retornos que depois entram na avaliação.

**Cenário de falha:** uma realização particularmente volátil faz um horizonte sobreviver e favorece resultados extremos em B. A seleção usou o teste, mas o ajuste considera somente os sobreviventes.

Eu removeria o filtro e congelaria as **30 células**. BH controla proporção esperada de falsas descobertas sob suas condições; não significa que a probabilidade de qualquer falso vencedor seja inferior a 5%.

Para o objetivo “encontrar pelo menos uma vantagem”, prefiro controle familiar: **Holm sobre p-valores válidos**, ou Romano–Wolf com reamostragem conjunta corretamente especificada. Este último considera a dependência entre estatísticas: [Romano e Wolf](https://onlinelibrary.wiley.com/doi/10.1111/j.1468-0262.2005.00615.x).

Predefinir também quais subgrupos podem confirmar. U1 e U3 não são replicações independentes quando compartilham mercados e datas com U2.

---

**9. Especificar comparadores, perdas de cobertura e condição de refutação.**

“Bate sempre long” e “moeda ao ar com mesma taxa” estão nas [linhas 91–92 e 107](C:/dev/project-hunter/.claude/state/r68/preregistro.md:91), mas faltam pesos e população comparável.

**Cenário de falha:** o sinal opera principalmente num ativo que subiu; o benchmark mistura todos os ativos igualmente. O estudo atribui ao timing uma diferença causada pela composição da carteira.

Comparar na mesma elegibilidade de dados e declarar ponderação por mercado, exposição, frequência e tratamento de entradas simultâneas. Média por operação não demonstra rendimento de uma mesa com capital limitado.

Além disso, barras incompletas são descartadas nas [linhas 31–32](C:/dev/project-hunter/.claude/state/r68/preregistro.md:31).

**Cenário de falha:** uma operação tem entrada válida, mas perde o dado de saída durante um episódio adverso. Excluí-la silenciosamente melhora a média. Separar inelegibilidade conhecida antes da entrada de desfecho ausente depois dela; publicar censura e sensibilidade.

Por fim, a [linha 110](C:/dev/project-hunter/.claude/state/r68/preregistro.md:110) distingue corretamente não confirmação de refutação, mas falta uma regra para encerrar a hipótese:

- Limite inferior ajustado acima de zero: evidência favorável no escopo definido.
- Limite superior abaixo do ganho mínimo economicamente relevante, fixado antes: evidência contra essa vantagem mínima.
- Intervalo atravessando esses limites: inconclusivo.

Sem ganho mínimo, horizonte de avaliação e regra de parada, qualquer fracasso pode virar “precisamos de mais dados”. Nenhum resultado desses refuta toda previsibilidade possível.

**NICE-TO-HAVE**

- Reportar contribuição por mercado, dobra e dia, além de concentração nas maiores operações.
- Mostrar estabilidade entre limiares vizinhos sem escolher outro vencedor depois.
- Apresentar frequência, exposição e retorno por tempo ao lado da média por operação.
- Publicar datas exatas, cobertura, hash do snapshot, seeds e registro de todas as tentativas.
- Tratar a reconciliação com R63 como comparação contextual: famílias semelhantes com saídas distintas não precisam reproduzir o mesmo sinal de resultado ([linhas 114–117](C:/dev/project-hunter/.claude/state/r68/preregistro.md:114)).

**O QUE EU FARIA DIFERENTE**

Manteria A descritiva; congelaria as 30 células, numerário, custo integral, execução e algoritmo; avaliaria o walk-forward sem seleção pelo teste; faria inferência temporal conjunta e controle familiar.

Usaria o histórico para identificar candidatas e reservaria uma avaliação prospectiva, com prazo fixo, para a conclusão sobre a mesa. Reutilizar um período já explorado em outros estudos exige declarar essa exposição prévia.

**CONCORDO COM**

Barras completas e finais, grade temporal explícita e teste deliberadamente antecipador são boas bases ([linhas 28–38](C:/dev/project-hunter/.claude/state/r68/preregistro.md:28)). Também concordo com avaliação temporal, comparação contra zero e benchmark, e proibição de ajustes após observar o teste ([linhas 82–110](C:/dev/project-hunter/.claude/state/r68/preregistro.md:82)).

**OBSIDIAN**

- **Revisoes-Astra/R68 — revisão do pré-registro:** registrar os bloqueios e a formulação econômica corrigida.
- **O walk-forward que não temos e o nulo que nunca calculamos:** incorporar dependência temporal conjunta e distinção entre benchmark aleatório e permutação válida.
- **Strategy Performance:** distinguir retorno por operação, retorno em SOL e desempenho realizável da mesa.
- **Diário — 2026-09-23:** registrar revisão anterior à execução e a versão efetivamente congelada do protocolo.