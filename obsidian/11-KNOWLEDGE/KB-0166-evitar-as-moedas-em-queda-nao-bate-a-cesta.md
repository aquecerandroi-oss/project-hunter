---
tags: [knowledge, cripto, momentum, serie-temporal, transversal, semanal, segunda-frente, hipotese, sobrevivencia, pesquisa]
tema: sair para o caixa das moedas cujo retorno de 14 dias é ≤ 0 (regra só-compra, semanal, top-20 da Binance à vista) não bate a própria cesta sempre comprada de forma confirmável em 2019–2026 (H-024 não confirma); a secundária transversal (terço de maior retorno) tem p de Holm abaixo de 0,05 mas é pico na grade 7/14/28 d
fonte: R84 (`.claude/state/notes-R84.md`) — H-024 da Fila de Hipóteses
fonte_url: https://data.binance.vision · https://api.binance.com/api/v3/exchangeInfo · http://web.archive.org (cópias históricas de cadastro da Binance)
lido_em: 2026-09-28
evidencia: medição própria — 843 543 velas diárias finais de 750 pares USDT à vista da Binance (arquivo público + API, incluindo deslistados), completude conferida contra 153 cópias históricas de cadastro (2017–2026; 0 pares faltando, 6 491 checagens de cobertura sem falha); 395 semanas (2019-02-25 → 2026-09-14); bootstrap de blocos móveis de 8 semanas, 10 000 réplicas; 18 testes; fumaça sintética com controle positivo e nulos; antecipação conferida no dado real (25 semanas reconstruídas só com velas anteriores: 0 divergências)
hipotese_testavel: sim
astra: concorda (desenho com 5 must-fix aceitos antes de qualquer retorno; veredito sem must-fix, números reproduzidos por ela; 4 correções de redação aceitas)
status: vivo
owner: sexta-feira
updated: 2026-09-28
confiança: "?"
tipo: pesquisa
hipotese: H-024
variavel: sinal_ts_14d (C_sabado / C_(sabado-14 d) - 1; compra 1/N se > 0, caixa se <= 0; rebalanceamento na abertura de segunda 00:00 UTC); secundaria tercil superior do mesmo retorno contra a cesta
populacao: 395 semanas, universo ponto-no-tempo dos 20 pares USDT a vista da Binance de maior volume em 30 d (listados >= 35 d, com deslistados; fora stablecoins, alavancados e embrulhos), N_T medio 19,98
efeito: D_ts = +0,137 p.p./semana (otimista) e +0,150 (pessimista); secundaria D_cs +0,354 / +0,367
ic: D_ts [-0,495, +0,864] e [-0,481, +0,873]; D_cs [-0,081, +0,696] e [-0,070, +0,712]
veredito: nao_confirma
proximo_passo: nenhuma variante no Lab; nao recalibrar lookback, janela, N, periodo ou custo depois de ver; o painel diario com deslistados fica como artefato de pesquisa reaproveitavel para uma hipotese nova pre-registrada
classe_de_perda: —
mercado: cripto
---

# KB-0166 — Evitar as moedas em queda de 14 dias não bate a cesta

> **H-024 (momentum semanal de série temporal, só compra, à vista): `NÃO CONFIRMA`.** Em 395 semanas (2019–2026) do
> top-20 da Binance à vista, com deslistados, a carteira que fica só nas moedas de retorno de 14 dias positivo e põe o
> resto em caixa rendeu **+0,14 p.p./semana** a mais que a mesma cesta sempre comprada (líquido de 0,15 %/perna),
> IC 95 % **[−0,50; +0,86]**; a previsão pedia ≥ +0,25 com o IC acima de zero. O IC superior passa de +0,25, então não
> é `REFUTA`: **não confirmou; a precisão não exclui +0,25 p.p./semana, e as condições de robustez (tamanho pontual,
> patamar de 7 dias, corte antes de 2022) também falharam.** Estudo em `.claude/state/notes-R84.md` · código e saídas
> em `.claude/state/r84/` (dado em `r84/cache/`, não versionado) · pré-registro em [[Fila de Hipoteses]] § H-024 ·
> literatura e desenho em [[KB-0164-momentum-semanal-em-cripto-grande]].

## O que afirma

Toda segunda-feira às 00:00 UTC, entre os 20 pares USDT à vista mais negociados nos 30 dias anteriores, a regra compra
1/N de cada moeda cujo fecho de sábado está acima do fecho de 14 dias antes e deixa o resto em USDT. Contra a cesta
que compra as 20 sempre (mesmo custo, mesma execução), o ganho médio foi pequeno e não se separa de zero. Em nível a
regra ganhou dinheiro (+0,57 %/semana contra +0,43 da cesta), com metade da exposição e uma queda máxima menor
(−71 % contra −96 %), mas o bloco mede a **diferença pareada** contra a cesta — e essa não confirmou. Comprar e segurar
BTC foi melhor que as duas nas mesmas semanas (+1,12 %/semana, Sharpe 0,98, queda máxima −75 %; série **bruta** de
custo), o que já estava previsto como referência descritiva, não como teste.

## Onde foi mostrado

| | otimista (sai no último fecho) | pessimista (perda total) |
|---|---|---|
| **D_ts 14 d (primária)** | **+0,137** [−0,495; +0,864], p 0,370 | **+0,150** [−0,481; +0,873], p 0,354 |
| patamar 7 d / 28 d | −0,112 / +0,268 | −0,098 / +0,281 |
| antes de 2022 (149 sem.) / depois (246 sem.) | −0,284 / +0,391 | −0,249 / +0,391 |
| nível TS / EW (%/sem) | +0,566 / +0,430 | +0,566 / +0,416 |
| D_cs 14 d (secundária) | +0,354 [−0,081; +0,696], p 0,022 (Holm 0,044) | +0,367 [−0,070; +0,712], p 0,019 (Holm 0,038) |
| patamar D_cs 7 d / 28 d | −0,134 / −0,142 | −0,121 / −0,129 |

p.p./semana; IC 95 % percentil de bootstrap de blocos móveis de 8 semanas (10 000, semente 20260928, as mesmas
semanas para todos os braços); p unilateral centrado; Holm sobre {D_ts, D_cs} em cada limite. Sensibilidade com blocos
de 4 e 16 semanas e com a regra automática de lacunas sem ligar migrações: mesmos vereditos. dp semanal de d_t =
6,7 p.p. (o pré-registro estimava ~5 a priori).

- **Secundária (terço de maior retorno − cesta):** o p de Holm passa, mas o IC percentil cruza zero e os vizinhos de
  7 e 28 dias são negativos — **pico observado na grade 7/14/28**, não planalto ([[KB-0149-o-que-a-mesa-real-ensinou]]
  §5 item 26). `NÃO CONFIRMA`; não vira candidata por ter passado no Holm.
- **O corte de período:** o contraste foi negativo em 2019–2021 e positivo desde 2022. Não se diz que "contrariou a
  literatura" (os estudos favoráveis usam dados até 2018, outros universos, sem custo e outro estimando), e a diferença
  entre os períodos não foi testada.
- **Sobrevivência:** a lista de pares veio da listagem do arquivo público (735 pares USDT, com pastas de deslistados)
  unida ao `exchangeInfo` de hoje (709, com os `BREAK`) = 750, e foi conferida contra **153 cópias históricas de
  cadastro** da Binance no Wayback Machine (2017–2026): **nenhum** par USDT delas falta no dado, e as **6 491**
  combinações "par `TRADING` na cópia × data" têm vela real a ±3 dias. Outras famílias do arquivo (diário, trades,
  aggTrades) não têm par fora. É evidência auditada, não prova de censo: 2023–2025 têm só 8–10 cópias por ano.
- **Exclusões por desenho, congeladas antes do preço:** 26 moedas de paridade fiduciária, 59 alavancados (40 UP/DOWN,
  10 BULL/BEAR, 9 ETFs tokenizados 2X/3X), 4 embrulhos (WBTC, WBETH, BETH, BNSOL). Ações tokenizadas não alavancadas
  ficaram pela regra literal: 13 de 7 893 moeda-semanas.
- **Continuidade:** 5 trocas de ticker que estavam no universo quando aconteceram ficaram ligadas com a razão oficial,
  conferida pela abertura do novo = fecho do antigo × razão (BCHABC→BCH 1:1, ERD→EGLD 1 000:1, LEND→AAVE 100:1,
  BNX→FORM 1:1, TON→GRAM 1:1). Só 2 fins de série tocaram posições (ambos na cesta: BSV em 2019, LUNA clássica em
  2022). FTT ficou 310 dias parada e voltou: posição mantida pela marca, sem venda (44 posição-semanas na cesta).

## Como mediríamos aqui

- **Sem antecipação:** o sinal usa só o fecho de sábado (uma barra de folga antes da ordem); ranking, idade e
  exclusões só com o que existia antes de T. Testes: nenhuma vela a partir de T nem o fecho de domingo muda universo,
  sinal ou alvo (7/14/28 d, três braços); no dado real, 25 segundas sorteadas reconstruídas só com velas anteriores
  a T deram **0 divergências**. A vela de 28/09 (em formação) ficou fora pelo `as_of` fixo; o último T é 14/09.
- **Fumaça sintética antes do dado real:** com o fator comum persistente o encanamento dá `CONFIRMA` (D_ts +1,29
  [+0,37; +2,11]); nenhum dos nulos executados confirmou (dois deram `REFUTA` do tamanho, correto com D verdadeiro 0).
  Nos cenários executados, a TS só confirmou quando o fator comum era persistente — isso **não** identifica a origem do
  resultado real. E, num mercado que sobe sem previsibilidade, a primária nasce negativa pelo braço de caixa
  (E[D_ts] ≈ −(1 − exposição)·E[r_cesta]): é o estimando congelado, não defeito.
- **Dado reaproveitável:** o painel diário com deslistados (`r84/cache/candles_1d.csv`, sha256 `e591a81f…`) e o código
  de universo ponto-no-tempo ficam como artefato de pesquisa, fora da base de produção.

## Por que pode falhar (e o que não concluir)

- A precisão é baixa: com dp de 6,7 p.p. por semana e 395 semanas, só um efeito de ~1 p.p./semana (erro-padrão empírico ≈ 0,35) teria 80 % de poder
  para ser detectado; +0,25 continua compatível com o IC.
- **Não concluir** que momentum semanal inexiste nem que +0,25 foi refutado; que D_cs pode ser promovido pelo Holm; que
  28 dias, só pós-2022 ou outro universo "resolvem" (seriam escolhas depois de ver); que o nível positivo é alfa ou
  viabilidade na Jupiter (preço Binance ≠ Jupiter e a taxa fixa por perna ficou fora — [[KB-0145-binance-como-sinal-solana-como-execucao]]);
  que a porta para papel foi aprovada (só se avalia depois de `CONFIRMA`).
- Aproximações declaradas: o custo multiplicativo reduz implicitamente uma posição congelada em ~4·10⁻⁵ por semana
  (só a cesta teve congelamento; sem efeito no veredito); a série de BTC é bruta de custo.

## Segunda opinião (Astra)

**Desenho** (`.claude/state/astra-review-R84-design.md`, antes de qualquer retorno): 5 must-fix aceitos — completude
tinha de ser demonstrada contra inventário independente (virou as 153 cópias históricas); distinguir fim de negociação
de fim de arquivo (nenhuma série termina na fronteira mensal); lacuna longa é alerta, não prova de deslistagem, e marca
carregada não é preço executável (posição congelada, compra vira caixa); migração com continuidade documentada não
pode virar perda total automática e o limite pessimista não ordena o contraste (5 ligações); blocos contíguos no
calendário (0 buracos). **Veredito** (`.claude/state/astra-review-R84-verdict.md`): concorda com `NÃO CONFIRMA` nas duas,
reproduziu os números, nenhum must-fix; 4 correções de redação aceitas (acima). Síntese em
[[06-DECISIONS/Revisoes-Astra/R84-momentum-semanal|R84-momentum-semanal]].

## Relacionados

[[KB-0164-momentum-semanal-em-cripto-grande]] · [[Fila de Hipoteses]] · [[Mapa de Estrategias]] ·
[[Proximas Hipoteses]] · [[KB-0002-momentum-e-reversao-em-cripto]] · [[KB-0145-binance-como-sinal-solana-como-execucao]] ·
[[KB-0149-o-que-a-mesa-real-ensinou]] · [[KB-0163-perto-da-maxima-de-24h-nao-separa-os-sinais-do-lab]]
