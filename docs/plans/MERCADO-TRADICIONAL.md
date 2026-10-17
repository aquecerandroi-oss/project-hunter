# Plano — mercado tradicional (B3 primeiro), a partir de 19/10/2026

> **Status:** plano, sem código. Escrito pelo `quant-engineer` em 17/10/2026 (sábado) a pedido da Sexta-feira,
> com diálogo da Astra (`.claude/state/dialogue-mercado-tradicional.md`, síntese em
> `obsidian/06-DECISIONS/Dialogos/mercado-tradicional.md`). Decisão de origem:
> `obsidian/06-DECISIONS/2026-10-17-pausar-memes-e-cripto-ir-para-mercado-tradicional.md`.
>
> **O que o Everton decidiu (17/10):** parar memes e cripto; operar mercado tradicional; **dinheiro real, à mão, na
> conta dele na Rico, a partir de segunda 19/10** — contra a recomendação da Sexta-feira de uma fase de papel antes.
> **O que não muda:** nenhum agente envia ordem, toca a conta ou credenciais, ou recomenda tamanho de posição. O que
> entregamos é um **painel de sinais** e o **registro** de cada sinal e desfecho com custo real (medição).
>
> **Classificação:** o painel e o suporte multiativo são **arquiteturais** (subsistema novo, schema novo). Pela regra
> da casa isso exige documento de desenho e aprovação explícita do Everton antes da implementação (§3, tarefa W0-2).
> Este plano não reclassifica nada para caber no prazo.

Fontes externas: todas na §12, com URL e data de leitura (17/10/2026). O site da Rico (`rico.com.vc` e
`atendimento.rico.com.vc`) **devolve 403 da CDN da XP a acesso automatizado**; não contornei. Os dados da Rico vêm do
texto que o buscador mostra dessas páginas (snippet) e estão marcados assim; o Everton confirma no app.

---

## 1. A estratégia para segunda: H-038, momento intradiário de mercado no WIN

### 1.1 Por que esta e não outra

É **uma hipótese simples, pré-registrada, extrapolada** de evidência em índice de ações americano e de mercados
desenvolvidos — **sem replicação brasileira conhecida**. Não é "a melhor estratégia"; é a candidata da nossa base que
(a) tem evidência original em índice de ações (o mesmo tipo de ativo do WIN), (b) dá **um sinal por dia com horas de
antecedência**, executável à mão, e (c) tem custo pequeno diante do movimento.

- [[KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto]]: Gao, Han, Li & Zhou (2018) — no ETF do S&P 500,
  1993–2013, o retorno da 1.ª meia hora (desde o fechamento anterior) prevê o da última meia hora, mais forte em dias
  de volatilidade e volume altos; Li, Sakkas & Urquhart (2022) — 12 de 16 mercados desenvolvidos, 2005–2017
  (o Brasil **não** está na amostra); Shen, Urquhart & Wang (2022) — no BTC o custo de equilíbrio foi 3–10 bp.
- Custo no WIN (§1.4): ≈ 0,6 bp de ida e volta no cenário condicionado, contra 11,6 bp medidos na Binance
  ([[KB-0193-o-custo-binance-medido-nos-instantes-do-lab]]). O inimigo das memes e da cripto era o custo
  ([[KB-0149-o-que-a-mesa-real-ensinou]] §1); aqui ele é pequeno, e a pergunta passa a ser só se o sinal existe.
- Alternativas da base e por que ficaram atrás: rompimento da faixa de abertura (ORB; [[EXP-0010-session-orb-faixa-de-abertura]]
  testou em cripto, sem resultado, e tem mais parâmetros → mais caminhos bifurcados); tendência de série temporal em
  futuros ([[KB-0001-momentum-academico-e-o-que-nao-se-transfere]]) é diária/mensal, com poucos episódios
  independentes; reversão de 15 min ([[KB-0082-reversao-de-15-minutos-o-sinal-e-o-fluxo]]) aparece em só 2,7 % das
  ações americanas e paga ~1,3 bp bruto; candles ([[KB-0080-candlestick-evidencia]]) não batem o acaso em ações.

**O prior honesto:** perto de "não confirma". Efeitos publicados encolhem depois da publicação
([[KB-0177-decaimento-e-regime-o-que-a-literatura-de-cripto-mostra]]: McLean & Pontiff, −58 %), o Brasil não está na
amostra, e no WIN 97 % das pessoas físicas que persistiram ≥ 300 dias perderam
([[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]]). Em cripto e memes, 0 `CONFIRMA` até hoje.

### 1.2 Regras mecânicas (para execução à mão)

Definições (relativas ao pregão **à vista**, para sobreviver à troca de grade):
- **O** = início da negociação do à vista: **10:00 BRT** (grade atual e grade a partir de 03/11/2026).
- **C** = fim do call de fechamento do à vista previsto na grade vigente: **17:00 BRT até 31/10/2026**;
  **18:00 BRT a partir de 03/11/2026** (Ofício Circular B3 050/2026-VNC). O WIN segue negociando até 18:25; o ajuste
  (17:00–17:15 hoje, 18:00–18:15 depois) **não** é preço de saída.
- **Instrumento:** WIN do vencimento vigente (hoje **WINZ26**, último pregão na quarta mais próxima do dia 15 de
  dezembro). Ponto = R$ 0,20; tick = 5 pontos = R$ 1,00 (especificação B3).

| passo | quando | o quê |
|---|---|---|
| 0 | 09:00 | painel mostra "aguardando a 1.ª meia hora"; nenhuma direção |
| 1. Sinal | O+30 (10:30); recebido até O+90 (11:30), senão "sem sinal" | **r1 = ln(Ibovespa no fechamento da barra que termina em O+30 ÷ fechamento oficial do Ibovespa do pregão anterior)**. r1 > 0 → **direção do sinal: compra**; r1 < 0 → **venda**; r1 = 0 → sem operação. Publicado quando os dois números válidos chegam; nunca recalculado |
| 2. Entrada | de C−30 a C−25 (16:30–16:35 hoje; 17:30–17:35 a partir de 03/11) | a mercado, no sentido do sinal, no WIN vigente; fora da janela → "não executado" (contado) |
| 3. Stop | junto com a entrada | **stop de catástrofe**: ordem stop a mercado; comprado = entrada × 0,995 **arredondado para baixo** ao tick; vendido = entrada × 1,005 **arredondado para cima** (com WIN ≈ 207 000 pts: ≈ 1 035 pts ≈ R$ 207 por contrato, distância **nominal**). Dispara com toque igual; preenche no nível, ou no primeiro negócio além se houver gap, sempre com 1 tick adverso **pelo lado** (compra +1 tick, venda −1 tick). Parâmetro **arbitrário** (sem distribuição do WIN medida); fração de stops publicada. Depois do stop, **sem reentrada** no dia |
| 4. Alvo | — | **sem alvo**; saída por tempo |
| 5. Saída | C (17:00 hoje; 18:00 a partir de 03/11) | zerar a mercado. **Risco de corrida:** se o stop for ordem independente, a saída por tempo e o stop podem executar os dois e abrir posição inversa; cancelar antes deixa um intervalo sem proteção. Como a plataforma da Rico encerra/protege (stop vinculado à posição ou ordem pendente independente) é **pendência verificável**; até lá o painel mostra a saída programada e pede para **conferir posição e ordens abertas na plataforma**, sem prometer que evita inversão. O registro só declara a operação encerrada depois da confirmação informada. Stop tocado antes de C tem precedência |
| 6. Tamanho | — | **decisão do Everton.** O painel mostra custo e distância de stop **por contrato**; não sugere quantidade |

Antes da entrada (contados e publicados, decididos sem olhar retorno): feriados e pregões encurtados da B3; dia de
vencimento do WIN (opera-se o vencimento seguinte a partir do pregão seguinte); impedimento conhecido em O+30 ou C−30
(leilão, interrupção); Ibovespa ausente ou fora do prazo → "sem entrada". **Depois da entrada nada é excluído**:
interrupção → saída no primeiro negócio após a retomada (atraso registrado); sem nenhum preço até o fim do pregão →
**censura explícita**, publicada; censura pós-entrada não resolvida **bloqueia o CONFIRMA** da coorte (a média dos observáveis sai só como descritivo), nunca vira zero nem REFUTA.

Os três números (sinal, entrada, saída) estão a **horas** de distância; nada exige precisão de segundo.

### 1.3 Pré-registro H-038 (rascunho para congelar antes de segunda 09:00)

> Rascunho. Só vale quando a Sexta-feira (ou o `quant-engineer` por ordem dela) o gravar na
> [[Fila de Hipoteses]] com data/hora, antes da abertura (tarefa W0-1). Revisado pela Astra em seis rodadas (DECISÃO CONJUNTA na 6.ª).

- **origem:** [[KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto]] (Gao et al. 2018; Li, Sakkas &
  Urquhart 2022); decisão [[2026-10-17-pausar-memes-e-cripto-ir-para-mercado-tradicional]]; contexto
  [[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]]. Mercado novo (B3); nenhuma variável esgotada.
- **variável:** sinal de r1 (§1.2), sem limiar (sempre opera quando r1 ≠ 0).
- **população:** **H-038r (retrospectiva)** — histórico **sincronizado** exportado pelo Everton do MT5 da Rico:
  Ibovespa intradiário (símbolo do índice), WIN em 1 min dos contratos efetivos de cada data, fechamento oficial
  anterior e calendário histórico; janela, contagem e lista de exclusões congeladas (sha256) **antes** de ler
  qualquer retorno. **Primário = primeiros 80 % dos pregões; holdout = últimos 20 %**, não aberto no cálculo inicial,
  lido uma vez depois. **H-038 (prospectiva)** — todo pregão elegível desde 19/10/2026.
- **desfecho:** retorno líquido por pregão em bp do nocional do WIN na entrada (pontos × R$ 0,20): preço-modelo =
  primeiro negócio do WIN em ou depois de C−30 (entrada) e de C (saída), **1 tick adverso por perna, pelo lado** (compra +1, venda −1),
  menos custos de B3 (§1.4); IR fora da métrica. Na H-038r o modelo é uma **aproximação por OHLC** de 1 min, rotulada aproximação, nunca execução observada:
  entrada na abertura da primeira barra em ou depois de C−30 (dentro da tolerância); stop avaliado só nas barras desde
  a entrada até a anterior à saída (barra que atravessa o nível → nível; barra que abre além → abertura); saída na
  abertura da primeira barra em ou depois de C. **Deslizamento por lado**, uma vez só: toda compra (entrada comprada
  ou recompra de saída) soma 1 tick, toda venda (entrada vendida ou venda de saída) subtrai 1 tick — no toque, no gap
  e na saída por tempo; os custos de B3 não descontam o mesmo deslizamento de novo. Nenhuma máxima/mínima posterior à saída decide stop.
- **previsão:** média ≥ **+1,5 bp** líquido por pregão (MRE — escolha: ~2,5× o custo condicionado de ida e volta) no
  primário; IC 95 % por bootstrap de blocos mensais (10 000 réplicas, semente 20261019) com limite inferior > 0;
  **permutação**: série de sinais embaralhada entre pregões dentro de cada mês-calendário (10 000, mesma semente),
  mantendo as **trajetórias de mercado** e **recalculando a estratégia inteira** com o sinal sorteado (entrada, stop do
  lado sorteado, saída, custos, ausências) sobre a população elegível fixada antes; p = (1 + nº de médias ≥ a
  observada) ÷ 10 001 < 0,05; supõe intercambiabilidade dentro do mês (declarado); mede associação, não substitui o
  IC; IC = percentil de bootstrap que reamostra meses-calendário inteiros com reposição; média > 0 nas duas metades pela data mediana; **patamar**: resultado
  **líquido da estratégia completa** com r1 lido em O+15 e em O+45, cada um > 0 (publicados juntos, nunca para
  escolher); braço lucrativo em nível; **holdout com média líquida > 0**. CONFIRMA = seleção de candidato à réplica,
  não prova de efeito > 1,5 bp.
- **refutação:** limite superior do IC < +1,5 bp → **REFUTA** o tamanho; qualquer outro caso → **NÃO CONFIRMA**;
  positividade (IC > 0) publicada como descritivo separado. **LIMITE DE DADO** se < 750 pregões no primário, ou > 5 %
  sem preço em O+30/C−30/C, ou censura > 5 %. Futilidade da prospectiva: em 125 pregões elegíveis, média ≤ 0 →
  coorte encerrada **sem rótulo** (não é REFUTA), descritivos preservados.
- **publicado sem decidir:** três séries separadas — (i) retorno do Ibovespa na janela (a hipótese econômica);
  (ii) WIN hipotético com trajetória e custos; (iii) execução real informada pelo Everton (real − modelo). Fração de
  stops, por lado (comprado/vendido), por ano, sensibilidade a 2 ticks por perna, comparação com "sempre comprado" na
  mesma janela.
- **poder (declarado antes):** desvio por pregão suposto ≈ 25 bp (não medido); com efeito verdadeiro de 2,5 bp,
  rejeitar zero com 80 % pede ~785 pregões independentes (~3 anos). **Uma semana — e mesmo três meses — não diz nada
  sobre vantagem**; o placar inicial mede execução, custo e o pipeline.
- **status:** rascunho (17/10/2026).

### 1.4 Custo por contrato (cenário condicionado)

| item | valor por perna | fonte |
|---|---|---|
| corretagem Rico em minicontratos com RLP ativo | **R$ 0** (se o RLP estiver ativo; senão **desconhecida**, não zero) | snippet `rico.com.vc/produtos/minicontratos/` e `/rlp/` |
| B3 (emolumentos + registro): tarifa única R$ 1,97 (ADV 1–50) × fator 0,2 | R$ 0,394 | tabela B3, Ibovespa futuros |
| redução day trade 35 % (ADV day trade 1–5) | → **R$ 0,256** | idem |
| deslizamento suposto 1 tick | R$ 1,00 | suposição (inclui o meio spread; não medido) |
| **ida e volta** | **≈ R$ 2,51 por contrato ≈ 12,6 pts ≈ 0,61 bp** (WIN ≈ 207 000) | soma |

Imposto: day trade paga **20 %** sobre o ganho líquido do mês (DARF código 6015 até o último dia útil do mês
seguinte); o **IRRF de 1 %** sobre o ganho de cada dia é **antecipação compensável**, não 21 %. Prejuízo de day trade
só compensa ganho de day trade. Margem de day trade do WIN na Rico: **não lida** (o Everton vê no app).

### 1.5 Capital: banca acima de R$ 10.000, R$ 1.000 por operação, limite diário de R$ 9.000

Números do Everton (17/10, substituem os anteriores): banca **acima de R$ 10.000**; **R$ 1.000 "colocados em cada
operação"**; limite de perda diária **R$ 9.000**. Volatilidade usada abaixo: leitura manual única de 1 ano de
fechamentos diários do Ibovespa, **1,21 % ao dia**; escala grosseira por meia hora ≈ **0,32 %** (supõe blocos
independentes — não é medida da última meia hora). "Efeito plausível" = ~2,5 bp por operação, a escala usada no
poder da §1.3 (suposição, não medição e **não teto**: pode ser zero ou maior). As razões custo ÷ efeito abaixo são condicionais a essa suposição.

**O que "R$ 1.000 por operação" quer dizer em cada instrumento:**

| instrumento | R$ 1.000 vira | R$ por ponto | 1σ por operação (≈, escala grosseira) | stop de catástrofe 0,5 % + custo | custo de ida e volta | **custo ÷ efeito plausível** |
|---|---|---|---|---|---|---|
| **WIN, 1 contrato** | **margem** (garantia de day trade; o valor exigido pela Rico **não foi lido** — se passar de R$ 1.000, não cabe); o nocional é ≈ **R$ 41,4 mil** (≈ 41× os R$ 1.000) | **R$ 0,20 por ponto**; tick de 5 pts = R$ 1,00 | ≈ R$ 134 (≈ 1,3 % de R$ 10 mil) | ≈ R$ 207 + R$ 2,51 = R$ 209,51 (2,0951 % de uma banca de referência de R$ 10 mil; **distância nominal, não perda máxima**) | ≈ R$ 2,51 ≈ **0,61 bp** | **≈ 0,24** (o custo come ~¼ do efeito, se ele existir) |
| **BOVA11** (ETF do Ibovespa), 4–5 cotas | **nocional** de ≈ R$ 810–1 010 (cota ≈ R$ 202 em 16/10) | R$ 0,01 por centavo × cotas | ≈ R$ 3 | stop 0,5 % ≈ R$ 5 | tarifa B3 de day trade de ETF de ações **0,0230 % por perna** → 4,6 bp + spread (≥ ~1 bp, não medido) ≈ **5,6 bp** ≈ R$ 0,55 | **≈ 2,2** (o custo é maior que o efeito → valor esperado líquido **negativo** mesmo se o efeito existir) |
| ações isoladas, R$ 1.000 | nocional | — | — | — | mesma tarifa + spread maior | pior que o BOVA11 para esta regra (o sinal é do índice) |
| WDO, 1 contrato | margem; nocional de US$ 10 mil | R$ 10 por ponto, tick 0,5 pt = R$ 5 (**não lido hoje**) | — | — | tarifas **não lidas** | **desconhecido**; o sinal da H-038 é de índice de ações, não de dólar |

**Leitura:** para esta estrutura, o **WIN com 1 contrato tem a melhor relação custo ÷ efeito** de longe (≈ 0,24
contra ≈ 2,2 no BOVA11), como cenário condicional. Margem, nocional, orçamento e perda tolerada são coisas distintas: "R$ 1.000 por operação" pode ser a margem, mas a margem exigida pela Rico não foi lida, e a distância nominal do stop (≈ R$ 209,51 com custos, ≈ 2,1 % de uma banca de referência de R$ 10 mil) **não é teto de perda**.
Em ETF/ações, R$ 1.000 de nocional paga ~5 bp para buscar ~2,5 bp: não faz sentido para esta regra (faria para regras
de horizonte mais longo, com menos giro). **A margem de day trade do WIN na Rico precisa ser lida pelo Everton no
app.** O tamanho continua sendo decisão dele.

**Sobre o limite diário de R$ 9.000:** no cenário condicionado, o stop representa cerca de R$ 209,51 por contrato com
custos, equivalente a 2,0951 % de uma banca de referência de R$ 10.000; **não é perda máxima** — stop rejeitado,
desconexão, interrupção ou gap deixam a perda passar do nível nominal, e o protocolo não prova teto. O limite diário
informado é R$ 9.000 (≈ 45 000 pontos por contrato antes dos custos); seu percentual depende do patrimônio efetivo. O
painel registra o limite como dado, **não controla a conta** e só acompanha o limite com execução real informada
("limite não monitorado" sem ela). Sugerir outro valor seria recomendar tamanho; a escolha é do Everton.

### 1.6 Um só módulo puro para o painel manual e para o robô MT5

O robô autônomo da Rico (desenho separado, no modelo do `meme-executor`: o Everton liga, a credencial só vive no
terminal) e o painel manual chamam **as mesmas funções**, sem IO e sem relógio (o contexto carrega tudo):

```python
def decide_intraday_momentum(readings: IndexReadings, session: SessionTimes,
                             params: IntradayMomentumParams) -> SignalDecision | NoSignal: ...
def protective_stop(entry_price: Decimal, side: Side, params: IntradayMomentumParams,
                    spec: InstrumentSpec) -> Decimal: ...   # arredondamento por lado
def exit_instant(session: SessionTimes, params: IntradayMomentumParams) -> datetime: ...
def episode_result(fills: EpisodeFills, spec: InstrumentSpec, fees: FeeSchedule) -> EpisodeResult: ...
```

- `IndexReadings`: fechamento oficial anterior e Ibovespa em O+30, em `Decimal`, cada um com `event_at` (instante UTC
  do **evento**), fonte e `received_at`; o instante da decisão `decision_at` entra explícito no contexto, com a
  invariante `event_at ≤ received_at ≤ decision_at` e o prazo O+90. `NoSignal` carrega o motivo
  (dado ausente, recebido depois de O+90, pregão excluído, r1 = 0).
- `IntradayMomentumParams` congelados com a versão (entrada C−30, tolerância 5 min, stop 0,005, sem alvo, saída C,
  prazo O+90). `InstrumentSpec` (tick 5 pts, ponto R$ 0,20, vencimentos) e `FeeSchedule` (tabela B3, corretagem)
  são dado, nunca constante no código.
- **Contrato próprio de sinal agendado** (compra **ou** venda, sem alvo, janela de entrada, saída por tempo). O
  `Decision` atual do Lab (`packages/core/hunter_core/strategies/base.py`) aceita só LONG, exige `target1` e
  `stop < referência < alvo` — forçar a H-038 nele obrigaria inventar alvo ou trocar venda por compra. Integração com
  o protocolo `Strategy` só depois de um desenho explícito de compatibilidade (parte do W0-2). r1 registrado com
  `FeatureDefinition {name, version, parameters, description, inputs}`.
- `episode_result` compartilha a aritmética, mas preserva tipo e proveniência das três séries (índice, modelo OHLC,
  execução real).
- Testes obrigatórios: valores conhecidos sintéticos; compra, venda, r1 = 0; **não antecipação** separando corte do
  evento, recebimento e instante da decisão (barra futura ou não final não muda nada; dado de O+30 recebido depois de
  O+90 → `NoSignal`); arredondamento do stop por lado; gap; toque exatamente em C; troca de grade em 03/11; o mesmo
  resultado para o painel e o robô.
- Compartilhar o cálculo **não autoriza** o robô a enviar ordens; isso é do desenho separado.

### 1.7 O que o painel mostra (e o que não pode mostrar)

Direção do sinal (compra/venda no WIN e vencimento; "posição" só depois de execução informada), horário do sinal e validade, fonte e atraso do dado, status de
qualidade, entrada em C−30, saída em C, "sem alvo — saída por tempo", stop em pontos e R$/contrato como **distância
nominal**, custo por contrato rotulado **cenário condicionado**, IR como acima, e a linha fixa **"vantagem no WIN não
demonstrada"** com o link do estudo FGV (população e período). Nunca "compre 1 contrato"; nunca o índice como lucro.

**"Pare por hoje":** limite de perda **dado pelo Everton** (decisão dele). O painel só pode dizer "dentro do limite"
se o resultado real do dia (preço executado que ele informa, com custos) estiver lançado; sem isso mostra **"limite
não monitorado"**. O painel mostra, por contrato, a distância nominal do stop com custos — **não** como perda máxima
(§1.5). O painel **não controla a conta**.

### 1.8 Pendências verificáveis antes de confiar no registro

Nada abaixo é capacidade demonstrada; cada item tem dono e não autoriza trocar de população ou de fonte se falhar:

1. Margem de day trade do WIN, RLP e condições de custo da conta Rico (Everton, no app).
2. Como a plataforma encerra e protege a posição (stop vinculado à posição × ordem pendente independente) — define o
   risco de corrida da saída (Everton, na plataforma; o desenho do robô MT5 trata o caso automático).
3. Símbolo, significado temporal das barras e histórico disponível do Ibovespa no MT5, e a sincronização
   índice/WIN/calendário para a H-038r (Everton exporta; `quant-engineer` confere).
4. Acesso, campos, retenção e termos de uso do BDI da B3 (`quant-engineer`).

---

## 2. Dado ao vivo para o sinal (segunda-feira)

O sinal só precisa de **dois números do Ibovespa** (fechamento oficial de sexta e o valor às 10:30) e a entrada é
~6 h depois. Por isso um dado atrasado em 15 min serve para decidir; o que ele **não** serve é para o stop (que fica
como ordem na plataforma do Everton) nem para o preço do WIN.

| opção | atraso | custo | legal/uso | o que dá | quem |
|---|---|---|---|---|---|
| **A. Entrada manual (escolhida para segunda)** | nenhum na decisão | grátis | sem risco: é o dado que o Everton vê na própria plataforma, por uso dele | os dois números do Ibovespa digitados: fechamento oficial anterior e o fechamento da barra que termina em O+30, **lido no histórico do gráfico**, com data/hora do **evento** (hora de digitação é outro campo); prazo O+90 | Everton |
| B. MT5/Profit da Rico no PC do Everton | tempo real | MT5: "isento para clientes Rico" (snippet); Profit: grátis com RLP e ≥ 1 minicontrato/mês (snippet) | uso pessoal dele; **nada nosso lê o terminal** fora do robô do desenho separado, que o Everton liga e onde só ele põe a credencial | preço do WIN para ele executar; exportação do histórico sincronizado para a H-038r (ele exporta) | Everton |
| C. Feed licenciado pago (B3 via vendor, ProfitDLL/Nelogica etc.) | tempo real | **não lido; pago → decisão do Everton** | licença formal | WIN e Ibovespa automáticos no painel | Everton (contrato) |
| D. Arquivo público negócio a negócio da B3 (BDI, `arquivos.b3.com.br/bdi`) | D+1 | grátis | termos da B3 ("consulta informativa") **a ler antes de usar** | trajetória do WIN para a série (ii) e para comparar com a execução real | `quant-engineer` (provar acesso, campos, retenção de ~20 dias, termos) |
| ~~E. Gráfico público do Yahoo~~ | ~15 min | grátis | **fora**: os termos do Yahoo proíbem coleta automatizada sem permissão expressa (Astra, rodada 3) | — | — |

Uma leitura manual única do Yahoo foi feita hoje **só para este plano** (nível do Ibovespa, timestamp de barra e
volatilidade diária); nada do produto depende dele.

**Regras do dado:** sinal publicado **nunca** é recalculado; cada leitura guarda fonte, barra, instante do evento,
instante de recebimento e versão; depois de O+90 sem os dois números válidos → "sem sinal". O painel publica quando
os dados chegam (não promete horário). Até a fonte D (ou o histórico do MT5) ser provada, a série (ii) do WIN é
**"não mensurável"**, e o placar real é o que o Everton lançar.

Atraso não enviesa a decisão: a regra lê o valor **de** O+30, não o último valor visto; por isso a hora do evento é
obrigatória e a cotação corrente digitada às 11:15 como se fosse de 10:30 é o erro a impedir.

---

## 3. Tarefas do fim de semana (menor viável primeiro)

O prazo real de segunda é a **publicação do sinal (quando os dois números chegam, até O+90)** e a **entrada às
16:30**, não as 09:00.

| id | tarefa | Files | Owner (tier) | Depends-on |
|---|---|---|---|---|
| W0-0 | **Everton:** confirmar RLP ativo e as condições de custo da conta; margem de day trade do WIN; confirmar o limite do "pare por hoje" (R$ 9.000 informado; ver §1.5) | — | Everton | none |
| W0-1 | Congelar H-038/H-038r na Fila (texto da §1.3) **antes de segunda 09:00** e abrir a página do experimento | `obsidian/11-KNOWLEDGE/Fila de Hipoteses.md` (append), `obsidian/05-EXPERIMENTS/EXP-0020-momento-intradiario-win.md` | `quant-engineer` (opus) | none |
| W0-S | **O módulo puro da §1.6** (é o mesmo que o robô MT5 vai usar) com os testes listados | `packages/core/hunter_core/strategies/intraday_momentum_win_v1.py`, `packages/core/tests/unit/test_intraday_momentum_win_v1.py` | `quant-engineer` (opus) | W0-1 |
| W0-F | **Rede de segurança (sem produto):** CLI de pesquisa que recebe os dois números digitados, chama o módulo de W0-S e imprime o cartão do dia (direção do sinal, janela, stop nominal, custo por contrato, avisos da §1.7); a Sexta-feira manda o cartão ao Everton se o painel não estiver no ar | `infra/research/b3/cartao_do_dia.py`, `infra/research/b3/tests/test_cartao_do_dia.py` | `quant-engineer` (sonnet) | W0-S |
| W0-2 | Documento de desenho curto do painel de sinais B3 (instrumento, sessões, calendário, limites como dado, registro, RLS) → **aprovação do Everton** | `docs/design/b3-painel-de-sinais.md` | `quant-engineer` + `backend-specialist` (opus) | W0-1 |
| W0-3 | Calendário B3 e grades de sessão como dado (feriados 2026–2027, pregões encurtados, troca de 03/11, vencimentos do WIN) com testes | `packages/core/hunter_core/markets/b3_calendar.py`, testes | `backend-specialist` (sonnet) | W0-2 aprovado |
| W0-4 | Schema: instrumento B3 (tick, multiplicador, moeda BRL, sessão), sinais B3, limites de risco do usuário (perda diária) **como linha de tabela**, execuções informadas; RLS e `organization_id` | `infra/migrations/versions/00xx_b3_signals.py` | `database-architect` (opus) | W0-2 aprovado |
| W0-5 | Entrada manual dos dois números do Ibovespa (rota da API + validação: instante do evento, fonte, prazo O+90, imutável depois de publicado) | `apps/api/...` (rota B3), testes | `backend-specialist` (sonnet) | W0-2, W0-4 |
| W0-6 | Serviço que chama o módulo de W0-S quando os números chegam e grava o sinal com proveniência | serviço no `strategy-worker` ou `apps/api`, testes | `backend-specialist` (sonnet) | W0-S, W0-3, W0-5 |
| W0-7 | Registro do desfecho: série (i) do índice em C, custo por contrato, campo de execução real, "pare por hoje" com "limite não monitorado" | `apps/api/...` (rota), serviço no `strategy-worker` | `backend-specialist` (sonnet) | W0-4, W0-6 |
| W0-8 | Página do painel (`/[org]/b3/sinais`) com os textos da §1.7 e o formulário da entrada manual | `apps/web/app/[org]/b3/sinais/*` | `frontend-specialist` (sonnet) | W0-7 |
| W0-9 | Revisões: `code-reviewer`; `security-reviewer` (sem credencial, RLS); `risk-engine-guardian` (semântica do limite diário) | — | revisores (sonnet/opus) | W0-3…W0-8 |
| W0-10 | Deploy na VPS | — | **Everton** roda `compose.sh update` | W0-9 |

Se W0-2 não for aprovado até domingo à noite, **segunda roda só com W0-S + W0-F** (cartão do dia a partir dos números
digitados), e o painel entra quando aprovado. Isso não é um rebaixamento de processo: W0-F é ferramenta de pesquisa,
não produto, e W0-S é o módulo que o painel e o robô usarão de qualquer forma.

---

## 4. Comparação de mercados (para o Everton escolher; recomendação na §8)

| | B3 mini-índice (WIN) / mini-dólar (WDO) | B3 ações/ETFs | EUA ações/ETFs | FX/CFD |
|---|---|---|---|---|
| liquidez | WIN: os autores do estudo FGV o descrevem como o 3.º contrato de índice mais negociado do mundo (dado de 2019) | concentrada nas maiores; spread largo fora delas | a maior do mundo | — |
| horário (BRT, grade até 31/10) | WIN 09:00–18:25; à vista 10:00–16:55 + call até 17:00; a partir de 03/11 à vista até 18:00 | 10:00–16:55, call 16:55–17:00 | à tarde de Brasília | 24 h |
| custo de ida e volta | WIN ≈ R$ 2,51/contrato ≈ 0,6 bp (cenário §1.4); WDO: tick 0,5 pt = R$ 5 (não lido hoje), tarifas não lidas | corretagem Rico zero em ordens próprias digitais (snippet); tarifas B3 de ações **não lidas** | IBKR fixo US$ 0,005/ação (mín. US$ 1), escalonado US$ 0,0035 (mín. US$ 0,35); Alpaca sem comissão; + câmbio e IOF (não lidos) | spread do intermediário |
| capital mínimo | margem de day trade definida pela corretora (**não lida**) | lote de 100 + fracionário | IBKR e Alpaca sem mínimo declarado nas páginas lidas | — |
| alavancagem | implícita no futuro (nocional ≈ R$ 41 mil por WIN) | sem, salvo termo/aluguel | margem regulamentada nos EUA | alta |
| IR (residente PF) | day trade 20 %, IRRF 1 %, DARF 6015; swing de futuros 15 %, **sem** isenção de R$ 20 mil | swing 15 % com isenção se as vendas de ações do mês ≤ R$ 20 mil; day trade 20 % | Lei 14.754/2023: rendimentos no exterior na declaração anual, alíquota de 15 % (secundária; conferir com contador) | — |
| regulação | B3/CVM | B3/CVM | conta no exterior; declarar | **CVM alerta** contra intermediários estrangeiros de forex/CFD que captam residentes; fora |
| automação | MT5 da Rico (pacote Python **só Windows**) — só o Everton usa; nada nosso lê a conta | idem | IBKR API; Alpaca API com conta **só de papel** sem depósito | — |
| achar vantagem sistemática | difícil: competição com HFT e 97 % de perdedores PF ([[KB-0194-day-trade-no-mini-indice-quase-ninguem-vive-disso]]); custo baixo ajuda | idem + spread | mais estudado e mais arbitrado | — |

**Conta nos EUA, para um residente no Brasil:** a IBKR lista o Brasil entre os países onde abre conta; a Alpaca tem
conta só de papel sem depósito e conta real para não residentes com KYC (o país Brasil não apareceu no texto da
página de países que consegui ler — **não verificado**). Abrir conta, enviar dinheiro e pagar dados é **decisão do
Everton**.

---

## 5. Rico, concretamente (fontes públicas; site bloqueia leitura automática)

| pergunta | o que as páginas públicas dizem | situação |
|---|---|---|
| MetaTrader 5 | "contratação opcional e isenta de cobrança para clientes da Rico" | snippet de `rico.com.vc/plataformas/metatrader/` |
| simulador MT5 | existe artigo "como ativar um simulador da plataforma MetaTrader" | snippet `atendimento.rico.com.vc/artigo/2315` |
| Profit (Nelogica) | Profit Trader/Pro grátis "por tempo ilimitado ao operar a partir de 1 minicontrato ao mês com o RLP ativo"; simulador incluso no Profit Pro/Plus | snippets do blog Riconnect e `artigo/983` |
| RicoTrader | R$ 89,90/mês com conta real e simulador | snippet `artigo/982` |
| Tryd | oferecido | snippet `rico.com.vc/plataformas/tryd/`; preço não lido |
| corretagem minicontratos | zero com RLP ativo (day trade e swing) | snippets `/produtos/minicontratos/`, blog RLP |
| RLP | grátis para WIN, WDO e ações selecionadas pela B3 | snippet `/rlp/` |
| corretagem ações/ETFs | zero em ordens do próprio cliente nas plataformas digitais (desde 14/09/2020) | snippet `artigo/1431` |
| taxa de dados B3 em tempo real | **não encontrado** | Everton confere |
| custódia | existe artigo; valor **não lido** | Everton confere |
| robôs/EA no MT5 | **regra não encontrada** | irrelevante agora: nenhum robô nosso envia ordem |

---

## 6. O que reaproveitamos e o que reconstruímos

| módulo | reaproveita | reconstrói |
|---|---|---|
| coleta de mercado | padrões do `hunter_exchanges` (normalização, proveniência, falha fechada) | entrada manual primeiro; depois fonte autorizada (feed licenciado ou o terminal do Everton via robô, desenho separado) e BDI para D+1; não há WebSocket público grátis da B3 |
| identidade de mercado | `market_type` já existe | instrumento B3: tick, multiplicador, moeda BRL, vencimento/rolagem, sessão e feriados |
| features/anomalias/regime/score | cálculo NumPy | baselines por hora assumem 24/7 → sessão; não é necessário para a H-038 |
| `Strategy` | protocolo puro (`evaluate` sem IO/relógio) | módulo novo `intraday_momentum_win_v1` |
| Risk Engine | contrato e auditoria; kill switch | sem ordens do sistema: o papel vira limites como dado (perda diária do usuário) e "pare por hoje"; margem e multiplicador de futuros |
| Lab/sombra | conceito de `signal_outcomes` e registro | recorder com sessão (o walker assume velas 24/7 da Binance) |
| pesquisa (`infra/research`) | inteiro (pré-registro, guardas, bootstrap) | carregador de WIN/Ibovespa |
| UI | shell, nav-registry, tabelas | página de sinais B3 |
| schema | RLS, `organization_id`, auditoria | tabelas B3; BRL × USD; calendário |

Tamanho: um **milestone novo (M-B3)**, arquitetural, com desenho em `docs/design/` e aprovação do Everton. O painel do
fim de semana é a fatia mínima dele.

---

## 7. Evidência por família — o que a nossa base já diz (antes de buscar fonte nova)

A maior parte da base de 11-KNOWLEDGE veio de pesquisa em **ações e futuros**, aplicada depois a cripto. Agora ela
volta ao mercado de origem. O que refutamos/não confirmamos em cripto **não** se transfere de volta automaticamente;
volta só como hipótese **nova em dado novo** (defensor), nunca relendo os dados velhos.

| família | notas | o que concluíram | evidência original | em cripto | volta como (dado novo) |
|---|---|---|---|---|---|
| momento intradiário de mercado | [[KB-0176-momento-intradiario-condicionado-o-vizinho-mais-perto]], [[KB-0175-estado-de-mercado-condiciona-momentum-mas-em-que-direcao]] | 1.ª meia hora prevê a última no SPY e em 12/16 mercados desenvolvidos; mais forte em dias voláteis (Gao); custo de equilíbrio pequeno | **índice de ações** — vale direto no WIN | nunca testado assim (a C1/H-027 era tendência diária) | **H-038** (§1) |
| tendência de série temporal / rompimento de canal | [[KB-0001-momentum-academico-e-o-que-nao-se-transfere]], [[KB-0003-rompimento-de-canal-e-data-snooping]], [[KB-0035-momentum-crashes-e-o-piso-que-virou-filtro-de-regime]] | TSMOM positivo em 58 futuros (Moskowitz, Ooi & Pedersen 2012); canal lucrou em 12 futuros 1978–84 e sumiu 1985–2003 (Park & Irwin 2005); resposta a regime é escalar exposição, não filtrar | **futuros** — vale direto, mas diário/mensal | H-024 NÃO CONFIRMA; H-027 REFUTA o tamanho | TSMOM diário em futuros B3 (WIN/WDO/DI), coorte futura; poucos episódios → baixo poder |
| análise técnica / gráfico | [[KB-0167-analise-grafica-o-que-sobra-depois-do-custo]], [[KB-0053-contracao-de-volatilidade-o-unico-pedaco-formalizavel]], [[EXP-0008-breakout-compressao-de-volatilidade]] | regras de Brock et al. sumiram depois de 1986; no futuro do S&P nenhuma regra bate o caixa (Sullivan et al.); VCP é anedótico | ações/índices | H-025 NÃO CONFIRMA; H-026 A REFUTA | não priorizar |
| candles | [[KB-0080-candlestick-evidencia]] | em ações diárias, nenhuma regra melhor que o acaso (Marshall et al.) | ações | — | não |
| reversão de curto prazo | [[KB-0082-reversao-de-15-minutos-o-sinal-e-o-fluxo]], [[EXP-0009-mean-reversion-pullback-em-tendencia]] | 15 min: 90 % dos pares cripto × 2,7 % das ações/ETFs dos EUA; bruto ~1,3 bp | cripto e ações | a `mean_reversion` é a única família bruto-positiva, IC com zero (H-036 em curso) | não no WIN |
| faixa de abertura (ORB) | [[EXP-0010-session-orb-faixa-de-abertura]] | evidência externa em índice (Crabel; Zarattini & Aziz 2023 — **não lido** por nós) | índice de ações | cripto não tem sessão; sem resultado | segunda candidata, só depois da H-038r |
| volume relativo | [[KB-0015-volume-relativo-e-o-pico-como-exaustao]] | prêmio de volume alto em ações (Gervais et al.), corte transversal semanal | ações | inconclusivo | ações B3 só com capital e dado diário |
| custo de execução | [[KB-0040-a-lei-da-raiz-quadrada-e-o-regime-que-nao-e-o-nosso]], [[KB-0041-almgren-chriss-ao-contrario-o-custo-dominante-e-o-relogio]], [[KB-0042-o-open-nao-e-preco-executavel]] | impacto ∝ raiz do tamanho; o relógio domina; a abertura da vela não é preço executável | — | — | preço-modelo = negócio depois do instante + 1 tick |
| decaimento e mineração | [[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]], [[KB-0177-decaimento-e-regime-o-que-a-literatura-de-cripto-mostra]] | cada variante custa; efeito publicado cai ~58 % | ações | confirmado na prática (0 CONFIRMA) | uma hipótese por vez, pré-registrada |
| fechamento/overnight, pares | — | **não há nota na base** | — | — | curar antes de propor |

---

## 8. Recomendação

**Começar pela B3, WIN, na Rico**, porque: (1) o Everton já tem a conta (nada a abrir); (2) o custo por operação é o
menor que já vimos (≈ 0,6 bp no cenário, contra 11,6 bp na Binance e 2–4 % nas memes); (3) o WIN é índice de ações,
o mesmo tipo de ativo da evidência que temos; (4) uma operação por dia cabe em execução manual. (5) Com a estrutura do Everton (R$ 1.000 por operação, banca > R$ 10 mil), o WIN com 1 contrato é o instrumento com a melhor relação custo ÷ efeito plausível (≈ 0,24, contra ≈ 2,2 no BOVA11 com R$ 1.000 de nocional; §1.5). **Os EUA perdem por
agora** por motivos práticos, não de mérito: conta nova no exterior, câmbio/IOF e imposto anual a conferir, horário
mais tarde; a vantagem dos EUA (liquidez, Alpaca com papel grátis e API) fica como segundo caminho, decisão do
Everton. FX/CFD fica fora (alertas da CVM).

A recomendação da Sexta-feira de **papel antes** foi registrada; o Everton escolheu dinheiro real. O que este plano
garante é medir desde o primeiro dia.

---

## 9. Plano de duas semanas (19/10 → 30/10)

Ondas pela regra de `parallel-subagent-driven-development` (arquivos disjuntos por onda; sem commit pelos agentes).

| onda | id | tarefa | Files | Owner (tier) | Depends-on |
|---|---|---|---|---|---|
| 0 (fim de semana) | W0-0 … W0-10 | §3 | §3 | §3 | §3 |
| 1 (19–23/10) | W1-1 | provar a fonte de negócios do WIN: BDI (acesso, campos, retenção) e/ou histórico 1 min exportado pelo Everton do MT5 | `infra/research/b3/fonte_win.py`, `obsidian/11-KNOWLEDGE/KB-0195-…` | `quant-engineer` (sonnet) | W0-1 |
| 1 | W1-2 | **H-038r**: rodar o pré-registro congelado (lista e exclusões congeladas com sha256 antes dos retornos; holdout lido depois); advogado de Jesus + defensor | `infra/research/b3/h038r.py`, testes, KB do resultado | `quant-engineer` (opus) | W1-1 |
| 1 | W1-3 | série (ii) do WIN no registro, assim que a fonte estiver provada | recorder | `backend-specialist` (sonnet) | W1-1, W0-7 |
| 1 | W1-4 | placar diário (três séries + execução real − modelo) no diário do Obsidian | `obsidian/09-OPERATIONS/Diario/2026-10-2x.md` | Sexta-feira | W0-7 |
| 2 (26–30/10) | W2-1 | grade de 03/11 testada no calendário antes da virada | `b3_calendar.py` | `backend-specialist` (sonnet) | W0-3 |
| 2 | W2-2 | desenho do M-B3 completo (instrumentos, multiativo, BRL/USD) | `docs/design/m-b3-multiativo.md` | `database-architect` + `quant-engineer` (opus) | W0-2 |
| 2 | W2-3 | segunda candidata pré-registrada **só em dado novo** (ORB ou TSMOM diário em futuros B3), se a H-038r não refutar a família | Fila (append) | `quant-engineer` (opus) | W1-2 |
| 2 | W2-4 | execução da opção escolhida pelo Everton para a pilha cripto/meme (§10) | VPS (Everton executa) | `devops-engineer` (sonnet) + Everton | decisão |

Se a H-038r **refutar** o tamanho, a recomendação ao Everton é parar de operar a regra (a decisão é dele).

---

## 10. A pilha de cripto e memes na VPS (opções para o Everton)

Inventário somente-leitura de hoje (17/10/2026 16:36Z; `BEGIN READ ONLY` com `default_transaction_read_only=on`;
nenhum desfecho da H-036 lido):

- **Banco:** 153 GB no total; tabelas de meme/Solana **55 GB**, cripto e comuns **98 GB**. Maiores: `outbox_events`
  48 GB, `opportunity_history_2026_10` 18 GB, `feature_snapshots` 9,9 + 9,1 GB, partições `meme_*` 3–7 GB cada.
- **Disco:** 257 de 348 GB (74 %), 92 GB livres. Docker: imagens 23,5 GB (20 GB recuperáveis), cache de build 35 GB
  (21,75 GB recuperáveis).
- **CPU (foto de um instante, 12 núcleos):** postgres 315 %, cinco `market-worker` ≈ 262 % somados, `scanner-worker`
  73 %, redis 33 %, `strategy-worker` ≈ 1 % cada.
- **`meme-worker` em laço de reinício** (`Restarting (1)`): a poda de `meme_tokens` viola a chave estrangeira de
  `meme_events` (log do contêiner). Bug para o `backend-specialist`; não corrigido aqui.
- **Lab de cripto:** 10 versões ativas (8 `mean_reversion` incluindo a v14 `paper`, `mean_reversion_h1 v1`,
  `momentum v3 paper`); sinais em 7 dias: `momentum v3` 173 (24,7/dia, 15 mercados), família `mean_reversion` 2,9–10,3
  por versão por dia. Histórico: `candles_1m` desde 11/06/2026 (566 mercados), `market_snapshots` desde 05/09/2026
  (494 mercados).

A **H-036** (`mean_reversion v14` em consultas cegas em 06/01, 07/04 e 07/07/2027) precisa de: os `market-worker`
de perpétuo (velas e `market_snapshots` para o spread), o `strategy-worker` com a v14 intocada e o export cego
semanal. **Não sei** se a v14 depende do `scanner-worker`; isso tem de ser conferido antes de parar o scanner.
Mexer na v14, depreciá-la ou superá-la antes de 07/07/2027 encerra a H-036 como LIMITE.

| opção | o que para | ganho | custo/risco |
|---|---|---|---|
| A. manter tudo | nada | zero trabalho | ~7 núcleos ocupados; disco cresce; meme-worker seguirá reiniciando |
| **B. enxugar (recomendada)** | `meme-worker` (já quebrado), `meme-executor` (piloto de cópia desligado), `market-worker-spot` se a `spot/1` seguir pausada; `docker image prune` + cache de build | ~42 GB de disco (imagens + cache) e a CPU das memes; a H-036 segue | parar contêiner e podar imagens são **comandos do Everton**; apagar dados de meme é irreversível → só com dump antes e decisão dele |
| C. só o mínimo da H-036 | também o scanner (se não for dependência) e as outras versões do Lab | mais CPU (o scanner e o postgres) | depreciar versões é mudança de estratégia (nota no Obsidian obrigatória); errar a dependência mata a H-036 |
| D. parar tudo | tudo | máximo | encerra a H-036 como LIMITE; não recomendado |

---

## 11. O que continua valendo para dinheiro real

O Everton decidiu operar real à mão. Fica registrado, como recomendação (decisões dele):
1. Tamanho: nenhum agente sugere; a conta do stop por contrato está no painel.
2. Nenhuma ampliação de tamanho com menos de 125 pregões de placar, e nunca por causa de uma semana boa.
3. Se a H-038r **REFUTAR**, parar a regra.
4. `LiveExecutionAdapter` continua levantando `LiveTradingDisabled`; nada no sistema envia ordem.

---

## 12. Fontes (lidas em 17/10/2026)

- B3, grade de derivativos de índice: https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-participantes-e-traders/horario-de-negociacao/derivativos/indices/
- B3, grade de ações: https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-participantes-e-traders/horario-de-negociacao/acoes/
- B3, Ofício Circular 050/2026-VNC (novas grades a partir de 26/10 e 03/11/2026): https://www.b3.com.br/data/files/99/B7/82/67/8A631A103BBB511AAC094EA8/OC%20050-2026-VNC%20NOVOS%20HORARIOS%20DE%20NEGOCIACAO_PT.pdf
- B3, tarifas de Ibovespa futuros: https://b3.com.br/pt_br/produtos-e-servicos/tarifas/listados-a-vista-e-derivativos/renda-variavel/tarifas-de-ibovespa-e-indice-brasil-50/futuros-e-estruturadas/
- B3, especificação do WIN: https://www.b3.com.br/en_us/products-and-services/trading/equities/mini-ibovespa-futures.htm
- B3, BDI (arquivos públicos): https://arquivos.b3.com.br/bdi/tabelas?lang=pt-br (só snippet; acesso a provar)
- Rico (snippets de busca; páginas devolvem 403 a acesso automatizado): https://www.rico.com.vc/plataformas/metatrader/ · https://www.rico.com.vc/produtos/minicontratos/ · https://www.rico.com.vc/rlp/ · https://riconnect.rico.com.vc/blog/profit-gratis/ · https://atendimento.rico.com.vc/artigo/982-o-simulador-e-gratuito-ricotrader · https://atendimento.rico.com.vc/artigo/983-o-simulador-e-gratuito-profit · https://atendimento.rico.com.vc/artigo/2315-como-ativar-um-simulador-da-plataforma-metatrader · https://atendimento.rico.com.vc/artigo/1431-quanto-custa-investir-em-acoes-fiis-etfs-bdrs · https://www.rico.com.vc/plataformas/tryd/
- MetaTrader 5, pacote Python (comunica com o terminal; distribuído para Windows): https://www.mql5.com/en/docs/python_metatrader5
- Receita Federal, isenção de R$ 20 mil em ações: https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda/pagamento/renda-variavel/bolsa-de-valores-1/isencoes
- Receita Federal, retenções (IRRF): https://www.gov.br/receitafederal/pt-br/assuntos/meu-imposto-de-renda/pagamento/renda-variavel/bolsa-de-valores-1/retencoes (citada pela Astra)
- Lei 14.754/2023: https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/lei/l14754.htm (só o art. 2.º pelo snippet; a alíquota de 15 % vem de fonte secundária)
- CVM, forex e cripto: https://www.gov.br/cvm/pt-br/assuntos/protecao/mercado-forex
- Interactive Brokers, países: https://www.interactivebrokers.com/en/accounts/open-account-country-list.php · comissões: https://www.interactivebrokers.com/en/pricing/commissions-stocks.php · dados: https://www.interactivebrokers.com/en/pricing/market-data-pricing.php
- Alpaca, planos de dados: https://alpaca.markets/data · conta só de papel: https://docs.alpaca.markets/us/docs/paper-trading · países: https://alpaca.markets/support/countries-alpaca-is-available (Brasil não verificado)
- Yahoo Finance, gráfico público `^BVSP` (endpoint `query1.finance.yahoo.com/v8/finance/chart`), leitura manual única para este plano às ~17h BRT de 17/10; os termos (https://legal.yahoo.com/br/pt/yahoo/terms/otos/index.html, cláusula achada pela Astra) proíbem coleta automatizada sem permissão — fora do produto
- B3, tarifas de ações e ETFs (à vista, day trade): https://www.b3.com.br/pt_br/produtos-e-servicos/tarifas/listados-a-vista-e-derivativos/renda-variavel/tarifas-de-acoes-e-fundos-de-investimento/a-vista/
- Chague, De-Losso & Giovannetti, "Day trading for a living?": https://ideas.repec.org/p/fgv/eesptd/525.html
