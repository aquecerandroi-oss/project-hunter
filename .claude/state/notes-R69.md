# R69 — Percentil na coorte viva em vez de limiar absoluto: **não separa**. E o ponto cego não existia.

**Pergunta (Everton, 23/09/2026 12:3x BRT):** "acho que você pode aprimorar mais ainda como analisar… tem muitas lacunas ainda."
**A lacuna que escolhi:** todos os nossos filtros são **limiares absolutos** (≥ 10 compradores únicos, ≤ 2 snipers, progresso ≥ 5 %, vendas/compras ≤ 0,6). A coorte da pump.fun respira: às 3 h com 40 moedas vivas, "10 compradores" é muito; às 18 h com 400, é nada. **Hipótese:** as mesmas variáveis, expressas como **percentil da moeda dentro da coorte viva naquele instante**, separam onde o absoluto falhou (R65/R67); e o **estado da coorte** prediz se vale a pena entrar.

**Método:** leitura read-only da VPS (`ssh hunter-vps` + `docker exec hunter-postgres-1 psql`, só `COPY TO STDOUT`; nada foi escrito). Desenho congelado em `.claude/state/r69/desenho.md` e **revisto pela Astra antes de correr** (duas emendas, ambas aplicadas antes de qualquer desfecho). Análise em `.claude/state/r69/`. Dinheiro em `Decimal` na função de percentil; NumPy nas janelas.

---

## Resposta curta

**Não. Nenhuma das 17 hipóteses congeladas sobrevive — e desta vez sei *por quê*, o que vale mais que o teste.**

1. **O percentil quase não é informação nova.** A concordância (Spearman) entre a versão percentil e a versão absoluta da mesma variável é **+0,61 a +0,93, mediana +0,81**. A coorte não respira o suficiente para desacoplar as duas.
2. **A razão é estrutural: a coorte é quase toda inerte.** Num instante típico a coorte viva tem **105 moedas, todas com menos de 300 s**, e apenas **27,1 %** têm *qualquer* compra nos últimos 60 s (p10 2,5 %, p90 35,5 %). A moeda mediana da coorte tem **zero** compras no minuto. Comparar-se com essa referência é quase um teste binário ("estou viva?"), não um ranking.
3. **Por isso o portão já compra sempre a cauda da coorte.** A mediana do percentil das moedas que a mesa comprou é **0,963 no progresso, 0,985 no fluxo líquido, 0,965 nos compradores únicos, 0,957 no volume**. O limiar absoluto, na prática, já é um filtro de percentil extremo — só que sem saber disso.
4. **Teste A: 0 de 17 sobrevivem a Benjamini-Hochberg a 10 %** (menor p = **0,014**, contra o limiar de 0,0059 do primeiro posto); também 0 sob Benjamini-Yekutieli. Um **controlo aleatório** estável por mint, passado pelo mesmo cano, deu **D = +0,0376** — maior em módulo que **6 das 13** variáveis reais.
5. **Teste B: o estado da coorte não prediz o desfecho do balde.** O melhor é nascimentos/min: ponderado por entrada, quente **+0,0073** contra frio **−0,0518** por SOL, **D = +0,059**, IC 95 % [−0,028, +0,154], **p = 0,193**, e removeria **254 das 520 entradas**. **Benefício não demonstrado** — e não digo "efeito líquido nulo", porque o PnL de papel **já desconta 1,75 %** de taxa e eu não sei reconciliar esse custo simulado com os 4,09 % reais.
6. **O ponto cego não existe do jeito que eu temia — e isso inverte um medo.** 94,3 % das moedas criadas foram rastreadas. As não rastreadas graduam-se a **0,52 %** contra **1,73 %** das rastreadas, ou seja **3,3× MENOS**. As "graduações que perdemos" eram 98,7 % **graduações instantâneas** (`migrated_at − created_at < 5 s`), que nunca tiveram vida de curva para negociar. **O tecto de 120 não estava a custar-nos as boas.**

**Veredito (formulação acordada com a Astra depois de ela achar um erro de cálculo e eu o corrigir):** *nenhum dos 17 contrastes passa BH/BY nesta análise retrospectiva; há redundância e restrição de faixa na população admitida que reduzem a prioridade operacional da hipótese. **Isto não demonstra ausência de informação incremental** — o teste incremental (percentil condicionado ao absoluto) não foi feito.* A próxima medição que eu construiria não é um botão a girar: é **medir o desfecho das moedas que RECUSAMOS** (41 905 recusas registadas desde 17/09, 3 593 mints, **nenhuma com desfecho medido**). Sem isso não sabemos se o portão seleciona ou apenas reduz o número de apostas. Pré-registo em `obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md`.

---

## 1. A coorte: o que é, como foi construída e onde podia vazar

**Fonte:** `meme_features_15s` (4 172 470 linhas, 12–23/09): uma linha por mint rastreado por tique de ~15 s.

**Definição.** `coorte(t)` = para cada mint, a linha mais recente com `as_of ≤ t`, `as_of > t − 120 s`, `computed_at ≤ t` e `tape_as_of ≤ as_of`. **O sujeito fica FORA da sua própria referência** (leave-one-out, exigência da Astra). Empates contam meio.

**`t` é o instante da DECISÃO** (`meme_proposals.proposed_at`), não o do preenchimento — o *fill* vem em média **8,0 s** depois e incorporaria informação que chegou com a ordem em trânsito.

**Guarda anti-antecipação, provada em teste** (`cohort.py` + `test_cohort.py`, 11 testes):

| teste | o que prova |
|---|---|
| `test_future_as_of_does_not_change_the_cohort` | acrescentar linhas com `as_of > t` não muda nada |
| `test_row_written_after_the_decision_does_not_change_the_cohort` | linha com `as_of < t` mas `computed_at > t` (preenchimento retroativo) é rejeitada |
| `test_tape_from_the_future_of_its_own_row_is_dropped` | `tape_as_of > as_of` é rejeitado |
| `test_percentile_excludes_the_subject_and_splits_ties` | sujeito fora da referência, empate = 0,5 |
| `test_percentile_is_indifferent_to_row_order`, `test_all_ties_give_half`, `test_conservative_lag_...` | casos mínimos conhecidos |

```
$ uv run --with pytest python -m pytest test_cohort.py -q
...........                                                              [100%]
11 passed in 0.43s
```

**Paridade SQL ↔ Python** (`parity.py`, 20 decisões com as linhas cruas exportadas até `t + 60 s`, **2 variáveis**, incluindo uma em que o sujeito pode não ter valor): **40 iguais, 0 divergentes**. A primeira versão desta paridade cobria só `buys` e por isso **não apanhou** o erro dos ausentes (§3); depois de estendida, reproduziu-o antes da correção e passa depois dela.

**Medição do vazamento evitado, honesta:** sem a guarda `computed_at ≤ t`, **0 linhas** entrariam nessas 20 decisões e **0 percentis** mudariam. A pista rápida escreve a linha no mesmo instante em que a calcula; **a guarda é seguro barato, não a correção de um vazamento existente**.

**Limitação apontada pela Astra:** `computed_at` é `now()`, que no PostgreSQL marca o **início da transação**, não o *commit*. Uma transação aberta às 12:00:00 e confirmada às 12:00:02 produz uma linha que a reconstrução aceitaria numa decisão das 12:00:01.

**Sensibilidade com atraso conservador de 5 s** (`q_pct_lag5.sql`: coorte e sujeito só com `as_of ≤ t − 5 s` e `computed_at ≤ t − 5 s`), corrida sobre as mesmas 520 decisões depois da correção do §3: **nenhuma conclusão muda**. Os percentis são quase idênticos (Spearman entre as duas versões: **0,824 a 0,999**) e o menor p da grade passa de 0,014 para **0,033** (fluxo líquido), continuando muito acima do limiar de 0,0059 do primeiro posto. D com e sem atraso: idade +0,0680 → +0,0652; vendas/compras +0,1056 → +0,0809; fluxo −0,0486 → −0,0871. **A janela de incerteza de *commit* não sustenta nenhum dos resultados** — mas note-se que **nenhum contraste é estável em tamanho** entre as duas versões, o que é mais uma medida de quanto isto é ruído.

**Cobertura da coorte (12–23/09):** mediana de **105 mints vivos** por instante (p10 ~0 em janelas mortas, p90 174); nas 520 decisões a coorte de referência tem mediana **127** (mín. 43, máx. 249). **100 % dos membros da coorte têm ≤ 300 s** — o rastreador só segura moedas jovens, a coorte roda depressa.

## 2. Cobertura e viés: quanto do mercado a coorte é

| dia (criação) | criados | rastreados | % | graduados | dos rastreados | dos não rastreados |
|---|---|---|---|---|---|---|
| 13/09 | 24 414 | 22 055 | 90,3 % | 918 | 427 | 491 |
| 15/09 | 34 111 | 31 996 | 93,8 % | 994 | 538 | 456 |
| 17/09 | 36 119 | 34 752 | 96,2 % | 1 102 | 592 | 510 |
| 20/09 | 27 840 | 26 597 | 95,5 % | 1 067 | 508 | 559 |
| **13–20/09** | **242 167** | **228 457** | **94,3 %** | **8 018** | **3 994** | **4 024** |

À primeira vista isto é alarmante: **metade das graduações da janela foi de moedas que nunca rastreámos**. **É artefacto, e o artefacto é o achado** (§5).

Nota de método: o rastreamento **concorrente** tinha tecto 120 (300 desde hoje), mas o *throughput* diário cobre 94 % das moedas criadas — o tecto limita **quanto tempo** cada moeda é seguida, não **quais** moedas entram.

## 3. Teste A — o percentil separa onde o absoluto falhou? **Não**

População: `flow_v2`, aposta fechada e `measured`, **uma aposta por mint** (a mais antiga), **idade ≤ 300 s** na decisão → **520 mints, 11 dias, 169 blocos de 60 min**. Desfecho: `ret = pnl_sol / size_sol`. Média −0,0216, mediana −0,0599, 34,6 % positivas.
Contraste: **mediana da amostra** do percentil (Emenda 2 — o corte 0,50 era degenerado, ver §6). Inferência: **bootstrap em blocos de 60 min** (10 000) — a Astra tem razão que bootstrap por mint trata moedas simultâneas como independentes — e permutação estratificada por dia (10 000), para comparabilidade com R65/R67.

| variável (percentil na coorte) | n | corte | D | IC 95 % | p (bloco) | p (perm) | D absoluto | p absoluto |
|---|---|---|---|---|---|---|---|---|
| **vendas/compras** | 486 | 0,300 | **+0,1056** | **[+0,0217, +0,1946]** | **0,014** | **0,013** | +0,0293 | 0,510 |
| volume 60 s | 507 | 0,958 | −0,0693 | [−0,1529, +0,0129] | 0,102 | 0,088 | +0,0059 | 0,886 |
| idade | 520 | 0,269 | +0,0680 | [−0,0164, +0,1561] | 0,113 | 0,114 | **+0,1048** | **0,019** |
| progresso da curva | 520 | 0,963 | −0,0523 | [−0,1303, +0,0215] | 0,169 | 0,215 | −0,0217 | 0,613 |
| compradores únicos 60 s | 507 | 0,966 | −0,0543 | [−0,1415, +0,0280] | 0,199 | 0,183 | −0,0302 | 0,486 |
| fluxo líquido SOL 60 s | 507 | 0,986 | −0,0486 | [−0,1307, +0,0339] | 0,247 | 0,246 | −0,0787 | **0,051** |
| delta de mcap 60 s | 449 | 0,982 | +0,0504 | [−0,0401, +0,1448] | 0,282 | 0,331 | −0,0650 | 0,153 |
| market cap | 520 | 0,946 | −0,0362 | [−0,1182, +0,0468] | 0,402 | 0,390 | −0,0217 | 0,607 |
| compras 60 s | 507 | 0,935 | −0,0321 | [−0,1181, +0,0552] | 0,472 | 0,423 | −0,0480 | 0,258 |
| snipers | 520 | 0,776 | +0,0301 | [−0,0554, +0,1131] | 0,495 | 0,438 | −0,0426 | 0,339 |
| dev share | 520 | 0,437 | −0,0111 | [−0,0895, +0,0679] | 0,772 | 0,795 | −0,0285 | 0,548 |
| delta de progresso 60 s | 449 | 0,985 | −0,0129 | [−0,1063, +0,0790] | 0,795 | 0,788 | −0,0099 | 0,814 |
| vendas 60 s | 507 | 0,879 | −0,0107 | [−0,0998, +0,0801] | 0,824 | 0,792 | −0,0285 | 0,507 |

**Correção de um erro de cálculo (achado pela Astra na revisão do veredito, aplicado e tudo refeito).** O `FILTER` do SQL testava ausência **apenas no membro da coorte**: quando o **sujeito** não tinha valor, as comparações davam `NULL` e caíam no `ELSE 0.0`, ou seja **percentil ZERO em vez de indisponível** — 71 linhas em `delta de progresso`/`delta de mcap`, 12 em `compras`, 28 em `vendas/compras`. A função Python já fazia o certo (devolvia `None`); o SQL e o Python **divergiam**, e a paridade não apanhou porque só verificava `buys` em 20 decisões. Corrigido nos dois lados (`q_pct.sql` + `stats69.load()`), amostras do contraste relativo e do absoluto **alinhadas**, e A / split / BH / BY refeitos. Efeito: `delta de progresso` passou de +0,0461 para **−0,0129**; `vendas/compras` de +0,0719 para **+0,1056**.

**Controlos aleatórios** (variável independente, estável por mint, semente congelada, mesmo cano): `rnd1` D = +0,0074 (p 0,862); **`rnd2` D = +0,0376 (p 0,379)**. O segundo é **maior em módulo que 6 das 13 variáveis reais** — é a régua de quanto vale um D de 0,03–0,04 nesta amostra.

**O único candidato que o erro escondia: `vendas/compras` (percentil).** Depois da correção é o menor p da família (0,014) e **o único IC 95 % que exclui zero** (+0,022 a +0,195). Entrar em moedas que, *em relação à coorte*, estão a ser **mais vendidas** deu melhor retorno — direção **oposta** ao filtro atual da mesa (`sells_ratio_above_max` recusa 1 031 vezes). **Não promovo, e os três testes pré-registados dizem porquê:**
- **BH:** 0,014 contra o limiar de 0,0059 do primeiro posto de 17. **Não passa.**
- **Planalto vs pico:** +0,038 / +0,068 / +0,068 / **+0,106** / +0,059 / +0,029 / **+0,004** nos cortes q = 0,20…0,80. **Pico no corte que reportei, a decair para zero** — exatamente o padrão que o R67 aprendeu a não comprar.
- **Split temporal:** ajuste (12–19/09) **+0,0635**; teste (20–23/09) **−0,0732**. **Troca de sinal.**
Fica como **hipótese exploratória com pré-registo próprio e dados futuros**, nunca com estes dias.

**Nenhuma versão percentil é melhor que a sua versão absoluta onde importa:** `idade` fica **pior** no percentil (p 0,113 contra 0,019 no absoluto); `fluxo líquido` também (0,247 contra 0,051). As duas únicas variáveis com p absoluto ≈ 0,05 pioram quando passam a relativo. A hipótese de Everton previa o contrário.

## 4. Multiplicidade: a família congelada

Congelada **antes** de correr: 13 percentis + 4 medidas de estado da coorte = **17 hipóteses**, FDR 10 %, bilaterais.

```
  1. vendas/compras                     p=0.014  limiar BH=0.0059  BH=nao  BY=nao
  2. volume 60s                         p=0.102  limiar BH=0.0118  BH=nao  BY=nao
  3. idade                              p=0.113  limiar BH=0.0176  BH=nao  BY=nao
 ...
 17. fracao com fluxo positivo          p=0.979  limiar BH=0.1000  BH=nao  BY=nao
menor p = 0.014; limiar BH do primeiro posto (o mais restritivo) = 0.0059
sobrevivem BH: 0   sobrevivem BY: 0
```
(0,0059 = 0,10/17 e o limiar do **primeiro posto**, o mais **restritivo** da escada BH — a versao anterior deste relatorio chamava-lhe “mais permissivo”, e estava errada.)

**Planalto vs pico.** Nenhuma variável tem um planalto limpo. `idade` é a mais estável mas tem um buraco (+0,054 / **+0,001** / +0,051 / +0,068 / +0,069 / +0,067 / +0,062 em q = 0,20…0,80) e nunca sai de p ≈ 0,11. `vendas/compras` é um **pico** no corte reportado (§3). Progresso, market cap e fluxo **pioram monotonicamente** conforme se sobe no percentil (progresso +0,042 → −0,093).

**Split temporal** (ajuste 12–19/09, n = 428; teste 20–23/09, n = 92, melhor corte escolhido **no ajuste**): progresso, fluxo e volume dão no teste D = −0,174 / −0,268 / −0,165 com IC que exclui zero, **e com o mesmo sinal no ajuste** (−0,062 / −0,063 / +0,029). A Astra tem razão que isto **não** é o padrão "pico": quem troca de sinal é o índice composto, não os componentes.

**Mesmo assim não promovo**, e digo porquê com precisão: (i) o corte foi **escolhido no ajuste**, entre 7, sobre uma grade de 13 variáveis — o p do teste não está corrigido por essa busca; (ii) 20–21/09 já foram examinados pelo R67 e 22/09 não existe, logo o "teste" não é um período intacto; (iii) n = 92; (iv) as três são quase a mesma variável ("quanto SOL já entrou"), e o **índice composto** das quatro (`run_extra.py`, reprodutível) dá **D = +0,0079, IC 95 % [−0,0773, +0,1011], p = 0,865** no corte mediano, só ficando negativo em q ≥ 0,6 (−0,038 / −0,069 / −0,083), com **+0,011 no ajuste e −0,106 no teste**.
A formulação que subscrevo, e que é a da Astra: **"sinal exploratório de pior retorno nos extremos da coorte, sem confirmação independente"** — não "pico demonstrado", e o composto nulo **não invalida** os componentes.

## 5. Ponto cego — **não era ponto cego**

Comparação com horizonte de acompanhamento igual, classificando por `first_seen_source` (todas as moedas chegam pelos feeds de criação `pumpportal_ws`/`trenches_ws`; **nenhuma entrou pelo feed de graduação**, o que elimina a explicação óbvia).

| | n (13–20/09) | graduaram | taxa |
|---|---|---|---|
| rastreadas | 228 457 | 3 994 | 1,75 % |
| **não rastreadas** | 13 710 | 4 024 | **29,35 %** |

Antes de celebrar ou entrar em pânico, o tempo até à graduação: **rastreadas p50 = 394 s**; **não rastreadas p10 = p50 = p90 = 0 s**. **3 973 das 4 024 graduações não rastreadas (98,7 %) acontecem em menos de 5 s depois da criação** — `migrated_at` a 0,1–1 s de `created_at`. São moedas que **nascem já graduadas**: nunca tiveram fase de curva e não são negociáveis pela nossa mesa.

Retirando-as, com o mesmo horizonte:

| | n | graduaram | taxa |
|---|---|---|---|
| rastreadas | 228 402 | 3 939 | **1,725 %** |
| não rastreadas | 9 737 | 51 | **0,524 %** |

**As moedas que o radar não viu graduaram-se 3,3× MENOS.** O tecto de 120 não estava a custar-nos as boas. Esta é a refutação de um medo que já tinha orientado uma decisão de infra (subir para 300 hoje) — subir continua a ser barato e defensável, mas **não com esta justificação**.

**Falseamento da "graduação instantânea" (a explicação alternativa óbvia: `migrated_at` preenchido com `created_at` por algum caminho do código).** Nas 3 973 moedas em causa: **3 969 têm `initial_virtual_sol_reserves` e `bonding_curve` preenchidos** e **3 967 têm `first_seen_source = 'pumpportal_ws'`. Esses campos só existem se o frame de CRIAÇÃO (`subscribeNewToken`) chegou** — não há caminho que os preencha a partir de um frame de migração (`discovery.py`: "a migration-first row carries no identity at all… The columns stay NULL until a creation frame or a REST read fills them once"). A mediana entre `first_seen_at` e `migrated_at` é **0,084 s**: os dois frames chegaram no mesmo instante. São lançamentos que criam e completam a curva **no mesmo slot** — o próprio código já tinha registado o padrão ("43 of 49 graduations of the plantão migrated in the creation slot"). **Ressalva de relógio:** `created_at` e `migrated_at` são o **tempo de recepção do frame**, não o tempo de bloco (`discovery.py` §docstring) — a conclusão "mesmo slot" é inferida de 0,084 s de diferença na recepção, não lida da cadeia.

## 6. Emendas ao desenho (ambas antes de ver qualquer desfecho)

- **Emenda 1 (revisão da Astra):** `t` = instante da decisão, não do fill; percentil leave-one-out; `tape_as_of ≤ as_of`; população com `age_s ≤ 300 s`; família congelada em 17; teste B com estado congelado no **início** do balde, nascimentos do balde anterior, graduações por `graduated_board_seen_at` (tempo de conhecimento) e reamostragem em blocos de 60 min; ponto cego por `first_seen_source` e horizonte igual.
- **Emenda 2 (olhando SÓ o regressor):** o corte `percentil ≥ 0,50` é degenerado — o portão já compra a cauda da coorte (`p_prog` mediana 0,963: só 2 das 520 entradas ficavam do lado baixo). Corte passou a ser a **mediana da amostra**, o mesmo corte que R65/R67 usaram no absoluto, preservando o confronto directo.

## 7. Veredito, por valor esperado

### 1º — **Nada a ligar. Prioridade operacional da hipótese: baixa.**
**Formulação acordada com a Astra** (a minha primeira versão dizia "respondida, não adiada, porque há mecanismo", e é forte demais): *nenhum dos 17 contrastes passou BH/BY nesta análise retrospectiva; há sinais de **redundância** (Spearman percentil↔absoluto 0,61–0,93, mediana 0,81) e de **restrição de faixa** na população admitida (o portão já compra o percentil 0,96), que reduzem a prioridade operacional da hipótese. **Isto não demonstra ausência de informação incremental.*** A coorte com 105 moedas e **73 % inertes** é uma **explicação plausível** para a ausência de sinal; não identifica causalmente a razão.
**O que ficou por fazer e que mudaria a conclusão:** o **teste incremental** (o percentil separa DENTRO dos tercis do absoluto?). Prometi a aproximação na Emenda 1 e **não a implementei** — o `D_t3` do `run_a.py` compara extremos do próprio percentil, não estratos do absoluto. É a primeira coisa a correr se alguém voltar a este assunto.
**Regra de refutação (o que me faria voltar):** se a coorte passar a ter **≥ 60 % dos membros com pelo menos uma compra por minuto** (hoje 27,1 %) **e** a concordância Spearman percentil↔absoluto cair abaixo de **0,6** em qualquer variável, o teste volta a ter sentido e refaz-se com os mesmos 17 contrastes.

### 2º — **Não parar a mesa por coorte fria.** Benefício não demonstrado, custo certo.
Nascimentos/min é a melhor das quatro e dá D = +0,059 (IC [−0,028, +0,154], p 0,193) removendo **48,8 % das entradas**. **Ponderado por entrada** (e não por balde, como a Astra exigiu): quente **+0,007252** (n = 266) contra frio **−0,051830** (n = 254). As outras três ponderadas por entrada: graduações/h D = +0,0458; tamanho da coorte +0,0153; fração com fluxo positivo −0,0038; progresso mediano −0,0386.
**O que NÃO digo:** que o efeito é nulo depois do custo. O PnL de papel **já desconta 1,75 %** de taxa (`paper_fill.py`), e eu não sei reconciliar esse custo simulado com os 4,09 % reais (que incluem o aluguel da ATA e a derrapagem) — exigir os 4,09 % outra vez seria **contar a taxa duas vezes**. A frase defensável é: **benefício não demonstrado** (IC contém zero), a um preço certo de metade das entradas.
**Regra de refutação:** só voltaria a este teste com o braço quente a mostrar retorno médio por entrada **positivo com IC 95 % inteiramente positivo** em amostra **prospectiva** de ≥ 3 dias, sob a política de saída real.

### 3º — **O tecto de rastreamento provavelmente não era o problema.** Não é motivo para voltar já; também não é assunto encerrado.
A Astra recusou o meu "registar e não voltar", com razão: **taxa média de graduação menor nas não rastreadas não prova que o tecto nunca perdeu moedas boas**, e graduação não é retorno negociável.
**Regra de refutação:** se, com o tecto em 300, a taxa de graduação das moedas *recém-incluídas pelo aumento* superar 1,725 %, o corte anterior estava a perder moedas e este achado cai.
**Auditoria pendente (pedida pela Astra, não feita):** separar `ttg < 0`, `ttg = 0` e `0 < ttg < 5` em vez de juntar tudo sob `< 5 s`, e conferir na cadeia uma amostra pequena (slots e instruções de criação/migração). Enquanto isso não for feito, "nunca tiveram curva negociável" é **inferência**, não medição.

### A medição que eu construiria a seguir — **e não é girar botão**

**Ninguém sabe o desfecho das moedas que recusamos.** Há **41 905 recusas** registadas em `meme_gate_refusals_by_mint` (desde 17/09, 3 593 mints distintos; principais: `snipers_above_max` 15 290, `progress_above_max` 7 933, `holders_below_min` 3 171), **e nenhuma tem desfecho medido**. Todos os estudos R58–R69 olham só a coluna "entrámos"; o quadrado "recusámos e teria dado certo" está vazio por construção. **Enquanto estiver vazio, não conseguimos distinguir um portão que seleciona de um portão que apenas aposta menos vezes** — e é exatamente essa a pergunta do Everton.

Proposta: braço `research_only` que abre **aposta de papel numa amostra aleatória das moedas recusadas**, com os parâmetros de saída da mesa real, com a recusa gravada na aposta. Pré-registo: `obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md`.

## 8. Ressalvas honestas

1. **Um só regime, uma só praça.** 520 mints, 11 dias de setembro de 2026, pump.fun, `flow_v2` (0,05 SOL / alvo 3× / 1800 s / trailing 35 %) — **não** a política de saída da mesa real (0,07 / 1,15× / 300 s / trailing 10 %). Isto testa a associação sob `flow_v2`; a transferência **não está demonstrada** (é a ressalva nº 1 do R67 e continua a valer).
2. **20–23/09 não é um holdout intacto** (a Astra insistiu, e tem razão): o R67 já examinou 20–21/09, e 22/09 não existe (mesa parada por rate-limit de RPC). O split é diagnóstico retrospectivo, não confirmação.
3. **`computed_at` é o início da transação, não o *commit*.** A sensibilidade com atraso conservador de 5 s foi corrida e não muda nada (§1), mas 5 s é um número que escolhi, não uma medida do atraso real de *commit* — que não sei medir com esta coleta.
4. **A coorte não é o mercado.** É "os mints recentemente observados pela pista de 15 s, sob a política de descoberta, retenção e capacidade vigente". A composição depende também da própria mesa (moedas seguradas por posições/propostas abertas).
5. **Potência.** Com o erro-padrão desta amostra, D da ordem de 0,04 é indistinguível de um controlo aleatório (`rnd2` deu +0,0376). Ausência de prova continua a não ser prova de ausência — mas aqui há **mecanismo**, e isso é mais forte que um p.
6. **Não fiz o teste que a Astra pediu** (contribuição incremental do percentil sobre o absoluto num modelo com controlos). Fiz a versão não-paramétrica (associação marginal + concordância Spearman + confronto directo com o absoluto na mesma amostra). É aproximação declarada, não o teste dela.
7. **O desfecho de papel é marcado na curva**, sem derrapagem, sem aluguel de ATA, sem venda falhada. Comparações são sempre **dentro** do papel.
8. **13 dos 17 contrastes têm n ≈ 260 por braço.** Uma moeda de cauda move qualquer célula.
9. **A paridade SQL↔Python cobre 2 das 13 variáveis** (`buys` e `delta de progresso`), em 20 decisões. Antes da correção cobria só `buys` — e foi exatamente por isso que o erro dos ausentes (§3) passou. Depois de estender a paridade ao caso "sujeito sem valor" ela **reproduziu o erro** (2 divergências) e, com o SQL corrigido e o `pct.csv` re-exportado, passa **40/40**. As outras 11 variáveis continuam sem paridade própria; a correção é a mesma linha de SQL em todos os 15 agregados.
10. **A janela do sujeito diverge:** 180 s no SQL, 120 s na função Python. **Nenhuma das 520 linhas exportadas ultrapassou 120 s**, logo não há impacto nesta amostra — mas a discrepância existe no código.
11. **"Todos os membros da coorte têm ≤ 300 s" é medição, não propriedade garantida:** numa grade de 30 min sobre 13–20/09 a fração da coorte com `age_s ≤ 300` tem **mediana 1,0000**. O coletor permite retenção maior para moedas fixadas por posições/propostas abertas (`fast_lane.py`), logo a universalidade vale para a mediana dos instantes medidos, não por construção.
12. **O corte "50 % da coorte tem zero compras" vem de uma grade de 30 min** (13–20/09, baldes com > 10 membros), não dos 520 instantes de decisão.

## 9. Segunda opinião (Astra)

Duas chamadas: **desenho antes de correr** (`.claude/state/astra-review-r69.md`) e **veredito depois** (`.claude/state/astra-review-r69-veredito.md`).

**No desenho ela mudou o estudo, não a redação.** O que aceitei e apliquei está na Emenda 1 (§6). O achado mais concreto dela: `computed_at` usa `now()` = início da transação; e uma abertura real em `features_tape.py:120` (`activity_for` aceita idade negativa, ou seja um `end_time` futuro passaria) — por isso acrescentei a guarda `tape_as_of ≤ as_of`. Também: não usar `meme_tokens.created_at`/`migrated_at` como história do conhecimento (por isso `first_seen_at` e `graduated_board_seen_at` no teste B), e não contar `rastreados agora / criados no balde` (mistura estoque e fluxo).

**No veredito ela não aprovou a primeira versão — e estava certa.** O que aceitei e corrigi:

1. **ERRO DE CÁLCULO (o mais grave).** O `FILTER` do SQL testava ausência só no membro da coorte; **sujeito sem valor recebia percentil ZERO em vez de indisponível** (71 linhas nos dois deltas, 28 em vendas/compras, 12 em compras). Corrigido em `q_pct.sql` e em `stats69.load()`; **A, split, planalto, BH e BY refeitos**. Mudou o resultado: `delta de progresso` de +0,046 para **−0,013** e `vendas/compras` de +0,072 para **+0,106** — esta última passou a ser o menor p da família (0,014) e o único IC a excluir zero. Continua a não passar BH, a ser um pico e a trocar de sinal fora de amostra (§3).
2. **Amostras desalinhadas** entre a versão relativa e a absoluta (a absoluta excluía ausentes, a relativa mantinha-os). Alinhadas.
3. **"Respondida, não adiada, porque há mecanismo" era forte demais.** Substituído pela formulação dela em §7.
4. **O teste B misturava pesos e custos.** Recalculei ponderado por **entrada** (quente +0,007252 / frio −0,051830 — idêntico ao recalculo dela) e retirei a exigência dos 4,09 %: o papel **já desconta 1,75 %** e cobrar o custo real outra vez é **contar a taxa duas vezes**.
5. **O split não é "pico demonstrado":** progresso, fluxo e volume têm o mesmo sinal no ajuste e no teste; quem troca de sinal é o composto. Reescrito como "sinal exploratório de pior retorno nos extremos, sem confirmação independente".
6. **Correções de leitura:** 0,0059 é o limiar **mais restritivo** (primeiro posto), não o mais permissivo; o controlo aleatório é maior que **6** de 13, não 8; a idade tem **+0,001** em q = 0,30, logo o planalto não é limpo; **fluxo também** tem p absoluto ≈ 0,05; a cobertura é **94,3 %**, não 95,7 %.
7. **`first_seen_source` não distingue criação de migração** (ambas são `pumpportal_ws`). Substituí esse argumento pelo que aguenta: **3 969 das 3 973 têm `initial_virtual_sol_reserves` e `bonding_curve`**, campos que só um frame de criação preenche. **Mantive a auditoria de cadeia como pendente** (§7).
8. **`created_at`/`migrated_at` são tempo de PROCESSAMENTO da mensagem** (`normalize.py`), não tempo de bloco — mensagens atrasadas e processadas juntas podem produzir duração artificialmente curta. Declarado.
9. **EXP-M23 confundia "ausência de significância" com "equivalência".** Reescrito com margem de não-inferioridade e limites para perdas graves.

**Onde discordámos:** ela queria o teste principal como **contribuição incremental** do percentil sobre o absoluto num modelo com controlos (`log N`, fração de ausentes, idade dos insumos, fonte da fita, hora cíclica). Com n = 520 e o histórico de sobreajuste do R65/R67, escolhi a versão não-paramétrica. **Registo a discordância** — e registo também que ela tem um ponto que eu não tenho resposta para: *"uma informação útil apenas condicionada ao absoluto é abandonada porque a sua associação marginal é fraca"*. Se o próximo estudo tiver > 1 500 mints, o desenho dela é o certo.

**Ela não subscreve o veredito como "refutação":** *"Despriorizar operacionalmente a hipótese é razoável. Declarar a sua refutação definitiva, ainda não."* **Aceite** — é a linguagem de §7.

## 10. Arquivos

`.claude/state/r69/`: `desenho.md` (desenho congelado + 2 emendas), `cohort.py` (coorte + percentil, funções puras), `test_cohort.py` (11 testes da guarda), `q_pct.sql` → `pct.csv` (520 decisões, 360 KB), `q_state.sql` → `state.csv` (3 205 baldes de 5 min, 272 KB), `q_parity.sql` → `parity.csv` (21 149 linhas cruas, 4,9 MB), `parity.py`, `stats69.py`, `run_a.py` → `a.txt`, `run_b.py` → `b.txt`, `run_family.py` → `family.txt`, `run_extra.py` → `extra.txt` (ponderado por entrada, índice composto, concordância), `q_pct_lag5.sql` → `pct_lag5.csv` (sensibilidade de atraso). Total 5,6 MB. Astra: `.claude/state/astra-review-r69.md`, `.claude/state/astra-review-r69-veredito.md`. KB: `obsidian/11-KNOWLEDGE/KB-0151-a-coorte-nao-respira.md`. Pré-registo: `obsidian/05-EXPERIMENTS/EXP-M23-desfecho-das-recusadas.md`.

## 11. Proposta de linha de diário (23/09)

> **23/09 R69 — o percentil dentro da coorte não separa; a coorte não respira como eu imaginava.** Reconstruí a coorte viva em cada instante de **decisão** (`meme_features_15s`, 4,17 M linhas) com guarda anti-antecipação provada por teste (11 testes) e calculei, para **520 moedas**, o percentil da moeda dentro da coorte nas 13 variáveis de decisão. **0 de 17 hipóteses congeladas passam Benjamini-Hochberg** (menor p **0,014** contra limiar 0,0059); nem Benjamini-Yekutieli. Um **controlo aleatório** deu D = +0,038, maior que **6 das 13** variáveis reais — essa é a régua. **A explicação mais plausível é estrutural:** a coorte tem ~105 moedas, praticamente todas com menos de 300 s, e **só 27 % têm qualquer compra no último minuto** — a mediana tem zero. Por isso o percentil é quase o absoluto disfarçado (**Spearman 0,81 de mediana**) e o portão já compra, sem saber, o **percentil 0,96** da coorte. O estado da coorte também não decide: parar quando está fria removeria **metade das entradas** para um D de +0,059 com IC que contém zero (ponderado por entrada: +0,0073 contra −0,0518) — **benefício não demonstrado**. E o **ponto cego que eu temia provavelmente não existe**: 94,3 % das moedas criadas foram rastreadas, e as não rastreadas graduam-se **3,3× menos** (0,52 % contra 1,73 %) depois de separar as **graduações instantâneas** (98,7 % delas, com `migrated_at` a 0,08 s de `created_at`), que nunca tiveram curva negociável. **O método apanhou o próprio método:** a Astra achou um **erro de cálculo** — sujeito sem valor recebia percentil ZERO em vez de indisponível — e refiz tudo; depois da correção apareceu o único candidato com IC a excluir zero (`vendas/compras` relativo, D +0,106, p 0,014), que **mesmo assim falha os três testes pré-registados**: não passa BH, é um pico (decai a +0,004) e **troca de sinal fora de amostra** (+0,064 no ajuste, −0,073 no teste). **Veredito: prioridade operacional baixa, sem parâmetro para a mesa — e não é refutação definitiva**, porque o teste incremental (percentil condicionado ao absoluto) não foi feito. **A próxima medição não é um botão: é medir o desfecho das moedas que RECUSAMOS** — 41 905 recusas gravadas, **zero desfechos**. Sem esse quadrado, não dá para distinguir um portão que **seleciona** de um portão que apenas **aposta menos vezes**.
