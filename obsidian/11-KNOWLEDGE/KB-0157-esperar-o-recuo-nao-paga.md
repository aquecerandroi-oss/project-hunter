---
tags: [knowledge, meme, mesa-real, entrada, recuo, hipotese, metodo, m4]
tema: esperar um recuo de 3–12 % em 20–60 s depois do sinal não paga — melhora um pouco o preço das entradas, mas perde as vencedoras que não recuam e não livra das perdas que caem desde a compra
fonte: R77 (`.claude/state/notes-R77.md`) — H-016 da Fila de Hipóteses (23/09/2026)
fonte_url:
lido_em: 2026-09-23
evidencia: medição própria — 65 decisões reais e 486 de papel da porta `fluxo_e_holders` (uma por mint, 12–24/09/2026), replay trade a trade da fita com a cadeia "sem nós", simulador do R72 sem alteração, moinho `run_hypothesis` emparelhado por mint; 46 testes de anti-antecipação
hipotese_testavel: sim
astra: concorda (duas rondas; 7 correções de desenho antes de correr, 1 defeito numa sensibilidade e 3 de redação no veredito)
status: vivo
owner: sexta-feira
updated: 2026-09-23
confiança: "?"
tipo: pesquisa
hipotese: H-016
variavel: politica de entrada com recuo (esperar queda de X% a partir da maxima, comprar no toque)
populacao: decisoes reais/papel da porta fluxo_e_holders com fita retrospectiva
efeito: melhor celula X=3%/W=60s: reais +1,99pp, papel +2,28pp
ic: reais [-3,60, +7,48]; papel [+0,69, +3,89]
veredito: refuta
proximo_passo: ganho de preco na entrada (sem esperar recuo grande) virou H-017, julgada em coorte nova
classe_de_perda: —
mercado: meme
---

# KB-0157 — Esperar o recuo não paga

> **H-016 (entrar no recuo, não no pico): `REFUTA`**, pelas cláusulas (a) e (b), nas duas populações.
> Estudo em `.claude/state/notes-R77.md`; pré-registo em [[Fila de Hipoteses]] § H-016.

## O que afirma

A ideia era esta: a porta compra no auge do fluxo, que é o topo local, e por isso esperar a primeira correção
depois do sinal daria uma entrada melhor. Medido, isso **não entrega a vantagem prevista** (+5 pp por SOL
decidido).

O pouco que existe (≈ +2 pp contra comprar logo) vem do preço um pouco melhor nas entradas. Esse ganho é
comido pelas vencedoras que nunca recuam e, por isso, ficam de fora. A política empata com "não comprar
nada".

## Onde foi mostrado

**Onde e quando:** mesa de memes pump.fun, 12 a 24/09/2026, porta `fluxo_e_holders`. Uma decisão por mint, a
primeira no tempo.
- **Reais:** 85 decisões, das quais 65 com fita até à saída.
- **Papel:** 596 decisões, das quais 486 com fita até à saída.

**Regra testada:** depois da aprovação em `t0`, comprar no primeiro trade que fique X % abaixo da máxima
desde `t0`, com validade de W s. Se não recuar, não compra (retorno 0).
- Grade: X ∈ {3, 5, 8, 12} %, W ∈ {20, 60} s.
- Controlo: comprar em `t0`.
- Os dois braços usam o mesmo modelo: pouso 1,6 s depois do gatilho e custo de 2,23 % por ida e volta.
- A saída é a regra congelada (1,15× · recuo 10 % · 300 s), contada a partir da entrada nova.

| | reais (n = 65) | papel (n = 486) |
|---|---|---|
| melhor célula | X 3 %, W 60 s (borda da grade) | X 3 %, W 60 s (borda) |
| D contra o controlo | **+1,99 pp** [−3,60, +7,48], p 0,50 | **+2,28 pp** [+0,69, +3,89], p 0,0065, Holm 0,052 |
| a 5 s de atraso | +1,11 pp | +1,51 pp |
| contra "não comprar nada" | +2,39 % [−1,87, +6,66] | **+0,08 %** [−1,70, +1,87] |
| vitórias do controlo perdidas por não entrar | 5 de 30 | 15 de 181 |
| com X 12 %, W 20 s | perde **25 de 30** vitórias | perde **146 de 181** |

**Leitura:**
- No papel, a vantagem de +5 pp fica **excluída** na análise principal (com o horizonte fixo de 370 s o IC
  chega a +5,38).
- Nas reais, a incerteza continua larga e não exclui +5 pp.
- Nenhuma célula tem IC inferior acima de +1 pp.

## O que se aprendeu

1. **Não entrar custa, não protege.** Em quase todas as células, a parte do D que vem das decisões sem entrada
   é **negativa**: as moedas que sobem sem olhar para trás são as que batem o alvo. Com X grande, o filtro
   "só compra se recuar" é um filtro contra vencedoras.
2. **O ganho, quando existe, é de preço.** No papel, +2,18 dos +2,28 pp vêm das entradas, e só +0,10 pp de
   ficar de fora. É esperar alguns segundos por um preço um pouco melhor, não evitar as moedas más.
3. **As perdas que "caem desde a compra" não somem.** Na melhor célula das reais continuam a ser **16 de 65**
   decisões, as mesmas do controlo. A fração entre as perdas até sobe (0,46 → 0,62), porque as outras perdas
   diminuem. O recuo de alguns por cento nos primeiros segundos acontece **tanto** nas vencedoras **como** nas
   perdedoras: quem compra no recuo apanha a queda que continua tão frequentemente quanto quem compra no pico.
4. **O modelo é otimista em relação à mesa.** Nas mesmas 65 reais, o controlo modelado rende +0,41 % por SOL e a
   realidade rendeu −5,42 %. A diferença vem do aluguel de ATA (≈ 2,8 pp) e das saídas históricas e execução
   (≈ 3,2 pp); o modelo de entrada coincide com o simulador do R72 no fill real (correlação 0,90). Um ganho
   relativo de 2 pp não atravessa essa distância.
5. **Na pista de eventos (o que opera hoje) o sentido é o mesmo, sem confirmação.** Reais, n = 53: X3 W60 +3,70 pp
   [−2,70, +10,14]. Papel, n = 162: +3,04 pp [−0,15, +6,08].

## Como mediríamos aqui

Já está medido; o código fica em `.claude/state/r77/`. O que foi preciso:
- **Cadeia de reservas "sem nós":** foto `solana_rpc` antes de `t0` como âncora, mais as trocas alheias; as
  fotos são descontadas das nossas próprias trocas.
- **Os nossos fills que faltam no arquivo por polling** (19 de 85 reais) injetados a partir de
  `meme_live_positions.entry/exit`. Onde existem na fita, batem ao lamport com esse registo (144 de 144).
- **Regra de entrada que só lê a cadeia por um cursor.** O batoteiro que olha o ponto seguinte é apanhado,
  inclusive nas cadeias reais.

## Hipótese testável no Lab

**Nenhum braço de papel é proposto** (a H-016 não confirmou).

Pista exploratória, que não é confirmação: o ganho de preço com X pequeno. Uma sucessora teria de:
- ser congelada numa coorte futura sem os mints do R77;
- comparar também com uma espera simples de N segundos, sem condição de recuo;
- exigir resultado líquido útil **contra não comprar**.

Registá-la é decisão do coordenador.

## Por que pode falhar (limites desta nota)

- **Observabilidade.** O replay assume que a fita WS entrega cada troca no seu `block_time`. A fita usada vem do
  arquivo por polling (~44 s de atraso de chegada, R73). A guarda impede ler o futuro da cadeia modelada, não
  prova a latência do WS.
- **"Sem nós" é replay contábil aproximado:** as trocas alheias ficam com os montantes históricos.
- **Censura.** Só entram decisões com fita sem buracos > 60 s até à saída de todos os braços. A regra foi
  revista depois de ver as contagens, e antes de ver retornos; o efeito vale para as decisões observáveis.
- **As reais já tinham sido olhadas** na anatomia que originou a hipótese. As duas populações partilham mints.

## Segunda opinião (Astra)

- **Antes de correr**, 7 correções de desenho:
  - nossa troca a faltar na fita (verificou-se: 19 de 85);
  - ordem dentro do slot;
  - fotos não disparam;
  - relógio da compra materializado no pouso;
  - censura comum;
  - o 0 é o retorno da política, não a diferença;
  - fração das perdas definida por braço.
- **No veredito:**
  - reproduziu o `REFUTA` nas duas populações (Holm 0,052);
  - achou um defeito na sensibilidade "estado final do slot" (uma foto escondia o slot), corrigido com teste e
    sem mudar a linha principal;
  - pediu que o `REFUTA` literal fosse escrito ao lado da leitura estatística;
  - pediu que o +2 pp fosse tratado como pista, não confirmação.
- **Discordância registada:** ela sugeria o rótulo "REFUTA operacional; evidência distinta por população".
  Ficou `REFUTA` (a fila tem três rótulos), com a distinção por população escrita ao lado.

## Relacionados

[[Fila de Hipoteses]] (H-016) · [[KB-0149-o-que-a-mesa-real-ensinou]] (§17: o segundo de entrada decide a
aposta) · [[KB-0154-subir-o-alvo-nao-paga]] · [[KB-0152-a-oscilacao-existe-o-giro-nao-paga]] ·
[[KB-0153-o-maior-comprador-nao-estava-no-arquivo]] · [[Strategy Backlog]]
