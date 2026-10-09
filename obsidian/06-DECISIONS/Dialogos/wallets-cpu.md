---
tags: [dialogo, astra, carteiras, desempenho, h-030]
date: 2026-10-06
updated: 2026-10-09
status: registro
owner: sexta-feira
decided_on: 2026-10-06
by: sexta-feira + astra
tarefa: CPU do motor de carteiras 1c-bis (≈ 31–34 h/núcleo por noite, extrapolação sintética)
veredito: rodada 1 sem decisão conjunta; rodada 2 com DECISÃO CONJUNTA (ordem perfil → trabalho repetido → fusão e 2 workers → vetorização seletiva); passos 1–2 medidos e executados em 06/10 (≈ 2–3× menos CPU, regra intacta; meta de < 2 h ainda pede 2–4× menos trabalho por fill); passo 3 em 06/10: fusão exata e mints inteiros em processos, provados (digests congelados com 1, 2 e 4 workers; 17/17 mutantes); 2 workers 1,2–1,9× sobre 1 worker, mas só vencem o serial em memória no mint quente (1,09×); densidade real por mint não medida (proposta pronta, sem rodar); passo 4 em 09/10: venda arredondada provadamente monotônica só numa região (contraexemplo fora; ela cobre a escala de produção), stop por limiar inteiro com fallback Decimal fora dela, digests congelados iguais, 15/15 mutantes; chave quente de 124 mil/h 200 → 10,8 s, noite em cenário 42–69 → 4,3–4,4 h serial (envelope com o bench 4,3–13,3 h; 2 workers 3,6–12,0 h), caminho crítico ≈ 0,5 h; meta de < 2 h ainda a 1,8–6×
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

## Passo 3 (06/10/2026, quant-engineer): fusão exata e workers em processos

**O bench e a varredura abaixo são sintéticos, não são dado de mercado** (gerador `kb0183-shape-v2`). Só a seção de densidade lê dado real: as três sondagens da onda 0. Revisão da Astra deste passo: [[wallets-cpu-step3]].

### O que mudou, sem mudar regra

- **Passadas 1–2 no coordenador** (`stream.plan_night`): survey, entidades, apostas com o teto diário **global** por entidade/dia e sementes de taxa. A passada 3 virou função pura de um mint (`stream.replay_one`), e o fecho virou `stream.finish_night`. O `stream_snapshot` de um processo continua dobrando tudo numa contagem só; o paralelo reduz partes. Assim, o diferencial compara as duas formas.
- **Workers são processos** (`stream_parallel.stream_snapshot_parallel`, contexto `spawn`), nunca threads: o LRU de preço é por processo e os índices preguiçosos da `MintTape` não são seguros entre threads ([[wallets-cpu-step2]]).
  - Cada worker recebe a noite uma vez, no inicializador. Depois recebe só **nomes** de mint, com as apostas e as sementes daquele mint, e lê a janela pelo `fetch(nome)`, que em produção é o armazenamento.
  - A fila vai do maior custo estimado para o menor, com custo = (eventos + carry) × (1 + apostas). O custo só ordena a fila; nunca entra no resultado.
  - No máximo 2 × workers tarefas ficam em voo.
- **Mints pequenos viajam em pacote.** Medido em processo (`transport-2026-10-06-step3.txt`): o pickle de ida e volta da contagem e do carry de cada mint custou 0,53 s para os 532 mints da base e 0,20 s para os 297 do `window7`, ou 0,7–1,0 ms por mint, quase metade no coordenador. Por isso, mints consecutivos da fila viajam juntos, cada pacote com ≈ 1/16 da parte de um worker, e são reduzidos no próprio worker. Um mint grande viaja sozinho.
- **Redução exata** (`Tallies.merge`, `EntityTally.merge`, `CopyTally.merge`): somas inteiras, uniões, máximo com ausência (`None` não vira 0) e posses concatenadas. Mediana, razões e drawdown só no fim. As três chaves (livros, cópias e W-PnL) se unem separadas: só um livro cria linha, inclusive um livro sem episódio, de venda sem lote.
- **Carries:** vão ao `emit` na ordem em que os mints terminam; sem `emit`, saem na ordem da fonte, a mesma tupla do serial.
- **Falhas:** uma falha no worker, no `fetch`, no `emit` ou na checagem encerra os workers à força e relança. Eles não gravam nada, e o resultado deles é descartado. No fim normal, os workers são esperados; se um Ctrl+C cair nessa espera, eles também são encerrados antes de relançar. Nenhum processo filho sobra (duas rodadas da Astra, abaixo).
- **Exceções entre processos:** `ContractViolation` atravessa processos com o nome intacto (`__reduce__`, must-fix 1 da Astra).
- **Recusa nova `fetch_mismatch`:** o worker confere o mint e o número de eventos contra o survey. É **checagem de sanidade, não prova**. A fonte imutável durante a execução entrou no contrato (`carry.py`) como garantia externa (must-fix 2 dela).
- **Divisão do `stream.py`:** passou de 350 linhas e virou também `stream_source.py` (contrato da entrada) e `stream_links.py` (co-compras e sementes de taxa). Os nomes que o perfil do passo 1 intercepta continuam globais de `stream.py`; o perfil ganhou uma linha (apostas agora vêm por mint).

### Prova

- **Digests congelados do `84704fa1`** ([[wallets-cpu-step2]]), noite a noite, com o carry de cada noite alimentando a seguinte:
  - 2 workers em todos os mundos (4 aleatórios e o denso; 23 noites);
  - 1 worker no denso;
  - 4 workers no denso e no `random2`, com mais workers que mints em algumas noites.
- **A redução não depende de ordem.** As partes por mint, reduzidas em 50 ordens (uma delas inversa) em três mundos, dão a contagem do serial campo a campo, com as posses comparadas como multiconjunto em `float.hex`. Retrato e carry também saem iguais.
- **Concorrência real e conclusão invertida, forçadas:** 2 workers. Cada carga registra o PID do worker e espera, numa barreira de arquivo com prazo, até haver dois PIDs distintos. O mint escalado primeiro só é carregado depois que o coordenador emitiu o carry de outro mint. O teste exige dois PIDs, a conclusão invertida e retrato e carry iguais ao serial.
  - **Correção do registro (revisão de código, 06/10):** o teste antigo, com atraso aleatório de até 30 ms, **não provava concorrência**. O revisor viu um único PID rodar os três mints nas 4 sementes, porque o spawn leva segundos. Ele continua no arquivo, mas só como teste de igualdade; a prova de ordem de conclusão é o teste novo, e a de redução em qualquer ordem são as 50 permutações.
- **Falhas:** exceção comum e `ContractViolation` dentro do worker chegam ao chamador, com o nome intacto. `emit` que falha e janela adulterada (`fetch_mismatch`) param a noite. Em todos os casos, `multiprocessing.active_children() == []`. Um segundo Ctrl+C **dentro do laço de `terminate`** (pool real de 2 workers) deixava os dois vivos, segundo a revisão de código. Agora, durante a limpeza, o SIGINT é registrado e não levantado, e só é relançado quando os workers saíram. Cada worker tem 5 s de graça depois do `terminate`; o sobrevivente leva `kill`, e se ainda houver vivo a limpeza recusa com os PIDs. O `shutdown(wait=False)` do executor roda sempre. Testes com pool real que falharam antes: interrupção dentro do `terminate` (dois filhos vivos); SIGINT de verdade no meio da limpeza (escapou e abortou o pytest); `terminate` sem efeito (sobrevivente depois de 30 s). Um pool real com uma tarefa de 30 s em curso teve o primeiro `join` interrompido e todos os seguintes devolvidos na hora, o estado que o CPython 3.12 pode deixar. Mesmo assim, nenhum filho sobrou, e tudo terminou em menos de 20 s.
- **Mutação: 17 de 17 mortos.** Na primeira rodada sobreviveram três:
  - máximo com ausência;
  - contaminação das cópias;
  - livro sem episódio.

  Eles viraram um teste de operadores com valores conhecidos. Um quarto mutante, que cria livro a partir das cópias, é equivalente em entradas válidas: uma cópia exige aposta, e a aposta é compra da entidade no mint, o que sempre gera livro na mesma parte. O teste fixa o contrato mesmo assim.
- Comandos e saídas no relatório da tarefa. `uv run pytest packages/indicators` deu 1 695 passed (1 671 antes do passo, 24 novos). O teste dos digests com 2 workers leva 100–150 s: são 23 pools, de ~2–4 s cada só de spawn e imports.

### Densidade por mint (parte A): a onda 0 não guardou o necessário

A sonda (`wallet_tape_probe_stats.py`) guardava só o **conjunto** de chaves (`keys["mints"]`, `keys["pools"]`), nunca uma contagem por chave. As amostras têm 3 frames crus por programa. O que dá para tirar são **médias**, da janela válida de cada corrida:

| corrida | janela válida | mints de curva / TradeEvent | pools / swaps de pool | média por chave |
|---|---|---|---|---|
| run1 | 5 408 s | 6 674 / 335 365 | 3 342 / 667 489 | 50 por mint, 200 por pool |
| run2 | 2 344 s | 3 305 / 143 170 | 3 092 / 629 752 | 43 por mint, 204 por pool |
| run3 | 901 s | 1 434 / 55 664 | 1 767 / 262 188 | 39 por mint, 148 por pool |

Não há histograma, nem a fatia do mint mais ativo, nem quantos mints passam de 1 000 eventos em 1 h. O mint mais ativo pode ter de algumas centenas de eventos por hora até boa parte dos ≈ 350 swaps/s do programa inteiro. O `meme_trades` da VPS também não serve como substituto: é uma cópia por *polling*, só da curva, enviesada pelo radar, com 47–54 % de cobertura ([[KB-0153-o-maior-comprador-nao-estava-no-arquivo]], [[KB-0161-o-grafico-de-5-minutos-nao-existe-na-porta]]).

**Proposta mais barata, que NÃO foi rodada** (captura de rede pede autorização): `infra/scripts/research/2026-10-06-wallet-tape-density-probe.py`.

- É a mesma sonda, por RPC público e desta máquina, com mais um contador: swaps por chave por minuto. A chave é a mint da curva ou a pool da PumpSwap, sem junção pool → mint.
- Rodar **60 min**. Com 30 min sai o histograma e a fatia dos maiores, mas não a janela móvel de 60 min.
- O contador foi conferido sem rede nos 18 frames gravados: contou 11 de 11 swaps.
- O número que decide o custo é a **densidade ponderada pelas cópias**, Σn²/Σn por chave e hora: as cópias se concentram onde há mais eventos.

**Custo condicional à densidade** (`hot-mint-sweep-2026-10-06-step3.txt`): o replay de um só mint, com N eventos em 1 h, sobre o fundo da base.

| eventos em 1 h | cópias | cotações do stop | CPU do mint |
|---|---|---|---|
| 1 000 | 109 | 41 659 | 0,28 s |
| 2 000 | 187 | 148 750 | 1,64 s |
| 4 000 | 280 | 422 809 | 3,34 s |
| 8 000 | 420 | 1 128 572 | 11,59 s |
| 16 000 | 624 | 3 206 466 | 37,42 s |

- O expoente local das cotações (contagem determinística) fica entre 1,4 e 1,8. O da CPU fica entre 1,0 e 2,5, com ruído.
- As cópias do gerador crescem menos que os eventos, porque a população de compradores é limitada. Um mint real com mais compradores distintos fica mais perto de quadrático.
- **Um mint nunca se divide entre workers:** um mint quente é o caminho crítico de qualquer número de workers.

### 1 contra 2 workers (`workers-2026-10-06-step3-run3.txt`; runs 1–2 confirmam as paredes)

- **Como foi medido:**
  - modos intercalados, com a ordem alternada a cada rodada; vale a menor parede por modo;
  - CPU de cada worker lida pelo handle do processo, depois de ele sair;
  - startup = spawn + imports + noite, lido no primeiro `fetch`;
  - plano e fecho medidos em parede **e** em CPU da thread, nos dois modos;
  - os workers leem cada mint de um arquivo pickle.
- **Correções entre as rodadas:**
  - Na run 1, o meu sondador de PIDs varria a pasta dos ~1 000 arquivos de mint a cada 5 ms. Isso inflava a CPU do coordenador (9,25 s com 1 worker em `fills_16k`).
  - Nas runs 1–2, plano e fecho eram parede, e a Astra mostrou que f e k misturavam unidades.
  - A run 3 é CPU/CPU.

| config | serial (parede / CPU) | 1 worker | 2 workers | 1w/2w | serial/2w | f (CPU) | k₂ (CPU) | maior mint sozinho |
|---|---|---|---|---|---|---|---|---|
| base | 8,06 / 7,33 s | 20,42 | 11,61 | 1,76× | 0,69× | 13,9 % | 1,63 | 1,39 s |
| hot_4k | 13,85 / 12,31 s | 16,69 | 12,68 | 1,32× | 1,09× | 4,3 % | 1,10 | 7,20 s |
| triggers 0,7 | 11,70 / 10,62 s | 16,72 | 13,51 | 1,24× | 0,87× | 4,9 % | 1,38 | 2,28 s |
| fills_16k | 12,95 / 11,56 s | 18,44 | 14,39 | 1,28× | 0,90× | 8,8 % | 1,55 | 1,91 s |
| window7 | 2,30 / 2,05 s | 6,81 | 3,52 | 1,94× | 0,65× | 13,7 % | 1,38 | 0,04 s |
| janela vazia, carry grande | 3,18 / 2,84 s | 8,26 | 6,88 | 1,20× | 0,46× | 17,6 % | 1,87 | 0,07 s |

- **f** = CPU de plano + fecho ÷ CPU do serial: 23–54 µs de CPU por fill de janela.
- **k₂** = CPU de replay dos dois workers, sem o startup, ÷ CPU de replay do serial (total − plano − fecho).
- **Paredes das runs 1 e 2, nas configs com eventos:** 1w/2w de 1,19–1,52×; serial/2w de 0,50–1,00×. Com a janela vazia incluída, as faixas vão a 0,75–1,52× e 0,35–1,00×.
- **Coordenador, com 2 workers:** além do plano e do fecho, gasta 0,19–1,78 s de CPU em spawn, envio, recepção e fusão.
- **O que explica:**
  - **startup** de 1,2–3,2 s de CPU por worker, por noite, nas três rodadas. Importar o motor num interpretador novo leva 1,2–1,5 s de **parede** (`params` → `features.definitions` → `hunter_core`; `transport-2026-10-06-step3.txt`, três medidas). É a maior parte do startup, mas a parcela exata em CPU não foi medida;
  - **transporte**: o desempacotamento da janela (em processo, 0,75 s para os 27 312 eventos das janelas da base, 27 µs por evento; 12 µs no `window7`), que o serial em memória nunca paga, e as partes e carries que voltam. Por isso, numa noite só de carry, k chega a 1,9;
  - **um memo frio por processo.**

  Nessas noites de 2–14 s os custos fixos empatam com o trabalho: **dois workers só vencem o serial em memória no `hot_4k` (1,09×).**
- **Estimativa idealizada:** plano + fecho + o startup mais lento + max(replay/2, maior mint sozinho). Não é limite: um worker pode rodar enquanto o outro inicia, e o maior mint foi medido em outra chamada. A parede medida ficou 0,7–3,9 s acima dela. No `hot_4k`, o mint quente sozinho (7,2 s) domina.
- **Memória:**
  - pico do working set de cada worker: 60–102 MB nas três rodadas (o processo inteiro: interpretador, imports, noite, um pacote);
  - heap Python do coordenador (tracemalloc, run 1): serial 5,7–20,0 MB; 2 workers 6,8–33,4 MB, pelas apostas por mint e pelas partes em voo;
  - o `Entities` e os financiadores vão inteiros para cada worker. O mapa só guarda carteiras ligadas, mas o custo cresce com o número de workers.

### Extrapolação nova para 200–217 M fills de janela (cenário, não medida)

| | horas por noite |
|---|---|
| serial do passo 2 (129–265 µs/fill num núcleo) | 7,2–16,0 |
| 2 workers, modelo idealizado T2/Ts = f + (1 − f)·k₂/2 = 0,57–0,84 (run 3, configs com eventos) | 4,1–13,5 |
| trecho serial do coordenador, cenário composto (f da run 3 × Ts do passo 2) | 0,3–2,2 |
| mesmo trecho, extrapolação linear direta da CPU de plano + fecho da run 3 (23–54 µs/fill, máquina mais carregada que no passo 2) | 1,3–3,3 |
| Astra, linear das linhas `best` da run 2: parede de plano + fecho / CPU total do coordenador | 1,63–2,58 / 3,56–6,35 |

- **O modelo ignora a CPU "outra" do coordenador**, que disputa os dois núcleos com os workers. Pela vazão, T2 ≥ (CPU total − startups)/2 = 0,61–0,85 Ts nas mesmas configs: coerente com o modelo.
- **O k inclui ler a janela**, e o serial em memória não lê nada. Um serial de produção leria a fonte três vezes, então contra ele o k seria menor. Isso não foi medido: o formato do armazenamento não existe.
- **A densidade real pode mudar tudo:** o custo do stop cresce com expoente de 1,4–1,8 nos eventos por hora do mint.
- **Meta de < 2 h com 2 núcleos:** pede Ts ≤ 2,4–3,5 h, ou seja, ≤ 40–58 µs de CPU por fill no serial. Hoje são 129–265: **ainda faltam 2,2–6,7× menos trabalho por fill**, antes do efeito da densidade. E o trecho serial do coordenador, sozinho, já chega a 0,3–3,3 h, conforme a base.

### O que sobra (passo 4 e além)

1. **Medir a densidade real** (proposta acima, aguardando autorização).
2. **O stop por cópia em O(1) por evento:** o limiar inteiro de átomos por evento, se a venda líquida arredondada for monotônica, ou um núcleo inteiro que reproduza o HALF_EVEN de 28 dígitos. É isso que ataca o expoente do mint quente; worker nenhum ataca.
3. **As passadas 1–2 também são mapa por mint + redução exata.** Co-compras por mint unidas; candidatos a aposta por mint e depois os N primeiros por (entidade, dia), exato. Com o trecho serial em 0,3–3,3 h, conforme a base, essa é a próxima alavanca do lado paralelo, junto com o custo de ler a fonte duas vezes no coordenador.
4. **O transporte:** a janela pode ser lida pelo worker num formato mais barato que o pickle de `Fill`, e o worker pode gravar o carry sem passar pelo coordenador. As duas coisas dependem do desenho do armazenamento.


## Densidade real (06/10/2026, quant-engineer): uma hora do programa inteiro

**Dado real, uma hora só:** terça-feira, 06/10, das 18:47:42 às 19:49:55 UTC. Fonte: `infra/scripts/research/2026-10-06-wallet-tape-density-probe.py`, autorizado pelo orquestrador, desta máquina e só pelo WebSocket do RPC público, com uma conexão por programa. O HTTP ficou desligado: o lado HTTP do RPC público respondeu 413 de cota em 06/10. Saídas em `.claude/state/carteiras-lucro/density/run1/`; tabelas de `2026-10-06-wallet-tape-density-read.py` em `density-read.md`. Conhecimento destilado em [[KB-0187-a-densidade-por-mint-mora-em-poucas-pools]].

**A captura:**

- 3 720 s de recepção, 1 308 464 swaps com chave (352/s);
- 0 recusas, 0 suspensões, 0 desconexões, 0 descartes de fila;
- a sonda usou 39 % de um núcleo.

A chave é a mint da curva ou a pool da PumpSwap, sem junção pool → mint. 516 769 swaps (39,5 %) são compras de pool chaveadas pela pool **inferida**, isto é, pela leitura do layout do `BuyEvent` conferida em [[KB-0184-o-buyevent-da-pumpswap-e-as-armadilhas-de-ler-eventos-do-programa-inteiro|KB-0184]].

**A hora mais cheia de cada chave** (janela deslizante exata de 60 min):

| eventos na hora | chaves de curva | eventos da curva | chaves de pool | eventos das pools | chaves, tudo | eventos, tudo |
|---|---|---|---|---|---|---|
| 1–9 | 4 690 | 4,3 % | 3 036 | 0,7 % | 7 726 | 1,4 % |
| 10–99 | 1 303 | 18,2 % | 657 | 1,7 % | 1 960 | 4,9 % |
| 100–999 | 441 | 53,6 % | 257 | 8,3 % | 698 | 17,0 % |
| 1 000–3 999 | 33 | 22,1 % | 144 | 29,2 % | 177 | 27,9 % |
| 4 000–15 999 | 1 | 1,8 % | 52 | 40,5 % | 53 | 33,1 % |
| ≥ 16 000 | 0 | 0 | 5 | 19,5 % | 5 | 15,8 % |

| | chaves | maior chave na hora | fatia da maior | fatia das 10 maiores | ≥ 1 000/h | ≥ 4 000/h | mediana | Σn²/Σn |
|---|---|---|---|---|---|---|---|---|
| curva | 6 468 | 4 512 | 1,8 % | 10,5 % | 34 | 1 | 2 | 738 |
| pool | 4 151 | 124 069 | 11,8 % | 26,7 % | 201 | 57 | 2 | 20 904 |
| tudo | 10 619 | 124 069 | 9,6 % | 21,6 % | 235 | 58 | 2 | 17 062 |

- **A densidade mora em poucas pools.** As 10 chaves mais cheias são pools. A maior teve **124 069 eventos na hora** (9,6 % de tudo, até 3 140 por minuto); da 2.ª à 10.ª, 14–25 mil cada.
- **Densidade ponderada por evento.** O evento médio vive numa chave com **17 062 eventos por hora** (Σn²/Σn), enquanto a chave mediana tem 2. Isso **não** é a hora que uma cópia típica varre. As cópias nascem de apostas elegíveis: a primeira compra ≥ 0,1 SOL de cada entidade no mint, sob o teto diário. Uma pool de 124 mil swaps de poucos robôs, ou de compras abaixo do piso, pesa muito em Σn²/Σn e pode dar zero apostas (Astra). A densidade por cópia pede apostas elegíveis por chave, que não foram medidas.
- **A curva é barata:** nenhum mint da curva passou de 4 512 por hora.

**Custo da noite com essa densidade (CENÁRIO).** Cada chave-hora é cotada na curva medida de um mint só (a varredura do passo 3, acima: sintética): linear abaixo de 1 000/h, log-log entre os pontos medidos e, além de 16 000/h, o expoente 1,51–1,69 dos últimos pontos.

| | valor |
|---|---|
| CPU de uma hora do programa (máquina da varredura) | 2 070–2 455 s, contra 365 s se todo evento custasse como num mint de 1 000/h: **M = 5,7–6,7×** (curva 1,31×, pools 6,7–8,0×) |
| só a maior pool, por hora de atividade | 819–1 194 s, 40–49 % da hora inteira |
| serial por noite (janela de 7 d ≈ 168 h × 352/s ≈ 213 M fills): direto, 168 × custo da hora | **97–115 h** |
| serial por noite: M × serial do passo 2 (7,2–16,0 h) | 41–108 h |
| 2 workers (× 0,57–0,84, passo 3) | 55–96 h sobre a projeção direta; 23–90 h sobre a razão. **Envelope das duas bases: 23–96 h**, não uma conta só |
| caminho crítico, se a maior pool ficar assim a janela toda (168 × 819–1 194 s, num worker só) | 38–56 h |

- **A meta de < 2 h com 2 núcleos fica a ≈ 12–48× de distância nesse cenário** (serial de 41–115 h contra os 2,4–3,5 h que a meta permite, com o f e o k do passo 3). O trabalho é o stop por cópia num punhado de pools, e um mint não se divide entre workers. **Mais workers não resolvem.**
- **O que resolve é o passo 4:** o stop em O(1) por evento, com o limiar inteiro de átomos se a venda líquida arredondada for monotônica. Sem ele, só uma decisão do Everton sobre o universo, por exemplo um teto de eventos por mint ou fora as pools de robô, que é versão nova do protocolo.

**Limites desta leitura:**

1. **Uma hora**, num dia e num horário. A forma pode mudar com o dia.
2. A curva de custo é **sintética**: as cópias do gerador crescem menos que os eventos.
   - Não sabemos quantas entidades distintas compram ≥ 0,1 SOL nas pools quentes. Uma pool de 124 mil eventos pode ser um laço de poucos robôs, com poucas cópias; mesmo assim, cada cópia varreria a hora inteira.
   - As 5 chaves acima de 16 000/h ficam fora da faixa medida (até 7,75×) e pesam **50–58 % do custo** do cenário (Astra; recalculado com os expoentes exatos, 1,506 e 1,691).
   - Por isso o cenário **pode errar para os dois lados**: para baixo, se as pools quentes tiverem muitos compradores distintos; para cima, se forem laços de robô com poucas apostas elegíveis.
3. **Pool e curva são chaves separadas.** Juntar as duas fitas de um mint graduado acrescenta no máximo os eventos da curva, que são poucos.
4. 39,5 % dos **swaps com chave** (não das chaves) são compras de pool chaveadas pela inferência do layout.

Próximos passos possíveis:

- medir entidades distintas por pool quente: precisa guardar carteira por chave, e a sonda guarda só contagens;
- repetir a captura em outro dia;
- escolher entre o passo 4 e a mudança de universo.


## Passo 4 (09/10/2026, quant-engineer): o stop por limiar inteiro

**Tudo o que é bench abaixo é sintético, não é dado de mercado** (gerador `kb0183-shape-v2`). Só a densidade dos cenários é real: a hora de 06/10 do [[KB-0187-a-densidade-por-mint-mora-em-poucas-pools]]. Revisão da Astra deste passo: [[wallets-cpu-step4]]. Nenhuma regra mudou e o universo é o mesmo.

### Prova primeiro: a venda líquida arredondada é monotônica nos átomos?

**Só numa região, e a região contém a escala de produção.** Testes em `test_wallets_stops_monotone.py`; a Astra conferiu a prova contra o código.

- **Pool (inteiros): sim, sempre.** `bruto = min(Q·a // (T + a), S)` não decresce em `a`, qualquer que seja o sinal da cotação virtual. `líquido = bruto − ⌈bruto·b/10⁴⌉ = ⌊bruto·(10⁴ − b)/10⁴⌋` não decresce para `0 ≤ b < 10⁴` (LP, protocolo, criador e cashback somados no `fee_bps`). Nenhuma recusa.
- **Curva (Decimal, 28 dígitos, HALF_EVEN): sim, se `sol·átomos < 10²⁸`, `token + átomos < 10²⁸` e `0 ≤ real < sol`.** Aí o produto e a soma são exatos, e o quociente é o arredondamento correto de um racional crescente. O `× 10⁹` só acrescenta zeros; o piso e a taxa mantêm a ordem; a recusa de reserva virtual esgotada fica impossível. Para `sol` abaixo de 10 000 SOL virtuais, a região cobre 10¹⁵ átomos, a oferta inteira (o maior virtual registrado em `curve.py`, num Mayhem, foi de 1 977 SOL).
- **Fora da região: não.** Uma busca dirigida achou vendas que **caem** um lamport entre átomos consecutivos (`sol ≈ 5,7·10²¹` lamports, `sol·átomos` com 44 dígitos): `…479, …479, …478, …478, …479` de `a` a `a + 4`. O caso está fixado em teste.
- **Grades:** 3 000 pools (cotação real de 1 lamport a 10⁸ SOL, base de 1 a 10²⁴ átomos, virtual negativa, zero e positiva) e 3 000 curvas (de 2 lamports a 10¹⁴, real em todo `[0, sol)`); dez taxas de 0 a 9 999 bps; pares aleatórios e janelas de átomos consecutivos, inclusive na borda da região.

### A mudança (uma só): `stops.py`

- **Por evento e piso**, o maior número de átomos cuja venda fica ≤ piso (`stop_limit`). Ele vem de um palpite inteiro pelo inverso, **certificado por cotações do próprio `sell_lamports`** (`líquido(c) ≤ F < líquido(c + 1)`) e reparado por galope e busca binária quando o palpite erra. A exatidão depende só da monotonia.
  - **O palpite erra de verdade dentro da região:** em curvas extremas (`sol = 17` lamports, `token ≈ 1,6·10²⁶`), o arredondamento põe o limite um átomo abaixo. É o único mutante que exigiu um caso achado por busca.
  - Na escala de produção, palpite e limite coincidiram em 200 000 estados.
- **Cópia com `1 ≤ átomos ≤ região do evento`:** para sse `átomos ≤ limite`. Acima da região, a cotação Decimal antiga, com as recusas. A curva completa nunca para; uma pool marcada `complete` continua cotada (bug achado na autorrevisão e confirmado pela Astra antes de qualquer número).
- **Índice preguiçoso por (fita, piso):** cada evento é resolvido uma vez, na primeira cópia que chega nele. Blocos de 64 guardam o maior limite e a menor região; um bloco é pulado sse `átomos > maior limite` e `átomos ≤ menor região`. `_find_exit` pula até a próxima parada, passa cada parada por `_landing`, troca o `best` só com pouso estritamente anterior e então encolhe o fim da janela.

### Prova de equivalência

- **Digests congelados do `84704fa1`** ([[wallets-cpu-step2]]) iguais. `uv run pytest packages/indicators`: 1 730 passed (1 700 antes, 30 novos).
- **Diferencial contra uma cópia congelada do laço antigo** (cotação Decimal por cópia e evento):
  - 6 sementes × 400 cópias, em fitas com curvas, pools de virtual negativa, zero e positiva, curvas completas, estados fora da região, vários eventos no mesmo slot e recebimento atrasado;
  - duas políticas (dois pisos) na mesma fita;
  - mais uma fita com estado recusável: a mesma `ValueError`, mensagem incluída.
- **Casos dirigidos** (`test_wallets_stops_index.py`): exatamente no limiar; um bloco cujo único impedimento ao salto é a menor região; uma recusa dentro de um bloco; início desalinhado e cauda parcial; piso fracionário negativo; átomos acima da sentinela.
- **Trabalho:** 300 cópias numa fita de 12 000 eventos que não para ninguém. O laço antigo faria > 100× mais cotações; o índice faz ≤ 3 por evento.
- **Mutação: 15 de 15 mortos** numa cópia do pacote. Lista e saída no relatório da tarefa. A Astra aprovou o diff na rodada 2 ([[wallets-cpu-step4]]).
- **Digests do replay da chave quente** iguais antes e depois em todos os pontos das varreduras, e **digest da noite** igual nas 6 configurações do bench (serial, 1 e 2 workers).

### Antes e depois: uma chave quente (`2026-10-09-wallets-stop-sweep.py`)

A varredura do passo 3 não conseguia pôr mais de ≈ 18 mil eventos numa hora, e o venue do mint quente ficava por sorteio. A nova reconstrói a chave quente depois de gerar: até 14 eventos por slot, e o mesmo passeio de preço cotado como curva ou como pool. São duas formas de passeio:

- **por evento:** o do gerador; a distância até o stop é um número fixo de eventos;
- **no tempo:** o passo dividido pela densidade, o que dá o mesmo caminho de preço no tempo. É o caso que a curva de custo do passo 3 supunha: a cópia varre mais eventos onde há mais eventos.

Antes = motor congelado do HEAD (`PYTHONPATH` para uma cópia do `git archive`), na mesma máquina e no mesmo dia. CPU com a máquina compartilhada; as contagens são determinísticas.

| chave, eventos em 1 h | cópias | cotações do stop antes → depois | CPU antes → depois | razão |
|---|---|---|---|---|
| pool, 16 000 (por evento) | 628 | 3 259 032 → 31 974 | 15,53 → 1,16 s | 13× |
| pool, 64 000 (por evento) | 1 657 | 23 644 526 → 127 900 | 104,75 → 5,27 s | 20× |
| pool, 124 000 (por evento) | 2 934 | 44 812 148 → 247 806 | 200,23 → 10,83 s | 18× |
| curva, 32 000 (por evento) | 997 | 9 779 458 → 63 942 | 127,77 → 3,62 s | 35× |
| pool, 64 000 (no tempo) | 1 657 | 43 106 071 → 127 900 | 188,42 → 4,86 s | 39× |
| pool, 124 000 (no tempo) | 2 934 | — → 247 806 | não medido → 11,39 s | — |

- **A chave quente ficou quase linear.** Expoentes locais da CPU, de 16 mil a 124 mil/h:
  - depois: 0,9–1,3;
  - antes, passeio por evento: 1,5 → 1,2 → 1,0. As cópias param depois de um número fixo de eventos;
  - antes, passeio no tempo: 1,5 → 1,7 → 1,9, de 4 mil a 64 mil. É o caso que cresce.

  Arquivos `stop-sweep-2026-10-09-{before,after}-{pool,curve}[-timewalk].txt`.
- **O que sobra na chave de 124 mil/h** (cProfile, passeio no tempo, 31,6 s instrumentados):
  - a resolução única dos limites, 3,8 s;
  - a caminhada por blocos, ≈ 4,3 s;
  - o resto é trabalho linear: E-PnL (`window_books`) 7,9 s, FIFO 5,7 s, entre outros.

### Antes e depois: a noite inteira do bench (`workers-2026-10-09-step4-{before,after}.txt`, pareado em `…-paired.md`)

Antes e depois rodaram ao mesmo tempo, então as razões valem mais que os absolutos.

| config | fills de janela | CPU serial antes → depois | razão | µs CPU/fill antes → depois | f depois | k₂ depois | T2/Ts (modelo) |
|---|---|---|---|---|---|---|---|
| base | 18 852 | 7,00 → 3,61 s | 1,94× | 371 → 191 | 15,2 % | 1,78 | 0,90 |
| hot_4k | 22 852 | 12,61 → 4,31 s | 2,92× | 552 → 189 | 14,1 % | 1,62 | 0,84 |
| triggers 0,7 | 18 852 | 10,83 → 4,17 s | 2,60× | 574 → 221 | 14,2 % | 1,74 | 0,89 |
| fills_16k | 31 087 | 11,98 → 6,75 s | 1,78× | 386 → 217 | 14,8 % | 1,65 | 0,85 |
| window7 | 11 624 | 2,75 → 2,05 s | 1,34× | 237 → 176 | 16,0 % | 1,69 | 0,87 |
| janela vazia, carry grande | 0 | 3,39 → 3,38 s | 1,00× | — | 14,4 % | 2,05 | 1,02 |

- **O stop deixou de dominar.** Depois do passo 4 (`profile-2026-10-09-step4-after.txt`; só as fatias valem, a máquina estava carregada pela mutação), as cópias ficam com 26–32 % do tempo (11 % em `history_5d`) e o E-PnL com 26–43 %.
- **Dois workers ficaram relativamente piores:** k₂ subiu de 1,10–1,87 (passo 3) para 1,62–2,05. O replay ficou mais barato, mas o desempacotamento da janela pelo worker (≈ 27 µs por evento, medido no passo 3) não mudou e agora pesa tanto quanto o próprio replay.

### Extrapolação nova para 200–217 M fills por noite (cenário, não medida)

| base | serial (1 núcleo) | 2 workers (× 0,84–0,90) | caminho crítico (a maior chave, 168 h) |
|---|---|---|---|
| densidade real × curva da chave quente, passeio por evento (`2026-10-09-wallets-night-scenario.py`) | 42,2 → **4,26 h** | **3,6–3,8 h** | 9,35 → **0,51 h** |
| idem, passeio no tempo (antes: 124 mil/h extrapolado de 32→64 mil) | 69,1 → **4,38 h** | **3,7–3,9 h** | 31,1 → **0,53 h** |
| µs/fill do bench pareado (176–221 depois; 237–574 antes) | 13,2–34,6 → **9,8–13,3 h** | **8,2–12,0 h** | — |

- **Conferência do método:** o mesmo script com a varredura do passo 3 dá 114,6 h e 1 194 s/h na maior pool, o teto dos 97–115 h e 819–1 194 s/h do [[KB-0187-a-densidade-por-mint-mora-em-poucas-pools]].
- **Por que as duas bases discordam (2–3×):**
  - o cenário ignora plano e fecho (f ≈ 14–16 %) e o custo fixo por chave: a chave mediana tem 2 eventos por hora e é cotada linearmente a partir do ponto de 1 000/h. Ele é otimista;
  - o µs/fill do bench é a mistura do gerador, com tudo dentro, numa máquina carregada.
- **Envelope: serial 4,3–13,3 h; 2 workers 3,6–12,0 h.**
- **A meta de < 2 h com 2 núcleos ainda não foi atingida: faltam ≈ 1,8–6×.** Mas o que era superlinear acabou: o caminho crítico caiu de 9–56 h para ≈ 0,5 h, e mais trabalho por worker agora reduz a noite.

### O que sobra (passo 5 e além; nada disso foi feito)

1. **Transporte da janela:** k₂ = 1,6–2,0. Um formato mais barato que o pickle de `Fill`, lido pelo worker, é a alavanca do lado paralelo (passo 3, item 4).
2. **E-PnL:** 26–43 % do tempo. É uma liquidação por posse e por fronteira, trabalho necessário. O núcleo inteiro da cotação de curva (a opção 3 desta proposta, não feita) voltaria a fazer sentido ali.
3. **Passadas 1–2 como mapa por mint + redução exata:** f ≈ 14–16 % (passo 3, item 3).
4. **Segundo nível do índice** (sugestão da Astra): ≈ 1–2 % da hora do programa na medida de hoje. Fica para depois.
5. **Medir a densidade de novo**, com apostas elegíveis por chave: a curva de custo por chave continua sintética nas cópias.
