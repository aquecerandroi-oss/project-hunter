---
tags: [knowledge, meme, custo, rent, ata, gate, entrada, buys-1m, mesa-real, r65, r67, fora-de-amostra, m4]
tema: 87 operações reais em 6 dias — 72 % do prejuízo é custo (e 33 % é rent de ATA parado); das 13 variáveis de decisão testadas nenhuma sobrevive à correção de múltiplas comparações, e `buys_1m` é a única pista
fonte: .claude/state/notes-R65.md (87 posições reais 16–21/09/2026, fita reconstruída + decomposição de custo por ordem) · .claude/state/notes-R67.md (teste fora de amostra de `buys_1m`, 473 mints de papel, 23/09/2026)
fonte_url:
lido_em: 2026-09-22
evidencia: medição própria — 87 posições fechadas, 174 ordens confirmadas com fill decomposto ao lamport (86 de 87 reconciliam exato), 22 868 trades de fita, 2 938 fotos de 15 s; bootstrap por cluster de mint e de dia (10 000), permutação (10 000), Benjamini-Hochberg FDR 10 %
hipotese_testavel: sim
astra: revisto — 8 correções aceites, 1 discordância registada (ver §7 do R65)
status: vivo
owner: sexta-feira
updated: 2026-09-23
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

# KB-0147 — Custo é o prejuízo; `buys_1m` é a única pista de entrada (R65, 16–21/09/2026)

## O que afirma

1. **Em 87 operações reais (−0,3473 SOL, 0 de 6 dias verdes), 72 % do prejuízo é custo, não escolha de moeda.** O preço tirou apenas **−0,0952 SOL** (bruto da curva, −1,6 % por aposta de 0,07); as taxas e o rent tiraram **−0,2492**: pump.fun −0,0971, criador −0,0307, rede −0,0079 e **rent de ATA −0,1135**. Cada operação nasce a **−4,09 % do tamanho** (pump.fun 1,59 % + criador 0,50 % + rede 0,13 % + rent 1,86 %); **sem o rent, −2,23 %**. Com alvo +15 % isso move o acerto de equilíbrio de ~27 % para ~19 % — a mesa fez 26 % (23 alvos em 87).
2. **O rent de ATA é 32,7 % do prejuízo acumulado e não é perda de mercado — é dinheiro parado.** 75 das 87 compras criaram ATA (1 513 840 lamports cada) e **nenhuma das 87 vendas pediu reembolso** (`intent.closes_ata = false` em todas). Confirma e quantifica o KB-0146 num horizonte 3,6× maior: o que lá eram 0,0514 SOL em 34 contas, aqui são **0,1135 SOL** em 75.
3. **Nenhuma variável de decisão separa os 23 alvos dos 46 trailing de forma que sobreviva a correção de múltiplas comparações.** Testadas 13 (idade, progresso da curva, SOL real, `buys_1m`, `sells_1m`, vendas/compras, compradores únicos, snipers, fluxo líquido em SOL, delta de mcap 60 s, `dev_share`, fluxo por comprador, hora BRT) em terços nas 87 e em mediana nos 69 alvo/trailing, com bootstrap (10 000), permutação (10 000) e Benjamini-Hochberg FDR 10 %. **O p mais baixo é 0,046 contra um limiar BH de 0,0077.** Em particular **snipers (p 0,52) e `dev_share` (p 0,67) — dois filtros em que a mesa confia — não separam nada**, e a "manhã melhor que a tarde" do KB-0146 não se confirmou (p 0,27).
4. **A única pista é `buys_1m` (compras no minuto anterior à decisão), e na direção contrária à intuição: lançamento mais disputado dá pior.** Metade `≤ 25` compras/min: 34 % de alvos, **MFE mediano +28,1 %**; metade `> 25`: 20 % de alvos, MFE mediano +8,2 %. Diferença +0,0057 SOL/operação, IC 95 % por bootstrap de **cluster de mint** [−0,00034, +0,01207], P(dif ≤ 0) = 3,2 %; estável em direção ao tirar um dia de cada vez (+0,0036 a +0,0066). `unique_buyers_1m` e `mcap_delta_60s` contam a mesma história e são quase colineares — é um achado, não três. **O corte foi escolhido olhando para estes dados: crédito zero como estimativa de lucro futuro.**
5. **No horizonte de 300 s com alvo +15 %, o destino alvo-vs-trailing é dominado por segundos de timing, não pelas features de entrada.** Dez mints foram comprados por duas ou três propostas com 19–190 s de diferença; **em 8 desses grupos um lado saiu por alvo e o outro por trailing** — ANT (+0,0185 / −0,0150 com 61 s de diferença), BLEP, Aura (19 s), DVD, TANK, Cupsey, NARKY, Paidichi. O que a entrada pode mover é a *distribuição* (MFE mediano 3,4× maior), não o resultado de cada aposta.
6. **As saídas por trailing continuam a ser moedas que nunca subiram, não saídas prematuras.** MFE mediano dos 46 trailing: **+7,6 %**; dos 23 alvos: +46,7 %. Confirma o KB-0146 com 46 casos em vez de 15 — **não há motivo nestes dados para alargar o trailing.**
7. **`creator_dump` (14 ops, −0,0998 SOL) é cara-ou-coroa com n = 14.** **0 de 14 tinham `creator_net_seller = true` na entrada** e só 2 tinham `dev_share > 0` — o sinal não existia na decisão. Mediana de 52 s entre entrada e gatilho. Em 5 de 14 a moeda subiu forte depois da saída (PS +117 %, Drillers +115 %, RIB +83 %, Catbyte +85 %) e em 6 de 14 continuou a cair. Não mexer.
8. **`operator/6` vs `operator/5` é indistinguível:** −0,00524 vs −0,00357 SOL/operação, p de permutação **0,64** com n = 22 e 65. Os pares no mesmo mint mostram os dois conjuntos a comprar as mesmas moedas e a trocar de destino por segundos.

## Onde foi mostrado

Mesa real de memecoins, 16–21/09/2026, VPS (leitura `SELECT`/`COPY`). `meme_live_positions` com `status='closed'`: **87** (`operator/5` 65, `operator/6` 22); 174 ordens confirmadas + 9 vendas falhadas. Decomposição de custo lida de `meme_live_orders.fill` (`fee`, `creator_fee`, `network_fee_lamports`, `ata_rent_lamports`, `sol_amount`) — **86 das 87 reconciliam ao lamport** contra `pnl_sol`; a exceção é TAXCOIN (a primeira operação de sempre, 16/09), com 2 860 040 lamports em `unexplained_lamports` porque o parser daquela data ainda não separava o rent. Features na decisão lidas de `meme_proposals.reasons`. Fita `meme_trades` reconstruída a partir das reservas exatas do fill com ressincronização por foto `solana_rpc` (método R62/R64); 74 das 87 com fita, **13 só com fotos de 15 s (MFE/MAE são piso)**.

**Atenção:** as 87 **não** correram a mesma regra. 72 com `0,07 SOL / alvo 1,15× / 300 s / trailing 10 %` (só 19, 20 e 21/09; −0,2038 SOL), 12 com `0,05 / 3× / 1800 s / trailing 35 %` (16–18/09), 2 com `1,3× / trailing 20 %`, 1 com `3× / 1800 s`. **A regra atual tem 3 dias, não 6.** Restrita às 72, o corte `buys_1m ≤ 25` dá +0,0353 SOL (37 ops, 3 dias positivos, 3 sem operação) contra −0,1115 com o rent devolvido; o p de permutação sobe para 0,10.

## O que muda para nós

- **P0, operacional:** ligar `MEME_CLOSE_ATA_ON_FULL_SELL=1` e fechar as ATAs abertas. Recupera 0,1135 SOL já gastos e corta 1,86 pp do custo de cada operação futura. Refutação: abandonar se, nas primeiras 20 vendas com `closes_ata = true`, menos de 18 trouxerem `ata_rent_refund_lamports > 0`, ou se a taxa de vendas falhadas passar de 15 % (já há 9 falhas em 96).
- **P1, entrada, em sombra:** recusar `buys_1m` acima do **percentil 50 móvel de 3 dias** (não congelar "25"). 3 dias com braço de controlo em paralelo. Abandonar se o MFE mediano do braço baixo não ficar ≥ 10 pp acima do alto, ou se o PnL líquido médio do braço baixo for negativo em 2 dos 3 dias, ou se produzir < 5 entradas/dia. Desfecho principal é **PnL líquido**; MFE é secundário.
- **Não mexer:** regra de saída (trailing 10 % na entrada + 1,15× + 300 s continua a melhor de 52 braços do KB-0146), tamanho 0,07, `concurrent_positions ≤ 2`, `creator_dump`, escolha entre `operator/5` e `/6`, filtros de snipers e `dev_share`, hora do dia.
- **Para o futuro:** com 26 % de acerto e alvo +15 %, **o custo é o que decide se a mesa empata**. Qualquer proposta de "melhorar a estratégia" que não baixe o custo por operação ou não suba o acerto acima de ~19 % (pós-rent) é conversa.

## Ressalvas

n por balde 29–35; **6 dias de um único regime**; 13 das 87 só com fotos de 15 s; a fita tem buracos e as moedas que morreram mais depressa têm menos fita (sobrevivência); o caminho "segurar" ignora os nossos trades mas ressincroniza com fotos que já contêm a nossa venda, e a ordem intra-slot é por assinatura, não por execução; os contrafactuais filtram posições e reaproveitam o PnL realizado — **não re-simulam saídas**; o corte `buys_1m` foi escolhido nestes dados entre 13 variáveis. A mesa parou 21/09 12:08 BRT por rate-limit de RPC; 22/09 não tem dados.

## Como ligar (acrescentado 23/09/2026, T4.80)

> **Ler primeiro a secção "Fora de amostra (R67)" no fim desta nota: o veredito de hoje é NÃO
> LIGAR.** O que segue é só a mecânica do interruptor, entregue pela T4.80 para o dia em que
> houver evidência.

O interruptor do P1 existe desde a T4.80 e **nasce ausente** — nada mudou na mesa ao entregá-lo.
É `max_buys_1m` em `meme_rule_sets.params`, um **inteiro JSON puro** (a regra "decimais são
strings" não vale para contagens): recusa `buys_1m_above_max` quando a contagem do último minuto
**excede** o teto (inclusivo — 25 passa, 26 recusa) e `buys_1m_unknown` quando a fita não cobriu o
minuto (falha fechada). Vale nas duas pistas (15 s/mesa e evento), sempre com o valor do instante
da decisão. Detalhe em `docs/RISK_ENGINE_MEME.md` §9.

**Escrever a chave em `operator/5`/`/6` não é sombra — é ligar o filtro na mesa real**: a proposta
deixa de nascer, os contadores de `lab_gate_refusals` só existem depois de ligado e não há braço
contrafactual. Medir sem mexer na mesa é pôr a chave num conjunto `research_only` (um braço
`flow_v2` paralelo) ou ler o portão de evento em `MEME_EVENT_GATE=shadow`.

```bash
# ensaio (não escreve nada), depois o mesmo comando com --apply
uv run python infra/scripts/meme_rule_set.py --set-param max_buys_1m=25 \
  --rule-set operator/5 --rule-set operator/6 --apply \
  --reason "T4.80/R65 (KB-0147 §4): teto de compras no minuto na mesa real"

# desligar (a chave fica com valor null, que o leitor trata como ausente)
uv run python infra/scripts/meme_rule_set.py --set-param max_buys_1m=null \
  --rule-set operator/5 --rule-set operator/6 --apply \
  --reason "T4.80: desligar o teto de compras no minuto"
```

Ressalva que continua de pé: o corte 25 foi escolhido nestes mesmos dados (§4 e Ressalvas), e a
R67 não o confirmou fora da amostra. A R65 pedia o **percentil 50 móvel de 3 dias**, não um número
congelado — `max_buys_1m` é um valor fixo por conjunto, então quem o usar como P50 móvel tem de
reescrevê-lo diariamente com o comando acima (cada escrita fica em `meme_rule_set_param_history`).

## Relacionado

`obsidian/11-KNOWLEDGE/KB-0146-trailing-apertado-e-rent-de-ata.md` (o rent e a grade de saídas, n = 24) · `KB-0143` · `.claude/state/notes-R64.md` · `.claude/state/notes-R62.md` · `obsidian/05-EXPERIMENTS/EXP-M21`, `EXP-M22`

---

## Fora de amostra (R67, 23/09/2026) — `buys_1m ≤ 25` **não se confirmou**

*Secção acrescentada, não reescreve nada acima. Fonte: `.claude/state/notes-R67.md`, desenho pré-registado em `.claude/state/r67/preregistro.md`.*

**O que foi testado.** O ponto 4 acima (`buys_1m ≤ 25` como a única pista de entrada) foi escolhido **dentro** das 87 operações reais, entre 13 variáveis. O R67 levou-o a uma população independente: **473 moedas** — uma aposta de papel por mint, braços `flow_v2`, 12–21/09, fechadas e `measured`, **sem nenhum dos 76 mints do R65** e sem as propostas que também viraram posição real. O desfecho é retorno líquido por SOL arriscado; o teste foi **um só, congelado antes de correr** (corte fixo 25), com bootstrap por cluster de mint e permutação estratificada por dia (10 000 cada).

**Resultado.**

| | `≤ 25` | `> 25` |
|---|---|---|
| n | 176 | 297 |
| ret médio por SOL | **−0,0000** | **−0,0358** |
| ret **mediano** | −0,0620 | −0,0597 |
| apostas positivas | 36,9 % | 33,0 % |
| tocou 1,15× de máximo | 29,5 % | 30,0 % |

**D = +0,0358 · IC 95 % [−0,0575, +0,1355] · p = 0,43.** O critério pré-registado (D > 0 **e** IC todo positivo **e** p < 0,05) falha em dois dos três braços.

**Por que o achado do R65 não se sustenta como parâmetro:**

1. **A mediana não se move** (−0,0024, do sinal errado). A diferença de médias vem da cauda: a soma do braço `≤25` é −0,001 SOL/SOL e **sem as suas 3 maiores observações é −7,53**.
2. **A curva de limiares é um pico, não um planalto:** `≤15` +0,155 → `≤25` +0,036 → `≤60` **−0,004** → `≤80` +0,084. Percentil móvel de 3 dias: P30 +0,028, P40 +0,018, P50 +0,011, P60 +0,008.
3. **Ajustando só em 19–20/09 — os dias onde o 25 foi descoberto — o 25 tem sinal negativo (−0,027)** e o "melhor" limiar do ajuste é 40.
4. **O MFE não replica.** No R65 era +28,1 % vs +8,2 % de MFE mediano; aqui, 29,5 % vs 30,0 % de apostas que tocam 1,15×.
5. **5 de 10 dias com D negativo**; 18 apostas excluídas por `outcome_quality='indeterminate'` (3,7 % da amostra) chegam, no pior caso, para zerar o efeito (D = −0,0006).

**O que sobrevive:** condicionando (por estratificação, não por regressão) em idade, progresso da curva e SOL real na curva no instante da decisão, a diferença mantém sinal e tamanho (D ponderado +0,031, +0,040 e +0,040). **`buys_1m` não é proxy dessas três.** `unique_buyers_1m` é quase colinear e não serve de controlo.

**Formulação exata do veredito (acordada com a Astra):** *não confirmado*, **não** *refutado*. O IC 95 % contém o efeito estimado no R65 (+0,00573 SOL/operação ÷ 0,07 ≈ **+0,082 por SOL**) e este teste tem **~38 % de poder** para o detectar; seria preciso algo da **ordem de 1,3 mil mints** (aproximação normal, independência entre mints). E o teste mede a associação **sob a saída `flow_v2`** (0,05 SOL / 3× / 1800 s / trailing 35 %): **não confirma nem refuta benefício sob a saída real de 1,15× / 300 s**. Este holdout é de **mints**, não de período futuro — 9 dos 10 dias são os mesmos do R65, porque a mesa esteve parada em 22/09.

**O que muda para nós:**

- **Não ligar `max_buys_1m`** — nem 25 fixo, nem P50 móvel, nem o `≤15` que brilhou na varredura (esse vai para backlog, com pré-registo próprio e **dados futuros**).
- A **sombra** do P1 do R65 pode continuar (é barata e o efeito não foi excluído), mas **não é candidata a promoção** com esta evidência.
- **O P0 do R65 — recuperar o rent da ATA — continua a ser a única mudança que os dados sustentam.**
- **Um D positivo compara dois grupos; não demonstra estratégia lucrativa.** A média do braço selecionado é −0,0000 por SOL: "menos negativo" passa no contraste e continua a não ganhar dinheiro.

**O que mudaria a opinião:** ~1,3 mil mints independentes medidos **sob a política de saída real**, com D > 0 e IC 95 % inteiramente positivo; uma curva de limiares com planalto de ≥ 4 limiares; e a **mediana** a mover-se. Isso é sombra prospectiva, não mais análise retrospectiva destes mesmos dias.
