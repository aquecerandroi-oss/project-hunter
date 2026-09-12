# 0006 — Separar a doutrina de execução meme (pump.fun/Solana) do Risk Engine SPOT e exigir fluxo verificado antes de qualquer transação assinada

- **Status:** proposto em 2026-09-12 (aguarda decisão do Everton nos sete pontos da §14 de `docs/RISK_ENGINE_MEME.md`)
- **Data:** 2026-09-12

## Contexto

Em 2026-09-12 o Everton apontou as memecoins da pump.fun como alvo real e pediu para "começar a
operar ainda hoje" numa carteira Solana nova, exclusiva do Hunter. O que existe hoje é: o plano do
Meme Radar (`docs/plans/T4-MEME-RADAR.md`, monitoramento apenas), o adapter público
(`packages/exchange-adapters/hunter_exchanges/pumpfun/**`, T4.1) e o mapa on-chain completo
(`docs/PUMPFUN-ONCHAIN.md`, T4.0d). Não existe motor de risco, coletor, carteira, simulador de curva
nem qualquer caminho de assinatura de transação.

Ao mesmo tempo, o contrato de risco que existe (`docs/RISK_ENGINE.md` v2.5) é **inteiramente** SPOT
com livro real: `limits.py:124` recusa `max_leverage != 1` citando a regra 6 da diretiva,
`checks.py:80-84` exige `LONG` + `MarketType.SPOT`, `MarketType` só tem `spot` e `perpetual`
(`enums.py:115`) e `MarketLiquidity` exige `asks[]`/`spread_pct`. Uma bonding curve não tem livro: o
preço é uma função determinística de duas reservas virtuais. A revisão da Astra
(`.claude/state/astra-review-t40-pumpfun.md`) já havia nomeado o risco: *"disfarçar reservas como
book aprova uma simulação sem modelar assinatura, blockhash, confirmação, MEV e migração; stop pode
não executar"*.

A tensão a resolver, portanto, não era técnica — era de governança: como atender "operar hoje" sem
que "hoje" signifique uma chave privada e uma transação assinada por um sistema que nunca foi
verificado, contrariando a própria diretiva dele de 2026-09-06 (*"só declare o modo autônomo pronto
quando o fluxo completo estiver verificado"*).

## Decisão

Escrever a doutrina **antes** do código, em `docs/RISK_ENGINE_MEME.md` (contrato v0.1), como um
**motor separado** do SPOT, e amarrar dinheiro real a três portões independentes — engenharia
(VM1–VM9 verdes + 7 dias de papel reconciliados), evidência (EXP-M1 com o funil já acordado com a
Astra) e o interruptor `ENABLE_MEME_LIVE_TRADING`, que só o Everton liga depois de digitar
`SOLANA_WALLET_SECRET_KEY` no `.env` da VPS.

O que a decisão fixa:

| Item | Conteúdo |
|---|---|
| Escopo | compra/venda na bonding curve e **venda** no PumpSwap; nada mais; allowlist por endereço de programa, com recusa nomeada para o resto |
| Motor | pacote novo **proposto** `packages/risk-core/hunter_risk_meme/`, puro e determinístico; `hunter_risk` **não muda** e não é importado nem importa |
| Unidade de risco | **o SOL gasto inteiro** por compra — numa curva o "stop" não é garantia, então o risco por operação é o teto em SOL, não a distância ao stop |
| Política de capital (só do Everton) | `MEME_WALLET_MAX_SOL`, `MEME_MAX_SOL_PER_TRADE`, `MEME_DAILY_LOSS_CAP_SOL` (**latched**, retomada só por OWNER), nº de posições, exposição por mint, tetos de priority fee e de tip Jito |
| Parâmetros de estratégia (da hipótese) | idade, janela de progresso, limiares de bundled/top-10, múltiplo-alvo, trailing, time stop — revisáveis por evidência, nunca confundidos com política |
| Falhar fechado | `unavailable` reprova; insumo nulo (bundled share, fluxo do criador, volume do minuto) **recusa** — consequência declarada: só com os canais gratuitos o motor aprova **zero** compras |
| Execução | verificação obrigatória da transação **antes** de assinar (allowlist de programas, signatário único, destinos, `max_sol_cost` conferido contra o nosso cálculo, CU, blockhash); idempotência por `client_order_id` derivado do `proposal_id` **e** pela assinatura; reserva de 5 s; fill = `TradeEvent` confirmado, nunca o envio |
| Segredo | `SOLANA_WALLET_SECRET_KEY` só no `.env` da VPS, lido por **um** processo (`services/meme-executor/`, proposto), nunca em log/métrica/heartbeat/API |
| Flag | `ENABLE_MEME_LIVE_TRADING`, default `false`, documentada ao lado de `ENABLE_LIVE_TRADING`; adaptador live levanta `MemeLiveTradingDisabled`; o processo recusa subir com a flag `true` e verificações vermelhas |

## Alternativas consideradas

- **Estender `hunter_risk` com um `market_type` de curva.** Rejeitado: exigiria afrouxar o validador
  que hoje recusa qualquer `max_leverage != 1` e ensinar todo consumidor de `MarketType` a lidar com
  um terceiro caso — uma mudança na doutrina SPOT do Everton como efeito colateral de uma classe de
  ativo nova.
- **Mapear reservas da curva para `MarketLiquidity.asks[]`** e reusar `book_depth`/`slippage_estimate`.
  Rejeitado, e é o achado central da Astra: seria fabricar um livro. A curva permite algo **melhor** —
  o impacto da própria ordem é exato pela fórmula —, então o motor meme ganha `price_impact` e
  `participation` em vez de um livro falso.
- **Começar com uma transação real minúscula ("só 0,01 SOL para provar o caminho").** Rejeitado: é
  exatamente a exceção que a diretiva proíbe, e o valor pequeno não reduz nenhum dos riscos que a
  verificação existe para pegar (duplo envio, transação adulterada, vazamento de chave).
- **Usar a Lightning Transaction API do PumpPortal** (eles assinam). Rejeitado sem discussão: exigiria
  a chave fora da nossa caixa; custa 1 % contra 0,5 % da Local; e nenhuma verificação nossa da
  transação seria possível.
- **Adotar a Local Transaction API como caminho definitivo.** Rejeitado como caminho de dinheiro
  real: são **0,5 % por trade** sobre os 1,25 % da curva (lido na página oficial de fees em
  2026-09-12) e a nossa intenção completa (carteira, mint, tamanho, slippage, prioridade) sai da
  nossa caixa antes de existir na cadeia. Aceito apenas para papel/devnet e comparação.
- **Deixar `MEME_DAILY_LOSS_CAP_SOL` reavaliado a cada ciclo, como o SPOT.** Rejeitado: a marca de
  uma meme oscila dezenas de por cento em minutos, e destravar por oscilação apagaria o limite. A
  trava é **latched**, com retomada manual do OWNER.

## Consequências

- **Fica mais fácil:** simular com honestidade (a curva é fórmula fechada, ao contrário do livro
  SPOT); testar o motor por tabela de casos; provar que a fronteira SPOT/meme existe (um teste de
  import).
- **Fica mais difícil, de propósito:** operar. Com só os canais gratuitos do PumpPortal o motor
  recusa **todas** as compras (checks 10, 11, 12 e 21 `unavailable`), então "ligar o radar" não é
  "ligar o robô" — falta uma decisão paga ou um decodificador on-chain próprio.
- **Três pendências que bloqueiam execução real**, todas registradas em `docs/RISK_ENGINE_MEME.md`
  §13: o `forbidden_patterns.sh` não cobre `ENABLE_MEME_LIVE_TRADING=true`; `CURVE_TRADE_FEE_PCT`
  como constante de contabilidade (a taxa é por tier — usar o `TradeEvent`); e o dedupe de
  `meme_trades` por `(signature, ts)`, que perde eventos dentro da mesma transação (MUST-FIX 2 da
  Astra, ainda aberto).
- **Sete decisões do Everton** ficam explicitamente pendentes (§14): valores de política, limiares de
  aviso, Mayhem, auto-close em EMERGENCY, caminho de execução, feed pago, e o reconhecimento de que
  nem β nem o piso de 50 M USDT de volume se aplicam a esta classe.
- **A revisitar quando:** (a) os valores live existirem; (b) T4.2 entregar volume/holders/criador;
  (c) o simulador T4.5 produzir os primeiros 7 dias reconciliados; (d) as VM1–VM9 existirem. Cada uma
  muda uma seção nomeada do contrato, não o contrato inteiro.

## Referências

`docs/RISK_ENGINE_MEME.md` v0.1, `docs/RISK_ENGINE.md` v2.5 (§2–§5, §7.1, §8, §10, §11),
`docs/PUMPFUN-ONCHAIN.md` (T4.0d, IDL commit `9c82f61`), `docs/plans/T4-MEME-RADAR.md`,
`.claude/state/astra-review-t40-pumpfun.md`, `.claude/state/astra-review-t40-plano-meme-radar.md`,
`.claude/state/notes-T4.0.md`, `.claude/state/notes-T4.0b.md`, `.claude/state/notes-T4.1.md`,
`.claude/state/spec-T3.9-verificacoes.md` (as V1–V9 do SPOT que as VM1–VM9 espelham),
`.claude/state/brief-T4.4-doutrina-execucao-pumpfun.md`, `.claude/state/notes-T4.4.md`,
ADR `0005` (a diretiva de risco de 2026-09-06, que este ADR não altera).
