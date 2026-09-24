# R77 — H-016, entrar no recuo e não no pico

**Pedido:** coordenador, 23/09/2026 ~22 h BRT, para testar a H-016 da fila (pré-registada ~22:10 BRT,
**congelada**; aqui só se preenche `status`/`veredito`).
**Método:** VPS só leitura (`q.sh` força `default_transaction_read_only=on`; só `SELECT`/`COPY TO STDOUT`).
Simulador do R72 (`r72/sim.py`: `simulate_current`, `per_sol`, `gross_buy_tokens`, `_fill_index`) **sem
alteração**; o que é novo é a cadeia de reservas "sem nós" a partir de `t0` e a regra de entrada.

## Resposta curta

**H-016: `REFUTA`, pelas cláusulas (a) e (b), nas duas populações.** Esperar um recuo antes de comprar
**não** entrega os +5 pp por SOL decidido que a hipótese previa. As cláusulas (c) (morrer a 5 s) e (d)
(ganhar só por não entrar) **não** disparam.

- **Reais (n = 65):** a melhor célula é X = 3 %, W = 60 s, com D = **+1,99 pp** e IC 95 % **[−3,60, +7,48]**
  (p = 0,50). Nenhuma célula tem IC inferior acima de +1 pp, e a melhor está na borda da grade. A amostra não
  distingue piora, zero ou melhora relevante: **+5 pp não fica excluído**.
- **Papel (n = 486):** a mesma célula dá D = **+2,28 pp**, IC **[+0,69, +3,89]**, p = 0,0065, Holm 0,052. O IC
  inferior fica abaixo de +1 pp e a célula está na borda. **+5 pp fica fora do IC** na análise principal (no
  horizonte fixo de 370 s o IC vai a +5,38; ver §6). Contra "não comprar nada", o nível fica em **+0,08 %**
  [−1,70, +1,87]: a política empata com ficar de fora, não dá lucro.
- **De onde vem o pouco que existe:** do **preço melhor nas entradas** (+2,18 pp dos +2,28 no papel), não de
  ficar de fora. Não entrar **custa** em quase todas as células, porque as moedas que não recuam são, em
  desproporção, as vencedoras. Com X = 12 % e W = 20 s perdem-se **25 das 30** vitórias do controlo nas reais
  e **146 das 181** no papel.
- **As perdas que "caem desde a compra" não somem.** Nas reais, a melhor célula tem as **mesmas 16** perdas
  que nunca passaram do custo (de 65 decisões) que o controlo. A fração entre as perdas **sobe** de 0,46 para
  0,62 porque as outras perdas diminuem. Quem compra no recuo apanha a queda que continua tão
  frequentemente quanto quem compra no pico. Das 21 perdas históricas deste tipo que estão na população, a
  melhor célula evita 5, vira 6 em ganho, melhora 6 e deixa 4 iguais ou piores.
- **Pista de eventos (descritivo, o que opera hoje):** o mesmo sentido, também sem IC acima de zero. Reais,
  n = 53: X = 3 %, W = 60 s dá +3,70 pp [−2,70, +10,14]. Papel, n = 162: +3,04 pp [−0,15, +6,08].
- **Para a mesa:** não mudar a entrada. O modelo é otimista em relação à execução real. Nas mesmas 65
  posições, o controlo simulado rende +0,41 %; a realidade rendeu −5,42 %, dos quais cerca de 2,8 pp vêm do
  aluguel da ATA e cerca de 3,2 pp das saídas históricas e da execução (§3). Um ganho relativo de ~2 pp que
  não chega ao lucro nem no modelo não paga a mudança. **Nenhum braço de papel é proposto.**

## 1. Desenho congelado ANTES de simular qualquer célula

Escrito às 22:1x BRT de 23/09, antes da primeira simulação. Mudanças posteriores vão na §9 com motivo.

### 1.1 População
- **Reais:** as 96 posições fechadas (−0,3993 SOL; todas da porta `fluxo_e_holders`: 81 da pista de
  eventos, 15 da de 15 s), **uma por mint, a primeira por `proposed_at`** → 85 decisões.
- **Papel:** apostas `leg = single` fechadas da porta `fluxo_e_holders/*`, `proposed_at` até 10 min antes do
  corte, uma por mint (a primeira) → 596 decisões. **Populações separadas** (um mint pode estar nas duas).
- **Recorte descritivo:** só decisões com `reasons[0].series = meme_event_gate_v1` (o que a mesa usa hoje).
- Corte dos dados: 24/09/2026 01:07 UTC (`pop.csv`, `cache/tape.csv.gz`, `cache/snap.csv.gz`).

### 1.2 Instante da decisão `t0`
`t0 = meme_proposals.proposed_at`. Na pista de eventos é igual a `features_end_time` (mediana 0 s). Na de
15 s, `proposed_at ≈ features_end_time + 11–15 s`: usar `features_end_time` punha a compra do controlo
antes de a proposta existir. Papel: o mesmo `proposed_at` da proposta da aposta (o `entry_at` do papel é
`t0 + 6,5–8 s` de atraso simulado de fill do papel; não é usado).

### 1.3 A cadeia "sem nós" (o preço que a regra de entrada vê)
- Âncora: a última foto `solana_rpc` (tem `slot`) com `observed_at ≤ t0`, até 3 min antes. Sem âncora → censura `sem_ancora`.
- Para a frente: trocas da fita com `trader ≠ nossa carteira` e `slot >` âncora, aplicadas às reservas
  virtuais (compra soma SOL e tira tokens; venda o inverso — o modelo do R72); fotos com `slot ≥` último
  aplicado ressincronizam, **descontado o efeito acumulado das nossas próprias trocas** até ao slot da foto
  (a foto real inclui a nossa compra; o contrafactual não). Ordem por `(slot, troca antes de foto, tempo)`;
  carimbo monótono (herdado do R72).
- **Suposição declarada:** a mesa vê a fita **WS** ao vivo; cada estado é observado no seu `block_time`.
  O atraso ~44 s do arquivo por polling (R73) é ressalva de observabilidade, não entrada da simulação.

### 1.4 Regra de entrada da célula (X, W)
- Preço = `vsol / vtok` da cadeia. Máxima corrente `M` = preço do estado em `t0` (último ponto `≤ t0`),
  atualizada por cada ponto com `t ∈ (t0, t0 + W]`.
- Gatilho = o primeiro ponto com `t ∈ (t0, t0 + W]` e preço `≤ M · (1 − X)`. Pontos de foto também podem
  disparar (a fita WS teria visto as trocas que a foto resume) — conta-se quantos.
- Sem gatilho até `t0 + W` → **não entra**, retorno 0.
- Grade: `X ∈ {3, 5, 8, 12} %`, `W ∈ {20, 60} s` (8 células). Controlo = gatilho em `t0`.

### 1.5 Pouso, custo, saída (iguais nos dois braços)
- Pouso = gatilho + `L`, `L = 1,6 s`; o fill usa o último estado da cadeia com `t ≤` pouso (`sim._fill_index`).
- Compra de `S` = tamanho nominal da decisão (`params.size_sol`, 0,05–0,07); a curva recebe `S·(1 − c/2)`,
  tokens por produto constante (`sim.gross_buy_tokens`); `c = 2,23 %` ida e volta.
- Caminho da posição = cadeia + a nossa compra (reservas somadas), marca `sell_net` do R72.
- Saída = `sim.simulate_current` **inalterado** (1,15× · recuo 10 % armado na entrada · 300 s contados do
  pouso novo), com `latency_s = L`; retorno = `sim.per_sol`.
- **Sensibilidade 5 s:** `L = 5 s` em **todas** as pernas dos **dois** braços, mesma população.
- O controlo também é simulado (não é o fill real), para o contraste ser emparelhado no mesmo modelo.
  Fidelidade publicada: controlo simulado × PnL real por SOL das mesmas posições.

### 1.6 Elegibilidade (igual para todas as células)
Uma decisão entra se: há âncora; ≥ 3 trocas da fita (não nossas) em `(t0, t0 + 300 s]` (critério do
R72); e o maior buraco da cadeia entre `t0` e o **último pouso de saída entre os 9 braços** (a 1,6 s) é
`≤ 60 s`. Censurada sai de todas as células (a população não muda entre células nem a 5 s).

### 1.7 Estatística
- Por célula: `D_i = r_política,i − r_controlo,i` (0 para quem não entrou), média por SOL decidido.
- Moinho `infra/research`: `run_hypothesis` com linhas empilhadas (2 por decisão: braço 1 = política, 0 =
  controlo; variável = braço; `cluster = mint` → bootstrap de mint 10 000 emparelhado; `stratum = mint` →
  a permutação dentro do mint é a troca de sinal do par). O `D` do moinho é exatamente a média de `D_i`.
- Holm sobre as 8 células, por população. D contra "não comprar nada" (retorno 0) pelo mesmo caminho.
- O veredito do moinho é impresso mas **não decide**: a curva de limiares dele é sobre a variável
  (degenerada aqui); o patamar da H-016 é em `X`.

### 1.8 Regra de decisão (congelada)
Por população, "melhor célula" = maior D a 1,6 s (empate → interior em X).
- **CONFIRMA** se existe uma célula com `D ≥ +0,05`, IC inferior `> 0` e um vizinho em X (mesmo W) com
  `D > 0`; e, nas reais, a fração das perdas que nunca passaram do custo cai.
- **REFUTA** (tem precedência) se: (a) nenhuma célula com IC inferior `> +0,01`; **ou** (b) a melhor célula
  está na borda em X (`X ∈ {3, 12}`; W tem só dois valores e não define borda); **ou** (c) o D da melhor
  célula a 5 s fica `≤ 0`; **ou** (d) a melhor célula não bate "não comprar nada": média do retorno por SOL
  decidido `≤ 0`.
- **NÃO CONFIRMA** nos restantes casos.
- Hipótese inteira: CONFIRMA só se as duas populações confirmam; REFUTA se as duas refutam; senão NÃO
  CONFIRMA com o rótulo de cada população escrito.

### 1.9 Descritivo (fora do veredito)
Por célula: n entradas; nível médio por SOL das entradas; vitórias do controlo perdidas por não entrar
(n e SOL); nas reais, das 34 perdas que nunca passaram do custo (`high_water_sol ≤ gasto`, as 96 reais) as
que estão na população: evitadas (não entrou), viradas (retorno > 0), melhoradas, ainda perda; perdas ≥ 50 %
criadas/evitadas.

## 2. População e cobertura (saída real de `r77/report.txt`)

| | reais | papel |
|---|---:|---:|
| decisões (uma por mint, a primeira por `proposed_at`) | 85 | 596 |
| menos de 3 trocas em `(t0, t0 + 300 s]` | 16 | 58 |
| buraco > 60 s até à saída em algum braço (emenda 9) | 4 | 52 |
| **elegíveis** | **65** | **486** |
| só pista de eventos (descritivo) | 53 | 162 |
| sensibilidade: horizonte fixo 370 s | 34 | 200 |

- A nossa compra **não estava no arquivo** em 19 das 85 decisões reais. Onde o nosso fill está na fita, ele
  bate ao lamport com `meme_live_positions.entry/exit` (144 de 144 pernas: SOL, tokens e slot). Por isso as
  pernas em falta foram **injetadas a partir desse registo** (30 decisões afetadas). O efeito ficou na 4.ª
  casa decimal (`report_v0.txt` × `report.txt`) e nenhum rótulo mudou.
- Nenhuma decisão elegível caiu por `ok=False` do simulador na linha principal.

## 3. Fidelidade do controlo simulado (`r77/fidelity.txt`, as 65 reais)

```
n = 65 (de 65 elegíveis; R72 não resolveu 0)
  PnL real por SOL (gasto total, saída histórica)                média -0.0542  mediana -0.0804
  R72 no fill real, gasto total com aluguel (saída congelada)    média -0.0225  mediana -0.0810
  R72 no fill real, gasto sem aluguel de ATA (saída congelada)   média +0.0052  mediana -0.0493
  controlo R77 (compra modelada em t0 + 1,6 s)                   média +0.0041  mediana -0.0257
  correlação R72-sem-aluguel × controlo R77: 0.90
  controlo R77 − R72 sem aluguel: média -0.0011, mediana +0.0022
  atraso fill real − t0 (s): mediana 0.1, min -0.9, max 7.6
  posições com saída histórica diferente da congelada (alvo ≠ 1,15 ou recuo ≠ 10 %): 12
```

Leitura:
- A cadeia "sem nós" com compra modelada **reproduz o simulador do R72 no fill real**: diferença média −0,11 pp,
  correlação 0,90.
- A distância para o PnL realizado (−5,42 %) **não vem do modelo de entrada**. Vem do aluguel de ATA (≈ 2,8 pp)
  e de saídas históricas e execução (≈ 3,2 pp; 12 posições tinham alvo ou recuo diferentes dos congelados).
- **O nível absoluto do modelo é otimista em relação à mesa.** O contraste emparelhado sofre menos com isso,
  porque os dois braços partilham o modelo.
- Casos isolados mostram quanto um segundo pesa (KB-0149 §17): o LVL dá −66 pp no controlo modelado e o fill
  real, 0,8 s antes, escapou.

## 4. Contraste principal (1,6 s, custo 2,23 %) — saída real

**Reais, n = 65** (controlo: +0,41 % por SOL a 1,6 s, +0,70 % a 5 s; 30 vitórias)

```
  | X | W | entradas | D vs controlo [IC 95 %] p | Holm | D a 5 s [IC] | vs nada [IC] | moinho |
  | 3 % | 20 s | 38 | +0.0061 [-0.0443, +0.0564] p=0.8178 | 1.000 | -0.0009 [-0.0577, +0.0538] | +0.0101 [-0.0207, +0.0414] | NÃO CONFIRMA |
  | 5 % | 20 s | 30 | -0.0100 [-0.0580, +0.0385] p=0.6929 | 1.000 | -0.0178 [-0.0771, +0.0400] | -0.0060 [-0.0307, +0.0193] | REFUTA |
  | 8 % | 20 s | 25 | -0.0140 [-0.0725, +0.0423] p=0.6433 | 1.000 | -0.0239 [-0.0840, +0.0359] | -0.0100 [-0.0465, +0.0208] | REFUTA |
  | 12 % | 20 s | 20 | -0.0210 [-0.0798, +0.0351] p=0.4857 | 1.000 | -0.0337 [-0.0943, +0.0256] | -0.0170 [-0.0515, +0.0118] | REFUTA |
  | 3 % | 60 s | 55 | +0.0199 [-0.0360, +0.0748] p=0.4997 | 1.000 | +0.0111 [-0.0519, +0.0712] | +0.0239 [-0.0187, +0.0666] | NÃO CONFIRMA |
  | 5 % | 60 s | 50 | +0.0088 [-0.0467, +0.0636] p=0.7615 | 1.000 | +0.0005 [-0.0654, +0.0640] | +0.0129 [-0.0263, +0.0525] | NÃO CONFIRMA |
  | 8 % | 60 s | 42 | +0.0032 [-0.0603, +0.0652] p=0.9231 | 1.000 | -0.0068 [-0.0744, +0.0613] | +0.0073 [-0.0364, +0.0475] | NÃO CONFIRMA |
  | 12 % | 60 s | 34 | -0.0170 [-0.0818, +0.0474] p=0.6116 | 1.000 | -0.0251 [-0.0936, +0.0450] | -0.0130 [-0.0539, +0.0252] | REFUTA |
  **Veredito (real): REFUTA**
    - (a) nenhuma célula com IC inferior > +0,01 (maior = -0.0360)
    - (b) melhor célula X=3% W=60s (D +0.0199) na borda em X
    - melhor célula X=3% W=60s: D +0.0199 (IC inf -0.0360), 5 s +0.0111, nível +0.0239
    melhor célula X=3 % W=60 s; impressão digital do pré-registo no moinho: 6e1f8c113bfe
```

**Papel, n = 486** (controlo: −2,21 % por SOL a 1,6 s, −1,83 % a 5 s; 181 vitórias)

```
  | X | W | entradas | D vs controlo [IC 95 %] p | Holm | D a 5 s [IC] | vs nada [IC] | moinho |
  | 3 % | 20 s | 359 | +0.0199 [+0.0034, +0.0367] p=0.0200 | 0.140 | +0.0111 [-0.0083, +0.0301] | -0.0022 [-0.0167, +0.0124] | REFUTA |
  | 5 % | 20 s | 312 | +0.0193 [+0.0007, +0.0383] p=0.0473 | 0.284 | +0.0127 [-0.0089, +0.0338] | -0.0027 [-0.0163, +0.0108] | REFUTA |
  | 8 % | 20 s | 263 | +0.0147 [-0.0057, +0.0352] p=0.1571 | 0.628 | +0.0106 [-0.0117, +0.0327] | -0.0074 [-0.0200, +0.0052] | REFUTA |
  | 12 % | 20 s | 185 | +0.0106 [-0.0101, +0.0312] p=0.3162 | 0.947 | +0.0121 [-0.0110, +0.0353] | -0.0115 [-0.0225, -0.0011] | REFUTA |
  | 3 % | 60 s | 446 | +0.0228 [+0.0069, +0.0389] p=0.0065 | 0.052 | +0.0151 [-0.0024, +0.0325] | +0.0008 [-0.0170, +0.0187] | REFUTA |
  | 5 % | 60 s | 417 | +0.0153 [-0.0034, +0.0339] p=0.1102 | 0.551 | +0.0082 [-0.0135, +0.0292] | -0.0068 [-0.0238, +0.0106] | REFUTA |
  | 8 % | 60 s | 385 | +0.0109 [-0.0105, +0.0324] p=0.3158 | 0.947 | +0.0078 [-0.0147, +0.0300] | -0.0112 [-0.0276, +0.0054] | REFUTA |
  | 12 % | 60 s | 329 | -0.0002 [-0.0227, +0.0221] p=0.9837 | 0.984 | +0.0019 [-0.0250, +0.0276] | -0.0223 [-0.0367, -0.0078] | REFUTA |
  **Veredito (paper): REFUTA**
    - (a) nenhuma célula com IC inferior > +0,01 (maior = +0.0069)
    - (b) melhor célula X=3% W=60s (D +0.0228) na borda em X
    - melhor célula X=3% W=60s: D +0.0228 (IC inf +0.0069), 5 s +0.0151, nível +0.0008
    melhor célula X=3 % W=60 s; impressão digital do pré-registo no moinho: 69145f46b870

## Hipótese inteira: REFUTA (reais: REFUTA; papel: REFUTA)
```

- A coluna "moinho" é o rótulo do `infra/research` para cada célula, que **não decide** aqui (§1.7). O `REFUTA`
  dele significa "IC superior abaixo do MRE de +0,05". No papel isso vale para **todas** as 8 células.
- **Leitura estatística ao lado da letra** (redação acordada com a Astra): no papel, a análise principal
  sugere uma melhora relativa pequena, e o IC dela exclui o ganho de +5 pp previsto. Nas reais, a incerteza
  continua larga e não exclui +5 pp. Isto não prova que esperar qualquer recuo seja inútil.
- Os IC são marginais, não simultâneos. O Holm 0,052 não passa de 5 %, mas não há rutura científica entre
  0,049 e 0,052.

## 5. O que acontece por dentro (descritivo, 1,6 s, melhor célula e extremos)

| | reais X3 W60 | reais X12 W20 | papel X3 W60 | papel X12 W20 |
|---|---|---|---|---|
| entradas | 55/65 (85 %), gatilho mediano aos 14,0 s | 20/65 (31 %) | 446/486 (92 %), 8,1 s | 185/486 (38 %) |
| D das entradas / das não-entradas (por decisão) | +0,0198 / +0,0001 | +0,0109 / −0,0319 | +0,0218 / +0,0010 | +0,0263 / −0,0157 |
| vitórias do controlo perdidas por não entrar | 5 de 30 (0,058 SOL) | **25 de 30** (0,329 SOL) | 15 de 181 (0,136 SOL) | **146 de 181** (1,474 SOL) |
| vitórias: política × controlo | 29 × 30 | 7 × 30 | 189 × 181 | 63 × 181 |
| PnL somado: política × controlo (SOL) | +0,1168 × +0,0215 | −0,0555 × +0,0215 | +0,0357 × −0,5010 | −0,2846 × −0,5010 |
| perdas ≥ 50 %: controlo → política | 2 → 0 | 2 → 1 | 7 → 5 (1 criada, 3 evitadas) | 7 → 2 |
| perdas que nunca passaram do custo (simuladas) | 16/35 = 0,46 → **16/26 = 0,62** | 0,46 → 0,62 | 0,58 → 0,59 | 0,58 → 0,62 |

- **O filtro "só compra se recuar" seleciona contra as vencedoras.** As moedas que sobem sem olhar para trás
  são as que batem o alvo. Com X grande e W curto, perdem-se quase todas.
- **A fração de perdas "que caem desde a compra" nunca cai** (a previsão secundária falhou em todas as células
  das reais). Na melhor célula das reais o numerador fica igual, 16 de 65, e o denominador de perdas desce.
- **As 34 perdas históricas que nunca passaram do custo:** 21 estão na população elegível (as outras são
  recompras do mesmo mint ou saíram por cobertura). Na melhor célula: evitadas 5, viradas em ganho 6,
  melhoradas mas ainda perda 6, iguais ou piores 4. Com X = 12 % e W = 20 s: evitadas 10, viradas 4.

## 6. Sensibilidades (saída real em `r77/report.txt`)

- **Só o estado final de cada slot** (ordem intra-slot ambígua; corrigida na ronda 2 da Astra, §10). Reais,
  X3 W60: +0,0174 [−0,0382, +0,0731]. Papel, X3 W60: **+0,0214 [+0,0044, +0,0387]**. É o mesmo quadro: pequeno,
  com IC inferior abaixo de +1 pp.
- **Fotos também disparam e criam a máxima:** 1 gatilho por foto nas reais e 7–21 no papel. Reais, X3 W60:
  +0,0232. Papel, X3 W60: +0,0240 [+0,0078, +0,0403]. Nenhum IC inferior passa de +1 pp.
- **Horizonte fixo de 370 s** (a emenda 5 original).
  - Reais, n = 34: o sinal fica negativo em todas as células com X ≥ 5 %. X12 W20: −0,0859 [−0,1674, −0,0151].
  - Papel, n = 200: X3 W60 dá **+0,0294 [+0,0061, +0,0538]**. É o único ponto em que o IC chega acima de +5 pp,
    por isso a exclusão de +5 pp no papel é "da análise principal", não de todas.
- **5 s de atraso em todas as pernas:** o D da melhor célula cai, mas não troca de sinal (reais +0,0111, papel
  +0,0151). A cláusula (c) não dispara.
- **Pista de eventos** (descritivo, sem veredito): mesmo sentido, com D maiores e IC maiores.
  - Reais, n = 53: X3 W60 +0,0370 [−0,0270, +0,1014]; X8 W60 +0,0298.
  - Papel, n = 162: X3 W60 +0,0304 [−0,0015, +0,0608], e a 5 s +0,0325 [+0,0006, +0,0648]. Contra nada:
    +0,0119 [−0,0185, +0,0413].
  - É o recorte que a mesa usa hoje. Nenhuma célula tem IC inferior acima de +1 pp.

## 7. Ressalvas (a mais importante primeiro)

1. **Observabilidade.** O replay assume que a mesa vê cada estado no `block_time` pela fita WS. A guarda
   impede consultar pontos futuros da cadeia modelada, mas **não prova** que o WS entregaria aquela troca
   naquele instante. A fita vem do arquivo por polling (~44 s de atraso de chegada, R73). Os 5 s atrasam o
   pouso, não a observação.
2. **"Sem nós" é replay contábil aproximado** (§9.1): as trocas alheias ficam com os montantes históricos, e
   não é o produto constante contrafactual exato.
3. **A censura seleciona pela observabilidade, e a emenda 9 foi feita depois de ver contagens** (antes de ver
   retornos). O efeito estimado vale para decisões observáveis sob toda a grade, não para todas as decisões da
   porta. Uma trajetória que fica exposta até um buraco sai da amostra inteira. Isso **não é** eliminado pela
   uniformidade.
4. **O nível do modelo é otimista** em relação à mesa (§3). O contraste emparelhado é mais robusto que o nível.
5. **As populações partilham mints:** não são réplicas independentes. Os dados das reais já tinham sido
   olhados na anatomia que originou a H-016 (as 96 posições), então as reais não são amostra independente da
   origem.
6. **Borda da grade:** o melhor ponto está em X = 3 %, o menor valor. O que acontece abaixo disso não foi
   medido e não pode ser medido nestes dados sem virar pesca (§8).

## 8. O que isto significa, e o que não propor

- **Para a mesa real: não mudar a entrada.** A regra "entra no recuo" tem D médio de +2 pp no modelo, mas não
  confirma, empata com "não comprar" no papel, e fica dentro da distância de ~3 pp entre modelo e execução
  real.
- **Nenhum braço de papel** (a H-016 não confirmou).
- **Pista exploratória (Astra: "legítima, não confirmação"):** o ganho que existe vem do **preço** das
  entradas, com X pequeno. Uma hipótese sucessora teria de:
  - ser congelada antes, numa **coorte futura sem os mints daqui**;
  - comparar também com uma espera simples de N segundos, sem condição de recuo;
  - exigir resultado líquido útil **contra não comprar**.

  Não foi registada na fila. Registá-la é decisão do coordenador.
- **O mecanismo da H-016 não se sustentou:** comprar depois de um recuo não livra das perdas que caem desde a
  compra (§5). A leitura mais simples é que, nesta porta, o recuo de alguns por cento nos primeiros 20–60 s é
  ruído de preço **tanto** nas vencedoras **como** nas perdedoras. Esperar por ele troca vencedoras perdidas por
  um preço um pouco melhor, e o saldo é quase zero.

## 9. Emendas ao desenho — antes de simular qualquer célula (Astra, ronda 1)

Resposta em `.claude/state/astra-review-R77.md`. Aceites e aplicadas **antes** da primeira simulação:

1. **"Sem nós" é replay contábil aproximado**, não a curva exata que existiria sem nós: remove-se o efeito
   das nossas trocas (SOL **e** tokens, compras **e** vendas, acumulado a partir da âncora) mantendo fixos os
   montantes históricos das trocas alheias. Verificação de completude: para cada posição real, a nossa
   compra tem de estar na fita (conta-se quantas faltam).
2. **Ordem dentro do slot é ambígua** (`(slot, signature, event_index)` não é a ordem de execução). Linha
   principal = troca a troca na ordem herdada do R72 (a fila diz "primeiro trade"); **sensibilidade** = só o
   estado final de cada slot (invariante à ordem). Publica-se quantos gatilhos caem num ponto que não é o
   último do seu slot.
3. **Fotos não disparam nem criam a máxima** na linha principal: a regra da fila é "primeiro trade". Fotos
   só ressincronizam as reservas. A máxima `M` = preço em `t0` e depois só pontos de troca. Sensibilidade:
   fotos também contam (máxima e gatilho). Nota: o `observed_at` da foto RPC é o tempo do bloco, não a
   chegada; a âncora `≤ t0` inicializa reservas que a fita WS já conhecia — não é informação de futuro.
4. **Relógio materializado:** o fill do controlo é o último estado com `t ≤ t0 + L` (não `_fill_index` a
   partir de um ponto passado); o caminho entregue a `simulate_current` começa **no pouso**, já com a nossa
   compra, sem prefixo pré-entrada.
5. **Censura em horizonte fixo, independente da política:** maior buraco da cadeia em `[t0, t0 + 370 s]`
   (`60 + 5 + 300 + 5`) `≤ 60 s`, medido a partir de `t0` e com a cauda até `t0 + 370`. Substitui o "último
   pouso entre os 9 braços" da §1.6. Vale para 1,6 s e 5 s. Se, mesmo assim, o simulador devolver `ok=False`
   num braço, a **decisão inteira** sai (nunca vira zero) e conta-se.
6. **Redação:** o 0 é o **retorno da política** quando não entra; `D_i = 0 − r_controlo,i` nesse caso. A
   estatística é a **média por decisão do retorno por SOL** (não ΣPnL/ΣSOL). Exclusão por decisão antes de
   empilhar (o moinho descarta linha a linha).
7. **Fração das perdas que nunca passaram do custo, por braço:** numerador = decisões com entrada, retorno
   `< 0` e marca máxima (`sell_net` do lote) entre o pouso da compra e o gatilho da saída `≤ S`; denominador
   = decisões com entrada e retorno `< 0`. Sem perdas no braço → fração 0. "Cai" = fração da política `<`
   fração do controlo (estimativa pontual). As 34 históricas (marca da mesa) ficam só no descritivo.
8. **Holm** é impresso, mas não entra na regra de confirmação (a fila não o pede). As populações partilham
   mints: não são réplicas independentes.

Concordâncias da Astra (sem mudança): controlo também simulado; `t0 = proposed_at`; empilhar 2 linhas por
decisão com `cluster = stratum = mint` dá bootstrap emparelhado e permutação por troca de sinal (bilateral);
(b) borda só em X; (c) 5 s em todas as pernas dos dois braços, mesma célula escolhida a 1,6 s; (d)
estimativa pontual `≤ 0`; rótulo da hipótese inteira como na §1.8.
9. **Emenda à emenda 5 — condição diferente das 8 anteriores: feita DEPOIS de simular e de ver só as contagens de censura, ANTES de examinar qualquer retorno** (24/09 ~01:3x UTC).
   O horizonte fixo de 370 s censurou 51 de 85 reais e 396 de 596 do papel. Diagnóstico **só de tempo**: em
   32 das 35 reais censuradas e 303 das 338 do papel, o primeiro buraco > 60 s **começa 120–300 s depois de
   `t0`**, depois de a maioria das saídas ter pousado (hold mediano 24–31 s no R74). Ou seja, o horizonte fixo
   censura silêncio **depois** da saída, o que se correlaciona com o desfecho (moeda morta fica quieta).
   Volta-se à regra literal do brief ("censurar quando a fita não tem dados **até à saída**"), aplicada de
   forma **uniforme**: a decisão entra se, em **todos** os braços da linha principal (controlo + 8 células, a
   1,6 s **e** a 5 s), o maior buraco da cadeia entre `t0` e o pouso da saída (ou `t0 + W`, se não entrou) é
   `≤ 60 s`. A preocupação da Astra (a 5 s expõe o lote a um buraco) fica coberta porque os braços a 5 s
   também contam. O horizonte fixo de 370 s passa a **sensibilidade** publicada ao lado.

Nota da ronda 2 da Astra sobre a emenda 9: é aceitável como emenda feita depois de inspecionar a cobertura e
sem olhar retornos. Mas os tempos dos buracos **justificam** a escolha, não **provam** que os buracos vieram
depois das saídas contrafactuais do R77. E a uniformidade não elimina a seleção pelo desfecho (§7.3).

## 10. Segunda opinião (Astra)

Chamadas:
- `bash infra/scripts/astra.sh ask R77 "..."` **antes** de simular, com resposta em
  `.claude/state/astra-review-R77.md`;
- `... ask R77-veredito "..."` depois de correr, com resposta em `.claude/state/astra-review-R77-veredito.md`.

**Ronda 1 (desenho):** 7 must-fix, todos aplicados antes de simular (§9, itens 1–8). O mais importante foi a
nossa própria troca a faltar na fita: com ela ausente, a foto seguinte carregava a nossa compra, inflava a
máxima e fabricava um recuo. Isto acabou por se verificar nos dados: 19 de 85 decisões reais, corrigidas por
injeção do fill registado (§2).

**Ronda 2 (veredito):**
- **Reprodução.** Refez a população e os contrastes em memória e chegou ao mesmo `REFUTA` nas duas populações,
  com Holm 0,051995 no papel e 45 testes a passar do lado dela.
- **Must-fix aceite: defeito na sensibilidade `slotfinal`.** Quando uma foto fechava o slot, a última troca
  desse slot era rejeitada e o slot inteiro sumia da regra. Cenário reproduzido: troca a 96 e foto a 96 no
  mesmo slot → `main=1 slotfinal=None`. Correção: `last_in_slot` passou a significar "última **troca** do
  slot", com teste `test_slot_final_uses_last_trade_even_when_a_photo_closes_the_slot` (falhou antes e passa
  depois). Só a sensibilidade mudou: reais X3 W60 +0,0147 → +0,0174; papel +0,0227 → +0,0214. A linha
  principal ficou idêntica.
- **Nice-to-have aplicados:**
  - uma falha numa sensibilidade já não censura a decisão da linha principal (o único caso também violava o
    buraco; n igual);
  - D decomposto em entradas e não-entradas;
  - impressão digital do pré-registo no relatório.
- **Redação aceite:**
  - o `REFUTA` literal ao lado da leitura estatística (§4);
  - a exclusão de +5 pp no papel é "da análise principal", porque o horizonte de 370 s vai a +5,38;
  - a subida da fração de perdas "desde a compra" é mudança de composição (mesmo numerador, 16 de 65), não
    mais perdas desse tipo;
  - o +2 pp é pista para hipótese nova numa coorte futura, não confirmação.
- **Não aplicado:**
  - a sensibilidade por blocos temporais (nice-to-have). Com o `REFUTA` por (a) e (b), um IC mais largo não
    muda o rótulo; fica como próximo passo de uma sucessora.
  - a sugestão de rotular "REFUTA operacional; evidência distinta por população". O rótulo da fila tem três
    valores e a letra dá `REFUTA`; a distinção por população está na leitura estatística ao lado.

## 11. Arquivos

`.claude/state/r77/`:

| ficheiro | o que é |
|---|---|
| `q.sh`, `q_*.sql` | exportações só-leitura (`default_transaction_read_only=on`) |
| `pop.csv` (3,3 MB), `own.csv` | população (reais + papel `fluxo_e_holders`) e os nossos fills registados |
| `cache/tape.csv.gz` (20 MB), `cache/snap.csv.gz`, `cache/arms.jsonl` (4 MB) | **caches grandes, separados; não são para commit** |
| `chain.py` | cadeia "sem nós": âncora, trocas alheias, fotos descontadas do nosso efeito |
| `entry.py` | `View`/`LookAheadError`, `Dip`, `Cheat`, `find_trigger`, `simulate_arm` (saída = `r72/sim.simulate_current` sem alteração) |
| `rule.py` | contraste emparelhado pelo moinho (`run_hypothesis`, 2 linhas por decisão, `cluster = stratum = mint`), Holm, regra congelada |
| `sim_all.py` → `cache/arms.jsonl` | simula controlo + 8 células (1,6 s e 5 s) + sensibilidades |
| `report.py` → `report.txt` | relatório final; `report_v0.txt` = antes da injeção dos nossos fills |
| `fidelity.py` → `fidelity.txt` | controlo modelado × R72 no fill real × PnL realizado |
| `test_r77.py` | 46 testes |

## 12. Testes (anti-antecipação e valores conhecidos)

- **Cadeia:**
  - remove as nossas trocas e desconta-as da foto;
  - sem âncora antes de `t0` → censura;
  - a compra nossa injetada sai da foto;
  - a injeção não duplica.
- **Regra de entrada:**
  - usa a máxima corrente e não o preço em `t0`;
  - a máxima inicial é o estado em `t0`;
  - respeita a janela W;
  - fotos não disparam na linha principal;
  - `slotfinal`, incluindo o slot fechado por foto.
- **Antecipação:**
  - o `Cheat` é apanhado (`LookAheadError`) em séries sintéticas **e em ~120 cadeias reais**;
  - o gatilho não muda quando o futuro muda, em 20 séries sintéticas × 4 células **e nas cadeias reais**
    (≥ 150 verificações com o futuro multiplicado por 0,2–5×);
  - o oráculo que compra no mínimo da janela (olhando o futuro) rende +8,95 % por SOL contra −1,08 % da regra
    causal X3 W60, nas 136 cadeias da amostra. É a distância que a guarda protege.
- **Pouso e saída:**
  - o controlo compra no estado conhecido a `t0 + 1,6 s`, não num ponto antigo;
  - o caminho começa no pouso, já com a nossa compra;
  - saída por alvo com valor conhecido (≈ 1,3·(1 − c/2)² − 1);
  - a marca "nunca passou do custo".
- **Estatística e regra:**
  - o D do moinho empilhado é igual à média das diferenças emparelhadas;
  - CONFIRMA no interior com patamar;
  - REFUTA na borda, só por não entrar, e quando morre a 5 s;
  - REFUTA (a) e NÃO CONFIRMA sem patamar;
  - nas reais é preciso que a fração caia;
  - rótulo da hipótese inteira.

```
$ cd .claude/state/r77 && uv run --project ../../.. pytest test_r77.py -p no:cacheprovider -q --rootdir=.
..............................................                           [100%]
46 passed in 13.33s
```

Lint: `ruff check` nos scripts dá só `UP031` (formatação com `%`) e `T201` (`print` é a saída de um script de
pesquisa, como no R74). `B007` e `I001` foram corrigidos.
