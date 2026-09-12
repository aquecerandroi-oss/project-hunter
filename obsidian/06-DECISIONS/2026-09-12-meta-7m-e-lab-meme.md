---
tags: [decisao, meme, pumpfun, meta, m4]
titulo: A meta de US$ 7 milhões em 30 dias e o Lab meme contínuo — quatro diretrizes do Everton
data: 2026-09-12
updated: 2026-09-12
owner: sexta-feira
origem: Everton, 2026-09-12, por volta de 04:5x BRT — turno de madrugada que abriu as tarefas T4.0-T4.6
status: registro
decided_on: 2026-09-12
by: everton
---

# A meta de US$ 7 milhões em 30 dias e o Lab meme contínuo

**Registrado por:** Sexta-feira (documentation-writer), a partir do brief do orquestrador desta
sessão. **Não é opinião nova** — é a consolidação de quatro diretrizes do Everton, cada uma já
com uma ou mais tarefas em execução no mesmo turno (T4.0 a T4.6). Nenhum número de mercado foi
medido por mim nesta nota; a aritmética da §2 é conta sobre o alvo declarado, nunca previsão de
retorno.

## 1. As quatro diretrizes, verbatim (2026-09-12, por volta de 04:5x BRT)

| # | Diretriz (verbatim) | Onde já aparece em execução nesta sessão |
|---|---|---|
| (a) | "US$ 7 milhões em 30 dias" no mercado de meme coins | `.claude/state/brief-T4.4-doutrina-execucao-pumpfun.md` ("vamos começar a operar ainda hoje"); [[KB-0090-a-meta-em-dinheiro]] já media a mesma classe de pergunta para o universo SPOT/perp antes do pedido de meme |
| (b) | "mapear cada canto do pump.fun" | `docs/plans/T4-MEME-RADAR.md`; [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] |
| (c) | "tudo sobre tendências vai anotando no Obsidian — o Obsidian vai ajudar a tomar decisão conforme a mente é alimentada" | esta mesma decisão e os hubs criados junto dela: [[03-TRADING/Meme/README|Meme (Trading)]], [[02-MARKET/Meme/README|Meme (Mercado)]], [[09-OPERATIONS/Diario-Meme/README|Diário Meme]], [[11-KNOWLEDGE/README-meme|Meme (Conhecimento)]] |
| (d) | "o Lab vai ficar em cima das meme coins simulando sem parar, com o Obsidian indo atrás, analisando e ganhando experiência em trade" | `.claude/state/brief-T4.6-lab-meme-continuo.md` (laço contínuo de paper trading na curva, um registro por dia) |

## 2. A aritmética do alvo — o que "US$ 7 M em 30 dias" exige, não o que ele promete

> [!alerta] Isto é conta sobre o alvo, não previsão de retorno
> As linhas abaixo respondem só "que multiplicador e que taxa diária composta esse alvo exige de um
> certo capital de partida, se todo dia fechasse igual e sem exceção" — nenhuma delas afirma que o
> Lab, a curva do pump.fun ou qualquer conjunto de regras vai entregar essa taxa. É a mesma
> disciplina da [[KB-0090-a-meta-em-dinheiro]]: a meta é decisão de capital, universo e expectancy,
> nessa ordem — nunca alavanca de vontade.

Fórmula usada, sem custo, sem imposto, sem retirada: dado um capital inicial `C` e um alvo `A` em
30 dias, o multiplicador é `A / C` e a taxa diária composta que fecha esse multiplicador em 30 dias
**se repetida todo dia sem exceção** é `r = (A / C)^(1/30) − 1`. Qualquer dia plano ou negativo no
meio do caminho empurra a taxa exigida dos dias restantes para acima do número desta tabela — a
tabela é o piso, não uma meta diária fixa.

| Capital de partida | Base do câmbio | Multiplicador até US$ 7.000.000 | Taxa diária composta exigida (30 dias, sem drawdown) |
|---|---|---|---|
| R$ 100.000 → ≈ US$ 20.000 | ≈ R$ 5,00/US$, arredondado pelo próprio Everton na diretriz; a última cotação USDT/BRL medida no projeto foi **5,1198** em 2026-09-11 05:05:35 BRT ([[KB-0090-a-meta-em-dinheiro]]) — este arredondamento é do Everton, não uma medição nova | **350×** | **≈ +21,6 %/dia** |
| US$ 100.000 | — (já em dólar) | **70×** | **≈ +15,2 %/dia** |

Cálculo: `350^(1/30) − 1 = 0,21563…` → 21,6 %/dia; `70^(1/30) − 1 = 0,15213…` → 15,2 %/dia.

**Contexto de escala (comparação, não proibição):** o teto medido do universo executável de hoje
(SPOT/perp, família `mean_reversion`, limites de risco atuais, [[KB-0090-a-meta-em-dinheiro]]) é
R$ 393,60/dia sobre R$ 100.000 de patrimônio — **≈ +0,39 %/dia**, cenário impossível de toda aposta
fechando +1 R. A taxa que a base de R$ 100.000 exige para o alvo de meme (+21,6 %/dia) é **≈ 55×**
maior que esse teto já medido em outro mercado. Isto não diz nada sobre a curva do pump.fun, que é
um instrumento diferente com dinâmica de preço, custo e volatilidade próprios
([[KB-0057-a-volatilidade-das-memes-e-o-piso-que-bane-o-btc]], [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]])
— é só a régua de quão fora da experiência medida do projeto o alvo está, para não tratar +21,6 %/dia
como um número pequeno.

## 3. O que NÃO muda

- **Dinheiro real só entra por switch explícito do Everton, depois do fluxo verificado.** Doutrina
  já registrada no brief da T4.4: `ENABLE_MEME_LIVE_TRADING`, padrão `false`, só o Everton liga; o
  desbloqueio pede N dias de paper com dado real de curva, os nove-equivalentes de verificação
  (V1–V9) verdes na VPS, um caminho manual comprovado, e então o switch — nunca automático. "Vamos
  começar a operar ainda hoje" (Everton, T4.4) foi traduzido nesse mesmo brief como **paper com dado
  real da curva**, não ordem assinada.
- **Paper primeiro, sempre.** Mesma doutrina que já vale para SPOT: "só declare o modo autônomo
  pronto quando o fluxo completo estiver verificado" — citada literalmente no brief da T4.4 como
  diretriz permanente do Everton, não específica de meme.
- **O funil é a única porta.** Nenhuma hipótese de meme vira estratégia viva sem pré-registro
  (`EXP-M<n>`, protocolo congelado antes de rodar, avaliações datadas append-only — mesmo formato de
  `_TEMPLATE-EXP.md`), sem simulação sobre a curva real (T4.5) e sem passar pela régua editorial já
  em vigor para `momentum`/`mean_reversion` (≥ 100 outcomes avaliáveis **e** ≥ 30 dias distintos, IC
  95 % por blocos de dia acima de zero, 2 de 3 janelas positivas — `docs/plans/SHADOW-LAB.md`,
  `docs/plans/REPLICATION.md`). A meta em dinheiro não abre atalho na régua.
- **A doutrina de risco do meme é um contrato irmão, ainda não escrito.** `docs/RISK_ENGINE_MEME.md`
  é responsabilidade da T4.4 (em execução nesta mesma sessão) e ainda **não existe** no repositório
  na data desta nota — hoje só há o brief que a encomenda. Quando existir, é ele (e não esta
  decisão) quem fixa tetos em SOL, kill switch, ausência de alavancagem e o escopo
  bonding-curve-buy/sell + PumpSwap-sell-only. Qualquer citação de número de risco nesta nota vem do
  brief, não de um contrato fechado — atualizar o link assim que `docs/RISK_ENGINE_MEME.md` existir.
- **O escopo continua só leitura para execução até segunda ordem.** `docs/plans/T4-MEME-RADAR.md`
  §0 já registra que T4.1–T4.3 não tocam `packages/risk-core`, `hunter_core.execution` nem
  `services/execution-worker` — o Meme Radar em si é monitoramento; a linha de paper trading (T4.5,
  T4.6) é simulação sobre dado real, nunca ordem on-chain.

## 4. Painel "Meta" — especificação para o Meme Radar (T4.3b)

**Planejado (T4.3b) — nada nesta seção está implementado; é a especificação a construir na tela
`/meme`** (`docs/plans/T4-MEME-RADAR-UI.md`), no mesmo espírito do painel de meta diária que já
existe para o universo geral (`GET /api/v1/orgs/{org}/lab/daily-goal`,
[[2026-09-10-validacao-em-um-dia-e-lucro-real]] §3: lucro sempre na moeda operada **e** convertido
pela cotação observada, com fonte e instante visíveis — nunca uma taxa adivinhada).

O painel tem exatamente quatro campos, cada um com a proveniência ao lado:

1. **Capital** — o saldo real da(s) `PaperCurveWallet` ativa(s) (T4.5/T4.6), em SOL, convertido para
   USD pela cotação SOL/USD observada (fonte + `observed_at`, mesmo padrão do `fx` do
   `daily-goal`). **Qual dos dois capitais de partida da §2 (R$ 100.000/US$ 20.000 ou US$ 100.000)
   é o oficial ainda não foi decidido pelo Everton** — o painel mostra o capital real em paper, não
   assume nenhuma das duas bases.
2. **Retorno diário exigido** — recalculado a cada dia a partir do capital corrente e dos dias
   restantes: `r_exigido = (7.000.000 / capital_atual)^(1/dias_restantes) − 1`. Os números da tabela
   da §2 (+21,6 %/+15,2 %) são só o ponto de partida do dia 0 com os capitais de exemplo — o painel
   nunca os trata como fixos.
3. **Retorno diário medido** — retorno realizado no paper naquele dia (PnL em SOL do dia dividido
   pelo capital do início do dia), na mesma régua do diário (§5 abaixo e o item 3 do brief
   `.claude/state/brief-T4.6-lab-meme-continuo.md`: apostas, acertos, R em SOL, PnL em SOL e USD,
   drawdown, por conjunto de regras, por dia).
4. **Dias restantes** — `30 − dias corridos desde a data de início do relógio`. **Qual data conta
   como início ainda é uma decisão em aberto**: 2026-09-12 (data desta diretriz) ou a data em que o
   T4.6 realmente começar a simular sem parar com dado ao vivo. O painel deve mostrar explicitamente
   qual das duas datas está usando — nunca escolher em silêncio.

Regra de honestidade que vale para os quatro campos, herdada dos quatro callouts
(`docs/OBSIDIAN.md` §2): **um campo sem leitura real fica em branco ou "—", nunca zero disfarçado de
medição.** Enquanto T4.5/T4.6 não estiverem no ar, "capital" e "retorno medido" não têm valor a
mostrar — isso é o próprio estado do sistema, não um erro a esconder.

## Relacionadas

[[KB-0090-a-meta-em-dinheiro]] · [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] ·
[[2026-09-10-validacao-em-um-dia-e-lucro-real]] · [[03-TRADING/Meme/README|Meme (Trading)]] ·
[[02-MARKET/Meme/README|Meme (Mercado)]] · [[09-OPERATIONS/Diario-Meme/README|Diário Meme]] ·
[[11-KNOWLEDGE/README-meme|Meme (Conhecimento)]] · `docs/plans/T4-MEME-RADAR.md` ·
`docs/plans/T4-MEME-RADAR-UI.md`

## Fontes

Diretriz verbal do Everton, 2026-09-12, por volta de 04:5x BRT (repassada ao documentation-writer
pelo orquestrador desta sessão) · `.claude/state/brief-T4.4-doutrina-execucao-pumpfun.md` ·
`.claude/state/brief-T4.5-simulador-curva.md` · `.claude/state/brief-T4.6-lab-meme-continuo.md` ·
`docs/plans/T4-MEME-RADAR.md` · `docs/plans/T4-MEME-RADAR-UI.md` ·
`.claude/state/notes-D-P19.md` (via [[KB-0090-a-meta-em-dinheiro]], câmbio de 2026-09-11)
