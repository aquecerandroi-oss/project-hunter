# R59 — A vantagem está na SAÍDA? Replay de regras de saída sobre a série de 15 s

**Data:** 2026-09-18 (as_of 17:40 UTC / 14:40 BRT). **Pergunta do Everton:** a mesa real perdeu (12 compras confirmadas, −0,077 SOL) enquanto o papel às vezes ganha; PS fez +0,66 R por acidente de saída. A vantagem está na saída?

**Resposta curta: não.** A regra de saída move a soma em ±0,1–0,3 SOL por ~200 apostas (≈ +0,001 SOL/aposta, +0,02 R/aposta); o efeito de um trailing sempre armado (30 %) é real (26 apostas melhoram, 3 pioram, teste do sinal p < 0,01), mas **nenhuma regra** deixa a concentração dos 3 maiores ganhos abaixo de 50 % num recorte honesto (mint único): as 3–5 moedas que sobem dominam o PnL sob qualquer saída. A hipótese de taxa (1,25 % vs 1,75 % por perna) muda a soma tanto quanto a melhor regra (+0,13 SOL em 215 apostas). Nas 12 reais, a melhor saída só chega a ≈ 0 SOL, e 100 % disso vem do PS.

## 1. Dados e método

| item | valor |
|---|---|
| janela | entradas de 2026-09-16 15:00 UTC (12:00 BRT) a 2026-09-18 17:40 UTC |
| conjuntos | `operator/5 real` (12 `meme_live_positions`, todas `decided_by=executor:auto_stage1`), `operator/5` (19 papel), `flow_v2/5` (139), `flow_v2/2` (165), `flow_v2/6` (25), `flow_v2/8` (31) = 391 linhas, 194 mints |
| "13 compras" | `meme_live_orders`: 12 `buy confirmed`, 7 `buy failed`, 359 `refused`; a 13.ª é uma compra que não virou posição — só as 12 têm PnL |
| caminho de preço | `meme_features_15s.mcap_sol` (mcap teórico das reservas virtuais), razão contra o mcap de entrada (papel: `entry.snapshot.mcap_sol`; real: `virtual_sol_reserves_after / virtual_token_reserves_after × 10⁹` do fill). Não usei `real_sol_reserves` (não existe na série de 15 s; `mcap_executable_sol` só difere em Mayhem) |
| taxas | 1,25 % por perna (`PnL = 0,05 × 0,9875² × múltiplo − 0,05`), stake normalizado a 0,05; sem slippage; instante de decisão = `as_of` (sem antecipação: a linha só carrega observações ≤ `as_of`) |
| linha de suporte (`line_broken`) | `meme_features_1m.support_line_sol + support_line_slope × Δmin` da linha mais nova com `end_time ≤ as_of` (`lines_exit.support_at`); rompida = 2 linhas de 15 s seguidas com mcap < linha (`line_break_snapshots = 2`); sem linha = cega, sequência zera |
| primeira venda do criador | mín(`meme_paper_bets.creator_sold_seen_at`, primeiro `meme_features_1m.creator_sold = true`) — o que o motor de papel lê; variante `f2` acrescenta `meme_features_15s.creator_net_seller` |
| código | `.claude/state/r59/replay.py` (NumPy, sem pandas); SQL em `.claude/state/r59/q_bets.sql`, `q_15s.sql`, `q_1m.sql`; saídas completas em `.claude/state/r59/out_earlier.md`, `out_hold600.md`, `out_hold120.md`, `out_earlier_fee175.md` |

### 1.1 Censura — o problema central

A série de 15 s segue uma moeda até 300 s de idade, ou até 1 800 s **enquanto** há aposta/posição/proposta fixada (T4.33). Quando a aposta fecha, a moeda deixa de ser observada. Logo:

| modo | o que mede | elegíveis (de 391) |
|---|---|---|
| `earlier` | a regra só pode disparar **antes** da saída registrada; se não disparar, vale a saída registrada (reprecificada a 1,25 %). Mede "sair mais cedo teria ajudado?" — sem censura | 387 (215 mint@minuto únicos no papel) |
| `hold ≥ 120 s` | regra sobre a série inteira, fechamento forçado na última linha (`censored`) | 300 (168 únicos; 11 reais) |
| `hold ≥ 600 s` | o recorte pedido (≥ 10 min de série depois da entrada) | **61** (30 únicos; 3 reais) — viés: só entram apostas que já ficaram ≥ 10 min abertas (`time_stop`/`line_broken` tardio) |

Cobertura mediana depois da entrada: 62 s (flow_v2), 92 s (real); hold mediano 76 s / 102 s. O "segurar mais" só é mensurável no subconjunto que de fato segurou.

`flow_v2/5` e `flow_v2/2` entram nas mesmas moedas nos mesmos minutos (a diferença do portão é pedigree): somar os 5 conjuntos conta a mesma moeda até 4 vezes — daí o recorte "papel único (mint@minuto)".

## 2. Resultado principal — papel único (215 apostas), modo `earlier`

| regra | n | hit | R médio | soma SOL | MDD SOL | top-3 |
|---|---|---|---|---|---|---|
| (a) saída registrada, PnL do banco (taxa 1,75 % + impacto) | 215 | 36 % | −0,002 | **−0,019** | 0,307 | — (soma ≤ 0) |
| (a') mesma saída, mcap × 1,25 % | 215 | 39 % | +0,010 | +0,112 | 0,290 | 259 % |
| (b) `line_broken` (2 linhas) | 215 | 38 % | +0,003 | +0,027 | 0,281 | 1060 % |
| (b') conjunto de papel inteiro replicado | 215 | 38 % | +0,001 | +0,011 | 0,276 | 2868 % |
| (c) trailing 15 % | 215 | 39 % | +0,029 | +0,311 | 0,191 | 92 % |
| (c) trailing 30 % | 215 | 40 % | +0,024 | +0,253 | 0,218 | 114 % |
| (c) trailing 50 % | 215 | 39 % | +0,012 | +0,132 | 0,277 | 219 % |
| (d) arma trailing 30 % só após +25 % | 215 | 40 % | +0,018 | +0,191 | 0,244 | 151 % |
| (d) arma trailing 30 % só após +50 % | 215 | 40 % | +0,016 | +0,168 | 0,266 | 172 % |
| (d) arma trailing 30 % só após +100 % | 215 | 39 % | +0,010 | +0,112 | 0,290 | 259 % |
| (d) alvo +25 % senão trailing 30 % | 215 | 44 % | +0,006 | +0,061 | 0,181 | 339 % |
| (d) alvo +50 % senão trailing 30 % | 215 | 41 % | +0,018 | +0,193 | 0,196 | 110 % |
| (d) **alvo +100 % senão trailing 30 %** | 215 | 40 % | +0,035 | **+0,372** | 0,178 | **76 %** |
| (e) tempo 2 min | 215 | 38 % | −0,009 | −0,100 | 0,323 | — |
| (e) tempo 5 min | 215 | 39 % | +0,008 | +0,087 | 0,302 | 329 % |
| (e) tempo 15 min | 215 | 39 % | +0,011 | +0,115 | 0,290 | 252 % |
| (e) tempo 30 min | 215 | 39 % | +0,010 | +0,112 | 0,290 | 259 % |
| (f) primeira venda do criador | 215 | 39 % | +0,006 | +0,063 | 0,296 | 458 % |
| (f2) idem + `creator_net_seller` 15 s | 215 | 39 % | +0,001 | +0,007 | 0,278 | 4081 % |
| (g) alvo +30 % ∨ trailing 20 % ∨ 5 min | 215 | 41 % | +0,011 | +0,117 | 0,167 | 175 % |
| (g) alvo +50 % ∨ trailing 20 % ∨ 5 min | 215 | 40 % | +0,021 | +0,227 | 0,182 | 94 % |
| (h) alvo 2× ∨ trailing 30 % ∨ 5 min | 215 | 40 % | +0,030 | +0,321 | 0,195 | 88 % |
| (h) alvo 2× ∨ trailing 30 % ∨ 15 min | 215 | 40 % | +0,035 | +0,374 | 0,178 | 76 % |
| (h) alvo 3× ∨ trailing 30 % ∨ 30 min | 215 | 40 % | +0,025 | +0,265 | 0,218 | 114 % |

Top-3 > 100 % significa que, fora das 3 maiores, o resto é negativo. Os 3 maiores são os mesmos sob quase toda regra: `4XYuRzrB` (+0,120, creator_dump a 52 s), `fsnuqm67` (+0,097, alvo 3× a 201 s), `H88Srjvu`/`5hmWwRNw` (+0,07).

### 2.1 Delta pareado por aposta (regra − saída registrada a 1,25 %)

| regra | melhora | piora | igual | Σ delta | top-3 dos deltas > 0 | p (sinal) |
|---|---|---|---|---|---|---|
| `line_broken` (2) | 21 | 24 | 170 | −0,084 | 64 % | 0,77 |
| trailing 15 % | 44 | 26 | 145 | +0,200 | 22 % | 0,04 |
| **trailing 30 %** | **26** | **3** | 186 | +0,142 | 50 % | **< 0,01** |
| trailing 50 % | 8 | 2 | 205 | +0,020 | 89 % | 0,11 |
| alvo 2× senão trailing 30 % | 30 | 7 | 178 | +0,261 | 49 % | < 0,01 |
| alvo 2× ∨ trailing 30 % ∨ 15 min | 30 | 7 | 178 | +0,263 | 48 % | < 0,01 |
| alvo +25 % senão trailing 30 % | 45 | 34 | 136 | −0,051 | 29 % | 0,26 |
| tempo 2 min | 24 | 20 | 171 | −0,212 | 41 % | 0,65 |
| tempo 5 min | 10 | 6 | 199 | −0,025 | 74 % | 0,45 |
| primeira venda do criador | 12 | 6 | 197 | −0,048 | 64 % | 0,24 |
| alvo +30 % ∨ trailing 20 % ∨ 5 min | 51 | 42 | 122 | +0,006 | 25 % | 0,41 |

Leitura: o único efeito robusto é **trailing sempre armado a 30 %** (o do papel, 35 % armado só depois de 1,5×, nunca dispara: 2 saídas por trailing em 164). Ele corta a reversão antes do `line_broken` (que espera 2 fotos abaixo de uma linha projetada) e antes do `creator_dump`. Alvo 2× acrescenta 8 saídas no pico (+0,12 SOL) — e essas são exatamente as 3 grandes: a parte "alvo" é concentrada, a parte "trailing" é difusa. Alvos curtos (+25/+30 %) e tempo 2 min **pioram**: matam as poucas que sobem.

### 2.2 Sensibilidade à taxa (modo `earlier`, papel único)

| regra | 1,25 %/perna | 1,75 %/perna |
|---|---|---|
| saída registrada reprecificada | +0,112 | +0,002 |
| trailing 30 % | +0,253 | +0,142 |
| alvo 2× senão trailing 30 % | +0,372 | +0,260 |

A diferença de 0,5 pp por perna vale ~0,11 SOL em 215 apostas — a mesma ordem do melhor ganho de regra. A taxa efetiva real (0,95 % + 0,30 % de criador + rede 9 000 lamports + rent de ATA ~0,0015 SOL + impacto) fica entre as duas; nas 12 reais, o PnL registrado (−0,0741 normalizado) contra o replay a 1,25 % (−0,0585) mostra ~0,0013 SOL/operação de custo além de 1,25 %.

## 3. Por conjunto de entrada (modo `earlier`, soma SOL / top-3)

| regra | operator/5 real (12) | operator/5 (19) | flow_v2/5 (137) | flow_v2/2 (163) | flow_v2/6 (25) | flow_v2/8 (31) |
|---|---|---|---|---|---|---|
| (a) registrada | −0,074 | −0,024 | −0,008 | +0,075 | +0,009 | +0,004 |
| (a') registrada × 1,25 % | −0,059 | −0,012 | +0,073 / 323 % | +0,174 / 166 % | +0,025 / 589 % | +0,023 / 640 % |
| (b) `line_broken` | −0,042 | +0,014 | −0,020 | +0,083 / 349 % | +0,032 / 433 % | +0,029 / 478 % |
| (c) trailing 15 % | −0,046 | −0,055 | +0,078 / 281 % | +0,253 / 112 % | **+0,077 / 188 %** | **+0,103 / 145 %** |
| (c) trailing 30 % | −0,058 | −0,012 | +0,147 / 161 % | +0,272 / 106 % | +0,051 / 286 % | +0,041 / 363 % |
| (d) alvo 2× senão trailing 30 % | −0,058 | +0,021 | **+0,259 / 84 %** | **+0,384 / 73 %** | +0,058 / 264 % | +0,048 / 325 % |
| (e) tempo 5 min | **−0,017** | **+0,033** | +0,043 / 523 % | +0,160 / 177 % | +0,013 | +0,010 |
| (f) 1.ª venda do criador | −0,075 | −0,005 | −0,019 | +0,115 / 252 % | +0,025 | +0,026 |
| (g) alvo +30 % ∨ trailing 20 % ∨ 5 min | −0,054 | −0,038 | −0,047 | +0,115 / 176 % | −0,003 | +0,033 |
| (g) alvo +50 % ∨ trailing 20 % ∨ 5 min | −0,039 | −0,014 | +0,026 | +0,208 / 102 % | +0,026 | +0,054 |

Nenhum conjunto atinge top-3 < 50 % em nenhuma regra (o pooled dos 5 conjuntos atinge 40 % com alvo 2×/trailing 30 %, mas é a mesma moeda contada 4 vezes). `flow_v2/6` e `/8` preferem trailing 15 %, `/2` e `/5` preferem alvo 2×/trailing 30 % — com n = 25/31 contra 137/163 a diferença não é distinguível de ruído; o denominador comum é "trailing sempre armado".

## 4. Modo `hold` — o recorte pedido (≥ 10 min de série) e o de ≥ 2 min

Papel único, ≥ 10 min (n = 30, viés de sobrevivência): registrada × 1,25 % +0,106 (174 %); trailing 15 % +0,127 (122 %); alvo +50 % senão trailing 30 % +0,165 (58 %); tempo 15 min +0,399 (76 %, 11 censuradas); alvo +50 % ∨ trailing 20 % ∨ 5 min +0,185 (50 %). Nesse subconjunto o trailing 30 % **perde** (+0,044, 578 %) porque as censuradas ainda estavam subindo.

Papel único, ≥ 2 min (n = 168, fechamento forçado na última linha): registrada × 1,25 % +0,169 (171 %); alvo 2× ∨ trailing 30 % ∨ 15 min +0,581 (52 %); alvo 2× ∨ trailing 30 % ∨ 5 min +0,557 (55 %); alvo 2× senão trailing 30 % +0,489 (62 %); trailing 15 % +0,201 (108 %); tempo 5 min +0,001. Aqui o alvo 2×/trailing 30 % chega perto de 50 % — mas 78 das 168 são censuradas (a série acaba antes de a regra decidir).

## 5. As 12 posições reais (PnL a 0,05 SOL, taxas 1,25 %)

Modo `earlier` (n = 12): registrada −0,0741 (do banco) / −0,0585 (× 1,25 %); `line_broken` −0,042; trailing 15 % −0,046; trailing 30 % −0,058; alvo 2× senão trailing 30 % −0,058; **tempo 5 min −0,017** (5 melhoram, 0 pioram, p = 0,06); 1.ª venda do criador −0,075; alvo +30 % ∨ trailing 20 % ∨ 5 min −0,054.

Modo `hold ≥ 2 min` (n = 11; `63NPcW9q` sem série): registrada −0,056; **tempo 5 min +0,008** (991 % do top-3 = só o PS); `line_broken` +0,001; alvo 2× ∨ trailing 30 % ∨ 5 min −0,004; trailing 15 % −0,016; trailing 30 % −0,016; 1.ª venda do criador −0,072.

| mint | registrada | `line_broken` | trailing 15 % | tempo 5 min | 1.ª venda criador | alvo +30 % ∨ trail 20 % ∨ 5 min |
|---|---|---|---|---|---|---|
| 7s4dKmpv | −0,0093 (creator_dump, 48 s) | −0,0116 (cens. 214 s) | −0,0108 (119 s) | −0,0116 (cens.) | −0,0067 (55 s) | −0,0116 |
| 63NPcW9q | −0,0035 (creator_dump, 52 s) | sem série além de 46 s | | | −0,0012 (31 s) | |
| CCLstvwa | −0,0071 (trailing, 396 s) | −0,0117 (56 s) | −0,0101 (24 s) | **+0,0143** (314 s) | −0,0058 | −0,0117 (40 s) |
| 2hhJXPy3 | −0,0176 (time_stop, 1800 s) | −0,0166 (cens.) | −0,0104 (20 s) | −0,0148 (307 s) | −0,0166 | −0,0131 (52 s) |
| Dy9YAbcL | −0,0059 (creator_dump, 514 s) | **+0,0122** (204 s) | +0,0030 (338 s) | +0,0072 (306 s) | −0,0048 (465 s) | **+0,0139** (alvo, 93 s) |
| GdZ5hSdz | −0,0038 (creator_dump, 86 s) | −0,0030 | −0,0030 | −0,0030 | −0,0030 (96 s) | −0,0030 |
| 6zdT1MxC (PS) | **+0,0329** (creator_dump, 117 s) | **+0,0811** (383 s) | +0,0780 (cens. 417 s, ainda subindo) | +0,0621 (302 s) | +0,0186 (55 s) | +0,0157 (alvo, 39 s) |
| rYJYP8jV | −0,0040 (creator_dump, 45 s) | −0,0040 (124 s) | −0,0040 | −0,0040 | −0,0026 (42 s) | −0,0040 |
| M3kpWCVA | −0,0122 (time_stop, 1804 s) | −0,0074 (31 s) | −0,0089 (63 s) | −0,0040 (308 s) | −0,0110 | −0,0040 |
| 8DqtPVgJ | −0,0025 (creator_dump, 33 s) | +0,0015 (cens.) | −0,0103 (60 s) | +0,0015 (cens.) | −0,0011 (44 s) | +0,0015 |
| 4c3rRxkp | −0,0029 (time_stop, 1804 s) | −0,0014 (124 s) | −0,0014 | −0,0014 (315 s) | −0,0014 | −0,0014 |
| ADxEynfQ | −0,0383 (trailing, 43 s) | −0,0379 (cens.) | −0,0379 (52 s) | −0,0379 (132 s) | −0,0379 (132 s) | −0,0379 (52 s) |

O que a tabela diz: 7 de 12 saíram por `creator_dump` entre 33 s e 117 s — o criador vendeu logo depois da nossa compra; segurar depois disso não mudou nada em 5 delas (preço morto, −0,003 a −0,012) e teria dobrado o PS (+0,033 → +0,078). `ADxEynfQ` perdeu 0,038 em 43 s (−77 % de queda instantânea: nenhuma saída salva). O PS sob "primeira venda do criador" faria +0,019, sob alvo +30 % faria +0,016 — as regras "rápidas" cortam justamente o acidente que deu certo. O problema das reais está na **seleção** (moedas cujo criador despeja em 1 min, ou que caem 77 % em 43 s), não na saída.

## 6. Respostas

1. **Qual saída maximiza a soma com < 50 % do top-3?** Nenhuma, no recorte honesto (papel único, 215 apostas, sem censura): a melhor absoluta é **alvo 2× senão trailing 30 % sempre armado** (+0,37 SOL vs +0,11 da saída registrada às mesmas taxas, e −0,02 como registrado), com **76 %** do top-3. No recorte ≥ 2 min com censura, a mesma regra + tempo 15 min chega a 52 % (+0,58) — no limiar, mas com 78/168 censuradas. O componente que passa num teste pareado é o trailing 30 % sempre armado (26 × 3, p < 0,01, deltas difusos: 50 % do top-3 dos deltas); o alvo 2× só adiciona nas 3 grandes.
2. **A melhor saída muda com o conjunto de entrada?** Só dentro do ruído: `/2` e `/5` (n ≈ 150) preferem alvo 2×/trailing 30 %; `/6` e `/8` (n ≈ 30) preferem trailing 15 %; `operator/5` papel e real preferem tempo 5 min (n = 19/12). Em todos, `line_broken`, 1.ª venda do criador, tempo 2 min e alvos curtos (+25/+30 %) ficam abaixo de um trailing simples. A direção comum: trailing sempre armado > trailing armado só após 1,5× (o vivo).
3. **As 12 reais sob a melhor saída:** sob alvo 2×/trailing 30 % (a melhor do papel) −0,056 a −0,058 SOL (praticamente igual ao registrado −0,059 às mesmas taxas); sob tempo 5 min (a melhor das reais) −0,017 sem segurar além do registrado, ou +0,008 segurando (n = 11) — e esse +0,008 é PS sozinho (+0,062). Não existe saída que torne o lote real positivo de forma difusa.

## 7. Ressalvas

- **Censura:** a série pára quando a aposta fecha (fixação da T4.33) — 300 s de idade antes da noite de 16/09; o contrafactual "segurar mais" só existe nas apostas que seguraram (61 com ≥ 10 min, viés forte). O modo `earlier` resolve isso ao custo de nunca medir ganhos por segurar mais.
- **Fills de papel sem slippage; mcap teórico:** o motor de papel marca com "marca honesta" (cotação de venda integral com impacto) e 1,75 %; o replay usa mcap das reservas virtuais e 1,25 %. Por isso (a) e (a') diferem em +0,13 SOL; compare regras entre si dentro do mesmo modo, não contra o PnL do banco.
- **Antecipação na escolha da regra:** 27 regras × 6 conjuntos numa amostra de 2 dias; a melhor "absoluta" é garimpada. O único resultado que sobrevive ao pareado e a um teste do sinal é o trailing 30 % sempre armado; o alvo 2× depende de 8 apostas.
- `flow_v2/2` e `/5` são quase o mesmo conjunto (mesmos mints, mesmos minutos); o pooled de 5 conjuntos infla n e deprime a concentração artificialmente.
- Cadência: o papel julga cada foto (~12 s) e a série é de 15 s; `line_broken` no replay dispara em 53 das 118 saídas registradas por `line_broken` antes da saída registrada — aproximação, não reprodução.

## 8. Recomendação

Registrar um braço de papel com a única mudança "trailing 30 % sempre armado + alvo 2× + tempo 15 min" (EXP-M17, rascunho em `obsidian/05-EXPERIMENTS/EXP-M17-regra-de-saida.md`), controle = `flow_v2/2`, previsão ΔR médio ≈ +0,02 R/aposta e top-3 ainda > 50 %. **Não** mudar a saída do executor real por esta evidência (n = 12, tudo PS); os `ExitParams` exatos ficam no EXP para quando o braço de papel fechar. A pergunta que resta aberta é a da seleção: 7/12 reais com `creator_dump` em ≤ 2 min é o dado mais forte deste lote.
