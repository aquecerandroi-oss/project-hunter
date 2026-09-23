# R73 — H-010, a concentração do maior comprador

**Data:** 23/09/2026, corte dos dados às ~20:2x UTC (17:2x BRT). **Pedido:** Everton, 17:3x BRT, a partir da
perda real do `AIRAA` (−0,0556 SOL, −77,6 %). **Pré-registo:** bloco H-010 da fila, usado verbatim.
**Método:** VPS só leitura (`ssh hunter-vps` + `docker exec hunter-postgres-1 psql`, só `SELECT`/`COPY TO STDOUT`;
nada escrito). Exports em `.claude/state/r73/` (`pop.csv` 1 566 linhas; `tape.csv` 144 859 trocas, 26 MB).
Reconstrução da fita herdada de R62/R64: SOL real da curva = soma com sinal de `sol_lamports` desde o nascimento.
Código: `load.py` (variável + guarda + cobertura), `build.py`, `run.py`, `test_load.py` (15 testes). Dinheiro em
`Decimal`, estatística em float, tempo UTC aware.

**Resposta curta.** **NÃO CONFIRMA — limite de dado.** A cláusula de cobertura da própria H-010 dispara antes de
qualquer contraste. O contraste exploratório também não confirma nem refuta. O contrafactual é o que interessa ao
Everton, e ele é desfavorável ao teto: **com a informação que tínhamos arquivada, o teto de 20 % matava o `SENTHOS`
(+19,6 %) e deixava passar o `AIRAA`.** Não ligar teto de concentração na mesa com base nisto.

## 1. Cobertura, primeiro (a regra manda parar abaixo de 60 %)

"Fita completa desde o nascimento" foi medida por duas condições independentes: a 1.ª troca da fita a ≤ 5 s do
`created_at` do token, **e** a fita reconstruir o `real_sol_reserves` da foto da curva da proposta (`quote`) a ±2 %
(banda de 1 s por causa da resolução do `block_time`).

| recorte | n | começa no nascimento | reconcilia com a foto | **as duas** | com a variável observável na decisão |
|---|---:|---:|---:|---:|---:|
| posições reais | 91 | 70 (76,9 %) | 49 (53,8 %) | **49 (53,8 %)** | 16 (17,6 %) |
| apostas de papel | 1 475 | 947 (64,2 %) | 711 (48,2 %) | **698 (47,3 %)** | 223 (15,1 %) |
| uma por mint | 694 | 459 (66,1 %) | 337 (48,6 %) | **331 (47,7 %)** | 79 (11,4 %) |

**Todas abaixo de 60 %: a regra dispara.** Eram 89 posições reais no pedido; no corte já eram 91 (todas
fechadas) e usei as 91. Mediana do erro de reconciliação: 2,8 %. p75: 60 %. Não é artefacto da tolerância: a 20 %
de folga a cobertura sobe só para 61 %.

**E com a guarda da T4.80 é muito pior.** Com a regra "uma troca só conta se `received_at <= decisão`", a fita
reconcilia com a foto em **1 das 91** posições reais. Das 91, **60 não tinham uma única troca no arquivo** no
instante da decisão. Causa medida: 100 % de `meme_trades` vem de `swap_api` (*polling*), e o atraso
`received_at − block_time` tem mediana **43,6 s**, p90 ≈ 129 s e p99 256 s. Quem tinha alguma fita via-a com
42 s de idade (mediana; p90 69 s).

## 2. O `AIRAA`: a premissa da origem não se verifica com o que persistimos

As 87 trocas do `AIRAA` anteriores à decisão, incluindo a compra de 8,89 SOL do criador `HTkSYn` às 20:01:02,
**chegaram ao arquivo num único poll às 20:03:25.43 UTC.** Isso é 6 s depois da nossa compra (20:03:19) e 6,6 s
depois da decisão (20:03:18.79). O brief dizia que "a compra estava na nossa própria fita há 2 minutos". **No
arquivo, não estava.**

**Correção da Astra, que aceitei e verifiquei:** a mesa não decide pelo arquivo. A proposta é do lane
`meme_event_gate_v1` (`reasons[0].series`), que mantém uma fita WS em memória
(`services/meme-worker/hunter_meme_worker/event_state.py`, `apply_trade`, `creator_trades`). Nessa decisão ela
tinha `buys_1m=31`, `unique_buyers_1m=14`, `net_sol_flow_1m=7,99` e `tape_reason=null`. **A mesa via trocas.** Se
via a compra do criador de 2 min antes, não dá para saber: a fita WS não é persistida troca a troca. A conclusão
honesta é então **"não verificável"**, não "a mesa não sabia".

Na fita retrospetiva, o `AIRAA` tinha `maior_comprador_pct` = **25,1 %**, e o maior comprador era **o criador**.

## 3. O contraste por tercil, com a cauda

**Variável principal = SOL líquido por carteira** (compras − vendas), como no brief. **Desvio declarado:** a
letra do bloco diz "soma de compras" (bruto). As duas estão abaixo, e mais o **estoque de tokens**
(contraexemplo da Astra: líquido em SOL ≠ o que ainda pode ser despejado). Desfecho = `pnl_sol / tamanho`, sob a
saída que cada mesa usou. Uma decisão por mint: a real ganha da de papel e, entre iguais, fica a mais antiga
(regra fixada sem olhar desfechos).

**(a) Com a guarda, só elegíveis (n = 79): amostra pequena demais e direção OPOSTA à tese**

| tercil | n | mediana var | ret médio | **cauda ≥ 50 % perda** | vitórias |
|---|---:|---:|---:|---:|---:|
| baixo (< 0,217) | 26 | 0,130 | −0,1947 | **30,8 %** | 19,2 % |
| meio | 26 | 0,311 | −0,1842 | **19,2 %** | 19,2 % |
| alto (≥ 0,662) | 27 | 0,973 | −0,1461 | **14,8 %** | 25,9 % |

**(b) Fita retrospetiva, oráculo (n = 562, a fita que hoje existe, não a que existia na decisão)**

| variável | cauda baixo / meio / alto | alto − baixo | IC 95 % | p (unilateral) | BH |
|---|---|---:|---|---:|---:|
| líquido SOL | 11,8 / 11,2 / 14,9 % | +3,1 pp | [−3,8, +10,1] | 0,229 | 0,344 |
| bruto SOL (letra do bloco) | 12,3 / 12,8 / 12,8 % | +0,5 pp | [−6,0, +6,9] | 0,503 | 0,503 |
| estoque de tokens | 10,9 / 9,8 / 17,8 % | +6,9 pp | [−0,1, +13,9] | 0,043 | **0,128** |

Nenhuma sobrevive ao BH. O estoque é a única na direção da tese pela cauda. É pista para uma medida nova, não
resultado.

**(c) Moinho** (`run_hypothesis`, fita retrospetiva, só os tercis extremos, limiar = máximo do tercil baixo,
cluster por mint, permutação estratificada por dia, 10 000 réplicas, semente 73):

- n = 375 (187 baixo / 188 alto), 375 clusters.
- **D (baixo − alto) = +0,0139 SOL/SOL.**
- IC de cluster [−0,0731, +0,0993]; IC de blocos [−0,0775, +0,1050].
- **p = 0,796.**
- Curva de limiares: **pico**.
- Veredito do moinho: **NÃO CONFIRMA.**
- A barra da fila (IC inferior de alto − baixo acima de −0,01, que espelhada fica em IC superior de baixo − alto
  abaixo de +0,01) **não é atingida**: não é refutação.
- Relatório completo em `.claude/state/r73/report.md`.

## 4. O contrafactual que importa: quantos ganhos o teto mata

Base: as 91 posições reais, com PnL total de **−0,3480 SOL**.

**Com a variável observável na decisão** (só 31 das 91 mensuráveis; nas outras 60 o teto não teria o que ler):

| teto | bloqueia | **vencedoras mortas** | Δ PnL |
|---:|---:|---:|---:|
| > 20 % | 11 | **2 (SENTHOS, KODA)** | +0,0632 |
| > 30 % | 6 | 1 | +0,0458 |
| > 40 % | 2 | 1 | +0,0033 |

**Com o oráculo (fita de hoje, 74 das 91 mensuráveis):**

| teto | bloqueia | **vencedoras mortas** | Δ PnL |
|---:|---:|---:|---:|
| > 20 % | 24 | **10** | +0,0060 |
| > 30 % | 10 | 4 | **−0,0255** |
| > 40 % | 4 | 2 | **−0,0280** |

**Os casos de teste:**

- **`SENTHOS` (+19,6 % real):** `maior_comprador_pct` = **68,0 %** observável (61,6 % no oráculo), e o maior
  comprador é **o criador**. Qualquer teto de 20–50 % o matava.
- **`AIRAA` (−77,6 %):** com a variável observável **não é bloqueado**, porque não havia fita no arquivo. Com o
  oráculo tem 25,1 % e é bloqueado a 20 %, mas não a 30 %.
- **`MMKT` (+63 %):** não observável (37 trocas bloqueadas pela guarda). No oráculo tem 18,6 %, mas numa fita que
  não começa no nascimento e reconstrói 13,7 SOL contra 35,6 SOL na foto: o valor não merece confiança.

O maior comprador é o criador em só 8,9 % das decisões. Dono concentrado é tanto o `SENTHOS` que subiu como o
`AIRAA` que afundou.

## 5. Veredito

**H-010 concluída — NÃO CONFIRMA por limite de dado.** A cobertura desde o nascimento fica abaixo de 60 % em
qualquer leitura (47–54 % na retrospetiva, 1–7 % na observável), e a própria regra pré-registada diz que isso é
limite de dado, não resultado. **Sem CONFIRMA não há braço de papel.** Não recomendo configurar
`max_top10_share` nem um teto de `maior_comprador_pct` nas mesas `operator/5` e `operator/6`. O `max_top10_share`
lê `features.top10_share` das fotos de holders, que é outra medida; este estudo não o testa diretamente.

**Para reabrir (medida nova, regra 1 da fila):** persistir por troca a fita WS que a mesa usa na decisão, ou
gravar em `reasons` o maior comprador e o seu estoque no instante da decisão. Depois, pré-registar a variável de
**estoque de tokens**.

## 6. A ressalva que mais importa

**O arquivo `meme_trades` não é o que a mesa sabia.** Ele é uma cópia por polling, atrasada em ~44 s, e a fita WS
que decide não é persistida troca a troca. Todo estudo que reconstrói features de fita a partir de `meme_trades`
(R62–R72 incluídos) mede, na melhor das hipóteses, a fita retrospetiva. Com a guarda de chegada aplicada, esses
estudos ficariam quase sem população.

## Segunda opinião (Astra)

- **Revisão do carregador, antes de correr** (`.claude/state/astra-review-r73.md`). Todos os achados foram
  aplicados antes de qualquer desfecho:
  - teste errado na banda de 1 s (somava 16, a fita soma 21): corrigido;
  - elegibilidade dependente de chegada atrasada: separei cobertura observável (`known_by`) de retrospetiva;
  - líquido ≠ estoque: acrescentei bruto e estoque;
  - reconciliação necessária mas não suficiente: acrescentei a âncora de nascimento e um teste que prova o
    buraco que ainda escapa;
  - regra de refutação espelhada: aplicada à mão, sem usar o rótulo do moinho;
  - limiares no vazio central: a varredura corre na população inteira.
- **Revisão do veredito** (`.claude/state/astra-review-r73-veredito.md`). Concorda com "concluída — NÃO CONFIRMA
  por limite de dado". Três must-fix, todos aplicados:
  1. a coluna "ambas" misturava elegibilidade com cobertura: corrigido (53,8 / 47,3 / 47,7 %);
  2. o `AIRAA` prova ausência no arquivo, não na mesa, porque há a fita WS do `meme_event_gate_v1`: verificado em
     `meme_proposals.reasons` e reescrito como "não verificável";
  3. a fronteira do tercil no moinho deslocava uma linha (188/187): corrigido para 187/188. Os números batem com
     a reprodução independente dela (D +0,0139, p 0,7959).
- **Rejeitado:** nada.
