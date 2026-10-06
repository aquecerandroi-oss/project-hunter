---
tags: [dialogo, astra, carteiras, desempenho, h-030]
date: 2026-10-06
updated: 2026-10-06
status: registro
owner: sexta-feira
decided_on: 2026-10-06
by: sexta-feira + astra
tarefa: CPU do motor de carteiras 1c-bis (≈ 31–34 h/núcleo por noite, extrapolação sintética)
veredito: rodada 1 sem decisão conjunta; rodada 2 com DECISÃO CONJUNTA (ordem perfil → trabalho repetido → fusão e 2 workers → vetorização seletiva); passos 1–2 medidos e executados em 06/10 (≈ 2–3× menos CPU, regra intacta; meta de < 2 h ainda pede 2–4× menos trabalho por fill)
---

# CPU do motor de carteiras: medir antes de reescrever

**Problema:** o motor 1c-bis ([[wallets-1c-bis]]) cabe na memória. Mas, extrapolado do bench sintético, levaria ≈ 31–34 h por noite num núcleo para 200–217 M fills de janela. A VPS tem poucos núcleos e roda produção.

**Rodada 1, Astra:** ainda não é decisão conjunta. Duas correções e três must-fix.
- **Correção 1:** medir a forma do custo (perfil) antes de escolher vetorização ou paralelismo. Pontos suspeitos de trabalho repetido:
  - `_prepared` deduplica e ordena a cada uma das três passadas;
  - cada cópia varre a fita para achar o gatilho e reconstruir o líder;
  - `MintCarry.flow_of` reconstrói o dicionário a cada consulta;
  - os pares de compradores no mesmo slot são combinatórios.
- **Correção 2:** o avanço "snapshot anterior + dia novo − dia velho" não é equivalente (contraexemplo das gêmeas). Mas "impossível em geral" não está provado: índices ou fatos independentes da janela podem ser reaproveitados depois do perfil.
- **Must-fix:**
  - não cortar dependências para reduzir a população (venda pequena, carteira antes da fusão, mint não copiável);
  - reduzir os acumuladores de forma exata antes de paralelizar (conjuntos, mediana exata, teto diário global);
  - 2 núcleos sozinhos não chegam a 2 h: é preciso ≈ 8× menos trabalho por núcleo.
- **Mudar o universo** (atividade mínima, só mints compráveis) é nova versão do protocolo e decisão do Everton.
- **Rodar fora da VPS** é opção operacional válida, se o envelope medido não couber.

**Rodada 2, Sexta-feira (enviada em 06/10):** aceitou as duas correções e os três must-fix. Ordem proposta:
1. perfil (cProfile só do stream, por passada) e matriz de escala;
2. tirar o trabalho repetido do trecho dominante, um por vez, com diferencial contra uma referência congelada;
3. fusão dos acumuladores e 2 workers, se a fração paralela justificar;
4. vetorização seletiva;
5. só então rodar fora da VPS.

Aceite de ponta a ponta: < 2 h sob 2 núcleos, como meta proposta. A resposta da rodada 2 está em `.claude/state/dialogue-wallets-cpu.md`; a síntese fica pendente de leitura.

[[wallets-1c-bis]] · [[wallet-tape-storage]] · [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]] · [[EXP-M15-carteiras-vencedoras]]

## Rodada 2, Astra: DECISÃO CONJUNTA (registrada em 06/10 pelo quant-engineer)

Ela abriu a rodada 2 com **DECISÃO CONJUNTA** (bruto: `.claude/state/dialogue-wallets-cpu.md`, seção "Astra (rodada 2)"). Aceitou a ordem perfil → trabalho repetido → fusão exata e 2 workers → vetorização seletiva → fora da VPS. Também aceitou os três must-fix como requisitos e a meta de < 2 h sob 2 núcleos, como proposta técnica ainda não atingida. A exigência dela que guiou os passos 1–2: uma **referência congelada independente**, para que um helper compartilhado com o batch não engane os dois lados do diferencial.

## Medição (06/10/2026, quant-engineer): passos 1 e 2

**Tudo abaixo é sintético, não é dado de mercado.** O gerador é `kb0183-shape-v2`.

- **Scripts:**
  - `infra/scripts/research/2026-10-06-wallets-engine-profile.py` e `-gen.py`;
  - o bench de 05/10, atualizado com `--generator`; o antigo fica como `v1`.
- **Saídas** em `.claude/state/carteiras-lucro/bench/`: `profile-2026-10-06-step1-before.txt`, `-before-fills16k-rerun.txt`, `-step1-after.txt` e `-step2-stages.txt`.
- **Ambiente:** revisão `84704fa1` (o motor é idêntico em `80e50cbc`), Python 3.12.14, Windows 11, Intel Family 6 Model 170 com 22 núcleos lógicos.
- **A máquina é compartilhada** com outros agentes, e o tempo da mesma configuração chegou a quase triplicar entre rodadas: base head foi de 10,05 a 21,78 s; hot_4k G2, de 5,39 a 15,36 s. Por isso o passo 2 mede cópias congeladas do pacote em cada estágio, de duas formas que vão separadas abaixo:
  - **passada 3:** duas rodadas intercaladas, em ordem inversa, sem cProfile; vale o mínimo;
  - **passada 4:** três chamadas seguidas no mesmo processo, com o memo vazio antes de cada uma, mais a contagem de chamadas sob cProfile. **A contagem é determinística e não depende da carga.**

### O gerador agora tem a forma do KB-0183

O gerador de 05/10 punha 54 % dos eventos em carteiras de um swap só. O novo usa a concentração da run 3 do [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]] e o tamanho de swap da errata (≈ 40 % abaixo de 0,01 SOL). Censo medido num dia gerado:

| | KB-0183 (15 min) | gerador (um dia) |
|---|---|---|
| carteiras com um swap | 58 % | 58–66 % |
| eventos dessas carteiras | 13 % | 13–14 % |
| carteiras com ≥ 20 swaps / eventos delas | 4 % / 46 % | 3–4 % / 45 % |
| swaps < 0,01 SOL | ≈ 40 % (errata) | 40 % |

Como a forma de 15 min se estica para um dia ou para a janela **não foi medido**. Na janela de 2 d, as carteiras com ≥ 20 swaps caem para 1,3 %, porque as de um swap são novas a cada evento.

### Passo 1: onde o tempo vai, com o motor intocado

Mede-se só a chamada do stream da última noite (janela de 2 d, salvo `window7`). As porcentagens são do tempo da chamada.

| config | fills | cópias | cotações de stop / cópia | cópias % | E-PnL % | survey+bets % | `_prepared` (3 passadas) % | µs CPU/fill |
|---|---|---|---|---|---|---|---|---|
| base (8 k/dia) | 18 852 | 2 256 | 132 | 75,7 | 14,4 | 2,9 | 1,7 | 402 |
| fills_4k / fills_16k | 7 090 / 31 087 | 860 / 4 136 | 64 / 116 | 59,6 / 74,5 | 25,1 / 15,4 | 2,9 / 1,9 | 2,2 / 1,8 | 264 / 389† |
| hot_1k / 2k / 4k (um mint com 1–4 mil eventos em 1 h) | 19 852–22 852 | 2 357–2 494 | 144 / 183 / 288 | 79,3 / 83,4 / 87,5 | 12,4 / 8,7 / 7,0 | ≤ 1,6 | ≤ 1,2 | 444 / 543 / 896 |
| triggers 0,1 / 0,7 (fração das compras ≥ 0,1 SOL) | 18 852 | 725 / 4 198 | 131 / 130 | 50,2 / 82,9 | 30,6 / 10,0 | 5,3 / 2,1 | 3,8 / 1,3 | 261 / ruído* |
| history 3 d / 5 d (carry maior) | 15 310 / 12 079 | 1 811 / 1 278 | 103 / 57 | 56,9 / 28,9 | 28,4 / 48,0 | 2,1 | 1,5 / 1,8 | 433 / 404 |
| burst 10 / 40 / 120 compradores no mesmo slot × 20 | 19 452–21 652 | 1 469–2 071 | 137–159 | 70–75 | 12–15 | 2,2 / 3,5 / 4,9 | ≤ 2,0 | 318 / 302 / 278 |
| janela vazia, carry grande (30 229 lotes) | 0 | 0 | — | 0 | 76,0 | 0,4 | 0,6 | 3,8 s no total |
| window7 (2 k/dia, 7 d) | 11 624 | 1 135 | 61 | 55,8 | 29,1 | 3,1 | 2,4 | 239 |

\* A rodada da matriz para `triggers_0.7` pegou a máquina carregada (27 s). Nas rodadas intercaladas, o mesmo motor deu 14,5–16,1 s.

† `fills_16k` vem do rerun (`profile-2026-10-06-step1-before-fills16k-rerun.txt`). A primeira rodada (559,9 µs/fill, relógio de 28 255 s) atravessou uma suspensão da máquina. O rerun usou o `pricing.py` do HEAD reescrito por `git show` (fim de linha LF), por isso o arquivo aparece como alterado e o hash difere: o conteúdo é o do HEAD. A passada 3 do passo 2 mediu o head de `fills_16k` de uma cópia limpa: 13,34 s.

O que o perfil mostra:

1. **O dominante é o stop de cada cópia.** Para cada estado observado depois da entrada, até a saída, `simulate_copy` cota a venda em Decimal: `_find_exit` chama `_stopped`, que chama `sell_lamports`, que chamava `curve.quote_sell`. No `hot_4k`, essas cotações somavam ≈ 30 de 36 s sob o cProfile.
2. **O segundo é o E-PnL**: a liquidação de cada posse em cada fronteira de dia. É uma cotação por (dono, fronteira), com átomos diferentes, ou seja, trabalho necessário, não repetido. Ele domina quando o carry pesa: 48 % em `history_5d` e 76 % na janela vazia.
3. **Mais que linear por mint.** O custo de um mint ≈ cópias × eventos no horizonte de saída da cópia (≤ 1 h):
   - o mint HOT com 2 000 eventos em 1 h custou 3,5 s; com 4 000, 11,0 s (≈ n^1,6);
   - um mint de 2 000 eventos espalhados em ~11 h custou 1,3 s;
   - as cotações por cópia sobem com a densidade: 64, depois 132, depois 288.

   Por isso o µs por fill **não é constante**: depende da densidade por mint, que **não foi medida em dado real** (o KB-0183 não tem histograma por mint).
4. **Não são gargalo de CPU:**
   - o `_prepared` repetido nas três passadas: 0,9–3,8 %;
   - os pares de compradores no mesmo slot: com 52 637 pares, survey+bets ficam em 4,9 %. Os pares pesam em memória, não em CPU, nesta escala;
   - o avanço do carry: 0,6–3,1 %.

### Passo 2: sete remoções de trabalho repetido, uma por vez

Nenhuma regra mudou. Cada remoção teve um teste que falhou antes, contando o trabalho (leituras da fita, conversões, contextos), e não o tempo. Os diferenciais existentes ficaram intocados e verdes.

| # | O que se repetia | Onde | Teste: antes → depois | Chamadas de função a menos (base, passada 4) |
|---|---|---|---|---|
| B | `curve.quote_sell` montava taxa, estado posterior (`dataclasses.replace`) e preço marginal em cada cotação do stop, e jogava fora | `pricing.sell_lamports` | não monta `SellQuote`; grade de 4 000 vendas contra a cópia congelada do caminho antigo | −32 % |
| C | `all(identity != …)` varria a fita a cada cópia | `simulate_copy` → `MintTape.has` | 120 820 leituras → < 6 080 | −15 % |
| D | filtro da fita inteira, por cópia, para achar o líder | `_leader_exit` → `MintTape.of_wallets` | 121 600 → < 6 080 | laço em C* |
| A | o stop varria desde o primeiro evento da fita | `_find_exit` → `MintTape.first_after` | 121 222 → < 6 080 | laço em C* |
| E | `MintCarry.flow_of` remontava o dicionário de todos os flows do mint, por cópia | `stream_mint` → `carry.flow_totals` | 4 920 → ≤ 360 | laço em C* |
| F | a mesma conversão Decimal de um estado, para cada cópia que passa por ele | `pricing._curve` (LRU de 16 384 entradas, 8,1 MB medidos) | 299 conversões → 1 | −10 % |
| G | piso do stop (fração × orçamento) recalculado em contexto Decimal a cada evento | `policy._find_exit` | 500 contextos → ≤ 1 | −7 % |

\* A contagem de chamadas não vê iterações dentro de um laço em C; a prova delas é o teste de leituras.

**Antes e depois** (`profile-2026-10-06-step2-stages.txt`). Cópias congeladas do pacote em cada estágio. As duas passadas vão em colunas separadas; as chamadas são da passada 4.

| config | passada 3: CPU head → G2 (s) | razão | passada 4: CPU head → G2 (s) | chamadas head → G2 (milhões) | razão das chamadas | µs CPU/fill G2 (passada 3) |
|---|---|---|---|---|---|---|
| base | 10,05 → 3,62 | 2,8× | 11,80 → 5,14 | 16,9 → 8,2 | 2,05× | 192 |
| hot_2k | 13,33 → 4,23 | 3,2× | — | — | — | 203 |
| hot_4k | 15,42 → 5,39 | 2,9× | 31,91 → 6,27‡ | 33,3 → 14,5 | 2,29× | 236 |
| triggers 0,7 | 12,61 → 4,41 | 2,9× | 12,70 → 4,83 | 27,2 → 12,1 | 2,25× | 234 |
| fills_16k | 13,34 → 5,97 | 2,2× | 12,56 → 5,64 | 28,3 → 14,0 | 2,03× | 192 |
| window7 | 2,83 → 1,50 | 1,9× | — | — | — | 129 |
| janela vazia, carry grande | 3,30 → 2,09 | 1,6× | 2,41 → 1,44 | 5,79 → 4,26 | 1,36× | — |
| burst_120 | 5,91 → 5,73 | 1,0×\*\* | — | — | — | 265 |

‡ As três chamadas do head deram 31,9–32,8 s, contra 15,4 s na passada 3: a carga ficou alta durante toda aquela medição. A razão de tempo desta linha não vale; a das chamadas vale.

\*\* Na passada 3, o estágio F mediu 2,69 s em `burst_120`. Que o G2 tenha sido pego por carga é **hipótese**: o `burst_120` não entrou na passada 4. Nas configurações contadas, o G2 faz menos chamadas que o F, ou o mesmo número na janela vazia (4 260 799), que não tem cópias.

- **O mint denso foi o que mais caiu.** O HOT de 4 000 eventos em 1 h, com 280 cópias, custa o replay desse mint numa única medição instrumentada:

  | | head | G2 |
  |---|---|---|
  | matriz do perfil (`step1-before.txt` / `step1-after.txt`) | 11,0 s | 7,1 s |
  | passada 4 (`step2-stages.txt`, máquina carregada no head) | 14,7 s | 2,7 s |

  A faixa larga do G2 é a carga da máquina: hipótese, não medida.
- **As cotações do stop são idênticas em todos os oito estágios** (297 964 na base, 718 076 no hot_4k). É a mesma regra fazendo a mesma varredura, só que mais barata.
- **Bench atualizado** (38 456 fills de janela na maior escala): o limitado gastou 5,39 s de CPU (140 µs/fill) numa rodada do motor final (`run-2026-10-06.txt`). No par lado a lado (`run-2026-10-06-head-vs-tree.txt`) foi de 14,92 s (388 µs/fill) no head para 7,89 s (205 µs/fill). O batch também ganha, porque divide os helpers.

**Prova:**

- Diferenciais intocados: `uv run pytest packages/indicators/tests/meme` foi de 204 para 217 passed (13 testes novos).
- **Referência congelada independente** (`wallets_golden.json`, digests do código `84704fa1` calculados antes de qualquer mudança): retratos batch e limitado mais o carry em cada noite de 5 mundos; `simulate_copy` com cada uma das 945 compras de um mundo denso como gatilho, em duas políticas e duas formas de chamada (1 890 resultados por política); uma grade de cotações. A Astra a reproduziu carregando o código antigo do git.
- Digest do retrato igual em todos os estágios, nas 8 configurações (diferencial em escala).
- 11 de 11 mutantes mortos.

### Extrapolação para 200–217 M fills de janela

É **cenário, não medida**. O custo por fill depende da densidade por mint, que não foi medida em dado real.

| | µs CPU/fill (sintético) | horas por noite num núcleo |
|---|---|---|
| antes (head; configs do perfil, mínimo das rodadas) | 243–675 | 13,5–40,7 |
| depois (G2; configs do perfil) | 129–265 | 7,2–16,0 |
| depois, bench de 05/10 atualizado (`run-2026-10-06.txt`, `run-2026-10-06-head-vs-tree.txt`) | 140–205 | 7,8–12,4 |

As 31–34 h de [[wallets-1c-bis]] vinham do gerador antigo.

**A meta ainda está longe.** < 2 h sob 2 núcleos são 14 400 núcleo-segundos para 217 M fills, ou seja, **≤ 66 µs de CPU por fill** (72 µs a 200 M), com paralelismo perfeito e sem contar IO, canonicalização, serialização e redução. Falta tirar **2–4× de trabalho por fill**. Dois workers não reduzem trabalho: só convertem os 2 núcleos em tempo de relógio.

### O que sobra para o passo 3 (e o 4)

1. **Fusão exata e 2 workers (passo 3).**
   - Reduzir os acumuladores como acordado: soma, união, máximo com ausência, posses concatenadas; mediana e razões só no fim.
   - Entidades, apostas e sementes de taxa globais antes de distribuir mints inteiros.
   - O maior mint não se divide: o HOT custou 2,7–7,1 s sozinho no motor final, conforme a carga.
   - O LRU é por processo (8,1 MB cada), e o índice preguiçoso da fita não é seguro entre threads (Astra).
2. **O stop por cópia continua sendo o maior trabalho** onde há muitas cópias: as cópias ficam com 17–73 % do tempo depois do passo 2 (`profile-2026-10-06-step1-after.txt`; a janela vazia, sem cópias, fica de fora, com 0 %), e o E-PnL com 13–65 %. Há duas reduções exatas candidatas para o passo 4, **ambas exigindo prova antes**:
   - um núcleo inteiro da venda na curva que reproduza o arredondamento de 28 dígitos HALF_EVEN do Decimal (a Astra adverte: equivalência algébrica não basta);
   - um limiar por evento (o maior número de átomos cuja venda fica ≤ piso), que trocaria as cotações por (cópia, evento) por uma comparação de inteiros. Isso só vale se a venda líquida, já arredondada, for monotônica nos átomos.
3. **O E-PnL nas fronteiras** é trabalho necessário (uma liquidação por posse e por dia). Só um núcleo mais rápido o reduz; ele domina as noites de carry grande.
4. **Medir a densidade real por mint** (eventos por hora no mint mais ativo, gatilhos por mint) antes de qualquer previsão. É ela que torna o custo mais que linear.

Revisão da Astra deste passo: [[wallets-cpu-step2]].
