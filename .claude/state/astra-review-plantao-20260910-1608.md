## RESUMO

**Eu faria D-P17 primeiro e testaria H-P18 somente após torná-la causal.** A dispersão permite investigar se o contexto transversal acrescenta informação ao BTC. **H-P17 merece protocolo congelado agora, mas permanece painel com ~10 eventos.** Posicionamento fica descritivo.

Parecer como `quant-engineer`, em modo OPINIÃO: nenhuma alteração ou commit.

## ARQUIVOS

Nenhum criado ou modificado. Base principal: [rascunho do run 6](C:/dev/project-hunter/.claude/state/plantao/2026-09-10-1608-lane2.md:23), hipóteses anteriores e EXP-0025/0026.

## TESTES

Não rodei testes, SQL ou replay; portanto, **não medi expectancy nem poder estatístico empírico**.

Conferências realizadas:

- O [BLS confirma](https://www.bls.gov/news.release/ppi.nr0.htm) PPI de **+0,4% m/m e +5,4% a/a**. O [calendário oficial](https://www.bls.gov/schedule/2026/09_sched.htm) confirma CPI em **11/09, 08:30 ET = 12:30Z**.
- Recalculando os números fornecidos: mediana dos 16 = **−4,80%**, entre **DOGE −5,12% e XRP −4,48%**; OI = **+1,959%**.
- Não reproduzi os snapshots históricos da Binance, liquidações, FedWatch ou opções. O comunicado do ECB não abriu nesta consulta.

## MUST-FIX

**1. H-P18 atual contém look-ahead se aplicada às entradas do próprio dia.**

O [rascunho](C:/dev/project-hunter/.claude/state/plantao/2026-09-10-1608-lane2.md:36) usa retorno diário completo. Cenário de falha: às 13:00Z o mercado ainda está estável; cai às 22:00Z; o replay classifica retroativamente a entrada das 13:00Z como “dia de amplitude negativa”. Isso identifica perdas com informação futura.

Minha especificação preferida:

> Em cada decisão no corte `t`, calcular, para cada mercado, `r24h(t) = close(t)/close(t−24h) − 1`, usando apenas fechamentos finais já disponíveis. Marcar a célula quando a mediana dos 16 for `< −3%` e o retorno equivalente do BTC for `> −2%`.

Às **13:00Z**, usa-se a janela encerrada às 13:00Z, depois de recebido seu fechamento; se ele ainda não estiver disponível, o rótulo aguarda. **Nenhum snapshot das 19:10Z entra nessa decisão.** O rótulo fica congelado por aposta, mesmo que mude depois.

Se quiser um rótulo **diário fixo**, use o último dia completo: às 13:00Z de 10/09, o retorno encerrado às 00:00Z de 10/09. É causal, mas testa persistência do estado anterior, outra pergunta.

**2. “Separa mais que BTC” precisa de contraste definido.**

Comparar a célula conjunta com “todos os demais” mistura amplitude e BTC. Eu mostraria quatro células:

| | BTC > −2% | BTC ≤ −2% |
|---|---|---|
| Mediana < −3% | Discordância de interesse | Queda conjunta |
| Mediana ≥ −3% | Controle principal | Discordância inversa |

O contraste primário seria **expectancy da discordância menos expectancy do controle principal**, dentro de BTC brando. Para dizer que amplitude acrescenta informação ao BTC, compararia também um modelo BTC-only com BTC+amplitude em período reservado, com métrica fixada antes.

Cenário de falha: a célula conjunta perde porque concentra certos meses ou retornos de BTC próximos de −2%; atribuímos tudo à amplitude.

Os cortes escolhidos após observar hoje são **pré-fixados para a próxima avaliação**, não independentes da descoberta. Os 90 dias já explorados continuam exploração. H-P18 também deve entrar na família da H-P8/H-P10, já registradas em [Hipóteses do plantão](C:/dev/project-hunter/obsidian/00-INBOX/Hipoteses-do-plantao.md:25).

**3. H-P17: quatro barras não multiplicam eventos independentes.**

Dez prints fornecem aproximadamente dez grupos de choque, não quarenta observações independentes — muito menos quarenta vezes dezesseis mercados. Alguns prints podem não produzir nenhuma aposta elegível.

**Existe chance de detectar um efeito enorme e consistente; não há base para prometer detectar um efeito moderado.** Como referência matemática idealizada, com dez diferenças evento–controle independentes e aproximadamente normais, teste bilateral a 5% e poder de 80%, o efeito detectável fica perto de **0,89 desvio-padrão dessas diferenças**. Com vinte, aproximadamente **0,63**. São aproximações otimistas, não poder medido do Lab; dependência, caudas e multiplicidade pioram isso.

Portanto:

- **Agora:** painel, contagem de eventos com apostas e estimativas de incerteza.
- **Depois:** poder calculado para uma diferença mínima relevante em R, com dependência preservada.
- **≥20 eventos:** marco de revisão, não certificado de suficiência. A régua editorial exige também **100 outcomes e 30 dias**, conforme [SHADOW-LAB.md](C:/dev/project-hunter/docs/plans/SHADOW-LAB.md:19).

“IC inclui zero” significa **inconclusivo**, não refutação. Para excluir uma perda economicamente relevante, precisamos definir essa perda mínima antes e verificar se o intervalo a exclui.

**4. H-P17 precisa resolver o relógio da decisão.**

As barras Binance são identificadas pela abertura: 12:30, 12:45, 13:00 e 13:15 fecham às **12:45, 13:00, 13:15 e 13:30**. Escolher quatro decisões às 12:30–13:15 testa outra janela.

Cenário de falha: atribuir a queda da barra iniciada às 12:30 a uma decisão tomada às 12:30, antes de conhecer essa barra. A estratégia agrega pelo corte `source_bar_close`: [mean_reversion_v1.py:169](C:/dev/project-hunter/packages/core/hunter_core/strategies/mean_reversion_v1.py:169).

Eu definiria tudo relativamente ao horário oficial de cada evento, inclusive horário de verão. Separaria **novas entradas após o print** de **posições anteriores expostas ao print**.

**5. O item de posicionamento contém duas inferências incorretas.**

- **OI subindo com preço caindo não demonstra o lado ausente do detector.** Ele olha `open_interest_change_1h` com `UP`, não a direção do preço: [detectors.py:177](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/detectors.py:177). `UP` significa desvio positivo perante a baseline: [severity.py:107](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/severity.py:107). Cenário de falha: justificar um detector bilateral com um episódio que o lado existente já poderia reconhecer. O painel continua útil; essa justificativa cai.
- **Funding pequeno no snapshot não prova custo realizado pequeno nem pouca alavancagem.** É preciso funding dos settlements atravessados por cada posição, normalizado pelo risco inicial. A [documentação da Binance](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) distingue a taxa mais recente e o próximo settlement. Cenário de falha: declarar diferença líquido–ex-funding próxima de zero sem apurar as apostas.

## NICE-TO-HAVE

Correções de linguagem que reduzem hype:

- US$190 mi e US$484 mi têm universos/janelas distintos; não formam uma faixa de estimativas do mesmo total.
- “Volume 8–9×” precisa de denominador fixo, não uma faixa de barras anteriores.
- Uma vela negativa não prova que a estratégia emitiu sinal, entrou ou perdeu. Conferir decisões e outcomes antes de chamar o episódio de falha da regra.
- BTC −1,5% não demonstra que o classificador real estava “brando” ou errado.
- Max pain não é alvo de preço; put/call de OI não revela intenção direcional líquida.
- ETF publicado depois do fechamento pode ser variável causal **após sua disponibilidade**. Chamá-lo de “regime” não resolve nem cria causalidade.
- “Regra de agenda” continua sendo restrição de elegibilidade se bloquear entradas; exige validação como qualquer outra.

## O QUE EU FARIA DIFERENTE

**D-P17 → H-P18 causal → H-P17 descritiva → posicionamento.**

No D-P17, mediria apostas únicas por mercado, com ZEC dentro/fora e sensibilidade retirando cada outro mercado. Fixaria a regra de representação das versões antes de olhar R; separaria bruto, execução e funding, com outcomes maturados e cobertura explícita.

Na H-P18, preservaria todos os mercados simultâneos nos blocos temporais e verificaria dependência entre dias: janelas móveis de 24 horas se sobrepõem. **Dez dias por célula não garantem dez episódios independentes.**

Na H-P17, usaria controles na mesma hora, dias úteis comparáveis e calendário conhecido previamente. Separaria CPI/PPI/payroll descritivamente, sem abrir três testes confirmatórios frágeis.

## CONCORDO COM

Registrar calendário antes do próximo evento; usar aposta única; começar pelo diagnóstico com/sem ZEC; manter posicionamento como painel; não alterar a estratégia a partir dessas manchetes.

**Congelar H-P17 agora é útil. Promovê-la agora a regra não é sustentado pela amostra.**

## OBSIDIAN

- **Hipóteses do plantão** — registrar H-P18 causal, contraste incremental ao BTC e H-P17 com janela decisória, efeito mínimo e amostra por evento.
- **Plantão de mercado — 2026-09-10** — corrigir mediana, inferência sobre OI e afirmações de funding, regime e desempenho ainda não medidos.
- **KB-0025 — O nosso detector de open interest só olha para cima** — esclarecer que o lado se refere ao desvio do OI, independentemente da direção do preço.
- **KB-0074 — Risco operacional: as regras de não operar quando** — distinguir indisponibilidade operacional de restrição de agenda baseada em hipótese de rentabilidade.
- **Revisões Astra — Plantão run 6** — guardar este parecer e vinculá-lo a H-P2, H-P5, H-P8/H-P10 e EXP-0025/0026.