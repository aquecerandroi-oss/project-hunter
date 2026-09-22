# R65 — As 87 operações reais (16–21/09/2026): onde o dinheiro foi, o que separa ganho de perda, e a UMA mudança

**Pergunta (Everton, 22/09 17:3x BRT):** "faz análise, já faz alguns dias que estamos rodando no real, precisamos de estratégia aprimorada para começarmos a lucrar." **Meta fixada:** cada dia fechar com mais ganho do que perda, líquido.
**Método:** leitura read-only da VPS (`ssh hunter-vps` + `docker exec hunter-postgres-1 psql`, só `SELECT`/`COPY`); reconstrução da fita herdada de R62/R64 (`.claude/state/r65/load.py`). Dinheiro em lamports inteiros e `Decimal`.

## Resposta curta

**−0,3473 SOL em 87 operações, 0 de 6 dias verdes. 72 % disso (−0,2492) é custo, não escolha de moeda: o mercado só tirou −0,0952 SOL.** O maior item isolado é **rent de ATA nunca reembolsado: −0,1135 SOL = 32,7 % do prejuízo** — dinheiro parado em 75 contas, recuperável fechando-as. Cada operação nasce **−4,09 %** (2,23 % sem o rent) e o alvo é +15 %: a mesa precisa de 27 % de acerto só para empatar, e teve 26 %.

Sobre a pergunta separadora: **testei 13 variáveis de decisão e nenhuma sobrevive à correção de múltiplas comparações (Benjamini-Hochberg, FDR 10 %)**. A única com sinal repetido é `buys_1m` (compras no primeiro minuto): quem entra em lançamento *menos* disputado ganha mais. E há prova direta contra a tese de que a entrada decide: **8 pares de moedas compradas por duas propostas com 19–190 s de diferença tiveram uma saída por alvo e a outra por trailing.**

**A recomendação, em ordem:** (0) **ligar o fechamento da ATA** — é operação, não estratégia, e sem isso nenhuma regra de entrada fecha o dia no verde; (1) **recusar entradas com `buys_1m` acima da mediana móvel de 3 dias**, primeiro em sombra por 3 dias com regra de promoção escrita antes. A Astra discorda de levar (1) ao dinheiro real agora e eu concordo com ela — ver §7.

---

## 1. Dados e cobertura

| item | valor |
|---|---|
| posições | `meme_live_positions` com `status='closed'` → **87** (`q3.sql`, `positions.csv`); nenhuma aberta; `operator/5` 65, `operator/6` 22 |
| ordens | `meme_live_orders` das 87 propostas: 87 compras confirmadas, 87 vendas confirmadas, **9 vendas falhadas** (5 `onchain_error 6003`, 2 `simulation_failed`, 2 `blockhash_expired`) — nenhuma com taxa de rede registada (`q4.sql`, `orders.csv`) |
| fita | `meme_trades` das 76 moedas, entrada −5 min → saída +10 min: 22 868 trades (`q5.sql`); **74 das 87 com fita**, 13 só com fotos |
| fotos | `meme_curve_snapshots`, cadência ~15 s: 2 938 (`q6.sql`) |
| features na decisão | `meme_proposals.reasons` — `age_s`, `curve_progress_pct`, `creator_net_seller`, `participation_pct`, e o bloco `flow` (`buys_1m`, `sells_1m`, `snipers`, `unique_buyers_1m`, `dev_share`, `net_sol_flow_1m`, `mcap_delta_60s`, `holders_rising`, `progress_rising`) + `pedigree`. **Não existe contagem de holders**, só o booleano `holders_rising` (foi `true` em todas as 87 — variável sem variância, excluída) |
| checks de risco | `meme_live_orders.admission` — 25 checks por ordem, todos `passed` nas 87 (o gate de risco não recusou nenhuma das que viraram posição; as recusas estão noutras propostas) |
| **parâmetros** | **as 87 NÃO são uma regra só:** 72 com `0,07 SOL / alvo 1,15× / 300 s / trailing 10 %` (a regra atual, e só dos dias 19, 20 e 21/09); 12 com `0,05 / 3× / 1800 s / trailing 35 %` (16–18/09); 2 com `0,07 / 1,3× / 300 s / trailing 20 %`; 1 com `0,07 / 3× / 1800 s`. **A regra atual tem 3 dias e 72 operações, −0,2038 SOL**, não 6 dias e 87 |

Ressincronização por foto e caminho "segurar" idênticos ao R64. Nada foi escrito na VPS.

## 2. Q1 — anatomia das 87 (tabela completa em `.claude/state/r65/metrics.txt` e `anat.csv`)

Uma linha por operação com: conjunto, hora BRT, `idade`, `progresso`, `buys_1m`, `sells_1m`, `snipers`, `unique_buyers_1m`, `net_sol_flow_1m`, `dev_share`, SOL real na curva **no instante da decisão**, MFE/MAE/marca aos 300 s reconstruídos da fita, motivo de saída, PnL e segundos segurados. Resumo:

| motivo | n | PnL SOL | média | MFE mediano | MAE mediano | marca 300 s |
|---|---|---|---|---|---|---|
| target | 23 | **+0,2939** | +0,0128 | +46,7 % | −24,2 % | −11,5 % |
| trailing | 46 | **−0,5045** | −0,0110 | +7,6 % | −39,2 % | −23,1 % |
| creator_dump | 14 | −0,0998 | −0,0071 | +10,2 % | −20,1 % | −9,7 % |
| time_stop | 4 | −0,0368 | −0,0092 | −3,5 % | −19,1 % | −12,5 % |

A assinatura é a mesma do R64 e agora com 3,6× mais dados: **as saídas por trailing são, na mediana, moedas que nunca subiram** (MFE +7,6 %), não moedas vendidas cedo demais.

Por hora (BRT) o padrão "manhã melhor" do R64 **não se confirmou**: 00–11 h 48 ops, 14 alvos, −0,1455; 12–23 h 39 ops, 9 alvos, −0,2018; a diferença por operação é +0,0039 com p de permutação 0,27. Era ruído.

**13 das 87 só têm fotos de 15 s** — nelas MFE/MAE são **piso**, não máximo.

## 3. Q3 — decomposição do PnL líquido por dia (SOL)

| dia BRT | n | bruto da curva | taxa pump.fun | taxa criador | rede | rent ATA | soma custos | líquido |
|---|---|---|---|---|---|---|---|---|
| 16/09 | 1 | −0,005728 | −0,000880 | −0,000278 | −0,000018 | 0* | −0,001176 | −0,009764 |
| 17/09 | 8 | +0,000304 | −0,007510 | −0,002371 | −0,000144 | −0,012111 | −0,022136 | −0,021831 |
| 18/09 | 6 | −0,097131 | −0,004027 | −0,001272 | −0,000396 | −0,009058 | −0,014752 | −0,111883 |
| 19/09 | 26 | +0,016708 | −0,031038 | −0,009801 | −0,002512 | −0,033304 | −0,076656 | −0,059948 |
| 20/09 | 31 | +0,045924 | −0,036563 | −0,011546 | −0,003499 | −0,039334 | −0,090943 | −0,045019 |
| 21/09 | 15 | −0,055262 | −0,017112 | −0,005404 | −0,001350 | −0,019680 | −0,043546 | −0,098808 |
| **total** | **87** | **−0,095186** | **−0,097129** | **−0,030672** | **−0,007919** | **−0,113487** | **−0,249208** | **−0,347254** |

\* 16/09 (TAXCOIN, a primeira operação de sempre) tem 2 860 040 lamports em `fill.unexplained_lamports` na compra — o parser daquela data ainda não separava `ata_rent_lamports`. É a **única linha que não reconcilia** (0,00286 SOL); quase de certeza é rent de ATA + rent de conta. Nas outras 86 a decomposição fecha ao lamport.

Leituras:

- **Custo é 72 % do prejuízo.** O mercado tirou −0,0952 SOL em 87 apostas de 0,07 (−1,6 % por operação, bruto). O resto foi taxa e rent.
- **Custo por operação: 0,002864 SOL = 4,09 % do tamanho** (pump.fun 1,59 % + criador 0,50 % + rede 0,13 % + rent 1,86 %). **Sem o rent: 2,23 %.** Com alvo +15 % e stop −10 %, o ponto de equilíbrio é ~27 % de acerto — a mesa fez 26 % (23/87).
- **Rent: 75 compras criaram ATA (1 513 840 lamports cada), 0 das 87 vendas pediu reembolso** (`intent.closes_ata = false` em todas). Não é perda de mercado: **está parado nas contas** e volta ao fechá-las.
- **Derrapagem realizada na saída** (`fill.sell_net` − `intent.net_proceeds`): **+0,0193 SOL no total**, mediana −0,000045 por operação. A execução não é o problema — em agregado até ajudou.
- Dois dias explicam metade: 18/09 (−0,0971 de bruto em 6 ops, com a regra antiga de 1800 s) e 21/09 (−0,0553 em 15).

## 4. Q2 — a pergunta separadora: **nada sobrevive**

Método (`stats.py`): 13 variáveis de decisão; terços nas 87 e mediana nos 69 (23 alvo + 46 trailing); por balde reporto n, taxa de alvo, PnL médio, **IC 95 % por bootstrap (10 000)**; para topo-vs-base, **p por permutação (10 000)** e Spearman com p por permutação; **Benjamini-Hochberg FDR 10 %** sobre os 13 p. Nenhum ajuste multivariado — 87 pontos não sustentam isso.

**Resultado: nas duas populações, o p mais baixo (0,046) fica muito acima do limiar BH (0,0077). Zero variáveis sobrevivem.**

A mais forte, e a única com sinal coerente nas duas populações e mecanismo plausível, é **`buys_1m`** (nº de compras no minuto anterior à decisão):

| balde (87 ops, terços) | n | alvo % | PnL médio | IC 95 % | PnL SOL |
|---|---|---|---|---|---|
| 10–20 compras/min | 29 | 31 % | −0,00156 | [−0,00786, +0,00446] | −0,0451 |
| 21–37 | 29 | 31 % | −0,00111 | [−0,00494, +0,00298] | −0,0321 |
| 38–361 | 29 | 17 % | −0,00931 | [−0,01473, −0,00436] | −0,2701 |

p de permutação (topo vs base) 0,064; ρ de Spearman −0,198 (p 0,063). Nos 69 alvo/trailing, a metade `buys_1m ≤ 25` tem 41 % de alvos e +0,0189 SOL contra 26 % e −0,2295 na metade alta (p 0,046; ρ −0,257, p 0,024). **MFE mediano +28,1 % vs +8,2 %** — a diferença aparece no caminho do preço, não só no resultado.

`unique_buyers_1m` (ρ −0,14/−0,19) e `mcap_delta_60s` (ρ −0,16/−0,26) contam a mesma história e são quase colineares com `buys_1m` — **não são três achados, é um.**

**Indistinguíveis de ruído** (p de permutação entre parênteses, nas 87): idade na entrada (0,81), vendas/compras (0,83), hora do dia (0,86), fluxo líquido em SOL (0,99), snipers (0,52), `dev_share` (0,67), progresso da curva (0,37), SOL real na curva (0,37), vendas/min (0,43), fluxo por comprador (0,67). **Snipers e `dev_share` — dois dos filtros em que a mesa mais confia — não separam nada nestas 87.**

**Robustez do único candidato** (`cluster.py`, PnL ajustado pelo rent devolvido, porque 10 dos 76 mints têm 2–3 entradas correlacionadas):

- bootstrap reamostrando **mints inteiros** (76 clusters): diferença por operação **+0,00573 SOL, IC 95 % [−0,00034, +0,01207], P(dif ≤ 0) = 3,2 %**;
- bootstrap reamostrando **dias** (6 clusters — frágil, mas é o teste que importa para a meta): [+0,00348, +0,00901], P(dif ≤ 0) = 0,6 %;
- **mas o total do braço** `≤25` reamostrado por dia tem IC 95 % **[−0,0912, +0,0900] SOL** — ou seja, a *diferença por operação* é mais robusta que o *sinal do total*. Restrito às 72 homogêneas, com um dia de cada vez fora: +0,0057 / +0,0066 / +0,0036 SOL por operação (estável em direção, não em tamanho).

### A evidência que corta contra: os 8 pares que trocaram de destino

Dez mints foram comprados por mais de uma proposta com 19–190 s de diferença. **Em 8 desses grupos um lado saiu por alvo e o outro por trailing**: ANT (+0,0185 / −0,0150, 61 s de diferença), BLEP (−0,0084 / +0,0039, 33 s), Aura (−0,0005 / +0,0114, 19 s), DVD (−0,0044 / +0,0204, 79 s), TANK (−0,0032 / +0,0125 / −0,0011), Cupsey, NARKY, Paidichi. A Astra tem razão ao notar que nem todos são controles limpos (Cupsey vai de 18 para 36 compras/min entre as duas entradas, NARKY de 20 para 92); mas ANT, BLEP, Aura e DVD entraram com features praticamente idênticas e a menos de 80 s.

**A conclusão honesta é essa:** no horizonte de 300 s com alvo de +15 %, o destino alvo-vs-trailing é dominado por segundos de timing, e o que as features de entrada podem mover é a *distribuição* (MFE mediano +28 % vs +8 %), não o resultado de cada aposta.

## 5. Q4 — o que teria dado lucro nestes dados

`cf.py`. Não re-simulo saídas: filtro posições e reaproveito o PnL realizado, somando de volta o rent — portanto (b) é um **corte de seleção**, não um backtest.

| cenário | n | total SOL | dias verdes |
|---|---|---|---|
| (0) real | 87 | −0,3473 | **0 de 6** |
| (a) mesma regra, **rent devolvido** | 87 | −0,2338 | 0 de 6 |
| (b) (a) + `buys_1m ≤ 25` | 41 | **+0,0141** | 4 positivos, 1 negativo, 1 dia sem operação |
| (b') idem, **só as 72 da regra atual** | 37 | **+0,0353** | 3 positivos, 0 negativos, 3 dias sem operação |
| (b'') `buys_1m ≤ 25` **e** progresso ≤ 70 % (72) | 34 | +0,0542 | 3/0/3 |
| (c) não entrar nas 14 que viraram `creator_dump` | 73 | −0,1536 | 1 de 5 |

**(a) rent devolvido:** +0,1135 SOL, **32,7 % do prejuízo**, e ainda assim 0 de 6 dias verdes. É condição necessária, não suficiente.

**(b) o corte por `buys_1m`:** vira o sinal, mas foi escolhido *olhando para estes mesmos dados*, entre 13 variáveis, e o corte 25 é a mediana da subamostra alvo/trailing (a mediana das 87 é 27; com 27 o resultado é +0,0483 nas 72 — não é sensível ao valor exato). Sobre as 72 homogêneas o p de permutação sobe para 0,10. **O valor honesto a atribuir ao "+0,0141" como lucro esperado é zero** — é uma hipótese, não uma estimativa.

**(c) `creator_dump` (14 ops, −0,0998):**
- **0 de 14 tinham `creator_net_seller = true` na entrada** e só 2 tinham `dev_share > 0`. O sinal não existia no momento da decisão — isso diz que **o indicador de entrada não via o criador**, não que a entrada estivesse "certa".
- Mediana de 52 s entre entrada e gatilho (mín. 5 s, máx. 514 s).
- Segurar até os 300 s daria −0,0174 em vez de −0,0998 — **mas esse número depende de 3 moedas** (PS +0,0605, Drillers +0,0617, RIB +0,0250) e a marca aos 300 s **não** re-simula alvo nem trailing; para PlanB (saída aos 514 s) os 300 s são *antes* do gatilho. **Não é uma estimativa de "remover o creator_dump".** O que fica: em 5 de 14 a moeda subiu forte depois da nossa saída (Catbyte +85 %, PS +117 %, Drillers +115 %, RIB +83 %, Crabbo +13 %) e em 6 de 14 continuou a cair. **É cara-ou-coroa com n = 14 — não mexer.**

**(d) `operator/6` vs `operator/5`:** −0,00524 vs −0,00357 SOL por operação; diferença −0,00167, **p de permutação 0,64**. Com n = 22 e 65 é **ruído**, e `p = 0,64` significa "não dá para distinguir", não "são iguais". Os pares no mesmo mint (ANT, BLEP, Aura, DVD, TANK) confirmam: os dois conjuntos compraram as mesmas moedas e trocaram de destino por segundos.

## 6. Recomendação, por ordem

### P0 — Recuperar o rent da ATA (operação, não estratégia). **Fazer já.**

Ligar `MEME_CLOSE_ATA_ON_FULL_SELL=1` e fechar as ATAs abertas (75 compras criaram ATA; inventário exato tem de ser lido na carteira antes de prometer o valor). **Efeito nestes dados: +0,1135 SOL** e −1,86 pp no custo de cada operação futura (de 4,09 % para 2,23 % ida-e-volta), o que baixa o acerto de equilíbrio de ~27 % para ~19 % — a mesa fez 26 %.
**Cenário de falha:** o `closeAccount` acrescenta instrução à venda e aumenta a taxa de falha (já há 9 vendas falhadas em 96); se a venda falha, a posição fica presa e custa mais que o rent.
**Regra de refutação:** abandonar se, nas primeiras 20 vendas com `closes_ata = true`, (i) menos de 18 trouxerem `fill.ata_rent_refund_lamports > 0`, **ou** (ii) a taxa de vendas falhadas subir acima de 15 %.

### P1 — A UMA mudança de gate: recusar `buys_1m` acima da mediana móvel de 3 dias. **Em sombra primeiro.**

Não congelar "25": usar o percentil 50 de `buys_1m` das propostas admitidas nos últimos 3 dias, recalculado diariamente, para não fossilizar um número de um regime.
**Efeito nestes 87:** de −0,2338 para **+0,0141** (41 ops); nas 72 da regra atual, de −0,1115 para **+0,0353** (37 ops). Taxa de alvo 34 % vs 20 %; MFE mediano +28,1 % vs +8,2 %; diferença por operação +0,0057 SOL, IC 95 % por cluster de mint [−0,0003, +0,0121].
**Mecanismo (por que é plausível e não só ajuste):** um lançamento com 40–360 compras no primeiro minuto já tem a subida precificada e está cheio de bots com o mesmo alvo; entramos na cauda do impulso e o `sells_1m` que vem a seguir é mecânico. Um com 10–25 compras/min ainda tem caminho — MFE mediano 3,4× maior.
**Cenário de falha:** `buys_1m` alto é proxy de "lançamento disputado" *neste* regime; num mercado mais frio a mediana cai e o filtro corta o que não devia, ou os bons lançamentos passam a ser exatamente os disputados. Além disso, cortar metade das entradas reduz n por dia de ~15 para ~7 — a variância diária **sobe**, e a meta é diária.
**Regra de refutação (escrever antes de ligar):** 3 dias em sombra, com o braço de controlo a correr em paralelo e com os mesmos parâmetros. Abandonar se (i) o MFE mediano do braço `≤ P50` não ficar pelo menos 10 pp acima do braço `> P50`, **ou** (ii) o PnL líquido médio por operação do braço `≤ P50` for negativo em 2 dos 3 dias, **ou** (iii) o braço `≤ P50` produzir menos de 5 entradas/dia (amostra insuficiente para decidir).
**Desfecho principal: PnL líquido. MFE é secundário** — não se promove um gate por MFE.

### P2 — Não mexer (ainda)

`creator_dump` (n = 14, cara-ou-coroa), escolha entre `operator/5` e `/6` (p = 0,64), filtro de snipers e de `dev_share` (não separam nada), hora do dia (era ruído do R64), e **sobretudo a regra de saída**: trailing 10 % armado na entrada + alvo 1,15× + `max_hold` 300 s continua a ser a melhor de 52 combinações medidas no R64, e estas 87 não trazem nada que a contradiga — os 46 trailing são moedas com MFE mediano +7,6 %, não saídas prematuras. Tamanho 0,07 SOL e `concurrent_positions ≤ 2` também ficam: o problema não é sizing.

## 7. Segunda opinião (Astra)

Chamada: `bash infra/scripts/astra.sh ask r65 "..."` → `.claude/state/astra-review-r65.md`. Resposta: *"recuperar o rent; não mudaria o gate nem o `creator_dump` com esta evidência; `buys_1m ≤ 25` merece teste prospectivo em sombra."*

**O que ela apanhou e eu corrigi:**
1. **As 87 não são uma regra só** — refiz tudo separando as 72 com `0,07/1,15×/300 s/trailing 10 %` (só 3 dias, −0,2038 SOL). §1 e §5 agora dizem isso; o contrafactual (b') é a versão homogênea. Era o erro mais grave.
2. **Bootstrap tratava operações como independentes** — acrescentei `cluster.py` (reamostragem por mint e por dia) e leave-one-day-out. O IC por cluster de mint quase toca o zero.
3. **"4/5 dias verdes" era enganador** — são 4 positivos, 1 negativo e **1 dia sem nenhuma operação**, em 6.
4. **O corte 25 não é a mediana das 87** (é 27); o BH cobre 13 contrastes por análise, não a busca inteira (duas populações + Spearman + cortes combinados). Assumido em §4/§5.
5. **O "segurar" do `creator_dump` não re-simula saídas** e PlanB saiu aos 514 s — §5(c) foi rebaixado a descritivo.
6. **Rent = 1,86 % do tamanho**, não 1,3 % (eu tinha errado na pergunta à Astra). Corrigido em §3/§6.
7. **TAXCOIN 0,00286 SOL não reconciliado** — rastreado: é `unexplained_lamports` na primeira compra de sempre (parser de 16/09). Declarado em §3.
8. **Ela relativizou os 8 pares** (Cupsey e NARKY mudam muito de features entre as duas entradas). Aceite e escrito em §4.

**Onde discordamos e a decisão:** a Astra dá **crédito zero de lucro esperado** ao `+0,0141` e não recomendaria sequer descrevê-lo como mudança de gate. Eu mantenho `buys_1m` como **a** hipótese de entrada a testar (é a única com sinal em duas populações, com mecanismo e com MFE a acompanhar), mas **aceito a posição dela sobre o destino**: vai para sombra com regra de promoção escrita antes, não para dinheiro real. Se o Everton quiser uma mudança na mesa real esta semana, **a única que estes dados sustentam é o rent (P0)**.

## 8. Ressalvas honestas

- **n por balde é 29 (terços) ou 34–35 (metades).** Um alvo a mais ou a menos muda qualquer célula. Nenhuma variável sobrevive à correção de múltiplas comparações — dizer "não achei nada" é o resultado, não um fracasso da análise.
- **A regra atual tem 3 dias e 72 operações**, não 6 e 87. Os 15 restantes correram com 3× de alvo e 1800 s.
- **6 dias, um regime de mercado.** Todas as 87 são pump.fun, tamanho fixo, mesma janela de setembro. Nada aqui generaliza para um mercado diferente.
- **Sobrevivência na fita:** `meme_trades` vem do `swap_api` por REST e tem buracos; as moedas que morreram mais depressa são as que têm menos fita. As fotos de 15 s curam parte, mas **13 das 87 só têm fotos** — MFE/MAE dessas são piso.
- **O caminho "segurar" está contaminado:** ignora os nossos trades mas ressincroniza com fotos que já incluem a nossa venda (herdado do R64); e a ordem dentro do mesmo slot é por assinatura, não por execução real.
- **Desativação da mesa:** parou 21/09 12:08 BRT por rate-limit de RPC; 22/09 não tem dados. As 9 vendas falhadas (6003 = slippage) também não entram como custo porque não há taxa de rede registada nelas.
- **O corte `buys_1m` foi escolhido nestes dados.** Sem 3 dias de sombra, o `+0,0141` é uma frase sobre o passado.

## 9. Arquivos

`.claude/state/r65/`: `q0–q8.sql`, `positions.csv` (87), `orders.csv` (183), `trades.csv` (22 868), `snaps.csv` (2 938), `load.py` (reconstrução), `costs.py` (decomposição por ordem), `metrics.py` → `metrics.txt` + `anat.csv` (Q1/Q3), `stats.py` → `stats.txt` (Q2), `cluster.py` → `cluster.txt` (robustez), `cf.py` → `cf.txt` (Q4). Astra: `.claude/state/astra-review-r65.md`. KB: `obsidian/11-KNOWLEDGE/KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista.md`.

## 10. Proposta de linha de diário (22/09)

> **22/09 R65 — 87 operações reais, −0,3473 SOL, 0 de 6 dias verdes.** 72 % do prejuízo é custo, não mercado: o preço tirou −0,0952 e as taxas + rent tiraram −0,2492, dos quais **−0,1135 é rent de ATA que nunca foi reembolsado** (75 contas abertas, dinheiro parado e recuperável). Cada operação nasce −4,09 % e o alvo é +15 %. Das 13 variáveis de decisão testadas (bucket + bootstrap por cluster de mint + permutação + Benjamini-Hochberg), **nenhuma sobrevive**; a única pista é `buys_1m` — lançamentos com ≤ 25 compras/min tiveram 34 % de alvos e MFE mediano +28 % contra 20 % e +8 %, e o corte viraria o sinal (+0,0141 em vez de −0,2338), mas foi escolhido olhando para os mesmos dados. Oito moedas compradas duas vezes com 19–190 s de diferença tiveram uma saída por alvo e outra por trailing: **a entrada move a distribuição, o segundo decide a aposta.** Decisão: **ligar o fecho da ATA já** (P0, operação) e levar `buys_1m ≤ P50 móvel de 3 dias` a **3 dias de sombra** com regra de refutação escrita antes (P1) — a Astra pediu crédito zero ao número retrospectivo e eu aceitei. Saídas, tamanho e `operator/5 vs /6` ficam como estão.
