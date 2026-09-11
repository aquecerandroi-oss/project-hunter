## RESUMO

**Eu faria primeiro o D-P23, com a régua causal retirada.** Ele responde à dúvida mais próxima do Lab: quanto movimento adicional aparece entre 80 e 240 minutos nas entradas já congeladas da mãe? Depois, enriqueceria o painel CPI; deixaria a extensão Kalshi/H-P18 em terceiro.

O diagnóstico pode orientar uma investigação futura. **Não pode concluir “a perda da filha é horizonte” nem justificar sua reabertura sozinho.** A aposentadoria da configuração testada continua defensável.

Papel assumido: `quant-engineer`. Parecer com ressalvas.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Nenhum commit.

## TESTES

Não executei testes, consultas ao banco nem o D-P23. Fiz inspeção estática e conferência das fontes primárias. Portanto, confirmo **viabilidade pelo contrato**, não cobertura efetiva das 542 entradas.

Os dois artigos arXiv abriram; a página da Block Scholes retornou `Internal Error`. Seus coeficientes são tratados abaixo como informações do rascunho, não como reconferidos.

## MUST-FIX

### 1. A régua 0,40/0,80 é arbitrária e não identifica a causa

Congelar limiares impede ajustá-los depois; **não lhes dá fundamento estatístico ou causal**.

Exemplo de falha: curva(80) = −0,01 ATR e curva(240) = +0,001 ATR produz razão −10. Sua regra declararia “horizonte”, embora o ganho terminal seja praticamente zero. Mesmo com denominador positivo estável, a curva da mãe nada determina sobre a trajetória das entradas diferentes da filha.

Além disso, o transporte mudou **ATR, tendência e horizonte**: tendência 1 h → 15 min, ATR 15 min → 5 min e horizonte 14.400 → 4.800 segundos. Isso está explicitado em [mean_reversion_m5_v1.py:27](C:/dev/project-hunter/packages/core/hunter_core/strategies/mean_reversion_m5_v1.py:27). “Grade” agrega várias mudanças.

Eu substituiria o veredito por:

- curva completa, com valores absolutos;
- **Δ pareado = média[retorno(240) − retorno(80)]**, com IC;
- razão apenas descritiva, se o denominador estiver suficientemente separado de zero;
- conclusão limitada a “há/não há evidência de acumulação adicional nas entradas da mãe”.

O bootstrap deve reamostrar os mesmos dias conjuntamente entre mercados e horizontes. As 20.000 reamostragens e a semente são adequadas para reprodução; não resolvem dependência entre dias nem falta de informação.

### 2. “Some em quatro horas” não significa “precisa de quatro horas para pagar”

Kitron compara **previsibilidade entre intervalos de amostragem**. Isso não é a trajetória acumulada de uma posição aberta pelo sinal de 15 minutos. A fonte não sustenta essa ponte. [Kitron & Wengrowicz, seção 3](https://arxiv.org/html/2608.21888v1#S3)

**Cenário de falha:** usar a ausência de previsibilidade em barras de quatro horas como justificativa para alongar a duração das posições.

Também não atribuiria peso à proximidade 3,1× versus 3,7×: mediana entre pares em bp e média por entrada em R, sob regras diferentes, não são uma replicação.

### 3. O MTM é factível, mas precisa da entrada correta e de cobertura medida

**Sim, há estrutura para fazê-lo sem novo replay de sinais.** Porém, para preservar a entrada histórica, eu usaria também `signal_outcomes`:

- `agent_signals` guarda direção e `supporting_features`: [agents.py:189](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents.py:189).
- O carregador recupera ATR congelado de `supporting_features.atr.value`: [load.py:136](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/replay/load.py:136).
- `signal_outcomes` guarda `virtual_entry` e `entry_ts`: [agents.py:232](C:/dev/project-hunter/packages/core/hunter_core/db/models/agents.py:232).
- `candles` oferece identidade por mercado, timeframe e abertura, fechamento e `is_final`: [market_data.py:46](C:/dev/project-hunter/packages/core/hunter_core/db/models/market_data.py:46).

**Cuidado com “bruto”:** a entrada virtual já incorpora spread/slippage; o walker entra pela abertura ajustada, não pelo fechamento do sinal. [walker.py:42](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/walker.py:42), [pricing.py:47](C:/dev/project-hunter/services/strategy-worker/hunter_strategy_worker/pricing.py:47).

Para movimento bruto, usaria:

`direção × (close em t+h − open da entrada) / ATR congelado`

Preservaria o instante e a elegibilidade históricos. Subtrair `virtual_entry` produziria uma curva que já contém fricção de entrada.

**Cenários de falha:** deslocar a entrada para `emitted_at`; usar o fechamento da barra que **abre** em t+h, acrescentando um minuto; excluir silenciosamente entradas sem preço em 240 minutos; comparar populações diferentes em cada ponto.

É necessário conferir os IDs da coorte, ATR válido e oito endpoints finais por entrada. Não preencher ausências com preço anterior. Para esse MTM sem barreiras, lacunas intermediárias não necessariamente invalidam um endpoint observado; precisam de tratamento diferente de uma simulação com stop/alvo.

### 4. Kalshi → célula de 24 h: hipótese nova, não previsão transportada

O salto troca simultaneamente:

- reprecificação observada por semana de calendário;
- volatilidade futura por retorno direcional;
- cinco dias por 24 horas;
- seis ativos por nosso universo de 16.

**Menor volatilidade futura não implica maior frequência de alts abaixo de −3% com BTC acima de −2%.** O sinal dessa previsão não decorre do paper.

Há ainda uma omissão relevante: BTC–Fed tem força em amostra, mas **MSFE fora da amostra de 1,009**, pior que o benchmark. Na correção BH, sobrevivem BTC–Fed e LINK–CPI, não todos os resultados destacados. [Mohanty & Krishnamachari, seções 5–6](https://arxiv.org/html/2604.01431v1)

**Cenário de falha:** carimbar “canal CPI” após observar mais discordância em três semanas, confundindo regime e calendário com mecanismo.

Pode medir a frequência, explicitamente exploratória. Defina semanas sobrepostas CPI/FOMC e denominador: frequência **entre apostas** não é frequência **do estado no mercado**. Para calendário semanal, blocos apenas de dia tendem a subestimar a dependência do episódio.

### 5. Barra pré-print mede atividade; não identifica posicionamento

Eu manteria a coluna. Ela registra retorno, amplitude, volume e negócios antes do evento. **Posicionamento é uma interpretação que OHLCV sozinho não distingue** de redução de liquidez, hedge ou outros fluxos.

**Cenário de falha:** chamar 22,4× de anomalia robusta porque a barra imediatamente anterior foi pequena. Preserve essa razão descritiva, mas acrescente uma referência histórica congelada para o mesmo horário e comparáveis de evento.

Também não confrontaria beta de retorno de **uma hora** com fechamento de **um minuto** ou barra parcial. Surpresa headline zero zera a contribuição desse regressor; não o intercepto, o resíduo ou o movimento possível. A surpresa depende ainda da referência: zero contra a primária carimbada não significa zero contra todo consenso.

## NICE-TO-HAVE

- **Correlação de 14 dias:** comparar primeiro sua distribuição dentro/fora da célula. “Concordância em %” exige transformar a correlação em rótulo por regra prévia; correlação alta pode coexistir com alts caindo mais que BTC.
- O rascunho acrescenta expectancy por tercis embora anuncie “só concordância”. Eu retiraria essa expansão desta rodada.
- Separe claramente snapshots parciais e fechamentos finais. O cabeçalho já menciona leitura às 13:00Z, posterior ao corte solicitado de 12:40Z: [rascunho:3](C:/dev/project-hunter/.claude/state/plantao/2026-09-11-0935-lane3.md:3).

## O QUE EU FARIA DIFERENTE

Rodaria o D-P23 como **curva de movimento após a entrada**, acompanhada de Δ(240−80), cobertura e incerteza. Sem procurar o “melhor” horizonte entre oito pontos.

Se aparecer acumulação tardia consistente, isso sustentaria propor um novo experimento controlado. A configuração 5 min/4 h continuaria uma hipótese pós-resultado, sujeita a novo pré-registro e validação futura.

## CONCORDO COM

A decomposição custo/bruto é informativa. Mas “sinal destruído” é excessivo: a própria EXP-0028 registra que o contraste líquido filha−mãe tem IC95 **[−0,2670; +0,0686]**, cruzando zero. A diferença pontual não comprova inferioridade entre versões. [EXP-0028:457](C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-0028-mean-reversion-5-min.md:457)

Concordo também com manter surpresa assinada, preservar o consenso anterior ao evento e separar ticker móvel de rótulo congelado por aposta.

## OBSIDIAN

- **Hipoteses-do-plantao** — registrar D-P23 como diagnóstico sem classificação causal; limitar a extensão H-P18.
- **EXP-0028 — a reversão à média decidida em 5 minutos** — separar reprovação da configuração de explicação causal da diferença.
- **KB-0082 — reversão de 15 minutos** — distinguir intervalo de amostragem de duração da posição.
- **Plantao/2026-09-11** — incorporar ressalvas sobre Kalshi, referência da surpresa, barra pré-print e horários parciais/finais.
- **Revisoes-Astra/Index** — indexar este parecer quando o orquestrador o registrar.