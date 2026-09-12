# Notas T4.4 — doutrina de execução pump.fun (contrato antes do código)

Execução em 2026-09-12, madrugada BRT (hora de servidor externo confirmada:
`Date: Sat, 12 Sep 2026 05:37:03 GMT` = 02:37 BRT). Papel: `risk-engine-guardian`.
Status: **DONE_WITH_CONCERNS** — entrega documental completa; quatro achados abertos (§4 abaixo),
sete decisões pendentes do Everton. **Nenhum commit. Nenhum código. Nenhum `.env*` tocado.**

## 1. Arquivos

| Arquivo | O que é |
|---|---|
| `docs/RISK_ENGINE_MEME.md` (novo, 687 linhas) | contrato v0.1: escopo, insumos puros, política da carteira/chave/flag, 25 checks com nome de recusa, sizing, saídas, kill switch latched, falhar fechado, caminho de execução com modelo de confiança, simulador de papel, VM1–VM9, definição de "fluxo completo verificado", "o que muda no motor atual", perguntas ao Everton, proveniência |
| `docs/decisions/0006-doutrina-de-execucao-meme-pumpfun-solana.md` (novo) | ADR **proposto** (não aceito): motor separado + três portões antes de dinheiro real; seis alternativas rejeitadas com motivo |
| `docs/decisions/README.md` (editado) | uma linha no índice |
| `docs/DEPLOYMENT.md` (editado) | três linhas na tabela "Feature flags de sistema", ao lado de `ENABLE_LIVE_TRADING`: a flag meme, a variável da chave e os três tetos — cada uma marcada **"proposta (T4.4) — nenhum processo lê hoje"** |
| `.claude/state/brief-T4.4-doutrina-execucao-pumpfun.md` (novo) | brief verbatim, como pedido |
| `.claude/state/notes-T4.4.md` (este) | — |

## 2. Lido antes de escrever

`docs/RISK_ENGINE.md` v2.5 inteiro (§1 insumos, §2 perfil e as três recusas de perfil, §3 checks e
os dois parágrafos de idade do volume, §4 sizing/limitante/participação, §5 kill switch, §6 β, §7 e
§7.1 as pré-checagens do worker, §8 garantias, §10 tentativa × intenção, §11 escopo de capital),
`docs/PIPELINE.md` §7/§8, `docs/ARCHITECTURE.md` §6, `docs/PUMPFUN-ONCHAIN.md` (T4.0d — apareceu na
árvore durante esta tarefa; §1.3 instruções, §1.4 eventos, §1.4b taxas por tier, §6 o que a execução
precisa), `docs/plans/T4-MEME-RADAR.md` (inclusive §8b e o adendo Mayhem),
`.claude/state/astra-review-t40-pumpfun.md`, `astra-review-t40-plano-meme-radar.md`,
`notes-T4.0.md`, `notes-T4.0b.md`, `notes-T4.1.md`, `spec-T3.9-verificacoes.md` (§0 e a lista
canônica V1–V9), `notes-T3.70.md` (a tabela V1–V9 → arquivo → resultado que as VM espelham),
`docs/decisions/{README,0005}.md`, `docs/SECURITY.md` §4/§8, `docs/DEPLOYMENT.md` (flags),
`packages/exchange-adapters/hunter_exchanges/pumpfun/{curve,models}.py`,
`packages/risk-core/hunter_risk/{limits,checks,inputs}.py`, `packages/core/hunter_core/domain/enums.py`,
`packages/core/hunter_core/execution/pricing.py`, `infra/scripts/forbidden_patterns.sh`.
`docs/PUMPFUN.md` não existe (só `PUMPFUN-ONCHAIN.md`).

## 3. Decisões de doutrina que este contrato toma (e a razão de cada uma)

1. **Motor separado, `hunter_risk` intocado.** Não é preferência: `limits.py:124-126` recusa
   `max_leverage != 1`, `checks.py:80-84` exige `LONG` + `MarketType.SPOT`, `MarketType`
   (`enums.py:115`) só tem `spot`/`perpetual` e `MarketIdentity`/`MarketLiquidity`
   (`inputs.py:39`) exigem exchange/symbol e livro. Reusar exigiria fabricar um livro a partir de
   reservas — o achado que a Astra já nomeou.
2. **O risco de uma compra na curva é o SOL gasto inteiro**, não a distância ao stop: numa curva o
   stop não é garantia (rug, venda que falha por slippage, liquidez real zero). É o que justifica
   caps em SOL em vez de `risk_per_trade_pct`, e é a maior diferença conceitual com o SPOT.
3. **Política de capital (só do Everton) separada de parâmetro de estratégia (da hipótese).** Os
   valores da coluna "papel" da §3.1 são parâmetros do EXP-M1; a coluna "live" está vazia de
   propósito.
4. **Trava diária latched** (diferente do SPOT, que reavalia a cada ciclo): a marca de uma meme
   oscila dezenas de por cento em minutos e destravar por oscilação apagaria o limite.
5. **Nenhuma liquidação automática em EMERGENCY** — mantém a §5 do contrato SPOT; numa curva sem
   comprador, liquidar é realizar a perda máxima. Se o Everton quiser o contrário, é decisão dele
   (pergunta 4), não default nosso.
6. **Idempotência tem duas chaves aqui:** `client_order_id` derivado do `proposal_id` (como no SPOT)
   **e** a assinatura da transação — porque blockhash novo = assinatura nova = compra nova. Sem
   isso, "timeout → retentativa" compra duas vezes.
7. **Fill é o `TradeEvent` confirmado**, e as taxas da contabilidade saem do evento, não da
   constante 1,25 % (a taxa é por tier no programa — T4.0d §1.4b).
8. **Papel nunca simula um caminho mais barato do que o live vai usar** (os 0,5 % do PumpPortal
   Local entram no papel se o live for por ele).
9. **Recusar por falta de dado é a regra, e a consequência é declarada:** com só os canais
   gratuitos, o motor aprova **zero** compras. Preferi escrever isso em caixa alta no §0 e §4 a
   entregar um contrato que aparenta operar.

## 4. Achados (arquivo:linha — severidade — cenário)

1. `infra/scripts/forbidden_patterns.sh:144` — **MÉDIO** — o padrão
   `ENABLE_LIVE_TRADING[[:space:]]*=[[:space:]]*true` não casa `ENABLE_MEME_LIVE_TRADING=true`.
   Cenário: compose/py com a flag meme `true` passa verde, e a recusa de boot equivalente ainda não
   existe para o executor meme.
2. `infra/scripts/forbidden_patterns.sh:144` — **MÉDIO** — o mesmo padrão exige a forma `=`, mas
   `infra/docker/docker-compose.yml:566` usa a forma YAML `ENABLE_LIVE_TRADING: "false"`. Probe
   colado na §5: a forma com `:` **passa livre**. Cenário: compose editado para `"true"`, gate
   verde; só a recusa de boot (`config.py:107`, `LiveTradingRefused`) impede — dinheiro não se move,
   mas a defesa é uma camada mais fina do que a documentação promete.
3. `packages/exchange-adapters/hunter_exchanges/pumpfun/curve.py:41` — **BAIXO (documental)** —
   `CURVE_TRADE_FEE_PCT = 1.25` descreve o tier de hoje, não uma taxa de protocolo. Cenário: o tier
   muda, a contabilidade continua debitando 1,25 % e o PnL divirge do extrato on-chain sem teste
   falhar. Mitigado no contrato (§9.6: taxa vem do `TradeEvent`).
4. `docs/plans/T4-MEME-RADAR.md` §5 — **MÉDIO para execução** — `meme_trades` com PK
   `(signature, ts)` não distingue instruções dentro da mesma transação (MUST-FIX 2 da Astra, ainda
   aberto). Cenário: bundle com criação de ATA + compra, ou duas trades na mesma tx, contam como
   uma — e a reconciliação obrigatória da §9.6 compara a cadeia com uma linha que já perdeu evento.
   Execução real não pode ser liberada antes disso fechar.

## 5. Comandos e saída real

### Leituras públicas datadas (read-only, sem chave)

```
$ timeout 60 curl -sSI -L "https://pumpportal.fun/" | grep -i "^date:"
Date: Sat, 12 Sep 2026 05:37:03 GMT

$ for u in .../local-trading-api .../local-trading-api/trading-api .../trading-api/setup /docs /
404  https://pumpportal.fun/local-trading-api
200  https://pumpportal.fun/local-trading-api/trading-api
200  https://pumpportal.fun/trading-api/setup
404  https://pumpportal.fun/docs
200  https://pumpportal.fun/
```

- `pumpportal.fun/local-trading-api/trading-api` → `POST https://pumpportal.fun/api/trade-local`,
  campos `publicKey, action, mint, amount, denominatedInSol, slippage, priorityFee, pool`; devolve
  transação serializada assinada **localmente** pelo cliente.
- `pumpportal.fun/fees` → **Local 0,5 % por trade** ("calculada antes do slippage"), Lightning 1 %,
  dados: `subscribeNewToken`/`subscribeMigration` sem custo, trades a 0,01 SOL/10.000 eventos;
  nenhuma inclui rede nem a taxa da curva.
- `pumpportal.fun/local-trading-api/jito-bundles` → body em **array**, até 5 transações,
  `priorityFee` da primeira é o **tip** (os demais ignorados), envio a
  `https://mainnet.block-engine.jito.wtf/api/v1/bundles`.
- `pump.fun/docs/fees` (HTTP 200, "Last Updated: 20 May 2026") → curva **1,25 %** (creator 0,300 % +
  protocol 0,950 % + LP 0 %); criar 0 SOL; graduação 0,015 SOL; USDC como quote desde 21/05/2026;
  PumpSwap por tier (`preço × 1 bilhão`): **1,25 % em 0–420 SOL**, 0,30 % só acima de 98.240 SOL —
  ou seja, **vender logo após a migração custa 1,25 %, não 0,30 %**.

### Probe do guardião de padrões proibidos

```
$ for s in 'ENABLE_LIVE_TRADING=true' 'ENABLE_LIVE_TRADING: "true"' \
           'ENABLE_MEME_LIVE_TRADING=true' 'ENABLE_MEME_LIVE_TRADING: "true"'; do ... done
ENABLE_LIVE_TRADING=true           -> PEGA
ENABLE_LIVE_TRADING: "true"        -> PASSA LIVRE
ENABLE_MEME_LIVE_TRADING=true      -> PASSA LIVRE
ENABLE_MEME_LIVE_TRADING: "true"   -> PASSA LIVRE
```

### Fronteira SPOT/meme e ausência das variáveis novas

```
$ grep -rniE "solana|pumpfun|bonding" packages/risk-core/hunter_risk services/execution-worker/hunter_execution_worker --include="*.py"
sem ocorrências (exit 1)

$ grep -rn "ENABLE_MEME_LIVE_TRADING\|SOLANA_WALLET_SECRET_KEY\|MEME_DAILY_LOSS_CAP_SOL" --include="*.py" --include="*.yml" --include="*.sh" --include="*.example" .
sem ocorrências (exit 1)

$ grep -n "max_leverage" packages/risk-core/hunter_risk/{limits,checks}.py
checks.py:83:            and limits.max_leverage == _ONE,
limits.py:124:        if self.max_leverage != _ONE:
limits.py:126:  "max_leverage must be exactly 1: directive §6 is spot only, with no borrowing"

$ grep -n "class MarketType" packages/core/hunter_core/domain/enums.py   → 115 (só SPOT e PERPETUAL)
$ grep -n "LiveTradingRefused" services/execution-worker/hunter_execution_worker/config.py → 37, 52, 53 (+ raise em 108)
```

### Lint do próprio contrato (o "teste" desta entrega documental)

`/tmp`-scratch `t44check.py` confere: as 17 seções obrigatórias do brief, numeração 1..N dos checks,
todo check com ≥ 1 nome de recusa, nenhum nome de recusa repetido, VM1–VM9 presentes com comando
demo, e ausência de qualquer padrão de segredo no texto. Primeira rodada **falhou** (parser do lint
não aceitava dígito no nome `top10_share`) — corrigido o lint, não o contrato:

```
$ timeout 290 uv run python <scratch>/t44check.py
checks numerados: 25
nomes de recusa distintos: 46
comandos demo VM: 9
OK: contrato consistente
```

### Não rodado até o fim

`timeout 290 bash infra/scripts/forbidden_patterns.sh` (árvore inteira) **estourou os 290 s e foi
morto pelo `timeout`** (`exit=124`) — não houve veredito, e registro isso em vez de afirmar verde.
Não é bloqueante para esta entrega: o próprio script exclui `docs/*` e `*.md`
(`is_excluded_path`), e esta tarefa só escreveu `.md`. Observação operacional para quem for rodar o
gate num pre-commit: nesta árvore ele leva **mais de 290 s**.

## 6. Pendências que este documento deixa abertas de propósito

1. Os sete pontos da §14 do contrato (valores de política, limiares de aviso, Mayhem, auto-close em
   EMERGENCY, caminho de execução, feed pago de trades, β/piso de volume não se aplicarem).
2. Validade do blockhash em slots — **não reconfirmada** nesta rodada; a ser fixada contra
   `solana.com/docs` antes de qualquer retentativa real (§9.4 do contrato).
3. Mcap de moeda Mayhem (supply 2 bilhões) contra a régua de tier "preço × 1 bilhão" — divergência
   não resolvida; mais uma razão para recusar Mayhem em v0.
4. O ADR 0006 está **proposto**: se outro agente criar um 0006 em paralelo, renumerar aqui (o índice
   estava com 0005 como último quando escrevi).
5. Tabelas `meme_*` de execução (proposta na §13) são dono de `docs/DATABASE.md`, tarefa futura.
