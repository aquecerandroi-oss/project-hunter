# R83 — H-023: proximidade da máxima de 24 h nos sinais do Lab de cripto

Início: 2026-09-28 ~01:30Z (27/09 ~22:30 BRT). Notas incrementais. Só SELECT na VPS (`r83/q.sh` força
`default_transaction_read_only=on`). Scripts em `.claude/state/r83/`, caches em `r83/cache/`.

## 0. Lido antes (regra Obsidian primeiro)
- **Fila de Hipoteses, H-023** (congelada 27/09 ~22:45 BRT): variável `distance_from_24h_high` no instante do sinal
  (fechamento da última vela anterior ao sinal; só dados ≤ sinal), em tercis; direção `high` para compra de
  continuação; `mean_reversion` reportada à parte (leitura esperada oposta, sem sinal previsto); secundária na mesma
  família (Holm) `distance_from_24h_low`. População: sinais de compra do Lab com desfecho resolvido, spot e perp, uma
  decisão por (mercado, versão, sinal). **Antes de qualquer contraste**, redundância: |ρ| de Spearman ≥ 0,8 com
  alguma feature do envelope (retorno 4 h/15 m, momentum, ATR%) → para por limite de medida. Previsão: tercil mais
  perto da máxima rende ≥ +0,05 R líquido a mais que o mais longe, IC 95 % bootstrap por mercado acima de zero,
  patamar em cortes vizinhos. Refutação: IC inf < −0,01 R (efeito oposto) → REFUTA; IC sup < +0,01 R → REFUTA pelo
  tamanho; pico → NÃO CONFIRMA; |ρ| ≥ 0,8 ou < 150 sinais resolvidos com a feature → limite de dado/medida.
- **KB-0004** (George & Hwang 2004): razão preço/máxima de 52 semanas, ações, mensal, transversal; extrapolação a
  24 h/15 m/cripto/long é hipótese nova. O envelope da `momentum` **não** guarda a distância: tratar ausência como
  reprovação rejeitaria tudo — contar cobertura e reconstruir das 1 440 velas finais contíguas até `observation_ts`,
  sem informação posterior. Máximas intrabar (não fechamentos): a feature pode estar a selecionar "menos pavio".
- **KB-0145**: mesa `spot/1` executa sinais `mean_reversion v14` na Jupiter; custo ~0,14 % ida-e-volta em 0,05 SOL.
- **Strategy Backlog item 8**: bloqueada só pela medição de redundância (retenção ~100 % mataria).
- **Dicionário, linha `distance_from_24h_high`/`_low`**: "existe mas não estava no envelope da v1; nunca testada".
- **docs/RESEARCH.md**: três rótulos; moinho contrasta selecionados × resto (limitação apontada no R70/H-006: a
  fila pede tercil × tercil); errata do R76 (§0.4b-4): "imprecisão não vira refutação".
- **docs/DATABASE.md §6/§16.2, PIPELINE §6b**: `signal_outcomes.r_multiple` = **R_net** (custos assumidos do envelope:
  taxa 4 bps, spread 2 bps, derrapagem 5 bps, + perna de funding); `meta.r_ex_funding` = R líquido de custos de
  negociação sem funding (100 % de cobertura); `r_multiple` NULL com `meta.r_net_reason` quando o funding não se
  estabelece. PIPELINE §6b T3.73: pesquisa filtra `market_type = 'perpetual'` (340 sinais antigos em linha spot com o
  custo do perp, gêmeos das decisões perp, todos sem R_net).
- **price.py:106** `DistanceFromExtreme` v1: `(close_última − max(high))/max(high)` sobre as 1 440 velas 1m finais
  contíguas do contexto (`tail_minutes`), máximas intrabar, vela final incluída.

## 1. Dados (extração cega, sem valor de desfecho)
- `r83/q_pop.sql` (contagem por estratégia/versão/estado, sem R): ver §1.1. `r83/q_env2.sql`: o envelope de **nenhum**
  sinal carrega `distance_from_24h_high`, `return_4h` nem `momentum_15m` (como no R70); carrega `atr` (Wilder 14 na
  grade da versão, `rolling_window_v1`), `return_15m` (só `momentum`), `zscore_15m` (reversão), volume relativo.
- `r83/q_feat.sql` → `cache/feat.csv` (17 451 sinais `terminal` long; md5 `533dfa0f77bec7b8adfb3a0e5615c901`): por sinal,
  agregados das velas `candles_1m` `is_final` com abertura em `[obs − 1440 min, obs − 1 min]` (`obs` =
  `observation_ts` do envelope = fecho da barra de decisão): n, 1.ª/última abertura, max(high), min(low),
  max(received_at); fechamentos em obs−1, obs−16, obs−61, obs−241 min. Só a **nulidade** de `r_multiple` e o motivo.
- **A feature não está persistida onde a população precisa:** envelope 0 %; `feature_snapshots` (produção, desde
  06/09 18:17Z) tem o valor `ok` no minuto `obs` em só **360 de 6 738** sinais prospectivos (a janela de 1 500 min do
  scanner costuma estar com buraco/aquecimento). Logo **reconstruo das velas com a fórmula de produção** — análise
  retrospectiva, declarada.
- **Validação da reconstrução** (`r83/validate.py` → `validate.txt`): contra o snapshot de produção do mesmo minuto,
  quando a última vela do snapshot fecha em `obs`: `d_high` **337/337 idênticos**, `d_low` 337/337, `return_15m`
  5 901/5 901, `return_4h` 3 324/3 324 (|Δ| < 1e-12). Os 23 restantes diferem porque o snapshot foi calculado antes
  de a vela de `obs` chegar (1 min atrasado) — ρ 0,9998. `return_15m` do envelope × reconstruído: 5 823/5 823 idênticos.
- **Testes** (`r83/test_r83.py`, 12): valores conhecidos; igualdade com a classe de produção `DistanceFromExtreme`
  sobre `build_context`; vela posterior a `obs` e vela em formação **não mudam** o valor (nem na réplica do SQL nem na
  produção); vela não final dentro da janela não é lida; buraco = ausente; `check_observable` recusa janela
  deslocada 1 min e vela chegada depois do sinal; controle do próprio teste (janela vazada muda o valor); tercis com
  empates; população.

### 1.1 População (passo cego `r83/blind.py` → `blind.txt`)
- 17 451 terminais long → **fora 133 spot** (todos `funding_schedule_unknown`, gêmeos do perp, T3.73) → **fora 1 494
  duplicadas** (mesma versão, mercado e `obs` em coortes de replay repetidas; mantém prospectiva, depois a coorte de
  menor id) → 15 824 → **guarda do moinho** (`check_observable`, `t = emitted_at`, `as_of = obs`, `computed_at` =
  última chegada das velas da janela na coorte prospectiva; = `obs` no replay, declarado): **79 recusadas**
  (prospectivas com vela chegada depois do sinal) → **15 745**.
- `emitted_at − obs` na prospectiva: mediana 12,4 s, p99 113 s.
- Feature disponível em 15 743 (2 `mean_reversion_m5` com janela incompleta). R_net nulo em 1 228 (1 113
  `funding_schedule_unknown`, 18 `funding_ambiguous_exit`, resto `funding_missing:*`) — censurados da primária.
- **Com R_net e feature:** continuação **9 187** (momentum 5 551, volume_anomaly 3 572, session_orb 56, breakout 8;
  289 mercados); reversão **5 129** (mean_reversion 4 549 — v14 183 —, h1 211, m5 369; 119 mercados); outras 199.
  **≥ 150: a cláusula de dado não dispara.**
- Retenção do filtro do KB-0004 (`d_high ≥ −0,005`): momentum 29,9 %, volume_anomaly 18,4 %, reversão 0 %.

### 1.2 Redundância (antes de qualquer desfecho) — **não dispara**
Spearman de `d_high` na continuação (n 9 187): return_15m +0,124 · return_1h +0,143 · return_4h +0,176 ·
momentum_15m (ret15 ÷ ATR% do envelope) +0,324 · ATR% −0,385 · volume relativo −0,094. Com os valores de
**produção** (snapshots, subconjunto): momentum_15m +0,302, return_4h +0,269, atr_14_pct −0,272. Reversão: ATR% −0,578,
return_4h +0,517 (produção atr_14_pct −0,693). **Máximo |ρ| = 0,385 (continuação) e 0,693 (reversão) < 0,8.**
Secundária `d_low` na continuação: ATR% +0,767, return_4h +0,698 (alta, abaixo de 0,8; a cláusula é da primária,
registrado). ρ(d_high, d_low) −0,002 na continuação.

## 2. Desenho (congelado ANTES de extrair qualquer desfecho — 2026-09-28 ~01:55Z)
1. **Famílias (pelo docstring de cada estratégia, não pelo resultado):**
   - **continuação** (sinal previsto +): `momentum` v1–v13 (rompe a máxima de 20 fechamentos), `breakout` v2 (rompe
     máximas após contração), `volume_anomaly` v1–v2 (pico de volume fechando forte), `session_orb` v1 (rompe a faixa de
     abertura);
   - **reversão** (sem sinal previsto): `mean_reversion` v1–v19, `mean_reversion_h1` v1, `mean_reversion_m5` v1; a
     `mean_reversion v14` (mesa `spot/1`) é linha própria, descritiva;
   - **outras** (descritivo, fora das duas famílias): `trendline_breakout` (89 % são quiques, pelo próprio docstring),
     `trendline_bounce`, `sweep_reclaim` — estrutura de reta/pivô, nem continuação pura nem reversão; n = 199.
2. **Desfecho:** `signal_outcomes.r_multiple` (**R_net**: custos assumidos do envelope + funding), em R. NULL fica fora
   (1 228, contado). Sensibilidade: `meta.r_ex_funding` em todos (inclui os NULL).
3. **Tercis dentro de cada estratégia** (`strategy key`), com os cortes do moinho (`stats.terciles`: xs[n/3], xs[2n/3];
   baixo ≤ c1, alto > c2, empates juntos). Motivo, decidido às cegas: a `momentum` fica perto da máxima por
   construção (mediana −1,06 %) e a `volume_anomaly` não (−2,43 %); tercis do agregado fariam do contraste
   "momentum × volume_anomaly". Sensibilidades: tercis do agregado da família; tercis por versão.
4. **Contraste primário** (continuação): **D = média R_net(alto) − média R_net(baixo)**, pelo moinho
   (`run_hypothesis`): linhas = baixo ∪ alto, variável = indicador `alto` (1/0), limiar congelado 0,5, direção `high`;
   `cluster = mercado` (bootstrap 10 000, semente 83); `stratum = estratégia × dia UTC` para a permutação (bilateral);
   guarda `ObservabilityColumns(as_of, computed_at, strict=False)`; MRE +0,05; `require_positive_level` (regra da casa:
   o tercil alto tem de ganhar em nível); `require_plateau = False` **no moinho** porque sobre o indicador a curva é
   degenerada — o patamar é julgado fora (item 5). IC por blocos de dia UTC reportado ao lado (descritivo).
5. **Patamar** nos cortes vizinhos: extremo-q de cima × extremo-q de baixo, dentro da estratégia, q ∈ {1/5, 1/4,
   3/10, **1/3**, 2/5, 9/20, 1/2}; D e IC por mercado em cada q; forma pelo `stats.plateau_or_spike` do moinho
   (≥ 4 cortes consecutivos com D > 0, ≥ 2 com IC inf > 0).
6. **Holm** sobre a família {`d_high` continuação, `d_low` continuação}, p de permutação bilateral. `d_low` orientado
   igual (alto = mais longe da mínima − baixo), sem previsão de sinal própria.
7. **Rótulo (ordem):**
   1. |ρ| ≥ 0,8 ou < 150 com R e feature → LIMITE (já verificado: não dispara — 0,385 e 9 187);
   2. IC sup de D < +0,01 → **REFUTA pelo tamanho** (inclui o caso "efeito oposto" sustentado: IC sup < −0,01);
   3. **CONFIRMA** se D ≥ +0,05 **e** IC inf > 0 **e** p < 0,05 **e** p Holm ≤ 0,05 **e** tercil alto > 0 em nível
      **e** patamar;
   4. curva em pico (com o resto a favor) → NÃO CONFIRMA; qualquer outro caso → NÃO CONFIRMA.
   **Errata (princípio do R76 §0.4b-4, escrita antes do contraste):** a cláusula congelada "limite inferior do IC
   abaixo de −0,01 R (efeito oposto) → REFUTA", lida ao pé da letra, dispara sempre que o IC é largo — um IC
   [−0,02, +0,20] a acionaria admitindo efeito forte a favor. O "efeito oposto" sustentado pelo intervalo é o IC
   **inteiro** abaixo de −0,01 (IC sup < −0,01). O relatório mostra as duas leituras; a literal sozinha dá
   NÃO CONFIRMA. O texto da fila não é reescrito.
8. **Reversão:** o mesmo contraste (alto − baixo, `d_high` e `d_low`), IC e p, **sem rótulo de previsão**; v14 à parte.
9. **Sensibilidades (descritivas, não mudam o rótulo):** `r_ex_funding`; só prospectiva; só replay; por estratégia
   (momentum, volume_anomaly); tercis agregados; tercis por versão; **uma decisão por (estratégia, mercado, barra)**
   (as versões da `momentum` decidem muito a mesma barra — mantém a versão de menor número); o filtro do KB-0004
   (`d_high ≥ −0,005` × resto) na momentum; média por tercil (baixo/meio/alto).

## 2b. Emenda pré-desfecho (revisão de desenho da Astra, `r83/astra_design.log`; ainda nenhum desfecho lido)
A Astra concordou com a janela/causalidade, as famílias, os tercis por estratégia, o indicador alto/baixo com patamar
externo, a errata e a deduplicação. Três must-fix, todos aceitos:
1. **`received_at` é carimbo de persistência do banco** (`server_default now()`, `persist_rows.py`), não a observação do
   coletor. A guarda com `computed_at = max(received_at)` fica como **proxy de persistência** (79 recusadas); no replay
   `computed_at = obs` é declaração da simulação. **A conclusão é sobre a reconstrução retrospectiva** (sem velas
   futuras, provado pelo teste), não sobre a feature como o scanner a teria visto: exigir a janela a terminar em `obs`
   censura casos em que a produção usaria 1 440 velas anteriores (e o banco pode ter janela completa que o scanner não
   tinha). Sensibilidade: sem a guarda de persistência (as 79 de volta).
2. **O p de permutação linha a linha não é válido para o Holm**: as versões da mesma estratégia decidem a mesma barra
   e, como `d_high` só depende de (mercado, obs), recebem o **mesmo** tercil. Regra nova (antes dos desfechos): o p do
   portão e do Holm é o **maior** de dois: (a) permutação de **episódios** (estratégia, mercado, obs) — os rótulos
   alto/baixo embaralhados entre episódios dentro de estratégia × dia, cada episódio carregando todas as suas linhas —
   e (b) o p bilateral do bootstrap por mercado (2·min(P[D* ≤ 0], P[D* ≥ 0])). O p linha a linha do moinho fica
   descritivo. Limite declarado: choques comuns entre mercados no mesmo dia não são capturados por nenhum dos dois; o
   IC por dia vai ao lado.
3. **O rótulo H-023 é externo** (`h023.fila_label`), e o `VEREDITO` do moinho é só saída mecânica (o moinho refuta com
   IC sup < MRE = +0,05; a fila, com IC sup < +0,01). Antes da regra da fila entram as guardas de potência do moinho
   (`verdict._no_power`: ≥ 20 por braço, ≥ 8 mercados no braço mais magro, IC finito, ≤ 1 % de réplicas inválidas).
   Nenhum `block` no moinho (o IC por dia é descritivo, calculado fora).
Nice-to-have aceitos: (i) sensibilidade `r_ex_funding` nos **mesmos** cortes/linhas da primária **e** com os cortes
recalculados sobre todos; (ii) o patamar conta **partições distintas** (dois q que dão a mesma partição valem um);
(iii) composição por estratégia/versão em cada braço. Correção de redação aceita: `trendline_bounce` é continuação pelo
próprio contrato e `sweep_reclaim` compra falha de rompimento — "outras" é exclusão operacional, não classificação.

## 3. Resultado (desfechos lidos às 2026-09-28T01:58:45Z, `r83/q_out.sql` → `cache/out.csv`, md5 e910321c1b3facf3a2e9fde5e6e92a69)
Saída integral: `r83/h023.txt` (moinho + portão + curva + sensibilidades + reversão). Fumaça com desfecho sintético de
efeito conhecido antes (`r83/smoke_synthetic.py` → `smoke_synth.txt`: o encanamento dá CONFIRMA com D +0,21 e patamar
7/7 no efeito injetado e NÃO CONFIRMA na variável nula).

### 3.1 Estados (pós-guarda, perp, dedup; `R nulo` = sem R_net)
- continuação: alvo 2 359 (+103 sem R), stop 1 974 (+55), invalidado 4 198 (+114), expirado 656 (+11) → **9 187 com R**;
- reversão: alvo 1 340 (+207), stop 1 673 (+366), expirado 2 117 (+373) → **5 130 com R** (5 129 com a feature);
- outras: alvo 31, stop 55, invalidado 75, expirado 38 → 199.

### 3.2 Primária — continuação, `distance_from_24h_high`, tercil alto − baixo (dentro da estratégia)
- Tercis (n, média R_net): **baixo 3 066 · −0,2158 | meio 3 062 · −0,2133 | alto 3 059 · −0,2482**.
- **D = −0,0324 R**, IC 95 % bootstrap por mercado **[−0,1131, +0,0376]** (279 mercados, 10 000, semente 83); IC por dia
  [−0,1319, +0,0928]; p episódios 0,497, p bootstrap 0,367 → **p do portão 0,497**; Holm 0,497.
- Composição por braço (alto/baixo): momentum 1 849/1 853, volume_anomaly 1 190/1 191, session_orb 18/19, breakout 2/3.
- Curva (7 partições distintas): D de −0,022 a −0,056, **nenhum corte com D > 0 → forma "ausente"**.
- **Cláusula a cláusula:** n 9 187 ≥ 150 e |ρ| 0,385 < 0,8 (não é limite); IC sup +0,0376 ≥ +0,01 → **não refuta pelo
  tamanho da fila**; efeito oposto sustentado exigiria IC sup < −0,01 → não; a leitura literal "IC inf < −0,01" aciona
  (−0,113) → pela errata, sozinha, NÃO CONFIRMA; D < +0,05, IC com zero, p 0,50, alto perde em nível (−0,248), curva
  ausente → **H-023: NÃO CONFIRMA**. Nota: o **tamanho previsto (+0,05 R) fica fora do IC** (IC sup +0,038) — o moinho,
  que refuta com IC sup < MRE, carimba mecanicamente `REFUTA` desse tamanho; a regra da fila (IC sup < +0,01) não.
- **Heterogeneidade forte (descritivo):** momentum **D +0,097 [+0,028, +0,162]** (tercis −0,193 / −0,156 / −0,096 — no
  sentido de George & Hwang, mas **todos os tercis perdem em nível**); volume_anomaly **D −0,231 [−0,363, −0,094]**
  (tercis −0,256 / −0,298 / −0,488 — perto da máxima é **pior**). O agregado da família cancela os dois.

### 3.3 Secundária — `distance_from_24h_low` (alto = mais longe da mínima)
- Tercis: baixo −0,3043 · meio −0,2754 · alto −0,0974. **D = +0,2069 [+0,1206, +0,2841]**, IC dia [+0,119, +0,329],
  p do portão 0,0002, **Holm 0,0004**, patamar 7/7 (D de +0,167 a +0,253, todos com IC > 0). Falha **só** no nível: o
  tercil alto perde −0,097 R. Sem sinal pré-registrado; ρ com ATR% +0,767 e com retorno 4 h +0,698.
- Pós-hoc declarado (`r83/posthoc.py` → `posthoc.txt`): dentro de estratégia × tercil de ATR% D cai para +0,126
  [+0,029, +0,211]; dentro de estratégia × tercil de retorno 4 h, +0,158 [+0,072, +0,236]; momentum +0,183 [+0,094,
  +0,273], volume_anomaly +0,251 [+0,099, +0,379]. **Pista** (não confirmação): só vira hipótese com população nova.

### 3.4 Sensibilidades da primária (descritivas; nenhuma muda o rótulo)
r_ex_funding mesmas linhas −0,032 [−0,112, +0,039]; cortes recalculados −0,037 [−0,116, +0,033]; sem a guarda
−0,029 [−0,108, +0,040]; só prospectiva **−0,088 [−0,177, −0,003]**; só replay +0,088 [−0,037, +0,176] (16 mercados);
tercis do agregado +0,022 [−0,064, +0,101]; por versão −0,048 [−0,133, +0,028]; uma por (estratégia, mercado, barra)
**−0,084 [−0,167, −0,002]**; momentum v3 (paper) +0,062 [−0,040, +0,163]. Filtro do KB-0004 (`d_high ≥ −0,005` × resto,
momentum): +0,068 [+0,008, +0,131], mas o selecionado perde −0,101 R em nível (retenção 29,9 %).

### 3.5 Reversão (sem sinal previsto) e outras
- reversão `d_high`: tercis −0,042 / **+0,046** / −0,035; D +0,007 [−0,101, +0,143], p ep 0,98; curva "pico" (D de −0,023
  a +0,025). `d_low`: D +0,081 [−0,062, +0,218].
- **mean_reversion v14 (mesa `spot/1`)**: 183 com R; tercis −0,094 / −0,010 / **+0,135**; D +0,228 [−0,099, +0,597]
  (46 mercados), p ep 0,22 — IC largo, descritivo.
- outras (199): D +0,080 [−0,292, +0,273].

## 4. Segunda opinião da Astra no veredito (`r83/astra_verdict.log`, bruto em `.claude/state/astra-review-R83-verdict.md`)
- **Concorda com NÃO CONFIRMA.** Reproduziu em memória D −0,03244 [−0,11308, +0,03756], p do portão 0,497 (d_high) e
  D +0,20694 [+0,12065, +0,28412], p 0,0002 (d_low); conferiu md5 dos caches, 0 desfechos duplicados, 0 sinais sem
  desfecho, 0 mudança de disponibilidade de R entre a extração cega e a final, nenhum episódio com rótulo/estrato misto,
  0 réplicas inválidas. 17 testes passaram na execução dela. **Nenhum must-fix que mude o rótulo.**
- Registra o **argumento literal para REFUTA** (a fila diz "IC inf < −0,01" e −0,113 satisfaz) e concorda que aplicá-lo
  abandonaria a errata escrita antes do contraste. Redação aceita: "a vantagem prevista de +0,05 R fica acima do IC sup por
  mercado (+0,0376), logo não é sustentada por esse intervalo; o critério formal de refutação por tamanho (IC sup < +0,01)
  não foi atingido" — e **só no IC por mercado**: o IC por dia [−0,132, +0,093] ainda comporta +0,05.
- Heterogeneidade: publicar momentum e volume_anomaly **juntos**, como decomposição descritiva, com as ressalvas de que
  todos os tercis da momentum perdem em nível e o IC por dia dela [−0,030, +0,233] contém zero; ICs separados não são teste
  de interação. Não tirar volume_anomaly nem inverter direção depois de ver.
- d_low: pista para população nova; ρ 0,767 não dispara 0,8 mas não demonstra informação incremental; os ajustes pós-hoc
  por tercis, separados, não provam independência conjunta. Desenho mínimo sugerido (não escrito como bloco): coorte
  prospectiva posterior ao R83, uma unidade por estratégia×mercado×barra, previsão direcional única, teste incremental
  **conjunto** contra ATR% e retorno 4 h congelado antes, parada por tamanho, e exigência de nível líquido positivo.
- Nice-to-have: (i) o texto de previsão do `mill()` para `d_low` reaproveita o da máxima — **defeito de redação só no
  cabeçalho da seção 1b de `h023.txt`**; o cálculo não muda e **não re-rodei** para não mexer nas impressões digitais
  publicadas; (ii) teste do intervalo IC sup ∈ [+0,01, +0,05) (moinho REFUTA × fila NÃO CONFIRMA) — **acrescentado**
  (`test_upper_between_fila_bar_and_mre_is_not_refuted_by_the_fila`, 18 testes).
- Ressalva operacional dela: rodou pytest com cache (criou `.pytest_cache`); nada mais escrito.
- Aviso do `astra.sh` de árvore alterada nas duas chamadas: os arquivos novos listados (`infra/research/exp_m26/tests/
  test_ler.py`, `test_migration_0067_visibility.py`, `astra-review-*.md`, a minha KB-0163) são de outros agentes na árvore
  compartilhada ou saídas esperadas — não da Astra.

## 5. Veredito
**H-023: NÃO CONFIRMA** (concluída). Sem CONFIRMA, **não há variante para o Lab**: nenhuma especificação de versão,
parâmetro ou ativação (`activate_strategy_version.py` não se aplica). Próximo passo recomendado (não executado): gravar
`distance_from_24h_high/_low` no envelope imutável do sinal, para que uma hipótese futura (a pista de `_low`, ou a
divergência por estratégia) seja medida em coorte nova sem reconstrução.
