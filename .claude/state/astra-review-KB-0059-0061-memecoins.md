**RESUMO**

A inferência sobre cadência **sobrevive como explicação plausível, não como identificação causal**. Beta alto com R² baixo é perfeitamente coerente, mas não significa “acompanha poucas vezes”. O `D-MEME-PICO` é recuperável como descrição de trajetórias condicionadas ao sinal.

Eu derrubaria por completo esta passagem: **“detectam em 25 segundos, portanto nossas barras de 5 minutos só observam o que sobrou”**. Tempo de detecção não determina duração do evento nem posição da entrada em relação ao pico.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisão no papel de `quant-engineer`, em modo OPINIÃO.

**TESTES**

Não executei consultas na VPS nem suítes do projeto. Trato as tabelas como medições fornecidas por você; conferi a interpretação, trechos de SQL, código e fontes externas.

Aritmética executada em PowerShell:

```text
[decimal]0.5 / 51 * 100
0,9803921568627450980392156900

[decimal]7 / 51 * 100
13,725490196078431372549019610
```

**MUST-FIX**

1. **KB-0059: trocar “é cadência, não sentimento” por “a comparação está confundida por cadência”.**

   A conclusão categórica aparece em [KB-0059:53](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0059-funding-em-memes-a-cadencia-antes-do-sentimento.md:53). As contagens são compatíveis com sua explicação, mas não identificam a cadência de cada intervalo nem isolam o componente mecânico.

   A fórmula da Binance sustenta o mecanismo: o funding combina prêmio e juros, com amortecimento, e escala pelo intervalo. No trecho em que o amortecimento cancela o prêmio, taxas de 0,5 bps/4 h e 1 bps/8 h são compatíveis com o mesmo componente horário. Isso **não demonstra que os contratos observados estavam todos nesse trecho**, nem exclui diferenças de prêmio. [Documentação da Binance](https://www.binance.com/en/support/faq/detail/360033525031).

   **Cenário de falha:** um contrato muda de cadência durante a janela, ou tem cobertura incompleta; sua contagem total recebe o rótulo “4 h”, mas parte das taxas veio de outro intervalo. Atribuir toda a diferença à cadência apaga diferenças econômicas reais.

   Também retiraria “todo mundo comprado” ([KB-0059:78](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0059-funding-em-memes-a-cadencia-antes-do-sentimento.md:78)). Funding positivo identifica o sentido da transferência; todo contrato tem contraparte vendida.

2. **KB-0059: normalizar antes de comparar extremos e corrigir a ponderação.**

   Sua consulta agrega **liquidações**, não mercados com pesos iguais ([KB-0059:30](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0059-funding-em-memes-a-cadencia-antes-do-sentimento.md:30)). Contratos mais frequentes têm mais peso. Acrescentar uma coluna de cadência não corrige isso.

   Para cada liquidação \(k\) do mercado \(i\), usaria:

   \[
   q_{ik}=\frac{10.000\,f_{ik}}{\Delta h_{ik}}
   \quad\text{em bps/h}
   \]

   Aqui, \(\Delta h\) é o **intervalo efetivo daquele pagamento**, validado; um intervalo entre registros com uma cobrança ausente não serve automaticamente.

   Para comparar coortes, primeiro resumiria cada mercado:

   \[
   \bar q_i=\frac{\sum_k10.000\,f_{ik}}{\sum_k\Delta h_{ik}},
   \qquad
   \bar a_i=\frac{\sum_k10.000\,|f_{ik}|}{\sum_k\Delta h_{ik}}.
   \]

   Depois publicaria a distribuição entre mercados, com pesos iguais e cobertura temporal comparável. Para quantis das taxas horárias, declararia também a ponderação por duração.

   **Cenário de falha:** 0,8 bps a cada hora parece menos extremo por cobrança que 1 bps a cada 8 h, mas representa 6,4 vezes a taxa horária. Além disso, aparece oito vezes mais na amostra de eventos.

   Portanto, “menos extremo” ainda vale como descrição **por liquidação nesta janela**, não como conclusão normalizada sobre memes. A comparação de mínimos entre 21 e 150 mercados também favorece encontrar um extremo no grupo maior.

3. **KB-0060: retirar a tradução de R² em frequência de acompanhamento.**

   “Amplificam quando acompanham e, na maior parte do tempo, simplesmente não acompanham” não decorre dos coeficientes ([KB-0060:22](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0060-correlacao-com-o-btc-e-a-meme-season.md:22)).

   Numa regressão simples com intercepto:

   \[
   \beta=\rho\frac{\sigma_{\text{ativo}}}{\sigma_{\text{BTC}}},
   \qquad R^2=\rho^2.
   \]

   **Cenário de falha:** \(r_{\text{meme}}=2{,}8r_{\text{BTC}}+\varepsilon\), com resíduo grande e não correlacionado com BTC. A inclinação continua 2,8 e o R² pode ser 0,029, sem existir um estado “acompanha” alternando com outro “não acompanha”.

   Eu escreveria: **“Nesta janela, as coortes apresentam inclinações medianas semelhantes, mas a coorte B tem menor fração da variância explicada linearmente pelo BTC.”**

   “Dois comportamentos diferentes” é aceitável como descrição exploratória desse contraste. “Comportamentos opostos” e dois tipos estáveis de ativo não estão demonstrados. As medianas separadas tampouco descrevem necessariamente o mesmo mercado.

   Também não usaria R² de retorno para validar um classificador de regime: associação linear contemporânea e utilidade de um regime são perguntas diferentes ([KB-0060:76](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0060-correlacao-com-o-btc-e-a-meme-season.md:76)).

4. **KB-0060: Epps não torna 0,39 e 0,77 comparáveis.**

   A ressalva em [KB-0060:62](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0060-correlacao-com-o-btc-e-a-meme-season.md:62) explica um mecanismo possível, mas não atribui a ele a diferença. Assincronia e relações de defasagem podem produzir dependência da correlação em relação à frequência. [Estudo sobre a origem do efeito Epps](https://arxiv.org/abs/physics/0701110).

   **Cenário de falha:** a outra amostra contém moedas diferentes, outro regime e uma carteira agregada; sua correlação diária seria maior mesmo sem qualquer efeito Epps relevante.

   Eu retiraria **0,77–0,78** enquanto a fonte e a definição não forem verificadas. A página SSRN também não abriu nesta revisão. Manteria apenas: “Resultados em frequências diferentes não são diretamente comparáveis.”

   Para investigar Epps aqui: mesmos mercados, mesma janela, mesmos critérios de cobertura, múltiplas frequências. Com 42 h, não há amostra diária suficiente para a comparação pretendida.

5. **KB-0060: o SQL apresentado permite emparelhar retornos de durações diferentes.**

   Em [KB-0060:35](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0060-correlacao-com-o-btc-e-a-meme-season.md:35), `n1m = 15` filtra barras antes do `lag(cl)`, e o join com BTC usa somente o horário final.

   **Cenário de falha:** falta a barra de 10:15 de uma meme. Seu retorno às 10:30 passa a cobrir 30 minutos, enquanto o BTC cobre 15. O par entra na regressão e deixa de medir o objeto declarado.

   Exigiria intervalo anterior de exatamente 15 minutos e igualdade dos dois extremos temporais do par. Se a parte omitida do SQL já garante isso, basta publicá-la; o trecho atual não permite verificar. Não afirmo que houve gaps nos seus dados.

6. **KB-0061: corrigir a ponte entre literatura e instrumento.**

   A inferência central de [KB-0061:16](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos.md:16) não sobrevive. O artigo completo abriu em HTML: cerca de **900 eventos coletados**, **317 eventos Binance** na avaliação, F1 **94,5%** com blocos de **25 s** e validação cruzada de cinco partes. Também descreve movimentos de horas e diferencia crowd pumps. Esses números não estabelecem um prazo universal para detectar ou operar. [Artigo, seções 4 e 5](https://arxiv.org/html/2105.00733v2).

   **Cenário de falha:** um movimento continua por uma hora e a entrada ocorre após cinco minutos, antes do máximo. Sua conclusão categórica o declara impossível sem observar a trajetória.

   “Literalmente a mesma regra” também deve sair ([KB-0061:51](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos.md:51)). Fechamento acima do meio da barra não equivale a anomalia de preço contra histórico. Sua estratégia ainda limita o retorno a \(2\times ATR\), podendo rejeitar movimentos explosivos ([volume_anomaly_v1.py:150](C:/dev/project-hunter/packages/core/hunter_core/strategies/volume_anomaly_v1.py:150)).

7. **KB-0061: preservar o diagnóstico, mas definir sua janela e retirar a identificação de exaustão.**

   A ressalva final já reconhece seleção por volume e ambiguidade causal, mas contradiz “está comprando exaustão” no corpo ([KB-0061:77](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0061-pump-and-dump-o-detector-que-precisa-de-25-segundos.md:77)).

   O desenho precisa resolver:

   - **Seleção completa:** volume alto, fechamento forte e limite de retorno selecionam a trajetória. Controle aleatório genérico não isola esses efeitos.
   - **Janela assimétrica:** poucos minutos anteriores à entrada contra duas horas posteriores. Não existe referência automática de 50% antes/depois.
   - **Saída antecipada:** buscar o máximo até stop/alvo torna a janela dependente do resultado. O acompanhamento termina ao resolver a saída ([walker.py:171](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:171)); o diagnóstico precisa consultar as candles até o horizonte fixo, mesmo após a saída.
   - **Cobertura e maturação:** sinais recentes sem duas horas futuras e janelas com gaps precisam aparecer no denominador e como indisponíveis.
   - **Empates e resolução:** definir `high` versus `close`, máximos repetidos e minuto de entrada. OHLC de um minuto não fornece o segundo exato do pico.
   - **Dependência:** vários sinais podem compartilhar o mesmo movimento; não são observações independentes.

   **Cenário de falha:** um sinal atinge stop rapidamente, mas o preço faz novo máximo 40 minutos depois. Usar somente seu acompanhamento o classifica “depois do pico”; a janela fixa o classificaria “antes”.

   **Duas horas não são censura para “máximo dentro de duas horas”**, desde que a janela esteja completa. São uma limitação se você pretende inferir o pico do evento inteiro. Um máximo posterior pode mudar a classificação.

**NICE-TO-HAVE**

A auditoria de “medição versus inferência” também encontrou:

| Trecho | Correção |
|---|---|
| KB-0059, metadados: **229 mercados** | A tabela soma **200**; esclarecer se 229 é o universo anterior ao filtro. |
| KB-0059: **16 mercados em 4 h ou menos; 23 em 8 h; um em 1 h** | As contagens são medidas; as cadências são inferências enquanto não houver validação dos intervalos. |
| KB-0059: **“engole metade da diferença”** | A razão entre medianas foi medida; a parcela explicada causalmente não. |
| KB-0060: **154 de 200** | A regressão apresentada tem **148 + 4 = 152** mercados nesses grupos; além disso, uma mediana não classifica todos os integrantes. |
| KB-0060: **85% não explicado** | É transformação válida de \(1-R²\), como resumo por mercado; não mede frequência nem a variância de uma carteira. |
| KB-0061: **14,4 bps de deslocamento** | Se herdado como mediana absoluta, manter “absoluto”; não implica atraso adverso. |

Os números de **1% e 14% de R já estão corretamente rotulados como aritmética**, não como resultado medido, em [KB-0059:84](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0059-funding-em-memes-a-cadencia-antes-do-sentimento.md:84).

**O QUE EU FARIA DIFERENTE**

Manteria três diagnósticos estreitos:

- **Funding:** distribuição por mercado em bps/h e custo por acompanhamento somando pagamentos atravessados. Taxa horária é normalização, não cobrança proporcional: uma posição curta que atravessa o pagamento pode pagar a taxa inteira.
- **Beta:** distribuição conjunta de beta e R² por mercado, com pares contíguos e sensibilidade à retirada de blocos temporais. Retirar um mercado testa a mediana da coorte; retirar um intervalo testa o choque que domina sua regressão.
- **Pico:** máximo observado entre início da barra de referência e entrada + 2 h, com cobertura completa, independentemente da saída. Publicar antes/no minuto/depois, amplitude posterior e comparação condicionada à elegibilidade, volatilidade e liquidez. Validar prospectivamente qualquer hipótese surgida daí.

Quanto a R: **0,5/51 = 0,009804 R**, ou **0,9804% de 1 R**; **7/51 = 0,137255 R**, ou **13,7255%**. Está certo no exemplo. O custo exato depende do notional no pagamento e do risco daquele acompanhamento; 51 bps continua sendo denominador sintético, como a [KB-0038:58](C:/dev/project-hunter/obsidian/11-KNOWLEDGE/KB-0038-a-taxa-de-4-bps-nao-e-nem-maker-nem-taker.md:58) já explica.

**CONCORDO COM**

- Separar taxa liquidada de estimativa em formação.
- Investigar cadência antes de interpretar funding.
- Mostrar beta junto de R² e dispersão entre mercados.
- Tratar 42–45 h como descrição local, sem estabelecer meme season.
- Manter `D-MEME-PICO` exploratório e registrar a tentativa.
- Não transformar essas notas em novos braços de estratégia.

**OBSIDIAN**

- **KB-0059 — Funding em memes:** normalizar por intervalo e mercado; estreitar a atribuição causal e corrigir a contagem de mercados.
- **KB-0060 — Correlação com o BTC:** corrigir a leitura de R², os pares temporais, o denominador e a comparação externa.
- **KB-0061 — Pump-and-dump:** separar tempo de detecção de duração; atualizar a evidência do artigo e definir o diagnóstico com horizonte fixo.
- **EXP-0002 — Volume anomaly v1:** registrar que o diagnóstico de trajetória continua até duas horas mesmo após encerramento do acompanhamento.
- **Registro de Tentativas:** registrar população explorada, definição do máximo e controles antes da execução do diagnóstico.