**RESUMO**

**Manteria D_ts, o horizonte de 14 dias e Holm sobre D_ts/D_cs. Não congelaria ainda o rascunho:** há problemas corrigíveis na fórmula, na execução por deslistagem, nos custos e na definição do veredito. O desenho tem **baixo poder para +0,25 p.p./semana**, mas trocar para painel moeda-semana não resolve isso automaticamente.

A leitura da literatura é cuidadosa ao distinguir versões e resumos, porém exagera a generalidade da evidência favorável e simplifica o artigo de 2025. Revisão feita como `quant-engineer`, em modo OPINIÃO.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Nenhum commit, consulta ao banco ou acesso a preços nossos.

O rascunho contém os seis campos exigidos pelo carregador. O campo adicional `registro` não integra o objeto retornado: a data precisará acompanhar explicitamente o protocolo executável. Isso decorre de [queue.py:32](C:/dev/project-hunter/infra/research/queue.py:32) e [queue.py:83](C:/dev/project-hunter/infra/research/queue.py:83). Compatibilidade inspecionada, não testada por execução.

**TESTES**

Não rodei pytest/lint: esta é uma revisão documental. Executei em PowerShell as contas de planejamento, usando `SE = 5/√n`, meio-IC `1,96 × SE` e efeito detectável com 80% de poder `(z_crítico + 0,8416) × SE`. Saída real:

```text
n=350; SE=0,2673 pp; meio_IC95=0,5238 pp; MDE80_z1.96=0,7488 pp; MDE80_z2.2414=0,8240 pp
n=400; SE=0,2500 pp; meio_IC95=0,4900 pp; MDE80_z1.96=0,7004 pp; MDE80_z2.2414=0,7708 pp
N80_MRE0.25_z1.96=3140; N80_MRE0.25_z2.2414=3802
Taxas fixas ida_volta sobre 0.05 SOL=4,00%; sobre 1 SOL=0,20%
```

São contas sob **normalidade e independência**, com desvio assumido, não resultados empíricos. A segunda coluna de MDE usa o primeiro limiar de Holm para dois testes **bilaterais**.

Conferi o texto integral de Grobys–Sapkota e Grobys et al., além da versão de abril/2019 de Liu–Tsyvinski–Wu disponibilizada por Yale. O PDF NBER de Liu–Tsyvinski e o SSRN de Arefev devolveram 403; não certifico todos os números desses dois trabalhos.

**MUST-FIX**

1. **Escrever a fórmula completa do retorno.**

   Na [KB-0164:126](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0164-momentum-semanal-em-cripto-grande.md:126), o parêntese define uma razão de fechamentos, sem subtrair 1. Escrever explicitamente:

   \[
   m_{i,T}=C_{i,d}/C_{i,d-14}-1,\qquad
   w^{TS}_{i,T}=\mathbf1(m_{i,T}>0)/N_T.
   \]

   Exigir 14 **dias de calendário**, não apenas 14 registros disponíveis.

   **Cenário de falha:** a implementação literal considera toda razão positiva, compra todas as moedas e produz TS ≈ EW. Com lacunas, “14 velas” também pode virar um horizonte maior que 14 dias.

2. **Substituir “sai no último fechamento disponível” por uma regra executável.**

   Essa saída está na [KB-0164:127](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0164-momentum-semanal-em-cripto-grande.md:127). Só se sabe retrospectivamente que determinado fechamento foi o último. A lista de deslistados, embora necessária, não corrige isso.

   Para deslistagem anunciada, usar anúncio disponível naquela data, prazo e regra de liquidação predefinidos. Para suspensão inesperada, preservar a posição e aplicar uma regra explícita de recuperação/perda; sem informação suficiente, declarar identificação parcial ou limite de dado. Um desconto arbitrário de 30% não garante conservadorismo.

   **Cenário de falha:** negociações param abruptamente após a última cotação. O backtest vende nessa cotação; a carteira real fica presa e recupera zero.

3. **Fechar o contrato de dados ponto-no-tempo e de disponibilidade.**

   As cláusulas da [KB-0164:105](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0164-momentum-semanal-em-cripto-grande.md:105) são necessárias, mas faltam regras para:

   - Exclusões por **identidade e classificação disponíveis em T**, incluindo mudanças de ticker e redenominações. Congelar hoje uma lista não a torna histórica.
   - Volume: soma de volume em **USDT**, janela exata, desempates, barras ausentes versus volume zero.
   - Lacunas posteriores à compra: não excluir a moeda nem redistribuir seu peso retrospectivamente.
   - Distinguir fechamento da barra de sua disponibilidade para calcular e enviar a ordem.

   **Cenários de falha:** uma stablecoin desancorada deixa de ser classificada como stable hoje e entra retrospectivamente no universo; uma moeda em colapso desaparece do arquivo e sua perda é descartada; ou a estratégia usa o fechamento de 23:59:59.999 para receber, sem latência, o primeiro negócio de 00:00.

   Com apenas dados diários, eu escolheria uma destas convenções antes dos retornos: sinal com uma barra adicional de atraso e execução na abertura T; ou sinal até T e execução no fechamento T. A abertura imediata pode continuar como aproximação idealizada, mas não como prova de execução sem antecipação.

4. **Corrigir a atribuição do custo à KB-0145 e especificar a contabilidade do giro.**

   A [KB-0164:113](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0164-momentum-semanal-em-cripto-grande.md:113) importa apenas 0,30% ida e volta. A [KB-0145:44](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0145-binance-como-sinal-solana-como-execucao.md:44) assume **0,30% mais 0,001 SOL por perna**. Não estou afirmando que essa taxa fixa continua correta; afirmo que ela foi omitida da referência utilizada.

   Congelar capital, tamanho mínimo e custos fixos, ou declarar que o teste considera somente custos proporcionais e não demonstra viabilidade na Jupiter. Calcular giro contra os **pesos efetivos antes do rebalanceamento**, após valorização, incluindo vendas de ativos que saem do universo.

   **Cenário de falha:** com a hipótese antiga de taxa fixa, uma posição de 0,05 SOL paga 4% ida e volta só nessa parcela. Outro erro possível: pesos-alvo continuam em 5%, mas os pesos reais mudaram; comparar alvo novo com alvo antigo atribui custo zero a operações necessárias.

   Também corrigiria “o giro de 20 posições soma”: custos proporcionais são ponderados pelo capital; não se multiplica automaticamente 0,30% por 20.

5. **Congelar exatamente a inferência e o significado de “sobrevive”.**

   A [KB-0164:128](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0164-momentum-semanal-em-cripto-grande.md:128) ainda deixa escolhas que alteram o veredito: teste unilateral/bilateral, tipo de bootstrap em blocos, construção do IC e quais condições devem persistir em cada estresse.

   Minha recomendação: testar a média da série semanal **pareada** \(d_t=r^{TS}_t-r^{EW}_t\), com blocos móveis contíguos de oito semanas, procedimento de borda explícito, IC marginal identificado como tal e p unilateral centrado sob \(H_0:D\leq0\). Reamostrar as mesmas semanas para todos os braços.

   **Cenário de falha:** após observar os resultados, “sobrevive” passa a significar apenas D positivo numa sensibilidade, mas exige significância em outra. Ou reamostram-se TS e EW independentemente, destruindo o pareamento e mudando o erro-padrão.

6. **Resolver a diferença entre MRE de +0,25 e refutação abaixo de +0,10.**

   A [KB-0164:129](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0164-momentum-semanal-em-cripto-grande.md:129) diverge da convenção de refutar o **tamanho previsto** quando o limite superior fica abaixo do MRE, em [RESEARCH.md:66](C:/dev/project-hunter/docs/RESEARCH.md:66).

   **Cenário de falha:** IC [+0,12; +0,20] exclui o efeito previsto de +0,25, mas o rascunho responde apenas NÃO CONFIRMA.

   Eu usaria `U < +0,25 → REFUTA o tamanho previsto`. Se +0,10 for um segundo piso econômico para abandono, nomeá-lo separadamente. Isso não obriga a abandonar todo efeito menor.

7. **Reequilibrar a síntese da evidência.**

   Na [KB-0164:28](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0164-momentum-semanal-em-cripto-grande.md:28), trocar “não há estudo aberto” por **“não encontramos entre as fontes consultadas”**. E não tratar os estudos recentes de carteiras compradas/vendidas como refutação direta da regra TS só-compra.

   O resumo de 2025 acerta 0,90%, 1,74%, o crash de aproximadamente −255% e 1,51% após retirar o evento. Entretanto, omite a melhora das estratégias com gestão de volatilidade nas grandes e a limitação de dados faltantes remanescentes. O artigo é evidência de fragilidade e risco de cauda, com resultados mistos. [Grobys et al., 2025](https://link.springer.com/article/10.1007/s11408-025-00474-9).

   **Cenário de falha:** a próxima decisão passa a tratar “momentum morreu depois de 2020” como fato estabelecido, embora parte importante do resultado negativo venha de uma posição vendida que a H-024 não terá.

**NICE-TO-HAVE**

- Em Grobys–Sapkota, escrever **“não significativo a 5%”**: os t de 1,65/1,84/0,41 estão corretos, mas existe evidência marginal nos horizontes maiores. A amostra também exige negociação iniciada antes do fim de 2014. [Artigo de 2019](https://osuva.uwasa.fi/server/api/core/bitstreams/ffee5cb1-92a8-443e-a117-cbaacd8a1028/content).
- Os spreads 2,7/3,3/4,1/2,5% e a comparação 4,2% versus 0,6% aparecem na versão de Liu–Tsyvinski–Wu consultada. “Grandes” significa acima da mediana daquela amostra, não equivalência ao top-20 líquido da Binance. [Versão dos autores, 2019](https://cowles.yale.edu/sites/default/files/2022-10/LiuTsyvinskiWu2019%20COMMON%20RISK%20FACTORS.pdf).
- Não encontrei erro numérico demonstrável nos valores de Liu–Tsyvinski; a impossibilidade de conferir o PDF impede uma certificação completa. Manter a distinção entre working paper e publicação.
- Fixar arredondamento do tercil, desempates e definição de N quando houver 15–19 elegíveis. Chamar o universo de “mais negociadas na Binance”, pois top-volume não garante grande capitalização.

**O QUE EU FARIA DIFERENTE**

**Sobre a primária:** manteria D_ts de 14 dias. Ela responde se a regra compra/caixa melhora o retorno líquido da mesma cesta. BTC como primária misturaria timing com seleção de moedas. Não vejo base para promover 7 ou 28 dias a principal; 14 dias é uma escolha de desenho, não um ótimo estabelecido pela literatura.

A expressão “mede só o timing” merece precisão. Ignorando custos e com caixa rendendo zero:

\[
d_t=-\frac1{N_t}\sum_{i:m_{i,t}\leq0}r_{i,t+1}.
\]

Portanto, o contraste mede o resultado de **evitar os ativos de sinal negativo**, com mudança de exposição. Não demonstra sozinho previsibilidade ajustada ao risco. Uma carteira de exposição constante comparável pode entrar como diagnóstico, sem virar outra porta de confirmação.

**Sobre poder:** a conta de ±0,5 p.p. é coerente como aproximação IID; não é previsão garantida do IC por blocos. Sob essas premissas, 80% de poder corresponde a efeitos próximos de **0,70–0,82 p.p./semana**, antes das demais exigências. Para +0,25 seriam aproximadamente **3.140–3.802 semanas independentes**.

Eu manteria o MRE econômico, mas apresentaria o estudo como capaz principalmente de detectar efeitos grandes. Não aumentaria o MRE apenas para acomodar a amostra.

**Não substituiria pela regressão em painel para obter significância.** O portfólio já agrega a diversificação transversal. Cluster apenas por semana permite dependência entre moedas naquele instante, mas não resolve dependência entre semanas. Um painel pode investigar associação e heterogeneidade; altera o estimando e exige tratamento temporal adequado.

O bloco de oito semanas é um ponto de partida defensável, não uma garantia. Predefiniria sensibilidades de quatro e dezesseis semanas, sem escolher depois a que produz o melhor p.

**Sobre as condições:** não tornam confirmação matematicamente impossível, mas tornam a hipótese muito mais exigente que “D_ts positivo e economicamente relevante”. Eu manteria na confirmação D_ts, MRE, IC/p com Holm, nível positivo e patamar, respeitando a convenção da casa. Publicaria fase, períodos e estresses em linhas separadas, com consequências explícitas para seguir ao papel.

Sharpe ≥ BTC e significância sob custo de 0,50% por perna não são necessários para demonstrar o contraste primário. Podem ser requisitos operacionais, se essa for a decisão prévia. Falhar neles não deve virar afirmação de inexistência do efeito.

As sete fases são fortemente dependentes; “5/7” é diagnóstico de estabilidade, não sete replicações. O corte de 2022 produz dois períodos, não necessariamente duas metades. No atraso de um dia, deslocar **todas** as execuções e carregar as posições anteriores até a execução seguinte: não reduzir silenciosamente cada holding para seis dias.

**CONCORDO COM**

- Universo ponto-no-tempo com deslistados e interrupção por limite de dado quando não for reconstruível.
- Mapa atual da Jupiter apenas descritivo; confirmação na Binance ainda exige validação prospectiva de execução.
- EW no mesmo universo como controle principal; BTC e caixa como referências complementares.
- Holm para as duas hipóteses e proibição de promover o melhor horizonte depois dos resultados.
- Não confundir ausência de poder com refutação.
- Abrir uma frente semanal: a lacuna de horizontes maiores está registrada na [KB-0149:100](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0149-o-que-a-mesa-real-ensinou.md:100), e o resultado da H-023 não testa esta regra semanal ([Fila:279](<C:/dev/project-hunter/obsidian/11-KNOWLEDGE/Fila de Hipoteses.md:279>)).

**OBSIDIAN**

- **KB-0164 — Momentum semanal em cripto grande:** corrigir fórmula, evidência, execução, custos, inferência e alcance do poder.
- **Fila de Hipóteses:** registrar H-024 somente após fechar essas convenções; distinguir MRE de eventual piso de abandono.
- **KB-0145 — Binance como sinal, Solana como execução:** esclarecer a relação entre custo cotado percentual, taxas fixas assumidas e tamanho da posição.
- **Revisões-Astra — H-024 momentum semanal:** registrar este parecer, as correções aceitas e eventuais divergências antes dos retornos.