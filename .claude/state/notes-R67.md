# R67 — `buys_1m ≤ 25` fora de amostra: **não confirmado**. Fica em sombra.

**Pergunta (Everton, 23/09/2026 11:0x BRT):** "hoje vamos achar uma estratégia e cair em cima dela." O único candidato era a pista do R65: **`buys_1m` (compras no minuto anterior à decisão) inversamente relacionado com o desfecho** — nas 87 operações reais, `≤ 25` deu 34 % de alvos e MFE mediano +28,1 % contra 20 % e +8,2 %. O próprio R65 avisou: **o corte foi escolhido dentro da amostra e não vale nada até sobreviver fora dela.**

**Método:** leitura read-only da VPS (`ssh hunter-vps` + `docker exec hunter-postgres-1 psql`, só `COPY TO STDOUT`; nada foi escrito). Desenho **pré-registado antes de correr** em `.claude/state/r67/preregistro.md`, emendado uma vez depois da revisão de desenho da Astra e **ainda antes** de qualquer teste. Análise em `.claude/state/r67/`. Dinheiro em `Decimal`.

---

## Resposta curta

**Não. Veredito (b): não confirmado fora de amostra — `buys_1m` fica só em sombra. Não ligar `max_buys_1m` na mesa real.**

**Precisão de linguagem (exigida pela Astra, e correta):** *não confirmado* ≠ *refutado*. O intervalo de confiança contém zero **e** contém efeitos que seriam relevantes. O que este estudo autoriza dizer é: **não confirmou a associação sob as políticas de saída `flow_v2`; não confirma nem refuta benefício sob 1,15× / 300 s.**

Em **473 moedas independentes** (uma aposta de papel por mint, braços `flow_v2`, 12–21/09, sem nenhum dos 76 mints do R65), o corte congelado `buys_1m ≤ 25` dá **D = +0,0358 de retorno líquido por SOL arriscado, IC 95 % [−0,0575, +0,1355], p de permutação 0,43**. O critério de confirmação pré-registado (D > 0 **e** IC 95 % inteiramente positivo **e** p < 0,05) **falha em dois dos três braços**.

E há três sinais de fragilidade, coerentes com artefacto e não com efeito (nenhum deles *prova* artefacto):

1. **A mediana não se move.** Retorno mediano `≤25` −0,0620 vs `>25` −0,0597 — **diferença de medianas −0,0024**, do sinal errado. Toda a diferença de médias vem da cauda: a soma do retorno do braço `≤25` é **−0,001**; sem as suas **3 maiores** observações é **−7,53**. Cinco das 10 maiores observações da fatia estão no balde alto.
2. **A curva de limiares é um pico, não um planalto.** `≤15` D=+0,155 → `≤20` +0,078 → `≤25` +0,036 → `≤30` +0,039 → `≤40` +0,033 → `≤60` **−0,004** → `≤80` +0,084. Um efeito real dá planalto. Ressalva da Astra, aceite: a diluição ao alargar o grupo também aconteceria se o efeito fosse **localizado** nos lançamentos mais calmos — o pico não *prova* artefacto, apenas não sustenta o 25.
3. **O número 25 tem o sinal errado quando é ajustado noutro sítio.** Ajustando só em 19–20/09 (os dias que geraram o achado), `≤25` dá **D = −0,027** e o melhor limiar do ajuste é **40**.

**A ressalva que mais importa (potência).** O efeito do R65 era +0,00573 SOL por operação de 0,07 SOL = **+0,082 por SOL**, e o meu IC 95 % **[−0,058, +0,136] contém +0,082**. Portanto: **não confirmo e também não excluo** um efeito daquele tamanho. Com o erro-padrão medido (0,0492) este teste tem **~38 % de poder** para o detectar; para o distinguir de zero com 80 % seria preciso algo da **ordem de 1,3 mil mints** (≈ 2,8× o que existe). Esse número é **aproximado** — supõe aproximação normal, variância e proporções constantes e independência entre mints; dependência temporal e caudas pesadas podem mudá-lo bastante. E a referência de +0,082 por SOL é a normalização **aproximada** do efeito agregado do R65 (+0,00573 SOL por operação ÷ 0,07 SOL), numa amostra que misturava tamanhos e políticas de saída — não é uma normalização exata. O que está demonstrado é: *o efeito, fora de amostra, é menos de metade do estimado e indistinguível de zero; e o valor 25 não é um parâmetro estável.*

---

## 1. Onde `buys_1m` está persistido na decisão (a primeira coisa a verificar)

**Está.** Para as apostas de papel, `meme_proposals.reasons` carrega o bloco `{"feature":"flow", "buys_1m":…, "sells_1m":…, "unique_buyers_1m":…, "snipers":…, "dev_share":…, "net_sol_flow_1m":…, "mcap_delta_60s":…}` — **exatamente o mesmo campo, gravado no mesmo instante, que o R65 usou nas 87 reais** (`.claude/state/r65/load.py:_flow`). Não foi preciso reconstruir nada de `meme_trades`.

Cobertura por braço (apostas fechadas, 12–23/09, `q1.sql` → `paper.csv`, 1 463 linhas / 480 KB):

| braço | params | tem `buys_1m` |
|---|---|---|
| `flow_v2/1..9` | 0,05 SOL / 3× / 1800 s / trailing 35 % armado a 1,5× | **sim, todas** |
| `hype_probe_v0/2` | 0,01 / 3× / 600 s / trailing 40 % | sim |
| `operator/5,6` | 0,07 / 1,15× / 300 s / trailing 10 % (dias 19–21) | sim |
| `moonshot_v0/1,2`, `meme_paper_v0/1`, `hype_probe_v0/1`, `operator/1,2` | — | **não** (excluídos) |

Não há apostas de papel em **22/09** (mesa parada por rate-limit de RPC desde 21/09 12:08 BRT) e só **1 aberta** em 23/09 — logo **o teste prospectivo de 22–23/09 pedido no brief não existe**.

## 2. A fatia principal e por que ficou com 473 linhas

| passo | n |
|---|---|
| apostas de papel fechadas, `outcome_quality='measured'`, com `buys_1m`, sem proposta partilhada com uma posição real | 1 143 |
| só `flow_v2` (params idênticos entre versões) | 1 069 |
| **menos os 76 mints do R65** | 971 |
| **uma aposta por mint** (a mais antiga) | **473** (473 mints, 10 dias) |

As duas últimas exclusões são a correção mais importante que a Astra pediu **no desenho** (`.claude/state/astra-review-r67-design.md`): vários braços `flow_v2` propõem **a mesma moeda no mesmo tique**, e sem deduplicar um único movimento de preço vira cinco "confirmações". Com uma linha por mint, a permutação dentro do dia é válida e o bootstrap por linha **é** o bootstrap por cluster. 85 apostas de papel partilhavam `proposal_id` com uma posição real e foram cortadas antes disso.

**Distribuição de `buys_1m` na fatia:** p10 13, p25 20, mediana **31**, p75 57, p90 97. O corte 25 apanha **37,2 %** das entradas — é mais apertado aqui do que era nas 87 reais (lá era a mediana).

## 3. O teste primário (um só, congelado antes de correr)

Desfecho: **retorno líquido por SOL arriscado**, `ret = pnl_sol / size_sol` (o PnL de papel já desconta 1,75 % de taxa; não tem rent de ATA).

| braço | n | ret médio | ret mediano | apostas positivas | `hit15` |
|---|---|---|---|---|---|
| `buys_1m ≤ 25` | 176 | **−0,0000** | −0,0620 | 36,9 % | 29,5 % |
| `buys_1m > 25` | 297 | **−0,0358** | −0,0597 | 33,0 % | 30,0 % |

**D = +0,0358 · IC 95 % (bootstrap de 10 000 por cluster de mint) [−0,0575, +0,1355] · P(D ≤ 0) = 0,23 · p de permutação estratificada por dia (10 000) = 0,43.**
No desfecho binário "aposta positiva": 36,9 % vs 33,0 %, **p = 0,41**.

**`hit15` (atingiu 1,15× de máximo) é 29,5 % contra 30,0 % — praticamente igual, e do sinal errado.** É o contraponto mais direto ao R65: lá o MFE mediano era +28,1 % vs +8,2 %, uma diferença de 3,4×. **Não se replica.** (`hit15` é descritivo por construção — depende da política de saída de cada braço, que decide quanto tempo a aposta vive; não entra em nenhum critério, como a Astra exigiu.)

Baldes por tercis (descritivo):

| balde | n | `hit15` | ret médio | ret mediano | hold mediano |
|---|---|---|---|---|---|
| ≤ 23 | 159 | 30,2 % | +0,0068 | −0,0610 | 99 s |
| 23–43 | 157 | 24,2 % | −0,0217 | −0,0588 | 79 s |
| > 43 | 157 | **35,0 %** | −0,0530 | −0,0601 | 75 s |

A monotonia do R65 aparece na **média** e some na **mediana** e no `hit15` — que é exatamente o que acontece quando o que se está a medir são três ou quatro apostas grandes.

## 4. É um planalto ou um pico? — **pico**

| limiar | n (≤ / >) | D | IC 95 % | P(D ≤ 0) |
|---|---|---|---|---|
| ≤ 10 | 10 / 463 | — | amostra insuficiente | — |
| ≤ 15 | 67 / 406 | **+0,1550** | [+0,0040, +0,3305] | 0,022 |
| ≤ 20 | 125 / 348 | +0,0779 | [−0,0269, +0,1946] | 0,075 |
| **≤ 25** | 176 / 297 | **+0,0358** | [−0,0553, +0,1324] | 0,235 |
| ≤ 30 | 236 / 237 | +0,0390 | [−0,0479, +0,1285] | 0,193 |
| ≤ 40 | 298 / 175 | +0,0331 | [−0,0506, +0,1191] | 0,223 |
| ≤ 60 | 362 / 111 | **−0,0037** | [−0,1044, +0,0932] | 0,529 |
| ≤ 80 | 413 / 60 | +0,0843 | [−0,0297, +0,1920] | 0,073 |

Percentil móvel de 3 dias (corte do dia calculado **só com os 3 dias anteriores** — sem antecipação): P30 (cortes 21–25) D=+0,028; P40 (26–30) +0,018; P50 (28–35) +0,011; P60 (32–43) +0,008. **Monótono a decair para zero conforme o corte afrouxa** — consistente com "o pouco que há está nos 15 % mais calmos", mas nenhum destes contrastes tem IC que exclua zero.

**Sobre o pico em `≤ 15` (D=+0,155):** o `P(D≤0)=0,022` é a **fração de réplicas de bootstrap abaixo de zero**, não um p ajustado pela busca nem a probabilidade da hipótese. É o oitavo limiar testado nesta varredura, num estudo que já é a segunda passagem sobre a mesma hipótese; n=67; e a maior observação da fatia inteira (`ret` +3,76) tem `buys_1m` 13. **Vai para o backlog como hipótese exploratória** e só volta com pré-registo próprio, justificação própria, **dados futuros** e orçamento de testes definido. Promovê-lo hoje seria repetir exatamente o erro que o R65 cometeu com o 25.

## 5. Sensibilidades pré-definidas

| sensibilidade | n (≤/>) | D | IC 95 % | p |
|---|---|---|---|---|
| **principal** | 176/297 | +0,0358 | [−0,0575, +0,1355] | 0,43 |
| sem dedup (todas as apostas `flow_v2`) | 335/636 | **+0,0059** | [−0,0938, +0,1062] | 0,85 |
| com os mints do R65 dentro | 202/317 | +0,0255 | [−0,0634, +0,1169] | 0,55 |

**Aparagem simétrica das caudas** (k maiores e k menores da fatia): k=1 D=+0,020 (p 0,65); k=2 +0,037 (0,35); k=3 +0,021 (0,58); k=5 +0,034 (0,34); k=10 +0,021 (0,54). **Nunca se aproxima de significância**, com ou sem cauda.

**Leave-one-day-out:** D entre +0,008 e +0,056, sempre positivo — estável em sinal, nunca em tamanho, e nunca significativo.

**Por dia (10 dias): 5 com D negativo.** 12/09 +0,311 (n=2/7), 13/09 +0,413, 14/09 −0,088, 15/09 −0,036, 16/09 −0,028, 17/09 −0,004, 18/09 +0,136, 19/09 +0,037, **20/09 −0,244**, 21/09 +0,069. Não há um dia em que a regra "funcione"; há dois dias em que uma moeda explodiu do lado certo.

**Split temporal (ajustar 19–20/09, testar 21/09):** no ajuste (n=131) o D por limiar é `{15: −0,013, 20: −0,054, 25: −0,027, 30: +0,050, 40: +0,106, 60: +0,061}` — **o corte 25 é negativo exatamente nos dias onde o R65 o descobriu**, e o "melhor" do ajuste é 40. Em 21/09 (n=22) ambos ficam positivos (+0,086 com 40, +0,069 com 25). **n=22 não decide nada** e o próprio 21/09 participou da descoberta do R65 — é reportado por completude, não como prova.

## 6. Confundimento: `buys_1m` é proxy de idade / progresso / SOL na curva?

Estratificando (não ajustando) por tercis e ponderando as diferenças dentro dos estratos:

| condicionante | estrato 1 | estrato 2 | estrato 3 | D ponderado |
|---|---|---|---|---|
| idade (s): ≤80 / 80–138 / >138 | +0,0405 | +0,0202 | +0,0331 | **+0,0314** |
| progresso %: ≤39,1 / 39,1–56,5 / >56,5 | +0,0666 | +0,1101 | **−0,0568** | **+0,0402** |
| SOL real na curva: ≤11,3 / 11,3–21,3 / >21,3 | +0,0582 | +0,0717 | **−0,0101** | **+0,0400** |

**O (pouco) efeito não é explicado por idade, progresso nem SOL na curva** — sobrevive à estratificação com o mesmo sinal e o mesmo tamanho (aliás, ligeiramente maior). Isto é o único ponto a favor da hipótese neste relatório. Mas "sobrevive a um controlo" não é o mesmo que "existe": o que sobrevive continua a ser um D de +0,03 a +0,04 com p de 0,43.

`unique_buyers_1m` **não serve de controlo**: é quase colinear com `buys_1m` (os estratos ficam 150/16, 26/128 e 0/153 — o terceiro sem nenhuma observação do lado baixo). O "D ponderado −0,041" que sai dessa estratificação **não é evidência de nada**, é a aritmética de células vazias, e está aqui apenas para não esconder um número que corri.

## 7. Fatias secundárias — todas pequenas demais para decidir

| fatia | n (≤25 / >25) | D | comentário |
|---|---|---|---|
| `hype_probe_v0/2` (0,01 / 3× / 600 s), dedup, sem mints do R65 | 13/31 | +0,0035 (p 0,98) | nada |
| `operator` de papel (o que sobra depois de excluir as partilhadas com o real) | **3/11** | +0,61 | **ruído puro**, uma observação; não interpretar |
| **reais 16–18/09** (15 operações) | 4/11 | +0,078, IC [−0,52, +0,80] | **não é holdout** — estas 15 entraram nas 87 onde o corte foi descoberto |

A fatia que o brief mais queria — `operator/5,6` de papel, com **os mesmos params da mesa real** — evaporou: das ~84 apostas, quase todas partilham `proposal_id` com uma posição real e foram excluídas por pureza; sobraram 14, com 3 de um lado. **Dizer qualquer coisa a partir dela seria desonesto.**

## 8. Risco de seleção nas exclusões (apontado pela Astra) — sensibilidade entregue

`excl.py` → `excl.txt`. Aplicando às apostas `indeterminate` **a mesma seleção da fatia principal** (só `flow_v2`, sem os mints do R65, sem proposta partilhada com o real, e só mints ainda não representados): sobram **18** — **3,7 %** da fatia. **33,3 %** delas têm `buys_1m ≤ 25` contra 37,2 % na fatia principal; os motivos são `time_stop` e "sem saída"; todas têm `pnl_sol` gravado; por dia estão espalhadas (máximo 4 num dia).

Repondo-as no contraste:

| cenário | n (≤/>) | D | IC 95 % | p |
|---|---|---|---|---|
| (0) só `measured` — referência | 176/297 | +0,0358 | [−0,0575, +0,1355] | 0,43 |
| (a) indeterminadas com `ret = 0` | 182/309 | +0,0344 | [−0,0560, +0,1280] | 0,44 |
| **(b) pior caso** (p10 = −0,511 no braço `≤25`, p90 = +0,467 no `>25`) | 182/309 | **−0,0006** | [−0,0921, +0,0951] | 0,99 |
| (c) melhor caso (simétrico, só por simetria) | 182/309 | +0,0697 | [−0,0243, +0,1630] | 0,13 |

**Leitura:** a exclusão **não fabricou** o resultado — o cenário neutro reproduz a referência. Mas **18 apostas, 3,7 % da amostra, chegam para o zerar**. Isso não muda o veredito; mede quão pequeno e frágil o efeito é. E composição parecida **não afasta** seleção pelo desfecho: fica registado como limitação, não como verificação concluída.

## 9. Veredito e parâmetro

> **(b) Não confirmado fora de amostra. Manter `buys_1m` em sombra; não introduzir `max_buys_1m` na mesa real.**

E uma frase que a Astra fez questão de separar, e que é verdade: **um D positivo compara dois grupos; não demonstra estratégia lucrativa.** A média do braço selecionado é −0,0000 por SOL — "menos negativo" passa no contraste e continua a não ganhar dinheiro.

O que fica escrito para hoje:

- **Não há parâmetro a ligar.** Nem `25` fixo, nem `P50 móvel` (D=+0,011), nem o `≤15` que brilhou na varredura.
- **O P0 do R65 continua a ser a única mudança que estes dados sustentam:** recuperar o rent da ATA (+0,1135 SOL já gastos, −1,86 pp de custo por operação, acerto de equilíbrio de ~27 % para ~19 %). Isso é operação, não estratégia, e não depende de nada aqui.
- **A sombra do R65 (P1) pode continuar**, porque é barata e porque este estudo não exclui o efeito; mas **não é candidata a promoção** com o que se sabe, e a regra de promoção escrita no R65 §6 continua a valer tal como está.

**O que mudaria a minha opinião (regra de refutação da refutação, escrita agora):**

1. **Mais massa independente com a saída certa.** ~1 340 mints (2,8× o que há) medidos sob **a política de saída real** (1,15× / 300 s / trailing 10 %) — e não sob 3×/1800 s — com D > 0 e IC 95 % inteiramente positivo. Hoje temos 473 mints sob a saída errada.
2. **Planalto, não pico.** A curva de limiares tem de ter ≥ 4 limiares consecutivos com D positivo e de tamanho comparável. Hoje o D cai 4× de `≤15` para `≤25` e troca de sinal em `≤60`.
3. **A mediana tem de andar.** Enquanto a diferença de medianas for ~0 e a de médias vier de 3 observações, o que está a ser medido é a cauda, não a seleção de entrada.
4. Um teste prospectivo limpo (sombra, braço de controlo em paralelo, ≥ 5 entradas/dia por braço, 3 dias) resolve os três ao mesmo tempo. **É isso que é preciso — não mais análise retrospectiva destes mesmos dias.**

## 10. Ressalvas honestas

1. **A maior: a população de teste corre uma política de saída diferente da mesa real.** `flow_v2` é 0,05 SOL / alvo 3× / 1800 s / trailing 35 % armado a 1,5×; a mesa é 0,07 / 1,15× / 300 s / trailing 10 %. Isto testa a **associação entre fluxo de entrada e retorno sob a saída `flow_v2`**; a transferência para 1,15×/300 s **não está demonstrada** e a direção pode, em princípio, mudar com a saída. É por isso que o veredito é **"não confirmado"** e não **"refutado"**.
2. **Potência.** O IC contém o efeito do R65 (+0,082/SOL). ~38 % de poder. Ausência de prova, não prova de ausência.
3. **`hit15` depende da política de saída** e não mede "probabilidade de tocar +15 % em 300 s". O desfecho correto (máximo em 300 s fixos desde o fill, medido mesmo depois da saída da aposta) **não está coberto por esta coleta** e não foi calculado.
4. **PnL de papel é marcado na curva**, não executado: não tem derrapagem real, não tem rent de ATA, não tem venda falhada. Comparações são sempre **dentro** do papel.
5. **Este holdout é de MINTS, não de período futuro.** Excluí os 76 mints do R65 e deduplico por mint, mas **9 dos 10 dias são os mesmos dias em que o R65 procurou** (12–21/09). Mints distintos **não** garantem independência temporal: um regime de mercado partilhado move os dois lados juntos. O holdout temporal verdadeiro (22/09 em diante) **não existe** porque a mesa esteve parada.
6. **10 dias, um regime, um mercado.** Todas as apostas são pump.fun, setembro de 2026. Nada aqui generaliza.
7. **22/09 não existe** e 23/09 tem uma aposta aberta: o teste prospectivo puro (dias posteriores ao R65) **não foi possível**, e é exatamente o que falta.
8. **Os 21 braços/versões `flow_v2` não são idênticos em gate** (só nos params de saída). Dias com mais versões ativas pesam mais na fatia sem dedup; a dedup por mint mitiga, não elimina.

## 11. Segunda opinião (Astra)

Duas chamadas: **desenho antes de correr** (`.claude/state/astra-review-r67-design.md`) e **veredito depois** (`.claude/state/astra-review-r67-veredito.md`).

**No desenho ela mudou o estudo, não a redação** — quatro correções aceites e aplicadas antes de qualquer teste, registadas na Emenda 1 de `preregistro.md`:
1. **Independência era a maior armadilha:** excluir só `proposal_id` partilhado não chega; braços diferentes propõem o mesmo mint no mesmo tique. → exclui os 76 mints do R65 **e** deduplico para uma aposta por mint. (Sem isto, o D teria sido calculado sobre 971 linhas com 543 mints e a inferência seria inválida.)
2. **`hit15` é descritivo**, dependente da saída; não corrigir por hold (é variável posterior à entrada). → saiu de todos os critérios.
3. **Excluir `indeterminate` pode selecionar** → §8.
4. **A permutação tem de preservar os clusters**, não só o bootstrap → resolvido pela dedup (uma linha por mint = cluster unitário).
Ela também pediu que eu retirasse "3 de 4 fatias" e "dois IC excluem zero" do critério de sucesso (reintroduziriam significância por trás de testes declarados exploratórios) e que as 15 reais de 16–18/09 fossem declaradas **não-holdout**. Aceite tudo.

**No veredito ela concordou com o resultado e apertou a linguagem.** Confirmou o cálculo de potência por conta própria (`SE = 0,049236; N = 1 343`). O que aceitei e corrigi neste documento depois de ler a resposta:

1. **"Não confirmado", nunca "refutado"** — §Resposta curta. E a formulação de transferência: *"não confirmou a associação sob as políticas `flow_v2`; não confirma nem refuta benefício sob 1,15×/300 s"*.
2. **A conta de potência não pode virar promessa** — "ordem de 1,3 mil mints", com as suposições declaradas, e a normalização +0,082/SOL declarada aproximada.
3. **A sensibilidade das exclusões estava prometida no pré-registo e eu não a tinha entregue** — corri-a (`excl.py`, §8) e o pior caso zera o efeito.
4. **Eram 5 dias negativos, não 4** (17/09 é −0,0035). Corrigido.
5. **O pico em `≤15` é exploratório, não prova de artefacto**; `0,022` é fração de réplicas de bootstrap, não p ajustado pela busca. Vai para backlog com pré-registo próprio e dados futuros.
6. **Este holdout é de mints, não de período futuro** — mints distintos não garantem independência temporal, e 9 dos 10 dias são os mesmos dias do R65. Escrito em §10.
7. **"D positivo compara grupos; não demonstra estratégia lucrativa"** — §9.

**Onde não há desacordo:** nenhum. Ela subscreve "não ligar `max_buys_1m` no real com esta evidência" e a frase que eu levaria ao Everton: **"hoje escolhemos um experimento, ainda não uma estratégia comprovada."**

## 12. Arquivos

`.claude/state/r67/`: `preregistro.md` (desenho congelado + emenda), `q1.sql` → `paper.csv` (1 463 apostas, 480 KB), `r65_mints.txt` (76), `load67.py`, `stats67.py`, `oos.py` → `oos.txt`, `tails.py` → `tails.txt`, `excl.py` → `excl.txt`. Total ~580 KB. Astra: `.claude/state/astra-review-r67-design.md`, `.claude/state/astra-review-r67-veredito.md`. KB: `obsidian/11-KNOWLEDGE/KB-0147-custo-e-o-prejuizo-e-buys-1m-e-a-unica-pista.md` (secção fora de amostra acrescentada).

## 13. Proposta de linha de diário (23/09)

> **23/09 R67 — a única pista do R65 não se confirmou fora de amostra.** Testei `buys_1m ≤ 25` em **473 moedas independentes** (uma aposta de papel por mint, braços `flow_v2`, 12–21/09, sem nenhum dos 76 mints do R65), com o desenho pré-registado antes de correr: **D = +0,036 de retorno por SOL, IC 95 % [−0,058, +0,136], p = 0,43**. A mediana não se move (−0,0620 vs −0,0597) e a média inteira vem da cauda: sem as 3 maiores, o braço `≤25` vai de −0,001 para **−7,53**. A curva de limiares é um **pico** (≤15 +0,155, ≤25 +0,036, ≤60 −0,004), não um planalto; e ajustando só em 19–20/09 — os dias onde o R65 achou o 25 — **o 25 tem o sinal errado (−0,027)**. O MFE, que no R65 era +28 % vs +8 %, aqui é 29,5 % vs 30,0 % de apostas que tocam 1,15×: **não se replica**. O efeito sobrevive a condicionar por idade, progresso e SOL na curva (D ponderado +0,031 a +0,040), mas isso só diz que o pouco que há não é proxy de outra coisa. **Veredito: não confirmado — fica em sombra, sem parâmetro para a mesa real.** (Não é o mesmo que refutado: o intervalo ainda contém efeitos relevantes.) A ressalva que mais importa: o meu IC **contém** o efeito do R65 (+0,082/SOL) e este teste tem ~38 % de poder — seria preciso algo da ordem de 1,3 mil mints, e **sob a política de saída real**, não sob 3×/1800 s. O que resolve isto não é mais análise destes dias: é sombra prospectiva. **A única mudança que os dados sustentam continua a ser o P0 do R65: recuperar o rent da ATA.**
