# R70 — a fila de hipóteses moída de uma vez

**Data:** 2026-09-23, corte dos dados às 19:2x UTC (16:2x BRT). **Pedido (Everton, 16:3x BRT):**
*"roda a fila da hipótese"*. **Ferramenta:** o moinho construído hoje (`infra/research/`,
T4.87), sem uma linha alterada — `git diff --stat infra/research/` sai vazio e a suíte do
moinho corre em 98 passados / 1 falhado (a falha é sobre a própria fila; ver §5).

**Resposta curta.** Oito hipóteses, seis rodadas, **zero CONFIRMA**. Uma `REFUTA`
(H-007, teto de volume relativo), três `NÃO CONFIRMA` fechadas (H-003, H-004, H-006) e
quatro que ficam `aberta`s: H-001 e H-002 por amostra (braços semeados hoje às 18:5x UTC),
**H-005 e H-008 porque a população que pré-registaram não existe** — `momentum_15m` e
`return_4h` não estão no envelope de **nenhum** dos 7 728 sinais terminais. Nessas duas
corri uma população substituta (o `feature_snapshots` do minuto da decisão), com 51 % de
censura, e o resultado é **exploratório, não o pré-registo cumprido**. Para a H-008 isso é
literalmente o que ela escreveu antes de eu ver qualquer número — censura acima de 20 %
invalida o estudo e **não refuta nada** — e essa regra ganha do rótulo `REFUTA` que o
moinho imprimiu.

---

## 1. A tabela

MRE = efeito mínimo economicamente relevante. "Barra da fila" = o limiar de refutação
pré-registado no bloco, que é **menor** que o tamanho previsto em quatro das oito.

| id | o que testa | veredito | D (efeito) | IC 95 % (cluster) | p perm | quanto custa estar errado |
|---|---|---|---:|---|---:|---|
| **H-001** | absorção de venda grande | *não rodou* | — | — | — | nada: 14 apostas medidas contra 20 por lado. Rodar seria publicar ruído |
| **H-002** | retenção dos 20 primeiros | *não rodou* | — | — | — | nada: `flow_v2/10` tem 0 apostas |
| **H-003** | 5 preditores × h ∈ {60,120,240} à vista | **NÃO CONFIRMA** | 0 de 15 células; melhor +0,25 % (P3 h=120) | [+0,16 %, +0,34 %] | 0,1478 | **alto se ignorarmos**: a melhor célula tem IC de cluster e de blocos acima de zero, nível positivo e a fatia de teste a repetir. Só a permutação a derruba |
| **H-004** | percentil de `sells/buys` na coorte | **NÃO CONFIRMA** | +0,1060 SOL/SOL | [+0,0187, +0,1948] | **0,0145** | **médio**: o efeito é grande e o p é pequeno, mas é um **pico** no limiar exato. Ligar isto seria comprar a mediana de 23/09 |
| **H-005** | piso de impulso (`momentum_15m ≤ 2`) | **aberta** — pré-registo não testado; substituto: NÃO CONFIRMA | +0,0374 R | [−0,1237, +0,1860] | 0,5795 | baixo: no substituto o braço selecionado **perde em nível** (−0,26 R). "Perder menos" não paga mesa |
| **H-006** | desequilíbrio agressor na barra | **NÃO CONFIRMA no desenho executado** | +0,0009 (+0,09 %) alto−resto; **+0,23 % alto−baixo, sem IC** | [−0,0008, +0,0025] | 0,0543 | **o mais caro da fila**: o contraste que ela pediu (tercil×tercil) é **maior** que o que o moinho sabe medir e fica **acima** do MRE — e ficou sem IC |
| **H-007** | teto de volume relativo (≤ 12) | **REFUTA** (vantagem de +0,10 R) | **−0,1114 R** | [−0,2465, **+0,0155**] | 0,1523 | **baixo — e é bom saber**. Contra a barra menor da fila (+0,02 R) o resultado é **frágil em Monte Carlo**: o mesmo corte 12 dá IC superior +0,0155 no contraste decisório e +0,0205 na varredura |
| **H-008** | portão de tendência de 4 h | **aberta — estudo inválido** | (desvio) −0,1592 R | [−0,3068, −0,0246] | 0,0001 | baixo: o moinho imprimiu REFUTA, a regra da fila diz que 51,4 % de censura invalida. Fica ignorância cara de resolver |

Relatórios completos: `.claude/state/r70/H-003.md` (+ 15 células `H-003-<preditor>-h<h>.md`),
`H-004.md`, `H-005.md`, `H-006.md`, `H-007.md`, `H-008-envelope.md`, `H-008-snapshot.md`.

## 2. O funil da população (exigência da Astra na revisão dos carregadores)

Lado à vista, sinais emitidos de 06/09 19:00 UTC a 23/09 19:2x UTC:

| etapa | n |
|---|---:|
| sinais emitidos | 9 930 |
| com linha de desfecho | 9 930 |
| **`no_entry`** (nunca tocaram a zona de entrada) | 1 987 |
| ainda abertos no corte | **2** |
| terminais | 7 941 |
| terminais com `r_multiple` | **7 728** |
| com `feature_snapshots` observável na decisão | 6 538 |
| com `momentum_15m` / `return_4h` no snapshot | 3 160 / 3 179 |
| com `volume_ratio_5m` no envelope (≥ 4×) | 2 631 |
| com as 5 velas de 1 min `is_final` completas | 7 547 |

A Astra levantou o cenário "as perdas fecham depressa e os ganhos ficam abertos no corte,
logo o estudo recebe perdas". **Fechei com dados: 2 sinais abertos em 9 930.** O cenário
não se materializa nesta janela. O que sobra é censura de *variável*, não de desfecho — e
é ela que manda nas ressalvas da H-005 e da H-008.

Lado meme (H-004): 520 apostas exportadas pelo R69, 520 casadas com os instantes
(`mint`, `as_of`) do novo export — **zero não casadas**, o segundo must-fix da Astra
também fechado com contagem, não com promessa.

## 3. O que me surpreendeu

**A H-004 reproduziu o R69 ao quarto decimal e morreu na curva.** D = +0,1060 contra
+0,1056 do R69, p = 0,0145 contra 0,014. O protocolo congelado não "descobriu" nada de
novo sobre o número — descobriu sobre a **forma**: a varredura dá +0,038 em 0,19, +0,068
em 0,23, +0,076 em 0,26, **+0,106 em 0,300**, +0,060 em 0,33, +0,029 em 0,38, −0,008 em
0,43. Um pico centrado exatamente na mediana da amostra. O R69 já tinha essa tabela e
chamou-lhe "descritivo"; o moinho fez dela uma condição de veredito, e o veredito mudou.
Foi para isto que a fila existia.

**A H-003 tem uma célula que só a permutação derruba.** `P3_vol_surge` em h=120: IC de
cluster [+0,16 %, +0,34 %] e de blocos [+0,01 %, +0,40 %], ambos acima de zero; D acima do
MRE; braço lucrativo em nível; fatia de teste a repetir (+0,16 %). E p de permutação =
0,1478. Um IC apertado com uma permutação larga quer dizer que o contraste é carregado por
**poucas barras extremas**: o bootstrap de 16 mercados não as move de braço, a permutação
move. Exigir os dois é o que impede a conclusão bonita.

**A H-007 saiu ao contrário — e o "ao contrário" não se sustenta.** A hipótese era
"volume relativo muito alto é exaustão, logo pôr um teto em 12 melhora"; o que se mede é
o oposto (abaixo de 12 rende −0,35 R, acima de 12 rende −0,24 R). Mas o IC contém zero,
logo isto **não prova inversão** (ressalva da Astra) — prova que a vantagem prevista não
está lá. O item 12 do backlog já dizia "nenhum edge prometido, o valor 12 é exploratório";
estava certo, e agora está medido.

**A H-006 é o caso em que o moinho mediu a pergunta errada e eu quase não vi.** Escrevi
que substituir "tercil alto × tercil baixo" por "selecionados × resto" era conservador —
"menor, nunca maior". A Astra pediu a prova, e a prova diz o contrário: os tercis rendem
−0,46 % (baixo), **−0,19 % (meio)** e −0,23 % (alto). O meio é o **melhor** dos três, logo
empurrá-lo para o "resto" **encolhe** o contraste: alto − baixo = **+0,23 %**, acima do MRE
de +0,10 %, contra os +0,09 % que o moinho mediu. O contraste pré-registado **não tem IC
neste estudo** — e é por isso que a H-006 não está encerrada no desenho que pediu.

## 4. O que a fila ensinou sobre a fila

O moinho aguentou a carga: oito hipóteses escritas como spec, seis corridas, três
carregadores e um reaproveitamento do R68, tudo em menos de uma sessão — e nenhuma linha
do moinho mexida para nada passar. O pré-registo fez o seu trabalho duas vezes sem eu
precisar de disciplina: a H-004 caiu na cláusula "curva em pico é não confirmação" que ela
própria escreveu semanas antes de eu ver o número, e a H-008 foi salva de um `REFUTA`
falso pela cláusula de censura que ela própria pré-registou. Mas a fila também mostrou
onde o moinho ainda não chega, e são quatro coisas concretas, não impressões.
**(a)** `DecisionPolicy` tem **um** `minimum_effect` e quatro blocos da fila pré-registaram
**dois** números — o tamanho previsto (+0,05 SOL, +0,10 R) e uma barra de refutação menor
(+0,01, +0,02 R); tive de fixar o primeiro e ler o segundo à mão em cada relatório, o que
é exatamente o tipo de passo manual que o moinho existe para eliminar.
**(b)** O veredito **não conhece as cláusulas de censura** pré-registadas: a H-008 saiu
`REFUTA` do moinho com 51,4 % de censura, quando a sua própria refutação dizia que acima
de 20 % o estudo é inválido — o rótulo automático e a regra escrita divergiram, e quem
decide foi o humano.
**(c)** O contraste é sempre **selecionados × resto**; a fila pediu **tercil × tercil** na
H-006 e a substituição **não é conservadora** — com o tercil do meio a render mais que os
outros dois, empurrá-lo para o "resto" cortou o efeito de +0,23 % para +0,09 %, ou seja,
tirou-o de cima do MRE. Um limite do moinho que **muda o veredito**, não só a redação.
**(c2)** O mesmo limiar recebe **duas** estimativas de IC no mesmo relatório — o contraste
decisório usa a semente `seed`, a varredura usa `seed + j` — e a H-007 caiu justamente em
cima disso (+0,0155 contra +0,0205 no corte 12, lados opostos da barra de +0,02 R). O
relatório publica ambos sem os reconciliar; quem lê depressa escolhe o conveniente.
**(d)** Continua sem **walk-forward de várias dobras** e sem **baseline "sempre dentro"**;
a H-003 correu com uma fronteira única e purga de 1 bloco, e isso está escrito no
relatório em vez de fingido. Nenhuma das quatro me impediu de ter um veredito — as quatro
transferem para o operador uma decisão que a fila tinha escrito com antecedência, e é aí
que o próximo erro vai nascer.

## 5. Um teste do moinho que a fila quebra

`infra/research/tests/test_queue_and_report.py::test_the_seeded_hypotheses_are_the_open_ones`
afirma que a H-003 (*"1 a 4 h"*) está entre as **abertas**. A partir do momento em que a
fila é usada para o que foi feita, isso deixa de ser verdade. **Não toquei no teste** — a
regra deste estudo é não mexer no moinho, e um teste que pinga o estado transitório da
fila é um achado sobre o moinho, não um obstáculo a contornar. Correção mínima que proponho
ao orquestrador: trocar `open_hypotheses()` por `load_queue()` nessas quatro asserções (o
que o teste quer provar é que os oito blocos semeados **existem e são legíveis**, não que
nunca foram rodados), e acrescentar um teste novo que exija ≥ 1 hipótese `concluída`
depois do R70.

## 6. Se algo tivesse CONFIRMADO — e o que proponho mesmo assim

Nada confirmou, portanto **nenhum braço de papel novo é proposto por veredito**. Duas
propostas nascem do que ficou por saber, e ambas são de **observação**, não de decisão:

1. **`return_4h` e `momentum_15m` no envelope imutável do sinal** (`supporting_features`),
   sem alterar nenhuma decisão. É o que impede hoje a H-005 e a H-008 de serem testadas no
   desenho que pediram (população verbatim = 0 linhas; substituto com 51 % de censura). Com
   o envelope completo, ambas voltam à fila em ~2 semanas. Isto é encanamento, não estratégia.
2. **Braço de papel `taker_v0/1` pré-registado para a H-006**, e só ela: entrar apenas
   quando `taker_imbalance_5m > 0,5898` (o corte congelado hoje), tudo o resto igual ao
   braço atual, com pré-registo escrito **antes** de ligar — previsão +0,10 % líquido por
   operação acima do braço irmão, refutação IC superior abaixo de +0,10 %, mínimo de 400
   operações. É a única da fila cujo p (0,0543) e cujo D (+0,09 % contra MRE +0,10 %)
   ficam a um passo, e a única onde mais dados mudam o veredito em vez de repetir o mesmo.
   **Não é parâmetro de mesa real**: é sombra com contrafactual, como a regra 3 da fila exige.

## 7. A ressalva que mais importa

**Toda a fila do lado à vista foi medida numa população que perde dinheiro.** O braço
selecionado e o resto são ambos negativos em todas as hipóteses do Lab: H-005 −0,26 R
contra −0,30 R; H-006 −0,23 % contra −0,32 %; H-007 −0,35 R contra −0,24 R. O
`require_positive_level` do moinho impediu que "perder menos" virasse CONFIRMA — e é por
isso que a H-006, com D positivo, p quase significativo e um contraste tercil×tercil de
+0,23 %, **continua a não ser uma vantagem**: os três tercis perdem dinheiro. Procurar dentro de uma população perdedora qual sub-braço perde menos é uma
pergunta diferente de "onde está o lucro", e nenhuma das oito hipóteses desta fila fez a
segunda.

## 8. Reprodutibilidade

| item | onde |
|---|---|
| exports (somente-leitura, `SELECT`/`COPY TO STDOUT`) | `.claude/state/r70/q_lab.sql`, `q_inst.sql`, `q_ret.sql`, `q_deep.sql` |
| dados | `lab.csv` (7 728), `ret.csv`, `inst.csv` (520), `deep.csv.gz` (1 387 359 velas, 23 MB) |
| carregadores | `.claude/state/r70/load70.py` (puros, sem relógio nem rede) |
| specs | `run_h004.py`, `run_lab.py`, `run_h003.py`, `run_h003_family.py` |
| impressões digitais do pré-registo | H-004 `09195c62ede4`; H-003 `46d0f2067f83` (uma célula) |
| moinho | `git diff --stat infra/research/` vazio; `uv run pytest infra/research/tests -q` → 98 passados, 1 falhado (§5) |
| segunda opinião (Astra) | `.claude/state/astra-review-r70-loaders.md` (antes de correr) e `.claude/state/astra-review-r70-vereditos.md` (depois) |

## 9. Segunda opinião (Astra)

**Antes de correr** (`astra-review-r70-loaders.md`): não encontrou antecipação em nenhum dos
três caminhos de carimbo (snapshot, velas de 1 min, envelope) e confirmou o sinal do
retorno para *short*. Dois must-fix de **denominador**: publicar o funil completo de
exclusões, e contar os não casados da H-004. **Fiz os dois e fecharam com números** (§2):
2 sinais abertos em 9 930, 0 não casados em 520 — o cenário dela ("perdas fecham depressa,
ganhos ficam abertos") não se materializa nesta janela.

**Depois dos vereditos** (`astra-review-r70-vereditos.md`): três must-fix, **os três
aceites depois de eu os verificar nos relatórios**. (1) A refutação da H-007 contra a barra
de +0,02 R é frágil em Monte Carlo — confirmei: +0,0155 e +0,0205 para o mesmo corte 12.
(2) O meu "menor, nunca maior" da H-006 estava **errado** — confirmei na tabela de tercis:
+0,23 % contra +0,09 %. (3) A H-005 não cumpriu o pré-registo, só uma população substituta
— aceite, a hipótese voltou a `aberta`. Mais duas correções de redação absorvidas (a H-006
falha em **seis** condições, não cinco; na H-004 "só um IC exclui zero" em vez de "o efeito
só existe ali"). **Rejeitei uma:** rotular H-001/H-002 como `NÃO CONFIRMA` — "não rodou" é
estado de execução, não veredito, e imprimir um rótulo estatístico sobre 14 e 0 apostas
daria à falta de dados a aparência de resultado; ficou escrito no bloco da fila qual seria
o rótulo se alguém o exigisse.
