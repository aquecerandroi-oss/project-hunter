# R84 — H-024: momentum semanal de série temporal em cripto grande (à vista, só compra)

Início: 2026-09-28 03:00Z. Notas incrementais. Nenhum acesso à VPS nem à base; dado = arquivo público da Binance,
guardado como artefato de pesquisa em `.claude/state/r84/cache/` (decisão do orquestrador; não vai para `candles`).
Scripts em `.claude/state/r84/`.

## 0. Lido antes (regra Obsidian primeiro)
- **Fila de Hipoteses, H-024** (congelada 28/09/2026, `status: aberta`): todos os parâmetros abaixo vêm de lá, sem edição.
  Sinal m(i,T) = C(i,d)/C(i,d−14) − 1, d = vela diária de sábado (fecho ≤ T − 1 d), d−14 = 14 dias de calendário antes;
  TS: w = 1[m>0]/N_T, resto em caixa a 0 %; execução na abertura da vela que começa em T (segunda 00:00 UTC) até a
  abertura de T+7 d. Primária D_ts = média de d_t = r_TS − r_EW (líquidos). Secundária D_cs = top ⌈N_T/3⌉ por m
  (desempate volume 30 d) − EW. Holm sobre os dois p unilaterais. Universo: top-20 pares USDT à vista por soma de
  `quote_volume` das velas com abertura em [T−30 d, T−1 d] (ausente = 0, desempate por símbolo), listados ≥ 35 d em
  T−1 d, com deslistados; exclusões por desenho (paridade fiduciária, alavancados, embrulhos) congeladas antes do preço;
  avaliável N_T ≥ 15; custo 0,15 %/perna sobre |w_novo − w_efetivo|; deslistagem em dois limites (último fecho /
  perda total). Previsão: D_ts ≥ +0,25 p.p./sem; IC 95 % percentil por bootstrap de blocos móveis de 8 semanas
  (10 000, semente 20260928, mesmas semanas para todos os braços) com inferior > 0; p unilateral centrado < limiar de
  Holm; TS lucrativa em nível; patamar 7 e 28 d com D_ts > 0; D_ts > 0 antes e depois de 2022-01-01; tudo nos dois
  limites. Refutação: IC sup < +0,25 → REFUTA o tamanho; resto → NÃO CONFIRMA; limite de dado sem a lista completa
  com deslistados ou < 200 semanas avaliáveis. Poder declarado: σ(d_t) ~5 p.p. a priori → meio-IC ~±0,5 p.p.
- **KB-0164**: literatura forte até 2018, bruta; frágil depois de 2020 (Grobys et al. 2025; Arefev 2026 só resumo);
  nenhum estudo só-compra à vista líquido pós-2020 encontrado. Fonte de dado sugerida: `data.binance.vision`
  mensal 1d; a condição dura é a lista de todos os pares USDT que existiram.
- **KB-0145**: custo de papel na Jupiter tier A ≈ 0,3 % ida e volta + 0,001 SOL fixo/perna (fora do teste);
  preço Binance ≠ preço Jupiter (+9 bp; representações podem desancorar).
- **KB-0149 §5**: antecipação mente com convicção (24); limiar escolhido olhando o resultado vale zero (25);
  patamar × pico (26); ligar critério novo na mesa real não é sombra (28).
- **docs/RESEARCH.md**: três rótulos (CONFIRMA / REFUTA / NÃO CONFIRMA), nunca "promissor"; falta de poder nunca
  vira refutação; o moinho faz Holm (`stats.adjust_family`) mas o seu `block_bootstrap` reamostra grupos rotulados,
  não blocos móveis contíguos — para a H-024 escrevo o bootstrap de blocos móveis congelado e uso o Holm do moinho.

## 1. Regras congeladas ANTES de listar símbolos e ANTES de baixar qualquer preço (03:05Z)

### 1.1 Fonte e sobrevivência
- Lista de símbolos: listagem S3 do arquivo público
  `https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/spot/monthly/klines/`
  (paginada), que guarda pastas de pares deslistados; cruzada com `GET /api/v3/exchangeInfo` (status atual, inclui
  `BREAK` de pares parados) e com uma lista de controle de deslistagens conhecidas escrita de memória antes de olhar
  (BCCUSDT, VENUSDT, BCHABCUSDT, BCHSVUSDT, ERDUSDT, LENDUSDT, NPXSUSDT, STRATUSDT, PAXUSDT, BKRWUSDT, BULLUSDT,
  BEARUSDT, BTCUPUSDT, LUNAUSDT, USTUSDT, SRMUSDT, FTTUSDT, MATICUSDT, MITHUSDT, BTTUSDT, HCUSDT, ANCUSDT, MIRUSDT,
  WAVESUSDT, OMGUSDT, XMRUSDT). Critério de "lista completa": todos os controles presentes no arquivo e a contagem de
  pares USDT com vela por mês plausível e monotônica em relação à história conhecida. Se algum controle faltar e não
  houver explicação documentada → **limite de dado**, a análise não roda.
- Preço: velas `1d` mensais do arquivo (`<PAR>-1d-AAAA-MM.zip`); mês corrente pelos arquivos diários ou
  `GET /api/v3/klines?interval=1d` (só para pares que ainda existem). Uma fonte por vela; coluna `quote_volume` = campo 8
  (índice 7) do kline. Tempo de abertura em ms (ou µs a partir de 2025 no arquivo — normalizar para ms).
- Par USDT à vista = símbolo que termina em `USDT` com base ≠ vazio (base = símbolo sem o sufixo `USDT`); pares com USDT
  como **base** (ex.: `USDTTRY`) não entram por construção.

### 1.2 Exclusões por desenho do ativo (só nomes/desenho, sem preço)
- **E1 paridade fiduciária** (desenhada para valer 1 unidade de moeda fiduciária, inclusive algorítmica e mesmo depois
  de desancorar; e as próprias moedas fiduciárias tokenizadas da Binance): USDC, BUSD, TUSD, PAX, USDP, USDS, USDSB,
  DAI, FDUSD, USDD, UST, USTC, USDE, USD1, RLUSD, PYUSD, SUSD, BFUSD, XUSD, USDB, EUR, EURI, AEUR, GBP, AUD, BRL, TRY,
  RUB, BIDR, IDRT, BKRW, BVND, NGN, UAH, ZAR, ARS, PLN, RON, JPY, MXN, COP, CZK, VAI, FRAX, LUSD, GUSD, HUSD. A lista
  pode ser completada ao ler os nomes (sem preço) por qualquer ativo cujo desenho documentado seja paridade
  fiduciária; cada acréscimo fica escrito com a razão. **Lastreados em ouro (PAXG, XAUT) NÃO são paridade
  fiduciária** e ficam (regra literal).
- **E2 alavancados**: base = X+`UP`/`DOWN`/`BULL`/`BEAR` onde X é um ativo com par USDT próprio no arquivo, mais
  `BULL`/`BEAR` sozinhos (tokens 3x de BTC da FTX). Cada casamento é revisto à mão pelo nome (ex.: `JUP` não é
  alavancado); a lista final fica escrita.
- **E3 embrulhos/derivados** de ativo com par USDT próprio no arquivo (o "já no universo" é aplicado como "que
  existe como ativo base listado"; conservador): WBTC, BTCB, WBETH, BETH, WETH, STETH, WSTETH, CBETH, RETH, BNSOL,
  RENBTC, HBTC, WBNB, LUNA2? (não — nova cadeia, não embrulho), BFUSD (já E1). Casamento também por nome ao ler a
  lista (prefixo W/ST/B + ticker existente só quando o desenho documentado for embrulho/staking 1:1). Cada acréscimo
  escrito com a razão.
- Nada fica de fora por preço, volume, "parece stablecoin" no gráfico, ou por ser meme.

### 1.3 Série, lacunas, deslistagem
- Cada símbolo é uma série. **Lacuna ≥ 14 dias** consecutivos sem vela dentro de um símbolo parte-o em duas séries
  (a primeira termina = deslistagem; a segunda é listagem nova, idade recomeça). Lacunas menores: para avaliação e
  negociação de posição já aberta, preço carregado do último fecho (abertura = fecho anterior, volume 0); para sinal
  e volume usam-se só velas reais (ausente = não elegível / volume 0).
- **Fim de série** = última vela real de um símbolo que não está `TRADING` hoje, ou o fim da 1.ª parte de uma quebra.
  Símbolo `TRADING` hoje: a última vela é só o fim do dado (não deslistagem).
- Posição aberta em série que termina antes da abertura de T+7: **otimista** = sai no fecho da última vela (custo de
  0,15 % sobre o peso vendido), resto da semana em caixa; **pessimista** = −100 % da posição.
- Moeda do universo sem vela real que abra em T: não é comprável; se a série ainda continua, entra pelo fecho
  anterior carregado (regra de lacuna); se já terminou, conta como fim de série no instante T.
- Troca de ticker (MATIC→POL, RNDR→RENDER, LEND→AAVE…) = deslistagem + listagem nova (regra literal "cada símbolo é
  uma série"); o limite pessimista trata essas como perda total — conservador para CONFIRMA; o número de eventos
  por braço é publicado.

### 1.4 Janela e datas
- Agora = 2026-09-28 03:00Z. A vela de 28/09 não é final. **Último T = 2026-09-14** (a última semana cujo preço de
  saída, a abertura de T+7 = 21/09, pertence a uma vela final). Primeiro T = primeira segunda-feira em que ≥ 20
  símbolos não excluídos estão vivos (vela real em T−1 d… definido só por datas: 1.ª vela ≤ T−36 d e série não
  terminada antes de T−1 d).
- Semana não avaliável (N_T < 15): os dois braços vão a caixa (custo de venda nos dois) e a semana sai de d_t.
- Custo: r_net = (1 − 0,0015·Σ|w_novo − w_ef|)·(1 + Σ w·r) − 1 (custo pago em T, antes de investir); venda forçada
  otimista por fim de série paga 0,15 % sobre o valor vendido.

### 1.5 Inferência (da fila, só explicitada)
- d_t sobre as semanas avaliáveis em ordem; blocos móveis de 8 semanas com início uniforme em [0, n−8],
  ⌈n/8⌉ blocos concatenados e truncados em n; 10 000 réplicas, `np.random.default_rng(20260928)`; **os mesmos
  índices** para TS, CS, os dois limites e os patamares.
- IC 95 % = percentis 2,5/97,5 das médias reamostradas. p unilateral centrado = (#{D*_b − D̂ ≥ D̂} + 1)/(B + 1).
- Holm (moinho `adjust_family`, α 0,05) sobre {p_ts, p_cs}, por limite de deslistagem.
- REFUTA só se o IC sup < +0,25 p.p. **nos dois limites**; se um limite refuta e o outro não → NÃO CONFIRMA
  (identificação parcial).

### 1.6 Aplicação das regras aos NOMES (03:20Z, ainda sem nenhum preço baixado)
Fontes de nome/desenho: listagem S3 (`r84/list_symbols.py` → `cache/archive_symbols.txt`, 3 710 pastas, **735** terminam
em USDT), `exchangeInfo` de hoje (3 673 símbolos, 2 305 `BREAK`; **709** com `quoteAsset = USDT`) e o catálogo público
de ativos `bapi/asset/v2/public/asset/asset/get-all-asset` (1 084 ativos: nome, tags `stablecoin`/`bStocks`/`ETF`,
`isLegalMoney`, `oldAssetCode`/`newAssetCode`). União = **750 pares USDT**. Nenhum símbolo terminado em USDT tem outra
moeda de cotação no `exchangeInfo`.
- **Sobrevivência — os 26 controles** de §1.1 estão todos no arquivo (BCCUSDT 2018, VENUSDT 2018, BCHSVUSDT 2019,
  ERD/LEND/STRAT 2020, PAX/BKRW/BULL/BEAR/BTCUP, UST/LUNA/SRM/FTT, MATIC, WAVES/OMG/XMR…). O arquivo guarda 41 pares
  que o `exchangeInfo` já apagou (40 alavancados UP/DOWN + NBTUSDT) — prova de que não é lista de sobreviventes. Os 15 do
  `exchangeInfo` que faltam no arquivo mensal são listagens recentes (bStocks `…B`, HYPE, MARSCOIN, 牛来): entram pela
  API se tiverem vela; nenhuma pode ter ≥ 35 dias antes do último T (14/09 → 1.ª vela ≤ 09/08) sem estar no mensal de
  agosto — conferido no download.
- **E1 paridade fiduciária (26 presentes):** AEUR, AUD, BFUSD, BKRW, BUSD, DAI, EUR, EURI, FDUSD, GBP, KGST (Kyrgyz Som
  Stablecoin), PAX (Paxos Standard), RLUSD, SUSD (sUSD, Synthetix), TUSD, U (United Stables), USD1, USDC, USDE, USDP,
  USDS, USDSB, USDSOLD (StableUSD), UST, USTC (TerraClassicUSD — desenho de paridade, fica fora depois de desancorar),
  XUSD. **Correção de nome antes do preço:** `FRAX` na Binance é o token de governança renomeado de FXS (catálogo:
  `oldAssetCode = FXS`, "Frax Finance"), não a stablecoin → **fica**. CHIP ("USD.AI"), USUAL, EDEN, FF, RESOLV, SKY,
  SYRUP, LISTA, ENA são tokens de governança → ficam. PAXG, XAUT (ouro) ficam.
- **E2 alavancados (50; contagem corrigida em §6 da revisão — era 51):** os 40 X+UP/DOWN de 20 bases com par próprio, BNB/EOS/ETH/XRP + BULL/BEAR (8), BULL, BEAR
  (FTX 3x BTC) — `JUP` casa o sufixo e **não** é alavancado. Acréscimo por desenho (catálogo `bStocks`, nome diz 2X/3X):
  INTWB, KORUB, MUUB, MVLLB, SNXXB, SOXLB, SOXSB, TQQQB, SQQQB (ETFs alavancados tokenizados) — total 59.
- **E3 embrulhos/derivados 1:1 de ativo com par próprio (4):** WBTC, WBETH, BETH (Beacon ETH da Binance), BNSOL. WNXM
  fica (NXM não tem par). BTCST fica (token de hashrate, não embrulho).
- **Ficam, pela regra literal, com leitura descritiva obrigatória:** as ações tokenizadas `bStocks` não alavancadas
  (≈ 60 pares de 2026: AAPLB, TSLAB, NVDAB, SPYB…). Não são paridade fiduciária, nem alavancadas, nem embrulho de ativo
  do universo. Publico quantas semanas-moeda do universo elas ocupam.
- **Continuidade de ticker:** o catálogo documenta `oldAssetCode → newAssetCode` (MATIC→POL, RNDR→RENDER, FXS→FRAX…),
  mas não a razão de troca; mantenho §1.3 (cada símbolo é uma série) e publico quantas perdas do limite pessimista vêm de
  trocas documentadas.

## 2. Astra — desenho de dados e sobrevivência (`.claude/state/astra-review-R84-design.md`, 28/09 ~03:40Z)
Nenhum retorno olhado antes nem depois desta revisão até §5. Must-fix e decisão:
1. **"Inclui deslistados" ≠ censo completo** (cenário: par removido do cadastro e sem arquivo mensal falta nas duas
   fontes e muda o top-20). **Aceito.** Fecho com inventários independentes, sem preço: (a) outras famílias do arquivo
   (`daily/klines` 749 USDT, `monthly/trades` 734, `monthly/aggTrades` 734, `daily/trades` 749 — **nenhum** par fora
   dos 750); (b) cópias históricas de cadastro no Wayback Machine (`exchangeInfo` v1/v3 2018–2026, lista legada
   `exchange/public/product` 2017–2020, `get-products` 2019–2023, listas de ticker 2018–2026) — só nomes/status,
   `r84/wayback.py`; (c) cobertura temporal: todo par `TRADING` numa cópia tem de ter vela real perto da data da cópia.
   Resultado em §4. Aceito também: contagens mensais não precisam ser monotônicas (retiro esse critério de §1.1).
2. **Cauda de setembro/fim de dado** (cenário: par que negociou até 10/09 e saiu do cadastro fica "deslistado" em
   31/08). **Aceito:** o `exchangeInfo` de hoje tem os `BREAK` e a API devolve velas deles (conferido com PAXUSDT);
   os 41 ausentes do cadastro são alavancados de 2022 e NBT; confiro que nenhuma série termina em 31/08/2026 sem
   explicação e que a última vela de cada série com fim coincide com o último arquivo diário (§4). Corte da vela em
   formação passa a ser pelo `as_of` fixo 2026-09-28 (constante, não o relógio).
3. **Lacuna ≥ 14 d não é prova de deslistagem; marca carregada não é preço executável.** **Aceito.** (a) Cada lacuna
   ≥ 14 d é listada (`Panel.long_gaps`) e classificada à mão por identidade (o mesmo ativo voltou → não parte,
   `keep_together`; ticker reaproveitado por outro ativo → parte). (b) Sem vela real em T: posição mantida pela marca
   carregada, sem venda nem compra; compra nova vira caixa (teste `test_held_coin_in_short_gap_is_frozen…`). Isto
   substitui a frase contraditória de §1.3 ("entra pelo fecho anterior carregado").
4. **Migração com continuidade documentada** (cenário: EW tem 5 % numa moeda migrada, TS não; perda total só na EW
   dá +5 p.p. ao contraste nessa semana — o pessimista **não** é conservador para TS−EW). **Aceito o argumento:** os dois
   limites são cenários, não ordenam o contraste. Decisão: listar as migrações documentadas no catálogo
   (`oldAssetCode→newAssetCode`) que tocam o universo com posição aberta; para cada uma, tratamento de continuidade
   (§4) e publicar o efeito.
5. **Blocos contíguos no calendário.** Verificado no código: `calendar_holes` conta semanas avaliáveis não
   consecutivas; se for 0, o achado se encerra.
Nice-to-have aceitos: manifesto (contagens, sha256 do CSV), E3 só vale quando o subjacente já existia (WBTC/BTC,
BETH e WBETH/ETH, BNSOL/SOL — todos os subjacentes existem antes do embrulho). Concorda: FRAX fica, bStocks não
alavancados ficam (com leitura descritiva), ETFs bStocks alavancados em E2, último T = 14/09, bootstrap próprio, p
centrado, Holm por limite, REFUTA só com os dois limites.

## 3. Fumaça sintética (`r84/smoke_synthetic.py` → `smoke_synth.txt`, nenhum preço real)
Painel de 45 moedas 2018–2026, 448 semanas, 8 deslistadas, mesma tubulação do teste real.
| cenário | D_ts [opt] p.p./sem (IC 95 %) | veredito primária | D_cs [opt] | veredito D_cs |
|---|---|---|---|---|
| série temporal (fator comum com deriva persistente 0,8 %/dia + moeda 0,4 %/dia) | +1,294 [+0,365; +2,112] | **CONFIRMA** | +0,761 [+0,397; +1,036] | CONFIRMA |
| só transversal (deriva só por moeda) | −0,142 [−0,646; +0,429] | NÃO CONFIRMA | +0,802 [+0,481; +1,108] | CONFIRMA |
| nulo (média aritmética 0), semente 12 | −0,314 [−0,746; +0,196] | REFUTA (o tamanho) | +0,025 | NÃO CONFIRMA |
| nulo, semente 13 | −0,413 [−0,970; +0,120] | REFUTA (o tamanho) | +0,058 | NÃO CONFIRMA |
| nulo com deriva aritmética > 0 (convexidade) | −0,275 [−0,811; +0,300] | NÃO CONFIRMA | +0,045 | NÃO CONFIRMA |
Leituras (escritas antes de qualquer retorno real):
- O nulo **nunca** dá CONFIRMA. REFUTA no nulo é correto pela regra da casa (D verdadeiro 0 < MRE +0,25).
- **D_ts é quase só *timing* do fator comum**: com moedas correlacionadas, o sinal de m(i) segue o mercado. Uma
  vantagem puramente transversal aparece em D_cs e não em D_ts. Com deriva comum de 0,4 %/dia, D_ts = +0,47
  [−0,22; +1,09] — não passa: o poder é o declarado (dp(d_t) ≈ 6–7 p.p./sem nos sintéticos, contra ~5 a priori).
- **Braço de caixa num mercado que sobe:** sem previsibilidade, E[D_ts] ≈ −(1 − exposição)·E[r_EW]; com exposição
  ≈ 0,5 e EW a +0,8 %/sem, a primária nasce ≈ −0,4 p.p. É propriedade do estimando congelado ("mede evitar as moedas
  de sinal ≤ 0"), não defeito.
- Testes (`r84/test_r84.py`, 17): painel/lacunas/quebra, vela em formação descartada, sinal = fecho de sábado ÷ 14 d
  antes, janela de volume [T−30, T−1] com ausente = 0, idade 35 d na fronteira, exclusões, desempate por símbolo,
  inelegível sem reposição, **vela futura e fecho de domingo não mudam nenhum sinal nem alvo (7/14/28 d)**, controle do
  próprio teste (sinal vazado vira o sinal), alvos TS/EW/CS, duas semanas calculadas à mão com custo sobre peso
  efetivo, dois limites de deslistagem, posição congelada em lacuna, segundas-feiras, blocos móveis contíguos, p
  centrado, regras do veredito com Holm do moinho.

## 4. Dado e auditoria de completude (sem retorno) — `r84/download.py`, `r84/wayback.py`, `r84/audit.py` → `audit.txt`
- **Velas:** 27 738 zips mensais (734 pares com arquivo mensal) + API para 2026-09 e para 16 listagens sem mensal →
  `cache/candles_1d.csv` (sha256 `e591a81f0159bf4058ffae375b2733f1c2dc4ed91388b624eec4f65103e2773e`); **843 543 velas
  finais** (abertura < 2026-09-28, corte pelo `as_of` fixo) em **750 símbolos**; fontes: arquivo 829 787, API 14 255.
  Nenhum par do inventário ficou sem vela.
- **Completude contra inventários independentes (Astra #1):** 153 cópias históricas de cadastro da Binance no Wayback
  (2017: 1, 2018: 11, 2019: 18, 2020: 24, 2021: 34, 2022: 29, 2023: 10, 2024: 8, 2025: 6, 2026: 12; `exchangeInfo`
  v1/v3, lista legada `exchange/public/product`, `get-products`, listas de ticker) — **0 pares USDT nelas fora do nosso
  dado**; **6 491** checagens (par com status `TRADING` numa cópia × data) — **0** sem vela real em ±3 dias. Outras
  famílias do arquivo (`daily/klines`, `trades`, `aggTrades`): 0 pares fora. Critério de §1.1 cumprido → **não há limite
  de dado por sobrevivência**. Ressalva: 2023–2025 têm menos cópias (8–10/ano); um par que nasceu e morreu entre duas
  cópias e não está em nenhuma família do arquivo escaparia — nenhum indício disso.
- Pares com vela por mês (jan): 2019: 25 · 2020: 96 · 2021: 231 · 2022: 343 · 2023: 334 · 2024: 375 · 2025: 396 ·
  2026: 446. Não-`TRADING` hoje: 254 símbolos; **nenhum fim em 2026-08-31** (fronteira mensal) e nenhum `TRADING` sem
  vela nos últimos 3 dias (Astra #2 fechado).
- **Lacunas ≥ 14 d (14) e classificação (Astra #3), `r84/gaps.py`:** o mesmo ativo volta → não parte: FTTUSDT
  2022-11-15→2023-09-22 (310 d), CVCUSDT (153 d), KEYUSDT (27 d), NBTUSDT (19 d). Parte (ticker de outro ativo ou fora
  do universo): LUNAUSDT 2022-05-13→05-31 (Terra 2.0 ≠ Terra Classic), USDSUSDT (E1), USDC/USDP/TUSD (E1),
  BCHUP/DOWN e ETHBULL/BEAR (E2), VENUSDT (2018, antes do 1.º T). Lacunas curtas: 10 (2–8 d).
- **Migrações (Astra #4):** o catálogo documenta 26 trocas com par antigo no dado; só **5** estavam no top-20 nas 3
  semanas finais do antigo e ganham ligação com a razão conferida pela abertura do novo = fecho do antigo × razão:
  BCHABC→BCH 1:1 (2019-11-28, 220,08 = 220,08), ERD→EGLD 1 000:1 (2020-09-03, 0,01971×1000 = 19,71), LEND→AAVE 100:1
  (2020-10-15, 0,51431×100 = 51,43), BNX→FORM 1:1 (2025-03-19, 1,7819), TON→GRAM 1:1 (2026-07-02, 1,600). Nas outras 21
  o antigo não estava no universo quando acabou. (Olhei só o nível de preço na virada para a razão, não retornos de
  estratégia.) Depois das ligações, **só 2 fins de série tocam o universo**: BCHSVUSDT (deslistagem, 2019-04-22) e
  LUNAUSDT#0 (Terra Classic, 2022-05-13; LUNC só volta em 2022-09-09 e o catálogo não liga) — ficam nos dois limites.
- Sensibilidade que não decide: a regra automática pura de §1.3 (toda lacuna ≥ 14 d parte, sem ligação).
- **Semanas:** 395, de 2019-02-25 (1.ª segunda com ≥ 20 listados não excluídos, só por datas) a 2026-09-14. 245 séries
  passaram pelo top-20.

## 5. Resultado (`r84/run_real.py` → `r84/h024.txt`; integridade `r84/integrity.py` → `integrity.txt`)
395 semanas avaliáveis (2019-02-25 → 2026-09-14), 0 buracos de calendário (Astra #5 fechado), N_T médio 19,98,
10 000 réplicas, semente 20260928, blocos de 8. Em p.p./semana, retornos líquidos de 0,15 %/perna:

| | D (opt) | IC 95 % (opt) | p (Holm) | D (pes) | IC 95 % (pes) | p (Holm) |
|---|---|---|---|---|---|---|
| **D_ts 14 d (primária)** | **+0,137** | [−0,495; +0,864] | 0,370 (0,370) | +0,150 | [−0,481; +0,873] | 0,354 (0,354) |
| D_cs 14 d (secundária) | +0,354 | [−0,081; +0,696] | 0,022 (0,044) | +0,367 | [−0,070; +0,712] | 0,019 (0,038) |

Cláusulas da primária (iguais nos dois limites): D ≥ +0,25 **não** (+0,14/+0,15); IC inferior > 0 **não**; p de Holm
< 0,05 **não**; nível TS > 0 sim (+0,566 %/sem contra EW +0,430/+0,416); patamar **não** (7 d −0,112/−0,098; 28 d
+0,268/+0,281); corte **não** (antes de 2022 −0,284/−0,249 em 149 semanas; depois +0,391 em 246). IC superior
+0,86 > +0,25 → não REFUTA. **H-024 = NÃO CONFIRMA** (falta de poder, não refutação). dp(d_t) = 6,7 p.p. (a priori ~5).
Secundária D_cs: p de Holm passa (0,044/0,038), mas IC percentil cruza zero e o **patamar falha dos dois lados** (7 d
−0,134, 28 d −0,142): o 14 d é **pico**, não planalto (KB-0149 §5 item 26) → NÃO CONFIRMA.
Sensibilidade blocos 4/16 (D_ts opt): [−0,480; +0,813] / [−0,530; +0,897] — mesma leitura. Sensibilidade sem ligações
nem classificação de lacunas: D_ts +0,134/+0,186, D_cs +0,352/+0,404 — mesmos vereditos.
Descritivo (mesmas 395 semanas): TS média +0,566 %/sem, Sharpe 0,59, DD −70,9 %; EW +0,430, Sharpe 0,28, DD −96,0 %;
**BTC comprado-e-segurado +1,117 %/sem, Sharpe 0,98, DD −75,2 %**; caixa 0. TS em caixa total em 25 semanas, exposição
média 0,49; giro acumulado TS 156, EW 90, CS 372 (em unidades de carteira). Fim de série com posição: EW 2 (BCHSV,
LUNA clássica), TS 0, CS 0; EW congelada 44 semanas-posição (FTT parada 2022-11→2023-09). bStocks no universo: 13 de
7 893 moeda-semanas (MUB, SNDKB, SPCXB) — desprezível.
**Antecipação no dado real:** 25 segundas sorteadas × 7/14/28 d × 3 braços reconstruídas com velas de abertura < T:
**0 divergências**. Integridade: saltos abertura ÷ fecho anterior > 1,5× só em alavancados excluídos (rebases de BLVT) e
no dia de listagem do SCR; extremos semanais no universo são episódios reais (DOGE +334 % 2021-04-12, BANK −88 %
2026-07-27).
Porta para papel: **não avaliada** (só depois de CONFIRMA).

## 6. Astra — veredito (`.claude/state/astra-review-R84-verdict.md`, log `r84/astra_verdict.log`)
**Concorda com NÃO CONFIRMA para D_ts e D_cs**; rodou os 18 testes (passam) e **reproduziu o relatório em memória**
(mesmos números; 395 semanas avaliáveis nos três lookbacks; 0 buracos). **Nenhum must-fix de implementação.** Conferiu
custo sobre peso efetivo, congelamento, as 5 ligações, BCHSV/LUNA, calendário, janela de volume, elegibilidade,
bootstrap, p centrado e Holm. (O aviso "a Astra alterou a árvore" do `astra.sh` vem do `git status` de uma árvore
compartilhada com outros agentes — KB-0167 apareceu no meio; ela declara não ter modificado nada.)
Correções de redação **aceitas**:
1. Não escrever "falta de poder" como causa única: "**não confirmou; a precisão não exclui +0,25 p.p./semana, e as
   condições de robustez (tamanho pontual, patamar de 7 d, corte antes de 2022) também falharam**".
2. A fumaça **não** mostra que o D_ts real é "quase só *timing* do fator comum": o cenário "só transversal" também tem
   persistência temporal por moeda. Redação: "nos cenários sintéticos executados, a TS confirmou quando o fator comum
   era persistente; isso não identifica a origem do resultado real". E "nenhum dos nulos executados confirmou" em vez
   de "o nulo nunca confirma" (§3 fica com esta ressalva).
3. Antes de 2022: "o contraste foi negativo em 2019–2021 e positivo desde 2022" — **não** "contrariou a literatura"
   (dados até 2018, outros universos, sem custo, outro estimando) e a diferença entre períodos não foi testada.
4. Secundária: "pico observado na grade 7/14/28", não "artefato comprovado"; o IC percentil e o p centrado não são
   inversões um do outro com distribuição assimétrica — não escolher depois o procedimento favorável.
Nice-to-have:
- Custo × posição congelada: o multiplicador global reduz implicitamente a posição presa em c·giro (ex.: 0,5 →
  0,49925). **Aceito como ressalva, não corrigido:** só a EW teve congelamento (FTT, 44 posição-semanas de peso
  ~5 %); o erro por semana é ≤ 0,0015 × giro × 0,05 ≈ 4·10⁻⁵ e a sensibilidade que parte a FTT dá D_ts +0,134 contra
  +0,137 — não muda nada.
- Migrações não ligadas (`r84/migr_check.py` → `migr_check.txt`): das 21, o ticker novo só aparece no top-20 nas 10
  semanas após ter idade em FET (já listado desde 2019, fusão de AGIX/OCEAN), ZRO (listado antes da fusão com STG) e S
  (FTM→S: S entra só em 2025-03-03; na 1.ª semana com idade e 30 d de volume próprio, 2025-02-24, não estava no top-20
  — ligar FTM não anteciparia a entrada). Fechado.
- BTC comprado-e-segurado é **bruto** de custo (razão de aberturas) — rotulado assim no KB.
Não concluir (dela, aceito): que momentum semanal inexiste ou que +0,25 foi refutado; promover D_cs pelo Holm; que
28 d, só pós-2022 ou outro universo "resolvem" (escolha depois de ver); que nível positivo é alfa ou viabilidade na
Jupiter; que dois nulos validam tamanho/poder; que a porta para papel foi aprovada (não foi avaliada).

## 7. Veredito
**H-024: NÃO CONFIRMA** (primária D_ts +0,137 p.p./sem [−0,495; +0,864] otimista, +0,150 [−0,481; +0,873]
pessimista; p 0,37/0,35); não REFUTA (IC superior > +0,25). Secundária D_cs NÃO CONFIRMA (pico). Porta para papel não
avaliada; **nenhuma variante do Lab especificada, nada implementado ou ativado.**
