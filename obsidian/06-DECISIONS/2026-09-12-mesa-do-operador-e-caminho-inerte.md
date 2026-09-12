---
tags: [decisao, meme, pumpfun, execucao, mesa, m4]
titulo: A Mesa do operador em papel e o caminho de assinatura construído inteiro e mantido inerte
data: 2026-09-12
updated: 2026-09-12
owner: sexta-feira
origem: Everton, 2026-09-12, por volta de 04:0x BRT — "já quero completamente funcional para operarmos; quero dar o aval da compra do meme, quanto de espera, vender; preciso o trader total funcionando"
status: registro
decided_on: 2026-09-12
by: everton
---

# A Mesa do operador em papel e o caminho de assinatura inerte

**Registrado por:** Sexta-feira (orquestradora), ao fim do turno de madrugada que entregou T4.6, T4.7 e
T4.8 (commits `f7edcfe`, `a153478`, `4a0c865`; VPS em `4a0c865` às 06:03 BRT). Esta nota fixa **o que foi
decidido sobre a forma do "trader total"** e **o que continua sendo decisão só do Everton**. Nenhum
número de mercado é medido aqui; os números de produção citados têm hora e vêm do heartbeat e do banco.

## 1. O pedido e a leitura que fizemos dele

O Everton pediu o trader completo com ele no circuito: **aval da compra**, **espera** (quanto tempo
segurar) e **venda**. A leitura: um fluxo de operador — proposta → aval → compra na curva → espera que
ele define → venda por regra ou "vender agora" → resultado em SOL e US$ — que nasce **em papel sobre
dado real** e que o mesmo código executa de verdade quando a chave e a flag existirem. Não é um
"modo demo": é o motor final com a última porta fechada.

## 2. O que foi decidido (e por quê)

| # | Decisão | Motivo | Onde está |
|---|---|---|---|
| (a) | A aposta é sempre `mode = 'paper'` hoje; `mode = 'live'` é recusado por CHECK no banco | "só declare o modo autônomo pronto quando o fluxo completo estiver verificado" (diretiva de 05/09) e `docs/RISK_ENGINE_MEME.md` §12 (três portões, hoje todos em zero) | migração `0022_meme_lab` |
| (b) | Dois conjuntos de regras: `meme_paper_v0/1` (`research_only`, aprova sozinho, pré-registro [[EXP-M1-comprar-cedo-na-curva]]) e `operator/1` (só propõe e **espera o aval**) | separar "o que o Lab acha" de "o que o Everton autoriza"; o Lab mede a taxa-base sem ninguém no circuito, a mesa mede o operador | `meme_rule_sets` |
| (c) | O fill é **sempre na fotografia seguinte** da curva (`observed_at > decided_at`), nunca no preço visto; a venda idem | não-antecipação (a regra do Lab inteiro); um meme anda em segundos e o preço visto já morreu | `paper_engine.py`, T4.5 |
| (d) | Risco inicial de uma compra na curva = **o SOL gasto inteiro** | `docs/RISK_ENGINE_MEME.md` §5: stop não é garantia numa curva | `meme_paper_bets.initial_risk_sol` |
| (e) | Taxa de papel 1,75 % por ponta (1,25 % curva + 0,5 % do caminho local) | papel nunca simula caminho mais barato que o live (§10.2) | T4.5 |
| (f) | Tetos de PAPEL do conjunto `operator`: carteira 2,0 SOL, 0,05 SOL por aposta, perda do dia 0,20 SOL | valores para a simulação; **os valores live são do Everton** (§14 da doutrina) | seed da 0022 |
| (g) | A API do operador escreve só decisão/manual/comandos; nunca cotação nem aposta; toda ordem com `Idempotency-Key` e `audit_logs` | o motor é a autoridade; a tela só diz por que um botão está desligado | `routers/meme_desk.py` |
| (h) | O caminho de assinatura (T4.8) é construído **inteiro** — instruções byte a byte iguais às do site, cotação local, verificador adversarial, `simulateTransaction` obrigatório — e fica **inerte** atrás de `ENABLE_MEME_LIVE_TRADING` + `SOLANA_WALLET_SECRET_KEY` + `meme_gates.json` | quando o Everton ligar, o código que roda é o que já foi provado; ligar não pode ser o primeiro teste | `hunter_core.execution.meme`, `pumpfun/tx.py` |

## 3. O que ficou provado hoje (com hora)

- Simulação real na mainnet (`simulateTransaction`, `sigVerify=false`, 04:59 BRT): `buy` ok 65 345 CU,
  `sell` ok 55 284 CU; `max_sol_cost − 1` ⇒ `TooMuchSolRequired` (a cotação bate o limiar exato).
- Paridade byte a byte com a CPI do roteador do site (18 contas) e com o `sell` de um bot (17 contas).
- 15 adulterações de transação recusadas por nome pelo verificador §9.1.
- A chave: lida uma vez, removida do ambiente, ausente de repr/logs/tracebacks/heartbeat; boot com a
  flag ligada e sem portões ⇒ `MemeLiveTradingRefused` **antes** de tocar na chave.
- Laço vivo em produção (06:04 BRT): 2 conjuntos ativos, 246 linhas avaliadas por tick, 0 propostas —
  o portão da EXP-M1 recusa toda linha por `creator_net_seller_unknown` / `curve_volume_1m_unknown`
  (fontes grátis) e `progress_unknown` em 117/123 (o denominador do progresso só é escrito quando a
  primeira observação tem `real_sol = 0`). Isto é honesto e é o próximo trabalho (T4.2c/T4.2d), não um
  ajuste de limiar.

## 4. O que continua sendo só do Everton

1. Os valores **live** da carteira meme (teto da carteira, por aposta, perda do dia, posições, cooldown).
2. Recusar Mayhem no v0 ou ter política própria.
3. Liquidar ou não em EMERGENCY (numa curva, liquidar realiza o pior preço).
4. PumpPortal (+0,5 %/trade, intenção entregue a terceiro) ou as nossas instruções (caminho B, já
   construído) — recomendação: B para dinheiro real.
5. Feed de trades pago (0,01 SOL / 10 000 eventos) ou o `swap-api` do próprio site (T4.2c, em curso);
   RPC com chave (Helius/QuickNode) ou o público.
6. Se aceita os portões A/B da doutrina (7 dias de papel; ≥ 100 operações em 30 dias) antes de ligar, ou
   autoriza um teste menor — **decisão explícita, escrita, dele**.
7. A carteira nova: criada só quando ele decidir ligar; chave digitada só no `.env` da VPS.

## 5. Ligações

- Contrato entre laço e mesa: `.claude/state/contrato-T4.6-T4.7-mesa-meme.md` (18 emendas).
- Doutrina: `docs/RISK_ENGINE_MEME.md`; ADR 0006; caminho on-chain: `docs/PUMPFUN-ONCHAIN.md` §6b.
- Meta e Lab contínuo: [[2026-09-12-meta-7m-e-lab-meme]]; alvo: [[README-meme]].
- Diário meme do dia: gerado por `infra/scripts/meme_diary.py` quando houver a primeira aposta fechada
  (hoje nenhuma; a pasta `09-OPERATIONS/Diario-Meme/` continua só com o formato).
