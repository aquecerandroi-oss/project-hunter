# R82 — veredito formal da H-017 (recuo pequeno 3 %/60 s) com o controle do EXP-M25

Início: 2026-09-27 ~20:20Z. Notas incrementais. Só SELECT na VPS (`r82/q.sh` força `default_transaction_read_only=on`).

## 0. Lido antes (regra Obsidian primeiro)
- **Fila de Hipoteses, H-017** (congelada): previsão D ≥ +2 pp por SOL decidido contra comprar em `t0`, IC 95 % bootstrap
  por mint acima de zero, **e** melhor que "não comprar nada"; refutação: IC sup < +1 pp, **ou** não bate "nada", **ou**
  < 150 decisões resolvidas (limite de dado). Status `em curso`; veredito R79 = limite de dado (39 pares com op5).
- **EXP-M24** (protocolo congelado): 1.ª `entry_pullback_armed` por mint; `no_pullback`/`pullback_killed:*` = 0;
  censuradas/dropped/not_inserted/indeterminate/sem desfecho fora dos dois lados, contadas.
- **EXP-M25** (protocolo congelado): controle `recuo_ctrl_v1/1` na mesma `(mint, t0)` (`features_end_time = t0`), aposta
  `leg='single'`; métrica R79 §2.2 `r = pnl_sol ÷ entry.sol_spent`; controle ausente/`unfilled`/`indeterminate`/aberto
  fora e contado; julgamento o da H-017 com ≥ 150 pares resolvidos; descritivos por dia UTC e a parte de D de pares na
  mesma foto. Início da coorte 2026-09-26 15:05:30Z; md5 `recuo_v1/1` 0ba31bb6…, `recuo_ctrl_v1/1` 04a27c19….
- **KB-0157** (H-016 refutada): o pouco ganho do recuo é preço de entrada; não entrar custa as vencedoras que não recuam;
  o simulador do R77 era ~5,8 pp otimista contra o real.
- **notes-R79 §4**: ressalva de fidelidade — o papel preenche na 1.ª foto depois de `decided_at`; em 22 de 34 pares que
  entraram os dois lados preencheram na mesma foto (D = 0 por construção); D do R79 decompunha em mesma foto 0,000 /
  foto posterior +0,013 / não-entradas +0,020. Papel × real no op5 (n 38) +0,002 [−0,087, +0,086].

## 1. Dados e verificação da coorte (antes de qualquer desfecho)
- **Assinaturas na VPS (2026-09-27 20:26Z, `r82/q_md5.sql`):** `recuo_v1/1` **0ba31bb6f939638f5d73642350cbd6dd**,
  `recuo_ctrl_v1/1` **04a27c1907160419c756dd306bf9d6d8** — iguais às registradas no deploy. `meme_rule_set_param_history`:
  0 linhas para os dois conjuntos; `audit_logs` com `entity_id` dos dois: 0 linhas (`r82/q_audit.sql`). **Nenhuma
  edição desde o deploy → a coorte não foi cortada.** Os dois `active`, `research_only`.
- Trilha retida (`r82/q_count.sql`): `recuo_v1/1` 14 139 linhas (24/09 03:43Z → 27/09 20:26Z, 394 armações no total),
  `recuo_ctrl_v1/1` 4 446 linhas (26/09 15:08Z → …). **Cópia integral** em `r82/cache/trail.csv` (poda de 7 d).
- Extração `r82/q_h017.sql` → `r82/cache/h017.csv` (20:28:29Z; cópia `h017_2026-09-27T2028Z_147pares.csv`).
- **Contagem cega** (`r82/count_blind.py` → `count_blind.txt`, sem PnL): 150 armações (1.ª por mint, 26/09 15:10:24Z →
  27/09 20:08:19Z), 0 rearmações, 0 mints com armação anterior ao início. Braço: entrou 123, `pullback_killed` 15,
  `no_pullback` 11, `indeterminate` 1, censuradas 0. Controle: resolvido 147, ausente 2 (BossAssHat e TELE — o controle
  já tinha entrado no mint pela pista de 15 s, `meme_features_15s_v1`, antes de `t0`: a falta prevista em "Como o par
  nasce"), `indeterminate` 1 (o mesmo mint do braço `indeterminate`). **Pares resolvidos: 147 < 150** — os "150" do
  pedido eram as armações. Controle: 148 propostas, todas `decided_by = rules`, pista `meme_event_gate_v1`, **0**
  posições reais. `operator/5` na mesma decisão: `expired` 135, `rejected` 13, sem proposta 2 — **nenhuma sombra
  do op5** nesta coorte (a mesa real não aceitou nada); o descritivo com o op5 fica vazio.
- **Regra de parada (congelada aqui, antes de qualquer desfecho):** 147 < 150 → esperar. A população do veredito é a
  da **primeira extração em que os pares resolvidos (t0 ≤ extração − 15 min) chegam a 150** (`r82/poll.sh`, a cada 5 min,
  sem imprimir PnL). Nenhum desfecho foi lido antes disso.

## 2. Desenho (congelado ANTES de calcular desfechos)
- **População:** 1.ª `entry_pullback_armed` de `recuo_v1/1` por mint com `t0 ≥ 2026-09-26 15:05:30Z` e
  `t0 ≤ extração − 15 min` (janela 60 s + `max_hold` 300 s + fill + folga; mais novas = "em voo", contadas).
- **Braço:** aposta resolvida → `r_a = pnl_sol ÷ entry.sol_spent`; sem aposta, 1.º desfecho do recuo na trilha depois
  de `t0`: `no_pullback`/`pullback_killed:*` → 0; `pullback_censored:*`/dropped/not_inserted/insert_* → fora; aposta
  `indeterminate`/aberta, proposta sem aposta, sem desfecho → fora.
- **Controle:** proposta de `recuo_ctrl_v1/1` em `(mint, features_end_time = t0)`, aposta `single` fechada, `pnl` não
  nulo, não `indeterminate` → `r_c = pnl_sol ÷ entry.sol_spent`; senão fora (ausente — com o motivo `already_open` quando
  a 1.ª proposta do controle no mint é anterior a `t0` —, `unfilled`, `indeterminate`, aberta).
- **(a) D = média(r_a − r_c)** nos pares; **IC 95 % bootstrap por mint, 10 000, semente 82**, pelo moinho
  (`infra.research.resampling.cluster_bootstrap` com as linhas do braço e do controle empilhadas e cluster = mint —
  uma decisão por mint, logo é o bootstrap emparelhado), conferido por um bootstrap numpy direto. p descritivo por
  troca de sinal: `permutation_p` do moinho com estrato = mint (trocar o rótulo dentro do mint = trocar o sinal de D).
- **(b) braço contra "não comprar nada":** média de `r_a` nos mesmos pares, IC pelo mesmo bootstrap (braço × zeros por
  mint). Descritivo: o mesmo em todas as decisões resolvidas do braço (sem exigir controle).
- **Rótulo (texto da H-017, sem mudança; ordem):**
  1. pares < 150 → LIMITE DE DADO;
  2. IC sup de D < +0,01 → **REFUTA (a)**;
  3. IC sup de `r_a` < 0 → **REFUTA (b)** (evidência de que o braço perde para "nada");
  4. D ≥ +0,02 **e** IC inf de D > 0 **e** IC inf de `r_a` > 0 → **CONFIRMA**;
  5. "não bate nada" lido **literalmente** pela estimativa (média `r_a` ≤ 0, ou IC de `r_a` contendo zero) sem
     evidência (IC sup ≥ 0) → reportado como "cláusula (b) literal dispara"; pela errata do R76 (a imprecisão nunca
     vira refutação, adotada em R79/R80/R81), sozinha → **NÃO CONFIRMA**;
  6. resto → NÃO CONFIRMA.
- **Descritivos (sem peso no rótulo):** por dia UTC; bootstrap por blocos de 6 h (moinho, `block_bootstrap`); sem o par
  de maior |D|; a sombra do op5 (vazia nesta coorte).
- **Decomposição de D (como o R79):** Σ(r_a − r_c) ÷ n por grupo — `mesma_foto` (entrou e a foto de fill do braço é a do
  controle: mesmo `entry.snapshot.observed_at` **e** mesmas reservas virtuais; mais estrito que o `entry_at` do R79),
  `foto_posterior` (entrou em outra foto), `nao_entrou` (`no_pullback` e `killed` separados).
- **Ressalva do papel quantificada:** (i) fração dos pares que entraram na mesma foto; (ii) atrasos: gatilho − `t0`
  (`trigger_at`), fill do controle − `t0`, fill do braço − gatilho; (iii) o preço que o papel **não viu**: nos pares de
  mesma foto, `p_fill_controle ÷ trigger_price − 1` (a melhora de preço no gatilho que o fill apagou); (iv) limite
  superior de 1.ª ordem: D se esses pares tivessem entrado ao preço do gatilho e saído ao mesmo preço
  (`r_a' = (1 + r_c)·p_c/p_gat − 1`), declarado otimista (a saída real é relativa à entrada) e **sem peso no rótulo**.
- **Verificação do mecanismo:** EXP-M24 item 1 (`trigger_price ≤ armed_max_price × 0,97` em todos os blocos);
  EXP-M25 itens 1–3 em toda a coorte (par em `t0`, `decided_by = rules`, 0 posições reais, md5).
- **Papel × real:** esta coorte não tem op5 real na mesma decisão (0 aceitas) → não mensurável aqui; cita-se R79
  (+0,002 [−0,087, +0,086], n 38) e o otimismo do simulador do R77 (~5,8 pp), sem número novo inventado.

### 2.1 Astra (desenho, `.claude/state/astra-review-R82-design.md`, antes de qualquer desfecho)
- **Concorda** com a ordem do rótulo (1–6) como operacionalização explícita da cláusula ambígua "não bate nada"
  ("não demonstrar superioridade não demonstra inferioridade"); pede que a avaliação diga que aqui se **aplica o
  princípio** da errata do R76, não uma definição que já estava na letra da H-017. Aceito.
- **Parada:** aceitável (conta pares sem olhar retorno); entram **todos** os pares elegíveis da extração que cruzar 150,
  nunca "exatamente 150". Ressalva: exigir resolução pode sub-representar apostas problemáticas que ficam abertas ou
  `indeterminate` → publicar os excluídos com motivo e idade. Aceito (o script lista-os).
- Bootstrap empilhado = bootstrap emparelhado: correto. p de troca de sinal: correto algebricamente, mas exige
  permutabilidade/simetria que dois braços não aleatorizados não garantem → **descritivo**. Aceito (já era).
- "Mesma foto" por `observed_at` + reservas: melhor, mas incremental (`entry_at = snapshot.observed_at` no motor);
  conferir também que fills e retornos são iguais. Aceito (o script confere e lista as exceções).
- **MUST-FIX aceito:** `(1 + r_c)·p_c/p_gat − 1` **não é limite superior** — uma entrada mais barata pode bater o alvo
  antes de uma queda (render mais) ou sair por trailing antes de uma recuperação (render menos). Renomeado para
  **sensibilidade com saída fixada** (`fixed_exit_counterfactual`), descritiva, com preços **marginais** dos dois lados
  (`marginal_price_before_sol` do fill do controle × `trigger_price` = reservas virtuais após o trade do gatilho).
- Nice-to-have aceitos: guarda de rearmação/mint repetido na extração final; `foto_desconhecida` separada de
  `foto_posterior`; número de blocos de 6 h publicado. Enquadramento: "veredito da H-017 **no papel**, com o controle
  do EXP-M25, entre pares avaliáveis" — a população não equivale às decisões aceitas pela mesa real.
- Testes: `r82/test_r82.py` 19/19 (classes, população cega ao desfecho, pares, mesma foto/desconhecida, bootstrap do
  moinho = numpy direto, braço × nada, troca de sinal, ordem do rótulo, decomposição soma D, sensibilidade).
- **Declaração:** para testar o script rodei-o numa cópia com PnL **aleatório** (`smoke_scramble.py`; cópia apagada).
  Essa corrida imprimiu campos reais que não são PnL — contagem de motivos de saída, 73 entradas na mesma foto, preços
  de gatilho/fill. O desenho e a regra de parada (por contagem) já estavam congelados; nada disso pode mudar o rótulo.

## 3. Parada (regra do §1)
- `r82/poll.log`: 147 (20:30Z) … 148 (20:55Z) · 149 (21:01Z) · **151 às 21:26:27Z** → população do veredito = essa extração,
  **todos os 151 pares** (não "150"). Cópia `r82/cache/h017_2026-09-27T2126Z_151pares.csv`; trilha reexportada na mesma
  hora (`r82/cache/trail.csv`, 19 190 linhas: `recuo_v1/1` desde 24/09 03:43Z, `recuo_ctrl_v1/1` desde 26/09 15:08Z).
- md5 conferidos de novo às 21:26:46Z: iguais (0ba31bb6… · 04a27c19…); param_history e audit_logs: 0 linhas. Coorte inteira.
- Contagem cega final (`r82/count_blind.txt`): 155 armações (1.ª por mint), 154 na população, 1 em voo; 0 rearmações.
  Braço: entrou 125, killed 17, no_pullback 11, indeterminate 1. Controle: resolvido 151, ausente 2 (`already_open` pela
  pista de 15 s: BossAssHat, TELE), indeterminate 1 (PROFIT, o mesmo mint do braço indeterminate).
  Fora dos dois lados (idade na extração 21,6–29,8 h, nenhum "em voo"): BossAssHat (braço killed / controle ausente),
  PROFIT (indeterminate/indeterminate), TELE (braço entrou / controle ausente).

## 4. Resultados (saída integral `r82/h017.txt`; pares um a um `r82/pairs.csv`; testes `r82/test_r82.py` 20/20)
- **(a) D = braço − controle = +0,0077 [−0,0269, +0,0410]** por SOL decidido (n 151; bootstrap por mint 10 000, moinho;
  numpy direto [−0,0267, +0,0410]); p troca de sinal 0,67 (descritivo). Melhor 47, pior 30, **igual 74**.
- **(b) braço contra "nada": −0,0385 [−0,0775, +0,0022]**; controle contra "nada": −0,0462 [−0,0914, +0,0015].
  Σ SOL braço −0,4066 × controle −0,4883 (0,07 SOL por decisão).
- **Rótulo pela regra congelada: NÃO CONFIRMA.** Cláusula a cláusula: n 151 ≥ 150 (não é limite de dado); IC sup de D
  +0,041 ≥ +0,01 → (a) **não** dispara; IC sup do braço +0,0022 ≥ 0 → (b) com evidência **não** dispara (por 0,22 pp);
  D +0,77 pp < +2 pp e IC inf < 0 → não confirma; **(b) literal dispara** (média do braço −3,85 %, não bate "nada") —
  pelo princípio da errata do R76, aplicado aqui por operacionalização declarada antes dos desfechos (§2, Astra de
  acordo), sozinha não refuta.
- Por dia UTC: 26/09 (n 68) D +0,0000 [−0,056, +0,052], braço −0,021; 27/09 (n 83) D +0,0141 [−0,031, +0,055], braço
  −0,053. Blocos de 6 h (6 blocos): D +0,0077 [−0,0272, +0,0380]. Sem o maior |D| (BULA-KUN: braço morto por
  `creator_sold_during_wait` 0,86 s depois de `t0`, controle **+102,5 %** no alvo): D +0,0146 [−0,0172, +0,0460], braço
  −0,0387 [−0,077, +0,002]. D aparado 5 %/cauda +0,0135; mediana de D 0,0000.
- **Decomposição** (soma = D): mesma foto (74) **+0,0000** (retorno idêntico em 74/74, preço médio de fill idêntico
  74/74; critério do R79 `entry_at` dá os mesmos 74); foto posterior (50) **−0,0014** (média no grupo −0,004; D só nesses
  −0,0043 [−0,084, +0,070]); `pullback_killed` (16) **+0,0106** (controle −0,0997 nesses; 2 de 16 ganharam); `no_pullback`
  (11) **−0,0014** (controle +0,019; 5 de 11 ganharam). Sem os pares de mesma foto (n 77): D +0,0152 [−0,052, +0,081].
  **A contribuição positiva líquida de D vem das mortes na rechecagem (`killed`); as entradas não contribuíram
  positivamente nesta amostra** (contabilidade da amostra, não separação causal de preço, momento e saída — Astra).
- **Ressalva do papel quantificada:** 74 de 124 entradas (59,7 %) na mesma foto do controle (R79: 22/34 = 64,7 %).
  Gatilho − t0: p10 0,5 · p50 5,2 · p90 23,6 s; foto de fill do controle − t0: p10 1,0 · p50 6,3 · p90 14,4 s; foto do
  braço − gatilho: p50 6,0 s. **Nos 74 de mesma foto, o preço marginal da foto de fill ficou em média 1,98 % abaixo do
  gatilho** (fill ÷ gatilho − 1, denominador = gatilho: média −0,0198, mediana −0,01; a média do quociente inverso é
  +9,2 % — médias de razões não se invertem): o preço em geral seguiu caindo depois do gatilho. **No agregado, o papel
  não escondeu uma melhora de preço nesses pares**; mas em **30 de 74** o gatilho era mais barato que o fill — ali houve
  melhora apagada. Nas 50 de foto posterior, o controle pagou em média 6,8 % a mais que o braço (preço marginal,
  mediana 4 %), e isso não virou retorno (D −0,004 no grupo). Gatilho ÷ t0: mediana 0,98, acima de t0 em 53 de 124 (subiu e recuou 3 % da nova máxima).
  Mecanismo EXP-M24 item 1: 124 blocos, **0** com `trigger_price > armed_max × 0,97`.
- **Sensibilidades com saída fixada (aproximação proporcional: escala `1 + r` pela razão de preços marginais; não é
  execução simulada nem limite — o motor calcula quantidade, impacto e taxas; descritivas, adicionais ao desenho):**
  (i) mesma foto ao preço marginal do gatilho: D +0,0008 [−0,047, +0,053], braço −0,045; (ii) **parcial, preço de
  decisão**: nas 124 entradas braço no gatilho e controle em `t0` (preço de `t0` ÷ gatilho − 1: média −0,022, mediana
  +0,02); **as 27 não-entradas ficam como observadas** (sem proposta do braço não há `t0_price` no bloco):
  D −0,0237 [−0,060, +0,010], braço −0,0627 [−0,114, −0,004]. Nenhuma das duas substitui o julgamento primário; e
  "nenhuma leitura dá +2 pp" **não** é exclusão estatística — o IC primário vai a +4,10 pp e o de (i) a +5,28 pp.
- **Mecanismo do controle (EXP-M25 itens 1–3, toda a coorte):** par em `t0` em 152 de 154 (2 ausências
  `already_open`, previstas); 152 `decided_by = rules`; **0** posições reais; md5 iguais.
- **Papel × real:** op5 na mesma decisão `expired` 139, `rejected` 13, sem proposta 2 → **nenhuma sombra nem posição
  real** nesta coorte; não mensurável aqui. Fica a do R79 (+0,002 [−0,087, +0,086], n 38) e o otimismo do simulador do
  R77 (~5,8 pp). A leitura de nível (−3,85 %) é de papel.
- Descritivo, braço em todas as decisões resolvidas (n 153, sem exigir controle): −0,0378 [−0,0751, +0,0018].

## 5. Astra (veredito, `.claude/state/astra-review-R82-verdict.md`)
- **Concorda com "H-017 concluída — NÃO CONFIRMA", no papel, entre os pares avaliáveis do EXP-M25**; conferiu a regra
  cláusula a cláusula (n 151; IC sup de D +4,10 pp ≥ +1; IC sup do braço +0,22 pp ≥ 0; D +0,77 pp e os dois IC com
  zero; (b) literal dispara e sozinha dá NÃO CONFIRMA) e pede que se diga que é a **operacionalização declarada no
  R82** (princípio da errata do R76), não uma definição que já estava na letra da H-017. Recalculou do CSV os quocientes
  dos 74 pares de mesma foto (−1,98 % e +9,21 %).
- **Must-fix aceitos (os três são de redação; nenhum número mudou):** (1) "gatilho 2 % mais caro" → "o preço marginal
  da foto ficou 1,98 % abaixo do gatilho, com o gatilho no denominador"; (2) a sensibilidade de preço de decisão é
  **parcial** (27 não-entradas não reprecificadas) — renomeada no código (`decision_price_sensitivity`, teste com uma
  não-entrada, 20/20) e no texto; (3) "não vem do preço" → "as entradas não contribuíram positivamente para D nesta
  amostra"; "o papel não escondeu melhora" restrito ao agregado (30 de 74 gatilhos eram mais baratos que o fill);
  "nenhuma leitura dá +2 pp" não é exclusão estatística.
- **Aposentadoria:** pode-se **recomendar** ao orquestrador encerrar `recuo_v1/1` e `recuo_ctrl_v1/1` preservando os
  resultados; é decisão operacional dele; NÃO CONFIRMA não é prova de ausência de efeito nem autoriza escrever REFUTA.
- Nada rejeitado.

## 6. Vereditos e entregáveis
- **H-017: concluída — NÃO CONFIRMA** (fila `status: concluída` + `veredito`; `test_queue_and_report.py`).
- KB `obsidian/11-KNOWLEDGE/KB-0162-o-recuo-pequeno-empata-com-comprar-na-hora.md`; avaliações datadas acrescentadas em
  EXP-M24 e EXP-M25; `Mapa de Estrategias.md` (H-017 sai de Vivas e Pistas para o Cemitério, `nao_confirma`); síntese
  da Astra em `obsidian/06-DECISIONS/Revisoes-Astra/R82-recuo-controle.md` + Index.
- **Recomendação ao orquestrador (não executada):** os braços `recuo_v1/1` e `recuo_ctrl_v1/1` podem ser aposentados.
  Nenhum conjunto foi ativado/desativado aqui.
- Só SELECT na VPS; nenhum `.env`, nenhuma chave, nenhum commit, nenhuma ordem, nenhum parâmetro mudado.
