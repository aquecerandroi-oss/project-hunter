---
tags: [knowledge, solana, jupiter, spot-1, custo, execucao, aluguel, medicao]
tema: Custo real de ida-e-volta da mesa spot/1 (Jupiter, ficha 0,05 SOL, NEAR/UNI/LINK/TAO), medido nas nossas 10 posições fechadas e nas 20 transações na cadeia
fonte: registros próprios — `spot_positions` (10 fechadas) e `spot_orders` (20 confirmadas) do banco da VPS (`BEGIN READ ONLY`), velas 1 m `is_final` da Binance perp no mesmo banco, e `getTransaction`/`getMultipleAccounts`/`getMinimumBalanceForRentExemption` na RPC pública da Solana (só leitura) — consultados em 2026-10-01 (UTC)
fonte_url: —
lido_em: 2026-10-01
evidencia: medição própria — 10 posições (20 pernas) de 25/09 a 01/10/2026, 4 ativos, ficha 0,05 SOL, mean_reversion v14; cotação gravada pelo executor × efeito real na cadeia × último close 1 m da Binance perp antes do pouso
hipotese_testavel: sim
astra: concorda
status: vivo
owner: sexta-feira
updated: 2026-10-01
confiança: "?"
tipo: pesquisa
hipotese: —
variavel: custo de ida-e-volta por operação (SOL e % da ficha)
populacao: 10 posições fechadas da spot/1 (TAO 2, NEAR 5, LINK 1, UNI 2), 25/09–01/10/2026, ficha 0,05 SOL
efeito: custo médio 0,493 % da ficha por ida-e-volta (0,000247 SOL; 0,28 R) = 0,199 % fixo + 0,295 % proporcional
ic: "[0,32 %; 0,67 %] bootstrap pareado por posição (nominal; não cobre erro de referência nem regime)"
veredito: —
proximo_passo: reabrir com ≥ 30 posições ou quando a ficha mudar; antes disso, corrigir a constante de aluguel do executor (ver Open Bugs)
classe_de_perda: —
mercado: cripto
---

# KB-0171 — O custo real da `spot/1` (10 operações, consulta de 01/10/2026)

## O que afirma

**Uma ida-e-volta da `spot/1` com ficha de 0,05 SOL custou em média 0,49 % da ficha (0,000247 SOL, 0,28 R): 0,20 % é
taxa de rede fixa (≈ 0,00005 SOL por perna, não 0,001) e 0,29–0,30 % é proporcional (pool + impacto + diferença entre
a pool e a Binance + atraso de segundos).** Isso é ~0,25 % por perna — acima dos 0,15 %/perna da R84/R85 e **20 vezes
abaixo** dos 2 %/perna que a premissa de 0,001 SOL/perna da [[KB-0145-binance-como-sinal-solana-como-execucao]] daria
em 0,05 SOL. A cotação da Jupiter cumpriu-se quase à risca (slippage cotação→pouso ≈ 0), não houve taxa de
plataforma identificada, e o aluguel de ATA é depósito, não custo.

**Achado lateral (bug):** o executor desconta 2 039 280 lamports de aluguel quando cria a ATA, mas a rede cobra hoje
**1 488 440** (`getMinimumBalanceForRentExemption(165)` e o `createAccount` real nas 4 compras). Resultado: `pnl_sol` de
4 posições está **0,00055084 SOL alto cada**; o placar da mesa diz Σ −0,001735 SOL (−1,92 R) e o real é
**Σ −0,003938 SOL (−4,40 R)**. Registrado em [[Open Bugs]].

## Onde foi mostrado

**Fonte.** `spot_positions`/`spot_orders` da VPS (leitura), as 20 assinaturas lidas na RPC pública
(`getTransaction`, `jsonParsed`), velas 1 m da Binance **perp** (o mesmo mercado do sinal), consulta em 2026-10-01.
Nenhuma ordem `refused` tem assinatura (28 compras e 1 venda recusadas antes de assinar) — nenhuma taxa paga em
falha; nenhuma ordem com mais de uma assinatura (sem reenvio).

**SQL (núcleo; as três consultas rodaram dentro de `BEGIN READ ONLY; … COMMIT;`):**

```sql
-- 1. posições
SELECT id, market_symbol, status, entry_at, exit_at, tokens, sol_spent_lamports,
       sol_received_lamports, ata_rent_lamports, pnl_sol, r_multiple, initial_risk_sol
FROM spot_positions ORDER BY entry_at;
-- 2. pernas (exportadas em JSON linha a linha para o script)
SELECT row_to_json(x) FROM (SELECT p.id AS position_id, p.market_symbol, p.entry_at, p.ata_rent_lamports AS pos_ata_rent,
  p.sol_spent_lamports, p.sol_received_lamports, p.pnl_sol, p.r_multiple, p.initial_risk_sol, o.side, o.tx_signature,
  o.signatures, o.quote->>'outAmount' AS q_out, o.quote->'platformFee' AS q_platform_fee, o.fill, o.submitted_at
  FROM spot_positions p JOIN spot_orders o ON o.id IN (p.entry_order_id, p.exit_order_id)
  ORDER BY p.entry_at, o.side) x;
-- 3. referência: último close 1 m final da Binance (token e SOLUSDT, mesmo exchange/market_type do sinal)
WITH legs AS (SELECT p.id, p.market_symbol, m.exchange_id, m.market_type, 'buy' AS side,
                     (o.fill->>'confirmed_at')::timestamptz AS fill_at
              FROM spot_positions p JOIN agent_signals s ON s.id = p.signal_id JOIN markets m ON m.id = s.market_id
              JOIN spot_orders o ON o.id = p.entry_order_id
              UNION ALL /* idem com exit_order_id, 'sell' */ ...)
SELECT l.id, l.side, tp.close AS tok_prev_close, sp.close AS sol_prev_close, tf.close, sf.close
FROM legs l
JOIN markets tm ON tm.symbol = l.market_symbol AND tm.exchange_id = l.exchange_id AND tm.market_type = l.market_type
JOIN markets sm ON sm.symbol = 'SOLUSDT' AND sm.exchange_id = l.exchange_id AND sm.market_type = l.market_type
LEFT JOIN candles tp ON tp.market_id = tm.id AND tp.timeframe = '1m' AND tp.is_final
                    AND tp.open_time = date_trunc('minute', l.fill_at) - interval '1 minute'
LEFT JOIN candles sp ON sp.market_id = sm.id AND sp.timeframe = '1m' AND sp.is_final
                    AND sp.open_time = date_trunc('minute', l.fill_at) - interval '1 minute'
/* tf/sf = vela do próprio minuto do pouso, usada só como sensibilidade */ ;
-- 4. ordens recusadas pagaram taxa?
SELECT side, status, reason, count(*), count(tx_signature) AS with_sig FROM spot_orders GROUP BY 1,2,3;
```

Saída da consulta 1 (resumida): 10 linhas `closed`; `ata_rent_lamports = 2039280` em 4 (TAO 25/09, NEAR 26/09,
LINK 29/09, UNI 29/09) e 0 nas outras 6 (ATA reaproveitada). Consulta de estados: `buy confirmed 10`, `buy refused 28`
(15 `spot_max_open_reached`, 8 `cost_above_r_cap`, 4 `impact_above_cap`, 1 `ata_account_via_lookup_table`),
`sell confirmed 10`, `sell refused 1` (`simulation_failed` 6001) — todas as recusadas com `with_sig = 0`.

**Método por perna** (script em scratchpad, `kb171_analyze.py`, `Decimal`): taxa de rede = `meta.fee` (base 5 000 ×
assinaturas — sempre 1 — e o resto é prioridade); aluguel = `createAccount` pago pela carteira cuja conta sobrevive à
tx (a WSOL ATA é criada **e fechada** na mesma tx: transitória, 1 488 440 ida e volta); SOL do swap = Δ nativo da
carteira + taxa + aluguel retido; slippage = preenchido ÷ cotado − 1. Custo proporcional decomposto **no mesmo lote** q
e em SOL (preço de referência b = TOKUSDT ÷ SOLUSDT): compra = I − q·bₑ, venda = q·bₛ − O; a soma das partes + taxas é
igual, por identidade, a PnL-sem-atrito − PnL-real (conferido: diferença < 1e-15 — checa a contabilidade, **não** valida a
referência). O minuto da referência foi escolhido pelo `blockTime` da cadeia: os 20 pousos caem no mesmo minuto que o
`confirmed_at` do executor (1–2 s depois).

**Por posição (SOL; % sobre a ficha de 0,05; R = risco inicial da própria posição):**

| id8 | mercado | compra | venda | taxas (2 pernas) | total SOL | % ficha | R |
|---|---|---|---|---|---|---|---|
| 01a0d8f9 | TAO | +0,0000423 | +0,0000474 | 0,0000453 | 0,0001350 | 0,270 % | 0,13 |
| 01a0db2c | NEAR | +0,0002584 | +0,0000387 | 0,0001687 | 0,0004659 | 0,932 % | 0,49 |
| 01a0df24 | TAO | +0,0001290 | +0,0001769 | 0,0001375 | 0,0004433 | 0,887 % | 0,59 |
| 01a0e293 | NEAR | +0,0001309 | −0,0000042 | 0,0001039 | 0,0002307 | 0,461 % | 0,24 |
| 01a0e54f | NEAR | +0,0000759 | −0,0000776 | 0,0001103 | 0,0001086 | 0,217 % | 0,11 |
| 01a0eb0d | LINK | +0,0002190 | −0,0002136 | 0,0000394 | 0,0000447 | 0,089 % | 0,05 |
| 01a0ed92 | UNI | +0,0000634 | +0,0002018 | 0,0001303 | 0,0003956 | 0,791 % | 0,54 |
| 01a0efaa | NEAR | −0,0000302 | +0,0000984 | 0,0001717 | 0,0002398 | 0,480 % | 0,23 |
| 01a0f2c6 | UNI | +0,0001141 | +0,0001515 | 0,0000299 | 0,0002956 | 0,591 % | 0,33 |
| 01a0f410 | NEAR | −0,0000181 | +0,0000699 | 0,0000557 | 0,0001075 | 0,215 % | 0,09 |

**Médias:** compra 0,197 %, venda 0,098 %, taxas 0,199 % → **total 0,493 %** (mediana 0,470 %), **0,28 R** (fixo 0,11 R).
Bootstrap pareado por posição: [0,32 %; 0,67 %]; por dia (6 dias): [0,33 %; 0,70 %]; tirando uma posição por vez a
média fica entre 0,445 % e 0,538 %.

**Componentes isolados:**

- **Taxa de rede por perna:** média 49 634 lamports (mediana 37 377; mín. 5 290; máx. 105 000). Prioridade: compra
  média 38 316, venda 50 951; **5 das 20 pernas bateram o teto** `SPOT1_PRIORITY_FEE_MAX_LAMPORTS = 100 000` (4 vendas).
- **Slippage cotação→pouso:** compra média −0,015 % (mediana 0,000 %; pior −0,181 %, NEAR 26/09), venda −0,014 %
  (mediana −0,002 %). A Jupiter entrega o que cota; o custo já está *dentro* da cotação.
- **Prêmio da cotação na decisão** (`admission.spot1.parity.ratio` = preço Jupiter ÷ close Binance): média +0,195 %,
  praticamente igual ao custo de compra medido (0,197 %) — esperado, porque compartilham cotação e referência; não é
  validação independente.
- **Taxa de plataforma da Jupiter:** nenhuma identificada (`quote.platformFee = null` nas 10 compras; a cotação da venda
  não é gravada em `spot_orders.quote`; nenhum dono "só recebe" com fatia relevante — só 2 × 500 lamports de taxa de
  protocolo numa compra de LINK, 0,002 %).
- **Aluguel de ATA:** 4 contas criadas a **1 488 440 lamports** cada; as 4 seguem abertas, com saldo de token 0 e
  1 488 440 lamports cada (`getMultipleAccounts`, 01/10) — **0,00595 SOL de depósito recuperável**, nenhum fechado na venda.
  Reaproveitadas nas 6 compras seguintes (custo de aluguel 0). Não é custo enquanto for recuperado; fechar custa uma
  taxa-base (5 000) se for tx própria, 0 se for no mesmo swap.

**Ficha × custo fixo** (taxa média 49 634; teto 105 000):

| ficha (SOL) | fixo/perna (média) | fixo/perna (teto) |
|---|---|---|
| 0,05 | 0,099 % | 0,210 % |
| 0,10 | 0,050 % | 0,105 % |
| 0,25 | 0,020 % | 0,042 % |
| 0,50 | 0,010 % | 0,021 % |
| 1,00 | 0,005 % | 0,011 % |

Para o **fixo** ficar abaixo de 0,15 %/perna: ficha > 0,0331 SOL com a taxa média, ≥ 0,070 SOL (exatamente 0,15 %) com a
prioridade no teto. Para o fixo ser só 10 % de um orçamento de 0,15 %/perna: ~0,33 SOL. **O proporcional (~0,15 %/perna
nesta amostra) não tem evidência de diluição com a ficha** — e o impacto pode crescer (KB-0145: 1 SOL dá 0,02–0,82 %
conforme o token).

**Break-even.** A borda bruta (antes de custo) por operação precisa passar de **~0,49 % do nocional ≈ 0,28 R** na
geometria atual (stop médio ≈ 1,9 %, R médio 0,00094 SOL). Nestas 10, a borda bruta foi negativa: PnL sem atrito em
preço Binance Σ −0,00148 SOL (−1,59 R); custo Σ 0,00247 SOL; real Σ −0,00394 SOL (−4,40 R).

## Como mediríamos aqui

Já está medido com o que o executor grava; o que falta para uma medição de rotina:

- gravar `blockTime` e a **cotação da venda** em `spot_orders` (hoje `quote` é nulo nas vendas; só `quoted_out` vai no `fill`);
- trocar a referência "último close 1 m perp" por preço contemporâneo (bookTicker spot no segundo do pouso) para separar
  custo de execução de drift — a referência atual tem 1–35 s de defasagem e mistura base perp×spot;
- corrigir a constante de aluguel (ler o `createAccount` real da tx, não uma constante) e reprocessar `pnl_sol`/`r_multiple`
  das 4 posições pelo caminho auditado.

## Hipótese testável no Lab

Não é hipótese de estratégia; é **parâmetro de custo** para todas. Proposta: papel/backtest que mira execução na
`spot/1` com ficha 0,05 SOL usa **0,25 %/perna** (0,10 % fixo + 0,15 % proporcional) como caso base e **0,35 %/perna**
como sensibilidade (limite superior do IC ÷ 2); fichas ≥ 0,25 SOL podem usar ~0,17 %/perna, com o proporcional ainda a
medir nesse tamanho. Refutação desta nota: com ≥ 30 posições, média fora de [0,32 %; 0,67 %].

## Por que pode falhar

- **n = 10, 4 ativos, 6 dias, um só regime;** NEAR é metade da amostra. O IC é nominal: não cobre erro de referência,
  dependência temporal nem mudança de regime/congestionamento.
- **Referência defasada e perp:** um movimento de 0,2 % entre o close e o pouso vira 0,2 % de "custo"; a reversão à média
  compra depois de queda e pode ter seleção adversa sistemática que não cancela.
- **Só posições fechadas:** se alguma saída problemática ainda estivesse aberta, a amostra ficaria favorável (hoje: 0 abertas).
- **Taxa de prioridade depende da rede:** 5/20 pernas no teto; num dia congestionado o fixo vai a 0,21 %/perna.
- "Sem taxa de plataforma" quer dizer **nenhuma identificada nas transações examinadas** — remuneração embutida na rota
  não é visível assim.

## Segunda opinião (Astra)

Revisão em [[06-DECISIONS/Revisoes-Astra/KB-0171-custo-spot1|KB-0171-custo-spot1]]. Concordou com `meta.fee` como fonte,
aluguel como depósito, WSOL transitória, "0,001 SOL/perna ≈ 20× a média" e "0,15 %/perna abaixo do ~0,247 %/perna
observado", e confirmou o bug do aluguel pela leitura do código. Quatro must-fix, todos absorvidos: (1) aluguel lido da
cadeia, não de constante — feito; (2) chamar a medida de **déficit contra o último close perp** e escolher o minuto pelo
pouso on-chain — feito (`blockTime`, nenhum minuto mudou); (3) decompor no mesmo lote, em SOL, sobre base comum, e dizer
que o fechamento é identidade — feito (0,493 % mantido); (4) bootstrap por posição, não por perna, e listar falhas que
pousaram — feito (já era por posição; 0 falhas com assinatura). Corrigiu minha frase "0,033 SOL" → 0,0331, e "o
proporcional não cai" → "sem evidência de diluição".

## Relacionados

[[KB-0145-binance-como-sinal-solana-como-execucao]] · [[KB-0149-o-que-a-mesa-real-ensinou]] (item 23: o "0,14 %" da
Jupiter era cotação ida-e-volta instantânea; o realizado é 0,29 % proporcional + 0,20 % fixo) ·
[[KB-0169-fibonacci-e-lta-diaria-no-dado]] (parte D) · [[03-TRADING/Spot/Mesa-spot-1|Mesa-spot-1]] · [[Open Bugs]] ·
`docs/design/spot1-lab-solana.md` §3 (o check `cost_r` estimava 0,3–0,5 R; medido 0,28 R)

## Correção no código (01/10/2026, risk-engine-guardian)

O executor passou a ler o aluguel da **própria transação** (delta de lamports da ATA nova da carteira no `meta`),
nunca uma constante; aluguel ilegível é dobrado no gasto e marcado `signature_delta_rent_unknown` (PnL pessimista,
nunca otimista); fill antigo sem proveniência não é acreditado na reabertura de órfão. As 4 posições afetadas
(`01a0d8f9`, `01a0db2c`, `01a0eb0d`, `01a0ed92`) são corrigidas pelo script auditado
`infra/scripts/spot_fix_ata_rent.py` (ensaio por padrão; o `--apply` é do Everton, com esta nota como `--note`) —
runbook em `docs/RISK_ENGINE_MEME.md` §19.1. Enquanto o `--apply` não rodar, o banco continua com os números
otimistas. Revisão: [[06-DECISIONS/Revisoes-Astra/Spot-ata-rent-fix|Spot-ata-rent-fix]].
