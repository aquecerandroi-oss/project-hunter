# Notas da T3.2 / T3.2b — invariantes novas para o contrato (`docs/RISK_ENGINE.md` v2)

**Autor:** risk-engine-guardian, 2026-09-06 (fechamento da revisão adversarial `bf4924b`).
**Para:** Sexta-feira levar ao contrato. **Eu não editei `docs/**`.**

As quatro decisões abaixo estão **implementadas e testadas** em `packages/risk-core`. Elas não
alteram nenhum limite escrito pelo Everton: preenchem lacunas que o v2 deixou implícitas e que a
revisão provou serem exploráveis. Cada uma traz o cenário numérico que a motivou.

## 1. Banda da zona de entrada: ±0,5 % em torno do **preço observado**

- Onde no contrato: §3.1, check 7 (`signal_validity`, "entrada fora da zona"), e §2 (tabela de
  limites do `paper_v1`).
- Novo limite do perfil: `max_entry_deviation_pct = 0.005`. O valor é o que a própria §3.1 nomeia
  (±0,5 %); nenhum limite de capital foi tocado.
- Preço observado = `mid` do book quando existe, senão `last_price`. Um deles sempre existe
  (`last_price` é obrigatório), então este check nunca é `unavailable` — a frescura do preço já é
  responsabilidade do check 4 (`data_quality`).
- `signal_validity` passa a exigir, junto: sinal ativo, stop abaixo de `entry_ref`, **stop abaixo do
  preço observado**, e `|entry_ref − observado| / observado ≤ 0,5 %`.
- Cenário que fecha: `entry_ref = 100`, stop 97,5, mercado a 110 — aprovado antes, com notional
  registrado 1.851,80 contra gasto real 2.036,98 e perda real no stop de 235,55 = **1,18 %** do
  patrimônio, contra teto de 0,25 %. E: LONG com stop 97,5 e mercado a 90 (stop já rompido)
  aprovado antes.

## 2. Preço do sizing: o **pior** entre `entry_ref` e o preço observado

- Onde no contrato: §4 (o bloco de fórmulas usa `entry_ref` em toda linha).
- Para um LONG, o pior é o **maior**. Todo teto, a perda planejada, o arredondamento por
  `step_size`, os dois contrafactuais e a distância de stop passam a ser medidos nesse preço, que a
  decisão publica como `sizing.sizing_price` (o `entry_ref` pedido continua gravado ao lado).
- Justificativa a escrever no contrato: **o teto nunca fica mais generoso por causa de um preço
  velho.** Com o mercado acima da referência, o motor compra menos unidades e reconhece a perda
  maior; com o mercado abaixo, a referência continua valendo. A admissibilidade da diferença é
  assunto do check 7 (item 1 acima), não do sizing.
- **Escopo honesto da frase, apontado pela Astra na revisão deste diff:** "nunca mais permissivo"
  vale para o **tamanho**, não para a geometria do stop. Referência 100, stop 99,8, mercado 100,2: a
  distância medida passa de 0,20 % (contra a referência) para 0,3992 % (contra o preço observado) e
  o mínimo de 0,3 % passa a ser cumprido — porque o stop está mesmo a 0,3992 % do preço que a ordem
  vai encontrar. É a mesma medida que o sizing usa; o contrato deve dizer isso em vez de prometer
  monotonicidade que não existe. Teste:
  `TestTheWorsePriceCanAlsoAdmitAProposal::test_a_stop_too_close_to_the_reference_can_be_far_enough_from_the_market`.
- **Assimetria da banda:** o desvio é dividido pelo **preço observado**, então para uma referência de
  100 a banda admite observado entre ≈ 99,5025 e ≈ 100,5025. É levemente mais tolerante à alta.
  Nenhum caminho aumenta o tamanho por causa disso (o preço do sizing é o pior dos dois), mas a
  assimetria tem de constar do contrato em vez de ser descoberta em produção.

## 3. Idade máxima do volume: `max_volume_age_s` passa a ser lido (120 s no `paper_v1`)

- Onde no contrato: §7 (R-OPS-2, "os insumos com idade máxima declarada … volume de 24 h, volume do
  minuto") e §3.1 check 9.
- O `MarketLiquidity` carrega **um** `volume_ts` para o volume de 24 h e para a referência do minuto;
  um carimbo vencido invalida os dois. Sem carimbo → `unavailable` (não é "fresco o bastante", é
  "desconhecido"). Carimbo no futuro → `unavailable`.
- Efeito: `liquidity_24h` vira `unavailable`, não há sizing, e `participation`, `sizing`,
  `slippage_estimate`, `cash` e `exposure_after` saem `unavailable` com o motivo. Rejeita.
- Cenário que fecha: volume do minuto de **45 minutos atrás** sustentando a participação como se
  fosse agora.

## 4. Caixa disponível é líquido das reservas

- Onde no contrato: §3.2 check 21 (`cash`) e §4 (`qty_by_cash`).
- `caixa_disponivel = max(0, cash − Σ reserved_cash)`. Cada reserva carrega **o seu próprio**
  `reserved_cash` (a coluna já existe em `trade_proposals`, T3.1), que é o caixa que ela segura com
  taxas incluídas — e o `PendingEntry` recusa `reserved_cash < reserved_notional` (SPOT: o caixa que
  uma compra segura é o notional mais as taxas, nunca menos).
- **Correção da Astra na revisão deste diff:** a primeira versão reestimava a reserva com o
  multiplicador de custo da **proposta candidata**. Cenário: caixa 500, reserva de 400 com custos
  padrão (segura 400,400096), candidata declarando custo zero → o motor aprovava mais 100 e
  comprometia 500,400096 contra 500. O compromisso de quem já reservou não pode encolher porque o
  próximo candidato declarou custo menor.
- O teto de caixa passa a publicar `limit = caixa_disponivel` (publicava `max_leverage = 1`, que não
  é um número de dinheiro e não dizia nada ao painel).
- Cenário que fecha: caixa 500 com 400 já reservados aprovava outros 499,5 — 900 comprometidos
  contra 500. Era o único teto que ignorava as reservas.

## 5. Perda do dia vem do patrimônio, não de campos opcionais (§5 já dizia; o código não fazia)

Não é invariante nova, é o contrato sendo cumprido, mas vale registrar a consequência para a T3.3:
`perda_diaria = max(0, 1 − equity / equity_inicio_dia)`, **sempre**. `daily_realized_pnl`,
`daily_unrealized_pnl` e `daily_costs` viraram **opcionais e só de relato**; nada no motor decide com
eles. Cenário que isso fecha: abertura 20.000, agora 19.500, campos vazios → o motor reportava
`daily_loss PASSED value=0` e aprovava entrada em tamanho cheio com o limiar de bloqueio de 2 % já
rompido.

**A divergência é medida, nunca bloqueia** (`PortfolioState.daily_decomposition_gap`). A primeira
versão recusava o estado quando `realizado + não realizado − custos ≠ equity − equity_inicio_dia`; a
Astra mostrou o buraco: `evaluate_exit` precisa de um `PortfolioState` **construído**, então um
descasamento contábil de `6E-11` impediria a construção do estado e, com ela, a **saída de
proteção** — exatamente o que a diretiva §3 proíbe. Uma trava de entrada não pode virar trava de
saída por via contábil.

**Para a T3.3, a identidade certa não é a que eu tinha escrito** (também da Astra): com uma posição
comprada a 100 e marcada a 110 na meia-noite, vendida hoje a 110, o realizado do dia é 10 e a
variação do patrimônio no dia é zero. A reconciliação diária é
`realizado_do_dia + não_realizado_agora − não_realizado_no_início_do_dia − custos_do_dia`, e o
`PortfolioState` de hoje não carrega o `não_realizado_no_início_do_dia`. Quem definir a política de
contabilização, arredondamento e corte temporal é a T3.3; o `daily_decomposition_gap` existe para
ela medir, não para o motor punir.

## 6. Saída de proteção não depende do `PortfolioState` (nova, achada pela Astra na 2ª rodada)

- Onde no contrato: §5 ("sem conseguir reconstruí-la o estado fica indisponível — entradas novas
  bloqueadas, **proteções preservadas**") e §10.
- `evaluate_exit(proposal, position, limits, kill_switch, *, portfolio=None)`: a saída passa a
  receber a **posição**, e o estado da carteira é opcional.
- Cenário que fecha: restart depois da meia-noite de São Paulo. O worker reconstrói a posição do
  Postgres muito antes de reconstruir a referência diária; `PortfolioState` **não constrói** sem
  `day_start_equity` e sem a âncora correta (`day_start_utc` é validado contra `as_of`). Com a
  assinatura antiga, o stop de uma posição que já existe esperava por um número que só limita
  **entradas** — ou o chamador inventaria um. Uma trava de entrada não pode virar trava de saída.
- Sem o estado, o kill switch registrado na decisão é o mais restritivo das **travas persistidas**
  (as escadas automáticas de perda e drawdown só *sobem* o estado e não são mensuráveis sem
  patrimônio); a mensagem do check diz "sem estado da carteira", para a proveniência não mentir.
- Continua sendo erro do chamador (`ValueError`) entregar posição de outro id, de outro mercado, ou
  um estado que não contém a posição.
- Quando os dois chegam, a quantidade vendável é o **menor** entre a posição entregue e a da
  carteira (3ª rodada da Astra). Cenário: depois de uma saída parcial de 6, a carteira tem 4 e o
  objeto de posição ainda diz 10 — vender 10 no SPOT venderia unidades que não existem. Divergência
  nunca recusa a saída; só faz vender menos.

## 7. Dono da retomada do kill switch

`hunter_risk.kill_switch.resume` **recusa** a retomada enquanto a avaliação automática ainda bloquear
(era um parâmetro morto). A trava durável, a transição auditada e a autenticação continuam sendo da
**T3.6** — o núcleo puro só diz que aquele destravamento seria desfeito pela próxima avaliação, e uma
transição que não muda nada é pior no log do que transição nenhuma.

## Pendência fora do meu escopo

`packages/core/hunter_core/strategies/envelope.py:45` — `AssumedCosts` aceita `float`. Dono do
`packages/core`. Detalhe e cenário no relatório da T3.2b.
