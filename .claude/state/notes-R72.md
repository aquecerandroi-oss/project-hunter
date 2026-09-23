# R72 — H-009, o giro rápido na oscilação: a oscilação existe, o giro não paga

**Pergunta (Everton, 23/09/2026 17:1x BRT):** *"conforme vai acompanhando o gráfico, vai comprando
e vendendo muito rápido: desceu comprou, subiu vendeu, desceu comprou, subiu vendeu — e lucra antes
de alguém vender tudo e derrubar."*
**Pré-registo:** H-009 em `obsidian/11-KNOWLEDGE/Fila de Hipoteses.md` (previsão e regra de
refutação usadas **verbatim**).
**Método:** reconstrução da fita trade a trade herdada de R62/R64/R65
(`.claude/state/r62/analyze.py`, `.claude/state/r64/load.py`), leitura **read-only** da VPS
(`SELECT`/`COPY TO STDOUT`), exportações em `.claude/state/r72/` (25 MB). Nada foi escrito na VPS.

---

## Resposta curta

**A oscilação existe — e mesmo assim o giro não paga. Veredito: `NÃO CONFIRMA`.**

A parte da ideia que estava em dúvida — *"será que a moeda sobe e desce tanto assim em 5 minutos?"* —
**está confirmada**: a mediana é de **3,5 a 4 oscilações completas de 3 %** por posição nos cinco
minutos seguintes à entrada, e 70 % das posições têm ≥ 2. A regra de refutação barata da fila
(*"mediana de giros < 2"*) **não dispara**. O estudo teve de continuar.

O que não se sustenta é a segunda metade: **0 de 12 células confirmam, nas duas populações**. A
diferença entre a política de giros e a regra atual vai de **−4,24 % a +4,44 % por SOL arriscado**
nas 76 posições reais; **todos os 12 intervalos de confiança atravessam zero** e o menor p de
permutação é **0,12**. O pré-registo pedia **+0,05 por SOL (+5 %)** com suporte estatístico: nenhuma
célula chega lá. Mas a refutação da fila também **não** foi atingida (limite superior do IC até
**+10,34 %**, contra o +1 % que refutaria). Portanto: **não sabemos, não é falso.**

**A oscilação de equilíbrio é 2,2176 %** (custo 2,23 % por ida e volta): abaixo disso nenhum giro
paga, por melhor que seja a execução. A fita entrega giros desse tamanho com folga (mediana 5 por
posição). **O teto da ideia não está na amplitude — está no que acontece entre os giros.**

---

## 1. Dados e cobertura (a ressalva que vem primeiro)

| item | reais | papel |
|---|---|---|
| população | `meme_live_positions` `status='closed'` → **89** (17/09 00:31 a 23/09 19:31 UTC) | `meme_paper_bets` fechadas, **uma por mint**, `leg <> 'probe'` → **545** |
| só com fotos de ~15 s — **excluídas e contadas** | **13** | **62** |
| com fita mas < 3 trades dentro dos 300 s | 0 | **20** |
| **resolvíveis (o censo)** | **76** | **463** |
| maior buraco entre pontos na janela de 300 s | p25 16 s · **mediana 45 s** · p75 62 s | p25 18 s · **mediana 54 s** · p75 82 s |
| posições com algum buraco > 30 s | **44 de 76** | **309 de 463** |
| regressões de relógio corrigidas | 183 | 1 070 |

As 13 exclusões reproduzem o R65 (*"13 das 87 só têm fotos"*) e o aviso do R64 (5 de 24). Uma
cadência de 15 s **não resolve** uma oscilação de 3 % em 30 s: essas posições não podem responder à
pergunta e ficam fora, contadas.

**A ressalva que importa mais, e fica em primeiro lugar (achado da Astra):** ter fita não prova
continuidade da fita. Em **44 de 76** posições reais e **309 de 463** de papel há pelo menos um
intervalo de mais de 30 s sem nenhum ponto. Nesses trechos, ausência de oscilação **não é prova de
ausência** — pode ser perda de coleta do `swap_api` por REST (limitação já conhecida do R65 §8).
Por isso: as células **N = 30 s são exploratórias**, e nenhuma refutação se apoia nelas.

**Desvio declarado face a R64/R65:** o carregador antigo reconstruía por `slot` e depois **reordenava
os estados prontos por timestamp**. A Astra mostrou com um contraexemplo que isso faz o caminho
**voltar a um slot antigo** e fabricar uma queda. Aqui a ordem é a da cadeia e o carimbo é monótono
não-decrescente. Isso corrigiu **183 regressões** nas reais e **1 070** no papel. É uma melhoria, não
uma reprodução — os números do R72 não são comparáveis linha a linha com os do R64.

---

## 2. Passo 1 — a oscilação existe (e é o único "sim" do estudo)

Oscilação completa = **queda ≥ X % a partir da máxima corrente**, seguida de **recuperação ≥ X %
dentro de N s**, na janela de 5 min após a entrada. Contagem por posição, 76 posições reais:

| X % | N s | p25 | **mediana** | p75 | ≥ 1 giro | ≥ 2 giros | média |
|---|---|---|---|---|---|---|---|
| 3 | 30 | 1,0 | **3,5** | 9,0 | 78,9 % | 69,7 % | 6,67 |
| 3 | 60 | 1,0 | **3,5** | 9,2 | 81,6 % | 69,7 % | 6,78 |
| 3 | 120 | 1,0 | **4,0** | 9,2 | 81,6 % | 71,1 % | 6,83 |
| 5 | 30 | 0,0 | **2,0** | 5,0 | 71,1 % | 60,5 % | 4,30 |
| 5 | 60 | 0,0 | **3,0** | 5,0 | 73,7 % | 61,8 % | 4,49 |
| 5 | 120 | 0,8 | **3,0** | 5,0 | 75,0 % | 65,8 % | 4,58 |
| 8 | 30 | 0,0 | **1,0** | 3,0 | 60,5 % | 43,4 % | 2,46 |
| 8 | 60 | 0,0 | **1,0** | 3,0 | 65,8 % | 48,7 % | 2,68 |
| 8 | 120 | 0,0 | **2,0** | 3,0 | 68,4 % | 51,3 % | 2,76 |
| 12 | 30 | 0,0 | **0,0** | 2,0 | 47,4 % | 28,9 % | 1,25 |
| 12 | 60 | 0,0 | **1,0** | 2,0 | 53,9 % | 34,2 % | 1,49 |
| 12 | 120 | 0,0 | **1,0** | 2,0 | 59,2 % | 39,5 % | 1,63 |

As 463 apostas de papel dizem o mesmo (mediana 3 a X=3 %, 2 a X=5 %, 1–2 a X=8 %, 1 a X=12 %).

**Maior mediana em qualquer célula: 4,0.** A regra de refutação da fila pedia *mediana < 2 em todas
as células* — **não dispara**. O Everton está certo sobre o gráfico: a moeda sobe e desce mesmo,
várias vezes, dentro dos 5 minutos.

---

## 3. Passos 2–4 — a política de giros contra a regra atual, na mesma moeda

Política simulada: vender a cada repique de X % sobre a marca do último negócio nosso; recomprar a
cada queda de X % sobre o valor do lote no instante da venda; se a queda não vier em N s depois do
**pouso**, ficar de fora até ao fim da janela. Comparador **congelado**: alvo 1,15× / trailing 10 %
armado na entrada / 300 s. Custo **2,23 % por ida e volta** (R65 §3, sem o aluguel da ATA, que agora
é reembolsado), **1,6 s de atraso por perna** (R62 §5, mediana gatilho → pouso 1,64 s), derrapagem
= impacto exato do nosso lote na curva de produto constante, como no R64.

**76 posições reais**, D = PnL líquido por SOL arriscado (giros − regra atual):

| X % | N s | giros | recompras | drenos | **D/SOL** | IC 95 % inf | IC sup | p perm | braço giros |
|---|---|---|---|---|---|---|---|---|---|
| 3 | 30 | 73 | 73 | 8 | **+1,27 %** | −4,97 % | +7,62 % | 0,685 | −0,77 % |
| 3 | 60 | 85 | 85 | 10 | **−1,63 %** | −7,54 % | +4,29 % | 0,599 | −3,67 % |
| 3 | 120 | 103 | 103 | 12 | **−4,24 %** | −10,51 % | +1,88 % | 0,188 | −6,29 % |
| 5 | 30 | 53 | 53 | 5 | **+1,89 %** | −4,40 % | +8,03 % | 0,536 | −0,15 % |
| 5 | 60 | 66 | 66 | 7 | **−1,58 %** | −7,55 % | +4,31 % | 0,596 | −3,62 % |
| 5 | 120 | 77 | 77 | 9 | **−3,48 %** | −9,39 % | +2,41 % | 0,244 | −5,53 % |
| 8 | 30 | 33 | 33 | 5 | **+1,78 %** | −3,39 % | +6,98 % | 0,482 | −0,26 % |
| 8 | 60 | 41 | 41 | 6 | **+0,75 %** | −4,59 % | +6,13 % | 0,780 | −1,30 % |
| 8 | 120 | 56 | 56 | 8 | **−0,51 %** | −6,23 % | +4,97 % | 0,857 | −2,56 % |
| 12 | 30 | 27 | 27 | 3 | **+4,44 %** | −1,27 % | **+10,34 %** | **0,120** | +2,40 % |
| 12 | 60 | 37 | 37 | 4 | **+3,67 %** | −2,04 % | +9,61 % | 0,212 | +1,62 % |
| 12 | 120 | 51 | 51 | 6 | **+1,63 %** | −5,16 % | +8,17 % | 0,612 | −0,41 % |

Regra atual nesta população: **−2,04 % por SOL**. Nas 463 de papel: regra atual **−2,97 %**, D entre
**−1,41 %** e **+2,27 %**, menor p **0,112** (X=12/N=60), **0 de 12** células confirmam.

- **Previsão (D ≥ +0,05 por SOL, IC inferior > 0, p < 0,05): 0 de 12 células, nas duas populações.**
- **Refutação da fila (IC superior < +0,01 por SOL em todas as células): não atingida** — o maior
  limite superior é **+10,34 %**, dez vezes acima. Ignorância, não falsidade.

**Curva em X: monótona crescente com ótimo na borda** (reais, média sobre N: −1,53 %, −1,06 %,
+0,67 %, +3,25 % para X = 3, 5, 8, 12). Não é planalto nem pico — é **tendência descritiva com o
máximo observado na borda da grelha**, o que **não estabelece um ótimo**. A Astra notou que no papel
a monotonia se quebra (X=5 → +0,73 %, X=8 → +0,54 %). Estender a grelha para X = 20 ou 30 % seria
exploração nova, e aproxima a "política" de simplesmente **não girar**.

### Sensibilidade (reais, X = 3 %, N = 120 s — a célula com mais giros)

| custo por ida e volta | atraso por perna | D | IC 95 % |
|---|---|---|---|
| 2,23 % | 1,6 s | −4,24 % | [−10,51 %, +1,88 %] |
| 2,23 % | 5,0 s | −2,80 % | [−11,10 %, +5,67 %] |
| 2,50 % | 1,6 s | −4,59 % | [−10,84 %, +1,49 %] |
| 3,00 % | 1,6 s | −5,22 % | [−11,41 %, +0,81 %] |
| 3,00 % | 5,0 s | −3,79 % | [−11,96 %, +4,55 %] |

Nenhuma variação de custo ou de atraso salva a célula. O atraso maior sai ligeiramente **melhor**, o
que é ruído da amostra, não uma vantagem da lentidão.

---

## 4. Passo 3 — a assimetria que mata o scalping

**11 % a 15 % das recompras acabam em dreno** (o lote recomprado chega a valer ≤ 50 % do que se pagou
por ele antes do fim da janela): 8 de 73 a X=3 %/N=30 s, 12 de 103 a X=3 %/N=120 s nas reais;
71 de 472 (15 %) na célula equivalente do papel. Quanto mais giros a política faz, mais drenos
acumula — é por isso que as células de N = 120 s, que produzem mais giros, têm o **pior** D.

A recompra é a perna que não tem defesa: comprar a queda é, por construção, comprar de quem está a
vender, e numa em cada sete vezes quem está a vender sabe algo que nós não sabemos.

---

## 5. Por que é que um giro que ganha fichas não vira lucro

Este é o coração do estudo. **Cada giro que se completa devolve mesmo mais fichas do que se tinha**:

| X % | ciclos (reais) | multiplicador de tokens por ciclo (mediana) | > 1 em |
|---|---|---|---|
| 3 | 85 | **1,0448** | 91 % dos ciclos |
| 5 | 66 | **1,0529** | 95 % |
| 8 | 41 | **1,0974** | 98 % |
| 12 | 37 | **1,1669** | 100 % |

(papel: 1,035 · 1,063 · 1,094 · 1,154, com 88–99 % acima de 1). **A mecânica do giro funciona.**
E ainda assim D ≈ 0. A decomposição por destino explica porquê (X = 3 %, N = 30 s, 76 reais):

| destino | n | braço giros | D vs regra |
|---|---|---|---|
| **vendeu e não voltou** (a queda não veio em N s) | 47 (62 %) | +8,21 % | **+3,44 %** |
| **girou** (≥ 1 ida e volta completa) | 17 | −3,68 % | +5,62 % |
| **nunca vendeu** (nunca subiu X %, segurou 300 s sem trailing) | 12 | **−31,82 %** | **−13,36 %** |

Os três termos cancelam-se. E lê-se assim:

1. **O que ganha dinheiro na ideia do Everton é a primeira venda** — tirar a ficha no repique. Em
   62 % das posições a política vende no repique e **a queda nunca chega**: fica de fora e ganha
   +3,44 pp sobre a regra. Isso não é giro, é **um alvo mais curto**.
2. **A recompra é neutra na melhor das hipóteses.**
3. **O que perde é ficar dentro sem freio.** Quando a moeda nunca dá o repique de X %, a política
   de giros não tem saída de emergência — não há trailing — e segura até aos 300 s: **−31,8 %**.
   Isto é −13,4 pp pior que a regra atual, e é o buraco por onde o resto escorre.

**Aviso metodológico, explícito:** os três grupos são definidos por **coisas que só se sabem depois
da entrada** ("a moeda subiu X %", "a queda veio"). Condicionar aí não é um filtro utilizável — é a
armadilha que já derrubou o H-005 e o H-006. **O único número válido para decidir é o D
incondicional da §3, e esse é zero com intervalo largo.** A decomposição serve para explicar o
mecanismo, não para escolher um braço.

**Controlo "SEGURAR 300 s sem alvo e sem trailing":** −0,48 % nas reais (D vs regra **+1,56 %**,
IC [−14,58 %, +18,48 %], p = 0,84) e +1,58 % no papel (D **+4,54 %**, IC [−1,17 %, +10,48 %],
p = 0,136). Correção à minha primeira leitura, apontada pela Astra: este controlo tira **alvo e
trailing ao mesmo tempo**, logo **não isola o efeito do trailing**, e um D de +1,56 % com aquele IC
não explica "boa parte" de nada. Fica registado como o que é: **nem segurar nem girar se distingue
da regra atual nesta amostra.**

---

## 6. Passo 5 — a oscilação de equilíbrio, que é o número que o Everton pediu

Por ciclo completo (vender no topo, recomprar no fundo), o multiplicador de fichas é

> **tokens′ / tokens = (1 − c/2)² / (1 − X)**, com equilíbrio em **X = c − c²/4**

- custo **c = 2,23 %** (actual, sem o aluguel da ATA) → **X de equilíbrio = 2,2176 %**
- custo 2,50 % → 2,484 % · custo 3,00 % → 2,978 %

Ou seja: **uma oscilação tem de passar de ~2,2 % só para pagar as taxas da ida e volta.** A grelha
pré-registada começa em X = 3 %, que deixa **0,78 pontos percentuais** de margem por giro — sobre
0,07 SOL, **0,00055 SOL por giro**. É essa a margem que o atraso de 1,6 s, o impacto do nosso lote
na curva e um dreno em cada sete recompras têm de caber.

**E a fita entrega essa amplitude com folga**: giros de ≥ 2,22 % em N = 60 s têm **mediana 5 por
posição** e ≥ 2 em **72 %** das posições reais. **O teto da ideia não é a amplitude. É a margem por
giro e o que se paga por estar dentro entre os giros.**

---

## 7. Veredito

> **H-009 — `NÃO CONFIRMA`.** A oscilação existe (mediana de até 4 giros de 3 % por posição em 5 min,
> a refutação por falta de oscilação **não** dispara), mas a política de giros **não** rende os
> +0,05 por SOL previstos em nenhuma das 12 combinações de (X, N), em nenhuma das duas populações:
> todos os IC atravessam zero e o menor p é 0,12. A refutação da fila (IC superior < +0,01 por SOL
> em todas as células) **também não** foi atingida — o maior limite superior é +0,103. **Não
> sabemos; não está refutada.** A oscilação de equilíbrio é **2,2176 %** ao custo actual de 2,23 %.

**Não proponho braço de papel.** A regra da casa é que só um `CONFIRMA` vira sombra pré-registada.

### O que a reabriria, com população ou medida nova

1. **Fita contínua.** Metade da amostra tem buracos > 30 s. Sem uma fita por WebSocket (e não por
   REST) as células de N = 30 s não são decidíveis. É a condição número um.
2. **A perna que ganha, isolada.** O que apareceu com sinal não foi o giro, foi **vender o primeiro
   repique e não voltar**. Isso é uma hipótese sobre o **alvo**, não sobre giros, e tem de nascer
   como bloco próprio na fila, com previsão e refutação escritas antes — nunca herdando os números
   desta análise, que foram olhados.

---

## 8. Anti-antecipação — o que foi provado, e como

`.claude/state/r72/test_r72.py`, **9 testes, todos a passar**:

- **invariância ao sufixo futuro** (o teste que interessa): trocar tudo o que acontece depois do
  instante *t* não muda nenhuma decisão tomada até *t*;
- **contraexemplo batoteiro**: uma versão do `_fill_index` que pousa no melhor dos 20 pontos
  seguintes **tem de** fazer a guarda levantar `LookAheadError` — sem este teste, o de invariância
  poderia estar a passar por vacuidade;
- **braço `cheat`** (vende no máximo da janela, a olhar o futuro): **+47,96 %** por SOL contra
  −2,04 % da regra atual nas reais. É a distância que a guarda protege;
- valores conhecidos do detector de oscilações em série sintética (1 giro a X=8 %, 0 a X=12 %,
  0 em queda monótona, 0 quando a recuperação chega fora do prazo);
- custo por perna igual ao declarado, e o equilíbrio algébrico X = c − c²/4 = 2,2176 %.

```
$ uv run pytest test_r72.py -p no:cacheprovider -q
.........                                                                [100%]
9 passed in 0.60s
```

---

## 9. Segunda opinião (Astra) — duas rondas

Chamadas: `bash infra/scripts/astra.sh ask r72 "..."` (**antes** de correr o simulador) e
`... ask r72-veredito "..."` (antes de escrever o veredito). Respostas em
`.claude/state/astra-review-r72.md` e `.claude/state/astra-review-r72-veredito.md`.

**Ronda 1 — revisão do simulador, antes de correr. Cinco must-fix, cinco aceites:**

1. **Relógio de execução.** Eu tratava `points[j][0]` (carimbo do último estado conhecido) como hora
   do pouso; o prazo da recompra começava até 1,6 s cedo demais, **prejudicando** a política. Agora
   há `_fill_time` = gatilho + latência, e o prazo N conta do pouso.
2. **Ordem da cadeia × relógio de observação.** Reordenar estados por timestamp fazia o caminho
   voltar a um slot antigo. Contraexemplo dela reproduzido; corrigido com carimbo monótono
   (183 e 1 070 regressões).
3. **Contabilidade do custo.** `per_sol` cobrava a taxa de entrada **duas vezes** —
   `sol_spent_lamports` é `fill.buy_total_lamports` e já a inclui. Corrigido.
4. **Comparador híbrido.** 13 posições carregam 3×/35 % e 2 carregam 1,3×/20 %; eu usava os
   parâmetros de cada uma. Congelado em 1,15× / 10 % / 300 s.
5. **Cobertura.** `resolvable` aceitava "fita algures no caminho"; agora exige ≥ 3 trades **dentro**
   da janela, e a declaração de cobertura da §1 é a dela, quase literal.

**Ronda 2 — revisão do veredito. Dois must-fix, ambos aceites e refeitos:**

6. **Multiplicador por ciclo errado.** Eu dividia pelos tokens da **entrada**, não pelos tokens
   **vendidos naquela volta**. Corrigido — e o sinal mudou: a mediana passa de ~1,02 para 1,045 e a
   fração de ciclos acima de 1 sobe de 69 % para 91 %. A §5 está reescrita com os números certos.
7. **Gatilho terminal.** A saída por tempo disparava no último ponto **antes** dos 300 s; com o
   ponto seguinte aos 301 s, liquidava a 291,6 s e ignorava o estado dos 301 s. Agora o gatilho é
   o instante `entrada + 300 s` e o pouso é `+1,6 s`, com a cauda de fita exportada de propósito.

**Também aceite:** eu tinha lido a coluna *"vs regra"* do `control.txt` como sendo o retorno da
regra — é o **D**. E o controlo "SEGURAR" tira alvo **e** trailing, logo não isola o trailing: a §5
foi reescrita.

**Concordâncias:** o veredito `NÃO CONFIRMA` (sem argumento para `REFUTA`), o D incondicional como
número decisório, a separação entre "não confirmou" e "refutou", a curva como tendência descritiva
com máximo na borda, e a ressalva de cobertura em primeiro lugar.

**Sem desacordos por resolver nesta ronda.**

---

## 10. Arquivos

`.claude/state/r72/`:

| ficheiro | o que é |
|---|---|
| `q1.sql` / `q1.csv` | 89 posições reais fechadas |
| `q2.sql` / `q2.csv` | fita das moedas das reais (19 936 trades) |
| `q3.sql` / `q3.csv` | fotos da curva das reais (2 775) |
| `q4.sql` / `q4.csv` | 545 apostas de papel, uma por mint |
| `q5.sql` / `q5.csv.gz` | fita das moedas de papel (150 777 trades) |
| `q6.sql` / `q6.csv` | fotos das de papel (15 415) |
| `load.py` | reconstrução do caminho da marca, cobertura, elegibilidade |
| `swings.py` | censo de oscilações (máquina de estados de uma passagem) |
| `sim.py` | política de giros, regra atual, braço `cheat`, `Guard` |
| `run.py` → `out.txt` | passos 1–5 e sensibilidade |
| `control.py` → `control.txt` | giros × SEGURAR × regra atual |
| `cycle.py` → `cycle.txt` | multiplicador de fichas por ciclo |
| `abandon.py` → `abandon.txt` | decomposição por destino (vendeu-e-não-voltou / girou / nunca vendeu) |
| `test_r72.py` | 9 testes de anti-antecipação e de valores conhecidos |

Astra: `.claude/state/astra-review-r72.md`, `.claude/state/astra-review-r72-veredito.md`.
KB: `obsidian/11-KNOWLEDGE/KB-0152-a-oscilacao-existe-o-giro-nao-paga.md`.

---

## 11. Proposta de linha de diário (23/09)

> **23/09 R72 — H-009 (giro rápido na oscilação, ideia do Everton): `NÃO CONFIRMA`.** A oscilação
> **existe** — mediana de 3,5 a 4 quedas-e-recuperações de 3 % por posição nos 5 min após a entrada,
> ≥ 2 em 70 % das 76 posições reais com fita — por isso a refutação barata da fila não disparou e o
> estudo teve de ir até ao fim. Mas a política de giros **não** rende os +0,05 por SOL previstos em
> **nenhuma** das 12 células (X ∈ {3,5,8,12} %, N ∈ {30,60,120} s), nem nas 76 reais nem nas 463 de
> papel: todos os IC de cluster por mint atravessam zero, menor p = 0,12, e o custo a 2,5 % ou 3 %
> e o atraso a 5 s não salvam nenhuma. **A oscilação de equilíbrio é 2,2176 %** ao custo actual de
> 2,23 % — a X = 3 % sobram 0,78 pp por giro, 0,00055 SOL sobre 0,07. O mecanismo até funciona (cada
> giro completo devolve 4,5 % mais fichas, e 91 % dos ciclos ficam acima de 1); o que o anula é o
> resto: **11–15 % das recompras caem em moeda que perde ≥ 50 %**, e nas posições que nunca dão o
> repique a política fica dentro sem freio e perde **−31,8 %**. O único pedaço com sinal é **vender
> o primeiro repique e não voltar** (+3,4 pp em 62 % das posições) — que é uma hipótese sobre o
> **alvo**, não sobre giros, e tem de nascer como bloco novo na fila. Astra apanhou 7 defeitos em
> duas rondas (relógio de execução, ordem da cadeia × relógio, taxa de entrada cobrada duas vezes,
> comparador híbrido, cobertura, multiplicador por ciclo, gatilho terminal): todos corrigidos antes
> do veredito. **Ressalva número um: 44 das 76 posições têm buracos de fita > 30 s — ausência de
> oscilação nesses trechos não é prova de ausência.**
