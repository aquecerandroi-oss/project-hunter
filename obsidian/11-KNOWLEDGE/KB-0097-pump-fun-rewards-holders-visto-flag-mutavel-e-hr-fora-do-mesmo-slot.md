---
tags: [knowledge, nota, plantao, meme, pumpfun, holder-rewards, instrumento, contrato]
tema: memecoin / pump.fun / o rótulo "Rewards → holders" foi visto pela primeira vez numa moeda (2 páginas; lista, detalhe, imc e board `new` `true` nos mesmos mints — superfícies do mesmo operador); `is_holder_reward` observado `true` em moedas graduadas antes do upgrade de 12/09 (HR em moedas antigas — conversão compatível, não comprovada; o flag não é atributo de criação); nenhuma das 23 graduadas HR do board graduou no mesmo slot (0/23 vs 63/103 não-HR — proxy temporal, descrição) — adendo datado à KB-0096 em nota própria
fonte: `pump.fun/coin/{mint}` ×2 (texto SSR); `frontend-api-v3.pump.fun` (`/coins` newest ×2 e `complete=true` ×2, `/coins/{mint}` ×10, `/coins/mayhem-mode`, top-50); `advanced-indexer.pump.fun` (`boards/{new,graduated ×3,graduating,movers}`, `in-memory-coin` ×2)
fonte_url: https://pump.fun/coin/8WKCZMvdySkco6m4R6eSRcWGRrPWHcRHLPXaMJ6nWqyv
lido_em: 2026-09-15
evidencia: medição própria (plantão T4.64, run 21, lane 1, 17:45:00–17:45:40 BRT; 28 GETs a hosts pump.fun, 28 × 200; brutos em `.claude/state/plantao-meme/raw-lane21/`); tudo observado na REST/indexer/página do mesmo operador com `received_at` nosso — o byte `is_holder_reward` e o `creator_fee_bps` da `BondingCurve` não foram lidos nesta run (a T4.8c já os leu — KB-0096, adendo; pendente é a validação prospectiva por fonte); 2 páginas, 2 moedas pré-upgrade, 23 vs 103 graduadas numa tarde — descrição, não taxa nem mecanismo
hipotese_testavel: sim
astra: ver seção Astra (run 21; parecer em `.claude/state/astra-review-plantao-meme-20260915-1725.md`)
status: vivo
owner: sexta-feira
updated: 2026-09-15
confiança: "?"
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# KB-0097 — pump.fun: "Rewards → holders" visto numa moeda, `is_holder_reward` observado em moedas antigas (conversão compatível) e HR fora do mesmo slot

**Adendo datado à KB-0096, em nota própria** (parecer da Astra do run 21: "publicaria como adendo da KB-0096"; esta lane só cria KBs novas — o orquestrador pode fundir).
**Plantão T4.64, run 21, lane 1 (15/09 17:25–18:1x BRT), primeira leitura da noite após o segundo deploy do programa (≈ 07:34 BRT, KB-0096).** Rascunho: `.claude/state/plantao-meme/2026-09-15-1725-lane1.md`
(itens 1, 3, 4, 8). Brutos: `.claude/state/plantao-meme/raw-lane21/` (`40_coinpage_hrT_*`, `20_coin_hrT_*`, `21_coin_hrF_*`, `30_imc_hrT_*`, `10–12_boards_graduated_*`, `14_boards_movers.json`, `_analysis.json`).
Continua a [[KB-0095-pump-fun-rotulos-observados-do-site-da-rest-e-os-limites-on-chain|KB-0095]] (templates do bundle; "holders" **não visto** em 12/09) e a
[[KB-0096-pump-fun-is-holder-reward-na-rest-e-o-segundo-deploy-de-15-09-2026|KB-0096]] (primeiros positivos na REST às 16:19; "holders" ainda não visto numa página).

## O fato medido

| o quê | valor | como/onde | lido em (BRT) |
|---|---|---|---|
| **rótulo da página "Rewards → holders"** (primeira observação numa moeda) | **2/2**: POO (`8WKCZMvd…`, "44s ago") e Giveback (`8sQ6oSPs…pump`, "47s ago") — texto SSR "Chain and launchpad : Pump · Creator rewards recipient : **Rewards → holders**", **sem percentual** (o template `rewards_to_holders_with_fee` "· {{percent}}%" existe no bundle e não foi o renderizado); as 4 chaves i18n presentes | `https://pump.fun/coin/{mint}` (HTML 2,05 MB não gravado; janelas de texto em `40_coinpage_hrT_0{1,2}_*.json`) | 17:45:37–17:45:40 |
| concordância nos mesmos 2 mints (POO, Giveback) | lista `/coins` **true**, detalhe `/coins/{mint}` **true**, `in-memory-coin` `isHolderReward` **true** (`numHolders` 0, `progress` 0 aos 20 s), board `new` `hr` **true**, página **holders** — cinco superfícies do mesmo operador, **não** cinco confirmações independentes; lista × detalhe 10/10 nos 10 detalhes; lista × board `hr` **90/90** nos mints comuns de **outra interseção** (completas ∩ `graduated`, sem estes 2) | `frontend-api-v3` + `advanced-indexer` | 17:45:04–17:45:35 |
| **`hr: true` em moedas graduadas antes do upgrade de 12/09** | **fone** `CTPoyCwkjMvoJwU4xvZZqoD8tiYk6yDchySiN5gGpump` — criada 26/08 21:02:12, `gd` 26/08 21:03:44, mc US$ 5,18 M, ATH 41,1 M, `nh` 6 117; **baton** `Hg5Ja55T5wESq4vyFoiVCMeHXtGyVA69X2UHq8hgpump` — 09/09 17:32:10 → `gd` 17:32:16, mc 5,84 M, ATH 18,7 M, `nh` 7 669; ambas `pg = pump`, `pa` SOL, `bo` 0 | `https://advanced-indexer.pump.fun/boards/movers?offset=0&limit=50` (`age` 1 716 187 s e 519 189 s) | 17:45:19 |
| `is_holder_reward` nas listas | mais novas **15/100** (26/139); `complete=true` **19/140**; `mayhem-mode` **2/60** (16:19: 0/60); boards `new` 8/43 pump · `graduated` **23/126 pump (0/23 StonkFun)** · `graduating` 2/50 · `movers` 10/28 pump; 16:19: 7/70 | `frontend-api-v3` + boards | 17:45:04–17:45:19 |
| **células `gd − criada` por `hr`** (board `graduated`, 126 pump-nativas, proxy ±1 s) | HR **0 / 5 / 11 / 7 / 0** (mesmo slot · (1, 60] s · (60 s, 5 min] · (5, 120] min · > 120 min); não-HR **63 / 10 / 7 / 17 / 6**; HR: Δ mín **16 s**, mediana **149 s**, máx 2 359 s; não-HR mediana 0,56 s | `boards/graduated?offset={0,50,100}` (`serverTs` 17:45:14–16; 150 entradas, 149 únicas) | 17:45:14–17:45:16 |
| dentro das células (HR · não-HR) | `t10` (1, 60] s 11,8 · 8,9 %; (60 s, 5 min] 14,6 · 8,3 %; (5, 120] min 19,9 · 18,7 %; `kol` > 0 (60 s, 5 min] 10/11 · 2/7; ATH > 1 M: HR 0/23, não-HR 25/103 (24/25 no mesmo slot) | idem | idem |
| fee na REST (restrito ao observado) | objeto `Coin` = união de **56 chaves** nos 10 detalhes consultados, **nenhuma** com `fee`/`bps`/`share` — bps de HR não encontrados nestes detalhes (o `creator_fee_bps: u64` está na `BondingCurve`, T4.8c); **campos de reservas comparados iguais** entre POO (HR) e `HRS1LJ…` (não-HR), ambas sem trade e quote SOL (30 000 000 001 · 1 073 000 000 000 000 · 1 · 793 100 000 000 000, supply 1e15) — igualdade do estado inicial, não de custo por trade | `/coins/{mint}` ×10 | 17:45:21–17:45:32 |

Denominadores: 2 páginas; 2 moedas antigas num board de 50; 100/139 + 140 + 60 linhas de listagem (observações de mints, não ensaios); 149 entradas de board (3 páginas contíguas, condicionadas e não exaustivas — 18/59 completas cheias fora dele nesta leitura); 10 detalhes. Nada disto é taxa-base por criação (KB-0091).

## O que está e o que não está estabelecido

- **Estabelecido (observação):** o rótulo "holders" **renderiza** numa moeda (KB-0095 só tinha o template); cinco superfícies do mesmo operador dizem o mesmo nos mesmos 2 mints; o flag **é observado `true` em moedas criadas e migradas semanas antes** do upgrade — logo **não é atributo de criação** (**conversão compatível, não comprovada**: sem estado anterior `false` observado, sem transação, sem semântica validada do board para migradas; coerente com "moedas regulares podem converter", README citado no run 20); entre as graduadas do board desta tarde, **nenhuma HR graduou no mesmo slot** (proxy temporal ±1 s).
- **Não estabelecido:** que o flag de **cada fonte** corresponde ao byte da `BondingCurve` nos mesmos mints e instantes (a T4.8c já leu o byte — `true` numa HR, `false` num controle, offset 124, existente desde pelo menos 12/09 — o que nasceu foi a exposição na REST; concordância entre superfícies do mesmo operador ≠ validação — M-D9/M-D13); **se e quando** fone/baton converteram (o board não tem histórico; uma reclassificação do indexer não é evento econômico); a **taxa** (bps) das HR — a REST dá a classe, o valor está on-chain; o **mecanismo** da ausência no mesmo slot — mesmo segundo ≠ mesmo slot ≠ bundle; 0/23 tem limite superior unilateral 95 % ≈ 12,2 % (binomial, ilustração da Astra); qualquer "HR gradua melhor" — o board não dá probabilidade de graduação por criação e o contraste bruto (`t10` 14,6 % vs 1,5 %) mostra influência da composição **sem provar que ela explica tudo** (residuais como `kol` 10/11 vs 2/7 ficam por estimar).

## O que muda para o Meme Radar (regra de casa)

1. **`is_holder_reward` é observação datada por fonte, nunca coluna de criação:** observações imutáveis por mint × fonte (lista/detalhe/board/imc/página/byte) com valor, `received_at`, tempo/slot da fonte e `program_version`; `first_seen_true`/`last_seen_false` derivados (transição observada ≠ instante comprovado de conversão); "exposição em L" (M-P34 na criação; M-P39/M-P41 nos seus marcos) = flag **recebido até L**; conversão posterior = classe compatível, separada quando identificável, não retroage à compra. → **M-D15** (adenda temporal a M-D13/M-D9, por parecer da Astra; primeira da ordem); a coleta bruta de M-P34 começa junto com o contrato.
2. **O classificador da página (M-D9) tem os primeiros positivos reais** (`holders`, sem percentual) — a variante "holders · {{percent}}%" ainda não vista; o percentual, quando aparecer, é a única leitura fora da cadeia do `creator_fee_bps`.
3. **A célula "mesmo slot" ganha a covariável `hr`:** com denominador = todas as criações (não o board) e slots comprovados, **M-P42** (subanálise de M-P18v2 cruzando HR com M-P28) pergunta se a fração mesmo slot difere entre HR recebida até a criação, HR recebida até L = criação + 60 s (uma moeda pode concluir no slot da criação e converter depois) e não-HR pareadas — margem pré-fixada, sem "≈ 0", ATH fora da previsão principal, sem "HR exclui bundles"; enquanto não testada, nenhum contraste HR × não-HR se lê sem estratificar por célula e sem estimar os residuais.
4. Normalizador (M-D1): `is_holder_reward` tri-estado (true/false/**ausente**); `market_cap` nulo com reservas normais (DICKSHIT2DUD, sem trade) ≠ 0; `security_verdict = unknown` é classe.

## Hipótese testável

**M-D15** (diagnóstico — adenda temporal a M-D13/M-D9: flag como observação datada por fonte; estado em L só do recebido até L) e **M-P42** (exploratória, prospectiva — subanálise de M-P18v2 × M-P28; previsão: fração mesmo slot comprovado menor entre HR recebida até a criação do que entre não-HR pareadas, com margem pré-fixada, sem afirmar zero; ATH fora da previsão principal) — linhas em [[00-INBOX/Hipoteses-do-plantao]].

## Por que pode falhar

As 2 páginas foram abertas 20–47 s após a criação (o rótulo pode mudar com a conversão); fone/baton podem ter `hr` por outra razão (rótulo aplicado à pool, não à curva) — o significado de HR numa moeda já migrada não foi lido; 23 vs 103 numa tarde de um board não exaustivo; a REST pode passar a expor `bps`; o proxy de slot (±1 s) pode classificar mal graduações a 1–2 s.

## Astra
Parecer do run 21 (`.claude/state/astra-review-plantao-meme-20260915-1725.md`, 17:54:34–17:57:55 BRT, DONE_WITH_CONCERNS): "o rótulo 'Rewards → holders' foi efetivamente encontrado nos extratos das duas páginas, sem percentual no trecho observado — fecha uma lacuna documental"; publicaria os fatos como **adendo datado à KB-0096**, incluindo 0/23 "apenas como descrição do board"; ordem M-D15 (contrato temporal) → coleta de M-P34 → M-P42 exploratória. Must-fixes 1, 2, 4, 6, 7 e 8 aplicados nesta nota (pendência on-chain atualizada com a T4.8c; "conversão compatível, não comprovada"; proxy temporal e limite superior 12,2 %; composição sem "explica tudo"; superfícies por mint; fee restrito ao observado); 3 e 5 nas linhas M-D15/M-P42. Detalhe na seção "Run 21" de [[02-MARKET/Meme/2026-09-15]].

## Ligações
[[02-MARKET/Meme/2026-09-15]] · [[00-INBOX/Hipoteses-do-plantao]] · [[KB-0096-pump-fun-is-holder-reward-na-rest-e-o-segundo-deploy-de-15-09-2026]] · [[KB-0095-pump-fun-rotulos-observados-do-site-da-rest-e-os-limites-on-chain]] · [[KB-0094-pump-fun-upgrade-de-12-09-2026-holder-rewards-e-bonding-curve-v2]] · [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] · [[README-meme]]
