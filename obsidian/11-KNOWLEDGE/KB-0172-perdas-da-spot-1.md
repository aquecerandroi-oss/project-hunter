---
tags: [knowledge, spot-1, perdas, mean-reversion, jupiter, solana, execucao, medicao]
tema: por que as 10 primeiras operações da spot/1 perderam — sinal sem vantagem fora da amostra, custo maior que a vantagem, denominação em SOL que comprime o resultado para perto de zero, e dois defeitos de execução
fonte: registros próprios — spot_positions (10 fechadas), spot_orders (21 linhas não recusadas ou de venda), agent_signals + signal_outcomes (os 10 sinais e toda a v14 prospectiva), velas 1 m is_final da Binance perp (mercado do sinal e SOLUSDT, 5 020 velas) — banco da VPS em BEGIN READ ONLY, consultado em 2026-10-01 (UTC); custo por operação de KB-0171
fonte_url: —
lido_em: 2026-10-01
evidencia: medição própria — 10 posições reais (25/09–01/10/2026, 4 ativos), comparadas com o desfecho do Lab dos mesmos sinais e com 202 sinais terminais da v14 prospectiva (07/09–30/09)
hipotese_testavel: sim
astra: "concorda com os achados A (aluguel) e B (cotação única) e com a separação sinal/denominação/execução; pediu dois eixos e retornos brutos da mesma janela no lugar do R líquido do Lab, absorvido"
status: vivo
owner: quant-engineer
updated: 2026-10-01
confiança: "?"
tipo: pesquisa
hipotese: —
variavel: "classe da perda (custo / denominacao_sol / movimento_adverso) e incidente (cotacao_fantasma / aluguel_constante)"
populacao: "10 posições da spot/1 (mean_reversion v14, ficha 0,05 SOL); contexto: 202 sinais terminais da v14 prospectiva"
efeito: "Σ verdadeiro −0,003938 SOL (−4,40 R; média −0,44 R); a v14 no Lab soma −0,03 R em 202 sinais terminais"
ic: —
veredito: —
proximo_passo: "corrigir o aluguel e a revalidação do gatilho; depois, pré-registrar H-c (a v14 paga o custo da spot?) antes de qualquer mudança de geometria"
classe_de_perda: movimento_adverso
mercado: cripto
---

# KB-0172 — Por que a `spot/1` perdeu nas 10 primeiras operações

## O que afirma

1. **O placar mente para cima.** Registrado: Σ −0,001735 SOL (−1,92 R), 6 perdas e 4 ganhos. Verdadeiro:
   **Σ −0,003938 SOL (−4,40 R), 8 perdas e 2 ganhos.** A diferença vem do aluguel de ATA constante (bug achado em
   [[KB-0171-custo-real-da-spot-1]]). Ele também **muda decisões**: o LINK parou em −1,64 R verdadeiro.
2. **O sinal não tem vantagem fora da amostra.** A v14 na coorte prospectiva do Lab (Binance perp, R já líquido de
   11 bp e funding), por semana de emissão: 07/09 (desde 09/09 19:48Z) **−15,21 R** (65 terminais) · 14/09 **+19,18 R** (42) · 21/09
   **−2,30 R** (76) · 28/09 **−1,70 R** (19). Somando, **202 terminais e Σ −0,03 R**. A seleção da v14 para a mesa
   (R63, Σ +14,90 R em 23 sinais) saiu da única semana boa. Nos mesmos 10 sinais executados, o Lab deu −3,88 R
   (2 alvos, 5 stops, 3 expirados).
3. **O custo é maior que a vantagem.** O custo medido é 0,28 R por ida-e-volta ([[KB-0171-custo-real-da-spot-1]]).
   A vantagem bruta do sinal está perto de zero. Pelo cálculo da KB-0171 para estas 10: PnL sem atrito em preço
   Binance Σ −0,00148 SOL, custo Σ 0,00247 SOL.
4. **Denominar em SOL comprime o resultado para perto de zero, e lá o custo decide.** A mesa carrega alt/SOL, não
   alt/USD. A correlação 1 m alt × SOL nas janelas foi 0,39–0,83, e o desvio de alt/SOL ficou entre 0,61 e 0,92 do de
   alt/USD. A geometria, porém, é medida no ATR de alt/USD. Resultado: **0 alvos reais contra 2 no Lab, 2 stops
   genuínos contra 5, e 7 de 10 saídas por tempo**, com R verdadeiro médio de −0,17 R nas saídas por tempo. A
   correlação corta para os dois lados. O NEAR de 27/09 foi salvo por ela (Lab stop −1,07 R; real +0,62 R, com o SOL
   −1,95 %). Os dois alvos do Lab (NEAR 30/09, UNI 30/09) viraram +0,03 R e −0,01 R.
5. **Duas cotações fantasmas em 10 operações.** A saída é decidida sobre **uma** cotação do lote. Uma vez a cotação
   veio −13,6 % (UNI 29/09, stop falso; a venda recotou normal). Outra vez veio +3,6 % (NEAR 26/09, alvo falso,
   simulação recusada). A Binance não mostrou nenhum dos dois movimentos.

## Onde foi mostrado

Banco da VPS, só leitura (`BEGIN READ ONLY; … COMMIT;`), 01/10/2026. Consultas usadas:

```sql
-- posições
SELECT p.id, p.signal_id, p.market_symbol, p.status, p.entry_at, p.exit_at, p.tokens, p.sol_spent_lamports,
  p.initial_risk_sol, p.ata_rent_lamports, p.high_water_sol, p.sol_received_lamports, p.pnl_sol, p.r_multiple,
  p.params::text, p.entry::text, p.exit::text, p.exit_intent::text
FROM spot_positions p ORDER BY p.entry_at LIMIT 20;
-- ordens (marca e r_now de cada decisão de saída)
SELECT o.position_id, o.market_symbol, o.side, o.attempt, o.status, o.reason, o.received_at,
  o.intent->>'reason', o.intent->>'r_now', o.intent->>'mark_sol', o.quote->>'outAmount', o.fill::text
FROM spot_orders o WHERE o.status <> 'refused' OR o.side = 'sell' OR o.position_id IS NOT NULL
ORDER BY o.received_at LIMIT 60;
-- sinais e desfecho do Lab
SELECT s.*, o.result, o.r_multiple, o.mfe, o.mae, o.exit_ts, o.meta FROM agent_signals s
LEFT JOIN signal_outcomes o ON o.signal_id = s.id WHERE s.id IN (SELECT signal_id FROM spot_positions);
-- caminho 1 m do mercado do sinal e de SOLUSDT perp, da entrada −5 min até +245 min
SELECT w.pid, m.symbol, c.open_time, c.open, c.high, c.low, c.close FROM (…) w
JOIN candles c ON c.market_id = w.market_id AND c.timeframe = '1m' AND c.is_final
 AND c.open_time >= date_trunc('minute', w.entry_at) - interval '5 minutes'
 AND c.open_time <  w.entry_at + interval '245 minutes' LIMIT 6000;   -- 5 020 linhas, cobertura completa
-- v14 por semana: agent_signals × signal_outcomes, cohort = 'prospective', direction = 'long'
```

**Aluguel, conferido de forma independente.** Nas 4 entradas que abriram ATA, −Δ SOL = 50 000 000 + prioridade +
5 000 + **1 488 440 exatos** (293 bytes × 5 080). Nas 6 sem ATA o resíduo é **0 exato**. A KB-0171 já tinha lido o
mesmo valor na cadeia (`getMinimumBalanceForRentExemption(165)` e o `createAccount` das 4 compras). O código desconta
`ATA_RENT_LAMPORTS = 2 039 280` (`spot_send_rules.py:27`, usado em `spot_send.py:298` e `spot_reconcile.py:320`).

**Funil da v14 desde 23/09** (sinais long; R do Lab, líquido). Nos 38 mercados mapeados, 44 sinais: executados 10
(−3,88 R), recusados por vaga cheia 15 (−4,38 R), por custo acima do teto em R 8 (+3,34 R), por impacto 4 (−0,24 R),
por ATA em tabela de consulta 1 (−1,05 R), e 6 sem ordem nenhuma (todos stop, −6,35 R). Total −12,6 R. Nos não
mapeados, 29 sinais (+2,30 R). Os +3,34 R recusados por custo não são resultado executável líquido (Astra).

Uma linha por operação, com MFE/MAE em USD e em alt/SOL, horários de toque e classe: [[Perdas-spot-1]].

## Hipóteses (propostas — NÃO estão na Fila; texto entregue ao dono da Fila)

O que é **bug** não vira hipótese: o aluguel (medir na transação) e **revalidar a condição de stop/alvo na cotação
que vai ser executada** são correções. As hipóteses, em ordem de valor:

- **H-c — a v14 paga o custo da `spot/1`?** É a que decide se a mesa continua. Reprecificar todos os sinais v14
  elegíveis nos mercados mapeados a partir do retorno **bruto**: tirar os 11 bp e o funding do `r_net` e aplicar
  0,25 %/perna ([[KB-0171-custo-real-da-spot-1]]), com a saída simulada em alt/SOL. A semana de seleção (14–20/09)
  fica fora do teste confirmatório. Bootstrap de blocos de dia. Refuta se o limite superior do IC 95 % da expectância
  líquida for ≤ 0. Não confirma se o IC cruzar zero.
- **H-a1 — geometria em alt/SOL.** Mesmos sinais e entradas, stop/alvo pelo ATR da série alt/SOL contra a geometria
  atual (corrigida), contraste emparelhado em SOL, mesma ficha, horizonte e custo. Só vale testar se a H-c não
  refutar: geometria não cria vantagem que o sinal não tem.
- **H-a2 — sinal medido em alt/SOL.** Experimento separado, em coorte futura, recalculando os gatilhos na razão.
  Melhorar nas 10 entradas escolhidas não confirma nada.

## Por que pode falhar

- **n = 10, 4 ativos (NEAR é metade), 6 dias, um regime.** Nada aqui estima a frequência de cotações fantasmas, o
  custo médio fora destas 10 nem dá para afirmar que o SOL prejudica de forma sistemática (o NEAR de 27/09 mostra o
  contrário).
- **A razão alt/SOL é reconstruída de fechamentos 1 m da Binance perp.** Não é o preço da pool, e máximas/mínimas da
  razão não existem: os MFE/MAE alt/SOL são aproximados.
- **As classes são triagem, não atribuição causal.** Cada classe olha a janela inteira, não o caminho.
- **A "semana de 07/09" da v14 começa em 09/09 19:48Z**, o primeiro sinal (a versão foi criada às 19:37Z), e tem
  98 sinais, dos quais só 65 são terminais. A soma de 202 terminais inclui a semana de seleção, então não é uma
  validação independente dela.

## Segunda opinião (Astra)

[[06-DECISIONS/Revisoes-Astra/KB-0172-perdas-spot-1|Revisão KB-0172]]. Concordou com a conta do aluguel e com o
efeito sobre stop/alvo, e citou uma proposta de redução de aluguel (SIMD-0437, patamar 5 080; não conferida por mim).
Também confirmou que a recotação da venda não reavalia o gatilho. Três correções, todas absorvidas: (1) dois eixos,
incidente × economia; (2) retornos brutos da mesma janela no lugar do R líquido do Lab, porque o `r_net` desconta
11 bp e funding; (3) `sinal_errado` passou a ser `movimento_adverso`. Na H-c, avisou que aplicar 0,3 R sobre um R já
líquido cobra o custo duas vezes. Ficou registrado que o contrafactual do UNI (+0,56 % até 18:30) é referência, não
fill.

## Relacionados

[[Perdas-spot-1]] · [[KB-0171-custo-real-da-spot-1]] · [[KB-0149-o-que-a-mesa-real-ensinou]] (§7: "se o sinal do Lab
tem vantagem fora da amostra" — 10 operações não respondem, os 202 sinais do Lab dizem ≈ 0) ·
[[KB-0145-binance-como-sinal-solana-como-execucao]] · [[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]] ·
[[03-TRADING/Spot/Mesa-spot-1|Mesa-spot-1]] · [[Open Bugs]] · [[Fila de Hipoteses]] · [[Mapa de Estrategias]]

## Correções no código (01/10/2026, risk-engine-guardian)

- **Cotação única (achado 5):** stop/alvo decididos na marca só vendem se uma **segunda** cotação do lote, a que a
  perna executa, disser o mesmo; senão nada é vendido no tique (nenhuma ordem, nenhuma tentativa gasta). Stop tem
  prazo de 60 s por episódio (início gravado na linha, sobrevive a reinício) e depois sai assim mesmo; alvo nunca é
  forçado; `time`/`sell_requested`/`emergency` não esperam. A Binance **não** virou portão (é a H-b, hipótese).
  Testado com as cotações do UNI 29/09 e do NEAR 26/09. `docs/RISK_ENGINE_MEME.md` §19.2; revisão
  [[06-DECISIONS/Revisoes-Astra/Spot-exit-confirm|Spot-exit-confirm]].
- **Aluguel constante (achado 1):** ver [[KB-0171-custo-real-da-spot-1]] (correção no código) e
  [[06-DECISIONS/Revisoes-Astra/Spot-ata-rent-fix|Spot-ata-rent-fix]].
- O que **não** muda: nada disto cria vantagem; a H-c continua sendo a pergunta que decide se a mesa continua.
